# umea-energi-api-client

Async-capable Python client for the Umeå Energi API, generated from its
[OpenAPI document](https://tapi.umeaenergi.se/swagger/v2/swagger.json).

## Usage

```python
from umea_energi_api_client import Client
from umea_energi_api_client.generated.api.electricity import (
    get_api_vversion_electricity_prices_net_area as get_prices,
)

async with Client(base_url="https://tapi.umeaenergi.se") as client:
    prices = await get_prices.asyncio(version="2", net_area=2, client=client)
```

Every endpoint module also provides `sync`, `sync_detailed`, and `asyncio_detailed`.
Use `AuthenticatedClient(base_url=..., token=...)` for endpoints that need a bearer token.

## Development

Tool versions (Python, uv, ruff, openapi-python-client) are pinned in `mise.toml`.

```sh
mise install         # install pinned tools
mise run sync        # create .venv and install dependencies
mise run generate    # generate the API client (gitignored; needed before imports work)
mise run check       # lint, typecheck, test
mise run fetch-spec  # update openapi/swagger.json from the API
```

Run `mise tasks` to list all available tasks.
