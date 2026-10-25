import asyncio
from collections.abc import Awaitable
from datetime import date

import httpx
import pytest

from umea_energi_api_client import ApiError, MeterPoint, Resolution, UmeaEnergiClient
from umea_energi_api_client.testing import FakeApi

CONTRACTS = {
    "pager": {"pageNumber": 1},
    "groupedContracts": [
        {
            "group": "Street 1",
            "contracts": [
                {
                    "customerId": "128",
                    "contractType": "ELECTRICITY_GRID",
                    "meterPoint": "735",
                    "address": "Street 1",
                },
                # No meter point of its own: the grid contract's at the same address is used.
                {
                    "customerId": "128",
                    "contractType": "ELECTRICITY",
                    "meterPoint": None,
                    "address": "Street 1",
                },
                {
                    "customerId": "128",
                    "contractType": "DISTRICT_HEATING",
                    "meterPoint": "900",
                    "address": "Street 1",
                },
                {
                    "customerId": "128",
                    "contractType": "BROADBAND",
                    "meterPoint": None,
                    "address": "Street 1",
                },
            ],
        },
        {"group": "Empty", "contracts": []},
    ],
}


def run[T](awaitable: Awaitable[T]) -> T:
    async def wrap() -> T:
        return await awaitable

    return asyncio.run(wrap())


def meter_point(contract_type: str, number: str = "735") -> MeterPoint:
    return MeterPoint(
        contract_type=contract_type,
        meter_point_no=number,
        customer_code="128",
        address=None,
        contract_id=None,
    )


@pytest.fixture
def fake() -> FakeApi:
    return FakeApi()


@pytest.fixture
def api(fake: FakeApi) -> UmeaEnergiClient:
    return UmeaEnergiClient("https://api.test", httpx_args={"transport": fake.transport})


def test_meter_points_come_from_grouped_contracts(api: UmeaEnergiClient, fake: FakeApi) -> None:
    fake.add("GET", "/api/v1/Contracts/128", httpx.Response(200, json=CONTRACTS))

    points = run(api.meter_points("token", "128"))

    assert [(p.contract_type, p.meter_point_no) for p in points] == [
        ("ELECTRICITY_GRID", "735"),
        ("ELECTRICITY", "735"),
        ("DISTRICT_HEATING", "900"),
    ]
    [request] = fake.requests
    assert request.headers["authorization"] == "Bearer token"
    assert (
        request.url.params["MaxContracts"] == "5000"
    )  # ASP.NET binds query names case-insensitively


@pytest.mark.parametrize(
    ("contract_type", "path"),
    [
        ("ELECTRICITY_GRID", "/api/v1/Customer/128/electricityConsumption/ELECTRICITY_GRID"),
        ("ELECTRICITY", "/api/v1/Customer/128/electricityConsumption/ELECTRICITY"),
        ("DISTRICT_HEATING", "/api/v1/Customer/128/heatingConsumption"),
        ("DISTRICT_COOLING", "/api/v1/Customer/128/consumption"),
    ],
)
def test_consumption_uses_the_endpoint_for_the_contract_type(
    api: UmeaEnergiClient, fake: FakeApi, contract_type: str, path: str
) -> None:
    fake.add(
        "GET",
        path,
        httpx.Response(200, json={"consumption": [{"period": "2026-10-01", "value": 1.5}]}),
    )

    result = run(
        api.consumption(
            "token",
            meter_point(contract_type),
            date(2026, 10, 1),
            date(2026, 10, 31),
            Resolution.DAY,
        )
    )

    assert result == {"consumption": [{"period": "2026-10-01", "value": 1.5}]}
    params = fake.requests_to(path)[0].url.params
    assert dict(params) == {
        "MeterPointNo": "735",
        "From": "2026-10-01T00:00:00",
        "To": "2026-10-31T00:00:00",
        "Resolution": "DAY",
    }


