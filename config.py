import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()

class AppConfig:
    """Centralized configuration for AlphaPulse."""
    
    def __init__(self):
        # 🚨 CRITICAL FIX: Add db_path attribute
        self.db_path = os.environ.get("DB_PATH", "/data/alphapulse.db")
        
        # Blockchain settings
        self.active_chain = os.environ.get("ACTIVE_CHAIN", "base")
        self.base_rpc = os.environ.get("BASE_RPC", "https://mainnet.base.org")
        self.basescan_api_key = os.environ.get("BASESCAN_API_KEY", "")
        
        # AI settings
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.ai_confidence_threshold = int(os.environ.get("AI_CONFIDENCE_THRESHOLD", "60"))
        
        # Trading settings
        self.base_private_key = os.environ.get("BASE_PRIVATE_KEY", "")
        self.take_profit_pct = float(os.environ.get("TAKE_PROFIT_PCT", "0.15"))
        self.stop_loss_pct = float(os.environ.get("STOP_LOSS_PCT", "0.10"))
        self.slippage_pct = float(os.environ.get("SLIPPAGE_PCT", "0.015"))
        
        # Notification settings
        self.platform = os.environ.get("PLATFORM", "telegram")
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        
        # Scheduler settings
        self.check_interval_minutes = int(os.environ.get("CHECK_INTERVAL_MINUTES", "5"))
        
        # Volume persistence (Hugging Face / Railway compatibility)
        self.volume_mount_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/data")
        
        # Ensure data directory exists
        Path(self.volume_mount_path).mkdir(parents=True, exist_ok=True)
        
        # Override db_path if volume mount is set
        if self.volume_mount_path != "/data":
            self.db_path = os.path.join(self.volume_mount_path, "alphapulse.db")
    
    def get_notifier_creds(self):
        """Returns notification credentials based on platform."""
        if self.platform == "telegram":
            return {
                "bot_token": self.telegram_bot_token,
                "chat_id": self.telegram_chat_id
            }
        return {}
    
    def load_example_configs(self):
        """Returns example monitoring configurations."""
        return {
            "whale_watch": {
                "type": "whale",
                "threshold_eth": 10.0,
                "check_interval_minutes": self.check_interval_minutes
            },
            "governance_watch": {
                "type": "governance",
                "space": "aave.eth",
                "check_interval_minutes": self.check_interval_minutes
            },
            "weekly_digest": {
                "type": "digest",
                "check_interval_minutes": 10080  # 7 days
            }
        }
    
    def load_config(self, name: str):
        """Loads a specific config by name."""
        configs = self.load_example_configs()
        return configs.get(name)

# Global settings instance
settings = AppConfig()
