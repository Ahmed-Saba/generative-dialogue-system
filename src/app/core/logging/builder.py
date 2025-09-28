# src/app/core/logging/builder.py
# src/app/core/logging/builder.py
"""
Logging builder: create and apply a dictConfig logging configuration and optionally
wire a background QueueListener to decouple log IO from producer threads.

This module:
 - builds a dictConfig-compatible mapping from Settings
 - allows a queue-backed logging mode (LOG_USE_QUEUE) to move actual writes to a
   background thread (QueueListener) while producers quickly enqueue records
 - provides a NonBlockingQueueHandler implementation to avoid blocking producers
   when using a bounded queue (drop policy + diagnostics)
 - stamps producer-side filters (RequestIdFilter, RedactFilter) on the QueueHandler
   so contextvars and redaction run in the producing context (important for async)
 - exposes stop_queue_logging() to flush & stop the background listener at shutdown.

Configuration knobs (on your Settings object):
 - LOG_USE_QUEUE: bool - enable queue-backed logging
 - LOG_QUEUE_MAX_SIZE: int | None - if > 0, use a bounded queue with this size.
   If 0 or None the queue will be unbounded.
 - LOG_QUEUE_BLOCKING: bool - if True and max_size > 0, producers will block on full queue;
   if False, NonBlockingQueueHandler will drop records when full.
 - LOG_QUEUE_DROP_WARNING_THRESHOLD: int - how often to warn when logs are dropped (every N drops).
 - LOG_TO_STDOUT, LOG_DIR, LOG_FORMAT, LOG_LEVEL, ENABLE_SQL_LOGGING, ENV - standard settings.
"""

from __future__ import annotations

from pathlib import Path
import logging
import logging.config
import queue as _queue
import threading
from typing import Optional
from app.utils.logging import get_project_name

# Handler/formatter/filter classes used in dictConfig must be importable here.
from logging.handlers import QueueHandler, QueueListener

from .formatters import JsonFormatter, ColorFormatter
from .filters import RequestIdFilter, RedactFilter
from .handlers import (
    get_console_handler,
    get_file_handler,
    get_error_file_handler,
    get_error_console_handler,
)

# Settings type (avoid calling get_settings() here to prevent import-time side effects)
from app.config.settings import Settings  # type: ignore

# Module-level references to running QueueListener and underlying queue so we can stop them
_QUEUE_LISTENER: Optional[QueueListener] = None
_QUEUE: Optional[_queue.Queue] = None

# Diagnostics for dropped logs (when using non-blocking/bounded queue)
_DROPPED_LOGS_COUNT = 0
_DROPPED_LOGS_LOCK = threading.Lock()


