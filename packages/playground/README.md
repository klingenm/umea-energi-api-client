# umea-energi-playground

Local web app for trying out [`umea-energi-api-client`](../api-client) against the real
Umeå Energi API. Not published.

- Log in with **BankID** (QR code or "open BankID on this device") or **email** (password,
  then a one-time code sent by email).
- The access token from a successful login is stored in a local SQLite database, with the
  user's name, customer code and the token's expiry.
- Pick a stored token and run sample API calls with it (customer, contracts, invoices, …).
  Public endpoints such as electricity prices work without logging in.

```sh
mise run playground   # from the repository root; open http://127.0.0.1:8000
```

> **Local use only.** Tokens are stored unencrypted in `playground.db` and the app has no
> authentication of its own. It listens on 127.0.0.1 only.

## Configuration

| Variable | Default |
| --- | --- |
| `PLAYGROUND_DATABASE_URL` | `sqlite+aiosqlite:///playground.db` (relative to `packages/playground/`) |
| `PLAYGROUND_API_BASE_URL` | `https://tapi.umeaenergi.se` |
| `PLAYGROUND_API_VERSION` | `2` |

## Database

Models are in `src/umea_energi_playground/models.py`; migrations are managed with Alembic and
applied automatically on startup. After changing a model:

```sh
mise run playground:revision -- -m "describe the change"
```

Alembic is configured in this package's `pyproject.toml` (`[tool.alembic]`), so call the CLI
with `-c pyproject.toml`, e.g. `uv run alembic -c pyproject.toml history`.
