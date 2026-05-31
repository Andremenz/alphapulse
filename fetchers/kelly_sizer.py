import os
import logging
from fetchers.shadow_ledger import ipfs_ledger

logger = logging.getLogger("KellySizer")

# Kelly parameters
MIN_POSITION_ETH = 0.001  # ~$2 minimum trade
MAX_POSITION_ETH = 0.01   # ~$20 maximum trade (risk control)
KELLY_FRACTION = 0.25     # Quarter-Kelly for conservative sizing
MIN_WIN_RATE = 0.5        # Don't increase size below 50% win-rate

def calculate_position_size(ai_score: int, current_balance_eth: float) -> float:
    """
    Calculates optimal position size using Bayesian Kelly-Criterion.
    
    Args:
        ai_score: AI confidence score (0-100)
        current_balance_eth: Available ETH balance
    
    Returns:
        Position size in ETH (capped between MIN/MAX)
    """
    # Fetch live win-rate from Shadow Ledger
    stats = ipfs_ledger.get_trading_stats()
    win_rate = stats.get("win_rate", 0.5)  # Default to 50% if no data
    
    # Only scale up if win-rate is proven
    if win_rate < MIN_WIN_RATE:
        logger.info(f"[KELLY] Win-rate {win_rate:.1%} below threshold. Using minimum size.")
        return MIN_POSITION_ETH
    
    # Kelly formula: f* = (bp - q) / b
    # b = avg win/loss ratio (assume 1.5:1 for crypto)
    # p = win probability (AI score / 100)
    # q = 1 - p
    b = 1.5  # Assumed reward/risk ratio
    p = ai_score / 100
    q = 1 - p
    
    kelly_fraction = ((b * p) - q) / b if b > 0 else 0
    # Apply conservative fraction and cap
    position = current_balance_eth * kelly_fraction * KELLY_FRACTION
    position = max(MIN_POSITION_ETH, min(MAX_POSITION_ETH, position))
    
    logger.info(f"[KELLY] Win-rate: {win_rate:.1%} | AI Score: {ai_score} | Position: {position:.4f} ETH")
    return position
