"""Serve backend (Django) and prebuilt frontend (React dist) with Waitress.

Backend  -> http://DJANGO_HOST:DJANGO_PORT   (default 0.0.0.0:8000)
Frontend -> http://FRONTEND_HOST:FRONTEND_PORT (default 0.0.0.0:8080)

The frontend calls the API at http://<page-hostname>:8000, so keep the
backend on port 8000 unless the UI is rebuilt.
"""
import mimetypes
import os
import threading
from pathlib import Path

from waitress import serve

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "automation.settings")

from django.core.wsgi import get_wsgi_application  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = Path(
    os.environ.get("FRONTEND_DIR", BASE_DIR.parent.parent / "UI" / "my-react-flow-app" / "dist")
).resolve()


def frontend_app(environ, start_response):
    """Static file server for the React build, with SPA fallback to index.html."""
    if environ["REQUEST_METHOD"] not in ("GET", "HEAD"):
        start_response("405 Method Not Allowed", [("Allow", "GET, HEAD")])
        return [b""]

    rel = environ.get("PATH_INFO", "/").lstrip("/")
    target = (DIST_DIR / rel).resolve()
    # block path traversal; fall back to index.html for unknown / directory paths
    if DIST_DIR not in target.parents and target != DIST_DIR or not target.is_file():
        target = DIST_DIR / "index.html"
    if not target.is_file():
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"Frontend build not found. Check that UI/my-react-flow-app/dist exists."]

    ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    size = target.stat().st_size
    start_response("200 OK", [("Content-Type", ctype), ("Content-Length", str(size))])
    if environ["REQUEST_METHOD"] == "HEAD":
        return [b""]
    return _iter_file(target)


def _iter_file(path, chunk=64 * 1024):
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            yield data


if __name__ == "__main__":
    api_host = os.environ.get("DJANGO_HOST", "0.0.0.0")
    api_port = int(os.environ.get("DJANGO_PORT", "8000"))
    ui_host = os.environ.get("FRONTEND_HOST", "0.0.0.0")
    ui_port = int(os.environ.get("FRONTEND_PORT", "8080"))
    threads = int(os.environ.get("WAITRESS_THREADS", "16"))

    application = get_wsgi_application()

    print(f"Frontend: http://{ui_host}:{ui_port}/  (from {DIST_DIR})")
    threading.Thread(
        target=serve,
        args=(frontend_app,),
        kwargs=dict(host=ui_host, port=ui_port, threads=4),
        daemon=True,
    ).start()

    print(f"Backend:  http://{api_host}:{api_port}/  ({threads} threads)")
    serve(
        application,
        host=api_host,
        port=api_port,
        threads=threads,
        channel_timeout=300,
        cleanup_interval=30,
        max_request_body_size=1073741824,
    )
