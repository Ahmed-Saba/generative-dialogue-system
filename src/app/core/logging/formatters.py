# src/app/core/logging/formatters.py

"""
Custom logging formatters for the application.

This module provides two formatters used by the logging system:

  - JsonFormatter: emits structured JSON logs suitable for ingestion by log
    collectors (ELK, Fluentd, CloudWatch, etc.). It is designed to be safe
    (converts non-serializable fields to strings), include useful observability
    fields (service, env, version, request_id), and be configurable via kwargs.

  - ColorFormatter: a human-friendly, ANSI-colored formatter intended for
    local development consoles. It produces compact, readable lines that
    highlight the level and include a request id when available.

Why separate formatters?
  - Production systems typically want structured logs (JSON) so fields can be
    queried and visualized. JSON is machine-friendly but not human-friendly.
  - During development, readable colored logs speed debugging; they are printed
    to terminals and not usually ingested into centralized systems.
  - Both formatters share the same logging record model; the builder (dictConfig)
    will select which formatter to use based on environment and settings.

How to use:
  - When constructing dictConfig (see builder.py), register these formatters and
    (for JsonFormatter) pass `env` and `service` as kwargs in the config. Example
    dictConfig fragment:

    # from .formatters import JsonFormatter, ColorFormatter
    formatters = {
        "standard": {
            "()": ColorFormatter
            if settings.ENV == "development" and settings.LOG_FORMAT == "text"
            else logging.Formatter,
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s",
        },
        "json": {
            "()": JsonFormatter,
            "env": settings.ENV,
            "service": "gds-api",
        },
    }

Security & performance notes:
  - Avoid logging sensitive data (passwords, tokens, PII). Formatters will include 
    whatever is passed in `extra` — sanitize at call sites or implement a filter.
  - JsonFormatter performs JSON serialization and may call `str()` on complex objects;
    this has a cost but is acceptable for typical web apps. For very high-throughput
    systems consider a dedicated logging pipeline or faster libraries (e.g., ujson).
"""

import json
import logging
from typing import Any
from logging import LogRecord
from app.utils.logging import get_project_version

PROJECT_VERSION = get_project_version()


class JsonFormatter(logging.Formatter):
    """
    Structured JSON formatter.

    Responsibilities:
      - Build a JSON object containing standard log fields (timestamp, level,
        logger name, message, pathname, lineno) plus observability fields
        (service, env, version, request_id).
      - Include exception stack information if present (exc_info, stack_info).
      - Include any `extra` keys provided when logging (via logger.info(..., extra={...})).
      - Safely convert non-JSON-serializable extras to strings.

    Construction:
      - env: environment name (e.g., "development" | "production"); optional.
      - service: logical service name to include in logs (defaults to "gds-api").
      - datefmt: optional date format passed to logging.Formatter (used by formatTime).

    Usage example (programmatic):
      formatter = JsonFormatter(env="production", service="gds-api")
      handler.setFormatter(formatter)

    Important implementation details:
      - self.formatTime(record, self.datefmt) is used to produce the timestamp so
        the underlying logging.Formatter datefmt semantics are preserved.
      - We use json.dumps(..., default=str) as a final fallback to ensure the
        formatter never raises on non-serializable objects.
      - request_id is attached by a RequestIdFilter or middleware; if missing we
        emit "-" as a sentinel.
    """

    def __init__(self, *, env: str | None = None, service: str = "gds-api", datefmt: str | None = None):
        # Call the base class constructor to ensure date formatting behavior is consistent.
        super().__init__(datefmt=datefmt)
        # Store env/service on the instance so they are constant for all logs.
        self.env = env
        self.service = service

    def format(self, record: LogRecord) -> str:
        """
        Format a LogRecord into a JSON string.

        Steps:
          1. Build the canonical set of fields for structured logs.
          2. Add exception and stack info if present.
          3. Collect extras (attributes attached to the LogRecord via `extra={...}`).
          4. Convert any non-serializable extras to strings.
          5. Serialize the resulting dict to a JSON string and return it.

        Note: This method must never raise. Any conversion/parsing errors are caught
        by the use of `default=str` and by prior try/except when converting extras.
        """
        # 1) Base fields commonly useful for observability.
        log_record: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),    # formatted message with % formatting applied
            "pathname": record.pathname,       # file path where the logging call was made
            "lineno": record.lineno,           # line number in the source file
            "request_id": getattr(record, "request_id", "-"),
            "service": self.service,
            "env": self.env,
            "version": PROJECT_VERSION,
        }

        # 2) Exception and stack information (if provided by the logging call).
        #    formatException and formatStack come from logging.Formatter base class.
        if record.exc_info:
            # formatException returns a string containing the traceback.
            log_record["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            # formatStack accepts a stack_info text and returns a formatted string.
            log_record["stack_info"] = self.formatStack(record.stack_info)

        # 3) Capture extras: any attribute on the record that is not already part
        #    of our canonical fields and does not begin with '_' (private).
        #    We also exclude typical logging attributes to avoid duplication.
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in log_record and not k.startswith("_") and k not in ("args", "msg", "levelname", "name")
        }

        # 4) Safely convert extras: attempt to JSON-serialize each extra; if it fails,
        #    fallback to str(v). This avoids ValueError/TypeError during dumps.
        for k, v in extras.items():
            try:
                # A cheap check to let simple values pass through unchanged.
                json.dumps(v)
                log_record[k] = v
            except Exception:
                # Fall back to a string representation for non-serializable values.
                # This is safer than letting the whole logging call fail.
                log_record[k] = str(v)

        # 5) Serialize and return the JSON string.
        #    - ensure_ascii=False preserves unicode characters in logs (recommended).
        #    - default=str is an additional safety net for nested non-serializable objects.
        return json.dumps(log_record, ensure_ascii=False, default=str)