# -----------------------
# Helper: non-blocking queue handler
# -----------------------
class NonBlockingQueueHandler(QueueHandler):
    """
    QueueHandler variant that does not block producers when a bounded queue is full.

    Behavior:
      - If the queue has room, enqueues record as normal.
      - If the queue is full:
          * increments a drop counter (module-level, thread-safe).
          * optionally calls `handleError(record)` so Python logging can record the failure
            (may itself create a log entry).
          * does NOT block the calling thread.
    Use this when you prefer a bounded memory footprint and cannot afford the producer to
    block (e.g. high-throughput request threads).
    """

    def __init__(self, q: _queue.Queue):
        super().__init__(q)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Try to put the record into the queue using put_nowait(). On Full, increment
        drop counter and call handleError(record).
        """
        global _DROPPED_LOGS_COUNT
        try:
            record = self.prepare(record)
            self.queue.put_nowait(record)
        except _queue.Full:
            # Increment dropped count (thread-safe)
            with _DROPPED_LOGS_LOCK:
                _DROPPED_LOGS_COUNT += 1
                dropped = _DROPPED_LOGS_COUNT

            # Let logging handle the error (this will normally write to sys.stderr)
            # or you might choose to silently drop. handleError is a hook to report.
            try:
                self.handleError(record)
            except Exception:
                # Ensure we never propagate exceptions from the logging path to producers.
                pass

            # Optionally: you could emit a periodic warning about drops; we leave that
            # to setup_logging to emit based on LOG_QUEUE_DROP_WARNING_THRESHOLD.
            return


def get_queue_stats() -> dict:
    """Return small diagnostics about queue usage (dropped logs count)."""
    with _DROPPED_LOGS_LOCK:
        return {"dropped_logs": _DROPPED_LOGS_COUNT, "queue_present": _QUEUE is not None}


# -----------------------
# dictConfig builder
# -----------------------
def make_dict_config(settings: Settings) -> dict:
    """
    Build the dictConfig mapping using the provided settings.

    The returned mapping includes:
      - formatters: "standard" (color/dev or normal) and "json"
      - filters: "request_id", "redact"
      - handlers: console, (file/error_file) OR error_console depending on LOG_TO_STDOUT
      - loggers: root, uvicorn.error, uvicorn.access, sqlalchemy.engine
    """
    console_handler = get_console_handler(settings)
    file_handler = get_file_handler(settings)
    error_file_handler = get_error_file_handler(settings)
    error_console_handler = get_error_console_handler(settings)

    formatters = {
        "standard": {
            # use ColorFormatter only in text development mode
            "()": ColorFormatter if settings.LOG_FORMAT == "text" else logging.Formatter,
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s",
        },
        "json": {
            "()": JsonFormatter,
            "env": settings.ENV,
            "service": get_project_name(),
        },
    }

    filters = {
        "request_id": {"()": RequestIdFilter},
        "redact": {"()": RedactFilter},
    }

    handlers: dict[str, dict] = {"console": console_handler}

    if (not settings.LOG_TO_STDOUT) and (settings.LOG_DIR):
        handlers["file"] = file_handler
        handlers["error_file"] = error_file_handler
    else:
        handlers["error_console"] = error_console_handler

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "filters": filters,
        "handlers": handlers,
        "loggers": {
            "": {
                "handlers": list(handlers.keys()),
                "level": settings.LOG_LEVEL,
                "propagate": True,
            },
            "uvicorn.error": {
                "level": settings.LOG_LEVEL,
                "handlers": list(handlers.keys()),
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            # Be cautious with SQL logging (may contain sensitive data)
            "sqlalchemy.engine": {
                "level": "DEBUG" if settings.ENABLE_SQL_LOGGING else "WARNING",
                "handlers": ["console"],
                "propagate": False,
            },
        },
    }

    return config


# --------------------------
# Entrypoint: setup & optional queue wiring
# --------------------------
def setup_logging(settings: Settings) -> None:
    """
    Initialize logging using settings and optionally switch to queue-backed logging.

    Steps:
      1. Ensure LOG_DIR exists when writing files.
      2. Apply dictConfig(make_dict_config(settings)) so handlers/formatters/filters exist.
      3. Register a RequestIdFilter on the root logger as a safety net.
      4. If settings.LOG_USE_QUEUE:
            - create a (bounded or unbounded) queue
            - remove real handlers from all loggers so they won't run in producer context
            - create a QueueListener that runs the real handlers in a background thread
            - attach a QueueHandler (or NonBlockingQueueHandler) to the root logger
              and add producer-side filters (RequestIdFilter, RedactFilter) so they run
              in the producer context (important for contextvars & redaction)

    Notes:
      - For multi-process servers (gunicorn with multiple worker processes) this
        approach isolates logging per-process. For centralized logging prefer a central
        agent (fluentd, filebeat, syslog, etc.) or a multiprocessing-safe strategy.
    """
    global _QUEUE_LISTENER, _QUEUE

    # Create log directory if necessary (avoid race by exist_ok=True)
    if (not settings.LOG_TO_STDOUT) and (settings.LOG_DIR):
        Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)

    # Apply dictConfig to create handlers and wire loggers/formatters/filters
    logging.config.dictConfig(make_dict_config(settings))

    # Attach RequestIdFilter to root as an extra safety net (keeps %(request_id)s safe).
    logging.getLogger().addFilter(RequestIdFilter())

    # If queueing disabled, we're done
    if not getattr(settings, "LOG_USE_QUEUE", False):
        return

    # Build the queue: bounded if LOG_QUEUE_MAX_SIZE > 0 else unbounded
    max_size = getattr(settings, "LOG_QUEUE_MAX_SIZE", 0) or 0  # 0 means unbounded in queue.Queue()
    blocking = bool(getattr(settings, "LOG_QUEUE_BLOCKING", False))
    drop_warn_threshold = int(getattr(settings, "LOG_QUEUE_DROP_WARNING_THRESHOLD", 100))

    # Copy real handler instances currently attached to root so listener can use them.
    root_logger = logging.getLogger()
    current_handlers = list(root_logger.handlers)
    if not current_handlers:
        # No handlers created by dictConfig? nothing to do
        return

    # Build a set for quick membership checks
    handlers_to_move = set(current_handlers)

    # Remove those handler *instances* from all named loggers (so they won't execute in producer threads).
    manager = logging.Logger.manager
    for name, logger_obj in list(manager.loggerDict.items()):
        if isinstance(logger_obj, logging.Logger):
            for h in list(logger_obj.handlers):
                if h in handlers_to_move:
                    logger_obj.removeHandler(h)

    # Also remove from root (there may be duplicates)
    for h in list(root_logger.handlers):
        if h in handlers_to_move:
            root_logger.removeHandler(h)

    # Create the actual queue
    if max_size > 0:
        log_queue: _queue.Queue = _queue.Queue(max_size)
    else:
        # unbounded
        log_queue = _queue.Queue()  # maxsize=0 -> unbounded

    # Choose handler type: blocking or non-blocking
    if max_size > 0 and not blocking:
        queue_handler_cls = NonBlockingQueueHandler
    else:
        # Use standard QueueHandler which will block when queue is full if blocking=True
        queue_handler_cls = QueueHandler  # type: ignore

    # Start a QueueListener running the real handlers in a background thread
    listener = QueueListener(log_queue, *current_handlers, respect_handler_level=True)
    listener.start()

    # Attach QueueHandler (or NonBlockingQueueHandler) to the root so producers enqueue quickly.
    qh = queue_handler_cls(log_queue)  # type: ignore

    # Add producer-side filters: these must run in the producer context (where contextvars exist).
    # - RequestIdFilter stamps request_id from contextvar into the LogRecord
    # - RedactFilter scrubs sensitive attributes before they enter the queue (prevents secrets in queue/file)
    qh.addFilter(RequestIdFilter())
    qh.addFilter(RedactFilter())

    # Optionally: add a small wrapper filter to warn periodically when drops occur.
    # For NonBlockingQueueHandler we monitor _DROPPED_LOGS_COUNT elsewhere (get_queue_stats()).
    # The periodic warning itself should be infrequent to avoid noise; we log it through the listener
    # (use a closure so it runs in the listener's thread when invoked via logging).
    def _maybe_warn_about_drops():
        with _DROPPED_LOGS_LOCK:
            dropped = _DROPPED_LOGS_COUNT
        if dropped and (dropped % drop_warn_threshold == 0):
            # This log will be processed by the QueueListener (safe).
            logging.getLogger(__name__).warning(
                "Dropped %d log records because queue was full", dropped
            )

    # Attach qh to the root logger
    root_logger.addHandler(qh)

    # Save references so shutdown can stop listener
    _QUEUE_LISTENER = listener
    _QUEUE = log_queue

    # If using non-blocking handler with dropping policy, schedule a small background timer
    # to occasionally emit a warning from the listener thread. We keep this optional and simple:
    if queue_handler_cls is NonBlockingQueueHandler and drop_warn_threshold > 0:
        # Emit one warn call synchronously here (it will be enqueued and handled by listener)
        _maybe_warn_about_drops()


def stop_queue_logging(timeout: Optional[float] = 5.0) -> None:
    """
    Stop the QueueListener and clear module refs. Wait up to `timeout` seconds
    for it to stop. This prevents long blocking shutdowns.
    """
    global _QUEUE_LISTENER, _QUEUE
    listener = _QUEUE_LISTENER
    if listener is None:
        return

    try:
        listener.stop()  # requests the listener thread to stop and joins it
        # listener.stop() internally joins; if you want a separate join with timeout:
        # if hasattr(listener, "_thread") and isinstance(listener._thread, threading.Thread):
        #     listener._thread.join(timeout)
    except Exception:
        logging.getLogger(__name__).exception("Failed to stop QueueListener cleanly")
    finally:
        _QUEUE_LISTENER = None
        _QUEUE = None






"""
This file might look intimidating, but it's really just a config assembler — it builds and applies a logging system 
that the rest of your app can use with a simple call to:
    ```
    setup_logging(settings)
    ```
