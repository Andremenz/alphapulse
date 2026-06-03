import asyncio
import signal
import logging
from config import settings
from listener import listener
from verify_db import verify_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("Main")

async def periodic_verification():
    """Run database verification every 5 minutes"""
    while True:
        await asyncio.sleep(300)  # 5 minutes
        try:
            verify_database()
        except Exception as e:
            logger.error(f"Verification error: {e}")

async def main():
    logger.info(f"🚀 AlphaPulse initializing on {settings.platform.upper()}...")
    
    # 1. Start the WebSocket Listener
    listener_task = asyncio.create_task(listener.run())
    logger.info("✅ WebSocket Listener task created.")
    
    # 2. Start periodic database verification
    verification_task = asyncio.create_task(periodic_verification())
    logger.info("✅ Database verification task created (runs every 5 minutes).")
    
    # Keep event loop alive until OS sends SIGINT/SIGTERM
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    
    def shutdown_handler():
        logger.info("\n🛑 Graceful shutdown requested...")
        listener_task.cancel()
        verification_task.cancel()
        stop_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)
        
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
        
    logger.info("✅ AlphaPulse stopped cleanly.")

if __name__ == "__main__":
    asyncio.run(main())
