"""Debug logging of every request to and response from the API, with secrets redacted.

Enable it with `logging.getLogger("umea_energi_api_client").setLevel(logging.DEBUG)`.
"""

import json
import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Values under these JSON keys (compared case-insensitively) are never logged: credentials,
# personal identity numbers, contact details and client IPs. Any key containing "token" is
# redacted as well, since the API names tokens inconsistently (access_token, accessJwtToken, ...).
REDACTED_KEYS = frozenset(
    {
        "password",
        "activationkey",
        "pnr",
        "persno",
        "phone",
        "phoneno",
        "mobileno",
        "faxno",
        "address",
        "coaddress",
        "postalno",
        "createdbyip",
        "revokedbyip",
    }
)
# JSON keys whose values are long but harmless; logged as their length only.
SUMMARIZED_KEYS = frozenset({"qrcode"})
MAX_BODY_CHARS = 2000
# Backstop for tokens under unexpected keys or in non-JSON bodies.
JWT_PATTERN = re.compile(r"eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+")
_STARTED = "umea_energi_api_client.started"


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_item(str(key), item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _redact_item(key: str, value: Any) -> Any:
    folded = key.lower()
    if value is None or isinstance(value, dict | list):
        return redact(value)
    if folded in REDACTED_KEYS or "token" in folded:
        return "<redacted>"
    if folded in SUMMARIZED_KEYS and isinstance(value, str):
        return f"<{len(value)} chars>"
    return value


def format_body(content: bytes) -> str:
    """A loggable rendering of a request or response body."""
    if not content:
        return "(empty body)"
    try:
        text = json.dumps(redact(json.loads(content)), ensure_ascii=False)
    except ValueError:
        text = content.decode(errors="replace")
    text = JWT_PATTERN.sub("<redacted>", text)
    if len(text) > MAX_BODY_CHARS:
        return f"{text[:MAX_BODY_CHARS]}… ({len(text)} chars)"
    return text


async def log_request(request: httpx.Request) -> None:
    request.extensions[_STARTED] = time.perf_counter()
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("→ %s %s %s", request.method, request.url, format_body(request.content))


async def log_response(response: httpx.Response) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return
    await response.aread()
    request = response.request
    started = request.extensions.get(_STARTED, time.perf_counter())
    # Cookie names only; values may be session secrets. Headers are never logged.
    cookies = [header.split("=", 1)[0] for header in response.headers.get_list("set-cookie")]
    logger.debug(
        "← %s %s %s (%.0f ms)%s %s",
        response.status_code,
        request.method,
        request.url.path,
        (time.perf_counter() - started) * 1000,
        f" sets cookies {cookies}" if cookies else "",
        format_body(response.content),
    )


EVENT_HOOKS: dict[str, list[Any]] = {"request": [log_request], "response": [log_response]}
