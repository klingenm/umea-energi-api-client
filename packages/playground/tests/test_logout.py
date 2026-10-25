from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from umea_energi_api_client.testing import FakeApi

EMAIL_STEP_1 = "/api/v2/Session/emailStep1"
EMAIL_STEP_2 = "/api/v2/Session/emailStep2"
REFRESH = "/api/v2/Session/refresh-token"
REVOKE = "/api/v2/Session/revoke-token"
FUTURE = 2_000_000_000


def login(
    client: TestClient,
    fake_api: FakeApi,
    login_session: Callable[[str], dict[str, object]],
    token: str,
    refresh_token: str | None = "refresh-1",
) -> int:
    headers = {"set-cookie": f"refreshToken={refresh_token}; path=/"} if refresh_token else None
    fake_api.add("POST", EMAIL_STEP_1, httpx.Response(200))
    fake_api.add(
        "POST", EMAIL_STEP_2, httpx.Response(200, json=login_session(token), headers=headers)
    )
    client.post("/login/email", data={"username": "ada@example.com", "password": "pw"})
    response = client.post("/login/email/verify", data={"username": "ada@example.com", "code": "1"})
    return int(response.headers["location"].rsplit("/", 1)[1])


def test_logout_revokes_the_refresh_token_and_forgets_the_token(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token = make_jwt(FUTURE)
    token_id = login(client, fake_api, login_session, token)
    fake_api.add("POST", REVOKE, httpx.Response(200))

    response = client.post(f"/tokens/{token_id}/logout")

    assert response.status_code == 303
    [revoke] = fake_api.requests_to(REVOKE)
    assert revoke.headers["authorization"] == f"Bearer {token}"
    assert revoke.headers["cookie"] == "refreshToken=refresh-1"
    assert client.get(f"/tokens/{token_id}").status_code == 404


def test_logout_refreshes_an_expired_token_before_revoking(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, login_session, make_jwt(1), "refresh-1")
    new_token = make_jwt(FUTURE)
    fake_api.add(
        "POST",
        REFRESH,
        httpx.Response(
            200,
            json={"token": {"access_token": new_token}},
            headers={"set-cookie": "refreshToken=refresh-2; path=/"},
        ),
    )
    fake_api.add("POST", REVOKE, httpx.Response(200))

    assert client.post(f"/tokens/{token_id}/logout").status_code == 303

    [revoke] = fake_api.requests_to(REVOKE)
    assert revoke.headers["authorization"] == f"Bearer {new_token}"
    assert revoke.headers["cookie"] == "refreshToken=refresh-2"


def test_failed_revoke_keeps_the_token_until_forgotten(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, login_session, make_jwt(FUTURE))
    fake_api.add("POST", REVOKE, httpx.Response(500, json={"message": "Boom"}))

    response = client.post(f"/tokens/{token_id}/logout")

    assert response.status_code == 502
    assert "Revoking the refresh token failed (HTTP 500: Boom)." in response.text
    assert client.get(f"/tokens/{token_id}").status_code == 200

    assert client.post(f"/tokens/{token_id}/delete").status_code == 303
    assert client.get(f"/tokens/{token_id}").status_code == 404


def test_logout_without_refresh_token_just_forgets_the_token(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, login_session, make_jwt(FUTURE), refresh_token=None)

    assert client.post(f"/tokens/{token_id}/logout").status_code == 303

    assert not fake_api.requests_to(REVOKE)
    assert client.get(f"/tokens/{token_id}").status_code == 404
