import sqlite3
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("StateDB")

class StateDB:
    """Lightweight SQLite state manager for AlphaPulse."""
    
    def __init__(self, db_path: str | Path):
        # 🚨 FIX: Convert string to Path if needed
        if isinstance(db_path, str):
            db_path = Path(db_path)
        
        self.db_path = db_path
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn: Optional[sqlite3.Connection] = None
        self._init_schema()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Lazy connection with WAL mode for concurrent reads."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=30)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn
    
    def _init_schema(self):
        """Creates tables if they don't exist."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # State tracking table (for deduplication)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS state_cache (
                config_name TEXT PRIMARY KEY,
                last_check_ts INTEGER NOT NULL,
                seen_ids TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Shadow Ledger: trade history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alpha_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_type TEXT NOT NULL,
                tx_hash TEXT UNIQUE,
                wallet_address TEXT,
                eth_value REAL,
                ai_score INTEGER,
                ai_reasoning TEXT,
                entry_price REAL,
                exit_price REAL,
                pnl_pct REAL,
                status TEXT DEFAULT 'OPEN',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Performance metrics
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                metric_name TEXT PRIMARY KEY,
                metric_value REAL NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        logger.info(f"✅ StateDB initialized at {self.db_path}")
    
    async def get_last_state(self, config_name: str) -> Tuple[int, List[str]]:
        """Fetches last check timestamp and seen IDs for deduplication."""
        try:
            cursor = self._get_conn().cursor()
            cursor.execute(
                "SELECT last_check_ts, seen_ids FROM state_cache WHERE config_name = ?",
                (config_name,)
            )
            row = cursor.fetchone()
            if row:
                last_ts, seen_json = row
                import json
                seen_ids = json.loads(seen_json) if seen_json else []
                return last_ts, seen_ids
            return 0, []
        except Exception as e:
            logger.error(f"[StateDB] Fetch error: {e}")
            return 0, []
    
    async def update_state(self, config_name: str, check_ts: int, seen_ids: List[str]):
        """Updates state cache with new check timestamp and seen IDs."""
        try:
            import json
            # Keep only last 100 IDs to bound storage
            trimmed = seen_ids[-100:]
            cursor = self._get_conn().cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO state_cache (config_name, last_check_ts, seen_ids, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (config_name, check_ts, json.dumps(trimmed)))
            self._get_conn().commit()
        except Exception as e:
            logger.error(f"[StateDB] Update error: {e}")
    
    def record_trade(self, tx_hash: str, token: str, entry_price: float, 
                     exit_price: float, reason: str, pnl_pct: float):
        """Records a closed trade in the Shadow Ledger."""
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO alpha_signals 
                (signal_type, tx_hash, entry_price, exit_price, pnl_pct, status, updated_at)
                VALUES (?, ?, ?, ?, ?, 'CLOSED', CURRENT_TIMESTAMP)
            """, ("trade", tx_hash, entry_price, exit_price, pnl_pct))
            self._get_conn().commit()
            logger.info(f"[ShadowLedger] Recorded {reason}: {pnl_pct:+.1f}% PnL")
        except Exception as e:
            logger.error(f"[ShadowLedger] Record error: {e}")
    
    def get_trading_stats(self) -> Dict[str, float]:
        """Returns live win-rate and trade count for Kelly sizing."""
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("SELECT COUNT(*) FROM alpha_signals WHERE status = 'CLOSED'")
            total_closed = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM alpha_signals WHERE status = 'CLOSED' AND pnl_pct > 0")
            wins = cursor.fetchone()[0]
            
            win_rate = wins / total_closed if total_closed > 0 else 0.5
            return {"win_rate": win_rate, "total_trades": total_closed, "wins": wins}
        except Exception as e:
            logger.error(f"[ShadowLedger] Stats error: {e}")
            return {"win_rate": 0.5, "total_trades": 0, "wins": 0}
    
    def get_open_positions(self, wallet: str) -> List[Dict]:
        """Fetches currently open positions for exit monitoring."""
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("""
                SELECT tx_hash, token_address, entry_price, token_amount 
                FROM alpha_signals 
                WHERE status = 'OPEN' AND wallet_address = ?
            """, (wallet,))
            return [
                {
                    "tx_hash": row[0],
                    "token_address": row[1],
                    "entry_price": row[2],
                    "token_amount": row[3]
                }
                for row in cursor.fetchall()
            ]
        except Exception as e:
            logger.error(f"[ShadowLedger] Position fetch error: {e}")
            return []
    
    def close(self):
        """Cleans up database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

# Global instance (lazy initialization)
_state_db: Optional[StateDB] = None

def get_state_db(db_path: str | Path) -> StateDB:
    """Returns singleton StateDB instance."""
    global _state_db
    if _state_db is None:
        _state_db = StateDB(db_path)
    return _state_db
