import asyncio
import httpx
import logging
import os
import json
from datetime import datetime

# Configure logging for Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("AsyncExecutor")

class AsyncEventEngine:
    def __init__(self):
        # Geo-permissionless, Zero-KYC Public RPC Rotator for Base
        self.rpc_urls = [
            "https://mainnet.base.org",
            "https://base.llamarpc.com",
            "https://base.drpc.org",
            "https://1rpc.io/base"
        ]
        self.current_rpc_index = 0
        self.client = httpx.AsyncClient(
            timeout=15.0, 
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
        self.last_processed_block = 0
        
        self.tracked_wallets = {
            "0x1234567890abcdef1234567890abcdef12345678".lower(),
            "0xabcdef1234567890abcdef1234567890abcdef12".lower()
        }

    @property
    def active_rpc(self):
        return self.rpc_urls[self.current_rpc_index]

    def rotate_rpc(self):
        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.rpc_urls)
        logger.warning(f"RPC Throttled/Failed. Rotating to: {self.active_rpc}")

    async def rpc_call(self, method, params):
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        
        for _ in range(len(self.rpc_urls)):
            try:
                response = await self.client.post(self.active_rpc, json=payload)
                if response.status_code == 429 or response.status_code >= 500:
                    self.rotate_rpc()
                    await asyncio.sleep(0.5)
                    continue
                response.raise_for_status()
                return response.json().get("result")
            except Exception as e:
                logger.debug(f"RPC Node {self.active_rpc} failed: {e}")
                self.rotate_rpc()
                
        logger.critical("All RPC nodes in the rotator failed simultaneously.")
        return None

    async def process_block(self, block_hex):
        block_data = await self.rpc_call("eth_getBlockByNumber", [block_hex, True])
        if not block_data or "transactions" not in block_data:
            return

        block_num = int(block_data["number"], 16)
        
        for tx in block_data["transactions"]:
            from_addr = tx.get("from")
            to_addr = tx.get("to")
            
            # 🚀 FIX: Contract deployments have a null 'to' address.
            # We safely handle None types before calling .lower()
            from_addr = from_addr.lower() if from_addr else None
            to_addr = to_addr.lower() if to_addr else None
            
            if (from_addr and from_addr in self.tracked_wallets) or \
               (to_addr and to_addr in self.tracked_wallets):
                
                try:
                    value_wei = int(tx.get("value", "0x0"), 16)
                    value_eth = value_wei / 10**18
                except ValueError:
                    value_eth = 0.0
                    
                await self.trigger_smart_money_alert(tx.get("hash", "0xunknown"), from_addr, to_addr, value_eth, block_num)

    async def trigger_smart_money_alert(self, tx_hash, from_addr, to_addr, value_eth, block_num):
        logger.warning(f"🚨 SMART MONEY MOVEMENT | Block: {block_num} | Tx: {tx_hash} | Value: {value_eth:.4f} ETH")
        # TODO: Hook into your AI Narrative Brain / Execution Layer here

    async def run_event_loop(self):
        logger.info(f"Loaded {len(self.tracked_wallets)} Smart Money Wallets.")
        logger.info("Starting Async Block Listener (Base 2s block time)...")
        
        current_hex = await self.rpc_call("eth_blockNumber", [])
        if current_hex:
            self.last_processed_block = int(current_hex, 16)
            logger.info(f"Starting from live block {self.last_processed_block}")

        while True:
            try:
                latest_hex = await self.rpc_call("eth_blockNumber", [])
                if latest_hex:
                    latest_num = int(latest_hex, 16)
                    if latest_num > self.last_processed_block:
                        for bn in range(self.last_processed_block + 1, latest_num + 1):
                            await self.process_block(hex(bn))
                        self.last_processed_block = latest_num
                
                await asyncio.sleep(1)
            except Exception as e:
                logger.critical(f"Event Loop Crash: {e}. Restarting in 5s...")
                await asyncio.sleep(5)

engine = AsyncEventEngine()

async def start_async_engine():
    await engine.run_event_loop()

if __name__ == "__main__":
    try:
        asyncio.run(start_async_engine())
    except KeyboardInterrupt:
        logger.info("Shutting down Async Executor gracefully.")
