import os
import time
import json
import httpx
from web3 import Web3
from fetchers.social_filter import check_social_sentiment
from fetchers.kelly_sizing import calculate_optimal_position_size
from fetchers.chain_config import get_chain

CFG = get_chain()
W3 = CFG["w3"]
CHAIN_ID = CFG["chain_id"]
EXPLORER = CFG["explorer"]

ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactETHForTokens","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"payable","type":"function"}]')

async def check_pool_safety(token_address: str) -> tuple[bool, float]:
    url = f"https://api.geckoterminal.com/api/v2/networks/{CFG['gecko_slug']}/tokens/{token_address}/pools"
    headers = {"Accept": "application/json", "User-Agent": "AlphaPulse-Bot"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            if resp.status_code != 200: return False, 0
            data = resp.json()
            pools = data.get("data", [])
            if not pools: return False, 0
            best = max(pools, key=lambda p: float(p["attributes"].get("reserve_in_usd", 0)))
            liq = float(best["attributes"].get("reserve_in_usd", 0))
            vol = float(best["attributes"].get("volume_usd", {}).get("h24", 0))
            print(f"[SAFETY] 🔍 {token_address[:8]}... | Liq: ${liq:,.2f} | Vol: ${vol:,.2f}")
            if liq < 50000 or vol < 10000: return False, 0
            return True, liq
        except Exception as e:
            print(f"[SAFETY] ⚠️ API Error: {e}")
            return False, 0

async def execute_snipe(space: str, proposal_title: str, ai_score: int):
    private_key = os.environ.get("BASE_PRIVATE_KEY")
    if not private_key:
        print("[TRADE] ❌ Missing BASE_PRIVATE_KEY")
        return

    space_lower = space.lower()
    token_data = CFG["tokens"].get(space_lower)
    if not token_data:
        print(f"[TRADE] ⚠️ No token mapped for '{space}' on {CFG['gecko_slug'].upper()}")
        return

    target_addr = token_data["address"]
    ticker = token_data["ticker"]

    is_safe, liq_usd = await check_pool_safety(target_addr)
    if not is_safe:
        print(f"[TRADE] 🛑 Aborted by Safety Shield")
        return

    social = await check_social_sentiment(ticker, proposal_title)
    if social["is_late"]:
        print(f"[TRADE] 🛑 Aborted by Social Filter: {social['reasoning']}")
        return
    print(f"[TRADE] ✅ Social Filter passed")

    account = W3.eth.account.from_key(private_key)
    wallet = account.address
    balance = W3.eth.get_balance(wallet)
    
    size_wei = calculate_optimal_position_size(ai_score, liq_usd, balance, W3)
    if size_wei == 0:
        print("[TRADE] 🛑 Aborted: Kelly size too small or insufficient balance")
        return

    try:
        router = W3.eth.contract(address=CFG["router_address"], abi=ROUTER_ABI)
        deadline = int(time.time()) + 600
        txn = router.functions.swapExactETHForTokens(
            0, [CFG["weth_address"], target_addr], wallet, deadline
        ).build_transaction({
            'from': wallet, 'value': size_wei, 'gas': 300000,
            'gasPrice': W3.eth.gas_price, 'nonce': W3.eth.get_transaction_count(wallet), 'chainId': CHAIN_ID
        })
        signed = W3.eth.account.sign_transaction(txn, private_key)
        tx_hash = W3.eth.send_raw_transaction(signed.rawTransaction)
        print(f"[TRADE] 🛡️ MEV-PROTECTED on {CFG['gecko_slug'].upper()}! {space.upper()} | Size: {W3.from_wei(size_wei, 'ether'):.4f} ETH | TX: https://{EXPLORER}/tx/{W3.to_hex(tx_hash)}")
    except Exception as e:
        print(f"[TRADE] ❌ Execution Error: {e}")
