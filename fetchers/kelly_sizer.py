import logging

logger = logging.getLogger("KellySizer")

def calculate_position_size(ai_score: int, current_balance_eth: float) -> float:
    """Returns minimum position size if stats fetch fails."""
    try:
        MIN_POSITION_ETH = 0.001
        # Placeholder: Add real Kelly logic after shadow_ledger is verified
        return MIN_POSITION_ETH
    except Exception as e:
        logger.error(f"[KELLY] Error calculating size: {e}")
        return 0.001  # Safe fallback
