import sqlite3
import asyncio
from pathlib import Path
from typing import Optional, List
from config import settings  # ← ADD THIS LINE

class StateDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_state (
                    config_name TEXT PRIMARY KEY,
                    last_checked_ts INTEGER DEFAULT 0,
                    processed_ids TEXT DEFAULT '[]'
                )
            """)
            conn.commit()

    async def get_last_state(self, config_name: str) -> tuple[int, List[str]]:
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("SELECT last_checked_ts, processed_ids FROM alert_state WHERE config_name = ?", (config_name,))
                row = cur.fetchone()
                return (row[0], eval(row[1])) if row else (0, [])

    async def update_state(self, config_name: str, ts: int, new_ids: List[str]):
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO alert_state (config_name, last_checked_ts, processed_ids)
                    VALUES (?, ?, ?)
                """, (config_name, ts, str(new_ids)))
                conn.commit()

state_db = StateDB(settings.db_path)
