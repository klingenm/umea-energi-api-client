"""Stored tokens: refreshes them and logs them out (revoke), persisting every change."""

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from umea_energi_api_client import ApiError, TokenExpiredError, UmeaEnergiClient

from .models import AuthToken

logger = logging.getLogger(__name__)


class RefreshError(Exception):
    """The token couldn't be refreshed; the user has to log in again."""


class LogoutError(Exception):
    """The refresh token couldn't be revoked on the server; the stored token was kept."""


def _rejected(error: ApiError) -> bool:
    return error.status_code is not None and 400 <= error.status_code < 500


class TokenManager:
    def __init__(self, api: UmeaEnergiClient) -> None:
        self._api = api
        # One operation per token at a time: a refresh may rotate the refresh token, and a
        # concurrent refresh or revoke with the old one would then fail.
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def ensure_fresh(
        self, db: AsyncSession, token: AuthToken, *, force: bool = False
    ) -> AuthToken:
        """Refresh `token` if its access token is about to expire (or always, with `force`)."""
        async with self._locks[token.id]:
            # Another request may have refreshed it while this one waited for the lock.
            await db.refresh(token)
            await self._refresh(db, token, force=force)
            return token

    async def logout(self, db: AsyncSession, token: AuthToken) -> None:
        """Revoke the token's refresh token on the server, then delete the stored token."""
        async with self._locks[token.id]:
            await db.refresh(token)
            if token.can_refresh():
                try:
                    # Revoking needs a valid access token.
                    await self._refresh(db, token, force=False)
                except RefreshError:
                    if token.refresh_token:  # still set: the API wasn't reachable
                        raise LogoutError(
                            "Couldn't refresh the token before revoking it."
                        ) from None
                if token.refresh_token:
                    try:
                        await self._api.revoke(token.credentials)
                    except ApiError as error:
                        logger.warning("Revoking token %d failed: %s", token.id, error)
                        raise LogoutError(
                            f"Revoking the refresh token failed ({error})."
                        ) from error
                    logger.info("Revoked the refresh token of token %d", token.id)
            else:
                logger.info("Token %d has no usable refresh token; nothing to revoke", token.id)
            await db.delete(token)
            await db.commit()

    async def _refresh(self, db: AsyncSession, token: AuthToken, *, force: bool) -> None:
        current = token.credentials
        try:
            credentials = await self._api.fresh_credentials(current, force=force)
        except TokenExpiredError as error:
            raise RefreshError(
                "The access token has expired and can't be refreshed. Log in again."
            ) from error
        except ApiError as error:
            if _rejected(error):
                # Revoked, expired or already rotated: don't try it again.
                token.refresh_token = None
                await db.commit()
            logger.warning("Refreshing token %d failed: %s", token.id, error)
            raise RefreshError(f"Refreshing the token failed ({error}). Log in again.") from error
        if credentials is current:
            return
        token.apply(credentials)
        token.refreshed_at = datetime.now(UTC)
        await db.commit()
        logger.info(
            "Refreshed token %d for %s (expires %s)", token.id, token.display_name, token.expires_at
        )
