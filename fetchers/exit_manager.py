import os
import json
import sqlite3
import httpx
import time
from web3 import Web3
from fetchers.shadow_ledger import DB_PATH, init_db
from fetchers.chain_config import get_chain
from fetchers.prompt_optimizer import propose_prompt_update
from fetchers.aerodrome_router import get_onchain_price_and_min_out, execute_aerodrome_swap, AERODROME_ROUTER_ADDRESS

CFG = get_chain()
W3 = CFG["w3"]
CHAIN_ID = CFG["chain_id"]
EXPLORER = CFG["explorer"]

ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"}]')
SPACE_TO_ADDRESS = {space: data["address"] for space, data in CFG["tokens"].items()}

async def check_and_execute_exits():
    init_db()
    private_key = os.environ.get("BASE_PRIVATE_KEY")
    if not private_key: return

    account = W3.eth.account.from_key(private_key)
    wallet_address = account.address
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT proposal_id, space, token_id, entry_price, target_price, ai_score FROM alpha_signals WHERE status = 'OPEN'")
    open_positions = cursor.fetchall()

    if not open_positions:
        conn.close()
        return

    for pos in open_positions:
        proposal_id, space, token_id, entry_price, target_price, ai_score = pos
        space_lower = space.lower()
        token_address = SPACE_TO_ADDRESS.get(space_lower)
        if not token_address: continue

        token_contract = W3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
        try:
            balance = token_contract.functions.balanceOf(wallet_address).call()
        except Exception: continue
        if balance == 0: continue

        stop_loss_price = entry_price * 0.90
        current_price = 0
        
        # 🚀 PHASE 16 UPGRADE: Replaced CoinGecko with GeckoTerminal for instant, Base-accurate pricing
        try:
            async with httpx.AsyncClient() as client:
                # GeckoTerminal is geo-permissionless and updates Base micro-caps instantly
                url = f"https://api.geckoterminal.com/api/v2/networks/base/tokens/{token_address}"
                resp = await client.get(url, timeout=5, headers={"Accept": "application/json"})
                if resp.status_code == 200:
                    data = resp.json().get("data", {}).get("attributes", {})
                    current_price = float(data.get("token_price_usd", 0))
        except Exception as e:
            print(f"[EXIT] ⚠️ Price fetch failed for {space}: {e}")
            continue
            
        if current_price == 0: continue

        if current_price >= target_price or current_price <= stop_loss_price:
            action_type = "TAKE PROFIT" if current_price >= target_price else "STOP LOSS"
            print(f"[EXIT] 🚨 {action_type} TRIGGERED on {space.upper()}! | Current: ${current_price:.6f} | Entry: ${entry_price:.6f}")

            try:
                # 1. Approve the Aerodrome V2 Router
                nonce = W3.eth.get_transaction_count(wallet_address)
                approve_txn = token_contract.functions.approve(AERODROME_ROUTER_ADDRESS, balance).build_transaction({
                    'from': wallet_address, 
                    'gas': 100000, 
                    'gasPrice': int(W3.eth.gas_price * 1.1), 
                    'nonce': nonce, 
                    'chainId': CHAIN_ID
                })
                signed_appro = W3.eth.account.sign_transaction(approve_txn, private_key)
                appro_hash = W3.eth.send_raw_transaction(signed_appro.rawTransaction)
                W3.eth.wait_for_transaction_receipt(appro_hash, timeout=60)
                print(f"[EXIT] ✅ Approved Aerodrome Router | TX: {W3.to_hex(appro_hash)}")

                # 2. Calculate exact on-chain slippage protection (1.5% tolerance)
                expected_out, min_out_wei = get_onchain_price_and_min_out(token_address, balance, slippage_bps=150)
                
                if min_out_wei == 0:
                    print(f"[EXIT] ❌ CRITICAL: Aerodrome liquidity too low or pool mismatch for {space}. Aborting swap to prevent MEV sandwich.")
                    continue

                # 3. Execute MEV-Protected Aerodrome Swap
                swap_hash_hex = execute_aerodrome_swap(private_key, token_address, balance, min_out_wei)
                
                if swap_hash_hex:
                    print(f"[EXIT] 🛡️ MEV-PROTECTED EXIT EXECUTED! SOLD {space.upper()} | TX: https://{EXPLORER}/tx/{swap_hash_hex}")
                    
                    cursor.execute("UPDATE alpha_signals SET status = 'CLOSED' WHERE proposal_id = ?", (proposal_id,))
                    conn.commit()
                    
                    # Phase 14: Trigger Self-Learning Optimizer
                    await propose_prompt_update(proposal_id, space, ai_score, entry_price, current_price)
                else:
                    print(f"[EXIT] ❌ Aerodrome Swap Reverted for {space}. Check logs.")

            except Exception as e:
                print(f"[EXIT] ❌ Error executing sell for {space}: {e}")
                
    conn.close()
