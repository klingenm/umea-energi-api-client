---
name: mise
description: "Manage tool versions, environment variables and project tasks with mise. Use when installing, adding, pinning, upgrading or removing a dev tool (python, uv, ruff, etc.), when running project tasks (format, lint, typecheck, test, check, build), when a command is missing or the wrong version, or when editing mise.toml."
---

# mise

mise is the single source of truth for tool versions and project tasks in this repo.
Configuration lives in `mise.toml` at the repository root.

## Rules

- Never install tools with `brew`, `pipx`, `pip install --user`, `uv tool install`, or curl scripts.
  Add them to `mise.toml` with `mise use` instead.
- Python *libraries* (runtime and dev dependencies) belong in the workspace packages' `pyproject.toml`
  via `uv add --package <name>` / `uv add --dev`, not in mise. Standalone CLIs (ruff, uv itself, gh, …) belong in mise.
- uv is configured (via `[env]` in `mise.toml`) to use the mise-managed Python and never
  download its own. Don't override `UV_PYTHON*` variables or add a `.python-version` file.
- Prefer `mise run <task>` over retyping the underlying commands, so local runs match CI.
- Use `mise.local.toml` (gitignored) for personal overrides; don't put them in `mise.toml`.
- Exact tool versions, download URLs and checksums are pinned in `mise.lock` (linux-x64 for CI,
  macos-arm64 for local). pipx tools also lock their Python dependencies under `.mise/locks/`.
  After any `mise use`, `mise unuse` or `mise upgrade`, run `mise lock` and commit `mise.lock`
  and `.mise/locks/` together with `mise.toml`. CI installs with `MISE_LOCKED=1` and fails on a
  stale lockfile.

## Running tasks

```sh
mise tasks                # list tasks with descriptions
mise run format           # ruff format + ruff check --fix
mise run lint             # ruff format --check + ruff check
mise run typecheck        # ty, via uv check
mise run test             # pytest (all workspace packages)
mise run test -- -k name  # pass extra args through to the task
mise run check            # lint + typecheck + test (run before committing)
mise run sync             # uv sync --all-packages --all-groups
mise run build            # uv build --package umea-energi-api-client
mise run fetch-spec       # download the latest OpenAPI document
mise run generate         # regenerate the API client (mise run --force generate to bypass the up-to-date check)
mise run change           # add a knope change file to .changeset/
mise run release          # release pending changes (pushes + publishes; only when asked)
```

When adding a task, define it under `[tasks.<name>]` in `mise.toml` with a `description`
and a `run` string or list; use `depends` to compose tasks. Flags for mise itself (e.g. `--force`)
go *before* the task name; anything after it is passed to the task's command.

## Managing tools

```sh
mise ls --current            # tools and versions active in this directory
mise install                 # install everything pinned in mise.toml
mise use <tool>@<version>    # add or change a pin in mise.toml (e.g. mise use ruff@0.17)
mise unuse <tool>            # remove a tool from mise.toml
mise ls-remote <tool>        # list available versions
mise latest <tool>           # latest available version
mise outdated                # pinned tools with newer versions
mise upgrade --bump          # upgrade and rewrite pins in mise.toml
mise lock                    # refresh mise.lock after changing tools
mise lock --bump             # move locked versions to the newest matching the mise.toml prefixes
mise exec -- <cmd>           # run a command with mise's tools on PATH (when not activated)
```

Pins in `mise.toml` use a major.minor prefix (e.g. `python = "3.14"`); `mise.lock` fixes the exact
patch version. Use `mise lock --bump` to take newer patch releases without editing `mise.toml`.

## Troubleshooting

- `mise ERROR ... not trusted`: run `mise trust` in the repo root (only after reviewing `mise.toml`).
- Command not found or wrong version: check `mise ls --current`, then `mise install`. If the
  shell isn't activated, prefix the command with `mise exec --`.
- `.venv` built against the wrong interpreter: `rm -rf .venv && mise run sync`, then confirm
  `home` in `.venv/pyvenv.cfg` points into `~/.local/share/mise/installs/python/`.
- Tasks run from the repository root unless they set `dir` (the generate and fetch-spec
  tasks run inside the api-client package directory).
- `... is not in the lockfile` (CI or `MISE_LOCKED=1`): run `mise lock` and commit the result.
- `mise doctor` reports activation and config problems.
