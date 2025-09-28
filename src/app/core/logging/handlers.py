# src/app/core/logging/handlers.py
"""
Console handler factory for logging.dictConfig.

This small module provides a single helper, `get_console_handler`, which builds
and returns a handler configuration dictionary suitable for inclusion in a
`logging.config.dictConfig()` call.

Why this exists:
- By centralizing the console handler construction in one place we keep the
  builder (dictConfig) concise and make it easy to change console behaviour
  (stdout vs stderr, formatter choice, filters) in a single, testable location.
- The function accepts your validated `Settings` object so environment-specific
  choices (json vs text, log level) come from a single source of truth.
"""

from app.config.settings import Settings
from pathlib import Path


def get_console_handler(settings: Settings) -> dict:
    """
    Return a logging handler configuration dict for a console/stream handler.

    Args:
        settings: The application Settings instance (pydantic BaseSettings).
                  Expected relevant attributes:
                    - LOG_FORMAT: 'json' or 'text' (used here to pick formatter name)
                    - LOG_LEVEL: logging level string ('DEBUG', 'INFO', ...)

    Returns:
        dict: A handler configuration dictionary compatible with dictConfig().

    Result shape and important keys explained:
		- "class": Specifies the handler class. Here we use "logging.StreamHandler",
						the stdlib handler that writes to a stream (defaults to sys.stderr).
						Example alternative: include "stream": "ext://sys.stdout" to force stdout.
		- "formatter": The name of the formatter defined in the "formatters" section
						of dictConfig. This function picks "json" when settings.LOG_FORMAT
						equals "json", otherwise "standard". The chosen formatter must
						exist in the overall dictConfig (builder.py provides them).
		- "level": Minimum level for this handler (string like "INFO"). The logging
						module accepts level names or integers. Using the settings value
						keeps behaviour configurable per environment.
		- "filters": A list of filter names to apply to the handler. The filter(s)
						must be defined in the "filters" section of the dictConfig.
						We use "request_id" so request-aware filters (e.g., RequestIdFilter)
						can attach/ensure request_id is present on every LogRecord.

    Notes & recommended improvements:
      - Default stream: StreamHandler writes to sys.stderr by default. In container
        environments it's common to direct logs to stdout so log collectors can
        capture them consistently; to do that, the dictConfig handler can include:
            "stream": "ext://sys.stdout"
        You can add that key here when you want console output on stdout.
      - Using strings vs callables: We return a dict with the "class" path as a
        string which is the standard dictConfig usage. Another option is to return
        a handler factory using "()" with a callable, but strings are simple and
        portable for dictConfig usage.
      - Testing: Because this is a pure function (no side effects), it's easy to
        unit test: assert the returned dict contains expected keys and values for
        different settings permutations.
      - Handler name: The builder will register this handler under some name
        (e.g., "console"). Keep the handler configuration stable to avoid confusion.
    """
    return {
        "class": "logging.StreamHandler",
        # The builder's "formatters" mapping must contain "json" and "standard".
        # We choose between them based on settings.LOG_FORMAT.
        "formatter": "json" if settings.LOG_FORMAT == "json" else "standard",
        # Keep the handler level configurable via settings. This controls which
        # records the handler will emit (in addition to any logger-level filtering).
        "level": settings.LOG_LEVEL,
        # Attach the request_id filter so every emitted record gets a request_id attribute.
        # The filter must be declared in the dictConfig's "filters" section (builder.py does this).
        "filters": ["request_id", "redact"],
        # Optional: to force stdout instead of stderr, add:
        # "stream": "ext://sys.stdout"
    }

def get_file_handler(settings: Settings) -> dict:
    file_path = str(Path(settings.LOG_DIR) / "app.log")
    return {
        "class": "logging.handlers.RotatingFileHandler",
        # choose formatter name (the formatters mapping below defines these)
        "formatter": "json" if settings.LOG_FORMAT == "json" else "standard",
        "level": settings.LOG_LEVEL,
        "filename": file_path,
        "maxBytes": settings.LOG_MAX_BYTES,
        "backupCount": settings.LOG_BACKUP_COUNT,
        "encoding": "utf-8",
        # Ensure request_id is added to each record (filter must be declared below)
        "filters": ["request_id", "redact"],
    }

# Error-specific rotating file to separate errors (useful for alerting/archival).
def get_error_file_handler(settings: Settings) -> dict:
    error_file_path = str(Path(settings.LOG_DIR) / "errors.log")
    return {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "json",  # keep error files structured for easier ingestion
        "level": "ERROR",
        "filename": error_file_path,
        "maxBytes": settings.LOG_MAX_BYTES,
        "backupCount": settings.LOG_BACKUP_COUNT,
        "encoding": "utf-8",
        "filters": ["request_id", "redact"],
    }

def get_error_console_handler(settings: Settings) -> dict:
    return {
        "class": "logging.StreamHandler",
        "formatter": "json",
        "level": "ERROR",
        "filters": ["request_id", "redact"],
        # Optional: to force stdout instead of stderr, add:
        # "stream": "ext://sys.stdout"
    }



