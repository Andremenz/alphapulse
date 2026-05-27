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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rl_metrics (
            ai_tier TEXT PRIMARY KEY,
            alpha REAL DEFAULT 2.0,
            beta REAL DEFAULT 2.0
        )
    """)
    conn.commit()
    conn.close()

def log_trade_outcome(proposal_id: str, is_win: bool):
    """
    Updates the Bayesian Beta-Binomial model based on trade outcome.
    Alpha increments on Wins, Beta increments on Losses.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Fetch current metrics
    cursor.execute("SELECT alpha, beta FROM rl_metrics WHERE ai_tier = 'narrative_brain'")
    row = cursor.fetchone()
    
    if not row:
        alpha, beta = 2.0, 2.0
    else:
        alpha, beta = row
        
    if is_win:
        alpha += 1.0
        logger.info(f"[RL] ✅ WIN recorded. New Alpha: {alpha}")
    else:
        beta += 1.0
        logger.info(f"[RL] ❌ LOSS recorded. New Beta: {beta}")
        
    cursor.execute("""
        INSERT INTO rl_metrics (ai_tier, alpha, beta) 
        VALUES ('narrative_brain', ?, ?)
        ON CONFLICT(ai_tier) DO UPDATE SET alpha=?, beta=?
    """, (alpha, beta, alpha, beta))
    
    # Update signal status
    status = 'WON' if is_win else 'LOST'
    cursor.execute("UPDATE alpha_signals SET status = ? WHERE proposal_id = ?", (status, proposal_id))
    
    conn.commit()
    conn.close()
