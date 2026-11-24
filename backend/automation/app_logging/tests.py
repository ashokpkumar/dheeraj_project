"""Run with:  python -m unittest app_logging.tests -v   (from backend/automation)"""
import csv
import json
import logging
import multiprocessing
import tempfile
import unittest
from pathlib import Path

from app_logging import COLUMNS, log_context, timed
from app_logging.config import FORMAT_CSV, FORMAT_FLAT, LogConfig
from app_logging.handlers import SharedFileHandler


def make_config(tmp, fmt=FORMAT_CSV, **overrides):
    base = dict(
        app_name="test-app", environment="test", app_version="1.2.3",
        log_dir=Path(tmp), file_format=fmt, level="DEBUG",
        max_bytes=0, retention_days=0, console=False, skip_paths=(),
    )
    base.update(overrides)
    return LogConfig(**base)


def make_logger(name, config):
    logger = logging.getLogger(name)
    logger.handlers = [SharedFileHandler(config)]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


def read_rows(tmp):
    rows = []
    for f in sorted(Path(tmp).glob("*.csv")):
        with open(f, newline="", encoding="utf-8") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def _child_writer(tmp, n):
    logger = make_logger("child", make_config(tmp))
    for i in range(n):
        logger.info("child message %s", i)


class CsvTests(unittest.TestCase):
    def test_header_columns_and_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = make_logger("t.csv", make_config(tmp))
            with log_context(operation_id="op1", rule_engine_id=7):
                logger.warning(
                    "hello, \"world\"\nline2",
                    extra={"event_name": "e", "result_code": 404, "duration_ms": 12.5, "rows": 3},
                )
            rows = read_rows(tmp)
            self.assertEqual(len(rows), 1)
            r = rows[0]
            self.assertEqual(list(r.keys()), COLUMNS)
            self.assertEqual(r["level"], "WARNING")
            self.assertEqual(r["severity_level"], "2")
            self.assertEqual(r["app_name"], "test-app")
            self.assertEqual(r["operation_id"], "op1")
            self.assertEqual(r["rule_engine_id"], "7")
            self.assertEqual(r["result_code"], "404")
            self.assertEqual(r["success"], "false")
            self.assertEqual(r["message"], 'hello, "world"\nline2')
            self.assertEqual(json.loads(r["custom_dimensions"]), {"rows": 3})
            self.assertTrue(r["timestamp"].endswith("Z"))

    def test_exception_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = make_logger("t.exc", make_config(tmp))
            try:
                1 / 0
            except ZeroDivisionError:
                logger.exception("boom")
            r = read_rows(tmp)[0]
            self.assertEqual(r["exception_type"], "ZeroDivisionError")
            self.assertIn("Traceback", r["stack_trace"])
            self.assertEqual(r["success"], "false")

    def test_timed_success_and_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = make_logger("t.timed", make_config(tmp))
            with timed(logger, "job"):
                pass
            with self.assertRaises(ValueError):
                with timed(logger, "job"):
                    raise ValueError("x")
            ok, bad = read_rows(tmp)
            self.assertEqual((ok["event_name"], ok["success"]), ("job_completed", "true"))
            self.assertEqual((bad["event_name"], bad["success"]), ("job_failed", "false"))
            self.assertNotEqual(ok["duration_ms"], "")

    def test_size_rollover_writes_header_per_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = make_logger("t.roll", make_config(tmp, max_bytes=2000))
            for i in range(30):
                logger.info("row %s %s", i, "x" * 50)
            files = sorted(Path(tmp).glob("*.csv"))
            self.assertGreater(len(files), 1)
            for f in files:
                self.assertTrue(f.read_text(encoding="utf-8").startswith("timestamp,"))
            self.assertEqual(len(read_rows(tmp)), 30)

    def test_multiprocess_writes_do_not_interleave(self):
        with tempfile.TemporaryDirectory() as tmp:
            procs = [multiprocessing.Process(target=_child_writer, args=(tmp, 40)) for _ in range(4)]
            for p in procs:
                p.start()
            for p in procs:
                p.join()
            rows = read_rows(tmp)
            self.assertEqual(len(rows), 160)
            self.assertTrue(all(r["message"].startswith("child message") for r in rows))
            self.assertEqual(len({r["process_id"] for r in rows}), 4)


