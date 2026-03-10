"""Structured logging configuration using structlog."""

import sys
from typing import Any

import structlog


def configure_logging() -> None:
    """Configure structlog for JSON output to stdout."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger with optional initial context.

    Args:
        **initial_context: Key-value pairs to bind to the logger.

    Returns:
        A bound structlog logger.
    """
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(
        **initial_context,
    )
    return logger
