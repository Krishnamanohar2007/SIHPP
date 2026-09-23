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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("notification_channels", mode="before")
    @classmethod
    def split_channels(cls, value):
        if isinstance(value, str):
            return [channel.strip().lower() for channel in value.split(",") if channel.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
