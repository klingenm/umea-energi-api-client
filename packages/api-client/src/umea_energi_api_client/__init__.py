"""Python client for the Umeå Energi API."""

from importlib.metadata import version

from .generated import AuthenticatedClient, Client

__all__ = ["AuthenticatedClient", "Client", "__version__"]

__version__ = version("umea-energi-api-client")
