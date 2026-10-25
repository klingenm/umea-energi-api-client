import asyncio
import base64
import json
import logging
from collections.abc import Awaitable
from datetime import UTC, datetime

import httpx
import pytest

from umea_energi_api_client import (
    DEFAULT_API_VERSION,
    PRODUCTION_BASE_URL,
    USER_AGENT,
    ApiError,
    Credentials,
    CustomerType,
    InvalidCredentialsError,
    TokenExpiredError,
    UmeaEnergiClient,
    __version__,
    jwt_expiry,
)
from umea_energi_api_client.generated.api.disturbance import get_api_vversion_disturbance
from umea_energi_api_client.testing import FakeApi

SESSION = "/api/v1/Session"


def run[T](awaitable: Awaitable[T]) -> T:
    async def wrap() -> T:
        return await awaitable

    return asyncio.run(wrap())


def make_jwt(exp: int) -> str:
    def encode(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{encode({'alg': 'none'})}.{encode({'exp': exp})}.signature"


def production_session(token: str) -> dict[str, object]:
    """A completed login as the production API returns it (made-up values)."""
    return {
        "completed": True,
        "token": {"access_token": token},
        "user": {
            "id": 7,
            "firstName": "Ada",
            "lastName": "Lovelace",
            "email": "ada@example.com",
            "customer": {"code": "128"},
            "defaultCustomerCode": None,
            "refreshToken": {"token": "body-refresh", "expires": "2027-01-01T00:00:00+01:00"},
        },
    }


def cookie(value: str) -> dict[str, str]:
    return {"set-cookie": f"refreshToken={value}; path=/; secure; httponly"}


@pytest.fixture
def fake() -> FakeApi:
    return FakeApi()


@pytest.fixture
def client(fake: FakeApi) -> UmeaEnergiClient:
    return UmeaEnergiClient("https://api.test", httpx_args={"transport": fake.transport})


def test_defaults_to_production_and_api_version_1() -> None:
    client = UmeaEnergiClient()

    assert client.base_url == PRODUCTION_BASE_URL == "https://api.umeaenergi.se"
    assert client.api_version == DEFAULT_API_VERSION == "1"


def test_bankid_flow(client: UmeaEnergiClient, fake: FakeApi) -> None:
    token = make_jwt(2_000_000_000)
    # `completed` on the start response only means the order was created.
    fake.add(
        "POST", f"{SESSION}/bankid", httpx.Response(200, json={"id": "ref", "completed": True})
    )
    fake.add(
        "GET",
        f"{SESSION}/bankid/ref/1",
        httpx.Response(200, json={"id": "ref", "qrCode": "UVI=", "autoStartToken": "auto"}),
        httpx.Response(200, json=production_session(token), headers=cookie("cookie-refresh")),
    )

    started = run(client.start_bankid(CustomerType.COMPANY))
    pending = run(client.poll_bankid("ref", CustomerType.COMPANY))
    done = run(client.poll_bankid("ref", CustomerType.COMPANY))

    assert started.reference == "ref"
    assert started.login is None
    assert json.loads(fake.requests[0].content) == {"type": 1}
    assert (pending.qr_code, pending.auto_start_token, pending.login) == ("UVI=", "auto", None)
    assert done.login is not None
    assert done.login.credentials.access_token == token
    assert done.login.credentials.refresh_token == "cookie-refresh"  # the cookie wins over the body
    assert done.login.user is not None
    assert done.login.user.display_name == "Ada Lovelace"
    assert done.login.user.customer_code == "128"


def test_email_login(client: UmeaEnergiClient, fake: FakeApi) -> None:
    token = make_jwt(2_000_000_000)
    fake.add("POST", f"{SESSION}/emailStep1", httpx.Response(200))
    fake.add("POST", f"{SESSION}/emailStep2", httpx.Response(200, json=production_session(token)))

    run(client.start_email_login("ada@example.com", "pw"))
    login = run(client.complete_email_login("ada@example.com", " 123 "))

    assert json.loads(fake.requests_to(f"{SESSION}/emailStep2")[0].content) == {
        "username": "ada@example.com",
        "activationKey": "123",
        "type": 0,
    }
    assert login.credentials.access_token == token
    assert login.credentials.refresh_token == "body-refresh"  # no cookie: taken from the body
    assert login.credentials.refresh_token_expires_at == datetime(2026, 12, 31, 23, tzinfo=UTC)


def test_email_login_with_wrong_password(client: UmeaEnergiClient, fake: FakeApi) -> None:
    fake.add("POST", f"{SESSION}/emailStep1", httpx.Response(404))

    with pytest.raises(InvalidCredentialsError):
        run(client.start_email_login("ada@example.com", "wrong"))


def test_refresh_sends_the_cookie_and_returns_the_rotated_token(
    client: UmeaEnergiClient, fake: FakeApi
) -> None:
    token = make_jwt(2_000_000_000)
    fake.add(
        "POST",
        f"{SESSION}/refresh-token",
        httpx.Response(200, json={"token": {"access_token": token}}, headers=cookie("new")),
    )

    login = run(client.refresh("old"))

    assert fake.requests[0].headers["cookie"] == "refreshToken=old"
    assert login.credentials.access_token == token
    assert login.credentials.refresh_token == "new"


def test_refresh_keeps_the_refresh_token_when_not_rotated(
    client: UmeaEnergiClient, fake: FakeApi
) -> None:
    fake.add(
        "POST",
        f"{SESSION}/refresh-token",
        httpx.Response(200, json={"token": {"access_token": "a"}}),
    )

    assert run(client.refresh("old")).credentials.refresh_token == "old"


def test_fresh_credentials(client: UmeaEnergiClient, fake: FakeApi) -> None:
    fresh = Credentials(access_token=make_jwt(2_000_000_000), refresh_token="r")
    expired = Credentials(access_token=make_jwt(1), refresh_token="r")
    fake.add(
        "POST",
        f"{SESSION}/refresh-token",
        httpx.Response(200, json={"token": {"access_token": make_jwt(2_000_000_001)}}),
    )

    assert run(client.fresh_credentials(fresh)) is fresh
    assert run(client.fresh_credentials(expired)).access_token_expires_at == datetime.fromtimestamp(
        2_000_000_001, UTC
    )
    with pytest.raises(TokenExpiredError):
        run(client.fresh_credentials(Credentials(access_token=make_jwt(1))))


def test_revoke_sends_bearer_token_and_refresh_cookie(
    client: UmeaEnergiClient, fake: FakeApi
) -> None:
    fake.add("POST", f"{SESSION}/revoke-token", httpx.Response(200))

    run(client.revoke(Credentials(access_token="access", refresh_token="refresh")))

    [request] = fake.requests
    assert request.headers["authorization"] == "Bearer access"
    assert request.headers["cookie"] == "refreshToken=refresh"


def test_api_errors(client: UmeaEnergiClient, fake: FakeApi) -> None:
    fake.add("POST", f"{SESSION}/revoke-token", httpx.Response(401, json={"message": "Nope"}))

    with pytest.raises(ApiError) as error:
        run(client.revoke(Credentials(access_token="a", refresh_token="r")))

    assert (error.value.status_code, error.value.detail) == (401, "Nope")


def test_network_errors_become_api_errors() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    client = UmeaEnergiClient(httpx_args={"transport": httpx.MockTransport(fail)})

    with pytest.raises(ApiError) as error:
        run(client.start_bankid())

    assert error.value.status_code is None


def test_traffic_is_logged_at_debug_without_secrets(
    client: UmeaEnergiClient, fake: FakeApi, caplog: pytest.LogCaptureFixture
) -> None:
    token = make_jwt(2_000_000_000)
    fake.add("POST", f"{SESSION}/emailStep2", httpx.Response(200, json=production_session(token)))

    with caplog.at_level(logging.DEBUG, logger="umea_energi_api_client"):
        run(client.complete_email_login("ada@example.com", "424242"))

    assert "→ POST https://api.test/api/v1/Session/emailStep2" in caplog.text
    assert "← 200 POST /api/v1/Session/emailStep2" in caplog.text
    for secret in (token, "424242", "body-refresh"):
        assert secret not in caplog.text


def test_custom_event_hooks_are_kept(fake: FakeApi) -> None:
    seen: list[str] = []

    async def hook(request: httpx.Request) -> None:
        seen.append(request.url.path)

    client = UmeaEnergiClient(
        "https://api.test",
        httpx_args={"transport": fake.transport, "event_hooks": {"request": [hook]}},
    )
    fake.add("POST", f"{SESSION}/revoke-token", httpx.Response(200))

    run(client.revoke(Credentials(access_token="a", refresh_token="r")))

    assert seen == [f"{SESSION}/revoke-token"]


def test_jwt_expiry() -> None:
    assert jwt_expiry("e30.eyJleHAiOjB9.sig") == datetime(1970, 1, 1, tzinfo=UTC)
    assert jwt_expiry("not-a-jwt") is None
    assert jwt_expiry("e30.e30.sig") is None  # no exp claim


def test_requests_send_a_user_agent_with_the_library_version(fake: FakeApi) -> None:
    client = UmeaEnergiClient("https://api.test", httpx_args={"transport": fake.transport})
    fake.add("POST", f"{SESSION}/revoke-token", httpx.Response(200))

    run(client.revoke(Credentials(access_token="a", refresh_token="r")))

    assert fake.requests[0].headers["user-agent"] == (
        f"umea-energi-api-client/{__version__} (+https://github.com/klingenm/umea-energi-api-client)"
    )
    assert fake.requests[0].headers["user-agent"] == USER_AGENT


def test_headers_and_timeout_can_be_customized_without_leaking_tokens(fake: FakeApi) -> None:
    client = UmeaEnergiClient(
        "https://api.test",
        httpx_args={"transport": fake.transport, "headers": {"User-Agent": "mine"}, "timeout": 5},
    )
    fake.add("POST", f"{SESSION}/revoke-token", httpx.Response(200))
    fake.add("GET", "/api/v1/Disturbance", httpx.Response(200, json=[]))

    run(client.revoke(Credentials(access_token="secret", refresh_token="r")))
    run(_get_disturbances(client))

    revoke, public = fake.requests
    assert revoke.headers["user-agent"] == public.headers["user-agent"] == "mine"
    assert "authorization" not in public.headers  # the bearer token stays on its own client


async def _get_disturbances(api: UmeaEnergiClient) -> None:
    async with api.client() as client:
        await get_api_vversion_disturbance.asyncio_detailed(api.api_version, client=client)
