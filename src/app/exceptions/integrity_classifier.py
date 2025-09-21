import logging
from enum import Enum
from typing import Type
from .base import DuplicateError
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


# =================================================================================================================
# Base repository exceptions
# =================================================================================================================

class RepositoryError(Exception):
    """Base exception for repository operations."""
    pass


class ConstraintViolationError(RepositoryError):
    """Base for integrity/constraint violations (subclass of RepositoryError)."""
    pass


# =================================================================================================================
# Constraint-specific exceptions
# =================================================================================================================

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

    # print("PGCODE:", pgcode)
    # print("Constraint Name:", constraint_name)

    exception_class = PGCODE_EXCEPTION_MAP.get(pgcode)
    if exception_class:
        return exception_class, constraint_name

    logger.warning(f"Unknown Postgres integrity error code encountered: {pgcode}")
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

    logger.warning(f"Unknown integrity error message encountered: {msg}")
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



def map_integrity_error_to_app_exception(
    exc: IntegrityError,
    model_name: str,
    operation: str = "creating"
) -> RepositoryError:
    """
    Maps a classified IntegrityError to a domain-specific app exception,
    and logs the classification details.

    Args:
        exc: The original SQLAlchemy IntegrityError
        model_name: The name of the model being affected
        operation: A string like "creating", "updating" (for logs)

    Returns:
        An appropriate app-level RepositoryError
    """
    exc_cls, constraint_name = classify_integrity_error(exc)

    # Centralized logging for consistency
    logger.error(
        "IntegrityError while %s %s: %s; classified_as=%s; constraint=%s",
        operation, model_name, exc, exc_cls.__name__, constraint_name
    )

    base_msg = f"{operation} {model_name}"
    constraint_info = f" (constraint={constraint_name})" if constraint_name else ""

    if exc_cls is UniqueConstraintError:
        return DuplicateError(f"{model_name} already exists{constraint_info}")

    if exc_cls is NotNullConstraintError:
        return RepositoryError(f"Missing required field when {base_msg}")

    if exc_cls is ForeignKeyConstraintError:
        return RepositoryError(f"Referenced entity not found during {base_msg}")

    if exc_cls is CheckConstraintError:
        return RepositoryError(f"Check constraint violated during {base_msg}")

    # Fallback
    return RepositoryError(f"Database integrity error during {base_msg}")



"""
# =================================================================================================================
# Why This Design Is Professional
# =================================================================================================================
1. Clear Separation of Concerns
    - The code separates exception definitions from classification logic.
    - Within classification, it further splits:
        - Postgres-specific error classification (_classify_postgres_integrity_error)
        - Generic error message parsing (_classify_generic_integrity_error)
    - This modularization helps:
        - Readability — each function does one thing
        - Maintainability — easy to update one part without breaking others
        - Testability — smaller units to test independently

2. Extensibility & Open/Closed Principle (SOLID)
    - By mapping Postgres codes to specific exception classes using a dictionary (PGCODE_EXCEPTION_MAP), 
      you can add support for new error codes or DB engines without changing existing logic, just by extending 
      the map or adding new helper functions.
    - The exception classes form a clear hierarchy — you can add new constraint error types easily.

3. Use of Constants for Magic Values
    - PostgreSQL error codes ("23505", "23502", etc.) are placed in a dedicated class (`PostgresErrorCodes`).
    - This removes "magic strings" scattered throughout the code.
    - Benefits include:
        - Easier to understand what each code means.
        - Less risk of typos.
        - Centralized updates.
        
4. Use of Typing & Documentation
    - Type hints clarify input/output types, helping both developers and IDEs/static analyzers.
    - Docstrings document intent, input/output, and behavior clearly.
    - This improves maintainability and onboarding new developers.
    
5. Pragmatic Fallback Handling
    - Not all databases provide structured error codes (like Postgres).
    - Generic message parsing fallback covers these cases, improving robustness across different DB backends.
    - This shows awareness of real-world variability in DB drivers.
    
6. Logging for Unknown Cases
    - Logging warnings when an unknown error code or message is encountered supports:
    - Observability — helps diagnose missing cases
    - Continuous improvement — you can refine classification based on logs
    
7. Exception Hierarchy Enables Expressive Error Handling
    Defining custom exceptions like UniqueConstraintError allows calling code to:
        - Catch specific errors for precise handling (e.g., show user-friendly "duplicate username" messages)
        - Separate DB-specific errors from generic app errors
        - Avoid leaking raw DB exceptions to upper layers (encapsulation)
"""
