import os
import json
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from typing import Literal, Dict, Any

class AppConfig(BaseSettings):
    platform: Literal["telegram", "discord"] = "telegram"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""
    alchemy_api_key: str = ""
    check_interval_minutes: int = Field(5, ge=1)
    configs_dir: Path = Path("configs")
    db_path: Path = Path("alphapulse_state.db")

    @validator("alchemy_api_key")
    def warn_missing_keys(cls, v):
        if not v:
            print("[CONFIG] Warning: No ALCHEMY_API_KEY provided. Using public Base RPC fallback.")
        return v

    def get_rpc_url(self) -> str:
        return f"https://base-mainnet.g.alchemy.com/v2/{self.alchemy_api_key or 'demo'}" if self.alchemy_api_key else "https://mainnet.base.org"

    def get_notifier_creds(self) -> dict:
        return {
            "bot_token": self.telegram_bot_token,
            "chat_id": self.telegram_chat_id,
            "webhook_url": self.discord_webhook_url
        }

    def load_example_configs(self) -> Dict[str, Any]:
        configs = {}
        for f in self.configs_dir.glob("*.json"):
            with open(f) as fh:
                configs[f.stem] = json.load(fh)
        return configs

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = AppConfig()