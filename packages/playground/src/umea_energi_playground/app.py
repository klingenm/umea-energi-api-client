"""FastAPI application factory. Run with `mise run playground`."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from umea_energi_api_client import UmeaEnergiClient

from .config import Settings
from .db import upgrade_database
from .logs import configure_logging
from .routes import router
from .tokens import TokenManager


def create_app(
    settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    """Build the app. `transport` replaces the network layer for API calls (used in tests)."""
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level, settings.api_log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        await asyncio.to_thread(upgrade_database, settings.database_url)
        engine = create_async_engine(settings.database_url)
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Umeå Energi API playground", lifespan=lifespan)
    app.state.api = UmeaEnergiClient(
        settings.api_base_url,
        api_version=settings.api_version,
        httpx_args=None if transport is None else {"transport": transport},
    )
    app.state.tokens = TokenManager(app.state.api)
    app.include_router(router)
    return app
