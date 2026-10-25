"""The login flows the playground needs, on top of the generated API client."""

import json
from dataclasses import dataclass
from typing import Any

import httpx

from umea_energi_api_client import AuthenticatedClient, Client
from umea_energi_api_client.generated.api.session import (
    delete_api_vversion_session_reference_type as cancel_bankid,
)
from umea_energi_api_client.generated.api.session import (
    get_api_vversion_session_bankid_reference_type as poll_bankid,
)
from umea_energi_api_client.generated.api.session import (
    post_api_vversion_session_bankid as start_bankid,
)
from umea_energi_api_client.generated.api.session import (
    post_api_vversion_session_email_step_1 as email_step_1,
)
from umea_energi_api_client.generated.api.session import (
    post_api_vversion_session_email_step_2 as email_step_2,
)
from umea_energi_api_client.generated.models import (
    UmeaEnergiApiMiscsLoginManagerState as LoginManagerState,
)
from umea_energi_api_client.generated.models import (
    UmeaEnergiApiModelsLoginActivationKeyCredentials as ActivationKeyCredentials,
)
from umea_energi_api_client.generated.models import (
    UmeaEnergiApiModelsLoginBankidCredentials as BankidCredentials,
)
from umea_energi_api_client.generated.models import (
    UmeaEnergiApiModelsLoginEmailCredentials as EmailCredentials,
)
from umea_energi_api_client.generated.models import (
    UmeaEnergiApiModelsLoginLoginSession as LoginSession,
)
from umea_energi_api_client.generated.types import Response, Unset

__all__ = ["ApiError", "BankIdProgress", "LoginManagerState", "LoginResult", "UmeaEnergiApi"]


class ApiError(Exception):
    """A request to the API failed; `detail` is a human-readable reason."""

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail if status_code is None else f"HTTP {status_code}: {detail}")
        self.detail = detail
        self.status_code = status_code

    @classmethod
    def from_response(cls, response: Response[Any]) -> ApiError:
        return cls(_error_detail(response.content), int(response.status_code))


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    display_name: str
    email: str | None
    api_user_id: int | None
    customer_code: str | None


@dataclass(frozen=True)
class BankIdProgress:
    reference: str
    auto_start_token: str | None
    qr_code: str | None
    """Base64-encoded SVG. BankID's QR code changes every second, so each poll returns a new one."""
    result: LoginResult | None
    """Set once the user has identified themselves in the BankID app."""


class UmeaEnergiApi:
    def __init__(
        self, base_url: str, version: str, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.base_url = base_url
        self.version = version
        self._httpx_args: dict[str, Any] = {} if transport is None else {"transport": transport}

    def client(self) -> Client:
        return Client(base_url=self.base_url, httpx_args=self._httpx_args)

    def authenticated_client(self, token: str) -> AuthenticatedClient:
        return AuthenticatedClient(base_url=self.base_url, token=token, httpx_args=self._httpx_args)

    async def start_bankid(self, state: LoginManagerState) -> BankIdProgress:
        async with self.client() as client:
            response = await start_bankid.asyncio_detailed(
                self.version, client=client, body=BankidCredentials(type_=state)
            )
        session = _login_session(response)
        reference = _value(session.id)
        if not reference:
            raise ApiError("The API did not return a BankID reference.")
        return _bankid_progress(reference, session)

    async def poll_bankid(self, reference: str, state: LoginManagerState) -> BankIdProgress:
        async with self.client() as client:
            response = await poll_bankid.asyncio_detailed(
                self.version, reference, int(state), client=client
            )
        return _bankid_progress(reference, _login_session(response))

    async def cancel_bankid(self, reference: str, state: LoginManagerState) -> None:
        async with self.client() as client:
            response = await cancel_bankid.asyncio_detailed(
                self.version, reference, int(state), client=client
            )
        _raise_for_status(response)

    async def start_email_login(
        self, username: str, password: str, state: LoginManagerState
    ) -> None:
        """Check the password; on success the API emails a one-time code to the user."""
        body = EmailCredentials(username=username, password=password, type_=state)
        async with self.client() as client:
            response = await email_step_1.asyncio_detailed(self.version, client=client, body=body)
        _raise_for_status(response)

    async def complete_email_login(
        self, username: str, code: str, state: LoginManagerState
    ) -> LoginResult:
        body = ActivationKeyCredentials(username=username, activation_key=code, type_=state)
        async with self.client() as client:
            response = await email_step_2.asyncio_detailed(self.version, client=client, body=body)
        result = _login_result(_login_session(response))
        if result is None:
            raise ApiError("The API did not return an access token.")
        return result


def _value[T](value: T | Unset) -> T | None:
    return None if isinstance(value, Unset) else value


def _raise_for_status(response: Response[Any]) -> None:
    if response.status_code >= 400:
        raise ApiError.from_response(response)


def _login_session(response: Response[Any]) -> LoginSession:
    _raise_for_status(response)
    if not isinstance(response.parsed, LoginSession):
        raise ApiError(f"Unexpected response: {_error_detail(response.content)}")
    return response.parsed


def _bankid_progress(reference: str, session: LoginSession) -> BankIdProgress:
    return BankIdProgress(
        reference=reference,
        auto_start_token=_value(session.auto_start_token),
        qr_code=_value(session.qr_code),
        result=_login_result(session),
    )


def _login_result(session: LoginSession) -> LoginResult | None:
    token = _value(session.token)
    access_token = _value(token.access_jwt_token) if token else None
    if not access_token:
        return None
    user = _value(session.user)
    if user is None:
        return LoginResult(access_token, "Unknown user", None, None, None)
    first_name, last_name = _value(user.first_name), _value(user.last_name)
    email = _value(user.email)
    customer = _value(user.customer)
    customer_code = _value(user.default_customer_code) or (
        _value(customer.code) if customer else None
    )
    return LoginResult(
        access_token=access_token,
        display_name=" ".join(filter(None, [first_name, last_name])) or email or "Unknown user",
        email=email,
        api_user_id=_value(user.id),
        customer_code=customer_code,
    )


def _error_detail(content: bytes) -> str:
    text = content.decode(errors="replace").strip()
    try:
        data = json.loads(text)
    except ValueError:
        return text[:500] or "(empty response)"
    if isinstance(data, dict):
        for key in ("message", "title", "error", "detail"):
            if isinstance(data.get(key), str):
                return data[key]
    return text[:500]
