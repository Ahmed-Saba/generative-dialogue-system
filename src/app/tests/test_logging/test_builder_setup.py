# src/app/tests/test_builder_setup.py
import logging
import os
from pathlib import Path
from app.core.logging.builder import make_dict_config, setup_logging
# Create a minimal Settings-like object for testing
class DummySettings:
    LOG_FORMAT = "json"
    LOG_LEVEL = "INFO"
    LOG_TO_STDOUT = False
    LOG_DIR = None  # will be set in test
    LOG_MAX_BYTES = 1000
    LOG_BACKUP_COUNT = 1
    ENV = "development"
    ENABLE_SQL_LOGGING = False

def test_make_dict_config_contains_handlers(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.LOG_DIR = tmp_path
    cfg = make_dict_config(settings)
    assert "handlers" in cfg
    assert "console" in cfg["handlers"]
    # In development we expect file handlers
    assert "file" in cfg["handlers"]
    assert "error_file" in cfg["handlers"]
    assert "formatters" in cfg
    assert "json" in cfg["formatters"]

def test_setup_logging_creates_log_dir(tmp_path, monkeypatch):
    settings = DummySettings()
    settings.LOG_DIR = tmp_path / "logs"
    # ensure DIR does not exist
    assert not settings.LOG_DIR.exists()
    setup_logging(settings)
    # setup should create log dir
    assert settings.LOG_DIR.exists()
    # ensure root logger has at least one handler
    root = logging.getLogger()
    assert any(True for _ in root.handlers)
