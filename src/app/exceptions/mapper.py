import re
import logging
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .integrity_classifier import (
    classify_integrity_error,
    UniqueConstraintError,
    NotNullConstraintError,
    ForeignKeyConstraintError,
    CheckConstraintError,
)
from .base import DuplicateError, RepositoryError

logger = logging.getLogger(__name__)

# -----------------------
# Column extraction helpers
# -----------------------

def _extract_columns_postgres(msg: str) -> list[str] | None:
    """
    Try to extract involved column names from common Postgres messages:
      - 'null value in column "username" violates not-null constraint'
      - 'DETAIL:  Key (email, username)=(a@b.com, u) already exists.'
    """
    if not msg:
        return None

    # Not-null pattern: null value in column "username"
    m = re.search(r'null value in column "(?P<col>[^"]+)"', msg, flags=re.IGNORECASE)
    if m:
        return [m.group("col")]

    # Key (col1, col2)=(...)
    m = re.search(r'key \((?P<cols>[^)]+)\)=', msg, flags=re.IGNORECASE)
    if m:
        return [c.strip().strip('"') for c in m.group("cols").split(",")]

    return None


def _extract_columns_sqlite(msg: str) -> list[str] | None:
    # SQLite: 'UNIQUE constraint failed: users.email'
    m = re.search(r'UNIQUE constraint failed: (?P<cols>.+)$', msg, flags=re.IGNORECASE)
    if m:
        cols = [c.split('.')[-1].strip() for c in re.split(r',\s*', m.group("cols"))]
        return cols

    # NOT NULL: 'NOT NULL constraint failed: users.email'
    m = re.search(r'NOT NULL constraint failed: (?P<cols>.+)$', msg, flags=re.IGNORECASE)
    if m:
        cols = [c.split('.')[-1].strip() for c in re.split(r',\s*', m.group("cols"))]
        return cols

    return None


def _extract_columns_mysql(msg: str) -> list[str] | None:
    # MySQL-ish: "Duplicate entry 'foo' for key 'idx_users_email'"
    m = re.search(r"for key '? (?P<key>[^']+)'?", msg, flags=re.IGNORECASE)
    if m:
        key = m.group("key")
        return [key]
    # fallback: try simpler match
    m2 = re.search(r"Duplicate entry .* for key '?([^']+)'?", msg, flags=re.IGNORECASE)
    if m2:
        return [m2.group(1)]
    return None


def extract_columns_from_integrity(exc: IntegrityError) -> list[str] | None:
    """
    Best-effort extraction of column names from the DB message (Postgres, SQLite, MySQL).
    """
    orig = exc.orig
    msg = str(orig) if orig is not None else str(exc)

    cols = _extract_columns_postgres(msg)
    if cols:
        return cols

    cols = _extract_columns_sqlite(msg)
    if cols:
        return cols

    cols = _extract_columns_mysql(msg)
    if cols:
        return cols

    return None


# -----------------------
# Mapper
# -----------------------

