import asyncio
from datetime import datetime
from web3 import AsyncWeb3
from config import settings
from typing import List, Dict

async def fetch_recent_whale_transfers(threshold_eth: float = 10.0, limit: int = 50) -> List[Dict]:
    """Queries Base chain for recent ETH transfers above the threshold."""
    w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(settings.get_rpc_url()))
    latest_block = await w3.eth.block_number
    # Look back ~5 blocks (Base block time ~2s, covers ~10s of history)
    start_block = max(0, latest_block - 5)
    
    alerts = []
    for b in range(start_block, latest_block):
        block = await w3.eth.get_block(b, full_transactions=True)
        for tx in block.transactions:
            if tx.to and tx.value > w3.to_wei(threshold_eth, "ether"):
                alerts.append({
                    "type": "whale_buy",
                    "tx_hash": tx.hash.hex(),
                    "from": tx["from"],
                    "to": tx.to,
                    "value_eth": w3.from_wei(tx.value, "ether"),
                    "block": b,
                    "timestamp": datetime.utcnow().isoformat()
                })
        # Rate limit protection for free Alchemy tier
        if (b - start_block) % 2 == 0:
            await asyncio.sleep(0.1)
            
    return alerts[:limit]
