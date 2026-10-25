from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from umea_energi_api_client.testing import FakeApi

EMAIL_STEP_1 = "/api/v2/Session/emailStep1"
EMAIL_STEP_2 = "/api/v2/Session/emailStep2"
REFRESH = "/api/v2/Session/refresh-token"
CUSTOMER = "/api/v2/Customer/12345"
FUTURE = 2_000_000_000


def refresh_cookie(value: str) -> dict[str, str]:
    return {"set-cookie": f"refreshToken={value}; path=/; secure; httponly"}


def login(
    client: TestClient,
    fake_api: FakeApi,
    login_session: Callable[[str], dict[str, object]],
    token: str,
    refresh_token: str = "refresh-1",
) -> int:
    """Log in with email, the API setting a refresh token cookie; return the stored token's id."""
    fake_api.add("POST", EMAIL_STEP_1, httpx.Response(200))
    fake_api.add(
        "POST",
        EMAIL_STEP_2,
        httpx.Response(200, json=login_session(token), headers=refresh_cookie(refresh_token)),
    )
    client.post("/login/email", data={"username": "ada@example.com", "password": "pw"})
    response = client.post("/login/email/verify", data={"username": "ada@example.com", "code": "1"})
    return int(response.headers["location"].rsplit("/", 1)[1])


def refreshed(token: str, refresh_token: str | None = None) -> httpx.Response:
    headers = refresh_cookie(refresh_token) if refresh_token else None
    return httpx.Response(200, json={"token": {"access_token": token}}, headers=headers)


def test_login_stores_refresh_token_from_cookie(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, login_session, make_jwt(FUTURE))

    page = client.get(f"/tokens/{token_id}")

    assert "Refresh now" in page.text


def test_expired_token_is_refreshed_before_calling_the_api(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, login_session, make_jwt(1), "refresh-1")
    new_token = make_jwt(FUTURE)
    fake_api.add("POST", REFRESH, refreshed(new_token, "refresh-2"), refreshed(make_jwt(FUTURE)))
    fake_api.add("GET", CUSTOMER, httpx.Response(200, json={"code": "12345"}))

    response = client.get("/examples/customer", params={"token_id": token_id})

    assert "HTTP <strong>200</strong>" in response.text
    [refresh] = fake_api.requests_to(REFRESH)
    assert refresh.headers["cookie"] == "refreshToken=refresh-1"
    [customer] = fake_api.requests_to(CUSTOMER)
    assert customer.headers["authorization"] == f"Bearer {new_token}"

    # The refresh rotated the refresh token, so the next refresh must use the new one.
    assert client.post(f"/tokens/{token_id}/refresh").status_code == 303
    assert fake_api.requests_to(REFRESH)[1].headers["cookie"] == "refreshToken=refresh-2"


def test_rejected_token_is_refreshed_and_the_call_retried(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, login_session, make_jwt(FUTURE))
    new_token = make_jwt(FUTURE + 1)
    fake_api.add("POST", REFRESH, refreshed(new_token))
    fake_api.add(
        "GET",
        CUSTOMER,
        httpx.Response(401),
        httpx.Response(200, json={"code": "12345"}),
    )

    response = client.get("/examples/customer", params={"token_id": token_id})

    assert "HTTP <strong>200</strong>" in response.text
    assert len(fake_api.requests_to(REFRESH)) == 1
    retried = fake_api.requests_to(CUSTOMER)[1]
    assert retried.headers["authorization"] == f"Bearer {new_token}"


def test_rejected_refresh_token_asks_to_log_in_again(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, login_session, make_jwt(1))
    fake_api.add("POST", REFRESH, httpx.Response(401))

    response = client.get("/examples/customer", params={"token_id": token_id})

    assert response.status_code == 401
    assert "Log in again" in response.text
    assert not fake_api.requests_to(CUSTOMER)
    # The rejected refresh token is dropped, so it isn't tried again.
    assert "Refresh now" not in client.get(f"/tokens/{token_id}").text
    assert len(fake_api.requests_to(REFRESH)) == 1
