# src/app/tests/test_filters.py
import logging
from app.core.logging.filters import RequestIdFilter, set_request_id, get_request_id

def make_record():
    # name, level, pathname, lineno, msg, args, exc_info
    return logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("world",), None)

def test_request_id_filter_defaults_to_dash():
    rec = make_record()
    # ensure no request id set in context
    set_request_id(None)
    f = RequestIdFilter()
    assert f.filter(rec) is True
    assert hasattr(rec, "request_id")
    assert rec.request_id == "-"  # fallback sentinel

def test_request_id_filter_uses_contextvar(monkeypatch):
    rec = make_record()
    set_request_id("abc-123")
    f = RequestIdFilter()
    f.filter(rec)
    assert rec.request_id == "abc-123"

def test_request_id_filter_respects_record_extra():
    rec = make_record()
    rec.request_id = "explicit"
    set_request_id("context-id")
    f = RequestIdFilter()
    f.filter(rec)
    # record.request_id should keep explicit value (respect extra)
    assert rec.request_id == "explicit"
