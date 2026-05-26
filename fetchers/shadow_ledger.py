import sqlite3
import httpx
import os
from datetime import datetime

# Ensure the persistent data directory exists (matches Railway Volume mount)
os.makedirs("data", exist_ok=True)
DB_PATH = "data/alpha_pulse_ledger.db"

# Mapping Snapshot spaces to CoinGecko IDs for accurate price fetching
DAO_TOKEN_MAP = {
    "aave.eth": "aave",
    "uniswap": "uniswap",
    "optimism": "optimism-ethereum",
    "arbitrum": "arbitrum",
    "ens.eth": "ethereum-name-service",
    "baseswap": "baseswap",
    "aerodrome": "aerodrome-finance",
    "friendtech": "friend-tech",
    "balancer": "balancer",
    "curve": "curve-dao-token",
    "lido": "lido-dao",
    "maker": "maker",
    "snapshot": "snapshot" 
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alpha_signals (
            proposal_id TEXT PRIMARY KEY,
            timestamp DATETIME,
            space TEXT,
            title TEXT,
            token_id TEXT,
            entry_price REAL,
            target_price REAL,
            ai_score INTEGER,
            ai_reasoning TEXT,
            status TEXT DEFAULT 'OPEN'
        )
    """)
    conn.commit()
    conn.close()

async def get_token_price(token_id: str) -> float:
    if not token_id: return 0.0
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies=usd"
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=10.0)
            data = resp.json()
            return data.get(token_id, {}).get("usd", 0.0)
        except Exception:
            return 0.0

async def log_snipe_signal(proposal: dict):
    init_db()
    space = proposal.get("space", "").lower()
    token_id = DAO_TOKEN_MAP.get(space)
    
    if not token_id:
        print(f"[LEDGER] Skipping {space} - no token mapping found.")
        return

    entry_price = await get_token_price(token_id)
    if entry_price == 0.0:
        print(f"[LEDGER] Skipping {space} - could not fetch price.")
        return

    # Set a standard 15% Take Profit target for the narrative pump
    target_price = entry_price * 1.15 

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO alpha_signals 
            (proposal_id, timestamp, space, title, token_id, entry_price, target_price, ai_score, ai_reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proposal["id"], datetime.utcnow().isoformat(), space, proposal["title"],
            token_id, entry_price, target_price, proposal["ai_score"], proposal["ai_reasoning"]
        ))
        conn.commit()
        if cursor.rowcount > 0:
            print(f"[LEDGER] ✅ Logged SNIPE signal for {space.upper()} @ ${entry_price} | Target: ${target_price:.4f}")
    except Exception as e:
        print(f"[LEDGER] DB Error: {e}")
    finally:
        conn.close()
