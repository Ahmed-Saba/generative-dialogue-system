# src/app/core/logging/filters.py
"""
Logging filters

Request ID filter and helpers for logging.

This module provides a tiny, focused API for attaching a per-request identifier
(request_id) to Python `logging.LogRecord`s in an async-friendly way.

Why this exists
----------------
- Correlating log lines that belong to the same HTTP request is essential for
  debugging distributed systems and tracing flows through your application.
- Using a context-local storage (contextvars) ensures the request id is properly
  propagated across asynchronous tasks and awaits (unlike threading.local()).
- The RequestIdFilter guarantees that any formatter referencing `%(request_id)s`
  will not KeyError — each record will have a `request_id` attribute (either the
  real id or the sentinel "-").

How it is intended to be used
------------------------------
1. Install the filter into your logging configuration (dictConfig):
   - Add an entry in the "filters" dictionary that references this class.
   - Attach the filter name to handlers that should include request ids (console, file, etc).

   Example (builder.py / dictConfig snippet):
    # from .filters import RequestIdFilter
     "filters": {
         "request_id": {
           "()": RequestIdFilter
           }
     },
     "handlers": {
         "console": {"class": "logging.StreamHandler", "filters": ["request_id"], ...}
     }

2. Set the request id at the start of each HTTP request (middleware):
   - Call `set_request_id(rid)` in a per-request middleware (see middleware.py).
   - Optionally read an incoming header `X-Request-ID` or generate a new UUID.

3. After `set_request_id` is called, any subsequent logging in the same context
   will have `record.request_id` populated by the filter — formatters can include it.

Important design notes
----------------------
- We use `contextvars.ContextVar` to store the request id because it is:
  * safe across asyncio tasks and preserves context across `await` boundaries;
  * more correct for async frameworks (FastAPI/Starlette) than `threading.local()`.
- The filter is extremely cheap: it's just a lookup into a context var and a simple
  assignment onto the LogRecord.
- We default `request_id` to "-" when nothing is set. This avoids KeyErrors in
  formatters and makes the logs easy to filter for missing IDs.
- The filter returns `True` so it never prevents a record from being emitted;
  its job is purely to annotate the record.

Security and privacy
--------------------
- Do not derive the request_id from sensitive information (user tokens, PII).
- If the incoming header `X-Request-ID` is used, consider validating/sanitizing
  its format to avoid log injection attacks (e.g., newlines).

Testing
-------
- Unit test the filter by creating a dummy LogRecord and asserting:
    * when no contextvar is set -> record.request_id == "-"
    * after calling set_request_id("abc") -> record.request_id == "abc"
- Integration test: add the filter to a temporary dictConfig and assert that
  emitted records include the request_id field in formatted output.

Potential enhancements
----------------------
- Accept an optional request-id generator or validator function (configurable).
- Add `set_request_trace(trace_id)` sibling helpers if you want both trace and span IDs.
- Provide a `clear_request_id()` helper to explicitly clear the context var (useful in tests).
"""

import logging
from logging import LogRecord
import contextvars

# contextvar for request id (used by RequestIdFilter and the HTTP middleware).
# It stores the request id for the current execution context (async task / logical flow).
# Default is None to indicate "no request id set".
_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def set_request_id(request_id: str | None):
    """
    Set the request id in the current context and return the token to allow reset.

    Returns:
        token: contextvar.Token which can be passed to reset_request_id(token)
    """
    return _request_id_ctx.set(request_id)


def reset_request_id(token):
    """
    Reset the contextvar to the previously saved token returned by set_request_id().
    """
    # Token should be the value returned by ContextVar.set(...)
    _request_id_ctx.reset(token)


def get_request_id() -> str | None:
    """
    Retrieve the current context's request id.

    Returns:
        The request id string or None if no id has been set for this context.
    """
    return _request_id_ctx.get()


class RequestIdFilter(logging.Filter):
    """
    Logging filter that guarantees every LogRecord has a `request_id` attribute.

    Responsibilities:
      - Read the current request id from the contextvar (if any).
      - Set `record.request_id` to:
           * record.request_id (if already set on the LogRecord via extra)
           * OR the contextvar value (if set via middleware)
           * OR the sentinel "-" (if no id available).
      - Always return True so the record continues through the logging pipeline.

    Why we set record.request_id this way:
      - Sometimes code might explicitly pass `extra={"request_id": value}`; respect that.
      - Otherwise, use the contextvar (set by middleware) which is the common case.
      - Fallback to "-" to avoid KeyError in format strings that reference %(request_id)s.
    """

    def filter(self, record: LogRecord) -> bool:
        # If a record already has a request_id (explicitly provided via extra), keep it.
        # Otherwise, use the contextvar value or fallback to "-".
        record.request_id = (
            getattr(record, "request_id", None) or get_request_id() or "-"
        )
        # Return True to indicate the record should be processed/emitted.
        return True


