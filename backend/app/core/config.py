from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'trade.db'}"
    config_path: str = str(ROOT_DIR / "configs" / "default.yaml")

    gateway_type: str = "sim"
    gateway_url: str = "http://127.0.0.1:8100"
    gateway_token: str = "change-me"
    live_trading_enabled: bool = False
    initial_cash: float = 1_000_000.0
    app_password: str = ""
    app_username: str = "aqt"

    # OpenAI-compatible LLM（也可在 UI 覆盖写入 system_state）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 180.0
    tavily_api_key: str = ""
    appbuilder_token: str = ""  # 千帆 AppBuilder API Key，环境变量 APPBUILDER_TOKEN


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def load_yaml_config() -> dict[str, Any]:
    path = Path(get_settings().config_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reload_config() -> dict[str, Any]:
    load_yaml_config.cache_clear()
    return load_yaml_config()