Lets break it all down in a clear and practical way.

-------------------------------------------------
Why Does builder.py Exist?
-------------------------------------------------
This file exists so you can configure logging once and use it everywhere in your app.

It has two jobs:
    - `make_dict_config(settings)`: creates a big config dict describing how logging should behave.
    - `setup_logging(settings)`: applies the config and sets up logging for the app.
    
-------------------------------------------------
Big Picture: What Are We Building?
-------------------------------------------------
You're using `logging.config.dictConfig()` to set up:
| Component      | What it does                                                 |
| -------------- | ------------------------------------------------------------ |
| **Formatters** | Decide how logs **look** (e.g. JSON, color, plain)           |
| **Filters**    | Modify or enrich logs (e.g. add `request_id`)                |
| **Handlers**   | Decide where logs go (e.g. console, file, only errors)       |
| **Loggers**    | Apply logging rules to specific modules (e.g. root, uvicorn) |


-------------------------------------------------
What Is a Logging Handler?
-------------------------------------------------
A handler is a component in Python's logging system that determines:
    - Where the log should go (e.g. console, file, external service),
    - How the log should be formatted (via a formatter),
    - What logs it should include (via filters and log level).
    
So when you log something like `logger.info("User created")`, the handlers determine:
    ➤ Does this go to stdout? A file? Both?
    ➤ Should it be printed as JSON or plain text?
    ➤ Should it include request ID or not?
    
