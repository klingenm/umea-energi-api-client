import json

from umea_energi_api_client.http_logging import format_body


def test_format_body_redacts_nested_secrets_and_summarizes_qr_codes() -> None:
    body = b'{"token": {"accessJwtToken": "jwt"}, "qrCode": "PHN2Zz4=", "user": {"pnr": "1"}}'

    assert format_body(body) == (
        '{"token": {"accessJwtToken": "<redacted>"}, "qrCode": "<8 chars>", '
        '"user": {"pnr": "<redacted>"}}'
    )


def test_format_body_handles_empty_and_non_json_bodies() -> None:
    assert format_body(b"") == "(empty body)"
    assert format_body(b"Bad Request") == "Bad Request"


def test_format_body_redacts_production_login_response() -> None:
    body = json.dumps(
        {
            "token": {"access_token": "eyJhbGciOiJIUzI1NiJ9.eyJpZCI6IjEifQ.c2ln"},
            "user": {
                "phone": "070-000 00 00",
                "customer": {"code": "777", "persNo": "190001019999", "mobileNo": "0700000000"},
                "refreshToken": {"token": "refresh-secret", "createdByIp": "192.0.2.1"},
            },
        }
    ).encode()

    logged = format_body(body)

    for secret in ("eyJ", "070-000", "190001019999", "0700000000", "refresh-secret", "192.0.2.1"):
        assert secret not in logged
    assert '"code": "777"' in logged


def test_format_body_redacts_jwts_in_non_json_bodies() -> None:
    assert format_body(b"token=eyJhbGciOiJIUzI1NiJ9.eyJpZCI6IjEifQ.c2ln") == "token=<redacted>"
