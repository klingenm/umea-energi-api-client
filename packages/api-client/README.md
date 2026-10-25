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

This package lives in the [umea-energi-api-client](https://github.com/klingenm/umea-energi-api-client)
repository. See the repository README for how to build and test it.

## License

[MIT](https://github.com/klingenm/umea-energi-api-client/blob/main/LICENSE). Provided "as is", without warranty of any kind.
