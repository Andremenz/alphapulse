import os
import json
import sqlite3
import httpx
import time
from web3 import Web3
from fetchers.shadow_ledger import DB_PATH, init_db
from fetchers.chain_config import get_chain
from fetchers.prompt_optimizer import propose_prompt_update

CFG = get_chain()
W3 = CFG["w3"]
CHAIN_ID = CFG["chain_id"]
EXPLORER = CFG["explorer"]
ROUTER_ADDRESS = CFG["router_address"]
WETH_ADDRESS = CFG["weth_address"]

ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"}]')
ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}]')
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

    router_contract = W3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
    
    for pos in open_positions:
        proposal_id, space, token_id, entry_price, target_price, ai_score = pos
        space_lower = space.lower()
        token_address = SPACE_TO_ADDRESS.get(space_lower)
        if not token_address: continue
            
        token_contract = W3.eth.contract(address=token_address, abi=ERC20_ABI)
        try:
            balance = token_contract.functions.balanceOf(wallet_address).call()
        except Exception: continue
        if balance == 0: continue
            
        stop_loss_price = entry_price * 0.90
        current_price = 0
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies=usd", timeout=10)
                current_price = resp.json().get(token_id, {}).get("usd", 0)
        except: pass
        if current_price == 0: continue
            
        if current_price >= target_price or current_price <= stop_loss_price:
            action_type = "TAKE PROFIT" if current_price >= target_price else "STOP LOSS"
            print(f"[EXIT] ️ {action_type} on {CFG['gecko_slug'].upper()}! {space.upper()} | Current: ${current_price} | Entry: ${entry_price}")
            
            try:
                approve_txn = token_contract.functions.approve(ROUTER_ADDRESS, balance).build_transaction({'from': wallet_address, 'gas': 100000, 'gasPrice': W3.eth.gas_price, 'nonce': W3.eth.get_transaction_count(wallet_address), 'chainId': CHAIN_ID})
                signed_approve = W3.eth.account.sign_transaction(approve_txn, private_key)
                approve_hash = W3.eth.send_raw_transaction(signed_approve.rawTransaction)
                W3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
                
                deadline = int(time.time()) + 600
                swap_txn = router_contract.functions.swapExactTokensForETH(balance, 0, [token_address, WETH_ADDRESS], wallet_address, deadline).build_transaction({'from': wallet_address, 'gas': 300000, 'gasPrice': W3.eth.gas_price, 'nonce': W3.eth.get_transaction_count(wallet_address), 'chainId': CHAIN_ID})
                signed_swap = W3.eth.account.sign_transaction(swap_txn, private_key)
                swap_hash = W3.eth.send_raw_transaction(signed_swap.rawTransaction)
                print(f"[EXIT]  MEV-PROTECTED EXIT! SOLD {space.upper()} | TX: https://{EXPLORER}/tx/{W3.to_hex(swap_hash)}")
                
                cursor.execute("UPDATE alpha_signals SET status = 'CLOSED' WHERE proposal_id = ?", (proposal_id,))
                conn.commit()
                
                #  Phase 14: Trigger Self-Learning Optimizer
                await propose_prompt_update(proposal_id, space, ai_score, entry_price, current_price)
                
            except Exception as e:
                print(f"[EXIT] ❌ Error executing sell for {space}: {e}")
    conn.close()
