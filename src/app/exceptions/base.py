class RepositoryError(Exception):
    """Base exception for repository operations."""
    pass


class NotFoundError(RepositoryError):
    """Raised when a requested entity is not found."""
    pass


class DuplicateError(RepositoryError):
    """Raised when trying to create a duplicate entity."""
    pass





r"""
# =================================================================================================================
# Two Levels of Exception Handling
# =================================================================================================================

🧱 1. Constraint-specific errors (low-level, technical classification)
```
    class ConstraintViolationError(RepositoryError): ...
    class UniqueConstraintError(ConstraintViolationError): ...
    class NotNullConstraintError(ConstraintViolationError): ...
    class ForeignKeyConstraintError(ConstraintViolationError): ...
    class CheckConstraintError(ConstraintViolationError): ...
    class UnknownIntegrityError(ConstraintViolationError): ...
```
These are used only internally inside your repository code to classify the IntegrityError (from SQLAlchemy). 
They represent "what exactly failed in the database", and are not intended to be directly raised to the user.

    - Think of them as error classifiers, like tags or internal labels.
    
    - You never raise them to the outside world (e.g., API, UI).

    - Example: SQLAlchemy raises an IntegrityError, and you figure out it's a `UniqueConstraintError`.

Used internally only in classify_integrity_error(...).


🏛️ 2. App-level errors (public API for your repository layer)
```
    class RepositoryError(Exception): ...
    class DuplicateError(RepositoryError): ...
    class NotFoundError(RepositoryError): ...
```

These are user-facing or app-facing errors, designed to be:
    - Raised from your `BaseRepository` methods
    - Caught by services, FastAPI handlers, or tests
    - Understood by the rest of your application
    - Mapped into HTTP responses like 409 Conflict, 404 Not Found, etc.

These are the real exceptions your app should raise and handle.


Analogy: Internal Classification vs. Public Interface
Think of this like a security scanner:
    - Scanner internals detects: "buffer overflow", "SQL injection", "race condition" (like `UniqueConstraintError`, etc.)
    - Scanner results present: "High Severity", "Duplicate Entry", "Invalid Input" (like DuplicateError, RepositoryError)
The scanner internally classifies the issue, but presents a general message the user or system can act on.


How They Work Together in Your Code ?
You classify the raw SQL error:
```
    # internally used to classify the error
    exc_cls, constraint_name = classify_integrity_error(e)
```

This gives you one of:
```
    UniqueConstraintError
    NotNullConstraintError
```
etc.

Then you map that to an app-level exception:
```
    if exc_cls is UniqueConstraintError:
        raise DuplicateError(...) from e
    elif exc_cls is NotNullConstraintError:
        raise RepositoryError("Missing required field")
    # ...
    else:
        raise RepositoryError("Unknown DB error")
```

So:
| Constraint-level (internal) | → | App-level (external)                   |
| --------------------------- | - | -------------------------------------- |
| `UniqueConstraintError`     | → | `DuplicateError`                       |
| `NotNullConstraintError`    | → | `RepositoryError("Missing ...")`       |
| `ForeignKeyConstraintError` | → | `RepositoryError("Ref ...")`           |
| `CheckConstraintError`      | → | `RepositoryError("Business rule ...")` |


Why Not Raise the Constraint Exceptions Directly?
You could, but there are good reasons not to:
    - Encapsulation: App logic shouldn't depend on DB-specific constraint names or types.
    - Abstraction: You want a clean repository interface (DuplicateError, etc.) that's stable even if you switch databases.
    - Consistency: Your API/clients just want to know: "Is it a duplicate?", not whether it came from a unique index 
      or some other mechanism.
    - Testability: Your tests should assert that app-level exceptions are raised. They shouldn't need to know SQL error 
      codes or low-level details.
      

Summary: Use Each Where It Belongs
| Exception Type                | Purpose                                | Where It's Used                              |
| ----------------------------- | -------------------------------------- | -------------------------------------------- |
| `UniqueConstraintError`, etc. | Internal classifier (DB-level details) | Only in `classify_integrity_error()`         |
| `DuplicateError`, etc.        | Public-facing errors                   | Raised from repository methods               |
| `RepositoryError`             | Catch-all for DB-related errors        | Raised for unknown cases or generic failures |
"""
