# src/app/tests/test_formatters.py
import logging
import json
from app.core.logging.formatters import JsonFormatter

def make_record():
    # create a LogRecord that simulates formatting with args
    return logging.LogRecord("app", logging.INFO, __file__, 10, "hello %s", ("tester",), None)

def test_json_formatter_basic_fields(tmp_path):
    rec = make_record()
    # attach an extra (simulate extra param)
    rec.custom = "value"
    # attach request_id
    rec.request_id = "req-1"
    fmt = JsonFormatter(env="testing", service="svc")
    out = fmt.format(rec)
    data = json.loads(out)
    # core assertions
    assert data["message"] == "hello tester"
    assert data["level"] == "INFO"
    assert data["service"] == "svc"
    assert data["env"] == "testing"
    assert "timestamp" in data
    assert data["request_id"] == "req-1"
    assert data["custom"] == "value"
    assert "version" in data  # PROJECT_VERSION is present

def test_json_formatter_non_serializable_extra():
    rec = make_record()
    class X: 
        def __repr__(self): 
            return "<X>"
    rec.obj = X()
    fmt = JsonFormatter(env="dev", service="svc")
    out = fmt.format(rec)
    data = json.loads(out)
    # non-serializable obj should be stringified
    assert isinstance(data["obj"], str)
