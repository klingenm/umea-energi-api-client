# umea-energi-api-client

Unofficial, async-capable Python client for the Umeå Energi API, generated from its
[OpenAPI document](https://tapi.umeaenergi.se/swagger/v2/swagger.json).
See the [API documentation](https://tapi.umeaenergi.se/) for endpoint details.

> **Disclaimer:** This is an independent project. The author has no affiliation with
> Umeå Energi, which neither endorses nor supports this library. The library is in alpha:
> its API may change between releases.

## Usage

`UmeaEnergiClient` handles logging in and keeping tokens fresh, and knows the API's quirks
(see [Differences from the OpenAPI document](#differences-from-the-openapi-document)).
For everything else, call the generated endpoint functions with the clients it gives you.

### Public endpoints

```python
from umea_energi_api_client import UmeaEnergiClient
from umea_energi_api_client.generated.api.electricity import (
    get_api_vversion_electricity_prices_net_area as get_prices,
)

api = UmeaEnergiClient()  # production, API version 1
async with api.client() as client:
    prices = await get_prices.asyncio(api.api_version, net_area=2, client=client)
```

Every endpoint module provides `asyncio`, `asyncio_detailed`, `sync` and `sync_detailed`.

### Logging in

With email and password; the API then emails a one-time code:

```python
from umea_energi_api_client import CustomerType, InvalidCredentialsError

try:
    await api.start_email_login("you@example.com", password, CustomerType.PRIVATE)
except InvalidCredentialsError:
    ...  # wrong email or password
login = await api.complete_email_login("you@example.com", code_from_email)
```

With BankID: show the QR code (a base64-encoded SVG that changes every second) or open
`bankid:///?autostarttoken=<auto_start_token>&redirect=null`, and poll about once a second:

```python
progress = await api.start_bankid()
while (progress := await api.poll_bankid(progress.reference)).login is None:
    show_qr_code(progress.qr_code)
    await asyncio.sleep(1)
login = progress.login
```

A `Login` holds `credentials` (access token, refresh token and their expiry) and `user`
(name, email, and the `customer_code` the customer endpoints take).

### Calling endpoints that need a login

The access token is valid for about 10 minutes. `fresh_credentials` refreshes it when it is
about to expire; store what it returns, since a refresh may replace the refresh token.

```python
from umea_energi_api_client.generated.api.customer import (
    get_api_vversion_customer_customer_code as get_customer,
)

credentials = await api.fresh_credentials(login.credentials)
async with api.authenticated_client(credentials.access_token) as client:
    customer = await get_customer.asyncio(api.api_version, login.user.customer_code, client=client)
```

### Consumption

```python
from datetime import date
from umea_energi_api_client import Resolution

points = await api.meter_points(credentials.access_token, login.user.customer_code)
grid = next(p for p in points if p.contract_type == "ELECTRICITY_GRID")
usage = await api.consumption(
    credentials.access_token, grid, date(2026, 10, 1), date(2026, 10, 31), Resolution.DAY
)
cost = await api.consumption_cost(
    credentials.access_token, grid, date(2026, 1, 1), date(2026, 10, 31)
)
```

`consumption` picks the right endpoint for the contract type. Meter readings work the same way:

```python
readings = await api.meter_readings(
    credentials.access_token, grid, date(2026, 1, 1), date(2026, 10, 31)
)
```

There are also `statistics_with_estimated_values`, `meter_statistics` (per meter variable,
e.g. `FVTQW`) and `max_consumption` (district heating, company customers only). These methods return the API's JSON
as is, since these responses don't match the OpenAPI document closely enough for the
generated models.

### Logging out

```python
await api.revoke(await api.fresh_credentials(credentials))
```

This revokes the refresh token (valid for about a year) on the server. The access token keeps
working until it expires.

### Errors, logging and testing

- `ApiError` (with `status_code` and `detail`) for failed requests; `status_code` is `None` for
  network errors. `InvalidCredentialsError` and `TokenExpiredError` are more specific.
- Every request and response is logged at DEBUG on the `umea_energi_api_client` logger, with
  tokens, passwords and personal data redacted.
- Requests identify themselves with `User-Agent: umea-energi-api-client/<version>`; pass
  `httpx_args={"headers": {"User-Agent": ...}}` to change it.
- `umea_energi_api_client.testing.FakeApi` stands in for the API in your tests:

  ```python
  fake = FakeApi()
  fake.add("GET", "/api/v1/Disturbance", httpx.Response(200, json=[]))
  api = UmeaEnergiClient("https://api.test", httpx_args={"transport": fake.transport})
  ```

### Differences from the OpenAPI document

`UmeaEnergiClient` takes care of these; keep them in mind when calling generated code directly.

- `https://api.umeaenergi.se` is production. `https://tapi.umeaenergi.se`, where the document is
  published, is a test environment where real accounts and BankID don't work.
- Umeå Energi's own site uses API version 1 (`DEFAULT_API_VERSION`).
- Logins return the token as `token.access_token`; the document says `accessJwtToken`.
- The refresh token is set as a `refreshToken` cookie, which refresh and logout read back.
- Login with a wrong email or password answers 404.
- `defaultCustomerCode` is often empty; the customer code is then on `user.customer.code`.
- `GET /Contracts/{customerCode}` returns `{pager, groupedContracts}`, not one contract, and
  `contractType` is a name like `"ELECTRICITY_GRID"`, not a number.
- Some generated response parsers fail on real data (e.g. month periods like `"2026-10"` where
  the document says date-time); `meter_points` and the consumption methods skip them.

## Development

This package lives in the [umea-energi-api-client](https://github.com/klingenm/umea-energi-api-client)
repository, together with a local playground app. See the repository README for how to build and test it.

## License

[MIT](https://github.com/klingenm/umea-energi-api-client/blob/main/LICENSE). Provided "as is", without warranty of any kind.
