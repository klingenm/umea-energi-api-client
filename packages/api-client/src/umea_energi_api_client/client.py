"""High-level async client: login flows, token refresh and logout, on top of the generated code.

The raw API differs from its OpenAPI document in several ways; this module hides them:

- `https://api.umeaenergi.se` is production; `https://tapi.umeaenergi.se` (where the document is
  published) is a test environment where real accounts and BankID don't work.
- Umeå Energi's own site (Mina sidor) uses API version 1, so that is the default here.
- Logins return the JWT as `token.access_token`, not `accessJwtToken`.
- The refresh token is set as a `refreshToken` cookie, which refresh and revoke read back.
- `emailStep1` answers 404 when the email and password don't match an account.
- On the BankID start response `completed` means the order was created; a poll is done when it
  returns a token.
- The customer endpoints need a customer code, which may only be on `user.customer.code`.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from enum import IntEnum
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

from .consumption import (
    ELECTRICITY_TYPES,
    ContractType,
    MeterPoint,
    Resolution,
    midnight,
    parse_meter_points,
)
from .credentials import DEFAULT_REFRESH_MARGIN, Credentials, Login, User
from .errors import ApiError, InvalidCredentialsError, UmeaEnergiError, error_detail
from .generated.api.contracts import (
    get_api_vversion_contracts_customer_code as contracts_endpoint,
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_consumption as consumption_endpoint,
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_consumption_cost_contract_category as cost_endpoint,
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_delsite_meter_readings as delsite_readings_endpoint,
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_electricity_consumption_contract_category as electricity_endpoint,  # noqa: E501
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_heating_consumption as heating_endpoint,
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_max_consumption as max_consumption_endpoint,
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_meter_readings as readings_endpoint,
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_meter_statistics as meter_statistics_endpoint,
)
from .generated.api.customer import (
    get_api_vversion_customer_customer_code_statistics_with_estimated_values as estimated_endpoint,
)
from .generated.api.session import (
    delete_api_vversion_session_reference_type as cancel_bankid,
)
from .generated.api.session import (
    get_api_vversion_session_bankid_reference_type as poll_bankid,
)
from .generated.api.session import (
    post_api_vversion_session_bankid as start_bankid,
)
from .generated.api.session import (
    post_api_vversion_session_email_step_1 as email_step_1,
)
from .generated.api.session import (
    post_api_vversion_session_email_step_2 as email_step_2,
)
from .generated.api.session import (
    post_api_vversion_session_refresh_token as refresh_token_endpoint,
)
from .generated.api.session import (
    post_api_vversion_session_revoke_token as revoke_token_endpoint,
)
from .generated.client import AuthenticatedClient, Client
from .generated.models import (
    UmeaEnergiApiMiscsLoginManagerState as LoginManagerState,
)
from .generated.models import (
    UmeaEnergiApiModelsLoginActivationKeyCredentials as ActivationKeyCredentials,
)
from .generated.models import (
    UmeaEnergiApiModelsLoginBankidCredentials as BankidCredentials,
)
from .generated.models import (
    UmeaEnergiApiModelsLoginEmailCredentials as EmailCredentials,
)
from .generated.models import (
    UmeaEnergiApiModelsLoginLoginSession as LoginSession,
)
from .generated.types import UNSET, Response, Unset
from .http_logging import EVENT_HOOKS

PRODUCTION_BASE_URL = "https://api.umeaenergi.se"
TEST_BASE_URL = "https://tapi.umeaenergi.se"
DEFAULT_API_VERSION = "1"
REFRESH_COOKIE = "refreshToken"


def _user_agent() -> str:
    try:
        package_version = version("umea-energi-api-client")
    except PackageNotFoundError:
        package_version = "unknown"
    return f"umea-energi-api-client/{package_version} (+https://github.com/klingenm/umea-energi-api-client)"


USER_AGENT = _user_agent()

# httpx.AsyncClient arguments the generated clients set themselves, mapped to their own options.
_CLIENT_OPTIONS = {
    "headers": "headers",
    "cookies": "cookies",
    "timeout": "timeout",
    "verify": "verify_ssl",
    "follow_redirects": "follow_redirects",
}


class CustomerType(IntEnum):
    """Whether to log in as a private person or a company (the API's `LoginManagerState`)."""

    PRIVATE = 0
    COMPANY = 1


class TokenExpiredError(UmeaEnergiError):
    """The access token has expired and there is no usable refresh token; log in again."""


@dataclass(frozen=True)
class BankIdProgress:
    reference: str
    auto_start_token: str | None
    """Open `bankid:///?autostarttoken=<token>&redirect=null` to start BankID on this device."""
    qr_code: str | None
    """Base64-encoded SVG. BankID's QR code changes every second; poll about once a second."""
    login: Login | None
    """Set once the user has identified themselves in the BankID app."""


@dataclass(frozen=True)
class _Sent[T]:
    response: Response[T]
    refresh_token: str | None
    """Value of a refreshToken cookie the response set, if any."""


class UmeaEnergiClient:
    """Async client for the Umeå Energi API.

    Use the login methods here, then call any generated endpoint with
    `client.authenticated_client(credentials.access_token)` and `version=client.api_version`.
    Requests and responses are logged at DEBUG level on the `umea_energi_api_client` logger,
    with tokens, passwords and personal data redacted.
    """

    def __init__(
        self,
        base_url: str = PRODUCTION_BASE_URL,
        *,
        api_version: str = DEFAULT_API_VERSION,
        httpx_args: dict[str, Any] | None = None,
    ) -> None:
        """`httpx_args` go to the underlying `httpx.AsyncClient` (e.g. `timeout`, `transport`).

        Requests send `User-Agent: umea-energi-api-client/<version>`; pass a `User-Agent` in
        `httpx_args["headers"]` to override it.
        """
        self.base_url = base_url
        self.api_version = api_version
        args = dict(httpx_args or {})
        self._options: dict[str, Any] = {
            option: args.pop(arg) for arg, option in _CLIENT_OPTIONS.items() if arg in args
        }
        headers = {"User-Agent": USER_AGENT}
        headers.update(dict(self._options.pop("headers", {})))
        self._headers = headers
        hooks = {event: list(functions) for event, functions in args.get("event_hooks", {}).items()}
        for event, functions in EVENT_HOOKS.items():
            hooks.setdefault(event, []).extend(functions)
        args["event_hooks"] = hooks
        self._httpx_args = args

    def client(self) -> Client:
        """A generated-code client for endpoints that need no login."""
        return Client(
            base_url=self.base_url,
            # A fresh dict per client: AuthenticatedClient writes its Authorization header into it.
            headers=dict(self._headers),
            httpx_args=self._httpx_args,
            **self._options,
        )

    def authenticated_client(self, access_token: str) -> AuthenticatedClient:
        """A generated-code client that sends `access_token` as a bearer token."""
        return AuthenticatedClient(
            base_url=self.base_url,
            token=access_token,
            headers=dict(self._headers),
            httpx_args=self._httpx_args,
            **self._options,
        )

    # BankID

    async def start_bankid(
        self, customer_type: CustomerType = CustomerType.PRIVATE
    ) -> BankIdProgress:
        """Start a BankID order. Show its QR code (or autostart link), then poll it."""
        body = BankidCredentials(type_=LoginManagerState(int(customer_type)))
        sent = await self._send(
            self.client(),
            lambda client: start_bankid.asyncio_detailed(
                self.api_version, client=client, body=body
            ),
        )
        session = _login_session(sent.response)
        reference = _value(session.id)
        if not reference:
            raise ApiError("The API did not return a BankID reference.")
        return _bankid_progress(reference, session, sent.refresh_token)

    async def poll_bankid(
        self, reference: str, customer_type: CustomerType = CustomerType.PRIVATE
    ) -> BankIdProgress:
        """Check a BankID order; `login` is set once the user has signed in."""
        sent = await self._send(
            self.client(),
            lambda client: poll_bankid.asyncio_detailed(
                self.api_version, reference, int(customer_type), client=client
            ),
        )
        return _bankid_progress(reference, _login_session(sent.response), sent.refresh_token)

    async def cancel_bankid(
        self, reference: str, customer_type: CustomerType = CustomerType.PRIVATE
    ) -> None:
        sent = await self._send(
            self.client(),
            lambda client: cancel_bankid.asyncio_detailed(
                self.api_version, reference, int(customer_type), client=client
            ),
        )
        _raise_for_status(sent.response)

    # Email: password first, then the one-time code the API emails to the user.

    async def start_email_login(
        self, username: str, password: str, customer_type: CustomerType = CustomerType.PRIVATE
    ) -> None:
        """Check the password; on success the API emails a one-time code to the user.

        Raises `InvalidCredentialsError` when the email and password don't match an account.
        """
        body = EmailCredentials(
            username=username, password=password, type_=LoginManagerState(int(customer_type))
        )
        sent = await self._send(
            self.client(),
            lambda client: email_step_1.asyncio_detailed(
                self.api_version, client=client, body=body
            ),
        )
        if sent.response.status_code == 404:
            # The route exists; the API answers 404 when no account matches the credentials.
            raise InvalidCredentialsError("Incorrect email or password (or no such account).", 404)
        _raise_for_status(sent.response)

    async def complete_email_login(
        self, username: str, code: str, customer_type: CustomerType = CustomerType.PRIVATE
    ) -> Login:
        """Exchange the emailed one-time code for tokens. Each code works once."""
        body = ActivationKeyCredentials(
            username=username,
            activation_key=code.strip(),
            type_=LoginManagerState(int(customer_type)),
        )
        sent = await self._send(
            self.client(),
            lambda client: email_step_2.asyncio_detailed(
                self.api_version, client=client, body=body
            ),
        )
        login = _login(_login_session(sent.response), sent.refresh_token)
        if login is None:
            raise ApiError("The API did not return an access token.")
        return login

    # Tokens

    async def refresh(self, refresh_token: str) -> Login:
        """Exchange a refresh token for a new access token (and possibly a new refresh token)."""
        sent = await self._send(
            self.client().with_cookies({REFRESH_COOKIE: refresh_token}),
            lambda client: refresh_token_endpoint.asyncio_detailed(self.api_version, client=client),
        )
        _raise_for_status(sent.response)
        try:
            session = LoginSession.from_dict(json.loads(sent.response.content))
        except (ValueError, TypeError, KeyError) as error:
            raise ApiError(f"Unexpected refresh response: {error}") from error
        login = _login(session, sent.refresh_token)
        if login is None:
            raise ApiError("The refresh response did not contain an access token.")
        if login.credentials.refresh_token:
            return login
        # The API didn't rotate the refresh token; keep using the old one.
        credentials = replace(login.credentials, refresh_token=refresh_token)
        return replace(login, credentials=credentials)

    async def fresh_credentials(
        self,
        credentials: Credentials,
        *,
        force: bool = False,
        margin: timedelta = DEFAULT_REFRESH_MARGIN,
    ) -> Credentials:
        """Return `credentials`, refreshed first if the access token expires within `margin`.

        Raises `TokenExpiredError` when a refresh is needed but there is no usable refresh token.
        Persist the result: the refresh token may have been rotated, and the old one stops working.
        """
        if not force and not credentials.needs_refresh(margin):
            return credentials
        if not credentials.refresh_token or not credentials.can_refresh():
            raise TokenExpiredError("The access token has expired and can't be refreshed.")
        login = await self.refresh(credentials.refresh_token)
        new = login.credentials
        if new.refresh_token_expires_at is None and new.refresh_token == credentials.refresh_token:
            new = replace(new, refresh_token_expires_at=credentials.refresh_token_expires_at)
        return new

    async def revoke(self, credentials: Credentials) -> None:
        """Log out: revoke the refresh token on the server.

        The API needs a valid access token for this, so call `fresh_credentials` first if it may
        have expired. The access token itself stays valid until it expires (about 10 minutes).
        """
        if not credentials.refresh_token:
            raise ValueError("There is no refresh token to revoke.")
        client = self.authenticated_client(credentials.access_token).with_cookies(
            {REFRESH_COOKIE: credentials.refresh_token}
        )
        sent = await self._send(
            client,
            lambda client: revoke_token_endpoint.asyncio_detailed(self.api_version, client=client),
        )
        _raise_for_status(sent.response)

    # Consumption. These responses don't reliably match the OpenAPI document (the generated
    # parsers fail on real data), so they are sent without them and returned as plain JSON.

    async def meter_points(self, access_token: str, customer_code: str) -> list[MeterPoint]:
        """The meter points of the customer's contracts (electricity, district heating, ...)."""
        request = contracts_endpoint._get_kwargs(
            self.api_version, customer_code, page_number=1, max_contracts=5000
        )
        return parse_meter_points(await self._get_json(access_token, request), customer_code)

    async def consumption(
        self,
        access_token: str,
        meter_point: MeterPoint,
        start: date,
        end: date,
        resolution: Resolution = Resolution.DAY,
    ) -> Any:
        """Consumption for a meter point between two dates, as the JSON the API returns.

        Picks the endpoint like Mina sidor does: `electricityConsumption/{type}` for electricity,
        `heatingConsumption` for district heating, and `consumption` for everything else.
        """
        code, number = meter_point.customer_code, meter_point.meter_point_no
        query: dict[str, Any] = {
            "meter_point_no": number,
            "from_": midnight(start),
            "to": midnight(end),
            "resolution": str(resolution),
        }
        if meter_point.contract_type in ELECTRICITY_TYPES:
            request = electricity_endpoint._get_kwargs(
                self.api_version, code, meter_point.contract_type, **query
            )
        elif meter_point.contract_type == ContractType.DISTRICT_HEATING:
            request = heating_endpoint._get_kwargs(self.api_version, code, **query)
        else:
            request = consumption_endpoint._get_kwargs(self.api_version, code, **query)
        return await self._get_json(access_token, request)

    async def consumption_cost(
        self,
        access_token: str,
        meter_point: MeterPoint,
        start: date,
        end: date,
        resolution: Resolution = Resolution.MONTH,
    ) -> Any:
        """Cost of the consumption for a meter point, as the JSON the API returns."""
        # Like Mina sidor: the cost of grid contracts is asked for as ELECTRICITY.
        category = (
            ContractType.ELECTRICITY
            if meter_point.contract_type in ELECTRICITY_TYPES
            else meter_point.contract_type
        )
        request = cost_endpoint._get_kwargs(
            self.api_version,
            meter_point.customer_code,
            str(category),
            meter_point_no=meter_point.meter_point_no,
            from_=midnight(start),
            to=midnight(end),
            resolution=str(resolution),
        )
        return await self._get_json(access_token, request)

    # Meter readings. Like Mina sidor, these pass the meter point as the "delivery site code".

    async def meter_readings(
        self, access_token: str, meter_point: MeterPoint, start: date, end: date
    ) -> Any:
        """Meter readings (meter indications) between two dates, as the JSON the API returns.

        Electricity grid contracts use `delsiteMeterReadings`; other contract types use
        `meterReadings`, including whether each value is estimated.
        """
        code, number = meter_point.customer_code, meter_point.meter_point_no
        if meter_point.contract_type == ContractType.ELECTRICITY_GRID:
            request = delsite_readings_endpoint._get_kwargs(
                self.api_version,
                code,
                start_date=midnight(start),
                end_date=midnight(end),
                delivery_site_code=number,
                contract_category=meter_point.contract_type,
            )
        else:
            request = readings_endpoint._get_kwargs(
                self.api_version,
                code,
                contract_type=meter_point.contract_type,
                delivery_site_code=number,
                start_date=midnight(start),
                end_date=midnight(end),
                show_estimated_values_status=True,
            )
        return await self._get_json(access_token, request)

    async def statistics_with_estimated_values(
        self,
        access_token: str,
        meter_point: MeterPoint,
        start: date,
        end: date,
        resolution: Resolution = Resolution.DAY,
    ) -> Any:
        """Meter statistics where gaps are filled with estimated values (HOUR or DAY)."""
        request = estimated_endpoint._get_kwargs(
            self.api_version,
            meter_point.customer_code,
            resolution=str(resolution),
            delivery_site_code=meter_point.meter_point_no,
            start_date=midnight(start),
            end_date=midnight(end),
        )
        return await self._get_json(access_token, request)

    async def meter_statistics(
        self,
        access_token: str,
        meter_point: MeterPoint,
        start: date,
        end: date,
        variables: str | None = None,
    ) -> Any:
        """Statistics per meter variable, e.g. `FVTQW` (district heating) or `MVT` (electricity)."""
        request = meter_statistics_endpoint._get_kwargs(
            self.api_version,
            meter_point.customer_code,
            delivery_site_code=meter_point.meter_point_no,
            start_date=midnight(start),
            end_date=midnight(end),
            specified_variables=variables or UNSET,
        )
        return await self._get_json(access_token, request)

    async def max_consumption(
        self, access_token: str, meter_point: MeterPoint, start: date, end: date
    ) -> Any:
        """The highest district heating effect (kW) readings between two dates, grouped by year.

        Only company customers get data (Mina sidor shows this only for companies, and asks for
        everything from 1970-01-01); for private customers the API returns an empty list.
        """
        request = max_consumption_endpoint._get_kwargs(
            self.api_version,
            meter_point.customer_code,
            delivery_site_code=meter_point.meter_point_no,
            from_date=midnight(start),
            to_date=midnight(end),
        )
        # The document calls the range FromDate/ToDate; Mina sidor sends from/to. Send both.
        request["params"].update({"from": start.isoformat(), "to": end.isoformat()})
        return await self._get_json(access_token, request)

    async def _get_json(self, access_token: str, request: dict[str, Any]) -> Any:
        """Send a request built by a generated `_get_kwargs`, without the generated parser."""
        client = self.authenticated_client(access_token)
        try:
            async with client:
                response = await client.get_async_httpx_client().request(**request)
        except httpx.HTTPError as error:
            raise ApiError(f"Request failed: {error!r}") from error
        if response.status_code >= 400:
            raise ApiError(error_detail(response.content), response.status_code)
        try:
            return response.json()
        except ValueError:
            return response.text

    async def _send[C: Client | AuthenticatedClient, T](
        self, client: C, call: Callable[[C], Awaitable[Response[T]]]
    ) -> _Sent[T]:
        """Make one API call, turning network failures into `ApiError`."""
        try:
            async with client:
                response = await call(client)
                return _Sent(response, _response_refresh_cookie(client.get_async_httpx_client()))
        except httpx.HTTPError as error:
            raise ApiError(f"Request failed: {error!r}") from error


def _value[T](value: T | Unset) -> T | None:
    return None if isinstance(value, Unset) else value


def _raise_for_status(response: Response[Any]) -> None:
    if response.status_code >= 400:
        raise ApiError.from_response(response)


def _login_session(response: Response[Any]) -> LoginSession:
    _raise_for_status(response)
    if not isinstance(response.parsed, LoginSession):
        raise ApiError(f"Unexpected response: {error_detail(response.content)}")
    return response.parsed


def _response_refresh_cookie(client: httpx.AsyncClient) -> str | None:
    # Cookies a response set carry the API's domain; cookies we sent ourselves have none.
    for cookie in client.cookies.jar:
        if cookie.name == REFRESH_COOKIE and cookie.domain and cookie.value:
            return cookie.value
    return None


def _bankid_progress(
    reference: str, session: LoginSession, refresh_cookie: str | None
) -> BankIdProgress:
    return BankIdProgress(
        reference=reference,
        auto_start_token=_value(session.auto_start_token),
        qr_code=_value(session.qr_code),
        login=_login(session, refresh_cookie),
    )


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _login(session: LoginSession, refresh_cookie: str | None) -> Login | None:
    token = _value(session.token)
    # Production returns access_token; the OpenAPI document only lists accessJwtToken.
    access_token = (_value(token.access_jwt_token) or _value(token.access_token)) if token else None
    if not access_token:
        return None
    user = _value(session.user)
    refresh = _value(user.refresh_token) if user else None
    credentials = Credentials(
        access_token=access_token,
        refresh_token=refresh_cookie or (_value(refresh.token) if refresh else None),
        refresh_token_expires_at=_aware(_value(refresh.expires)) if refresh else None,
    )
    if user is None:
        return Login(credentials=credentials, user=None)
    first_name, last_name = _value(user.first_name), _value(user.last_name)
    email = _value(user.email)
    customer = _value(user.customer)
    return Login(
        credentials=credentials,
        user=User(
            id=_value(user.id),
            display_name=" ".join(filter(None, [first_name, last_name])) or email or "Unknown user",
            email=email,
            customer_code=_value(user.default_customer_code)
            or (_value(customer.code) if customer else None),
        ),
    )
