from functools import lru_cache
from pydantic import field_validator
from typing import Annotated

from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Land Acquisition Risk Monitor API"
    environment: str = "development"
    database_url: str
    notification_channels: Annotated[list[str], NoDecode] = ["console"]
    notification_risk_threshold: float = 60
    notification_recipient: str = "risk-operations@example.invalid"
    notification_scan_interval_minutes: int = 15
    retrain_interval_hours: int = 0  # 0 disables scheduled continuous learning
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://localhost:8080"]
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("notification_channels", "cors_origins", mode="before")
    @classmethod
    def split_channels(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("notification_channels", mode="after")
    @classmethod
    def normalize_channels(cls, value):
        return [channel.lower() for channel in value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
