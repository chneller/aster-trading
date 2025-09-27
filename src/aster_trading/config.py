from __future__ import annotations

import os
from pydantic import BaseModel
from dotenv import load_dotenv


class Settings(BaseModel):
    api_key: str | None = None
    api_secret: str | None = None
    api_passphrase: str | None = None
    api_base: str = "https://fapi.asterdex.com"
    ws_base: str = "wss://fstream.asterdex.com"
    log_level: str = "INFO"


def load_settings() -> Settings:
    load_dotenv(override=False)
    return Settings(
        api_key=os.getenv("ASTER_API_KEY"),
        api_secret=os.getenv("ASTER_API_SECRET"),
        api_base=os.getenv("ASTER_API_BASE", "https://fapi.asterdex.com"),
        ws_base=os.getenv("ASTER_WS_BASE", "wss://fstream.asterdex.com"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )

