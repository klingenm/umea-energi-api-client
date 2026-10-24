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
- `.changeset/` — pending change files; `knope.toml` — release config; `CHANGELOG.md` — written by knope
- `pyproject.toml` — package metadata, dependencies, and ruff/ty/pytest config (build backend: `uv_build`)
- `mise.toml` — pinned tool versions (python, uv, ruff, openapi-python-client, knope), env, and project tasks

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

## Releases

Versioning uses [knope](https://knope.tech) change files (like JS changesets); commit messages don't affect versions.

- Every user-facing change adds a change file in `.changeset/` in the same commit. `mise run change` creates one
  interactively; or write it directly:

  ```markdown
  ---
  default: minor
  ---

  # Short summary (becomes the changelog heading)

  Optional details.
  ```

  Use `major` / `minor` / `patch`. While on 0.x, knope bumps one level lower (`major` → 0.x+1.0, `minor` → patch).
- Don't edit the version in `pyproject.toml` or `CHANGELOG.md` by hand.
- `mise run release` (from a clean, pushed `main`) bumps the version, updates `CHANGELOG.md` and `uv.lock`, commits,
  pushes and creates the GitHub release, which triggers `.github/workflows/publish.yml` → PyPI. Only run it when the
  user asks; preview with `mise run release -- --dry-run`.

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
