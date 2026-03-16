from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    app_name: str = "AgentShield Lite"
    debug: bool = False
    database_url: str = "sqlite+aiosqlite:///./agentshield.db"

    # Auth
    api_key: Optional[str] = None

    # Risk
    risk_alert_threshold: int = 70

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # ── Alert channels ────────────────────────────────────────────────────────
    # Slack
    slack_webhook_url: Optional[str] = None

    # Microsoft Teams
    teams_webhook_url: Optional[str] = None

    # Email (SMTP)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_tls: bool = True
    alert_email_to: Optional[str] = None  # recipient address

    # Generic webhooks (comma-separated URLs)
    webhook_urls: list[str] = []

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