"""
-------------------------------------------------
What is a Handler in Python Logging?
-------------------------------------------------
A handler is what actually sends your log records somewhere.
Think of logging like a pipeline:
```
Logger → Filter(s) → Handler → Formatter → Output (e.g., console, file, HTTP)
```

You can think of it like this:
| Component   | Role                                                                      |
| ----------- | ------------------------------------------------------------------------- |
| `Logger`    | You call `logger.info(...)`, and it emits a `LogRecord`.                  |
| `Filter`    | Optionally modify or skip that record (e.g. add `request_id`).            |
| `Handler`   | Chooses **where to send** the log (console, file, email, etc).            |
| `Formatter` | Formats the `LogRecord` into a human-readable or machine-readable string. |
| Output      | The final destination: terminal, file, log collector, etc.                |

-------------------------------------------------
What Problem is `handlers.py` Solving?
-------------------------------------------------
When you log something like:
```
	logger.info("Something happened")
```
The handler decides where that log goes.

Common destinations:
	- Console (your terminal)
	- A file (like logs/app.log)
	- External services (e.g. Sentry, Slack, HTTP API)
	- Nowhere (if the handler blocks it)
So `handlers.py` is where we configure the rules that control this.

-------------------------------------------------
So What Do We Actually Do in handlers.py?
-------------------------------------------------
The file contains a single function:
```
	def get_console_handler(settings: Settings) -> dict:
```
Its job is to build a dictionary that describes:
	- Which class to use (e.g. console output handler)
	- What formatter to use (`json` or `standard`)
	- Which filters to apply (e.g. request ID)
	- What log level to allow (`INFO`, `DEBUG`, etc.)

Here's the handler config it returns:
```
	{
		"class": "logging.StreamHandler",         # Logs to stderr by default
		"formatter": "json" or "standard",        # Chooses how logs look (JSON or plain text)
		"level": "INFO" or "DEBUG",               # Logs below this level are ignored
		"filters": ["request_id"],                # Adds request_id to every log record
		# Optional: "stream": "ext://sys.stdout"  # You could add this if needed
	}
```
This dictionary gets plugged into Python's logging.config.dictConfig() (in builder.py) — and that's what activates it.

-------------------------------------------------
Why Define It Like This (via Function)?
-------------------------------------------------
Benefits of get_console_handler(settings):
	1. Centralized config: You define your handler logic in one place.
	2. Environment-aware: The handler config changes based on environment settings (json vs text, log level, etc).
	3. Easier testing: Since it's just a pure function, you can write unit tests for it.

So we can write this in builder.py:
```
handlers = {
    "console": get_console_handler(settings),
}
```

That keeps your config dynamic and flexible. For example:
	- In dev, use "text" logs, level "DEBUG"
	- In prod, use "json" logs, level "INFO"
All from the Settings object.

-------------------------------------------------
Analogy:
-------------------------------------------------
Imagine you're logging a message like:
```
logger.info("User created successfully")
```
Here's what happens:
	1. The logger emits a `LogRecord`.
	2. That record flows through any filters (`RequestIdFilter`).
	3. It reaches a handler (like `StreamHandler`) — which says “I'll send this to the console”.
	4. Before sending it, the formatter turns it into a string:
		```
		2025-09-27 10:31:04 | INFO | my_module | abc123 | User created successfully
		```
	5. The output goes to stdout or stderr.

Analogy: Think of a Log "Handler" Like a Waiter in a Restaurant:
| Role          | Job                                                                    |
| ------------- | ---------------------------------------------------------------------- |
| **Logger**    | The kitchen making the food (log message)                              |
| **Filter**    | A chef double-checking if the food is OK                               |
| **Handler**   | The waiter delivering the food to the right table (console, file, etc) |
| **Formatter** | The plate it’s served on (plain vs fancy presentation)                 |
Your handler config says:
	- “Use StreamHandler, formatted as JSON or text, add the request ID, and only serve INFO-level logs or higher.”

So, What Do You Actually Do in handlers.py?

Just one thing: define how to build a handler config dict.
```
	def get_console_handler(settings: Settings) -> dict:
		return {
			"class": "logging.StreamHandler",  # Write to terminal
			"formatter": "json" if settings.LOG_FORMAT == "json" else "standard",
			"level": settings.LOG_LEVEL,
			"filters": ["request_id"],
		}
```
That's it. It doesn't actually do logging. It returns config that will be used later by dictConfig() in builder.py.

-------------------------------------------------
Bonus: What if You Wanted to Add a File Handler?
-------------------------------------------------
You could add a new function:

```
def get_file_handler(log_file_path: str) -> dict:
    return {
        "class": "logging.FileHandler",
        "filename": log_file_path,
        "formatter": "standard",
        "level": "INFO",
        "filters": ["request_id"],
    }
```

Then in builder.py, plug it in:
```
handlers = {
    "console": get_console_handler(settings),
    "file": get_file_handler("/var/log/app.log"),
}
```
Now logs go both to console and a file.

Summary
| You're doing this...            | To accomplish this...                             |
| ------------------------------- | ------------------------------------------------- |
| Writing `get_console_handler()` | To configure how console logs are handled         |
| Returning a dictionary          | Because `logging.config.dictConfig()` expects it  |
| Using `StreamHandler`           | Because you want logs printed to the terminal     |
| Using a formatter name          | To control whether logs are JSON or pretty text   |
| Adding `request_id` filter      | So logs contain request IDs for traceability      |
| Using `settings`                | So behavior adapts to dev/production environments |

You're Not Supposed to Do Much Here. This file is intentionally small and focused. You:
  1. Return a handler config dictionary.
  2. Use it in builder.py to build the final logging setup.
"""
