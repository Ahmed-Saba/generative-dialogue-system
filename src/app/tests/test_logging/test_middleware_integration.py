# src/app/tests/test_logging/test_middleware_integration.py
import json
import logging
from fastapi import FastAPI
from starlette.testclient import TestClient
from app.core.logging.builder import setup_logging
from app.core.logging.middleware import RequestIDMiddleware

def test_request_id_in_response_and_logs_stdout(tmp_path, capsys):
    class S:
        LOG_FORMAT = "json"
        LOG_LEVEL = "INFO"
        LOG_TO_STDOUT = True
        LOG_DIR = tmp_path / "logs"
        LOG_MAX_BYTES = 1000
        LOG_BACKUP_COUNT = 1
        ENV = "production"
        ENABLE_SQL_LOGGING = False

    settings = S()
    setup_logging(settings)

    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/hello")
    def hello():
        logging.getLogger("app").info("handling hello")
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/hello")
    assert resp.status_code == 200

    rid = resp.headers.get("X-Request-ID")
    assert rid is not None

    # Capture the text written to stdout/stderr by the logging handlers
    captured = capsys.readouterr()
    stderr = captured.err.strip()
    assert stderr, "Expected logs on stderr/stdout but nothing was captured."

    # Each line is a JSON object (because LOG_FORMAT=json). Iterate and parse lines.
    found = False
    for line in stderr.splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("request_id") == rid:
            found = True
            break

    assert found, "No log line in stderr with matching request_id"
