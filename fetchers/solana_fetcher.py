import httpx
from config import settings
from typing import List, Dict

def get_solana_rpc() -> str:
    return f"https://mainnet.helius-rpc.com/?api-key={settings.helius_api_key}"

async def fetch_solana_vesting_transfers(program_address: str, limit: int = 20) -> List[Dict]:
    alerts = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Get recent signatures for the program/treasury
            resp = await client.post(get_solana_rpc(), json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [program_address, {"limit": limit}]
            })
            signatures = resp.json().get("result", [])
            
            for sig in signatures[:5]:  # Check last 5 txs
                tx_resp = await client.post(get_solana_rpc(), json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [sig["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 0}]
                })
                tx = tx_resp.json().get("result")
                if not tx or tx.get("meta", {}).get("err"):
                    continue
                    
                # Extract token transfers
                for log in tx.get("meta", {}).get("logMessages", []):
                    if "Transfer" in log and "lamports" in log.lower():
                        alerts.append({
                            "type": "solana_vesting",
                            "program": program_address[:8] + "..." + program_address[-4:],
                            "tx": f"https://solscan.io/tx/{sig['signature']}",
                            "slot": sig.get("slot", 0),
                            "chain": "solana"
                        })
                        break
    except Exception as e:
        print(f"[solana_fetcher] Error: {e}")
    return alerts
