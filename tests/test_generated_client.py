import asyncio
import datetime

import httpx

from umea_energi_api_client import Client
from umea_energi_api_client.generated.api.temperature import get_api_vversion_temperature
from umea_energi_api_client.generated.models import (
    UmeaEnergiApiModelsTemperatureResponse,
    UmeaEnergiApiMuleResponseTypesElectricityPricesAreaResponse,
)


def test_async_endpoint_call_parses_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"timeStamp": "2026-10-24T12:00:00+00:00", "value": 4.5})

    base_url = "https://tapi.umeaenergi.se"
    client = Client(base_url=base_url).set_async_httpx_client(
        httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(handler))
    )

    result = asyncio.run(get_api_vversion_temperature.asyncio(version="2", client=client))

    assert isinstance(result, UmeaEnergiApiModelsTemperatureResponse)
    assert result.value == 4.5
    assert result.time_stamp == datetime.datetime(2026, 10, 24, 12, tzinfo=datetime.UTC)
    assert requests[0].url.path == "/api/v2/Temperature"


def test_null_reference_property_is_accepted() -> None:
    # The upstream spec omits `nullable` on $ref properties; scripts/normalize_openapi.py adds it.
    parsed = UmeaEnergiApiMuleResponseTypesElectricityPricesAreaResponse.from_dict(
        {"error": None, "netArea": 2, "contracts": []}
    )

    assert parsed.error is None
    assert parsed.net_area == 2
