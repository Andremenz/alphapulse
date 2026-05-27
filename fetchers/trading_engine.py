import os
import time
import json
import httpx
from web3 import Web3
from fetchers.social_filter import check_social_sentiment

# Base Chain Configuration
BASE_RPC_URL = "https://mainnet.base.org"
W3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
CHAIN_ID = 8453

# Uniswap V2 Router on Base
ROUTER_ADDRESS = Web3.to_checksum_address("0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24")
WETH_ADDRESS = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")

# Mapping Snapshot Spaces to their Base Chain Token Contract Addresses
BASE_TOKEN_MAP = {
    "aerodrome": {"address": Web3.to_checksum_address("0x940181a94A35A4569E4529A3CDfB74e38FD98631"), "ticker": "AERO"},
    "baseswap": {"address": Web3.to_checksum_address("0x78a087d713Be963Bf307B18F2Ff8122EF9A63ae9"), "ticker": "BSWAP"},
    "brett": {"address": Web3.to_checksum_address("0x532f27101965dd16442E59d40670FaF5eBB142E4"), "ticker": "BRETT"},
}

ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"}]')

async def check_pool_safety(token_address: str) -> bool:
    """Queries GeckoTerminal to ensure the token has enough liquidity and volume to safely enter."""
    url = f"https://api.geckoterminal.com/api/v2/networks/base/tokens/{token_address}/pools"
    headers = {"Accept": "application/json", "User-Agent": "AlphaPulse-Bot"}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            if resp.status_code != 200: 
                print(f"[SAFETY] ⚠️ GeckoTerminal API error: {resp.status_code}")
                return False
                
            data = resp.json()
            pools = data.get("data", [])
            if not pools: 
                print("[SAFETY] ❌ ABORT: No liquidity pools found on Base.")
                return False
            
            best_pool = max(pools, key=lambda p: float(p["attributes"].get("reserve_in_usd", 0)))
            liquidity = float(best_pool["attributes"].get("reserve_in_usd", 0))
            volume_24h = float(best_pool["attributes"].get("volume_usd", {}).get("h24", 0))
            
            print(f"[SAFETY] 🔍 {token_address[:8]}... | Liquidity: ${liquidity:,.2f} | 24h Vol: ${volume_24h:,.2f}")
            
            if liquidity < 50000:
                print("[SAFETY] ❌ ABORT: Liquidity too low (<$50k). High slippage risk.")
                return False
            if volume_24h < 10000:
                print("[SAFETY] ❌ ABORT: Volume too low (<$10k). Dead token risk.")
                return False
                
            print("[SAFETY] ✅ Pool is safe. Liquidity and Volume meet institutional thresholds.")
            return True
            
        except Exception as e:
            print(f"[SAFETY] ⚠️ API Error, aborting trade for safety: {e}")
            return False

async def execute_snipe(space: str, proposal_title: str):
    """Executes a market buy on Base chain ONLY if Safety Shield AND Social Filter pass."""
    private_key = os.environ.get("BASE_PRIVATE_KEY")
    snipe_amount_str = os.environ.get("SNIPE_AMOUNT_ETH", "0.005")
    
    if not private_key:
        print("[TRADE] ❌ Missing BASE_PRIVATE_KEY in Railway variables.")
        return

    space_lower = space.lower()
    token_data = BASE_TOKEN_MAP.get(space_lower)
    
    if not token_data:
        print(f"[TRADE] ⚠️ No Base chain token mapped for '{space}'. Alert sent, but no trade executed.")
        return

    target_token_address = token_data["address"]
    token_ticker = token_data["ticker"]

    # 🚨 OMEGA UPGRADE 1: RUN THE SAFETY SHIELD 🚨
    is_safe = await check_pool_safety(target_token_address)
    if not is_safe:
        print(f"[TRADE] 🛑 Trade aborted by Safety Shield for {space.upper()}.")
        return

    # 🚨 OMEGA UPGRADE 2: RUN THE SOCIAL FILTER 🚨
    social_check = await check_social_sentiment(token_ticker, proposal_title)
    if social_check["is_late"]:
        print(f"[TRADE] 🛑 Trade aborted by Social Filter for {space.upper()}. {social_check['reasoning']}")
        return
    else:
        print(f"[TRADE] ✅ Social Filter passed: {social_check['reasoning']}")

    try:
        account = W3.eth.account.from_key(private_key)
        wallet_address = account.address
        snipe_amount_wei = W3.to_wei(float(snipe_amount_str), 'ether')
        
        balance = W3.eth.get_balance(wallet_address)
        if balance < snipe_amount_wei + W3.to_wei(0.001, 'ether'):
            print(f"[TRADE] ❌ Insufficient Base ETH. Balance: {W3.from_wei(balance, 'ether')} ETH")
            return

        router_contract = W3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
        deadline = int(time.time()) + 600 
        
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

        signed_txn = W3.eth.account.sign_transaction(txn, private_key)
        tx_hash = W3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        space_upper = space.upper()
        print(f"[TRADE] 🚀 SNIPE EXECUTED! Buying {space_upper} | TX: https://basescan.org/tx/{W3.to_hex(tx_hash)}")
        
    except Exception as e:
        print(f"[TRADE] ❌ Execution Error: {e}")
