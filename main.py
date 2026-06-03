import asyncio
import signal
import logging
from config import settings
from scheduler import scheduler, setup_scheduler
from listener import listener # Import the new WebSocket listener

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("Main")

async def main():
    logger.info(f"🚀 AlphaPulse initializing on {settings.platform.upper()}...")
    
    # 1. Start the existing APScheduler (Your dashboard & background jobs)
    setup_scheduler()
    scheduler.start()
    logger.info("✅ Scheduler started.")
    
    # 2. Start the WebSocket Listener concurrently
    listener_task = asyncio.create_task(listener.run())
    logger.info("✅ WebSocket Listener task created.")
    
    # Keep event loop alive until OS sends SIGINT/SIGTERM
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    
    def shutdown_handler():
        logger.info("\n🛑 Graceful shutdown requested...")
        scheduler.shutdown(wait=True)
        listener_task.cancel()
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
