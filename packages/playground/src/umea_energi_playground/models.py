"""Database models. After changing them, run `mise run playground:revision -- -m "..."`."""

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from umea_energi_api_client import Credentials

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
    refresh_token: Mapped[str | None] = mapped_column(Text)
    refresh_token_expires_at: Mapped[datetime | None]
    refreshed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    @property
    def credentials(self) -> Credentials:
        return Credentials(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            refresh_token_expires_at=self.refresh_token_expires_at,
        )

    def apply(self, credentials: Credentials) -> None:
        """Store new tokens from a login or refresh."""
        self.access_token = credentials.access_token
        self.expires_at = credentials.access_token_expires_at
        self.refresh_token = credentials.refresh_token
        self.refresh_token_expires_at = credentials.refresh_token_expires_at

    def is_expired(self) -> bool:
        return self.credentials.is_expired()

    def can_refresh(self) -> bool:
        return self.credentials.can_refresh()
