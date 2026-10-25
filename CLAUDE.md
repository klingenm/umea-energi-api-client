# umea-energi-api-client

uv workspace with an unofficial Python client for the Umeå Energi API and a local web playground for it.

## Layout

- `pyproject.toml` — workspace root (virtual, no package): member list, dev dependency group, and the shared
  ruff/ty/pytest config for all packages
- `packages/api-client/` — `umea-energi-api-client`, published to PyPI (src layout, ships `py.typed`)
  - `src/umea_energi_api_client/client.py` — `UmeaEnergiClient`: login flows, refresh, revoke, and every
    workaround for where the real API differs from the OpenAPI document (listed in its module docstring).
    Put new workarounds here, not in the playground.
  - `credentials.py` (`Credentials`, `Login`, `User`, `jwt_expiry`), `errors.py`, `http_logging.py` (DEBUG
    traffic log with redaction), `testing.py` (`FakeApi`, a public httpx `MockTransport` test double)
  - `src/umea_energi_api_client/generated/` — client generated from the OpenAPI document. Gitignored, and
    regenerated automatically by the `typecheck`, `test`, `build` and `playground` tasks. **Never edit by hand**;
    change `openapi/config.yaml` or `scripts/normalize_openapi.py` and run `mise run --force generate`.
  - `openapi/swagger.json` — upstream OpenAPI document, kept verbatim (refresh with `mise run fetch-spec`)
  - `scripts/normalize_openapi.py` — patches known upstream spec gaps before generation
  - `README.md` is the PyPI page; `CHANGELOG.md` is written by knope
- `packages/playground/` — `umea-energi-playground`, never published: FastAPI app with server-rendered Jinja
  templates, SQLite via async SQLAlchemy (aiosqlite), and Alembic migrations
  - `src/umea_energi_playground/models.py` — database models
  - `src/umea_energi_playground/migrations/` — Alembic env and versions (config in the package's `pyproject.toml`
    under `[tool.alembic]`; there is no `alembic.ini`, so pass `-c pyproject.toml` to the alembic CLI)
  - `src/umea_energi_playground/tokens.py` — `TokenManager`: refresh and logout of stored tokens, with
    per-token locks; uses the library's `UmeaEnergiClient`
  - `src/umea_energi_playground/examples.py` — the sample API calls the UI can run
- `.changeset/` — pending change files; `knope.toml` — release config
- `mise.toml` — pinned tool versions (python, uv, ruff, openapi-python-client, knope), env, and tasks
- `mise.lock`, `.mise/locks/` — exact tool versions and checksums (`mise lock`; never edit by hand)

## Tooling

- **mise** manages tool versions and tasks. See the `mise` skill. Never install tools any other way.
- **uv** manages Python dependencies and the `.venv` for the whole workspace. Add dependencies to the package that
  needs them: `uv add --package umea-energi-playground <pkg>`; shared dev tools go in the root `dev` group
  (`uv add --dev <pkg>`). Never edit `uv.lock` by hand or use `pip`.
- **GitButler** (`but`) handles version control. See the `gitbutler` skill. Don't use git write commands.

## Commands

```sh
mise run sync        # install all workspace packages + dev deps into .venv
mise run format      # format + autofix lint
mise run check       # lint + typecheck + test (all packages) — run before every commit
mise run test -- -k <name>
mise run fetch-spec  # download the latest OpenAPI document
mise run generate    # regenerate the client (skips if inputs unchanged; `mise run --force generate`)
mise run playground  # run the playground on http://127.0.0.1:8000
mise run playground:revision -- -m "describe change"  # autogenerate a migration after editing models
```

## Playground

- Local use only: it stores real access and refresh tokens unencrypted in `packages/playground/playground.db`
  (gitignored). Don't log or print tokens.
- The app applies migrations on startup (`db.upgrade_database`). Every model change needs a migration:
  run `mise run playground:revision -- -m "..."`, review the generated file, and keep `render_as_batch` (SQLite).
  `mise run playground` reloads on model changes before the migration exists; run `mise run playground:migrate`
  afterwards. `tests/test_tokens.py::test_migrations_match_models` fails if models and migrations drift.
- Timestamps are timezone-aware UTC (`db.UTCDateTime`); never store naive datetimes.
- Login, refresh and logout all go through the library's `UmeaEnergiClient`; the playground only stores tokens
  (`AuthToken.apply(credentials)`) and serializes refresh/logout per token (`TokenManager`), because a refresh
  can rotate the refresh token. Examples refresh first and retry once on 401.
- Logout revokes the refresh token (needs a valid access token, so it refreshes first), then deletes the row;
  if revoking fails the row is kept and the user can retry or "forget locally" (`/tokens/{id}/delete`).