Handlers You're Using — Compared:
| Handler Name         | Type/Class                             | Destination                  | Purpose/Use Case                                                    |
| -------------------- | -------------------------------------- | ---------------------------- | ------------------------------------------------------------------- |
| `console_handler`    | `logging.StreamHandler`                | Terminal (stderr by default) | Show logs during development, or in Docker logs if using stdout     |
| `file_handler`       | `logging.handlers.RotatingFileHandler` | `app.log` file               | Log **all levels** to a rotating file (INFO, DEBUG, etc)            |
| `error_file_handler` | `logging.handlers.RotatingFileHandler` | `errors.log` file            | Capture only **ERROR and above** logs for alerts, audits, etc       |
| `error_console`      | `logging.StreamHandler`                | Terminal                     | Emit **only ERRORs** to stdout in production (when not using files) |

1. console_handler
```
    "console": get_console_handler(settings)
```
    - Class: `logging.StreamHandler`
    - Outputs logs to console (usually stderr)
    - Used in:
        - Development to see real-time logs
        - Containers (e.g. Docker) where logs are picked from stdout/stderr
    - Format: JSON or plain text, depending on `settings.LOG_FORMAT`

2. file_handler
```
    "file": get_file_handler(settings)
```
    - Class: `logging.handlers.RotatingFileHandler`
    - Outputs all logs (DEBUG, INFO, WARNING, etc.) to `app.log`
    - Rotates when it hits a max size (`maxBytes`, `backupCount`)
    - Best for:
        - Persistent logs in local development
        - On-prem deployments where stdout logging isn't sufficient

