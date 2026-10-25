# Changelog
## 0.1.1 (2026-10-25)

### Features

#### Add UmeaEnergiClient for logging in, refreshing and logging out

`UmeaEnergiClient` wraps the generated code with BankID and email login, token refresh (`refresh`, `fresh_credentials`) and logout (`revoke`). It targets production and API version 1 by default and handles where the real API differs from its OpenAPI document: the `access_token` field, the `refreshToken` cookie, 404 for wrong credentials, and the customer code fallback. Requests send a `User-Agent: umea-energi-api-client/<version>` header and are logged at DEBUG with secrets redacted, and `umea_energi_api_client.testing.FakeApi` helps test code that uses the library. `meter_points`, `consumption`, `consumption_cost`, `meter_readings`, `statistics_with_estimated_values`, `meter_statistics` and `max_consumption` list a customer's meter points and fetch consumption, costs and meter readings, picking the endpoint per contract type.

### Fixes

#### Read the access token returned by the production API

The production login endpoints return the JWT as `token.access_token`, which the OpenAPI document doesn't list, so the generated `UmeaEnergiApiModelsLoginAccessToken` model dropped it. The model now has an `access_token` attribute alongside `access_jwt_token`.

#### Use the production API host in the README example

`https://api.umeaenergi.se` is production; `https://tapi.umeaenergi.se`, previously used in the example, is Umeå Energi's test environment.

## 0.1.0 (2026-10-24)

### Features

#### Initial release

Unofficial, async-capable Python client for the Umeå Energi API, generated from its OpenAPI document.
