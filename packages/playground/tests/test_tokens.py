from collections.abc import Callable
from pathlib import Path

import httpx
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from umea_energi_api_client.testing import FakeApi
from umea_energi_playground.db import Base, upgrade_database


def login(
    client: TestClient,
    fake_api: FakeApi,
    token: str,
    login_session: Callable[[str], dict[str, object]],
) -> str:
    """Log in with email and return the stored token's page URL."""
    fake_api.add("POST", "/api/v2/Session/emailStep1", httpx.Response(200))
    fake_api.add(
        "POST", "/api/v2/Session/emailStep2", httpx.Response(200, json=login_session(token))
    )
    client.post("/login/email", data={"username": "ada@example.com", "password": "pw"})
    response = client.post("/login/email/verify", data={"username": "ada@example.com", "code": "1"})
    return response.headers["location"]


def test_example_runs_with_stored_token(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token = make_jwt(2_000_000_000)
    login(client, fake_api, token, login_session)
    fake_api.add("GET", "/api/v2/Customer/12345", httpx.Response(200, json={"code": "12345"}))

    response = client.get("/examples/customer", params={"token_id": 1})

    assert response.status_code == 200
    assert "HTTP <strong>200</strong>" in response.text
    assert "&#34;code&#34;: &#34;12345&#34;" in response.text
    [request] = fake_api.requests_to("/api/v2/Customer/12345")
    assert request.headers["Authorization"] == f"Bearer {token}"


def test_public_example_runs_without_login(client: TestClient, fake_api: FakeApi) -> None:
    fake_api.add("GET", "/api/v2/Disturbance", httpx.Response(200, json=[]))

    response = client.get("/examples/disturbances")

    assert response.status_code == 200
    assert "Authorization" not in fake_api.requests_to("/api/v2/Disturbance")[0].headers


def test_login_only_example_needs_a_token(client: TestClient) -> None:
    response = client.get("/examples/customer")

    assert response.status_code == 400
    assert "Log in to run this example." in response.text


def test_delete_token(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    page = login(client, fake_api, make_jwt(1), login_session)

    assert client.post("/tokens/1/logout").status_code == 303
    assert client.get(page).status_code == 404


def test_migrations_match_models(tmp_path: Path) -> None:
    database = tmp_path / "migrated.db"
    upgrade_database(f"sqlite+aiosqlite:///{database}")

    with create_engine(f"sqlite:///{database}").connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert diff == []
