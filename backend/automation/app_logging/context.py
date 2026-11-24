"""Request / operation scoped context that is stamped onto every log record.

Built on ``contextvars`` so it is correct for Waitress worker threads and
asyncio alike. Anything bound here shows up on each record logged inside the
``with log_context(...)`` block, without having to pass it to every call.

Well-known keys map onto dedicated columns (see ``schema.py``); any other key
ends up in the ``custom_dimensions`` JSON column.
"""
from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator

_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "app_logging_context", default={}
)


def new_operation_id() -> str:
    """32 hex chars - same shape as an Azure / W3C trace id."""
    return uuid.uuid4().hex


def new_span_id() -> str:
    """16 hex chars - same shape as a W3C span id."""
    return uuid.uuid4().hex[:16]


def get_context() -> Dict[str, Any]:
    return dict(_context.get())


def bind(**fields: Any) -> contextvars.Token:
    """Add fields to the current context. Returns a token for ``reset``."""
    merged = {**_context.get(), **{k: v for k, v in fields.items() if v is not None}}
    return _context.set(merged)


def reset(token: contextvars.Token) -> None:
    _context.reset(token)


@contextmanager
def log_context(**fields: Any) -> Iterator[Dict[str, Any]]:
    """Bind fields for the duration of a ``with`` block.

    Example::

        with log_context(rule_engine_id=5, rule_name="Nightly claims"):
            logger.info("starting")
    """
    token = bind(**fields)
    try:
        yield get_context()
    finally:
        reset(token)
