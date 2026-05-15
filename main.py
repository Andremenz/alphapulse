import asyncio
import signal
from config import settings
from scheduler import scheduler, setup_scheduler

async def main():
    print(f"🚀 AlphaPulse initializing on {settings.platform.upper()}...")
    setup_scheduler()
    scheduler.start()
    
    # Keep event loop alive until OS sends SIGINT/SIGTERM
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    
    def shutdown_handler():
        print("\n🛑 Graceful shutdown requested...")
        scheduler.shutdown(wait=True)
        stop_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)
        
    await stop_event.wait()
    print("✅ AlphaPulse stopped cleanly.")

if __name__ == "__main__":
    asyncio.run(main())