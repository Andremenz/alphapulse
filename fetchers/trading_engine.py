import os
import time
import json
from web3 import Web3

# Base Chain Configuration
BASE_RPC_URL = "https://mainnet.base.org"
W3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
CHAIN_ID = 8453

# Uniswap V2 Router on Base
ROUTER_ADDRESS = Web3.to_checksum_address("0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24")
WETH_ADDRESS = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")

# Mapping Snapshot Spaces to their Base Chain Token Contract Addresses
# (Verified 42-character addresses for Base native tokens)
BASE_TOKEN_MAP = {
    "aerodrome": Web3.to_checksum_address("0x940181a94A35A4569E4529A3CDfB74e38FD98631"), # AERO
    "baseswap": Web3.to_checksum_address("0x78a087d713Be963Bf307B18F2Ff8122EF9A63ae9"), # BSWAP
    "brett": Web3.to_checksum_address("0x532f27101965dd16442E59d40670FaF5eBB142E4"), # BRETT
}

# Minimal ABI for Uniswap V2 swapExactETHForTokens
ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"}]')

async def execute_snipe(space: str, proposal_title: str):
    """Executes a market buy on Base chain if the token is mapped and funded."""
    private_key = os.environ.get("BASE_PRIVATE_KEY")
    snipe_amount_str = os.environ.get("SNIPE_AMOUNT_ETH", "0.005")
    
    if not private_key:
        print("[TRADE] ❌ Missing BASE_PRIVATE_KEY in Railway variables.")
        return

    space_lower = space.lower()
    target_token_address = BASE_TOKEN_MAP.get(space_lower)
    
    if not target_token_address:
        print(f"[TRADE] ⚠️ No Base chain token mapped for '{space}'. Alert sent to Telegram, but no trade executed.")
        return

    try:
        account = W3.eth.account.from_key(private_key)
        wallet_address = account.address
        snipe_amount_wei = W3.to_wei(float(snipe_amount_str), 'ether')
        
        balance = W3.eth.get_balance(wallet_address)
        if balance < snipe_amount_wei + W3.to_wei(0.001, 'ether'): # Keep 0.001 ETH for gas
            print(f"[TRADE] ❌ Insufficient Base ETH. Balance: {W3.from_wei(balance, 'ether')} ETH")
            return

        router_contract = W3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
        deadline = int(time.time()) + 600 # 10 minutes
        
        # Build the transaction
        txn = router_contract.functions.swapExactETHForTokens(
            0, 
            [WETH_ADDRESS, target_token_address], 
            wallet_address, 
            deadline
        ).build_transaction({
            'from': wallet_address,
            'value': snipe_amount_wei,
            'gas': 300000,
            'gasPrice': W3.eth.gas_price,
            'nonce': W3.eth.get_transaction_count(wallet_address),
            'chainId': CHAIN_ID
        })

        # Sign and send
        signed_txn = W3.eth.account.sign_transaction(txn, private_key)
        tx_hash = W3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        space_upper = space.upper()
        print(f"[TRADE] 🚀 SNIPE EXECUTED! Buying {space_upper} | TX: https://basescan.org/tx/{W3.to_hex(tx_hash)}")
        
    except Exception as e:
        print(f"[TRADE] ❌ Execution Error: {e}")
