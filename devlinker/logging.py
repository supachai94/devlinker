"""Logging setup for the application."""

from __future__ import annotations

import sys

from loguru import logger

from devlinker.settings import LoggingSettings


def configure_logging(settings: LoggingSettings) -> None:
    """Configure loguru with either human-readable or JSON output."""

    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.level.upper(),
        serialize=settings.json_logs,
        backtrace=False,
        diagnose=False,
    )
