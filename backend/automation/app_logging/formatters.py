"""CSV and flat-file formatters.

* ``CsvFormatter``   - one RFC-4180 CSV row per record, fixed columns,
                       header row written by the handler at the top of each file.
* ``FlatFileFormatter`` - one ``key=value`` (logfmt style) line per record.
                       Empty fields are omitted so lines stay short; embedded
                       newlines are escaped so every record is exactly one line.
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Optional

from .config import FORMAT_CSV, LogConfig
from .schema import COLUMNS, build_row


class _BaseFormatter(logging.Formatter):
    def __init__(self, config: LogConfig):
        super().__init__()
        self.config = config

    def header(self) -> Optional[str]:
        return None


class CsvFormatter(_BaseFormatter):
    LINE_TERMINATOR = "\r\n"

    def header(self) -> str:
        buf = io.StringIO()
        csv.writer(buf, lineterminator=self.LINE_TERMINATOR).writerow(COLUMNS)
        return buf.getvalue()

    def format(self, record: logging.LogRecord) -> str:
        row = build_row(record, self.config)
        buf = io.StringIO()
        csv.writer(buf, lineterminator=self.LINE_TERMINATOR).writerow(
            [row[c] for c in COLUMNS]
        )
        return buf.getvalue()


class FlatFileFormatter(_BaseFormatter):
    LINE_TERMINATOR = "\n"

    @staticmethod
    def _escape(value: str) -> str:
        value = value.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")
        if value == "" or any(c in value for c in ' ="\t'):
            value = '"' + value.replace('"', '\\"') + '"'
        return value

    def format(self, record: logging.LogRecord) -> str:
        row = build_row(record, self.config)
        parts = [f"{col}={self._escape(row[col])}" for col in COLUMNS if row[col] != ""]
        return " ".join(parts) + self.LINE_TERMINATOR


class ConsoleFormatter(logging.Formatter):
    """Short human-readable line for the console."""

    def __init__(self):
        super().__init__(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s", "%H:%M:%S"
        )


def make_formatter(config: LogConfig) -> _BaseFormatter:
    return CsvFormatter(config) if config.file_format == FORMAT_CSV else FlatFileFormatter(config)
