"""Production WSGI entry point (Waitress - pure Python, Windows-native).

Usage:  python serve.py
Env:    DJANGO_HOST (default 0.0.0.0), DJANGO_PORT (default 8000),
        WAITRESS_THREADS (default 16)
"""
import os

from waitress import serve

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "automation.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()

from app_logging import get_logger  # noqa: E402

logger = get_logger("server")

if __name__ == "__main__":
    host = os.environ.get("DJANGO_HOST", "0.0.0.0")
    port = int(os.environ.get("DJANGO_PORT", "8000"))
    threads = int(os.environ.get("WAITRESS_THREADS", "16"))
    print(f"Serving with Waitress on http://{host}:{port}/ ({threads} threads)")
    logger.info("Backend starting on http://%s:%s/ (%s threads)", host, port, threads,
                extra={"event_name": "server_starting", "host_bind": host, "port": port, "threads": threads})
    serve(
        application,
        host=host,
        port=port,
        threads=threads,
        channel_timeout=300,      # long-running rule executions
        cleanup_interval=30,
        max_request_body_size=1073741824,  # 1 GB uploads (Excel/CSV)
    )
