"""File-based structured logging (CSV or flat file) for the backend.

Quick start::

    from app_logging import get_logger, log_context, timed

    logger = get_logger(__name__)
    logger.info("Claims imported", extra={"event_name": "claims_import",
                                          "result_code": 200, "rows": 120})

    with log_context(rule_engine_id=5, rule_name="Nightly"):
        with timed(logger, "node_run", node_id=12, node_function="validate"):
            ...

Wiring (already done in ``automation/settings.py``)::

    from app_logging import build_logging_config
    LOGGING = build_logging_config()
    MIDDLEWARE = ["app_logging.middleware.RequestLoggingMiddleware", ...]

See README.md in this folder for the column reference and configuration.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from .config import LogConfig, get_config
from .context import (  # noqa: F401  (public API)
    bind,
    get_context,
    log_context,
    new_operation_id,
    new_span_id,
    reset,
)
from .schema import AZURE_FIELD_MAP, COLUMNS  # noqa: F401

__all__ = [
    "build_logging_config",
    "setup_logging",
    "get_logger",
    "timed",
    "log_context",
    "get_context",
    "new_operation_id",
    "get_config",
    "COLUMNS",
    "AZURE_FIELD_MAP",
]

_ROOT_NAMESPACE = "app"


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Normal ``logging`` logger; ``name`` is written to the ``module`` column."""
    return logging.getLogger(name or _ROOT_NAMESPACE)


def build_logging_config(config: Optional[LogConfig] = None) -> Dict[str, Any]:
    """A ``logging.config.dictConfig`` dict - assign it to ``LOGGING`` in settings."""
    config = config or get_config()
    handlers: Dict[str, Any] = {
        "app_file": {"()": "app_logging.handlers.build_file_handler"},
    }
    if config.console:
        handlers["app_console"] = {"()": "app_logging.handlers.build_console_handler"}
    active = list(handlers)

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": handlers,
        "root": {"handlers": active, "level": config.level},
        "loggers": {
            # The request middleware already logs every response (including
            # 5xx) with full detail; silence Django's duplicate of it.
            "django.request": {"handlers": [], "propagate": False, "level": "ERROR"},
            # Noisy at DEBUG (every SQL statement); opt in via code if needed.
            "django.db.backends": {"level": "WARNING"},
        },
    }


def setup_logging(config: Optional[LogConfig] = None) -> None:
    """For scripts that run outside Django (Django applies ``LOGGING`` itself)."""
    import logging.config

    logging.config.dictConfig(build_logging_config(config))


@contextmanager
def timed(
    logger: logging.Logger,
    event_name: str,
    message: Optional[str] = None,
    level: int = logging.INFO,
    **fields: Any,
) -> Iterator[Dict[str, Any]]:
    """Log one record with ``duration_ms`` and ``success`` when the block ends.

    ``message`` is used on success. On an exception an ERROR record
    ("<event_name> failed") with the stack trace is logged and the exception is
    re-raised. The yielded dict lets the block add fields::

        with timed(logger, "export", rows=0) as t:
            t["rows"] = do_export()
    """
    started = time.perf_counter()
    extra: Dict[str, Any] = dict(fields)
    try:
        yield extra
    except Exception:
        extra.update(
            event_name=f"{event_name}_failed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            success=False,
        )
        logger.error(f"{event_name} failed", exc_info=True, extra=extra)
        raise
    else:
        extra.update(
            event_name=f"{event_name}_completed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            success=True,
        )
        logger.log(level, message or f"{event_name} completed", extra=extra)
