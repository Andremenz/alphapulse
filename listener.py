import asyncio
import json
import logging
from web3 import AsyncWeb3
from config import settings
from abis import AERODROME_ROUTER_ABI, AERODROME_FACTORY_ABI, SWAP_TOPIC, POOL_CREATED_TOPIC
from database import state_db

logger = logging.getLogger("Listener")

class DexListener:
    def __init__(self):
        if not settings.base_ws:
            raise ValueError("BASE_WS is not set in config/secrets!")
        self.w3 = AsyncWeb3(AsyncWeb3.WebsocketProvider(settings.base_ws))
        
        self.aero_router = settings.routers["Aerodrome"].lower()
        self.aero_factory = settings.factories["Aerodrome"].lower()
        
    async def run(self):
        """Main WebSocket loop with auto-reconnect"""
        while True:
            try:
                if not await self.w3.is_connected():
                    logger.warning("WebSocket disconnected. Reconnecting in 5s...")
                    await asyncio.sleep(5)
                    continue

                logger.info("✅ WebSocket Connected to QuickNode.")
                
                # Subscribe to Aerodrome V2 Swaps
                await self.w3.eth.subscribe("logs", {
                    "address": [settings.routers["Aerodrome"]],
                    "topics": [SWAP_TOPIC]
                })
                
                # Subscribe to Aerodrome Pool Creations
                await self.w3.eth.subscribe("logs", {
                    "address": [settings.factories["Aerodrome"]],
                    "topics": [POOL_CREATED_TOPIC]
                })
                
                logger.info(f"🎧 Listening to Aerodrome Swaps & Pool Creations...")
                
                # Process incoming logs
                async for response in self.w3.socket.process_subscriptions():
                    await self.process_log(response)
                    
            except Exception as e:
                logger.error(f"Listener Critical Error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def process_log(self, response):
        """Routes logs to the correct handler"""
        try:
            log = response['result']
            address = log['address'].lower()
            
            # Safe TX hash extraction
            tx_hash = log['transactionHash'].hex() if isinstance(log['transactionHash'], bytes) else log['transactionHash']
            
            if address == self.aero_router:
                await self.handle_swap(log, tx_hash)
            elif address == self.aero_factory:
                await self.handle_pool_creation(log, tx_hash)
                
        except Exception as e:
            logger.error(f"Error processing log: {e}")

    async def handle_swap(self, log, tx_hash):
        """Decodes and logs Aerodrome V2 Swaps"""
        try:
            contract = self.w3.eth.contract(address=settings.routers["Aerodrome"], abi=json.loads(AERODROME_ROUTER_ABI))
            event = contract.events.Swap().process_log(log)
            args = event['args']
            
            amount0_in = args.get('amount0In', 0)
            amount1_in = args.get('amount1In', 0)
            
            if amount0_in > 0:
                action = "SELL"
                amount_in = self.w3.from_wei(amount0_in, 'ether')
            else:
                action = "BUY"
                amount_in = self.w3.from_wei(amount1_in, 'ether')
                
            logger.info(f"🔔 AERODROME SWAP | {action} | Volume: {amount_in:.4f} ETH | TX: {tx_hash[:10]}...")
            
            # Log to database
            state_db.log_dex_swap(
                router="Aerodrome", token_in="0", token_out="1",
                amount_in=float(amount_in), amount_out=0.0, tx_hash=tx_hash
            )
            
        except Exception as e:
            logger.debug(f"Failed to decode Aerodrome swap: {e}")

    async def handle_pool_creation(self, log, tx_hash):
        """Decodes and logs New Pool Creations"""
        try:
            contract = self.w3.eth.contract(address=settings.factories["Aerodrome"], abi=json.loads(AERODROME_FACTORY_ABI))
            event = contract.events.PoolCreated().process_log(log)
            args = event['args']
            
            logger.info(f"🚀 NEW AERODROME POOL | T0: {args['token0'][:8]}... T1: {args['token1'][:8]}... | Pool: {args['pool'][:8]}...")
            
            # Log to database
            state_db.log_new_pool(
                token0=args['token0'], token1=args['token1'],
                stable=args['stable'], pool_address=args['pool'], tx_hash=tx_hash
            )
            
        except Exception as e:
            logger.error(f"Failed to decode pool creation: {e}")

# Global instance
listener = DexListener()
