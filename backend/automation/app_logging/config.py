"""Configuration for the file-based logging module.

Everything is driven by environment variables (also picked up from the
backend ``.env`` file because ``settings.py`` loads it before this module is
used), so no code change is needed to switch format, folder or level.

=====================  ====================  =================================
Variable               Default               Meaning
=====================  ====================  =================================
APP_LOG_FORMAT         csv                   ``csv`` or ``flat`` (flat file)
APP_LOG_DIR            <backend>/logs        Folder the log files are written to
APP_LOG_LEVEL          INFO                  DEBUG / INFO / WARNING / ERROR / CRITICAL
APP_LOG_APP_NAME       umr-claims-automation Azure ``cloud_RoleName``
APP_LOG_ENVIRONMENT    development           dev / test / prod ...
APP_LOG_APP_VERSION    unknown               Azure ``application_Version``
APP_LOG_MAX_BYTES      52428800 (50 MB)      Roll over to a new file past this size (0 = never)
APP_LOG_RETENTION_DAYS 30                    Delete log files older than this (0 = keep all)
APP_LOG_CONSOLE        true                  Also echo records to the console
APP_LOG_SKIP_PATHS     /static/,/assets/,... Request paths the middleware ignores
APP_LOG_HTTP_BODIES    true                  Log API request/response parameters and bodies
APP_LOG_MAX_BODY_CHARS 8000                  Truncate each logged payload to this many chars
APP_LOG_REDACT_KEYS    (built-in list)       Extra comma-separated key names to mask
=====================  ====================  =================================
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

FORMAT_CSV = "csv"
FORMAT_FLAT = "flat"

_FORMAT_ALIASES = {
    "csv": FORMAT_CSV,
    "flat": FORMAT_FLAT,
    "flatfile": FORMAT_FLAT,
    "flat_file": FORMAT_FLAT,
    "text": FORMAT_FLAT,
    "txt": FORMAT_FLAT,
    "log": FORMAT_FLAT,
}

_FILE_EXTENSIONS = {FORMAT_CSV: ".csv", FORMAT_FLAT: ".log"}

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

DEFAULT_SKIP_PATHS = "/static/,/assets/,/favicon.ico"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError:
        _warn(f"{name}={raw!r} is not an integer; using {default}")
        return default


def _warn(message: str) -> None:
    print(f"[app_logging] {message}", file=sys.stderr)


@dataclass(frozen=True)
class LogConfig:
    app_name: str
    environment: str
    app_version: str
    log_dir: Path
    file_format: str
    level: str
    max_bytes: int
    retention_days: int
    console: bool
    skip_paths: Tuple[str, ...]
    http_bodies: bool = True
    max_body_chars: int = 8000
    redact_keys: Tuple[str, ...] = ()

    @property
    def file_extension(self) -> str:
        return _FILE_EXTENSIONS[self.file_format]

    @property
    def file_prefix(self) -> str:
        """Safe-for-filesystem version of the app name."""
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in self.app_name)
        return safe or "app"

    @classmethod
    def from_env(cls, base_dir: Optional[Path] = None) -> "LogConfig":
        base = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent

        raw_format = os.environ.get("APP_LOG_FORMAT", FORMAT_CSV).strip().lower()
        file_format = _FORMAT_ALIASES.get(raw_format)
        if file_format is None:
            _warn(f"APP_LOG_FORMAT={raw_format!r} is not supported; using 'csv'")
            file_format = FORMAT_CSV

        level = os.environ.get("APP_LOG_LEVEL", "INFO").strip().upper()
        if level not in _VALID_LEVELS:
            _warn(f"APP_LOG_LEVEL={level!r} is not valid; using 'INFO'")
            level = "INFO"

        log_dir = Path(os.environ.get("APP_LOG_DIR") or (base / "logs"))
        if not log_dir.is_absolute():
            log_dir = base / log_dir

        skip_raw = os.environ.get("APP_LOG_SKIP_PATHS", DEFAULT_SKIP_PATHS)
        skip_paths = tuple(p.strip() for p in skip_raw.split(",") if p.strip())

        return cls(
            app_name=os.environ.get("APP_LOG_APP_NAME", "umr-claims-automation").strip(),
            environment=os.environ.get("APP_LOG_ENVIRONMENT", "development").strip(),
            app_version=os.environ.get("APP_LOG_APP_VERSION", "unknown").strip(),
            log_dir=log_dir,
            file_format=file_format,
            level=level,
            max_bytes=_env_int("APP_LOG_MAX_BYTES", 50 * 1024 * 1024),
            retention_days=_env_int("APP_LOG_RETENTION_DAYS", 30),
            console=_env_bool("APP_LOG_CONSOLE", True),
            skip_paths=skip_paths,
            http_bodies=_env_bool("APP_LOG_HTTP_BODIES", True),
            max_body_chars=max(0, _env_int("APP_LOG_MAX_BODY_CHARS", 8000)),
            redact_keys=tuple(
                k.strip().lower()
                for k in os.environ.get("APP_LOG_REDACT_KEYS", "").split(",")
                if k.strip()
            ),
        )


_cached: Optional[LogConfig] = None


def get_config(reload: bool = False) -> LogConfig:
    """Process-wide config, read from the environment on first use."""
    global _cached
    if _cached is None or reload:
        _cached = LogConfig.from_env()
    return _cached
