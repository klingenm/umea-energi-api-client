"""Logging setup: the playground's own logs and the API client's traffic log, to stderr."""

import logging


def configure_logging(level: str, api_level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s", "%H:%M:%S")
    )
    for name, logger_level in (
        ("umea_energi_playground", level),
        ("umea_energi_api_client", api_level),
    ):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(logger_level.upper())
        logger.propagate = False
