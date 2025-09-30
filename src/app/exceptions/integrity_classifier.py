import logging
from enum import Enum
from typing import Type
from sqlalchemy.exc import IntegrityError
from .base import RepositoryError

logger = logging.getLogger(__name__)

# =================================================================================================================
# Constraint-specific exceptions
# =================================================================================================================


class ConstraintViolationError(RepositoryError):
    """Base for integrity/constraint violations (subclass of RepositoryError)."""
    pass


class UniqueConstraintError(ConstraintViolationError):
    """Unique constraint / duplicate value."""
    pass


class NotNullConstraintError(ConstraintViolationError):
    """NOT NULL violation (missing required field)."""
    pass


class ForeignKeyConstraintError(ConstraintViolationError):
    """Foreign key constraint violated."""
    pass


class CheckConstraintError(ConstraintViolationError):
    """CHECK constraint violated."""
    pass


class UnknownIntegrityError(ConstraintViolationError):
    """Unrecognized integrity error."""
    pass


# =================================================================================================================
# Postgres error code mapping
# =================================================================================================================

# https://www.postgresql.org/docs/current/errcodes-appendix.html
class PostgresErrorCodes(str, Enum):
    UNIQUE_VIOLATION = "23505"
    NOT_NULL_VIOLATION = "23502"
    FOREIGN_KEY_VIOLATION = "23503"
    CHECK_VIOLATION = "23514"


PGCODE_EXCEPTION_MAP = {
    PostgresErrorCodes.UNIQUE_VIOLATION: UniqueConstraintError,
    PostgresErrorCodes.NOT_NULL_VIOLATION: NotNullConstraintError,
    PostgresErrorCodes.FOREIGN_KEY_VIOLATION: ForeignKeyConstraintError,
    PostgresErrorCodes.CHECK_VIOLATION: CheckConstraintError,
}


# =================================================================================================================
# Integrity Error Classifiers
# =================================================================================================================

def _match_any(msg: str, keywords: list[str]) -> bool:
    return any(keyword in msg for keyword in keywords)


def _classify_from_postgres_diag(orig) -> tuple[Type[ConstraintViolationError], str | None]:
    """
    Classify Postgres integrity error based on pgcode and diagnostics.
    """
    pgcode = getattr(orig, "pgcode", None)
    if not pgcode:
        return None, None

    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) if diag else None

    exception_class = PGCODE_EXCEPTION_MAP.get(pgcode)

    if exception_class:
        # Debug-level diagnostic: includes pgcode and constraint_name.
        # DEBUG chosen because it may contain implementation/runtime details and
        # is useful during development / troubleshooting but noisy in production.
        logger.debug("Postgres integrity diagnostic", 
                    extra={"pgcode": pgcode, "constraint_name": constraint_name}
        )  
        
        return exception_class, constraint_name

    # Unknown pgcode: warn (noticeable) but keep raw diagnostics at DEBUG only.
    logger.warning(
        "Unknown Postgres integrity error code encountered",
        extra={"pgcode": pgcode, "constraint_name": constraint_name}
    )

    # If we need raw orig for deeper debugging, it's available at DEBUG:
    logger.debug("Postgres orig diagnostic (raw)", extra={"orig_repr": repr(orig)})

    return UnknownIntegrityError, constraint_name


def _classify_from_generic_message(msg: str) -> tuple[Type[ConstraintViolationError], None]:
    """
    Classify integrity error based on message content (fallback for SQLite, MySQL, etc).
    """
    normalized = msg.lower()

    if _match_any(normalized, ["unique constraint", "unique failed", "unique violation", "duplicate"]):
        return UniqueConstraintError, None

    if _match_any(normalized, ["not null constraint", "not null", "null value in column"]):
        return NotNullConstraintError, None

    if _match_any(normalized, ["foreign key constraint", "foreign key", "is not present in table"]):
        return ForeignKeyConstraintError, None

    if _match_any(normalized, ["check constraint", "check failed"]):
        return CheckConstraintError, None

    # Unknown generic message - warn so it surfaces to monitoring
    logger.warning("Unknown integrity error message encountered", extra={"message_snippet": (msg or "")[:200]})
    # Keep full message at DEBUG for developers (don't expose raw DB messages at INFO)
    logger.debug("Unknown integrity raw message", extra={"raw": msg})
    return UnknownIntegrityError, None


def classify_integrity_error(exc: IntegrityError) -> tuple[Type[ConstraintViolationError], str | None]:
    """
    Heuristically classify a SQLAlchemy IntegrityError into a specific ConstraintViolationError subclass.

    Returns:
        A tuple of (ExceptionClass, constraint_name if available)
    """
    orig = exc.orig

    # Prefer Postgres-specific classification
    exception_class, constraint_name = _classify_from_postgres_diag(orig)

    if exception_class is not None:
        return exception_class, constraint_name

    # Fallback to generic message parsing
    return _classify_from_generic_message(str(orig))
