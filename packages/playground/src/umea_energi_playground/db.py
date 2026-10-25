"""Database plumbing: the declarative base, column types and Alembic migrations."""

from datetime import UTC, datetime
from typing import ClassVar

from alembic import command
from alembic.config import Config
from sqlalchemy import DateTime, Dialect, TypeDecorator
from sqlalchemy.orm import DeclarativeBase

MIGRATIONS = "umea_energi_playground:migrations"


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime stored as naive UTC, since SQLite has no time zone support."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar = {datetime: UTCDateTime}


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    # Config values go through configparser interpolation, so escape literal percent signs.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade_database(database_url: str) -> None:
    """Apply all pending migrations. Blocking; run it in a worker thread from async code."""
    command.upgrade(alembic_config(database_url), "head")
