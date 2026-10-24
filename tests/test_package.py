import umea_energi_api_client


def test_version_is_exposed() -> None:
    assert umea_energi_api_client.__version__ == "0.1.0"
