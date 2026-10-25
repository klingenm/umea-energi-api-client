"""Alembic environment for the playground database.

The database URL comes from the caller (`db.upgrade_database`) or, on the command line,
from `PLAYGROUND_DATABASE_URL` (see `config.Settings`).
"""

import asyncio
import logging
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from umea_energi_playground import models  # noqa: F401 (registers the tables on Base.metadata)
from umea_energi_playground.config import Settings
from umea_energi_playground.db import Base, UTCDateTime

config = context.config

if config.cmd_opts is not None:
    # Running from the alembic CLI: show which migrations run.
    logging.basicConfig(format="%(levelname)-5.5s [%(name)s] %(message)s")
    logging.getLogger("alembic").setLevel(logging.INFO)

if not config.file_config.has_option(config.config_ini_section, "sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", Settings.from_env().database_url.replace("%", "%%"))


def render_item(type_: str, obj: Any, autogen_context: AutogenContext) -> str | Literal[False]:
    """Render app-specific column types as plain SQLAlchemy ones, so migrations stay standalone."""
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime()"
    return False


def configure(**kwargs: Any) -> None:
    context.configure(
        target_metadata=Base.metadata,
        # SQLite can't ALTER most things; batch mode recreates the table instead.
        render_as_batch=True,
        render_item=render_item,
        **kwargs,
    )


def run_migrations_offline() -> None:
    configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
