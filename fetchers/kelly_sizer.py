import sqlite3
import math
import logging
from fetchers.shadow_ledger import DB_PATH

logger = logging.getLogger("KellySizer")

def get_bayesian_win_rate(ai_tier: str = "narrative_brain") -> float:
    """
    Fetches live Bayesian win-rate from Shadow Ledger.
    Uses Beta-Binomial conjugate prior to smooth out variance on low sample sizes.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure RL table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rl_metrics (
            ai_tier TEXT PRIMARY KEY,
            alpha REAL DEFAULT 2.0,
            beta REAL DEFAULT 2.0
        )
    """)
    conn.commit()
    
    cursor.execute("SELECT alpha, beta FROM rl_metrics WHERE ai_tier = ?", (ai_tier,))
    row = cursor.fetchone()
    
    if not row:
        # Initialize with a neutral prior (50% win rate, low confidence: alpha=2, beta=2)
        cursor.execute("INSERT INTO rl_metrics (ai_tier, alpha, beta) VALUES (?, 2.0, 2.0)", (ai_tier,))
        conn.commit()
        alpha, beta = 2.0, 2.0
    else:
        alpha, beta = row
        
    conn.close()
    
    # Expected value of Beta distribution is alpha / (alpha + beta)
    expected_win_rate = alpha / (alpha + beta)
    return max(0.1, min(0.9, expected_win_rate)) # Clamp between 10% and 90%

def calculate_position_size(
    portfolio_eth: float, 
    ai_confidence: float, 
    liquidity_score: float, 
    odds_payout_ratio: float = 2.0
) -> float:
    """
    Dynamic Kelly-Criterion Position Sizing.
    Auto-scales bet size by AI confidence × liquidity × live Bayesian win-rate.
    """
    win_rate = get_bayesian_win_rate("narrative_brain")
    
    # Kelly Formula: f* = (bp - q) / b
    # b = odds received (payout ratio, e.g., 2.0 for 2:1 TP/SL)
    # p = probability of winning (Bayesian win rate)
    # q = probability of losing (1 - p)
    b = odds_payout_ratio
    p = win_rate
    q = 1.0 - p
    
    raw_kelly = (b * p - q) / b
    
    # Fractional Kelly (Half-Kelly) is standard in quant trading to reduce variance/volatility
    half_kelly = max(0.0, raw_kelly / 2.0)
    
    # Apply AI Confidence and Liquidity multipliers (0.0 to 1.0)
    adjusted_fraction = half_kelly * ai_confidence * liquidity_score
    
    # Hard cap: Never risk more than 15% of portfolio on a single micro-cap, regardless of AI hype
    max_risk_fraction = 0.15
    final_fraction = min(adjusted_fraction, max_risk_fraction)
    
    position_size_eth = portfolio_eth * final_fraction
    
    logger.info(f"[KELLY] WinRate: {p:.2%} | Raw Kelly: {raw_kelly:.3f} | Final Fraction: {final_fraction:.3f} | Size: {position_size_eth:.4f} ETH")
    
    # Minimum viable trade size on Base to avoid dust limits and gas drain
    if position_size_eth < 0.005:
        return 0.0 
        
    return round(position_size_eth, 4)