def raise_mapped_integrity_error(exc: IntegrityError, model_name: str | None = None) -> None:
    """
    Map a SQLAlchemy IntegrityError to an app-level exception and raise it.
    Populates `.fields` and `.constraint` where possible.
    """
    exc_cls, constraint_name = classify_integrity_error(exc)
    columns = extract_columns_from_integrity(exc)

    model_part = f"{model_name}" if model_name else "Record"

    # UNIQUE / Duplicate
    if exc_cls is UniqueConstraintError:
        # Log at INFO because duplicate errors are expected client-level scenarios
        # (they result in a 409 conflict). We include structured minimal context:
        logger.info(
            "mapper.duplicate_detected",
            extra={
                "model": model_part,
                "fields": columns,
                "constraint": constraint_name,
            },
        )
        if columns:
            raise DuplicateError(f"{model_part} already exists for field(s): {', '.join(columns)}", fields=columns, constraint=constraint_name)
        if constraint_name:
            raise DuplicateError(f"{model_part} already exists (constraint: {constraint_name})", fields=None, constraint=constraint_name)
        raise DuplicateError(f"{model_part} already exists (unique constraint)", fields=None, constraint=constraint_name)

    # NOT NULL / Missing required field
    if exc_cls is NotNullConstraintError:
        
        # Not-found of required input -> safe to return RepositoryError; log at INFO
        logger.info(
            "mapper.not_null_violation",
            extra={"model": model_part, "fields": columns, "constraint": constraint_name},
        )

        if columns:
            raise RepositoryError(f"Missing required field(s): {', '.join(columns)} for {model_part}", fields=columns, constraint=constraint_name)
        if constraint_name:
            raise RepositoryError(f"Missing required field for {model_part} (constraint: {constraint_name})", fields=None, constraint=constraint_name)
        raise RepositoryError(f"Missing required field for {model_part}")

    # FOREIGN KEY
    if exc_cls is ForeignKeyConstraintError:
        logger.info(
            "mapper.foreign_key_violation",
            extra={"model": model_part, "fields": columns, "constraint": constraint_name},
        )

        if columns:
            raise RepositoryError(f"{model_part} referenced entity not found for field(s): {', '.join(columns)}", fields=columns, constraint=constraint_name)
        if constraint_name:
            raise RepositoryError(f"{model_part} foreign key violation (constraint: {constraint_name})", fields=None, constraint=constraint_name)
        raise RepositoryError(f"{model_part} foreign key constraint violated")

    # CHECK
    if exc_cls is CheckConstraintError:
        raw = str(exc.orig) if exc.orig is not None else str(exc)
        # Keep the raw DB message at DEBUG level only (do not expose it at INFO)
        logger.debug(
            "mapper.check_constraint_failure",
            extra={"model": model_part, "raw": raw, "constraint": constraint_name},
        )
        # Raise a safe message only (no raw DB text)
        raise RepositoryError(
            f"{model_part} business rule violated (check constraint).", fields=None, constraint=constraint_name
        )

    # Unknown/unclassified integrity error
    raw = str(exc.orig) if exc.orig is not None else str(exc)
    # Warn that an unknown integrity error occurred; include minimal context at WARNING
    logger.warning(
        "mapper.unknown_integrity_error",
        extra={"model": model_part, "constraint": constraint_name},
    )
    # For debugging purposes (developer workflows), include the raw DB message at DEBUG.
    logger.debug("mapper.unknown_integrity_raw", extra={"model": model_part, "raw": raw})

    # Raise a generic, non-leaking message
    raise RepositoryError(f"{model_part} database integrity error.") from exc


# -----------------------
# Async context manager to DRY error handling in repositories
# -----------------------
@asynccontextmanager
async def db_error_handler(db: AsyncSession, model_name: str | None = None):
    """
    Usage:
        async with db_error_handler(self.db, self.model.__name__):
            ... DB ops that may raise IntegrityError ...
    This will rollback on error and raise a mapped app-level exception.
    """
    try:
        yield
    except IntegrityError as exc:
        try:
            await db.rollback()
        except Exception:
            # If rollback fails, that is unusual — log exception (with stack) at ERROR.
            logger.exception("Failed to rollback session after IntegrityError", extra={"model": model_name})
        # Map and raise a friendly, sanitized app-level exception
        raise_mapped_integrity_error(exc, model_name)
    except Exception as exc:
        # Attempt rollback; log and re-raise a RepositoryError.
        try:
            await db.rollback()
        except Exception:
            # Log rollback failure
            logger.exception("Failed to rollback session after unexpected error", extra={"model": model_name})

        # Unexpected exceptions are logged with stack trace for diagnostics.
        # Include structured 'model' context so logs can be filtered / alerted on.
        logger.exception("Unexpected DB error for %s", model_name, extra={"model": model_name})
        # Convert to a generic RepositoryError to avoid leaking internals to callers.
        raise RepositoryError(f"Failed to operate on {model_name or 'database'}") from exc
