import base64
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from umea_energi_api_client.testing import FakeApi
from umea_energi_playground.app import create_app
from umea_energi_playground.config import Settings


@pytest.fixture
def fake_api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'playground.db'}",
        api_base_url="https://api.test",
        api_version="2",
    )


@pytest.fixture
def client(settings: Settings, fake_api: FakeApi) -> Iterator[TestClient]:
    app = create_app(settings, transport=fake_api.transport)
    with TestClient(app, follow_redirects=False) as client:
        yield client


@pytest.fixture
def make_jwt() -> Callable[[int], str]:
    def make(exp: int) -> str:
        def encode(data: dict[str, object]) -> str:
            return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

        return f"{encode({'alg': 'none'})}.{encode({'exp': exp})}.signature"

    return make


@pytest.fixture
def login_session() -> Callable[[str], dict[str, object]]:
    """Body of a completed login, as returned by the BankID poll and email step 2."""

    def make(token: str) -> dict[str, object]:
        return {
            "id": "ref123",
            "completed": True,
            "token": {"accessJwtToken": token},
            "user": {
                "id": 7,
                "firstName": "Ada",
                "lastName": "Lovelace",
                "email": "ada@example.com",
                "defaultCustomerCode": "12345",
            },
        }

    return make
