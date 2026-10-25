"""Runtime settings, read from environment variables."""

import os
from dataclasses import dataclass
from typing import Self

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///playground.db"
DEFAULT_API_BASE_URL = "https://tapi.umeaenergi.se"
DEFAULT_API_VERSION = "2"


@dataclass(frozen=True, kw_only=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    api_base_url: str = DEFAULT_API_BASE_URL
    api_version: str = DEFAULT_API_VERSION

    @classmethod
    def from_env(cls) -> Self:
        return cls(
            database_url=os.environ.get("PLAYGROUND_DATABASE_URL", DEFAULT_DATABASE_URL),
            api_base_url=os.environ.get("PLAYGROUND_API_BASE_URL", DEFAULT_API_BASE_URL),
            api_version=os.environ.get("PLAYGROUND_API_VERSION", DEFAULT_API_VERSION),
        )
