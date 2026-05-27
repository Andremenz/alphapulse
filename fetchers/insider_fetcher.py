import os
import httpx
import time
from datetime import datetime
from typing import List, Dict
from config import settings
from fetchers.ai_brain import analyze_alpha_event
from fetchers.shadow_ledger import log_snipe_signal
from fetchers.trading_engine import execute_snipe

BASESCAN_API_URL = "https://api.basescan.org/api"
API_KEY = os.environ.get("BASESCAN_API_KEY", "")
ROUTERS = {"0xcf77a3ba9a5ca399b7c97c74d54e5b1beb301b6e": "aerodrome", "0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24": "baseswap"}
INSIDER_WALLETS = {"aero_lead_dev": "0x8F5B2b1A5B5E5C8D9E0F1A2B3C4D5E6F7A8B9C0D", "baseswap_founder": "0x1A2B3C4D5E6F7A8B9C0D1E2F3A4B5C6D7E8F9A0B"}

async def check_insider_wallets():
    if not API_KEY: return
    async with httpx.AsyncClient() as client:
        for name, wallet_addr in INSIDER_WALLETS.items():
            params = {"module": "account", "action": "txlist", "address": wallet_addr, "startblock": 0, "endblock": 99999999, "page": 1, "offset": 5, "sort": "desc", "apikey": API_KEY}
            try:
                resp = await client.get(BASESCAN_API_URL, params=params, timeout=10.0)
                data = resp.json()
                if data.get("status") != "1": continue
                for tx in data.get("result", []):
                    to_addr = tx.get("to", "").lower()
                    val = int(tx.get("value", "0"))
                    tx_hash = tx.get("hash", "")
                    if to_addr in ROUTERS and val > 10**16: 
                        space = ROUTERS[to_addr]
                        eth_amt = val / 10**18
                        print(f"[INSIDER] 🕵️‍♂️ {name} swapped {eth_amt:.4f} ETH on {space.upper()} | TX: {tx_hash}")
                        await log_snipe_signal({"id": f"insider_{tx_hash[:10]}", "space": space, "title": f"Insider Buy: {name} -> {space.upper()}", "ai_score": 92, "ai_reasoning": "Direct DEX accumulation by known insider"})
                        await execute_snipe(space, f"Insider accumulation by {name}", 92)
                        yield {"id": f"insider_{tx_hash}", "type": "insider_swap", "name": name, "space": space.upper(), "eth_amount": f"{eth_amt:.4f}", "link": f"https://basescan.org/tx/{tx_hash}", "timestamp": datetime.utcnow().isoformat()}
                time.sleep(1.5)
            except Exception as e: print(f"[INSIDER] Error: {e}")
