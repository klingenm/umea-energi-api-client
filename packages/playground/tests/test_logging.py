import logging
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

from umea_energi_api_client.testing import FakeApi


def test_api_traffic_is_logged_without_secrets(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The app's loggers don't propagate to the root logger, where caplog listens by default.
    for name in ("umea_energi_playground", "umea_energi_api_client"):
        logging.getLogger(name).addHandler(caplog.handler)
    token = make_jwt(2_000_000_000)
    fake_api.add("POST", "/api/v2/Session/emailStep1", httpx.Response(200))
    fake_api.add(
        "POST", "/api/v2/Session/emailStep2", httpx.Response(200, json=login_session(token))
    )

    client.post("/login/email", data={"username": "ada@example.com", "password": "hunter2"})
    client.post("/login/email/verify", data={"username": "ada@example.com", "code": "424242"})

    logs = caplog.text
    assert "→ POST https://api.test/api/v2/Session/emailStep1" in logs
    assert "← 200 POST /api/v2/Session/emailStep2" in logs
    assert '"username": "ada@example.com"' in logs
    assert "email login succeeded: stored token 1 for Ada Lovelace" in logs
    for secret in ("hunter2", "424242", token):
        assert secret not in logs
