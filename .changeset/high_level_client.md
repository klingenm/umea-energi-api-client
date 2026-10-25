---
default: minor
---

# Add UmeaEnergiClient for logging in, refreshing and logging out

`UmeaEnergiClient` wraps the generated code with BankID and email login, token refresh (`refresh`, `fresh_credentials`) and logout (`revoke`). It targets production and API version 1 by default and handles where the real API differs from its OpenAPI document: the `access_token` field, the `refreshToken` cookie, 404 for wrong credentials, and the customer code fallback. Requests send a `User-Agent: umea-energi-api-client/<version>` header and are logged at DEBUG with secrets redacted, and `umea_energi_api_client.testing.FakeApi` helps test code that uses the library. `meter_points`, `consumption`, `consumption_cost`, `meter_readings`, `statistics_with_estimated_values`, `meter_statistics` and `max_consumption` list a customer's meter points and fetch consumption, costs and meter readings, picking the endpoint per contract type.
