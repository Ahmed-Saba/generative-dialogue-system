# app/api/error_handlers.py
"""
FastAPI exception handlers that map repository-level exceptions to HTTP responses.

How to use:
    - Import and register these handlers in your FastAPI app startup (see example below).
    - Repositories raise app.exceptions.base.* exceptions (DuplicateError, InvalidFieldError, ...)
    - These handlers produce stable JSON payloads (via .to_payload()) and correct HTTP codes (via .http_status()).
"""

from fastapi import Request
from fastapi.responses import JSONResponse
import logging
from app.exceptions.base import (
    RepositoryError, 
    DuplicateError, 
    InvalidFieldError, 
    NotFoundError
)

logger = logging.getLogger(__name__)


# Most specific first (DuplicateError, InvalidFieldError, NotFoundError)
# These handlers are intentionally tiny — mapping is centralized in exception classes.

async def duplicate_error_handler(request: Request, exc: DuplicateError) -> JSONResponse:
    """
    409 Conflict for duplicates.
    Payload: exc.to_payload() -> {"detail": "...", "code": "duplicate", "fields": [...]}
    """
    # Log the event for observability (do not log raw DB messages here)
    logger.info("DuplicateError for %s %s: fields=%s", request.method, request.url, exc.fields)
    return JSONResponse(status_code=exc.http_status(), content=exc.to_payload())


async def invalid_field_handler(request: Request, exc: InvalidFieldError) -> JSONResponse:
    """
    422 Unprocessable Entity for unexpected fields.
    """
    logger.info("InvalidFieldError for %s %s: fields=%s", request.method, request.url, exc.fields)
    return JSONResponse(status_code=exc.http_status(), content=exc.to_payload())


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """
    404 Not Found.
    """
    logger.info("NotFoundError for %s %s: fields=%s", request.method, request.url, exc.fields)
    return JSONResponse(status_code=exc.http_status(), content=exc.to_payload())


async def repository_error_handler(request: Request, exc: RepositoryError) -> JSONResponse:
    """
    Fallback for general repository errors -> 400 by default (or code-defined status).
    Keep the message user-friendly; do not include DB internals.
    """
    # Log stack / details at warning level for later triage
    logger.warning("RepositoryError for %s %s: %s", request.method, request.url, str(exc))
    return JSONResponse(status_code=exc.http_status(), content=exc.to_payload())


# Helper to register all handlers on an app (call this from your app factory)
def register_exception_handlers(app):
    app.add_exception_handler(DuplicateError, duplicate_error_handler)
    app.add_exception_handler(InvalidFieldError, invalid_field_handler)
    app.add_exception_handler(NotFoundError, not_found_handler)
    app.add_exception_handler(RepositoryError, repository_error_handler)

"""
---------------------------------------------------------
Register handlers in your FastAPI app (example):
---------------------------------------------------------
In your app factory (e.g., app/main.py or app/api/__init__.py):
```
from fastapi import FastAPI
from app.api.error_handlers import register_exception_handlers

def create_app() -> FastAPI:
    app = FastAPI()
    # ... router includes, middleware, etc.

    # Register our exception handlers
    register_exception_handlers(app)

    return app
```

---------------------------------------------------------
Quick example route & repository integration
---------------------------------------------------------
Repository raises DuplicateError:
```
# in repository (already done)
raise DuplicateError("User already exists", fields=["email"])
```

Route handler:
```
from fastapi import APIRouter, Depends
from app.repositories.user_repository import UserRepository

router = APIRouter()

@router.post("/users")
async def create_user(payload: UserCreateSchema, repo: UserRepository = Depends(get_user_repo)):
    # repo.create_user will raise DuplicateError / InvalidFieldError etc.
    user = await repo.create_user(**payload.dict())
    return {"id": str(user.id)}
```

If the repo raises DuplicateError, the client gets HTTP 409 and body:
```
{
  "detail": "User already exists",
  "code": "duplicate",
  "fields": ["email"]
}
```
"""
