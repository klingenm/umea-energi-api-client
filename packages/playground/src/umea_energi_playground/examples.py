"""Sample API calls the playground can run, with or without a stored login."""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from umea_energi_api_client import AuthenticatedClient, Client
from umea_energi_api_client.generated.api.contracts import (
    get_api_vversion_contracts_customer_code as contracts,
)
from umea_energi_api_client.generated.api.customer import (
    get_api_vversion_customer_customer_code as customer,
)
from umea_energi_api_client.generated.api.disturbance import (
    get_api_vversion_disturbance as disturbances,
)
from umea_energi_api_client.generated.api.electricity import (
    get_api_vversion_electricity_prices_net_area as electricity_prices,
)
from umea_energi_api_client.generated.api.electricity import (
    get_api_vversion_electricity_spotprices_net_area_nordpool as spot_prices,
)
from umea_energi_api_client.generated.api.invoices import (
    get_api_vversion_invoices_customer_code as invoices,
)
from umea_energi_api_client.generated.api.session import get_api_vversion_session_ping as ping
from umea_energi_api_client.generated.types import Response

# Umeå is in electricity area SE2.
NET_AREA = 2


class ExampleUnavailable(Exception):
    """The example can't run with the current login."""


@dataclass(frozen=True)
class ExampleContext:
    version: str
    client: Client | AuthenticatedClient
    customer_code: str | None = None

    def authenticated_client(self) -> AuthenticatedClient:
        if not isinstance(self.client, AuthenticatedClient):
            raise ExampleUnavailable("Log in to run this example.")
        return self.client

    def require_customer_code(self) -> str:
        if not self.customer_code:
            raise ExampleUnavailable("The logged-in user has no customer code.")
        return self.customer_code


@dataclass(frozen=True)
class Example:
    slug: str
    title: str
    description: str
    requires_login: bool
    call: Callable[[ExampleContext], Awaitable[Response[Any]]]


async def _electricity_prices(ctx: ExampleContext) -> Response[Any]:
    return await electricity_prices.asyncio_detailed(ctx.version, NET_AREA, client=ctx.client)


async def _spot_prices(ctx: ExampleContext) -> Response[Any]:
    return await spot_prices.asyncio_detailed(ctx.version, NET_AREA, client=ctx.client)


async def _disturbances(ctx: ExampleContext) -> Response[Any]:
    return await disturbances.asyncio_detailed(ctx.version, client=ctx.client)


async def _ping(ctx: ExampleContext) -> Response[Any]:
    return await ping.asyncio_detailed(ctx.version, client=ctx.authenticated_client())


async def _customer(ctx: ExampleContext) -> Response[Any]:
    client = ctx.authenticated_client()
    return await customer.asyncio_detailed(ctx.version, ctx.require_customer_code(), client=client)


async def _contracts(ctx: ExampleContext) -> Response[Any]:
    client = ctx.authenticated_client()
    return await contracts.asyncio_detailed(ctx.version, ctx.require_customer_code(), client=client)


async def _invoices(ctx: ExampleContext) -> Response[Any]:
    client = ctx.authenticated_client()
    customer_code = ctx.require_customer_code()
    if not customer_code.isdigit():
        raise ExampleUnavailable("The invoices endpoint needs a numeric customer code.")
    return await invoices.asyncio_detailed(ctx.version, int(customer_code), client=client)


EXAMPLES: dict[str, Example] = {
    example.slug: example
    for example in [
        Example(
            "electricity-prices",
            "Electricity prices",
            "Contract prices for net area SE2 (GET /Electricity/prices/{netArea}).",
            requires_login=False,
            call=_electricity_prices,
        ),
        Example(
            "spot-prices",
            "Spot prices",
            "Nord Pool spot prices for SE2 (GET /Electricity/spotprices/{netArea}/nordpool).",
            requires_login=False,
            call=_spot_prices,
        ),
        Example(
            "disturbances",
            "Disturbances",
            "Current outages and disturbances (GET /Disturbance).",
            requires_login=False,
            call=_disturbances,
        ),
        Example(
            "session-ping",
            "Check token",
            "Whether the token is still accepted (GET /Session/ping).",
            requires_login=True,
            call=_ping,
        ),
        Example(
            "customer",
            "Customer",
            "The logged-in customer (GET /Customer/{customerCode}).",
            requires_login=True,
            call=_customer,
        ),
        Example(
            "contracts",
            "Contracts",
            "The customer's contracts (GET /Contracts/{customerCode}).",
            requires_login=True,
            call=_contracts,
        ),
        Example(
            "invoices",
            "Invoices",
            "The customer's invoices (GET /Invoices/{customerCode}).",
            requires_login=True,
            call=_invoices,
        ),
    ]
}


def format_body(content: bytes) -> str:
    """Pretty-print a JSON response body, falling back to the raw text."""
    try:
        return json.dumps(json.loads(content), indent=2, ensure_ascii=False)
    except ValueError:
        return content.decode(errors="replace")
