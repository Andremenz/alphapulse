import asyncio
import json
import logging
from web3 import Web3
from config import settings
from abis import AERODROME_FACTORY_ABI, POOL_CREATED_TOPIC
from database import state_db

logger = logging.getLogger("Listener")

class DexListener:
    def __init__(self):
        if not settings.base_rpc:
            raise ValueError("BASE_RPC is not set in config/secrets!")
        
        self.w3 = Web3(Web3.HTTPProvider(settings.base_rpc, request_kwargs={'timeout': 30}))
        self.aero_router = settings.routers["Aerodrome"].lower()
        self.aero_factory = settings.factories["Aerodrome"].lower()
        
        # ✅ Method IDs WITHOUT 0x prefix (will normalize input)
        self.swap_methods = {
            'cac88ea9': 'swapExactTokensForTokens',
            '903638a4': 'swapExactETHForTokens',
            'c6b7f1b6': 'swapExactTokensForETH',
            '4111d597': 'UNSAFE_swapExactTokensForTokens',
            '88cd821e': 'swapExactTokensForTokensSupportingFeeOnTransferTokens',
            '3da5acba': 'swapExactETHForTokensSupportingFeeOnTransferTokens',
            '12bc3aca': 'swapExactTokensForETHSupportingFeeOnTransferTokens',
            'fb49bafd': 'zapIn',
            'a81b9159': 'zapOut',
            'dede6c4': 'unknown_swap_1',  # From your logs
        }
        
        logger.info(f"🎯 Monitoring Router: {self.aero_router}")
        logger.info(f"📋 Tracking {len(self.swap_methods)} methods")
        self.last_block_checked = 0
        self.total_swaps = 0
        
    async def run(self):
        """Main polling loop with proper method ID normalization"""
        while True:
            try:
                if not self.w3.is_connected():
                    logger.warning("HTTP disconnected. Reconnecting...")
                    await asyncio.sleep(5)
                    self.w3 = Web3(Web3.HTTPProvider(settings.base_rpc, request_kwargs={'timeout': 30}))
                    continue

                current_block = self.w3.eth.block_number
                
                if self.last_block_checked == 0:
                    self.last_block_checked = current_block - 1
                    logger.info(f"✅ Starting from block {self.last_block_checked}")
                
                end_block = min(current_block, self.last_block_checked + 5)
                
                if end_block > self.last_block_checked:
                    for block_num in range(self.last_block_checked + 1, end_block + 1):
                        await self.scan_block(block_num)
                        
                    self.last_block_checked = end_block

                await asyncio.sleep(3)
                
            except Exception as e:
                logger.error(f"Error: {e}. Retrying in 10s...", exc_info=True)
                await asyncio.sleep(10)

    async def scan_block(self, block_num):
        """Scan block with proper method ID extraction"""
        try:
            block = self.w3.eth.get_block(block_num, full_transactions=True)
            block_swaps = 0
            
            for tx in block.transactions:
                if tx.to and tx.to.lower() == self.aero_router:
                    if tx.input and len(tx.input) >= 4:
                        # ✅ PROPER EXTRACTION: Get first 4 bytes, convert to hex, strip 0x
                        method_bytes = tx.input[:4]
                        if isinstance(method_bytes, bytes):
                            method_id = method_bytes.hex()
                        else:
                            # Handle if it's already a string
                            method_id = str(method_bytes).replace('0x', '')[:8]
                        
                        # Remove any remaining 0x prefix
                        method_id = method_id.lower().replace('0x', '')
                        
                        if method_id in self.swap_methods:
                            block_swaps += 1
                            self.total_swaps += 1
                            await self.handle_swap(tx, method_id)
                        else:
                            # Log unknown methods for debugging
                            if block_num % 10 == 0:  # Only log occasionally
                                logger.debug(f"Unknown method: 0x{method_id}")
            
            # Check for pool creations
            try:
                pool_logs = self.w3.eth.get_logs({
                    "fromBlock": block_num,
                    "toBlock": block_num,
                    "address": [settings.factories["Aerodrome"]],
                    "topics": [POOL_CREATED_TOPIC]
                })
                
                for log in pool_logs:
                    await self.handle_pool_creation(log)
            except Exception as e:
                logger.debug(f"Pool log error: {e}")
            
            # Heartbeat every 10 blocks
            if block_num % 10 == 0:
                logger.info(f"📊 Block {block_num} | Swaps: {block_swaps} | Total: {self.total_swaps}")
                
        except Exception as e:
            logger.error(f"Block {block_num} error: {e}")

    async def handle_swap(self, tx, method_id):
        """Log swap with full details"""
        try:
            method_name = self.swap_methods[method_id]
            eth_value = self.w3.from_wei(tx.value, 'ether') if tx.value > 0 else 0
            tx_hash = tx.hash.hex() if isinstance(tx.hash, bytes) else str(tx.hash)
            
            logger.info(
                f"🔔 SWAP | {method_name} | "
                f"{eth_value:.4f} ETH | "
                f"{tx_hash[:10]}..."
            )
            
            state_db.log_dex_swap(
                router="Aerodrome",
                token_in="ETH" if eth_value > 0 else "TOKEN",
                token_out="TOKEN" if eth_value > 0 else "ETH",
                amount_in=float(eth_value),
                amount_out=0.0,
                tx_hash=tx_hash
            )
            
        except Exception as e:
            logger.warning(f"Swap log error: {e}")

    async def handle_pool_creation(self, log):
        """Log new pools"""
        try:
            contract = self.w3.eth.contract(
                address=settings.factories["Aerodrome"],
                abi=json.loads(AERODROME_FACTORY_ABI)
            )
            event = contract.events.PoolCreated().process_log(log)
            args = event['args']
            
            tx_hash = log['transactionHash'].hex() if isinstance(log['transactionHash'], bytes) else str(log['transactionHash'])
            
            logger.info(
                f"🚀 POOL | "
                f"{args['token0'][:8]}... | "
                f"{args['token1'][:8]}... | "
                f"{args['pool'][:8]}..."
            )
            
            state_db.log_new_pool(
                token0=args['token0'],
                token1=args['token1'],
                stable=args['stable'],
                pool_address=args['pool'],
                tx_hash=tx_hash
            )
            
        except Exception as e:
            logger.warning(f"Pool decode error: {e}")

listener = DexListener()
