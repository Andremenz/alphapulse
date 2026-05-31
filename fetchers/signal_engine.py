import logging

logger = logging.getLogger("SignalEngine")

async def scan_smart_money():
    """Minimal scan function that always returns empty list if dependencies fail."""
    try:
        logger.info("[SIGNAL_ENGINE] Scan started.")
        # Placeholder: In production, add wallet scanning logic here
        # For now, return empty to avoid crashes
        return []
    except Exception as e:
        logger.error(f"[SIGNAL_ENGINE] Critical error: {e}")
        return []