def test_cost_of_grid_contracts_is_asked_for_as_electricity(
    api: UmeaEnergiClient, fake: FakeApi
) -> None:
    path = "/api/v1/Customer/128/consumptionCost/ELECTRICITY"
    fake.add("GET", path, httpx.Response(200, json=[{"period": "2026-10", "costIncl": 312.5}]))

    result = run(
        api.consumption_cost(
            "token", meter_point("ELECTRICITY_GRID"), date(2026, 1, 1), date(2026, 10, 31)
        )
    )

    assert result == [{"period": "2026-10", "costIncl": 312.5}]
    assert fake.requests_to(path)[0].url.params["Resolution"] == "MONTH"


def test_consumption_errors_raise(api: UmeaEnergiClient, fake: FakeApi) -> None:
    fake.add(
        "GET",
        "/api/v1/Customer/128/heatingConsumption",
        httpx.Response(400, json={"message": "Bad dates"}),
    )

    with pytest.raises(ApiError, match="Bad dates"):
        run(
            api.consumption(
                "token", meter_point("DISTRICT_HEATING"), date(2026, 10, 2), date(2026, 10, 1)
            )
        )


def test_grid_meter_readings_use_delsite_readings(api: UmeaEnergiClient, fake: FakeApi) -> None:
    path = "/api/v1/Customer/128/delsiteMeterReadings"
    readings = {
        "values": [{"timeStamp": "2026-10-01T00:00:00", "reason": "READ", "value": 12345.6}]
    }
    fake.add("GET", path, httpx.Response(200, json=readings))

    result = run(
        api.meter_readings(
            "token", meter_point("ELECTRICITY_GRID"), date(2026, 1, 1), date(2026, 10, 31)
        )
    )

    assert result == readings
    params = fake.requests_to(path)[0].url.params
    assert (params["DeliverySiteCode"], params["ContractCategory"]) == ("735", "ELECTRICITY_GRID")


def test_other_meter_readings_include_estimated_status(
    api: UmeaEnergiClient, fake: FakeApi
) -> None:
    path = "/api/v1/Customer/128/meterReadings"
    fake.add("GET", path, httpx.Response(200, json=[]))

    run(
        api.meter_readings(
            "token", meter_point("DISTRICT_HEATING", "900"), date(2026, 1, 1), date(2026, 10, 31)
        )
    )

    params = fake.requests_to(path)[0].url.params
    assert (params["ContractType"], params["DeliverySiteCode"]) == ("DISTRICT_HEATING", "900")
    assert params["ShowEstimatedValuesStatus"] == "true"


def test_meter_statistics(api: UmeaEnergiClient, fake: FakeApi) -> None:
    fake.add("GET", "/api/v1/Customer/128/meterStatistics", httpx.Response(200, json={}))
    fake.add(
        "GET", "/api/v1/Customer/128/statisticsWithEstimatedValues", httpx.Response(200, json=[])
    )
    point = meter_point("DISTRICT_HEATING", "900")

    run(api.meter_statistics("token", point, date(2025, 10, 1), date(2026, 10, 1), "FVTQW"))
    run(
        api.statistics_with_estimated_values(
            "token", point, date(2026, 10, 1), date(2026, 10, 2), Resolution.HOUR
        )
    )

    statistics, estimated = fake.requests
    assert statistics.url.params["SpecifiedVariables"] == "FVTQW"
    assert (estimated.url.params["DeliverySiteCode"], estimated.url.params["Resolution"]) == (
        "900",
        "HOUR",
    )


def test_max_consumption_sends_both_date_parameter_names(
    api: UmeaEnergiClient, fake: FakeApi
) -> None:
    fake.add("GET", "/api/v1/Customer/128/maxConsumption", httpx.Response(200, json=[]))

    run(
        api.max_consumption(
            "token", meter_point("DISTRICT_HEATING", "900"), date(2026, 1, 1), date(2026, 10, 31)
        )
    )

    params = fake.requests[0].url.params
    assert (params["FromDate"], params["ToDate"]) == ("2026-01-01T00:00:00", "2026-10-31T00:00:00")
    assert (params["from"], params["to"]) == ("2026-01-01", "2026-10-31")