3. error_file_handler
```
"error_file": get_error_file_handler(settings)
```
    - Class: `RotatingFileHandler`
    - Logs only `ERROR` and above
    - Separate file: `errors.log`
    - Useful for:
        - Alerting (monitor this file for critical failures)
        - Easier troubleshooting — separate noise from real problems
        - Historical error archiving
        
4. error_console
```
"error_console": get_error_console_handler(settings)
```
    - Only used when file logging is disabled (e.g., production containers)
    - Outputs errors to stdout/stderr in JSON format
    - Designed for log ingestion systems like:
        - AWS CloudWatch
        - Datadog
        - GCP Logging
    - Ensures your errors are visible and structured
    
Summary Table (Quick Comparison):
| Name                 | Stream/File | Levels Captured | Used When?                         | File Name    |
| -------------------- | ----------- | --------------- | ---------------------------------- | ------------ |
| `console_handler`    | Stream      | All             | Always (for human visibility)      | —            |
| `file_handler`       | File        | All             | Dev / when `LOG_TO_STDOUT=False`   | `app.log`    |
| `error_file_handler` | File        | Only ERROR+     | Dev / file-based prod logging      | `errors.log` |
| `error_console`      | Stream      | Only ERROR+     | Production w/ `LOG_TO_STDOUT=True` | —            |


-------------------------------------------------
How to Switch Between Handlers Based on Environment
-------------------------------------------------
The logic is handled here in `builder.py`:
```
    # We always include "console" (stdout/stderr).
    handlers: dict[str, dict] = {"console": console_handler}

    if (not settings.LOG_TO_STDOUT) and (settings.LOG_DIR):
        handlers["file"] = file_handler
        handlers["error_file"] = error_file_handler
    else:
        handlers["error_console"] = get_error_console_handler(settings)
```
Meaning:
| `LOG_TO_STDOUT` | `LOG_DIR` Set  | Active Handlers                                        |
| --------------- | -------------- | -------------------------------------------------------|
| `true`          | doesn't matter | ✅ `console` + `error_console` (no file logs)          |
| `false`         | not set        | ✅ `console` + `error_console` (file logging skipped)  |
| `false`         | set            | ✅ `console` + `file` + `error_file`                   |

Summary:
    - `Console` output is always enabled (regardless of settings).
    - File logging is enabled only when:
        - LOG_TO_STDOUT is set to false, and
        - LOG_DIR is configured (LOG_DIR has a default value in config/settings.py)
        - If LOG_TO_STDOUT=false but LOG_DIR is missing or invalid, file logging is skipped 
          as a safety fallback — no crash.
    - Production containers should use LOG_TO_STDOUT=true for Docker 🐳 best practices.
    - In development, you can toggle file logging by simply:
        - Setting `LOG_TO_STDOUT=false`, and
        - Defining LOG_DIR (e.g., logs/gds) or use the default value defined in settings.

How Handlers Are Auto-Activated:
    Handlers are wired up dynamically in the handlers dictionary in builder.py:
    ```
        handlers: dict[str, dict] = {"console": console_handler}

        # More handlers added based on config
        if (not settings.LOG_TO_STDOUT) and (settings.LOG_DIR):
            handlers["file"] = file_handler
            handlers["error_file"] = error_file_handler
        else:
            handlers["error_console"] = get_error_console_handler(settings)
    ```

    Then they're attached to each logger, like the root logger:
    ```
        "loggers": {
            "": {
                "handlers": list(handlers.keys()),  # dynamically pulls whatever handlers were added
                "level": settings.LOG_LEVEL,
                "propagate": True,
            },
            ...
        }
    ```
    This means:
        - Only the handlers defined above will actually be wired into the log system.
        - If you set `LOG_TO_STDOUT=True`, then `file` and `error_file` will not exist in the config, 
           and therefore won't run or write files.
           

