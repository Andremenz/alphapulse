import os
import json
import logging
from datetime import datetime
from ipfshttpclient import Client as IPFSClient

logger = logging.getLogger("IPFSStorage")

# IPFS Configuration (geo-permissionless, no KYC)
IPFS_GATEWAY = os.environ.get("IPFS_GATEWAY", "https://ipfs.io")
PINATA_API_KEY = os.environ.get("PINATA_API_KEY")  # Optional: for reliable pinning
PINATA_SECRET = os.environ.get("PINATA_SECRET")

class IPFSLedger:
    """
    Decentralized Shadow Ledger backed by IPFS.
    Falls back to local SQLite if IPFS is unavailable (hybrid mode).
    """
    def __init__(self, fallback_db_path: str = "./data/alphapulse_shadow.db"):
        self.fallback_path = fallback_db_path
        self.ipfs = None
        self.use_ipfs = os.environ.get("DECENTRALIZED_MODE", "false").lower() == "true"
        
        if self.use_ipfs:
            try:
                self.ipfs = IPFSClient(IPFS_GATEWAY)
                logger.info("✅ IPFS client initialized")
            except Exception as e:
                logger.warning(f"⚠️ IPFS init failed, falling back to local SQLite: {e}")
                self.use_ipfs = False
    
    def _save_local(self, data: dict, cid_key: str):
        """Fallback: save to local SQLite (Railway volume)"""
        import sqlite3
        conn = sqlite3.connect(self.fallback_path)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ipfs_cache (
            cid_key TEXT PRIMARY KEY,
            data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute(
            "INSERT OR REPLACE INTO ipfs_cache (cid_key, data) VALUES (?, ?)",
            (cid_key, json.dumps(data))
        )
        conn.commit()
        conn.close()
    
    def _load_local(self, cid_key: str) -> dict:
        """Fallback: load from local SQLite"""
        import sqlite3
        conn = sqlite3.connect(self.fallback_path)
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM ipfs_cache WHERE cid_key = ?", (cid_key,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return {}
    
    def save_signal(self, signal: dict) -> str:
        """
        Saves a trading signal to IPFS and returns the CID.
        Falls back to local SQLite if IPFS fails.
        """
        signal["timestamp"] = datetime.utcnow().isoformat()
        signal["decentralized"] = self.use_ipfs
        
        if self.use_ipfs and self.ipfs:
            try:
                # Add to IPFS and get CID
                result = self.ipfs.add_json(signal)
                cid = result["Hash"]
                logger.info(f"📦 Signal saved to IPFS: {cid}")
                
                # Optional: Pin via Pinata for persistence
                if PINATA_API_KEY and PINATA_SECRET:
                    import requests
                    headers = {"pinata_api_key": PINATA_API_KEY, "pinata_secret_api_key": PINATA_SECRET}
                    json_data = {"hashToPin": cid, "pinataMetadata": {"name": f"alphapulse-signal-{signal.get('proposal_id', 'unknown')}"}}
                    requests.post("https://api.pinata.cloud/pinning/pinByHash", headers=headers, json=json_data)
                
                # Cache locally for fast reads
                self._save_local(signal, cid)
                return cid
            except Exception as e:
                logger.warning(f"⚠️ IPFS save failed, falling back to local: {e}")
        
        # Fallback: save locally only
        cid = f"local_{signal.get('proposal_id', 'unknown')}_{datetime.utcnow().timestamp()}"
        self._save_local(signal, cid)
        logger.info(f"📦 Signal saved locally: {cid}")
        return cid
    
    def load_signal(self, cid: str) -> dict:
        """Loads a signal by CID, trying IPFS first then local fallback"""
        if self.use_ipfs and self.ipfs and cid.startswith("Qm"):
            try:
                data = self.ipfs.cat_json(cid)
                logger.info(f"📥 Signal loaded from IPFS: {cid}")
                return data
            except Exception as e:
                logger.warning(f"⚠️ IPFS load failed, trying local fallback: {e}")
        
        # Fallback to local
        data = self._load_local(cid)
        if data:
            logger.info(f"📥 Signal loaded from local cache: {cid}")
        return data
    
    def get_all_signals(self, limit: int = 100) -> list:
        """Returns recent signals from local cache (IPFS enumeration is non-trivial)"""
        import sqlite3
        conn = sqlite3.connect(self.fallback_path)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT data FROM ipfs_cache 
        ORDER BY timestamp DESC 
        LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [json.loads(row[0]) for row in rows]

# Global instance for easy import
ipfs_ledger = IPFSLedger()
