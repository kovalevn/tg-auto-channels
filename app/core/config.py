from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    app_name: str = Field(default="tg-auto-channels", alias="APP_NAME")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(..., alias="DATABASE_URL")
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    telegraph_token: str | None = Field(default=None, alias="TELEGRAPH_TOKEN")
    posting_interval_minutes: int = Field(default=10, alias="POSTING_INTERVAL_MINUTES")

    environment: Literal["dev", "prod", "test"] = Field(default="dev", alias="ENVIRONMENT")


@lru_cache()
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]
