import json
from collections.abc import Callable

import httpx
from fake_api import FakeApi
from fastapi.testclient import TestClient

BANKID_START = "/api/v2/Session/bankid"
BANKID_POLL = "/api/v2/Session/bankid/ref123/0"
BANKID_CANCEL = "/api/v2/Session/ref123/0"
EMAIL_STEP_1 = "/api/v2/Session/emailStep1"
EMAIL_STEP_2 = "/api/v2/Session/emailStep2"


def bankid_pending(qr_code: str) -> dict[str, object]:
    return {"id": "ref123", "autoStartToken": "auto", "completed": False, "qrCode": qr_code}


def test_bankid_login_stores_token(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token = make_jwt(2_000_000_000)
    # The start response says "completed": the order was created, not that the user logged in.
    fake_api.add("POST", BANKID_START, httpx.Response(200, json=bankid_pending("UVIx")))
    fake_api.add(
        "GET",
        BANKID_POLL,
        httpx.Response(200, json=bankid_pending("UVIy")),
        httpx.Response(200, json=login_session(token)),
    )

    started = client.post("/login/bankid", data={"state": "0"})
    assert started.status_code == 303
    assert started.headers["location"].endswith("/login/bankid/ref123?state=0")
    assert json.loads(fake_api.requests_to(BANKID_START)[0].content) == {"type": 0}
    assert client.get(started.headers["location"]).status_code == 200

    pending = client.get("/login/bankid/ref123/status", params={"state": 0})
    assert pending.json() == {"status": "pending", "qr_code": "UVIy", "auto_start_token": "auto"}

    completed = client.get("/login/bankid/ref123/status", params={"state": 0}).json()
    assert completed["status"] == "complete"

    page = client.get(completed["redirect"])
    assert page.status_code == 200
    assert "Ada Lovelace" in page.text
    assert "12345" in page.text
    assert "2033-05-18 03:33 UTC" in page.text  # read from the JWT's exp claim
    assert "Ada Lovelace" in client.get("/").text


def test_bankid_poll_failure_is_reported(client: TestClient, fake_api: FakeApi) -> None:
    fake_api.add("GET", BANKID_POLL, httpx.Response(400, json={"message": "Order expired"}))

    response = client.get("/login/bankid/ref123/status", params={"state": 0})

    assert response.status_code == 502
    assert response.json() == {"status": "failed", "error": "HTTP 400: Order expired"}


def test_bankid_cancel(client: TestClient, fake_api: FakeApi) -> None:
    fake_api.add("DELETE", BANKID_CANCEL, httpx.Response(200, json={"completed": True}))

    response = client.post("/login/bankid/ref123/cancel", data={"state": "0"})

    assert response.status_code == 303
    assert len(fake_api.requests_to(BANKID_CANCEL)) == 1


def test_email_login_stores_token(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    fake_api.add("POST", EMAIL_STEP_1, httpx.Response(200))
    fake_api.add("POST", EMAIL_STEP_2, httpx.Response(200, json=login_session(make_jwt(1))))

    step_1 = client.post(
        "/login/email", data={"username": "ada@example.com", "password": "pw", "state": "0"}
    )
    assert step_1.status_code == 200
    assert 'name="code"' in step_1.text
    assert json.loads(fake_api.requests_to(EMAIL_STEP_1)[0].content) == {
        "username": "ada@example.com",
        "password": "pw",
        "type": 0,
    }

    step_2 = client.post(
        "/login/email/verify",
        data={"username": "ada@example.com", "code": " 123456 ", "state": "0"},
    )
    assert step_2.status_code == 303
    assert json.loads(fake_api.requests_to(EMAIL_STEP_2)[0].content) == {
        "username": "ada@example.com",
        "activationKey": "123456",
        "type": 0,
    }
    page = client.get(step_2.headers["location"])
    assert "Ada Lovelace" in page.text
    assert "expired" in page.text  # exp=1 is in 1970


def test_email_login_shows_api_error(client: TestClient, fake_api: FakeApi) -> None:
    fake_api.add("POST", EMAIL_STEP_1, httpx.Response(401, json={"message": "Wrong password"}))

    response = client.post(
        "/login/email", data={"username": "ada@example.com", "password": "nope", "state": "0"}
    )

    assert response.status_code == 400
    assert "Wrong password" in response.text
    assert 'name="code"' not in response.text


def test_email_code_without_token_is_an_error(client: TestClient, fake_api: FakeApi) -> None:
    fake_api.add("POST", EMAIL_STEP_2, httpx.Response(200, json={"completed": False}))

    response = client.post(
        "/login/email/verify", data={"username": "ada@example.com", "code": "1", "state": "0"}
    )

    assert response.status_code == 400
    assert "did not return an access token" in response.text
