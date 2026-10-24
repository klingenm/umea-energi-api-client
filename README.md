# umea-energi-api-client

Unofficial, async-capable Python client for the Umeå Energi API, generated from its
[OpenAPI document](https://tapi.umeaenergi.se/swagger/v2/swagger.json).
See the [API documentation](https://tapi.umeaenergi.se/) for endpoint details.

> **Disclaimer:** This is an independent project. The author has no affiliation with
> Umeå Energi, which neither endorses nor supports this library. The library is in alpha:
> its API may change between releases.

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
mise run change      # describe a change for the next release
```

### Releasing

Changes are tracked with [knope](https://knope.tech) change files in `.changeset/`.
`mise run release` bumps the version, updates the changelog, pushes, and creates a GitHub
release, which publishes the package to PyPI.

Run `mise tasks` to list all available tasks.

## License

[MIT](https://github.com/klingenm/umea-energi-api-client/blob/main/LICENSE). Provided "as is", without warranty of any kind.
