# src/app/core/logging/middleware.py
"""
Request ID middleware for FastAPI / Starlette.

Purpose
-------
This middleware ensures each incoming HTTP request is associated with a
unique request identifier (request_id) that gets propagated to log records
via the RequestIdFilter (contextvar). The request id is also returned to the
client in the `X-Request-ID` response header so external systems (or humans)
can correlate logs and traces with a particular HTTP interaction.

How it works (high level)
-------------------------
1. On each request the middleware looks for an incoming `X-Request-ID` header.
   - If present, it uses that value (useful when a client or upstream proxy
     already provided a correlation id).
   - Otherwise it generates a new UUID4 string.
2. It calls `set_request_id(rid)` which stores the id in a `contextvars.ContextVar`.
   - This context var is available to the RequestIdFilter which attaches the id
     to each `LogRecord`.
3. The request is forwarded to the application via `call_next(request)`.
4. Before returning, the middleware ensures the `X-Request-ID` header is present
   on the response so clients and logs can be correlated.

Integration notes
-----------------
- Register this middleware with FastAPI early (before routers that may emit logs).
  Example:
      app.add_middleware(RequestIDMiddleware)

- Ensure the RequestIdFilter is installed into your logging config so log records
  produced during a request carry `request_id`. See `filters.py` and `builder.py`.

Security & validation
---------------------
- Do not blindly trust `X-Request-ID` values provided by upstream sources.
  Consider validating its format (e.g., UUID format) to avoid log injection or
  very long values. If invalid, either sanitize it or generate a fresh UUID.
- Avoid deriving the request id from any sensitive data (tokens, credentials).
  The id should be a random/opaque value.

Concurrency model
-----------------
- We use `contextvars` to store the request id; this works correctly with asyncio
  and FastAPI/Starlette — each concurrent request has its own logical context.
- If you spawn background tasks that should inherit the same request id,
  ensure they are created in the same context (the default behavior of asyncio.create_task
  preserves contextvars in modern Python). If you use threading, contextvars will not
  automatically cross thread boundaries.

Testing tips
------------
- Unit test middleware by simulating a Request object with and without `X-Request-ID`
  and asserting:
    * `set_request_id` was called with the expected value
    * response contains `X-Request-ID` header
- Integration test: run an app instance, call an endpoint, capture logs, assert
  logs for that request include the same request id that the response returned.

Possible improvements
---------------------
- Validate incoming header value (e.g., must be a UUID) and sanitize if needed.
- Clear the contextvar after handling the request (use a `try/finally`) to be explicit
  about lifecycle — not strictly necessary in typical async frameworks but good for clarity.
- Offer a pluggable generator function (e.g., settings.REQUEST_ID_GENERATOR) so teams
  can implement different formats (UUID, snowflake, trace-id).

Below is the current implementation with helpful inline comments.
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from .filters import set_request_id, reset_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Starlette / FastAPI middleware that sets a request id for each incoming request.

    Notes:
      - Uses header 'X-Request-ID' when provided; otherwise generates a new UUID4.
      - Calls set_request_id() (from filters.py) to store the id in a contextvar so
        the RequestIdFilter can attach it to LogRecords.
      - Adds the same id to the response header 'X-Request-ID' for external correlation.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Dispatch a request.

        Args:
            request: Starlette Request object.
            call_next: function that executes the next handler in the chain and returns a Response.

        Returns:
            Response: The response from downstream application, with X-Request-ID header set.
        """
        # 1) Prefer an incoming header if present (useful for end-to-end correlation).
        #    If absent, generate a new opaque UUID4 string.
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # 2) Store the id in the contextvar so RequestIdFilter can pick it up.
        #    This effectively attaches the id to the current async context.
        token = set_request_id(rid)

        try:
            # 3) Forward the request to the application and obtain the response.
            #    We intentionally do not wrap call_next in try/except here because:
            #      - we want exceptions to propagate to the framework (and error handlers)
            #      - but adding a try/finally to clear the contextvar is a good practice.
            response = await call_next(request)

            # 4) Ensure the response includes X-Request-ID so clients see the correlation id.
            response.headers["X-Request-ID"] = rid

            # 5) Return the response to the client.
            return response

        finally:
            # 6) Reset the request_id contextvar in middleware
            reset_request_id(token)


# ---- Optional improved variant (recommended) ----
#
# The above implementation works, but the following version is slightly safer:
# - It wraps the call_next in try/finally to ensure any cleanup (clearing the contextvar)
#   happens even when downstream raises an exception.
# - It optionally validates the incoming header to ensure it's a valid UUID string.
#
# You can substitute this into the class above if you prefer the extra safety.
#
# Example:
#
# class RequestIDMiddleware(BaseHTTPMiddleware):
#     async def dispatch(self, request: Request, call_next):
#         incoming = request.headers.get("X-Request-ID")
#         if incoming:
#             # Simple validation: accept only UUID-like values; otherwise ignore
#             try:
#                 # This will raise ValueError if not a valid UUID string
#                 _ = uuid.UUID(incoming)
#                 rid = incoming
#             except ValueError:
#                 rid = str(uuid.uuid4())
#         else:
#             rid = str(uuid.uuid4())
#
#         set_request_id(rid)
#         try:
#             response = await call_next(request)
#             response.headers["X-Request-ID"] = rid
#             return response
#         finally:
#             # Clear the contextvar explicitly to avoid any accidental leakage.
#             set_request_id(None)
#
# Note: clearing the contextvar with None is optional because a new request will
# overwrite it. However, being explicit can help in tests and long-running tasks.
