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
        if isinstance(db_path, str):
            db_path = Path(db_path)
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn: Optional[sqlite3.Connection] = None
        self._init_schema()
    
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=30)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn
    
    def _init_schema(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Existing tables
        cursor.execute("""CREATE TABLE IF NOT EXISTS state_cache (
            config_name TEXT PRIMARY KEY, last_check_ts INTEGER NOT NULL,
            seen_ids TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS alpha_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_type TEXT NOT NULL,
            tx_hash TEXT UNIQUE, wallet_address TEXT, eth_value REAL,
            ai_score INTEGER, ai_reasoning TEXT, entry_price REAL,
            exit_price REAL, pnl_pct REAL, status TEXT DEFAULT 'OPEN',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS metrics (
            metric_name TEXT PRIMARY KEY, metric_value REAL NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

        # --- 🆕 NEW: WebSocket Listener Tables ---
        cursor.execute("""CREATE TABLE IF NOT EXISTS dex_swaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            router TEXT, token_in TEXT, token_out TEXT, amount_in REAL,
            amount_out REAL, tx_hash TEXT UNIQUE)""")
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS new_pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
            token0 TEXT, token1 TEXT, stable BOOLEAN, pool_address TEXT UNIQUE, tx_hash TEXT)""")
        
        conn.commit()
        logger.info(f"✅ StateDB initialized at {self.db_path}")
    
    # --- 🆕 NEW: WebSocket Logging Methods ---
    def log_dex_swap(self, router, token_in, token_out, amount_in, amount_out, tx_hash):
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("""INSERT OR IGNORE INTO dex_swaps 
                (router, token_in, token_out, amount_in, amount_out, tx_hash)
                VALUES (?, ?, ?, ?, ?, ?)""", 
                (router, token_in, token_out, amount_in, amount_out, tx_hash))
            self._get_conn().commit()
        except Exception as e:
            logger.error(f"[StateDB] Log swap error: {e}")

    def log_new_pool(self, token0, token1, stable, pool_address, tx_hash):
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("""INSERT OR IGNORE INTO new_pools 
                (token0, token1, stable, pool_address, tx_hash)
                VALUES (?, ?, ?, ?, ?)""", 
                (token0, token1, stable, pool_address, tx_hash))
            self._get_conn().commit()
        except Exception as e:
            logger.error(f"[StateDB] Log pool error: {e}")

    # --- EXISTING METHODS (Preserved for Dashboard) ---
    async def get_last_state(self, config_name: str) -> Tuple[int, List[str]]:
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("SELECT last_check_ts, seen_ids FROM state_cache WHERE config_name = ?", (config_name,))
            row = cursor.fetchone()
            if row:
                import json
                return row[0], json.loads(row[1]) if row[1] else []
            return 0, []
        except Exception as e:
            logger.error(f"[StateDB] Fetch error: {e}")
            return 0, []
    
    async def update_state(self, config_name: str, check_ts: int, seen_ids: List[str]):
        try:
            import json
            cursor = self._get_conn().cursor()
            cursor.execute("""INSERT OR REPLACE INTO state_cache 
                (config_name, last_check_ts, seen_ids, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)""", 
                (config_name, check_ts, json.dumps(seen_ids[-100:])))
            self._get_conn().commit()
        except Exception as e:
            logger.error(f"[StateDB] Update error: {e}")
    
    def get_trading_stats(self) -> Dict[str, float]:
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("SELECT COUNT(*) FROM alpha_signals WHERE status = 'CLOSED'")
            total_closed = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM alpha_signals WHERE status = 'CLOSED' AND pnl_pct > 0")
            wins = cursor.fetchone()[0]
            return {"win_rate": wins / total_closed if total_closed > 0 else 0.5, "total_trades": total_closed, "wins": wins}
        except Exception as e:
            return {"win_rate": 0.5, "total_trades": 0, "wins": 0}

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

# Global instance
_state_db: Optional[StateDB] = None
def get_state_db(db_path: str | Path) -> StateDB:
    global _state_db
    if _state_db is None:
        _state_db = StateDB(db_path)
    return _state_db

from config import settings
state_db = StateDB(settings.db_path)