class ColorFormatter(logging.Formatter):
    """
    Development-friendly colored formatter.

    Responsibilities:
      - Produce concise, readable log lines for interactive terminals.
      - Highlight level using ANSI color codes so issues jump out during debugging.
      - Include request_id if present so developers can correlate logs to a request.
      - Include exception traceback inline when exc_info is set.

    Construction:
      - fmt: optional format string (same semantics as logging.Formatter).
      - datefmt: optional date format string.

    Notes:
      - This formatter is intended for stdout/stderr in developer machines or CI
        where colored output is helpful. Avoid using it for structured production logs.
      - ANSI codes may not render in all consoles (e.g., Windows without ANSI support).
        In such cases, colors will appear as escape sequences; you can wrap with a
        small helper to disable colors when unsupported.
    """

    COLOR_CODES = {
        # DEBUG: Bold cyan text on white background
        # \033       : Start of ANSI escape sequence
        # 1          : Bold text style
        # 36         : Foreground color cyan
        # 47         : Background color white
        # m          : End of ANSI escape sequence
        "DEBUG": "\033[1;36;47m",

        # INFO: Green text (normal weight) on default background
        # \033       : Start of ANSI escape sequence
        # 32         : Foreground color green
        # m          : End of ANSI escape sequence
        "INFO": "\033[32m",

        # WARNING: Yellow text (normal weight) on default background
        # \033       : Start of ANSI escape sequence
        # 33         : Foreground color yellow
        # m          : End of ANSI escape sequence
        "WARNING": "\033[33m",

        # ERROR: Red text (normal weight) on default background
        # \033       : Start of ANSI escape sequence
        # 31         : Foreground color red
        # m          : End of ANSI escape sequence
        "ERROR": "\033[31m",

        # CRITICAL: Bold text on red background (foreground defaults to terminal default)
        # \033       : Start of ANSI escape sequence
        # 1          : Bold text style
        # 41         : Background color red
        # m          : End of ANSI escape sequence
        "CRITICAL": "\033[1;41m",

        # RESET: Reset all styles and colors to terminal defaults
        # \033       : Start of ANSI escape sequence
        # 0          : Reset all attributes
        # m          : End of ANSI escape sequence
        "RESET": "\033[0m",
    }

    def __init__(self, fmt: str | None = None, datefmt: str | None = None) -> None:
      """
      Initialize the ColorFormatter.

      Parameters:
      - fmt: Optional format string that defines the overall log message structure.
            If None (default), logging.Formatter uses its own default format.
            Example: "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

      - datefmt: Optional date/time format string used to format the timestamp.
                If None (default), logging.Formatter outputs an ISO8601-like timestamp,
                e.g., '2025-09-26 12:31:45,038'.
                Common example: "%Y-%m-%d %H:%M:%S" for "2025-09-26 12:31:45"

      Note:
      Passing these to the base logging.Formatter constructor ensures helper
      methods like `formatTime` work correctly.
      """
      # Call the base class constructor to handle formatting setup.
      super().__init__(fmt=fmt, datefmt=datefmt)


    def format(self, record: LogRecord) -> str:
        """
        Create the human-readable colored log line.

        Behavior:
          - Compose a string: TIMESTAMP | LEVEL | LOGGER_NAME | REQUEST_ID | MESSAGE
          - Prepend/append ANSI color codes around the level text.
          - When exc_info is present, append formatted exception text on a new line.

        Note:
          If this method is not overridden or is commented out, the formatter will fall back
          to the default `logging.Formatter.format()` behavior, which means:
            - No ANSI colors will be applied.
            - The output format will follow the base formatter's format string (`fmt`).
            - Custom formatting such as including `request_id` or inline exception formatting
              will not occur.
        """
        # Get the ANSI color code for the log level (e.g., INFO → green, ERROR → red)
        color = self.COLOR_CODES.get(record.levelname, "")      
        
        # ANSI reset code — clears any color formatting after the level name to prevent it from affecting the rest of the log line
        # (Color is applied only to the level name, not the whole line).
        reset = self.COLOR_CODES["RESET"]                       
        # Without the reset (\033[0m), the terminal would continue applying the same foreground/background color 
        # to everything after the log level (including the logger name, request ID, and message), 
        # making the entire line hard to read — or even spill color into the next lines of output.
        
        # Format the log record's creation time using the base Formatter logic
        timestamp = self.formatTime(record, self.datefmt)

        # Construct the main log line with aligned fields:
        # - Level name is colorized and padded for alignment
        # - Logger name is padded to 30 characters
        # - request_id is pulled from the record (or "-" if missing)
        # - Message is inserted at the end
        base = (
            f"{timestamp} | {color}{record.levelname:<10}{reset} | "
            f"{record.name:<30} | "
            f"{getattr(record, 'request_id', '-'):<10} | "
            f"{record.getMessage()}"
        )

        # If the logging call included exception info, include a readable traceback.
        if record.exc_info:
            base = base + "\n" + self.formatException(record.exc_info)

        return base


