import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger("ShadowLedger")

# Railway mounted volume path for persistent SQLite
# Ensure you have added a Volume in Railway and mounted it to /data
DB_DIR = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "./data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "alphapulse_shadow.db")

def init_db():
    """Initialize database tables for signals and RL metrics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Alpha signals table (existing)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alpha_signals (
        proposal_id TEXT PRIMARY KEY,
        space TEXT,
        token_id TEXT,
        entry_price REAL,
        target_price REAL,
        stop_loss REAL,
        ai_score REAL,
        status TEXT DEFAULT 'OPEN',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # NEW: RL metrics table for Bayesian win-rate tracking
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rl_metrics (
        ai_tier TEXT PRIMARY KEY,
        alpha REAL DEFAULT 2.0,
        beta REAL DEFAULT 2.0,
        last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()

def log_trade_outcome(proposal_id: str, is_win: bool, ai_tier: str = "narrative_brain"):
    """
    Updates the Bayesian Beta-Binomial model based on trade outcome.
    
    - Wins increment alpha (successes)
    - Losses increment beta (failures)
    
    This creates a self-correcting system: consistent losses shrink position sizes,
    consistent wins allow gradual scaling—all while protecting against overfitting
    on small sample sizes via the Bayesian prior.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Fetch current Bayesian parameters
    cursor.execute(
        "SELECT alpha, beta FROM rl_metrics WHERE ai_tier = ?", 
        (ai_tier,)
    )
    row = cursor.fetchone()
    
    if not row:
        # Initialize with neutral prior if not exists
        alpha, beta = 2.0, 2.0
    else:
        alpha, beta = row
    
    # Update parameters based on outcome
    if is_win:
        alpha += 1.0
        logger.info(f"[RL] ✅ WIN recorded for {proposal_id}. New Alpha: {alpha}")
    else:
        beta += 1.0
        logger.info(f"[RL] ❌ LOSS recorded for {proposal_id}. New Beta: {beta}")
    
    # Upsert the updated metrics
    cursor.execute("""
    INSERT INTO rl_metrics (ai_tier, alpha, beta, last_updated)
    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(ai_tier) DO UPDATE SET 
        alpha = excluded.alpha,
        beta = excluded.beta,
        last_updated = excluded.last_updated
    """, (ai_tier, alpha, beta))
    
    # Update signal status for audit trail
    status = 'WON' if is_win else 'LOST'
    cursor.execute(
        "UPDATE alpha_signals SET status = ? WHERE proposal_id = ?", 
        (status, proposal_id)
    )
    
    conn.commit()
    conn.close()
