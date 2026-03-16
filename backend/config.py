from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "AgentShield Lite"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./agentshield.db"
    slack_webhook_url: Optional[str] = None
    risk_alert_threshold: int = 70
    api_key: Optional[str] = None
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
