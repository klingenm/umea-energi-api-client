# umea-energi-api-client

uv workspace with an unofficial Python client for the Umeå Energi API.

## Layout

- `pyproject.toml` — workspace root (virtual, no package): member list, dev dependency group, and the shared
  ruff/ty/pytest config for all packages
- `packages/api-client/` — `umea-energi-api-client`, published to PyPI (src layout, ships `py.typed`)
  - `src/umea_energi_api_client/generated/` — client generated from the OpenAPI document. Gitignored, and
    regenerated automatically by the `typecheck`, `test` and `build` tasks. **Never edit by hand**;
    change `openapi/config.yaml` or `scripts/normalize_openapi.py` and run `mise run --force generate`.
  - `openapi/swagger.json` — upstream OpenAPI document, kept verbatim (refresh with `mise run fetch-spec`)
  - `scripts/normalize_openapi.py` — patches known upstream spec gaps before generation
  - `README.md` is the PyPI page; `CHANGELOG.md` is written by knope
- `.changeset/` — pending change files; `knope.toml` — release config
- `mise.toml` — pinned tool versions (python, uv, ruff, openapi-python-client, knope), env, and tasks
- `mise.lock`, `.mise/locks/` — exact tool versions and checksums (`mise lock`; never edit by hand)

## Tooling

- **mise** manages tool versions and tasks. See the `mise` skill. Never install tools any other way.
- **uv** manages Python dependencies and the `.venv` for the whole workspace. Add dependencies to the package that
  needs them: `uv add --package <package-name> <pkg>`; shared dev tools go in the root `dev` group
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
```

## Releases

Versioning uses [knope](https://knope.tech) change files (like JS changesets); commit messages don't affect versions.

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
- Commit messages follow `type(scope): summary`; use the package as scope (e.g. `api-client`).
