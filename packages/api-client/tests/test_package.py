import tomllib
from pathlib import Path

import umea_energi_api_client


def test_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert umea_energi_api_client.__version__ == pyproject["project"]["version"]
