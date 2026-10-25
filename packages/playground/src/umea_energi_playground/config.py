"""Runtime settings, read from environment variables."""

import os
from dataclasses import dataclass
from typing import Self

from umea_energi_api_client import DEFAULT_API_VERSION, PRODUCTION_BASE_URL

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///playground.db"
DEFAULT_LOG_LEVEL = "INFO"
# The API client logs every request and response (with secrets redacted) at DEBUG.
DEFAULT_API_LOG_LEVEL = "DEBUG"


@dataclass(frozen=True, kw_only=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    api_base_url: str = PRODUCTION_BASE_URL
    api_version: str = DEFAULT_API_VERSION
    log_level: str = DEFAULT_LOG_LEVEL
    api_log_level: str = DEFAULT_API_LOG_LEVEL

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            database_url=os.environ.get("PLAYGROUND_DATABASE_URL", DEFAULT_DATABASE_URL),
            api_base_url=os.environ.get("PLAYGROUND_API_BASE_URL", PRODUCTION_BASE_URL),
            api_version=os.environ.get("PLAYGROUND_API_VERSION", DEFAULT_API_VERSION),
            log_level=os.environ.get("PLAYGROUND_LOG_LEVEL", DEFAULT_LOG_LEVEL),
            api_log_level=os.environ.get("PLAYGROUND_API_LOG_LEVEL", DEFAULT_API_LOG_LEVEL),
        )
