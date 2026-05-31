# =============================================================================
# 🚨 CONTAINER IMPORT FIX: Ensure fetchers/ is in Python path
# =============================================================================
import sys
import os
from pathlib import Path

# Get the directory containing this script
current_dir = Path(__file__).resolve().parent

# Add project root to sys.path if not already present
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Explicitly add fetchers/ and notifiers/ to path
fetchers_path = current_dir / "fetchers"
notifiers_path = current_dir / "notifiers"

if fetchers_path.exists() and str(fetchers_path) not in sys.path:
    sys.path.insert(0, str(fetchers_path))
if notifiers_path.exists() and str(notifiers_path) not in sys.path:
    sys.path.insert(0, str(notifiers_path))
# =============================================================================

# NOW your normal imports can work
from database import state_db
from fetchers.chain_config import get_chain
import asyncio
import logging
import os
import sys
from datetime import datetime
from web3 import Web3
from config import settings
from database import state_db
from fetchers.chain_config import get_chain
from fetchers.whale_fetcher import fetch_recent_whale_transfers
from scheduler import setup_scheduler  # 🚨 Import the updated scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("AsyncExecutor")

CFG = get_chain()
W3 = CFG["w3"]

# Smart Money Wallets (Phase 21)
SMART_WALLETS = [
    "0x6d4223342506d27548042B1B86d0389675F972b2",  # Jesse Pollak
    "0x3154Cf16ccdb4C6d922629664174b904d80F2C35",  # Base Bridge
]

async def main():
    logger.info("🚀 AlphaPulse Dual-Process Engine Initializing...")
    
    # 🚨 Initialize the updated scheduler (Phase 21/22)
    try:
        setup_scheduler()
        logger.info("✅ Scheduler initialized with Phase 21/22 jobs")
    except Exception as e:
        logger.error(f"❌ Scheduler initialization failed: {e}")
    
    # Start blockchain polling loop
    logger.info(f"Starting Async Block Listener (Base 2s block time)...")
    last_block = None
    
    while True:
        try:
            current_block = W3.eth.block_number
            if current_block != last_block:
                logger.info(f"Starting from live block {current_block}")
                last_block = current_block
                
                # Quick wallet scan (fallback if scheduler jobs fail)
                for wallet in SMART_WALLETS:
                    # Minimal check - expand in production
                    pass
                    
            await asyncio.sleep(2)  # Base block time
        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    # Start scheduler in background thread
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    try:
        setup_scheduler()
        scheduler.start()
        logger.info("✅ Background scheduler started")
    except Exception as e:
        logger.error(f"❌ Background scheduler failed: {e}")
    
    # Run main polling loop
    asyncio.run(main())
