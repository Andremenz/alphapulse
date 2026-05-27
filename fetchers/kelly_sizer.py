import sqlite3
import logging
from fetchers.shadow_ledger import DB_PATH

logger = logging.getLogger("KellySizer")

def get_bayesian_win_rate(ai_tier: str = "narrative_brain") -> float:
    """
    Fetches live Bayesian win-rate from Shadow Ledger.
    Uses Beta-Binomial conjugate prior to smooth variance on low sample sizes.
    Formula: E[win_rate] = alpha / (alpha + beta)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure RL metrics table exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rl_metrics (
        ai_tier TEXT PRIMARY KEY,
        alpha REAL DEFAULT 2.0,
        beta REAL DEFAULT 2.0,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    
    # Fetch current Bayesian parameters
    cursor.execute("SELECT alpha, beta FROM rl_metrics WHERE ai_tier = ?", (ai_tier,))
    row = cursor.fetchone()
    
    if not row:
        # Initialize with neutral prior (50% win rate, low confidence)
        alpha, beta = 2.0, 2.0
        cursor.execute(
            "INSERT INTO rl_metrics (ai_tier, alpha, beta) VALUES (?, ?, ?)",
            (ai_tier, alpha, beta)
        )
        conn.commit()
    else:
        alpha, beta = row
    
    conn.close()
    
    # Expected value of Beta(alpha, beta) distribution
    expected_win_rate = alpha / (alpha + beta)
    
    # Clamp to prevent extreme sizing on tiny sample sizes
    return max(0.15, min(0.85, expected_win_rate))

def calculate_position_size(
    portfolio_eth: float,
    ai_confidence: float,
    liquidity_score: float,
    odds_payout_ratio: float = 2.0
) -> float:
    """
    Dynamic Kelly-Criterion Position Sizing with Bayesian win-rate.
    
    Kelly Formula: f* = (bp - q) / b
    Where:
      b = odds received (payout ratio, e.g., 2.0 for 2:1 TP/SL)
      p = probability of winning (Bayesian win rate)
      q = 1 - p = probability of losing
    
    We use Half-Kelly (f*/2) to reduce volatility, then apply AI confidence 
    and liquidity multipliers for final sizing.
    """
    # Get live Bayesian win-rate from Shadow Ledger
    win_rate = get_bayesian_win_rate("narrative_brain")
    
    # Kelly calculation
    b = odds_payout_ratio
    p = win_rate
    q = 1.0 - p
    
    raw_kelly = (b * p - q) / b
    
    # Half-Kelly is standard in quant trading to reduce drawdowns
    half_kelly = max(0.0, raw_kelly / 2.0)
    
    # Apply AI confidence (0.0-1.0) and liquidity score (0.0-1.0) multipliers
    adjusted_fraction = half_kelly * ai_confidence * liquidity_score
    
    # Hard cap: Never risk >15% of portfolio on a single micro-cap trade
    max_risk_fraction = 0.15
    final_fraction = min(adjusted_fraction, max_risk_fraction)
    
    position_size_eth = portfolio_eth * final_fraction
    
    # Log the mathematical breakdown for transparency
    logger.info(
        f"[KELLY] WinRate: {win_rate:.2%} | Raw Kelly: {raw_kelly:.3f} | "
        f"Final Fraction: {final_fraction:.3f} | Size: {position_size_eth:.4f} ETH"
    )
    
    # Minimum viable trade size on Base to avoid dust limits and gas drain
    if position_size_eth < 0.004:
        return 0.0
    
    return round(position_size_eth, 4)