- Logging: `logs.configure_logging` sends `umea_energi_playground` (`PLAYGROUND_LOG_LEVEL`, INFO) and the
  library's traffic log (`PLAYGROUND_API_LOG_LEVEL`, DEBUG) to stderr; `mise run playground` output can be
  tee'd to `packages/playground/playground.log` (gitignored).
- Tests use `umea_energi_api_client.testing.FakeApi` and a temporary SQLite file; never call the real API.

## API facts (verified against production)

- `https://api.umeaenergi.se` is production; `https://tapi.umeaenergi.se` is a test environment (it serves the
  OpenAPI document; real accounts and BankID don't work there). Mina sidor (minasidor.umeaenergi.se) uses
  API version 1 for everything.
- `LoginManagerState` is the customer type (`CustomerType`): 0 = private person, 1 = company.
- `emailStep1` answers 404 for wrong credentials (the route exists; a wrong method gives 405).
- Logins return `token.access_token` (not `accessJwtToken`); the access token lives ~10 minutes. The refresh
  token (~1 year) comes as a `refreshToken` cookie and in `user.refreshToken.token`. `session/refresh-token`
  takes only the cookie; `session/revoke-token` takes the bearer token and the cookie.
- BankID: the start response's `completed` only means the order exists; a poll is done when it has a token.
  The QR code is a base64 SVG that changes every second.
- `user.defaultCustomerCode` is often null; the customer code is then `user.customer.code`.
- `GET /Contracts/{customerCode}` returns `{pager, groupedContracts: [{group, contracts}]}` (the document says one
  `ContractResponse`); `contractType` is a string (`ELECTRICITY`, `ELECTRICITY_GRID`, `DISTRICT_HEATING`,
  `DISTRICT_COOLING`, `BROADBAND`, `SOLAR_CELL`), not the document's integer enum.
- Consumption endpoint by contract type (as Mina sidor does): electricity → `electricityConsumption/{type}`,
  district heating → `heatingConsumption`, others → `consumption`; cost of `ELECTRICITY_GRID` is asked for as
  `ELECTRICITY`. Resolutions: `YEAR`, `MONTH`, `DAY`, `HOUR`, `QUARTER`. Query names are case-insensitive.
- Meter readings: the "delivery site code" these endpoints take is the contract's meter point. Electricity grid
  readings come from `delsiteMeterReadings` (`{values: [{timeStamp, reason, value}]}`); other types from
  `meterReadings` with `ShowEstimatedValuesStatus=true`. `maxConsumption` is documented with `FromDate`/`ToDate`
  but Mina sidor sends `from`/`to`; the client sends both. It only has data for company customers (Mina sidor shows
  it for district heating when the customer is a company); private customers get `[]` for any range.
- Generated response parsers can raise on real data (e.g. `"2026-10"` in a date-time field). Where that happens,
  build the request with the endpoint's `_get_kwargs` and send it without parsing (`UmeaEnergiClient._get_json`).
- Never log secrets: `http_logging.REDACTED_KEYS` plus any key containing "token" are redacted, and JWTs are
  scrubbed from any body. Add new secret-bearing keys there.

## Releases

Versioning uses [knope](https://knope.tech) change files (like JS changesets); commit messages don't affect versions.
Only `umea-energi-api-client` is released; playground changes need no change file.

- Every user-facing change to the client adds a change file in `.changeset/` in the same commit. `mise run change`
  creates one interactively; or write it directly:

  ```markdown
  ---
  default: minor
  ---

  # Short summary (becomes the changelog heading)

  Optional details.
  ```

  Use `major` / `minor` / `patch`. While on 0.x, knope bumps one level lower (`major` → 0.x+1.0, `minor` → patch).
- Don't edit the version in `packages/api-client/pyproject.toml` or its `CHANGELOG.md` by hand.
- `mise run release` (from a clean, pushed `main`) bumps the version, updates the changelog and `uv.lock`, commits,
  pushes and creates the GitHub release, which triggers `.github/workflows/publish.yml` → PyPI. Only run it when the
  user asks; preview with `mise run release -- --dry-run`.

## Generated client

Built with openapi-python-client (httpx + attrs). Every endpoint module exposes `sync`, `sync_detailed`,
`asyncio`, and `asyncio_detailed`. Endpoints live under `generated/api/<tag>/`, models under `generated/models/`.
The generated code is formatted with ruff but excluded from linting; ty still type-checks it.

## Conventions

- Python 3.14+. Use modern syntax (`X | None`, built-in generics, `match` where it helps).
- Type checking is ty via `uv check --all-packages` (pinned in the `typecheck` task); warnings fail the check.
  Annotate every function, including tests.
- Ruff line length is 100.
- Keep tests alongside the behavior they verify, in the package's own `tests/`. Don't hit the real API in tests;
  mock HTTP.
- Commit messages follow `type(scope): summary`; use the package as scope (`api-client`, `playground`).
