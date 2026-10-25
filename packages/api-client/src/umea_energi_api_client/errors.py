"""Exceptions raised by `UmeaEnergiClient`."""

import json
from typing import Any

from .generated.types import Response


class UmeaEnergiError(Exception):
    """Base class for errors from this library."""


class ApiError(UmeaEnergiError):
    """A request failed. `status_code` is None when no response was received (network error)."""

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail if status_code is None else f"HTTP {status_code}: {detail}")
        self.detail = detail
        self.status_code = status_code

    @classmethod
    def from_response(cls, response: Response[Any]) -> ApiError:
        return cls(error_detail(response.content), int(response.status_code))


class InvalidCredentialsError(ApiError):
    """The API didn't accept the email and password (or there is no such account)."""


def error_detail(content: bytes) -> str:
    """A short, human-readable reason from an error response body."""
    text = content.decode(errors="replace").strip()
    try:
        data = json.loads(text)
    except ValueError:
        return text[:500] or "(empty response)"
    if isinstance(data, dict):
        for key in ("message", "title", "error", "detail"):
            if isinstance(data.get(key), str):
                return data[key]
    return text[:500]
