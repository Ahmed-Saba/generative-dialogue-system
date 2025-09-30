"""
Base repository class providing common database operations.

This class serves as a reusable foundation for repositories that interact with 
the database using SQLAlchemy's async sessions.

It defines common CRUD operations that are likely to be used across many models, 
helping reduce code duplication. 

While model-specific repositories can inherit from this base class to reuse 
generic logic, they are also free to implement their own custom queries and 
methods as needed.

Unlike abstract base classes, `BaseRepository` does not enforce any required methods — 
it simply provides optional, shared functionality that can be extended.
"""
from app.exceptions.base import (
    RepositoryError,
    DuplicateError,
    NotFoundError,
    InvalidFieldError
)

from app.exceptions.mapper import db_error_handler
from app.validators.exception_validators import find_unknown_model_kwargs, get_required_columns, find_unique_conflicts

import time
from typing import TypeVar, Generic, Type, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
import logging

from app.database.base import Base

# Type variable for the model class
ModelType = TypeVar("ModelType", bound=Base)

# Setup logging
logger = logging.getLogger(__name__)


# helper: mask sensitive keys if you ever need to log values (avoid logging raw secrets)
_SENSITIVE_KEYS = {"password", "secret", "token", "access_token", "refresh_token", "ssn"}

def _mask_sensitive(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Return a shallow copy with sensitive values replaced by '***'.
    Only use for low-volume debug logs; prefer logging keys or counts otherwise.
    """
    out = {}
    for k, v in payload.items():
        if k.lower() in _SENSITIVE_KEYS:
            out[k] = "***"
        else:
            out[k] = v
    return out



class BaseRepository(Generic[ModelType]):
    """
    Generic base repository providing common CRUD operations.

    This class implements the Repository pattern, providing a clean interface
    for database operations. All specific repositories should inherit from this class.

    Type Parameters:
        ModelType: The SQLAlchemy model class this repository manages.
    """

    def __init__(self, model: Type[ModelType], db: AsyncSession):
        """
        Initialize the repository.

        Args:
            model: The SQLAlchemy model class
            db: The async database session

        Notes:
            model: Type[ModelType]: this expects a model class itself (not an instance), e.g., User, not User().
            Needed for constructing queries dynamically: select(self.model), update(self.model), etc.

            db: AsyncSession: the async database session injected (usually via FastAPI dependency).
            Needed for executing queries like await db.execute(...), committing, flushing, etc.
        """
        self.model = model
        self.db = db

    # =================================================================================================================
    # Basic Create Operations
    # =================================================================================================================

    async def create(self, **kwargs) -> ModelType:
        """
        Create an entity with validation + DB write. Logging:
        - DEBUG: start event with model name and provided keys (not values).
        - INFO: expected domain errors (invalid fields, missing required, duplicate).
        - INFO: success event with created id and duration_ms.
        - EXCEPTION: unexpected errors with stack trace.
        """
        # debug: show operation start and which keys were provided (safe)
        logger.debug(
            "repo.create.start",
            extra={
                "model": self.model.__name__,
                "operation": "create",
                # list keys only (avoids sensitive values), helpful to spot incorrect callers
                "provided_keys": sorted(list(kwargs.keys())),
            },
        )


        # 1) unknown fields check (existing)
        unknown = find_unknown_model_kwargs(self.model, kwargs)
        if unknown:
            # INFO: client-level validation error; expected input problem -> no stack trace
            logger.info(
                "repo.create.invalid_fields",
                extra={
                    "model": self.model.__name__,
                    "operation": "create",
                    "invalid_fields": sorted(unknown),
                },
            )
            raise InvalidFieldError(f"Unknown field(s) for {self.model.__name__}: {', '.join(unknown)}", fields=unknown)

        # 2) required fields check (detect all missing)
        required_cols = get_required_columns(self.model)
        # consider missing if not provided or explicitly None (since NOT NULL)
        missing = [c for c in required_cols if (c not in kwargs) or (kwargs.get(c) is None)]
        if missing:
            # INFO: missing input - expected client error
            logger.info(
                "repo.create.missing_required",
                extra={
                    "model": self.model.__name__,
                    "operation": "create",
                    "missing_fields": sorted(missing),
                },
            )
            raise RepositoryError(f"Missing required field(s): {', '.join(missing)} for {self.model.__name__}", fields=missing)

        # 3) pre-check unique conflicts (best-effort)
        conflicts = await find_unique_conflicts(self.db, self.model, kwargs)
        if conflicts:
            # INFO: duplicate detected during pre-check. Provide fields for observability.
            logger.info(
                "repo.create.duplicate_precheck",
                extra={
                    "model": self.model.__name__,
                    "operation": "create",
                    "conflict_fields": sorted(conflicts),
                },
            )
            raise DuplicateError(f"{self.model.__name__} already exists for field(s): {', '.join(sorted(conflicts))}", fields=sorted(conflicts))

        # 4) Actual DB write with fallback mapping on integrity errors
        start = time.perf_counter()

        async with db_error_handler(self.db, self.model.__name__):
            entity = self.model(**kwargs)
            self.db.add(entity)
            await self.db.flush()
            await self.db.refresh(entity)
                
            duration_ms = int((time.perf_counter() - start) * 1000)
            # INFO: creation success; include id and duration. Avoid including full entity data.
            logger.info(
                "repo.create.success",
                extra={
                    "model": self.model.__name__,
                    "operation": "create",
                    "id": getattr(entity, "id", None),
                    "duration_ms": duration_ms,
                },
            )

            return entity

        # ------------------------------------------------------------------------
        # `flush()` vs `commit()`: Why We Use `flush`, Not `commit`
        # ------------------------------------------------------------------------
        # `flush()`: Sends the SQL to the DB, but doesn't finalize it
        #     - It pushes pending changes (like INSERT, UPDATE) to the database within the transaction, but does not commit the transaction.
        #     - It lets you get things like auto-generated primary keys, foreign key validations, etc., early — without making the change permanent yet.

        #     Use case:
        #         ```
        #         await db.flush()
        #         print(user.id)  # Now available
        #         ```

        # `commit()`: Ends the transaction — permanently saves changes
        #     - `commit()` finalizes all operations in the session and writes them permanently to the database.
        #     - Once you `commit`, you're done with that transaction — any rollback or change has to start a new one.

        #     🛑 Why We Avoid commit() in Repositories
        #         - Separation of concerns: You want your repository layer to handle only what happens (like create, update), not when it gets saved permanently.
        #         - Commit is usually done in the service layer or FastAPI dependency using a pattern like:
        #         ```
        #         @router.post("/users/")
        #         async def create_user(..., db: AsyncSession = Depends(get_db)):
        #             try:
        #                 user = await user_repo.create(...)
        #                 await db.commit()  # Committed here, not in the repo
        #                 return user
        #             except:
        #                 await db.rollback()
        #                 raise
        #         ```
        # This gives better **transaction control**: You can batch multiple operations and commit them together, or rollback them all if any fails.

        # ------------------------------------------------------------------------
        # refresh(): Why and When to Use It
        # ------------------------------------------------------------------------
        # ```
        #     await db.refresh(entity)
        # ```
        # What it does:
        # - Reloads the entity’s data from the database.
        # - Useful after a flush to get fields that were auto-filled by the DB, like:
        #     - `id` (if generated on insert)
        #     - `created_at` or `updated_at` (if set via default or trigger)
        #     - Default enum values, booleans, etc.

        # When to use it:
        # | Situation                                         | Use `refresh()`?       |
        # | ------------------------------------------------- | ---------------------  |
        # | You need to return the full created object to API | Yes                    |
        # | DB generates fields (timestamps, UUIDs)           | Yes                    |
        # | You just need to insert and move on               | Not strictly needed    |

        # Example:
        # ```
        #     user = User(username="alice")
        #     db.add(user)
        #     await db.flush()

        #     print(user.id)         # ✅ Available now (after flush)
        #     print(user.created_at) # ❌ Might still be None (if DB sets it)

        #     await db.refresh(user)
        #     print(user.created_at) # ✅ Now it should be set
        # ```

        # in the `create()` method above
        # ```
        #   await self.db.flush()
        #   await self.db.refresh(entity)
        #   logger.debug(f"Created {self.model.__name__} with ID: {entity.id}")
        # ```
        # You're doing this to:
        #   - Make sure the ID is available before logging.
        #   - Ensure the entity has all server-generated fields populated.

        # If you don’t need to access
        #   - The `id`,
        #   - Or any other DB-generated fields (e.g., timestamps, UUIDs, defaults),
        #   - Or you don’t return the full object immediately,
        # Then you can skip both `flush()` and `refresh()`.
        # Example:
        # ```
        #   self.db.add(entity)
        #   return entity  # ID may still be None at this point if not flushed
        # ```
        # This is totally fine as long as:
        #   - You’re not accessing `entity.id` right after creation.
        #   - You're okay with waiting until the commit for DB defaults to be populated.

        # ------------------------------------------------------------------------
        # Summary Table
        # ------------------------------------------------------------------------
        # | Method      | What it does                | When to use                              | Why not in repo                                |
        # | ----------- | --------------------------- | ---------------------------------------- | ---------------------------------------------- |
        # | `flush()`   | Sends SQL, generates IDs    | When you need the ID or triggers to fire | It's lightweight, doesn’t finalize             |
        # | `refresh()` | Reloads full entity from DB | To get DB-generated fields               | Only needed if you care about those fields     |
        # | `commit()`  | Finalizes the transaction   | After all operations are successful      | Should be done at a higher level (service/API) |
        #
        # Best Practice: Transaction Control in FastAPI
        # You typically structure things like this:
        # ```
        #     async def create_user(..., db: AsyncSession = Depends(get_db)):
        #         try:
        #             user = await user_repo.create(...)
        #             other = await other_repo.do_something(...)
        #             await db.commit()  # Commit everything together
        #             return user
        #         except:
        #             await db.rollback()
        #             raise
        # ```
        # This gives you full control and clean error handling.

        # Final Tip
        # In most repository patterns, using `flush()` (and sometimes `refresh()`) is preferred because:
        #   - It avoids surprises when `id` or timestamps are `None`.
        #   - It makes the method’s return predictable and consistent.
        # Even if you're not logging id now, a future caller might rely on it.

    # =================================================================================================================
    # Basic Read Operations (Single Entity)
    # =================================================================================================================

    async def get_by_id(self, entity_id: UUID) -> ModelType | None:
        """
        Get an entity by its ID.

        Args:
            entity_id: The UUID of the entity to retrieve

        Returns:
            The entity if found, otherwise None

        Raises:
            AttributeError: If the model does not have an `id` attribute.
            RepositoryError: If an error occurs during retrieval.

        """
        try:
            # Construct a SELECT query that fetches one row matching the provided ID
            # Example: SELECT * FROM users WHERE id = :entity_id
            result = await self.db.execute(
                select(self.model).where(self.model.id == entity_id)
            )

            # scalar_one_or_none() returns:
            #   - the single result if exactly one row is found
            #   - None if no rows are found
            #   - raises error if more than one row (won't happen with ID filter)
            entity = result.scalar_one_or_none()

            # Log the successful fetch for traceability
            logger.debug(f"Retrieved {self.model.__name__} by ID: {entity_id}")

            # Return the found entity (or None if not found)
            return entity

        except Exception as e:
            # Log and raise a domain-level error to decouple DB logic from business logic
            logger.error(
                f"Error retrieving {self.model.__name__} by ID {entity_id}: {e}")
            raise RepositoryError(
                f"Failed to retrieve {self.model.__name__}") from e

        # Why `select(self.model).where(self.model.id == entity_id)`?
        #     - This dynamically builds a `SELECT` query for any model that has an `id` field.
        #     - Works generically across all models that inherit from your Base and have a UUID `id` column.
        # Why `scalar_one_or_none()`?
        # Perfect for `get_by_id`, because:
        #   - You're querying by a **unique primary key**, so expect 0 or 1 results.
        #   - If you use `.scalar_one()`, you'd get an exception if the entity doesn't exist.
        #   - `.scalar_one_or_none()` gracefully returns `None` if not found.

    async def get_by_id_or_raise(self, entity_id: UUID) -> ModelType:
        """
        Get an entity by its ID or raise NotFoundError.

        Args:
            entity_id: The UUID of the entity

        Returns:
            The entity

        Raises:
            NotFoundError: If the entity is not found in the database.
        """

        # Call the generic `get_by_id` method to fetch the entity.
        # This ensures we reuse logic, centralize query code, and keep DRY.
        entity = await self.get_by_id(entity_id)

        # If no entity is found, raise a domain-specific exception.
        # This is useful in service layers where you want to fail fast and
        # return a 404 or equivalent error to the client.
        if entity is None:
            raise NotFoundError(
                f"{self.model.__name__} with ID {entity_id} not found")

        # If found, return the entity as expected.
        return entity

        # `get_by_id_or_raise` method builds on top of `get_by_id`. It serves to:
        #   - Avoid `None` checks in your service or business logic code.
        #   - Immediately raise an error if the record isn’t found.
        #   - Return the entity confidently, guaranteeing a value.
        #   - Support fail-fast logic and cleaner code at higher layers (e.g., services, APIs).

    async def find_by_field(self, field: str, value: Any) -> ModelType | None:
        """
        Find a single entity by any field.

        Args:
            field: Field name to search by (must exist on model)
            value: Value to search for

        Returns:
            The entity if found, None otherwise

        Raises:
            RepositoryError: If the field does not exist on the model or query fails
        """

        # Safety check: Make sure the field exists on the model
        if not hasattr(self.model, field):
            raise RepositoryError(
                f"{self.model.__name__} has no field '{field}'")

        try:
            # Dynamically construct a SELECT query using the provided field and value
            # Example: SELECT * FROM users WHERE email = 'john@example.com'
            query = select(self.model).where(
                getattr(self.model, field) == value)

            # Execute the query
            result = await self.db.execute(query)

            # scalar_one_or_none():
            #   - Returns one result if found
            #   - Returns None if nothing is found
            #   - Raises an error if multiple results are found (won’t happen unless DB is inconsistent)
            entity = result.scalar_one_or_none()

            # Log the result (for debugging and traceability)
            logger.debug(f"Found {self.model.__name__} by {field}: {value}")

            return entity

        except Exception as e:
            # Catch any DB-level errors or unexpected failures
            logger.error(
                f"Error finding {self.model.__name__} by {field}={value}: {e}")
            raise RepositoryError(
                f"Failed to find {self.model.__name__}") from e

        # Why This Method Exists
        #   - Provides dynamic lookup by any model field — not just by `id`.
        #   - Makes the repository flexible for use cases like:
        #     - Find user by `email`
        #     - Find product by `slug`
        #     - Find order by `reference_number`
        #   - Avoids needing to write a new method for each "get by X" case.

        # When to Use It
        # | Use Case                                    | Use This Method?                                |
        # | ------------------------------------------- | --------------------------------                |
        # | You know the name of the field at runtime   | Yes                                             |
        # | Need to look up by `email`, `username`      | Yes                                             |
        # | Want stricter type-checking at compile-time | No (use typed methods instead)                  |
        # | Looking for multiple entities               | Use a `find_all_by_field()`  (Not implemented)  |

        # ⚠️ Notes & Gotchas
        # 1. Model field must exist:
        #   - The `hasattr` check prevents runtime errors when a wrong field is passed.

        # 2. Single result assumption:
        #   - `scalar_one_or_none()` expects zero or one result.
        #   - If your model allows multiple matches (e.g. status = 'active'), it may be better to use `scalars().all()`.

        # 3. SQL injection-safe:
        # ` - Since this uses `getattr(self.model, field)`, not raw SQL strings, you're protected from injection — as long as field is validated against the model.

        # Optional Enhancements
        # 1.  Return multiple results if needed:
        # ```
        #    async def find_all_by_field(self, field: str, value: Any) -> List[ModelType]:
        #        ...
        #        entities = result.scalars().all()
        #        ...
        # ```
        #
        # 2.  Stricter Error for Unsafe Field
        #   - You could raise `AttributeError` instead of `RepositoryError`, or define a custom one like `InvalidFieldError`.

    # =================================================================================================================
    # Basic Read Operations (Multiple Entities)
    # =================================================================================================================

    async def get_all(
        self,
        offset: int = 0,                # Used for pagination: how many records to skip
        limit: int = 100,               # Max number of records to return
        order_by: str | None = None     # Optional: field to sort results by
    ) -> list[ModelType]:
        """
        Get all entities with optional ordering and pagination.

        Args:
            offset: Number of entities to skip (for pagination).
            limit: Maximum number of entities to return (page size).
            order_by: Field name to order results by. Defaults to 'created_at' if present.

        Returns:
            A list of model instances (empty if none found).
        """
        try:
            # Start building a SELECT query for the model table
            query = select(self.model)

            # -------------------
            # ORDERING
            # -------------------
            if order_by:
                # Check if the model has the given attribute to avoid AttributeError
                if hasattr(self.model, order_by):
                    # Dynamically order by the specified field
                    query = query.order_by(getattr(self.model, order_by))
                    # Dynamically get the column attribute from the model class by its name.
                    # For example, if `order_by` is "username", this is equivalent to `self.model.username`.
                    # Then pass this attribute to `order_by()` to apply ordering on that column.
                    # Note: By default, this will order in ascending (ASC) order unless `.desc()` is called explicitly.

                    # Log the field used for ordering
                    logger.debug(
                        f"Ordering {self.model.__name__} by field: '{order_by}'")

                else:
                    # Log a warning if the given field doesn't exist on the model
                    logger.warning(
                        f"Ignored invalid 'order_by' field: '{order_by}' does not exist on {self.model.__name__}")

            elif hasattr(self.model, 'created_at'):
                # Fallback: If model has 'created_at', sort by newest first
                query = query.order_by(self.model.created_at.desc())
                logger.debug(
                    f"Ordering {self.model.__name__} by default field: 'created_at' DESC")

            # -------------------
            # PAGINATION
            # -------------------
            query = query.offset(offset).limit(limit)

            # Execute the constructed query asynchronously
            result = await self.db.execute(query)

            # Extract all scalar results (model instances) from the result
            entities = result.scalars().all()

            # Log how many entities were retrieved
            logger.debug(
                f"Retrieved {len(entities)} {self.model.__name__} entities")

            # Return as a list (ensures compatibility even if result is empty)
            return list(entities)

        except Exception as e:
            # Catch and wrap any unexpected errors
            logger.error(f"Error retrieving all {self.model.__name__}: {e}")
            raise RepositoryError(
                f"Failed to retrieve {self.model.__name__} entities") from e

        # `order_by` Logic Decision Table
        # | Case | `order_by` Provided?          | Field Exists on Model?    | Ordering Applied                | Log Message                                                                          |
        # | ---- | ----------------------------- | ------------------------- | ------------------------------- | ------------------------------------------------------------------------------------ |
        # | 1    | No                            | N/A                       | `created_at DESC` *(if exists)* | `Ordering by default field: 'created_at' DESC`                                       |
        # | 2    | No                            | Model has no `created_at` | None applied                    | No order clause, no log                                                              |
        # | 3    | Yes (`"username"`)            | Yes                       | `ORDER BY username ASC`         | `Ordering by field: 'username'`                                                      |
        # | 4    | Yes (`"nonexistent_field"`)   | No                        | None applied                    | `Ignored invalid 'order_by' field: 'nonexistent_field' does not exist on <Model>`    |
        # | 5    | Yes (`"created_at"`)          | Yes                       | `ORDER BY created_at ASC`       | `Ordering by field: 'created_at'` (not DESC unless explicitly handled)               |

        # Additional Notes:
        #   - Default fallback: Only applies if `order_by` is not given and the model has a `created_at` field.
        #   - Invalid fields: Silently ignored with a warning log — no exception is raised.
        #   - The default ordering direction when using order_by is ascending (ASC)
        #   - Explicit ASC/DESC logic isn't handled here** (e.g. `order_by="created_at:desc"`), but you can extend the logic to support it if needed.

    # =================================================================================================================
    # Update Operations
    # =================================================================================================================

    async def update(self, entity_id: UUID, **kwargs) -> ModelType | None:
        """
        Update an entity by its ID.

        Args:
            entity_id: The UUID of the entity to update
            **kwargs: Fields and values to update

        Returns:
            The updated entity if found, None otherwise

        Raises:
            DuplicateError: If update would violate unique constraints
            RepositoryError: For other database errors
        """
        try:
            # Filter out keys with None or empty string values.
            # This avoids overwriting existing fields with null or empty values unintentionally.
            update_data = {k: v for k,
                           v in kwargs.items() if v is not None and v != ""}

            # If no valid data is provided to update, log a warning and just return the current entity.
            if not update_data:
                logger.warning(
                    f"No valid data provided for updating {self.model.__name__}")
                return await self.get_by_id(entity_id)

            # If the model has an 'updated_at' field, set it to the current DB timestamp.
            # This is a common pattern to track when a record was last updated.
            if hasattr(self.model, 'updated_at'):
                update_data['updated_at'] = func.now()

            # Build an UPDATE statement:
            # - Filter by entity ID to update only the targeted record.
            # - Set the new values using **update_data.
            # - Use synchronize_session='fetch' to update session state correctly after the DB update.
            stmt = (
                update(self.model)
                .where(self.model.id == entity_id)
                .values(**update_data)
                .execution_options(synchronize_session="fetch")
            )

            # Execute the UPDATE statement asynchronously.
            result = await self.db.execute(stmt)

            # Check how many rows were affected by the update.
            # If zero, it means no entity was found with the given ID.
            if result.rowcount == 0:
                logger.warning(
                    f"{self.model.__name__} with ID {entity_id} not found for update")
                return None

            # Fetch the updated entity from the DB to return the fresh state.
            updated_entity = await self.get_by_id(entity_id)

            logger.debug(f"Updated {self.model.__name__} with ID: {entity_id}")

            # Return the updated entity instance.
            return updated_entity

        except IntegrityError as e:
            # Rollback the session on integrity errors (like unique constraint violations).
            await self.db.rollback()
            logger.error(
                f"Integrity error updating {self.model.__name__}: {e}")
            raise DuplicateError(
                f"Update would violate unique constraints") from e

        except Exception as e:
            # Rollback on any other unexpected exceptions.
            await self.db.rollback()
            logger.error(
                f"Error updating {self.model.__name__} {entity_id}: {e}")
            raise RepositoryError(
                f"Failed to update {self.model.__name__}") from e

        # Notes / Tips:
        #   - Filtering out None and empty strings helps avoid accidental data loss. Sometimes empty strings are valid, but if you want to allow empty strings explicitly, you could adjust that condition.
        #   - Using `func.now()` to update timestamps leverages the database’s time instead of Python’s, which ensures consistency if multiple app servers or time zones are involved.
        #   - `synchronize_session='fetch'` ensures the SQLAlchemy session’s identity map stays consistent after a bulk update. It fetches the affected rows and updates the session. This is important to prevent stale data in the current session.
        #   - Returning the updated entity after update is useful to confirm the current state, especially if there are triggers, default values, or database-generated fields that could change during update.
        #   - If you expect partial updates frequently, this method is safe since it won’t overwrite fields with None or empty strings by default.
        #   - You might want to add validation or whitelist allowed update fields depending on your use case for added security or integrity.

    # =================================================================================================================
    # Delete Operations
    # =================================================================================================================

    async def delete(self, entity_id: UUID) -> bool:
        """
        Delete an entity by its ID.

        Args:
            entity_id: The UUID of the entity to delete

        Returns:
            True if entity was deleted, False if not found

        Raises:
            RepositoryError: For database errors
        """
        try:
            # Build the DELETE statement with a WHERE clause to target the entity by ID.
            stmt = delete(self.model).where(self.model.id == entity_id)

            # Execute the DELETE operation
            result = await self.db.execute(stmt)

            # result.rowcount indicates how many rows were affected.
            if result.rowcount > 0:
                # If at least one row was deleted, it means the entity was found and removed.
                logger.debug(
                    f"Deleted {self.model.__name__} with ID: {entity_id}")
                return True
            else:
                # No rows affected → entity not found.
                logger.warning(
                    f"{self.model.__name__} with ID {entity_id} not found for deletion")
                return False

        except Exception as e:
            # Rollback in case of an unexpected error to keep DB state clean.
            await self.db.rollback()
            logger.error(
                f"Error deleting {self.model.__name__} {entity_id}: {e}")
            raise RepositoryError(
                f"Failed to delete {self.model.__name__}") from e

        # Notes & Tips
        # 1. Why return `bool` instead of raising `NotFoundError`?
        #   - Because deletion is often idempotent. Trying to delete something that doesn’t exist is not always an error — it just means "already deleted" or "never existed."
        #   - If your domain logic requires strict existence, you could use a `delete_or_raise()` version that raises a `NotFoundError`.
        # 2. No call to `commit()`?
        #   - Correct. This method assumes that the commit will be handled outside the repository, typically at the service or unit-of-work level.
        #   - This keeps the repository reusable and testable.
        # 3. Safety Check: `result.rowcount`
        #   - Some databases (e.g., PostgreSQL) return accurate `rowcount`, but others (e.g., MySQL with certain settings) may not.
        #   - If you’re using a DB where `rowcount` is unreliable, consider first checking existence with a `SELECT`, then deleting.
        # 4. Alternatives:
        #   - Add soft delete support (`is_deleted = True`) if you don’t want to actually delete rows but just mark them.

    # =================================================================================================================
    # Validation / Existence Checks
    # =================================================================================================================

    async def exists(self, entity_id: UUID) -> bool:
        """
        Check if an entity exists by its ID.

        Args:
            entity_id: The UUID of the entity

        Returns:
            True if entity exists, False otherwise
        """
        try:
            # Build a SELECT query that only fetches the ID (not the entire row)
            # This is more efficient than SELECT * for existence checks
            query = select(self.model.id).where(self.model.id == entity_id)

            # Execute the query
            result = await self.db.execute(query)

            # `scalar()` fetches the first column of the first row
            # If result is None => entity does not exist
            exists = result.scalar() is not None

            # Log the result for traceability
            logger.debug(
                f"{self.model.__name__} with ID {entity_id} exists: {exists}")

            return exists

        except Exception as e:
            # If there's a DB error, log and raise a domain-specific error
            logger.error(
                f"Error checking existence of {self.model.__name__} {entity_id}: {e}")
            raise RepositoryError(
                f"Failed to check {self.model.__name__} existence") from e

        # Why This Method Exists
        #   - This method checks only the presence of a record — not the full data.
        #   - It is more lightweight and efficient than `get_by_id`, especially when you don't care about the full entity.

        # When to Use
        # | Scenario                                   | Use `exists()`?   |
        # | ------------------------------------------ | ----------------- |
        # | Before deleting or updating a record       | Yes               |
        # | To validate foreign keys or relationships  | Yes               |
        # | When performance matters (e.g. huge table) | Yes               |
        # | You need the full entity                   | Use `get_by_id`   |

        # Tips & Notes
        # ✅ Efficient SELECT: You only select the `.id` column, which is fast.
        # ✅ Avoid unnecessary data fetching: Better than loading the full model if you just need to check existence.
        # 🧪 Good for validation: This can be used in service layers to short-circuit invalid requests early.
        # ✅ Works with any model: Because you're using `self.model.id`, it's generic.

        # 🚀 Enhancement (Optional)
        # If you want even better performance, especially on large datasets or under high load,
        # you can use `exists().select()`:
        # ```
        #   from sqlalchemy import exists as sql_exists
        #   query = select(sql_exists().where(self.model.id == entity_id))
        #   result = await self.db.execute(query)
        #   exists = result.scalar()
        # ```
        # This will generate an `SQL SELECT EXISTS(...)` query, which is optimized for presence checks by the database engine.
        # 🟢 You can replace your current logic with this if you're performing tons of existence checks in production systems.

    # =================================================================================================================
    # Aggregation / Count Operations
    # =================================================================================================================

    async def count(self, **filters: Any) -> int:
        """
        Count entities with optional filters.

        Args:
            **filters: Optional filter conditions (e.g., status="active", is_deleted=False)

        Returns:
            Number of matching entities
        """
        try:
            # Start by selecting a count of the primary key (usually 'id') from the model.
            # Equivalent SQL: SELECT COUNT(id) FROM model WHERE ...
            query = select(func.count(self.model.id))

            # Dynamically apply filters to the query (if provided)
            for field, value in filters.items():
                # Only apply valid filters (i.e., the model must have the field, and value is not None)
                if hasattr(self.model, field) and value is not None:
                    query = query.where(getattr(self.model, field) == value)

            # Execute the query
            result = await self.db.execute(query)

            # Get the scalar result (the count), default to 0 if None
            count = result.scalar() or 0

            # Log the number of entities found
            logger.debug(f"Counted {count} {self.model.__name__} entities")

            # Return the total count
            return count

        except Exception as e:
            # Rollback not needed here (no data mutation), but still handle & log the error
            logger.error(f"Error counting {self.model.__name__}: {e}")
            raise RepositoryError(
                f"Failed to count {self.model.__name__} entities") from e

        # | Scenario                                  | What Happens                                                             |
        # | ----------------------------------------- | ------------------------------------------------------------------------ |
        # | No filters provided                       | Counts **all rows** in the table                                         |
        # | Filters provided (e.g. `status="active"`) | Counts only rows matching the filters                                    |
        # | Field doesn't exist on model              | Filter is skipped (fails silently); only valid fields are considered     |
        # | `value is None` in filter                 | Filter is ignored to avoid unintended results like `WHERE field IS NULL` |
        # | Count fails                               | Logs error and raises `RepositoryError`                                  |

        # Pros
        #   - Safe: avoids bad filters by checking with hasattr()
        #   - Flexible: accepts any number of filters
        #   - Reusable: works for any model

        # Enhancements
        # 1. Support custom operators (e.g., `>=`, `LIKE`):
        #   - Right now, it only supports `=` equality comparisons.
        #   - If needed, you could support more complex filters using something like a `filters: dict[str, tuple[str, Any]]` pattern:
        #       ```
        #       filters = {"created_at": (">=", datetime.utcnow() - timedelta(days=7))}
        #       ```
        # 2. Handle nullable fields more explicitly:
        #   - If your use case needs to count `NULL` values explicitly, add a flag to support that.
        # 3. Logging filters:
        #   -  Add debug logging for the actual filters applied:
        #       ```
        #       logger.debug(f"Applied filters: {filters}")
        #       ```

        # Example Usage
        #   ```
        #   # Counts active admin users
        #   await user_repo.count(status="active", role="admin")
        #
        #   # Counts all posts
        #   await post_repo.count()
        #   ```

        # NOTE:
        # Under the hood, when you do something like this:
        # ```
        #   query = select(User)
        #   query = query.where(User.status == "active")
        #   query = query.where(User.role == "admin")
        # ```
        # It chains the filters together, and the final query object is functionally equivalent to:
        # ```
        #   select(User).where(
        #       User.status == "active",
        #       User.role == "admin"
        #   )
        # ```
        # Or in simplified chained form:
        # ```
        #   select(User).where(User.status == "active").where(User.role == "admin")
        # ```


# BaseRepository Method Summary
# | Method Name                        | Purpose                                                      | Returns                                 | When to Use                                                   | Notes / Highlights                                                          |
# | ---------------------------------- | ------------------------------------------------------------ | --------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------- |
# | `create(**kwargs)`                 | Create a new entity in the database                          | The created model instance              | When inserting new data into the DB                           | Uses `flush` and `refresh` to get autogenerated fields without committing   |
# | `get_by_id(entity_id)`             | Retrieve a single entity by its UUID `id`                    | Model instance or `None`                | When you want to fetch by ID, and handle missing result       | Returns `None` if not found                                                 |
# | `get_by_id_or_raise(id)`           | Same as `get_by_id`, but raises `NotFoundError` if not found | Model instance                          | When a missing entity should be treated as an error           | Common for API endpoints                                                    |
# | `find_by_field(field, value)`      | Fetch a single entity by any field                           | Model instance or `None`                | When you want to look up by fields like `email`, `slug`, etc. | Validates the field exists; raises error if not                             |
# | `get_all(offset, limit, order_by)` | Fetch multiple entities with pagination and ordering         | List of model instances                 | When listing results (e.g., in a table or dashboard)          | Supports dynamic `order_by` with fallback to `created_at` if available      |
# | `update(id, **kwargs)`             | Update an entity with provided fields                        | Updated model or `None`                 | When editing/updating a record by ID                          | Filters out `None` and empty string values, handles timestamps if supported |
# | `delete(entity_id)`                | Delete an entity by ID                                       | `True` if deleted, `False` if not found | When removing records from the DB                             | Uses `rowcount` to determine if the entity existed                          |
# | `exists(entity_id)`                | Check whether an entity exists with a given ID               | `True` / `False`                        | When you need a lightweight existence check                   | More efficient than retrieving full object                                  |
# | `count(**filters)`                 | Count number of entities that match optional filters         | Integer count                           | When you need totals, e.g. for pagination or metrics          | Filters are dynamically applied                                             |

# Usage Tips
#   - Use `get_by_id_or_raise` in service layers to avoid writing `if not found: raise`.
#   - Use `count` before `get_all` for paginated results to know total pages.
#   - Use `update` only when you are sure about fields — it silently ignores empty values.
#   - Avoid using `find_by_field` for unindexed fields — can lead to slow queries.
