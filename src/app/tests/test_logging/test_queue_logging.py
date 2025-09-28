# src/app/tests/test_logging/test_queue_logging.py
import logging
import time
from types import SimpleNamespace
from pathlib import Path

from app.core.logging.builder import setup_logging, stop_queue_logging
from app.core.logging.filters import set_request_id

def make_test_settings(tmp_path: Path):
    # Build a lightweight settings object for tests (duck-typed)
    s = SimpleNamespace()
    s.ENV = "testing"
    s.LOG_LEVEL = "DEBUG"
    s.LOG_FORMAT = "json"
    s.LOG_TO_STDOUT = False     # write to files, not stdout
    s.LOG_DIR = tmp_path        # Path-like or str
    s.LOG_MAX_BYTES = 1_000_000
    s.LOG_BACKUP_COUNT = 1
    s.ENABLE_SQL_LOGGING = False
    s.LOG_USE_QUEUE = True      # enable queue for the test
    return s

def test_queue_listener_writes_file(tmp_path):
    # Ensure previous listener (if any) is stopped before test starts
    stop_queue_logging()

    settings = make_test_settings(tmp_path)

    # Initialize logging (this will create handlers, start QueueListener, etc.)
    setup_logging(settings)

    logger = logging.getLogger("test.queue")

    # Attach a request id to be included in logs
    set_request_id("test-req-1")

    # Emit logs quickly
    for i in range(10):
        logger.info("test message %d", i, extra={"iteration": i})

    # Give listener a small moment (not strictly necessary if we stop it)
    time.sleep(0.05)

    # Stop and flush the queue listener — important to ensure logs are written
    stop_queue_logging()

    # Assert the file exists and contains the logs
    app_log = Path(settings.LOG_DIR) / "app.log"
    assert app_log.exists(), "app.log should exist after logging"
    text = app_log.read_text()
    assert "test message 0" in text
    # extras may appear as JSON fields depending on JsonFormatter; check presence of 'iteration'
    assert "iteration" in text
    assert "test-req-1" in text  # request_id present
