"""Django middleware: one structured log record per HTTP request.

Captures method, URL, response code, duration, client IP, user agent, user and
session, and correlates everything logged during the request through a shared
``operation_id``. Honours an incoming W3C ``traceparent`` or ``X-Request-ID``
header and always returns ``X-Request-ID`` so the UI can quote it in bug reports.
"""
from __future__ import annotations

import logging
import re
import time

from . import payloads
from .config import get_config
from .context import log_context, new_operation_id

logger = logging.getLogger("app.http")

_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _correlation(request):
    """-> (operation_id, parent_id) from the incoming headers, or fresh ids."""
    match = _TRACEPARENT.match(request.META.get("HTTP_TRACEPARENT", "").strip().lower())
    if match:
        return match.group(1), match.group(2)
    supplied = request.META.get("HTTP_X_REQUEST_ID", "").strip()
    if supplied and len(supplied) <= 64 and re.fullmatch(r"[\w.\-]+", supplied):
        return supplied, ""
    return new_operation_id(), ""


def _user_and_session(request):
    user_id = session_id = ""
    try:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            user_id = user.get_username()
    except Exception:
        pass
    try:
        session = getattr(request, "session", None)
        if session is not None and session.session_key:
            session_id = session.session_key
    except Exception:
        pass
    return user_id, session_id


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.config = get_config()
        self.skip_paths = self.config.skip_paths

    def __call__(self, request):
        if any(request.path.startswith(p) for p in self.skip_paths):
            return self.get_response(request)

        operation_id, parent_id = _correlation(request)
        request.operation_id = operation_id
        request._log_request = self._capture_request(request)

        with log_context(
            operation_id=operation_id,
            parent_id=parent_id or None,
            http_method=request.method,
            client_ip=_client_ip(request),
        ):
            started = time.perf_counter()
            try:
                response = self.get_response(request)
            except Exception:
                # Normally Django converts exceptions to a 500 response before
                # they reach us (process_exception logs those); this is the
                # safety net for anything that escapes.
                self._log(request, 500, started, error=True)
                raise
            response["X-Request-ID"] = operation_id
            self._log(request, response.status_code, started, response=response)
            return response

    def process_exception(self, request, exception):
        if not hasattr(request, "operation_id"):
            return None
        logger.error(
            "Unhandled exception in %s %s: %s",
            request.method, request.path, exception,
            exc_info=exception,
            extra={"event_name": "http_exception", "url": request.get_full_path(),
                   **getattr(request, "_log_request", {})},
        )
        return None  # let Django build the 500 response

    def _capture_request(self, request) -> dict:
        """Request parameters + body (masked / truncated). Never raises."""
        if not self.config.http_bodies:
            return {}
        try:
            body, size = payloads.request_payload(request, self.config)
            return {
                "request_query": payloads.query_params(request, self.config),
                "request_body": body,
                "request_size": size,
            }
        except Exception:
            logger.debug("Could not capture request payload", exc_info=True)
            return {}

    def _capture_response(self, response) -> dict:
        if not self.config.http_bodies or response is None:
            return {}
        try:
            body, size = payloads.response_payload(response, self.config)
            return {"response_body": body, "response_size": size}
        except Exception:
            logger.debug("Could not capture response payload", exc_info=True)
            return {}

    def _log(self, request, status: int, started: float, error: bool = False, response=None):
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        match = getattr(request, "resolver_match", None)
        route = getattr(match, "route", None) or request.path
        user_id, session_id = _user_and_session(request)

        if status >= 500:
            level = logging.ERROR
        elif status >= 400:
            level = logging.WARNING
        else:
            level = logging.INFO

        logger.log(
            level,
            "%s %s -> %s (%.1f ms)",
            request.method, request.get_full_path(), status, duration_ms,
            extra={
                "event_name": "http_request",
                "operation_name": f"{request.method} {route}",
                "url": request.build_absolute_uri(),
                "result_code": status,
                "success": status < 400 and not error,
                "duration_ms": duration_ms,
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                "user_id": user_id or None,
                "session_id": session_id or None,
                **getattr(request, "_log_request", {}),
                **self._capture_response(response),
            },
        )
