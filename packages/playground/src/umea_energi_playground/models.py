"""Database models. After changing them, run `mise run playground:revision -- -m "..."`."""

import base64
import json
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class LoginMethod(StrEnum):
    BANKID = "bankid"
    EMAIL = "email"


class AuthToken(Base):
    """An access token obtained by logging in to the Umeå Energi API."""

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    method: Mapped[LoginMethod] = mapped_column(
        Enum(
            LoginMethod,
            native_enum=False,
            length=16,
            values_callable=lambda members: [member.value for member in members],
        )
    )
    display_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    api_user_id: Mapped[int | None]
    customer_code: Mapped[str | None] = mapped_column(String(64))
    access_token: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and self.expires_at <= (now or datetime.now(UTC))


def jwt_expiry(token: str) -> datetime | None:
    """Read the `exp` claim of a JWT without verifying it (the API is the one that verifies)."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return datetime.fromtimestamp(claims["exp"], UTC)
    except IndexError, KeyError, TypeError, ValueError:
        return None
