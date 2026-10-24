# umea-energi-api-client

Python library providing a client for the Umeå Energi API.

## Layout

- `src/umea_energi_api_client/` — the package (src layout, ships `py.typed`)
- `src/umea_energi_api_client/generated/` — API client generated from the OpenAPI document. Gitignored, and
  regenerated automatically by the `typecheck`, `test` and `build` tasks. **Never edit by hand**; change
  `openapi/config.yaml` or `scripts/normalize_openapi.py` and run `mise run --force generate`.
- `openapi/swagger.json` — upstream OpenAPI document, kept verbatim (refresh with `mise run fetch-spec`)
- `scripts/normalize_openapi.py` — patches known upstream spec gaps before generation
- `tests/` — pytest tests
- `pyproject.toml` — package metadata, dependencies, and ruff/ty/pytest config (build backend: `uv_build`)
- `mise.toml` — pinned tool versions (python, uv, ruff, openapi-python-client), env, and project tasks

## Tooling

- **mise** manages tool versions and tasks. See the `mise` skill. Never install tools any other way.
- **uv** manages Python dependencies and the `.venv`. Use `uv add <pkg>` / `uv add --dev <pkg>`;
  never edit `uv.lock` by hand or use `pip`.
- **GitButler** (`but`) handles version control. See the `gitbutler` skill. Don't use git write commands.

## Commands

```sh
mise run sync       # install deps into .venv
mise run format     # format + autofix lint
mise run check      # lint + typecheck + test — run before every commit
mise run test -- -k <name>
mise run fetch-spec # download the latest OpenAPI document
mise run generate   # regenerate the client (skips if inputs unchanged; `mise run --force generate`)
```

## Generated client

Built with openapi-python-client (httpx + attrs). Every endpoint module exposes `sync`, `sync_detailed`,
`asyncio`, and `asyncio_detailed`. Endpoints live under `generated/api/<tag>/`, models under `generated/models/`.
The generated code is formatted with ruff but excluded from linting; ty still type-checks it.

## Conventions

- Python 3.14+. Use modern syntax (`X | None`, built-in generics, `match` where it helps).
- Type checking is ty via `uv check` (pinned in the `typecheck` task); warnings fail the check.
  Annotate every function, including tests.
- Ruff line length is 100.
- Keep tests alongside the behavior they verify. Don't hit the real API in tests; mock HTTP.
- Commit messages follow `type(scope): summary`.
