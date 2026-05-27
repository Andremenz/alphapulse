import os
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class AppConfig:
    """Centralized configuration with decentralized overrides"""
    
    # Core settings
    platform: str = os.environ.get("PLATFORM", "telegram").lower()
    check_interval_minutes: int = int(os.environ.get("CHECK_INTERVAL_MINUTES", "5"))
    
    # Decentralized mode flags
    decentralized_mode: bool = os.environ.get("DECENTRALIZED_MODE", "false").lower() == "true"
    ipfs_gateway: str = os.environ.get("IPFS_GATEWAY", "https://ipfs.io")
    akash_network: str = os.environ.get("AKASH_NETWORK", "mainnet")
    
    # API Keys (optional in decentralized mode)
    groq_api_key: Optional[str] = os.environ.get("GROQ_API_KEY")
    basescan_api_key: Optional[str] = os.environ.get("BASESCAN_API_KEY")
    telegram_bot_token: Optional[str] = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Trading config
    active_chain: str = os.environ.get("ACTIVE_CHAIN", "base")
    snipe_amount_eth: Optional[str] = os.environ.get("SNIPE_AMOUNT_ETH")  # Deprecated: use Kelly sizing
    
    def get_notifier_creds(self) -> Dict[str, str]:
        """Returns Telegram/Discord credentials"""
        if self.platform == "telegram":
            return {
                "bot_token": self.telegram_bot_token or "",
                "chat_id": self.telegram_chat_id or ""
            }
        elif self.platform == "discord":
            return {"webhook_url": os.environ.get("DISCORD_WEBHOOK_URL", "")}
        return {}
    
    def load_example_configs(self) -> Dict[str, Dict]:
        """Returns example fetcher configs (override in decentralized mode)"""
        return {
            "whalewatch": {"type": "whale", "threshold_eth": 10.0},
            "govwatch": {"type": "governance", "space": "aerodrome"},
            "degendigest": {"type": "digest"},
            "sundaydigest": {"type": "digest"},
            "vestingwatch": {"type": "vesting", "contracts": [{"address": "0x...", "chain": "base"}]},
            "solana_watch": {"type": "solana_monitor", "programs": []},
            "intelligence": {"type": "intelligence", "contracts": []},
        }

# Global instance
settings = AppConfig()