# class CsvFormatter(logging.Formatter):
#     """
#     CSV-style log formatter: outputs logs as comma-separated values.

#     Format:
#         timestamp,level,name,message,request_id
#     """

#     def __init__(self, datefmt: str | None = None) -> None:
#         super().__init__(datefmt=datefmt)

#     def format(self, record: LogRecord) -> str:
#         # Format the timestamp using the parent class method (respects datefmt)
#         timestamp = self.formatTime(record, self.datefmt)
        
#         # Get log level, logger name, message, and request_id (default to '-')
#         level = record.levelname
#         name = record.name
#         message = record.getMessage()
#         request_id = getattr(record, 'request_id', '-')

#         # Return a CSV-style string
#         return f"{timestamp},{level},{name},{message},{request_id}"


"""
-------------------------------------------------
ANSI Color Codes Breakdown
-------------------------------------------------
ANSI SGR (Select Graphic Rendition) codes use different number ranges to specify foreground vs background colors.

| Code Range | Meaning                  |
| ---------- | ------------------------ |
| 30-37      | Set **foreground** color |
| 40-47      | Set **background** color |

For foreground colors:
- 30 = black
- 31 = red
- 32 = green
- 33 = yellow
- 34 = blue
- 35 = magenta
- 36 = cyan
- 37 = white

For background colors:
- 40 = black background
- 41 = red background
- 42 = green background
- 43 = yellow background
- 44 = blue background
- 45 = magenta background
- 46 = cyan background
- 47 = white background

-------------------------------------------------
If you want a new custom format, the steps are:
-------------------------------------------------
1. Inherit from `logging.Formatter`.
2. Override the `format()` method, which takes a `LogRecord` instance.
3. Use fields from record to build your desired string (or object).
4. Optionally, use `formatTime(record, self.datefmt)` for formatted timestamps.
5. Optionally, use `getattr(record, "custom_attr", "-")` to pull extra fields like `request_id`.
6. Register this formatter in your logging `dictConfig` in `builder.py`.

-------------------------------------------------
Common `LogRecord` Fields You Can Use in `format()`:
-------------------------------------------------
| **Field**                | **Type**       | **Example Value**                     | **Description**                                                          |
| ------------------------ | -------------- | ------------------------------------- | ------------------------------------------------------------------------ |
| `record.name`            | `str`          | `"app.module"`                        | Name of the logger that emitted the record.                              |
| `record.levelno`         | `int`          | `20`                                  | Numeric log level (e.g., `20` for INFO, `40` for ERROR).                 |
| `record.levelname`       | `str`          | `"INFO"`                              | Log level as a string (`"DEBUG"`, `"INFO"`, etc.).                       |
| `record.msg`             | `str`          | `"User %s logged in"`                 | The raw message template before interpolation.                           |
| `record.args`            | `tuple/dict`   | `("alice",)`                          | Arguments for message formatting (`record.msg % record.args`).           |
| `record.getMessage()`    | `str`          | `"User alice logged in"`              | Final formatted log message (after applying args).                       |
| `record.pathname`        | `str`          | `"/app/api/auth.py"`                  | Full file path of the logging call.                                      |
| `record.filename`        | `str`          | `"auth.py"`                           | Just the filename part of `pathname`.                                    |
| `record.module`          | `str`          | `"auth"`                              | Module name (filename without extension).                                |
| `record.funcName`        | `str`          | `"login_user"`                        | Name of the function containing the log call.                            |
| `record.lineno`          | `int`          | `87`                                  | Line number in source code where the log was called.                     |
| `record.created`         | `float`        | `1695800302.145`                      | Time when the LogRecord was created (UNIX timestamp).                    |
| `record.msecs`           | `float`        | `145.00`                              | Milliseconds portion of the timestamp.                                   |
| `record.relativeCreated` | `float`        | `3456.789`                            | Time (in ms) since logging system was initialized.                       |
| `record.asctime`         | `str`          | `"2025-09-27 14:22:43,145"`           | Human-readable timestamp (used only if formatter sets it explicitly).    |
| `record.thread`          | `int`          | `123145304584192`                     | Thread ID.                                                               |
| `record.threadName`      | `str`          | `"MainThread"`                        | Name of the thread in which the log call occurred.                       |
| `record.process`         | `int`          | `51423`                               | Process ID of the running process.                                       |
| `record.processName`     | `str`          | `"MainProcess"`                       | Process name (if available).                                             |
| `record.exc_info`        | `tuple`/`None` | Tuple from `sys.exc_info()`           | Exception info if `exc_info=True` in `logger.error(..., exc_info=True)`. |
| `record.stack_info`      | `str`/`None`   | Stack trace as a string (if present). | Stack trace info if `stack_info=True` is passed to logger call.          |
| `record.__dict__`        | `dict`         | See below ⬇️                          | Contains all the above, plus any `extra={...}` values.                   |


Examples of Extra Fields via `extra={}`:
  You can attach custom fields to a log message like this:
  ```
  logger.info("Payment succeeded", extra={"request_id": "abc123", "user_id": 42})
  ```
  - This will add `record.request_id = "abc123"` and `record.user_id = 42`.
  - These can be accessed in your formatter using getattr(record, "request_id", "-").
  
Pro Tip: Print All Fields from a `LogRecord`:
  To inspect all available fields during logging, add this to your formatter temporarily:
  ```
  def format(self, record):
      print(record.__dict__)  # See all keys/values at runtime
      return super().format(record)
  ```
  
When customizing formatters:
  - Use `record.getMessage()` for final text output (not `record.msg`).
  - Use `record.pathname` + `record.lineno` for tracing source lines.
  - Always wrap optional fields (like `record.request_id`) using `getattr(record, "field", "-")` to avoid `AttributeError`.
"""
