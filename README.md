# umea-energi-api-client

Unofficial Python tooling for the [Umeå Energi API](https://tapi.umeaenergi.se/).

> **Disclaimer:** This is an independent project. The author has no affiliation with
> Umeå Energi, which neither endorses nor supports it.

| Package | Description |
| --- | --- |
| [`packages/api-client`](packages/api-client) | [`umea-energi-api-client`](https://pypi.org/project/umea-energi-api-client/): async-capable client generated from the API's OpenAPI document. Published to PyPI. |
| [`packages/playground`](packages/playground) | Local web app for trying the client: log in with BankID or email, store the token, and call the API with it. |

## Development

The repository is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/).
Tool versions (Python, uv, ruff, openapi-python-client, knope) are pinned with [mise](https://mise.jdx.dev).

```sh
mise install         # install pinned tools
mise run sync        # create .venv with all packages and dev dependencies
mise run check       # lint, typecheck and test everything
mise run playground  # run the playground on http://127.0.0.1:8000
```

The API client is generated into `packages/api-client/src/umea_energi_api_client/generated/`
(gitignored). The `check`, `build` and `playground` tasks generate it as needed; run
`mise run generate` once after cloning so imports work in your editor. `mise run fetch-spec`
updates the OpenAPI document.

Run `mise tasks` to list all tasks.

### Releasing

Changes to the API client are tracked with [knope](https://knope.tech) change files in
`.changeset/` (`mise run change`). `mise run release` bumps the version, updates the changelog,
pushes, and creates a GitHub release, which publishes the package to PyPI.

## License

[MIT](LICENSE). Provided "as is", without warranty of any kind.