# Redact sensitive information
class RedactFilter(logging.Filter):
    SENSITIVE = {"password","secret","token","access_token","refresh_token","ssn","authorization"}
    def filter(self, record: LogRecord) -> bool:
        # mask attributes on record that match SENSITIVE
        for key in list(record.__dict__.keys()):
            if key.lower() in self.SENSITIVE:
                record.__dict__[key] = "***REDACTED***"
        # also scrub extras if present under 'extra' or similar keys (custom)
        return True


r"""
-------------------------------------------------
What is the goal of `filters.py`?
-------------------------------------------------
To automatically attach a `request_id` to every log message so that you can trace which logs came from the same HTTP request.

Think of it like this:
  - In an API, one incoming HTTP request may generate multiple logs.
  - To correlate those logs, you need a shared identifier: request_id.
  - But Python's logging system doesn't know anything about your HTTP requests by default.
  - So this module makes logging request-aware in a way that works with async code like FastAPI.
  
Summary of what the file does:
| Part                     | Purpose                                                            |
| ------------------------ | ------------------------------------------------------------------ |
| `contextvars.ContextVar` | Stores the request ID in a way that survives across `await` calls. |
| `set_request_id()`       | Sets the request ID at the beginning of a request.                 |
| `get_request_id()`       | Gets the current request ID (if one is set).                       |
| `RequestIdFilter`        | Adds the request ID to every log record, so formatters can use it. |

-------------------------------------------------
Why use ContextVar?
-------------------------------------------------
When handling requests asynchronously (like with FastAPI), threading.local() doesn't work 
because multiple requests may share a thread. You need a way to store data per logical request, not per thread.

✅ Solution: contextvars.ContextVar
  - It keeps data isolated per request, even in async code.
  - It survives across await, yield, etc.
  - That makes it perfect for storing things like request_id.
  
-------------------------------------------------
Full Logging Flow with request_id
-------------------------------------------------
Here's a real-world step-by-step walkthrough:

1. HTTP request comes in
	```
	GET /users
	X-Request-ID: 123abc
	```

2. Middleware sets the request ID
	Inside your middleware (like in middleware.py), you do:
	```
	set_request_id("123abc")
	```
	That saves "123abc" into the ContextVar just for this request.

3. Logs are written during the request
	Anywhere in your code:
	```
	logger.info("Fetching user data")
	```

	This calls your formatter, but before that, the RequestIdFilter runs:
	```
	record.request_id = get_request_id() or "-"
	```

	So now the log record has:
	```
	record.request_id == "123abc"
	```
	Your JsonFormatter or ColorFormatter can now include that value in the output.
 

4. You get logs like:
	```
	2025-09-27 13:22:45 | INFO      | myapp.views.user        | 123abc     | Fetching user data
	```

	or JSON:
	```
	{
		"timestamp": "2025-09-27T13:22:45Z",
		"level": "INFO",
		"message": "Fetching user data",
		"request_id": "123abc"
	}
	```
 
5. If no request_id is set?
	You still get:
	```
	"request_id": "-"
	```
	This avoids KeyError in your format string ("%(request_id)s") and makes it obvious which logs were not part of a request.
 
-------------------------------------------------
Internals of RequestIdFilter.filter(record)
-------------------------------------------------
This part:
```
record.request_id = (
    getattr(record, "request_id", None) or get_request_id() or "-"
)
```
Does three things:
	1. If the log record already had a request_id (e.g. via extra={"request_id": "abc"}), use that.
	2. Else, try to pull from the contextvar.
	3. If none is set, use the default "-".
 
-------------------------------------------------
Where is this filter actually used?
-------------------------------------------------
In builder.py, when setting up logging with dictConfig, you'll see something like:
```
	"filters": {
		"request_id": {
			"()": RequestIdFilter,
		},
	},
	"handlers": {
		"console": {
			"class": "logging.StreamHandler",
			"filters": ["request_id"],  # <- Filter is applied here
			...
		}
	}
```

This tells Python's logging system: “Before emitting a log to the console, run it through RequestIdFilter.”

-------------------------------------------------
Testing Tip
-------------------------------------------------
You can test this manually like:
```
	import logging
	from app.config.settings import get_settings
	from app.core.logging import setup_logging
	from .filters import RequestIdFilter, set_request_id

	# Initialize settings and logging
	settings = get_settings()
	setup_logging(settings)

	# Use standard logging
	logger = logging.getLogger(__name__)
	# Add filter manually
	logger.addFilter(RequestIdFilter())

	# Set request id
	set_request_id("abc-123")

	# Log
	logger.debug("Debug message (only in development) if enabled in settings file or env var LOG_LEVEL=debug is set")
	logger.info("Info message")
	logger.warning("Warning message")
	logger.error("Error message")
	logger.critical("Critical message")
```

Output (with a formatter that includes %(request_id)s):
```
2025-09-27 12:00:00 | INFO | test | abc-123 | Hello!
```

-------------------------------------------------
The RequestIdFilter works anywhere in your code — as long as the `request_id` was set in the current async context
-------------------------------------------------
`RequestIdFilter` is global. Once it's added to your log handlers via dictConfig, 
it's applied to every log message, no matter where it comes from:
	- API routes ✅
	- Middleware ✅
	- Service layer ✅
	- Repository layer ✅
	- Exception handlers ✅
	- Anywhere else ✅

❗ But: It can only inject a `request_id` if one was previously set.
That happens in middleware, like:
	```
	set_request_id("abc-123")
	```

So how does this play out?
| Where you're logging                      | Will it have `request_id`? | Why?                                                                                                                             |
| ----------------------------------------  | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| ✅ API route (inside request)             | Yes                        | Middleware has already set the `request_id` in contextvars.                                                                      |
| ✅ Service/repository (called from route) | Yes                        | Same async context — it inherits the `request_id` automatically via `contextvars`.                                               |
| ✅ Exception handlers (FastAPI)           | Yes                        | Still in the request flow, so still same context.                                                                                |
| ❌ CLI script / startup code              | No (will show "-")         | No request context exists, so `set_request_id()` was never called. Filter falls back to `"-"` to avoid crashing.                 |
| ❌ Background task (not request-based)    | No (unless manually set)   | If the task isn’t spawned from a request, there’s no `request_id` unless you set it manually (e.g., from Celery or a scheduler). |


So when you're logging from the repository or exceptions layer, you still get the request ID if:
	- The log call is part of a FastAPI request.
	- And your middleware has already called set_request_id() for that request.
✅ This is the normal case for most web apps.

You can try it!
	In any repo layer file:
	```
		import logging
		logger = logging.getLogger(__name__)

		def get_user():
			logger.info("Getting user from DB")
	```
	If you call get_user() during a request to FastAPI — you'll see the `request_id` in your logs.
	If you call it from a test or CLI script, you'll see request_id: "-".
 
 
Bonus Tip: Want a custom request_id per background job?
	You can manually set it like:
	```
		set_request_id("job-42")
		logger.info("Starting scheduled cleanup task")
	```
	This will populate request_id: "job-42" in logs.
 
In short:
`RequestIdFilter` is not limited to API routes. It applies globally — to all log calls — but only injects a real `request_id` 
if one was set in the context using `set_request_id()` (typically via middleware in an HTTP request).

-------------------------------------------------
why is logging request_id useful?
-------------------------------------------------
Logging a request_id is one of the most important things you can do for debugging and observability 
in modern applications — especially web apps or microservices. Here's why:

1. Log correlation across the system
	When multiple log lines are generated for a single HTTP request (or background job), 
	the request_id allows you to group or filter all those logs together.
	Without it, logs look like a giant soup of unrelated messages.
	Example:
	```
	2025-09-27 12:00:01 | INFO     | auth.login             | abc123 | User login started
	2025-09-27 12:00:01 | DEBUG    | db.session             | abc123 | Executing SQL...
	2025-09-27 12:00:01 | INFO     | auth.login             | abc123 | Login successful
	```
	Now imagine 10 users logging in at once — without `request_id`, you'd never know which logs belong to which request.
 
2. End-to-end tracing in microservices
	If you pass the same request_id (or trace_id) across multiple services, you can:
		- Trace how a request flows through services A → B → C
		- Identify where delays or failures happen
		- Debug distributed issues
	This is often combined with tools like Jaeger, Zipkin, or OpenTelemetry.
 
3. Improves debugging
	When a user reports a bug or an error happens in production:
		- You can grep logs for `request_id: abc123`
		- Instantly see the full request lifecycle, DB calls, errors, etc.
	It's like a breadcrumb trail for the request.
 
4. Safety for async logs
	- In async systems (like FastAPI), logs from different requests can interleave — making it hard to understand what's happening.
	- request_id lets you untangle interleaved logs.
 
5. Structured logging / Log search
	In tools like:
		- ELK (Elasticsearch + Kibana)
		- Datadog
		- CloudWatch Logs Insights
		- Loki / Grafana
	You can easily run queries like:
		```
		filter request_id = "abc123"
		```
	Or visualize all logs per request in a timeline.
 
 
Real-World Use Case
	Imagine this scenario:
		1. User clicks "Place Order" → calls `/orders`
		2. Backend does:
			- Authenticate user
			- Validate cart
			- Charge payment
			- Save order
		3. Something fails.
	❌ Without request ID:
		- You have no idea which log lines belong to that order.
	✅ With request ID:
		- You can filter logs and see exactly what happened in that specific request — including:
			- Start time
			- DB queries
			- External API calls
			- Exceptions
			- Response time

TL;DR: Why log `request_id`?
| Benefit                           | Why it matters                                       |
| --------------------------------- | ---------------------------------------------------- |
| Log correlation                   | Trace all logs for a request                         |
| Async context tracking            | Untangle mixed logs in async servers (e.g., FastAPI) |
| Faster debugging                  | Find root cause of errors easily                     |
| Microservices tracing             | Follow request across services                       |
| Log search & filtering            | Enable queries in tools like ELK, Datadog            |
| Avoid KeyErrors in formatters     | Safe fallback for missing context                    |
"""