class DailyFileTests(unittest.TestCase):
    def test_new_file_each_day_with_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            handler = SharedFileHandler(make_config(tmp))
            from datetime import datetime, timezone
            for day in ("2026-11-24", "2026-11-25"):
                rec = logging.LogRecord("t.day", logging.INFO, __file__, 1, "msg " + day, None, None)
                rec.created = datetime.fromisoformat(day + "T01:00:00+00:00").timestamp()
                handler.emit(rec)
            names = sorted(f.name for f in Path(tmp).glob("*.csv"))
            self.assertEqual(names, ["test-app-2026-11-24.csv", "test-app-2026-11-25.csv"])
            for f in Path(tmp).glob("*.csv"):
                self.assertTrue(f.read_text(encoding="utf-8").startswith("timestamp,"))


class PayloadTests(unittest.TestCase):
    def test_redaction_is_recursive_and_case_insensitive(self):
        from app_logging.payloads import REDACTED, redact, _sensitive
        cfg = make_config(tempfile.gettempdir(), redact_keys=("ssn_full",))
        out = redact({"user": "a", "Password": "x", "nested": [{"apiToken": "t", "ok": 1}],
                      "ssn_full": "1"}, _sensitive(cfg))
        self.assertEqual(out["Password"], REDACTED)
        self.assertEqual(out["nested"][0]["apiToken"], REDACTED)
        self.assertEqual(out["ssn_full"], REDACTED)
        self.assertEqual((out["user"], out["nested"][0]["ok"]), ("a", 1))

    def test_truncation(self):
        from app_logging.payloads import _dump
        self.assertIn("[truncated", _dump("x" * 50, 10))


try:
    import django  # noqa: F401
    HAVE_DJANGO = True
except ImportError:
    HAVE_DJANGO = False


@unittest.skipUnless(HAVE_DJANGO, "Django not installed")
class MiddlewareTests(unittest.TestCase):
    def test_request_and_response_payloads_logged(self):
        import json as _json
        from django.conf import settings
        from django.http import HttpResponse, JsonResponse
        from django.test import Client, RequestFactory
        from app_logging.middleware import RequestLoggingMiddleware

        with tempfile.TemporaryDirectory() as tmp:
            cfg = make_config(tmp, skip_paths=("/static/",))
            if not settings.configured:
                settings.configure(ALLOWED_HOSTS=["*"], SECRET_KEY="x")
                django.setup()
            logging.getLogger("app.http").handlers = [SharedFileHandler(cfg)]
            logging.getLogger("app.http").setLevel(logging.DEBUG)
            logging.getLogger("app.http").propagate = False

            def view(request):
                if request.method == "POST":
                    _json.loads(request.body)  # body must still be readable after logging
                return JsonResponse({"ok": True, "token": "abc", "items": [1, 2]}, status=201)

            mw = RequestLoggingMiddleware(view)
            mw.config = cfg
            mw.skip_paths = cfg.skip_paths
            rf = RequestFactory()
            resp = mw(rf.post("/api/x/?page=2&api_key=zzz",
                              data=_json.dumps({"rule_name": "r1", "password": "hunter2"}),
                              content_type="application/json"))
            self.assertEqual(resp.status_code, 201)
            self.assertTrue(resp["X-Request-ID"])
            mw(rf.get("/static/app.js"))  # skipped path

            rows = read_rows(tmp)
            self.assertEqual(len(rows), 1)
            r = rows[0]
            self.assertEqual(r["result_code"], "201")
            self.assertEqual(_json.loads(r["request_query"]), {"page": "2", "api_key": "***REDACTED***"})
            body = _json.loads(r["request_body"])
            self.assertEqual((body["rule_name"], body["password"]), ("r1", "***REDACTED***"))
            out = _json.loads(r["response_body"])
            self.assertEqual((out["ok"], out["token"]), (True, "***REDACTED***"))
            self.assertNotIn("hunter2", r["request_body"])
            self.assertGreater(int(r["request_size"]), 0)
            self.assertGreater(int(r["response_size"]), 0)


class FlatFileTests(unittest.TestCase):
    def test_flat_line_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = make_logger("t.flat", make_config(tmp, FORMAT_FLAT))
            logger.error("two\nlines here", extra={"result_code": 500, "event_name": "x"})
            files = list(Path(tmp).glob("*.log"))
            self.assertEqual(len(files), 1)
            lines = files[0].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertIn("level=ERROR", lines[0])
            self.assertIn('message="two\\nlines here"', lines[0])
            self.assertIn("result_code=500", lines[0])
            self.assertNotIn("stack_trace=", lines[0])


if __name__ == "__main__":
    unittest.main()