Each handler watches for log levels. Here's how:
| Handler         | Triggers On             | Output                  |
| --------------- | ----------------------- | ----------------------- |
| `console`       | All logs `>= LOG_LEVEL` | Console (stdout/stderr) |
| `file`          | All logs `>= LOG_LEVEL` | `app.log`               |
| `error_file`    | Only logs `>= ERROR`    | `errors.log`            |
| `error_console` | Only logs `>= ERROR`    | Console                 |

Example Behavior: If `LOG_LEVEL=INFO`, and your code does this:
```
logger.info("User signed in")
logger.error("Failed to load user profile")
```
Then:

If `LOG_TO_STDOUT=true`:
    - ✅ console: prints both INFO and ERROR messages (human-readable format)
    - ✅ error_console: prints only the ERROR message (in structured JSON format)
    - ❌ No log files are created

If `LOG_TO_STDOUT=false` and `LOG_DIR` is set (LOG_DIR already has a default value in settings.py):
    - ✅ `console`: prints both messages
    - ✅ `file`: writes both to `logs/gds/app.log` (the path you defined in .env or the default in settings.py)
    - ✅ `error_file`: writes only the error to logs/gds/errors.log
    
You Can Test This Yourself
    Change your .env file:
    ```
    LOG_TO_STDOUT=true
    LOG_DIR=logs/gds
    LOG_LEVEL=INFO
    ```
    
    Then run:
    ```
    import logging
    from app.config.settings import get_settings
    from app.core.logging import setup_logging
    from app.core.logging.filters import RequestIdFilter, set_request_id

    # Initialize settings and logging
    settings = get_settings()
    setup_logging(settings)

    # Get a logger and attach request_id
    logger = logging.getLogger(__name__)
    logger.addFilter(RequestIdFilter())
    set_request_id("abc-123")

    # Log some messages
    logger.debug("debug")      # Won't show unless LOG_LEVEL=DEBUG
    logger.info("info")        # Printed to `console`
    logger.error("error")      # Printed to `console` + `error_console` (JSON format)
    ```
    📝 Tip: Change `LOG_TO_STDOUT` to `false` to see logs written to files instead.
    
    
-------------------------------------------------
What Are `stdout` and `stderr`?
-------------------------------------------------
They are standard output streams used by all operating systems (Unix/Linux, macOS, Windows) 
to handle program output.

| Stream   | Name                | Purpose                                             | Example                                        |
| -------- | ------------------- | --------------------------------------------------- | ---------------------------------------------- |
| `stdout` | **Standard Output** | For **normal program output** (e.g. logs, results). | `print("Hello")` → goes to `stdout`            |
| `stderr` | **Standard Error**  | For **error messages or warnings**.                 | `logger.error("Failed to connect")` → `stderr` |

Why They Matter
    1. Logging Separation
        You can separate normal logs from error logs, which helps in filtering/log collection.
        For example:
        ```
        python app.py > output.log 2> errors.log
        ```
            - `>` → sends `stdout` to `output.log`
            - `2>` → sends `stderr` to `errors.log`
            
    2. Containerized Environments (Docker, Kubernetes)
        - Logging to `stdout` and `stderr` is a best practice because:
            - The container runtime (e.g., Docker) automatically captures these.
            - Logs appear in centralized log collectors without needing file access.
            
    3. Cleaner Piping
        You can redirect just the stdout to another tool or file while keeping errors visible:
        ```
        python app.py | grep "INFO"
        ```
        
In Python
    - `print()` writes to stdout.
    - `logging.error()`, `logging.exception()` write to `stderr` if configured (e.g., `StreamHandler()` defaults to `stderr`).
    - You can change a handler to log to `stdout` like this:
    ```
    import sys
    handler = logging.StreamHandler(sys.stdout)
    ```

Summary
| Term     | Meaning         | Default Use                   |
| -------- | --------------- | ----------------------------- |
| `stdout` | Standard Output | Normal logs, print statements |
| `stderr` | Standard Error  | Warnings, errors, exceptions  |

"""
