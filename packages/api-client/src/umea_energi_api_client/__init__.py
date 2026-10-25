"""Unofficial async Python client for the Umeå Energi API."""

from importlib.metadata import version

from .client import (
    DEFAULT_API_VERSION,
    PRODUCTION_BASE_URL,
    TEST_BASE_URL,
    USER_AGENT,
    BankIdProgress,
    CustomerType,
    TokenExpiredError,
    UmeaEnergiClient,
)
from .consumption import ContractType, MeterPoint, Resolution
from .credentials import Credentials, Login, User, jwt_expiry
from .errors import ApiError, InvalidCredentialsError, UmeaEnergiError
from .generated import AuthenticatedClient, Client

__all__ = [
    "DEFAULT_API_VERSION",
    "PRODUCTION_BASE_URL",
    "TEST_BASE_URL",
    "USER_AGENT",
    "ApiError",
    "AuthenticatedClient",
    "BankIdProgress",
    "Client",
    "ContractType",
    "Credentials",
    "CustomerType",
    "InvalidCredentialsError",
    "Login",
    "MeterPoint",
    "Resolution",
    "TokenExpiredError",
    "UmeaEnergiClient",
    "UmeaEnergiError",
    "User",
    "__version__",
    "jwt_expiry",
]

__version__ = version("umea-energi-api-client")