r"""
-------------------------------------------------
What is a logging filter?
-------------------------------------------------
A logging filter is just a class or function that gets a chance to inspect or modify each log record before it's emitted.

A logging filter is:
	- Subclasses `logging.Filter`
	- Has a `.filter(record: LogRecord) -> bool` method
	- Is called **before** the record is passed to formatters and handlers

It can:
	- Modify the record (e.g., inject fields like user_id)
	- Decide whether the record should be emitted (`True`) or dropped (`False`)

------------------------------------------------- 
Steps to Create a Custom Logging Filter:
-------------------------------------------------
1. Create a filter class
```
	Subclass logging.Filter and implement the filter(self, record: LogRecord) -> bool method.

	import logging
	from logging import LogRecord

	class UserIdFilter(logging.Filter):
		def filter(self, record: LogRecord) -> bool:
			record.user_id = getattr(record, "user_id", "anonymous")
			return True
```

2. Register the filter in your logging config (dictConfig)
```
	LOGGING = {
		"version": 1,
		"filters": {
			"user_id_filter": {
				"()": "myapp.logging.filters.UserIdFilter"
			},
		},
		"handlers": {
			"console": {
				"class": "logging.StreamHandler",
				"filters": ["user_id_filter"],
				...
			}
		},
		...
	}
```
The `"()"` key tells dictConfig how to instantiate the filter (as a callable/class).

3. Reference %(user_id)s in your formatter (optional)
```
	"formatters": {
		"standard": {
			"format": "%(asctime)s | %(levelname)s | %(user_id)s | %(message)s",
		},
	},
```

-------------------------------------------------
Common Examples of Useful Filters
-------------------------------------------------
1. RequestIdFilter: As you will see — injects `request_id` from context for log correlation.

2. UserIdFilter
	Adds the authenticated user ID to every log record.
	```
	record.user_id = get_current_user_id() or "anonymous"
	```
 
3. Adds the current environment (dev, staging, prod) to the log.
	```
	class EnvironmentFilter(logging.Filter):
		def __init__(self, env: str = "production"):
			self.env = env

		def filter(self, record: LogRecord) -> bool:
			record.env = self.env
			return True
	```
	You can inject env when you configure it in dictConfig.
 
4. ModuleFilter
	Only allow logs from a certain module or package:
	```
		class OnlyFromAuth(logging.Filter):
			def filter(self, record: LogRecord) -> bool:
				return record.name.startswith("app.auth")
	```
	This drops logs from other modules — useful when routing different logs to different files.

5. LevelRangeFilter
	Only include logs in a certain level range (e.g., WARNING to ERROR).
		```
		class LevelRangeFilter(logging.Filter):
			def __init__(self, min_level=logging.WARNING, max_level=logging.ERROR):
				self.min_level = min_level
				self.max_level = max_level

			def filter(self, record: LogRecord) -> bool:
				return self.min_level <= record.levelno <= self.max_level
		```
	Attach it to a handler to restrict which logs it handles.
 
6. MaskSensitiveDataFilter
	Scan the log message and redact sensitive info (e.g., passwords, tokens).
	```
	import re
	class MaskSensitiveDataFilter(logging.Filter):
		def filter(self, record: LogRecord) -> bool:
			message = record.getMessage()
			# naive masking — real impls use better regex
			message = re.sub(r'password=\S+', 'password=***', message)
			record.msg = message
			return True
	```

🛑 Filters vs Formatters vs Handlers — Know the Roles
| Component     | Responsibility                                        |
| ------------- | ----------------------------------------------------- |
| **Filter**    | Add/remove/modify log records before formatting       |
| **Formatter** | Define how the final string is built from the record  |
| **Handler**   | Sends the formatted log (e.g., to console, file, etc) |
"""

