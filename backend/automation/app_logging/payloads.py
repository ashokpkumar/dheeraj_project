"""Build safe, size-limited log values for HTTP request / response payloads.

* Sensitive keys (password, token, secret, authorization, ...) are masked at
  any nesting depth - in JSON bodies, form fields and the query string.
* Values are truncated to ``APP_LOG_MAX_BODY_CHARS``.
* Only text-like bodies are logged. Multipart uploads log field names and file
  names/sizes (never file content); binary and streaming responses log only a
  placeholder and the size.
"""
from __future__ import annotations

import json
from typing import Any, Tuple
from urllib.parse import parse_qsl

from .config import LogConfig

REDACTED = "***REDACTED***"

_DEFAULT_SENSITIVE = (
    "password", "passwd", "pwd", "secret", "token", "authorization", "auth",
    "api_key", "apikey", "access_key", "private_key", "credential", "cookie",
    "session", "csrf", "ssn", "card_number", "cvv",
)

# Do not buffer request bodies larger than this just to log them.
_MAX_READ_BYTES = 1024 * 1024

_TEXT_TYPES = ("json", "text", "xml", "x-www-form-urlencoded", "javascript", "csv")


def _sensitive(config: LogConfig):
    keys = _DEFAULT_SENSITIVE + tuple(config.redact_keys)
    return lambda name: any(k in str(name).lower() for k in keys)


def redact(value: Any, is_sensitive) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED if is_sensitive(k) else redact(v, is_sensitive))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v, is_sensitive) for v in value]
    return value


def _dump(value: Any, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(
        value, default=str, ensure_ascii=False
    )
    if limit and len(text) > limit:
        return text[:limit] + f"...[truncated {len(text) - limit} chars]"
    return text


def _is_text(content_type: str) -> bool:
    ct = (content_type or "").lower()
    return not ct or any(t in ct for t in _TEXT_TYPES)


def query_params(request, config: LogConfig) -> str:
    qs = request.META.get("QUERY_STRING", "")
    if not qs:
        return ""
    params: dict = {}
    for k, v in parse_qsl(qs, keep_blank_values=True):
        if k in params:
            params[k] = (params[k] if isinstance(params[k], list) else [params[k]]) + [v]
        else:
            params[k] = v
    return _dump(redact(params, _sensitive(config)), config.max_body_chars)


def request_payload(request, config: LogConfig) -> Tuple[str, int]:
    """-> (logged body text, size in bytes)."""
    try:
        size = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        size = 0
    if size == 0 and request.method in ("GET", "HEAD", "OPTIONS", "DELETE"):
        return "", 0

    content_type = request.META.get("CONTENT_TYPE", "")
    is_sensitive = _sensitive(config)

    if "multipart/form-data" in content_type:
        # request.POST / FILES parse the stream; file contents are never logged.
        summary = {
            "fields": redact(
                {k: (v if len(v) > 1 else v[0])
                 for k, v in ((k, request.POST.getlist(k)) for k in request.POST)},
                is_sensitive,
            ),
            "files": [
                {"field": k, "name": f.name, "size": f.size, "content_type": f.content_type}
                for k in request.FILES for f in request.FILES.getlist(k)
            ],
        }
        return _dump(summary, config.max_body_chars), size

    if not _is_text(content_type):
        return f"[{content_type or 'binary'} body not logged]", size
    if size > _MAX_READ_BYTES:
        return f"[body too large to log: {size} bytes]", size

    try:
        raw = request.body
    except Exception:
        return "[body unreadable]", size
    size = size or len(raw)
    text = raw.decode("utf-8", errors="replace")

    if "json" in content_type:
        try:
            return _dump(redact(json.loads(text), is_sensitive), config.max_body_chars), size
        except ValueError:
            pass  # malformed JSON: log as raw text below
    elif "x-www-form-urlencoded" in content_type:
        form = dict(parse_qsl(text, keep_blank_values=True))
        return _dump(redact(form, is_sensitive), config.max_body_chars), size
    return _dump(text, config.max_body_chars), size


def response_payload(response, config: LogConfig) -> Tuple[str, int]:
    if getattr(response, "streaming", False):
        disposition = response.get("Content-Disposition", "")
        return f"[streaming response{': ' + disposition if disposition else ''}]", 0

    content_type = response.get("Content-Type", "")
    try:
        raw = response.content
    except Exception:
        return "", 0
    size = len(raw)
    if not size:
        return "", 0
    if not _is_text(content_type):
        return f"[{content_type} body not logged]", size

    limit = config.max_body_chars
    if "json" in content_type:
        if size > _MAX_READ_BYTES:
            # Too big to parse and mask safely: log nothing rather than leak.
            return f"[json body too large to log: {size} bytes]", size
        try:
            return _dump(redact(json.loads(raw), _sensitive(config)), limit), size
        except ValueError:
            pass
    return _dump(raw[: limit * 4 if limit else None].decode("utf-8", errors="replace"), limit), size
