from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from umea_energi_api_client.testing import FakeApi
from umea_energi_playground.consumption import chart_rows

CONTRACTS = {
    "groupedContracts": [
        {
            "group": "Street 1",
            "contracts": [
                {"customerId": "12345", "contractType": "ELECTRICITY_GRID", "meterPoint": "735"},
                {"customerId": "12345", "contractType": "DISTRICT_HEATING", "meterPoint": "900"},
            ],
        }
    ]
}


def login(
    client: TestClient, fake_api: FakeApi, token: str, session: Callable[[str], dict[str, object]]
) -> int:
    fake_api.add("POST", "/api/v2/Session/emailStep1", httpx.Response(200))
    fake_api.add("POST", "/api/v2/Session/emailStep2", httpx.Response(200, json=session(token)))
    client.post("/login/email", data={"username": "ada@example.com", "password": "pw"})
    response = client.post("/login/email/verify", data={"username": "ada@example.com", "code": "1"})
    return int(response.headers["location"].rsplit("/", 1)[1])


def test_consumption_page_lists_meter_points_and_shows_consumption(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, make_jwt(2_000_000_000), login_session)
    fake_api.add("GET", "/api/v2/Contracts/12345", httpx.Response(200, json=CONTRACTS))
    path = "/api/v2/Customer/12345/electricityConsumption/ELECTRICITY_GRID"
    fake_api.add(
        "GET",
        path,
        httpx.Response(
            200,
            json={
                "consumption": [
                    {"period": "2026-10-01", "value": 4},
                    {"period": "2026-10-02", "value": 8},
                ]
            },
        ),
    )

    page = client.get(f"/tokens/{token_id}/consumption")
    assert "ELECTRICITY_GRID · 735" in page.text
    assert "DISTRICT_HEATING · 900" in page.text

    result = client.get(
        f"/tokens/{token_id}/consumption",
        params={"meter_point": "ELECTRICITY_GRID:735", "start": "2026-10-01", "end": "2026-10-02"},
    )

    assert result.status_code == 200
    assert "8.00" in result.text  # charted row
    assert "&#34;period&#34;: &#34;2026-10-02&#34;" in result.text  # raw response
    params = fake_api.requests_to(path)[0].url.params
    assert (params["MeterPointNo"], params["From"], params["Resolution"]) == (
        "735",
        "2026-10-01T00:00:00",
        "DAY",
    )


def test_consumption_page_shows_cost(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, make_jwt(2_000_000_000), login_session)
    fake_api.add("GET", "/api/v2/Contracts/12345", httpx.Response(200, json=CONTRACTS))
    fake_api.add(
        "GET",
        "/api/v2/Customer/12345/consumptionCost/ELECTRICITY",
        httpx.Response(200, json=[{"period": "2026-10", "costIncl": 312.5}]),
    )

    result = client.get(
        f"/tokens/{token_id}/consumption",
        params={"meter_point": "ELECTRICITY_GRID:735", "kind": "cost", "resolution": "MONTH"},
    )

    assert result.status_code == 200
    assert "312.50" in result.text


def test_consumption_page_reports_api_errors(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, make_jwt(2_000_000_000), login_session)
    fake_api.add("GET", "/api/v2/Contracts/12345", httpx.Response(500, json={"message": "Down"}))

    result = client.get(f"/tokens/{token_id}/consumption")

    assert result.status_code == 502
    assert "HTTP 500: Down" in result.text


def test_chart_rows() -> None:
    rows = chart_rows({"consumption": [{"period": "a", "value": 2}, {"period": "b", "value": 4}]})

    assert [(row.period, row.value, row.share) for row in rows] == [
        ("a", 2.0, 0.5),
        ("b", 4.0, 1.0),
    ]
    assert chart_rows([{"period": "2026-10", "costIncl": 1.5}])[0].value == 1.5
    assert chart_rows("not json") == []


def test_consumption_page_shows_meter_readings(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, make_jwt(2_000_000_000), login_session)
    fake_api.add("GET", "/api/v2/Contracts/12345", httpx.Response(200, json=CONTRACTS))
    fake_api.add(
        "GET",
        "/api/v2/Customer/12345/delsiteMeterReadings",
        httpx.Response(
            200,
            json={
                "values": [{"timeStamp": "2026-10-01T00:00:00", "reason": "READ", "value": 4321.5}]
            },
        ),
    )

    result = client.get(
        f"/tokens/{token_id}/consumption",
        params={"meter_point": "ELECTRICITY_GRID:735", "kind": "readings"},
    )

    assert result.status_code == 200
    assert "<h2>Meter readings</h2>" in result.text
    assert "2026-10-01T00:00:00" in result.text
    assert "4321.50" in result.text


def test_consumption_page_shows_max_consumption_and_statistics(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, make_jwt(2_000_000_000), login_session)
    fake_api.add("GET", "/api/v2/Contracts/12345", httpx.Response(200, json=CONTRACTS))
    fake_api.add("GET", "/api/v2/Customer/12345/maxConsumption", httpx.Response(200, json=[]))
    fake_api.add("GET", "/api/v2/Customer/12345/meterStatistics", httpx.Response(200, json={}))
    page = f"/tokens/{token_id}/consumption"

    assert (
        client.get(page, params={"meter_point": "DISTRICT_HEATING:900", "kind": "max"}).status_code
        == 200
    )
    statistics = client.get(
        page,
        params={"meter_point": "DISTRICT_HEATING:900", "kind": "statistics", "variables": "FVTQW"},
    )

    assert statistics.status_code == 200
    assert (
        fake_api.requests_to("/api/v2/Customer/12345/maxConsumption")[0].url.params[
            "DeliverySiteCode"
        ]
        == "900"
    )
    assert (
        fake_api.requests_to("/api/v2/Customer/12345/meterStatistics")[0].url.params[
            "SpecifiedVariables"
        ]
        == "FVTQW"
    )


def test_empty_max_consumption_explains_it_is_for_companies(
    client: TestClient,
    fake_api: FakeApi,
    make_jwt: Callable[[int], str],
    login_session: Callable[[str], dict[str, object]],
) -> None:
    token_id = login(client, fake_api, make_jwt(2_000_000_000), login_session)
    fake_api.add("GET", "/api/v2/Contracts/12345", httpx.Response(200, json=CONTRACTS))
    fake_api.add("GET", "/api/v2/Customer/12345/maxConsumption", httpx.Response(200, json=[]))

    result = client.get(
        f"/tokens/{token_id}/consumption",
        params={"meter_point": "DISTRICT_HEATING:900", "kind": "max"},
    )

    assert "The API returned no data" in result.text
    assert "only provides max effect readings for company customers" in result.text
