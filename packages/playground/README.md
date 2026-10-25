# umea-energi-playground

Local web app for trying out [`umea-energi-api-client`](../api-client) against the real
Umeå Energi API. Not published.

- Log in with **BankID** (QR code or "open BankID on this device") or **email** (password,
  then a one-time code sent by email).
- The access token from a successful login is stored in a local SQLite database, with the
  user's name, customer code and the token's expiry.
- The refresh token the API sets on login is stored too; access tokens (valid ~10 minutes) are
  refreshed automatically before they expire, or when the API rejects them.
- Pick a stored token and run sample API calls with it (customer, contracts, invoices, …).
- **Log out** revokes the refresh token at Umeå Energi and deletes the stored token.
- **Consumption and meter readings**: pick one of your meter points and a period to see
  consumption, cost, meter readings, meter statistics or max consumption as a bar chart (where
  the data has periods and values) and as the raw JSON response.
  Public endpoints such as electricity prices work without logging in.

```sh
mise run playground   # from the repository root; open http://127.0.0.1:8000
```

> **Local use only.** Access and refresh tokens (the latter valid for about a year) are stored unencrypted in `playground.db` and the app has no
> authentication of its own. It listens on 127.0.0.1 only.

## Configuration

| Variable | Default |
| --- | --- |
| `PLAYGROUND_DATABASE_URL` | `sqlite+aiosqlite:///playground.db` (relative to `packages/playground/`) |
| `PLAYGROUND_API_BASE_URL` | `https://api.umeaenergi.se` (production; `https://tapi.umeaenergi.se` is the test environment) |
| `PLAYGROUND_API_VERSION` | `1` (what Umeå Energi's own Mina sidor site uses) |
| `PLAYGROUND_LOG_LEVEL` | `INFO` |
| `PLAYGROUND_API_LOG_LEVEL` | `DEBUG`: the API client's request/response log, with secrets redacted |

## Database

Models are in `src/umea_energi_playground/models.py`; migrations are managed with Alembic and
applied automatically on startup. After changing a model:

```sh
mise run playground:revision -- -m "describe the change"
```

Alembic is configured in this package's `pyproject.toml` (`[tool.alembic]`), so call the CLI
with `-c pyproject.toml`, e.g. `uv run alembic -c pyproject.toml history`.
