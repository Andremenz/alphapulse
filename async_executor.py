#!/usr/bin/env python3
"""
AlphaPulse Async Executor - Minimal Self-Contained Version
Guaranteed to run on Hugging Face Spaces without package import issues.
"""
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# =============================================================================
# 🚨 INLINE CONFIG (No external config.py dependency)
# =============================================================================
class MinimalConfig:
    def __init__(self):
        self.db_path = Path(os.environ.get("DB_PATH", "/data/alphapulse.db"))
        self.active_chain = os.environ.get("ACTIVE_CHAIN", "base")
        self.base_rpc = os.environ.get("BASE_RPC", "https://mainnet.base.org")
        self.base_private_key = os.environ.get("BASE_PRIVATE_KEY", "")
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.volume_mount_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/data")
        
        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

settings = MinimalConfig()

# =============================================================================
# 🚨 INLINE WEB3 SETUP (No external chain_config.py dependency)
# =============================================================================
try:
    from web3 import Web3
    CFG_W3 = Web3(Web3.HTTPProvider(settings.base_rpc))
except ImportError:
    print("⚠️ web3 not available - running in monitor-only mode")
    CFG_W3 = None

# =============================================================================
# 🚨 INLINE DATABASE (No external database.py dependency)
# =============================================================================
import sqlite3
class MinimalStateDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = None
        self._init_schema()
    
    def _get_conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=30)
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn
    
    def _init_schema(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS state_cache (
            config_name TEXT PRIMARY KEY, last_check_ts INTEGER, seen_ids TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS alpha_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_type TEXT, tx_hash TEXT UNIQUE,
            entry_price REAL, exit_price REAL, pnl_pct REAL, status TEXT DEFAULT 'OPEN')""")
        conn.commit()
        print(f"✅ StateDB initialized at {self.db_path}")
    
    async def get_last_state(self, config_name: str):
        try:
            cursor = self._get_conn().cursor()
            cursor.execute("SELECT last_check_ts, seen_ids FROM state_cache WHERE config_name=?", (config_name,))
            row = cursor.fetchone()
            if row:
                import json
                return row[0], json.loads(row[1]) if row[1] else []
            return 0, []
        except: return 0, []
    
    async def update_state(self, config_name: str, check_ts: int, seen_ids: list):
        try:
            import json
            cursor = self._get_conn().cursor()
            cursor.execute("INSERT OR REPLACE INTO state_cache VALUES (?,?,?)", 
                         (config_name, check_ts, json.dumps(seen_ids[-100:])))
            self._get_conn().commit()
        except: pass

state_db = MinimalStateDB(settings.db_path)

# =============================================================================
# 🚨 MAIN EXECUTOR LOOP (No external fetchers dependency)
# =============================================================================
logger = logging.getLogger("AsyncExecutor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

SMART_WALLETS = [
    "0x6d4223342506d27548042B1B86d0389675F972b2",  # Jesse Pollak
    "0x3154Cf16ccdb4C6d922629664174b904d80F2C35",  # Base Bridge
]
SEEN_TXS = set()
MIN_ETH = 0.5

async def poll_blockchain():
    """Minimal blockchain polling loop - no external dependencies."""
    print(f"[AsyncExecutor] Starting Async Block Listener (Base 2s block time)...")
    last_block = None
    
    while True:
        try:
            if CFG_W3:
                current_block = CFG_W3.eth.block_number
                if current_block != last_block:
                    print(f"[AsyncExecutor] Starting from live block {current_block}")
                    last_block = current_block
                    
                    # Minimal wallet scan (inline, no fetchers import)
                    for wallet in SMART_WALLETS:
                        try:
                            # Check last 5 blocks for activity
                            for i in range(5):
                                block_num = current_block - i
                                if block_num < 0: continue
                                block = CFG_W3.eth.get_block(block_num, full_transactions=True)
                                for tx in block.transactions:
                                    if isinstance(tx, dict):
                                        tx_hash = tx.get('hash', b'').hex() if tx.get('hash') else None
                                        from_addr = tx.get('from', '').lower()
                                        to_addr = tx.get('to', '').lower() if tx.get('to') else ''
                                        value_eth = float(CFG_W3.from_wei(tx.get('value', 0), 'ether'))
                                        
                                        if tx_hash and tx_hash not in SEEN_TXS:
                                            if from_addr == wallet.lower() or to_addr == wallet.lower():
                                                if value_eth >= MIN_ETH:
                                                    SEEN_TXS.add(tx_hash)
                                                    print(f"🚨 SMART MONEY: {wallet[:10]}... | {value_eth:.3f} ETH | Block {block_num}")
                                                    # Here you would route to AI/execution in full version
                        except Exception as e:
                            pass  # Skip errors, continue polling
                await asyncio.sleep(2)  # Base block time
            else:
                # Fallback: just log heartbeat if web3 unavailable
                print(f"[AsyncExecutor] Heartbeat - monitoring mode (web3 unavailable)")
                await asyncio.sleep(10)
                
        except Exception as e:
            print(f"[AsyncExecutor] Polling error: {e}")
            await asyncio.sleep(5)

# =============================================================================
# 🚨 ENTRY POINT
# =============================================================================
async def main():
    print("🚀 AlphaPulse Dual-Process Engine Initializing...")
    print(f"📡 Using port: {os.environ.get('PORT', 7860)}")
    print("✅ Async Executor started in background")
    
    # Start blockchain polling
    await poll_blockchain()

if __name__ == "__main__":
    # Run the async main loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Shutdown requested")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)
