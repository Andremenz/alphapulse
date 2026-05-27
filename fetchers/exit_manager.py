import os
import json
import sqlite3
import httpx
import time
from web3 import Web3
from fetchers.shadow_ledger import DB_PATH, init_db

BASE_RPC_URL = "https://mainnet.base.org"
W3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
ROUTER_ADDRESS = Web3.to_checksum_address("0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24")
WETH_ADDRESS = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")

ERC20_ABI = json.loads('[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"}]')
ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForETH","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}]')

SPACE_TO_ADDRESS = {
    "aerodrome": Web3.to_checksum_address("0x940181a94A35A4569E4529A3CDfB74e38FD98631"),
    "baseswap": Web3.to_checksum_address("0x78a087d713Be963Bf307B18F2Ff8122EF9A63ae9"),
    "brett": Web3.to_checksum_address("0x532f27101965dd16442E59d40670FaF5eBB142E4"),
}

async def check_and_execute_exits():
    # 🛡️ FIX: Initialize DB immediately to prevent "no such table" crash
    init_db()

    private_key = os.environ.get("BASE_PRIVATE_KEY")
    if not private_key:
        return
        
    account = W3.eth.account.from_key(private_key)
    wallet_address = account.address
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT proposal_id, space, token_id, entry_price, target_price FROM alpha_signals WHERE status = 'OPEN'")
    open_positions = cursor.fetchall()
    
    if not open_positions:
        conn.close()
        return

    router_contract = W3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
    
    for pos in open_positions:
        proposal_id, space, token_id, entry_price, target_price = pos
        space_lower = space.lower()
        token_address = SPACE_TO_ADDRESS.get(space_lower)
        
        if not token_address:
            continue
            
        token_contract = W3.eth.contract(address=token_address, abi=ERC20_ABI)
        try:
            balance = token_contract.functions.balanceOf(wallet_address).call()
        except Exception:
            continue
            
        if balance == 0:
            continue
            
        stop_loss_price = entry_price * 0.90
        
        current_price = 0
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies=usd", timeout=10)
                current_price = resp.json().get(token_id, {}).get("usd", 0)
        except:
            pass
            
        if current_price == 0:
            continue
            
        if current_price >= target_price or current_price <= stop_loss_price:
            action_type = "TAKE PROFIT" if current_price >= target_price else "STOP LOSS"
            print(f"[EXIT] 🚨 {action_type} triggered for {space.upper()}! Current: ${current_price} | Entry: ${entry_price}")
            
            try:
                approve_txn = token_contract.functions.approve(ROUTER_ADDRESS, balance).build_transaction({
                    'from': wallet_address,
                    'gas': 100000,
                    'gasPrice': W3.eth.gas_price,
                    'nonce': W3.eth.get_transaction_count(wallet_address),
                    'chainId': 8453
                })
                signed_approve = W3.eth.account.sign_transaction(approve_txn, private_key)
                approve_hash = W3.eth.send_raw_transaction(signed_approve.rawTransaction)
                print(f"[EXIT] Approving Router... TX: {W3.to_hex(approve_hash)}")
                
                W3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
                
                deadline = int(time.time()) + 600
                swap_txn = router_contract.functions.swapExactTokensForETH(
                    balance,
                    0,
                    [token_address, WETH_ADDRESS],
                    wallet_address,
                    deadline
                ).build_transaction({
                    'from': wallet_address,
                    'gas': 300000,
                    'gasPrice': W3.eth.gas_price,
                    'nonce': W3.eth.get_transaction_count(wallet_address),
                    'chainId': 8453
                })
                signed_swap = W3.eth.account.sign_transaction(swap_txn, private_key)
                swap_hash = W3.eth.send_raw_transaction(signed_swap.rawTransaction)
                print(f"[EXIT] 💰 SOLD {space.upper()} back to ETH! TX: https://basescan.org/tx/{W3.to_hex(swap_hash)}")
                
                cursor.execute("UPDATE alpha_signals SET status = 'CLOSED' WHERE proposal_id = ?", (proposal_id,))
                conn.commit()
                
            except Exception as e:
                print(f"[EXIT] ❌ Error executing sell for {space}: {e}")
                
    conn.close()
