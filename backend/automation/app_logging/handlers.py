"""Multi-process-safe, date + size rolling file handler.

Why not ``RotatingFileHandler``? The rule executor spawns child processes and
the scheduler runs as its own process, all writing the same log. Renaming
files on rotation breaks on Windows when another process has the file open.
Instead this handler:

* names files by date and a roll index: ``<app>-2026-11-24.csv``,
  ``<app>-2026-11-24.1.csv`` ... (never renames anything);
* takes an OS-level lock (``msvcrt`` / ``fcntl``) around every write, so rows
  from different processes never interleave;
* writes the CSV header whenever it creates a new file;
* prunes files older than ``APP_LOG_RETENTION_DAYS`` once a day.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import LogConfig, get_config
from .formatters import ConsoleFormatter, make_formatter

try:  # Windows
    import msvcrt

    def _lock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)

except ImportError:  # POSIX
    import fcntl

    def _lock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


_LOCK_TIMEOUT_SECONDS = 10.0


class _CrossProcessLock:
    """Advisory lock on ``<log_dir>/.app_logging.lock``."""

    def __init__(self, path: Path):
        self.path = path
        self.fh = None
        self.locked = False

    def __enter__(self):
        self.fh = open(self.path, "a+b")
        if self.fh.tell() == 0 and os.path.getsize(self.path) == 0:
            self.fh.write(b"\0")
            self.fh.flush()
        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                _lock(self.fh)
                self.locked = True
                break
            except OSError:
                if time.monotonic() > deadline:
                    # Better to risk an interleaved row than to drop the log.
                    break
                time.sleep(0.005)
        return self

    def __exit__(self, *exc):
        try:
            if self.locked:
                _unlock(self.fh)
        finally:
            self.fh.close()


class SharedFileHandler(logging.Handler):
    def __init__(self, config: Optional[LogConfig] = None):
        super().__init__()
        self.config = config or get_config()
        self.setFormatter(make_formatter(self.config))
        self.log_dir = self.config.log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.log_dir / ".app_logging.lock"
        self._day: Optional[str] = None
        self._index = 0
        self._pruned_day: Optional[str] = None

    # -- file naming -------------------------------------------------------
    def _path_for(self, day: str, index: int) -> Path:
        suffix = f".{index}" if index else ""
        return self.log_dir / f"{self.config.file_prefix}-{day}{suffix}{self.config.file_extension}"

    def _current_path(self, day: str) -> Path:
        if day != self._day:
            self._day, self._index = day, 0
        limit = self.config.max_bytes
        while True:
            path = self._path_for(day, self._index)
            if limit <= 0:
                return path
            try:
                if path.stat().st_size < limit:
                    return path
            except FileNotFoundError:
                return path
            self._index += 1

    # -- retention ---------------------------------------------------------
    def _prune(self, day: str) -> None:
        if self._pruned_day == day or self.config.retention_days <= 0:
            return
        self._pruned_day = day
        cutoff = time.time() - self.config.retention_days * 86400
        prefix, ext = f"{self.config.file_prefix}-", self.config.file_extension
        try:
            for entry in self.log_dir.iterdir():
                if entry.name.startswith(prefix) and entry.name.endswith(ext):
                    try:
                        if entry.stat().st_mtime < cutoff:
                            entry.unlink()
                    except OSError:
                        pass  # in use by another process; next day's pass gets it
        except OSError:
            pass

    # -- logging.Handler ---------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            day = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d")
            header = self.formatter.header()
            with _CrossProcessLock(self._lock_path):
                path = self._current_path(day)
                is_new = (not path.exists()) or path.stat().st_size == 0
                # newline="" => no \n -> \r\n translation; formatters own line endings.
                with open(path, "a", encoding="utf-8", newline="") as fh:
                    if is_new and header:
                        fh.write(header)
                    fh.write(line)
            self._prune(day)
        except Exception:
            self.handleError(record)


def build_file_handler() -> logging.Handler:
    """Factory used by ``dictConfig`` (``"()": "app_logging.handlers.build_file_handler"``)."""
    return SharedFileHandler(get_config())


def build_console_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(ConsoleFormatter())
    return handler
