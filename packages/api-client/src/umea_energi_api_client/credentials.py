"""Login results: the tokens and the user they belong to."""

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Refresh this long before the access token expires, so a request doesn't race the expiry.
DEFAULT_REFRESH_MARGIN = timedelta(seconds=60)


def jwt_expiry(token: str) -> datetime | None:
    """Read the `exp` claim of a JWT without verifying it (the API is the one that verifies)."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(claims["exp"], UTC)
    except IndexError, KeyError, TypeError, ValueError:
        return None


@dataclass(frozen=True, kw_only=True)
class Credentials:
    """An access token (valid for about 10 minutes) and the refresh token that renews it."""

    access_token: str
    refresh_token: str | None = None
    refresh_token_expires_at: datetime | None = None

    @property
    def access_token_expires_at(self) -> datetime | None:
        return jwt_expiry(self.access_token)

    def is_expired(self, now: datetime | None = None) -> bool:
        expires = self.access_token_expires_at
        return expires is not None and expires <= (now or datetime.now(UTC))

    def needs_refresh(
        self, margin: timedelta = DEFAULT_REFRESH_MARGIN, now: datetime | None = None
    ) -> bool:
        """Whether the access token expires within `margin`. An unknown expiry counts as fresh."""
        expires = self.access_token_expires_at
        return expires is not None and expires - margin <= (now or datetime.now(UTC))

    def can_refresh(self, now: datetime | None = None) -> bool:
        if not self.refresh_token:
            return False
        expires = self.refresh_token_expires_at
        return expires is None or expires > (now or datetime.now(UTC))


@dataclass(frozen=True, kw_only=True)
class User:
    id: int | None
    display_name: str
    email: str | None
    customer_code: str | None
    """The code customer endpoints take: the default customer code, or the user's own customer."""


@dataclass(frozen=True, kw_only=True)
class Login:
    """A successful login or token refresh."""

    credentials: Credentials
    user: User | None
