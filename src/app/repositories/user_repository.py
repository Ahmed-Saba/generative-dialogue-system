"""
User repository for handling user-specific database operations.

This module provides the UserRepository class which extends BaseRepository
with user-specific functionality like authentication, user lookup by email/username,
and user status management.
"""

from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
import logging

from app.models.user import User
from app.models.conversation import Conversation
from .base_repository import BaseRepository, RepositoryError

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """
    Repository for User entity operations.

    Inherits from the generic `BaseRepository`, providing standard CRUD functionality.
    Adds specialized methods for user-specific operations such as authentication,
    user lookup, and loading related entities.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize the UserRepository with a SQLAlchemy AsyncSession.

        This constructor passes the `User` model and DB session to the `BaseRepository`
        so that all base CRUD operations are available for the User entity.

        Args:
            db: The async database session
        """
        super().__init__(User, db)

        # | Concept                                | Explanation                                                                                                                                                                                                         |
        # | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
        # | `UserRepository(BaseRepository[User])` | You're **subclassing** the generic `BaseRepository`, specializing it for the `User` model. This means all generic CRUD methods (like `create`, `get_by_id`, `update`, etc.) become available for the `User` entity. |
        # | `super().__init__(User, db)`           | This calls the `BaseRepository.__init__()` and injects two things: <br>1. `User`: the model to operate on<br>2. `db`: the `AsyncSession` used for all DB interactions.                                              |
        # | Why not duplicate CRUD logic?          | The base repo handles common behavior once. The user repo only adds behavior that is **specific to users** (e.g., `get_by_email`, `authenticate`, etc.).                                                            |

        # When & Why You Extend the Base Repository
        #   - You extend the BaseRepository when:
        #   - You want to reuse all the generic functionality (like `get_by_id`, `create`, `delete`, etc.).
        #   - You want to add custom business logic that only applies to a particular model (like `find_by_username()`` for users or `get_active_sessions()` for a session model).

        # Summary
        #   - Inheriting from `BaseRepository[User]` gives your `UserRepository` access to all standard CRUD methods.
        #   - The constructor passes the User model to the base so it knows what model to operate on.
        #   - Now you can add user-specific methods without rewriting generic database logic.

    # =================================================================================================================
    # Create Operations
    # =================================================================================================================

    async def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        is_active: bool = True
    ) -> User:
        """
        Create a new user with the provided credentials.

        This method wraps the generic `create()` method from `BaseRepository`
        and applies some pre-processing and normalization specific to user data.

        Args:
            username: Unique username for the user
            email: Unique email address (will be normalized to lowercase)
            hashed_password: Already hashed password (never store raw passwords!)
            is_active: Whether the user account is active (default: True)

        Returns:
            The created User entity

        Raises:
            DuplicateError: If a user with the same username or email already exists
            RepositoryError: For any unexpected database errors
        """
        logger.info(f"Creating new user: {username} ({email})")

        return await self.create(
            username=username.strip(),                # Remove accidental whitespace
            email=email.strip().lower(),              # Normalize email to lowercase
            hashed_password=hashed_password,
            is_active=is_active
        )

        # This `create_user` method is a specialized wrapper around the generic `create()` method
        # inherited from your `BaseRepository`

        # Why This Method Exists (When We Already Have `create()` in `BaseRepository`)
        # | Reason                     | Explanation                                                                                                                                                                |
        # | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
        # | **Preprocessing inputs**   | Ensures consistent formatting: trims whitespace, normalizes email casing. This prevents issues like treating `John@Email.com` and `john@email.com` as two different users. |
        # | **Encapsulation of logic** | Instead of calling `create(...)` all over the codebase with repetitive field handling, we centralize user-specific creation rules here.                                    |
        # | **Separation of concerns** | Keeps user-specific logic within the `UserRepository`, so the base remains generic.                                                                                        |
        # | **Extensibility**          | Later, if you want to add logging, auditing, default role assignment, etc., you can do it here without modifying shared code.                                              |

        # Usage Example
        # ```
        #   user_repo = UserRepository(db_session)
        #   user = await user_repo.create_user(
        #       username="JohnDoe",
        #       email="JohnDoe@example.com",
        #       hashed_password=some_hashed_pw,
        #       # is_active=True  # Default: True
        #   )
        # ```
        # This avoids the caller needing to know how to handle normalization or which fields are required — it’s all abstracted away.

        # Suggestions for Enhancement
        # | Idea                                                     | Benefit                                                          |
        # | -------------------------------------------------------- | ---------------------------------------------------------------- |
        # | Validate email/username format before calling `create()` | Catch bad data early (e.g., with a utility or pydantic schema)   |
        # | Accept a pydantic model instead of individual fields     | Clean separation of data validation and persistence              |
        # | Automatically assign roles or permissions                | Useful if your app has user roles (e.g., admin, moderator, etc.) |

    # =================================================================================================================
    # Read Operations (Single Entity)
    # =================================================================================================================

    async def get_by_username(self, username: str) -> User | None:
        """
        Get a user by their username.

        Args:
            username: The username to search for (case-sensitive)

        Returns:
            The User if found, None otherwise
        """
        try:
            query = select(User).where(User.username == username.strip())
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()

            if user:
                logger.debug(f"Found user by username: {username}")
            else:
                logger.debug(f"No user found with username: {username}")

            return user
        except Exception as e:
            logger.error(f"Error retrieving user by username {username}: {e}")
            raise RepositoryError(
                f"Failed to retrieve user by username") from e

        # Notes:
        #   - Strips whitespace from input, which is good for user input.
        #   - Case-sensitive match (SQLAlchemy doesn't apply `LOWER()` unless you explicitly tell it to).
        #   - Could consider ilike for case-insensitive search depending on your app logic.

    async def get_by_email(self, email: str) -> User | None:
        """
        Get a user by their email address.

        Args:
            email: The email address to search for (case-insensitive)

        Returns:
            The User if found, None otherwise
        """
        try:
            # Normalize email to lowercase for comparison
            normalized_email = email.strip().lower()
            query = select(User).where(User.email == normalized_email)
            result = await self.db.execute(query)
            user = result.scalar_one_or_none()

            if user:
                logger.debug(f"Found user by email: {email}")
            else:
                logger.debug(f"No user found with email: {email}")

            return user
        except Exception as e:
            logger.error(f"Error retrieving user by email {email}: {e}")
            raise RepositoryError(f"Failed to retrieve user by email") from e

        # Notes:
        #   - Email is normalized to lowercase before query (important if your database is case-sensitive).
        #   - You assume emails are stored in lowercase — this is a good practice, and you enforced it in `create_user()`.

    async def get_by_username_or_email(self, identifier: str) -> User | None:
        """
        Retrieve a user by either their username or email address.

        This method is useful for login forms where users can provide either
        their username or email as their identifier for authentication.

        Args:
            identifier: A string that may be either a username or email address

        Returns:
            The User if found, None otherwise

        Raises:
            RepositoryError: If an unexpected error occurs during query
        """
        try:
            # Step 1: Normalize the identifier for email matching
            # ---------------------------------------------------
            # Strip whitespace (leading/trailing) and lowercase it.
            # This helps ensure consistent matching when checking against email.
            normalized_identifier = identifier.strip().lower()

            # Step 2: Build a SQL SELECT query with an OR condition
            # -----------------------------------------------------
            # We want to find a user whose *username* OR *email* matches the input.
            # `or_()` is an SQLAlchemy function that generates SQL like:
            #    WHERE username = :val OR email = :val
            #
            # ⚠️ We don't lowercase the username side intentionally —
            #    usernames are usually case-sensitive (unless app rules say otherwise).
            #
            # Example SQL this generates:
            #   SELECT * FROM users WHERE username = 'Ali' OR email = 'ali@example.com'
            query = select(User).where(
                or_(
                    User.username == identifier.strip(),        # Raw input for username
                    User.email == normalized_identifier         # Normalized input for email
                )
            )

            # Step 3: Execute the query against the database
            result = await self.db.execute(query)

            # Step 4: Extract the result
            # - `scalar_one_or_none()` returns:
            #     → The user instance if one match is found
            #     → None if no match is found
            #     → Raises error if more than one match (which shouldn't happen here)
            user = result.scalar_one_or_none()

            # Step 5: Logging for observability
            if user:
                logger.debug(f"Found user by identifier: {identifier}")
            else:
                logger.debug(f"No user found with identifier: {identifier}")

            return user

        except Exception as e:
            # Step 6: Handle and wrap unexpected errors
            logger.error(
                f"Error retrieving user by identifier {identifier}: {e}")
            raise RepositoryError(
                "Failed to retrieve user by identifier") from e

        # Notes:
        #   - Useful in auth scenarios (`login with username or email`).
        #   - Handles case-insensitive match for email, but username remains case-sensitive.
        #   - Consider using `ilike()` for username if case-insensitivity is important.

        # | Field    | Case Sensitive?                        | Store As                   | Compare As | Why?                             |
        # | -------- | ------------------------------------   | -------------------------- | ---------- | -------------------------------- |
        # | Email    | No                                     | Lowercase (normalized)     | Lowercase  | Consistent, avoids confusion     |
        # | Username | No (for logic) / Yes (for display)     | As entered (original case) | Lowercase  | Prevents duplicates, improves UX |

        # Notes on `or_()`
        # `or_()` is part of SQLAlchemy's expression language.
        # It combines two or more conditions into a single SQL `OR` clause.
        # Equivalent SQL:
        # ```
        #     SELECT * FROM users WHERE username = 'Ali' OR email = 'ali@example.com';
        # ```

        # `and_()` vs `or_()`:
        #   - `and_(A, B)` → matches when both conditions are true.
        #   - `or_(A, B)` → matches when either condition is true.

        # Why use both `identifier.strip()` and `normalized_identifier`?
        #   - `User.username == identifier.strip()` → preserves original case (usernames may be case-sensitive).
        #   - `User.email == normalized_identifier` → ensures email is case-insensitive by design.

        # Enhancement Suggestions
        # | Area                                 | Suggestion                                                                                | Why                                            |
        # | ------------------------------------ | ----------------------------------------------------------------------------------------- | ---------------------------------------------- |
        # | **Case-insensitive username search** | Use `User.username.ilike(identifier)`                                                     | For UX consistency (users often forget casing) |
        # | **Validation**                       | Add a `utils.is_email(identifier)` helper to check format and separate username vs. email | More robust than trying both every time        |
        # | **Indexing**                         | Ensure `username` and `email` have unique indexes in the DB                               | Prevents duplicates and improves lookup speed  |
        # | **Security**                         | Avoid exposing in logs whether a user exists (in production)                              | Prevents account enumeration attacks           |

        # | Method                     | Purpose                         | Input        | Normalization                       | Search Type                                     |
        # | -------------------------- | ------------------------------- | ------------ | ----------------------------------- | ----------------------------------------------- |
        # | `get_by_username`          | Find a user by username         | `username`   | `strip()`                           | Exact match on `User.username`                  |
        # | `get_by_email`             | Find a user by email            | `email`      | `strip().lower()`                   | Exact match on `User.email`                     |
        # | `get_by_username_or_email` | Flexible login/lookup by either | `identifier` | `strip()`, and `.lower()` for email | Match on either `User.username` or `User.email` |

    async def get_with_conversations(
        self,
        user_id: UUID,
        load_messages: bool = False
    ) -> User | None:
        """
        Get a user along with their conversations (and optionally, conversation messages).

        Args:
            user_id: UUID of the user
            load_messages: If True, also loads messages for each conversation

        Returns:
            The User instance with conversations (and possibly messages) loaded, or None if not found.
        """
        try:
            # Start with a basic SELECT query filtering by user ID
            query = select(User).where(User.id == user_id)

            if load_messages:
                # Eagerly load:
                #   - User.conversations (many)
                #   - For each conversation, also load Conversation.messages (many)
                query = query.options(
                    selectinload(User.conversations).selectinload(
                        Conversation.messages)
                )
            else:
                # Only load conversations, without the nested messages
                query = query.options(selectinload(User.conversations))

            # Execute the query against the async session
            result = await self.db.execute(query)

            # Get the first result (or None if not found)
            user = result.scalar_one_or_none()

            # Log result
            if user:
                logger.debug(f"Retrieved user with conversations: {user_id}")
            else:
                logger.debug(f"No user found with ID: {user_id}")

            return user

        except Exception as e:
            logger.error(
                f"Error retrieving user with conversations {user_id}: {e}")
            raise RepositoryError(
                f"Failed to retrieve user with conversations") from e

        # What `selectinload()` Does
        #   - `selectinload()` is a loader strategy used by SQLAlchemy to efficiently load relationships.
        #   - It performs a separate `SELECT` for the relationship, batched for performance.
        #   - This is ideal for one-to-many or many-to-many relationships.

        # Why not just use `.join()` or `.joinedload()`?
        #   - Those would flatten the data and duplicate rows (e.g., a user with multiple conversations and messages).
        #   - `selectinload()` avoids this and is better for loading nested lists.

        # If `load_messages=True`, this is what's loaded:
        # User
        # ├── conversations (list[Conversation])
        # │         └── messages (list[Message])
        #
        # SQLAlchemy runs:
        #   - One query for the user
        #   - One query for that user’s conversations
        #   - One query for messages for all those conversations

        # Example SQL Under the Hood
        # ```bash
        #   -- First query: get user
        #   SELECT * FROM user WHERE id = :user_id;
        #
        #   -- Second query: get conversations for that user
        #   SELECT * FROM conversation WHERE user_id = :user_id;
        #
        #   -- Third query: get messages for all those conversations
        #   SELECT * FROM message WHERE conversation_id IN (:c1, :c2, ...);
        # ```

        # Optional Enhancements
        # | Feature                                                     | How                                                                  | Benefit                                    |
        # | ----------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------ |
        # | Add `notfound_error: bool = False`                          | Raise `NotFoundError` if user not found                              | Consistent with `get_by_id_or_raise()`     |
        # | Add selective fields                                        | Use `.options(load_only(User.id, User.email))`                       | Save bandwidth if you don't need full user |
        # | Add filtering on conversations/messages (e.g., only active) | Use `.filter()` inside `selectinload()` via `with_loader_criteria()` | More control over data shape               |

    # =================================================================================================================
    # Read Operations (Multiple Entities / Search)
    # =================================================================================================================

    async def get_active_users(
        self,
        offset: int = 0,
        limit: int = 100
    ) -> list[User]:
        """
        Get all active users with pagination support.

        This method returns a subset of users who are marked as active.
        Useful for admin dashboards, user listings, etc.

        Args:
            offset: How many users to skip (for pagination)
            limit: Maximum number of users to return (for pagination)

        Returns:
            A list of active User instances
        """
        try:
            # Build the SELECT query
            query = (
                select(User)                             # SELECT * FROM users
                # WHERE is_active = true
                .where(User.is_active == True)
                # ORDER BY created_at DESC (most recent first)
                .order_by(User.created_at.desc())
                # OFFSET for pagination (skip N records)
                .offset(offset)
                # LIMIT to control the number of results
                .limit(limit)
            )

            # Execute the query asynchronously using the DB session
            result = await self.db.execute(query)

            # Fetch all resulting rows as scalar objects (i.e., full User instances)
            users = result.scalars().all()

            # Log how many users were fetched
            logger.debug(f"Retrieved {len(users)} active users")

            # Return the result list
            return list(users)

        except Exception as e:
            # If anything goes wrong, rollback and raise a domain-level error
            logger.error(f"Error retrieving active users: {e}")
            raise RepositoryError("Failed to retrieve active users") from e

        # | Part                               | Purpose                                                                       |
        # | ---------------------------------- | ----------------------------------------------------------------------------- |
        # | `User.is_active == True`           | Filters only active users (e.g., those not soft-deleted or banned)            |
        # | `order_by(User.created_at.desc())` | Returns newest users first — useful in admin panels or lists                  |
        # | `.offset()` & `.limit()`           | Enables pagination, which is critical for large datasets                      |
        # | `scalars().all()`                  | Returns ORM-mapped `User` instances instead of raw rows/tuples                |
        # | `try/except` block                 | Prevents crashes and provides meaningful logs and domain-level error handling |
        # | `logger.debug(...)`                | Useful for tracing and debugging API/database behavior during development     |

        # Optional Enhancements
        # | Feature                        | Description                                                          |
        # | ------------------------------ | -------------------------------------------------------------------- |
        # | `search: Optional[str] = None` | Add a `search` parameter to allow filtering by username/email        |
        # | `is_active: bool = True` param | Make it a flexible parameter to optionally get inactive users too    |
        # | Caching                        | Consider caching this method for performance if it's used frequently |

    async def search_users(
        self,
        search_term: str,
        active_only: bool = True,
        offset: int = 0,
        limit: int = 50
    ) -> list[User]:
        """
        Search users by username or email (case-insensitive).

        Args:
            search_term: Term to search for in username or email
            active_only: Whether to return only active users
            offset: Number of users to skip (for pagination)
            limit: Maximum number of users to return (pagination)

        Returns:
            List of matching User entities
        """
        try:
            # Prepare a search pattern for SQL ILIKE (case-insensitive LIKE)
            # '%term%' allows searching for term anywhere in the field
            search_pattern = f"%{search_term.strip().lower()}%"

            # Build base query using `or_` to match either username or email
            query = select(User).where(
                or_(
                    User.username.ilike(search_pattern),
                    User.email.ilike(search_pattern)
                )
            )

            # Optional filter: only include active users
            if active_only:
                query = query.where(User.is_active == True)

            # Order results alphabetically by username, apply offset/limit for pagination
            query = (
                query.order_by(User.username)
                     .offset(offset)
                     .limit(limit)
            )

            # Execute the query
            result = await self.db.execute(query)

            # Extract all matching User instances
            users = result.scalars().all()

            # Log the number of users found
            logger.debug(
                f"Found {len(users)} users matching search term: {search_term}")

            return list(users)

        except Exception as e:
            logger.error(f"Error searching users with term {search_term}: {e}")
            raise RepositoryError(f"Failed to search users") from e

        # Suggestions for Enhancement
        # | Feature              | Benefit                              | How                                    |
        # | -------------------- | ------------------------------------ | -------------------------------------- |
        # | Sanitize input more  | Avoid weird chars                    | e.g., `.replace("%", "")`              |
        # | Add `order_by` param | Let caller decide sort field         | `order_by: Optional[str] = "username"` |
        # | Allow more fields    | Extend search (e.g., full name)      | Add more `or_()` conditions            |
        # | Support fuzzy search | Better results (e.g., typo-tolerant) | Use trigram or full-text search        |

    # =================================================================================================================
    # Update Operations
    # =================================================================================================================

    async def update_profile(
        self,
        user_id: UUID,
        username: str | None = None,
        email: str | None = None
    ) -> User | None:
        """
        Update user profile information (username and/or email).

        Args:
            user_id: UUID of the user to update.
            username: New username (optional).
            email: New email address (optional).

        Returns:
            The updated User entity if found, otherwise None.

        Raises:
            DuplicateError: If the new username or email already exists (violating unique constraints).
        """
        # Logging the high-level operation — safe because we don't expose PII like full email
        logger.info(f"Updating profile for user: {user_id}")

        # Prepare only the fields that are provided (non-null)
        update_data = {}

        if username is not None:
            update_data['username'] = username.strip()

        if email is not None:
            # Normalize email to lowercase for consistency and uniqueness
            update_data['email'] = email.strip().lower()

        # Call the shared update logic from the BaseRepository
        return await self.update(user_id, **update_data)

        # Why This Method Exists
        # | Reason          | Description                                                                     |
        # | --------------- | ------------------------------------------------------------------------------  |
        # | ✅ Encapsulation | Keeps profile-specific update logic (like email normalization) in one place.   |
        # | ✅ Safety        | Prevents overwriting other fields by mistake.                                  |
        # | ✅ Reusability   | Other services can reuse this method without repeating logic.                  |
        # | ✅ Clear API     | Makes the intent of the update more explicit than calling `update()` directly. |

        # 🔐 Validation & Safety Considerations
        # You're assuming that username/email are optional and unique. Consider:
        # | Case                         | Handled?                                                    | Tip                                                                  |
        # | ---------------------------- | ----------------------------------------------------------  | -------------------------------------------------------------------- |
        # | Unique constraint violations | ✅ Yes, raised via `DuplicateError` in `update`             |                                                                      |
        # | Blank strings                | ⚠️ No                                                       | Optional: ignore empty strings or treat them as `None`               |
        # | Email format                 | ❌ No                                                       | Optional: validate with a regex or Pydantic validator before passing |
        # | No fields passed             | ✅ Yes, handled by the base method returning unchanged user |                                                                      |

        # ✨ Enhancement Ideas (Optional)
        # | Feature                                   | Description                                                        |
        # | ----------------------------------------- | ------------------------------------------------------------------ |
        # | `username_changed_at`, `email_changed_at` | Useful audit fields if your model supports them                    |
        # | Notification                              | Send email confirmation or notification after email change         |
        # | Restrict domains                          | You can restrict business emails (e.g., only allow `@company.com`) |

    async def update_password(self, user_id: UUID, new_hashed_password: str) -> User | None:
        """
        Update a user's password.

        Args:
            user_id: UUID of the user whose password should be updated.
            new_hashed_password: The new password (already hashed; plain-text passwords must never be stored).

        Returns:
            The updated User object if found, or None if no such user exists.
        """
        # Always log sensitive operations — but never include the password itself
        logger.info(f"Updating password for user: {user_id}")

        # Delegates the update to the base repository
        # Sets the 'hashed_password' field to the new value
        return await self.update(user_id, hashed_password=new_hashed_password)

        # Why This Method Exists
        # | Purpose                       | Reason                                                                                                         |
        # | ----------------------------- | -------------------------------------------------------------------------------------------------------------- |
        # | Encapsulation of intent       | Makes code more readable: `repo.update_password(...)` is clearer than `repo.update(..., hashed_password=...)`. |
        # | Security-sensitive operation  | Password changes should be isolated, logged, and clear.                                                        |
        # | Consistent with other methods | Like `activate_user`, this keeps the public API focused and semantically clear.                                |

        # Security Reminder: Consider rotating a `password_changed_at` timestamp in the future, if you have such a field.

        # Optional Enhancements
        # | Enhancement               | Description                                                                                    |
        # | ------------------------- | ---------------------------------------------------------------------------------------------- |
        # | `password_changed_at`     | If your model has it, add: `password_changed_at=func.now()` in the `update()` call.            |
        # | `raise_if_not_found=True` | You could allow optional error-raising if the user doesn't exist.                              |
        # | Prevent no-op updates     | If `new_hashed_password` is the same as the current one, you might skip the update (optional). |

    async def activate_user(self, user_id: UUID) -> User | None:
        """
        Activate a user account.

        Args:
            user_id: UUID of the user to activate

        Returns:
            The updated User object if found and modified, or None if user doesn't exist.
        """
        logger.info(f"Activating user: {user_id}")

        # Delegates to the BaseRepository's update method
        # It will update the 'is_active' field to True
        return await self.update(user_id, is_active=True)

    async def deactivate_user(self, user_id: UUID) -> User | None:
        """
        Deactivate a user account.

        Args:
            user_id: UUID of the user to deactivate

        Returns:
            The updated User object if found and modified, or None if user doesn't exist.
        """
        logger.info(f"Deactivating user: {user_id}")

        # Sets 'is_active' to False
        return await self.update(user_id, is_active=False)

        # Why activate/deactivate methods Exist
        # | Purpose                    | Benefit                                                                                                                      |
        # | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
        # | **Encapsulation**          | These methods make the intent (`activate` / `deactivate`) clearer than calling `update(..., is_active=True/False)` directly. |
        # | **Reusability**            | You can use them in services, APIs, or admin panels without repeating logic.                                                 |
        # | **Separation of concerns** | You don’t need to know how `update()` works—just call a method that describes what you want to do.                           |
        # | **Logging**                | Each method logs the action, which is useful for audits, debugging, or security.                                             |

        # What Happens Internally?
        # When `await self.update(user_id, is_active=True)` is called:
        #   1. It looks up the user by ID.
        #   2. It sets the `is_active` field to `True` (or `False` for deactivation).
        #   3. If the model has an `updated_at` field, it's also updated with `func.now()`.
        #   4. Returns the updated user, or `None` if the user wasn’t found.

        # Optional Enhancements
        # | Feature                              | Description                                                                        |
        # | ------------------------------------ | ---------------------------------------------------------------------------------- |
        # | `raise_if_not_found: bool = False`   | Optional parameter to raise `NotFoundError` instead of returning `None`.           |
        # | Prevent Redundant Updates            | You could check if the user is already active/inactive and skip DB update/logging. |
        # | Audit Log                            | Add more detailed logging or hook into an audit trail for critical changes.        |

        # Example enhancement:
        # ```
        #   user = await self.get_by_id(user_id)
        #   if user and user.is_active:
        #       logger.info(f"User {user_id} is already active.")
        #       return user
        # ```

    # =================================================================================================================
    # Validation / Existence Checks
    # =================================================================================================================

    async def username_exists(self, username: str) -> bool:
        """
        Check if a username already exists.

        Args:
            username: Username to check

        Returns:
            True if username exists, False otherwise
        """
        # Calls existing get_by_username method
        # If a user is returned, then the username exists
        user = await self.get_by_username(username)
        return user is not None

        # Why it's useful:
        #   - Common for user registration or update forms to prevent duplicate usernames.
        #   - ✅ You’re using the pre-existing repository method (get_by_username) to avoid duplication.

    async def email_exists(self, email: str) -> bool:
        """
        Check if an email address already exists.

        Args:
            email: Email address to check

        Returns:
            True if email exists, False otherwise
        """
        user = await self.get_by_email(email)
        return user is not None

        # Why it's useful:
        #   - Prevents duplicate emails which usually need to be unique in systems (e.g., for authentication, notifications).
        #   - ✅ Reuses logic through get_by_email.

        # Possible Enhancements
        # | Suggestion             | Why                                                      | How                                                  |
        # | ---------------------- | -------------------------------------------------------- | ---------------------------------------------------- |
        # | **Normalize input**    | Prevent false negatives from case mismatch or whitespace | `.strip().lower()` on input                          |
        # | **Early return in DB** | Performance optimization                                 | Use `exists()` query instead of fetching full entity |
        # | **Generic version**    | Can be reused for other fields                           | e.g. `field_exists(field: str, value: Any)`          |

        # Example: Optimized username_exists using .exists():
        # If you're concerned about performance and want to avoid loading the whole user object, consider:
        # ```
        #   from sqlalchemy import exists, select
        #   async def username_exists(self, username: str) -> bool:
        #       stmt = select(exists().where(User.username == username.strip()))
        #       result = await self.db.execute(stmt)
        #       return result.scalar()
        # ```
        # This will return `True` or `False` without fetching the full `User` object.

    # =================================================================================================================
    # Aggregation / Count Operations
    # =================================================================================================================

    async def count_active_users(self) -> int:
        """
        Count the number of active users.

        Returns:
            Number of active users
        """
        # Leverages the `count()` method from `BaseRepository`,
        # passing a filter to count only users where `is_active = True`
        return await self.count(is_active=True)

        # Why it's useful:
        #   - Gives a quick metric on active user base.
        #   - Can be used for dashboards, reports, admin analytics.


# | #  | Method Name                | Purpose                                                    | Type            | Related Base Method    |
# | -- | -------------------------- | ---------------------------------------------------------- | --------------- | ---------------------  |
# | 1  | `create_user`              | Create a new user with given credentials                   | Create          | ✅ `create()`          |
# | 2  | `get_by_username`          | Get a user by username                                     | Read (single)   | ❌ Custom              |
# | 3  | `get_by_email`             | Get a user by email                                        | Read (single)   | ❌ Custom              |
# | 4  | `get_by_username_or_email` | Lookup user by either username or email (used in login)    | Read (single)   | ❌ Custom              |
# | 5  | `get_with_conversations`   | Get user and their conversations (eager loading)           | Read (relation) | ❌ Custom              |
# | 6  | `get_active_users`         | Get paginated list of active users                         | Read (list)     | ❌ Custom              |
# | 7  | `search_users`             | Search users by username/email with optional active filter | Search          | ❌ Custom              |
# | 8  | `update_profile`           | Update username and/or email                               | Update          | ✅ `update()`          |
# | 9  | `update_password`          | Update user's password                                     | Update          | ✅ `update()`          |
# | 10 | `activate_user`            | Set `is_active=True` for user                              | Update          | ✅ `update()`          |
# | 11 | `deactivate_user`          | Set `is_active=False` for user                             | Update          | ✅ `update()`          |
# | 12 | `username_exists`          | Check if username is already taken                         | Validation      | ✅ `get_by_username()` |
# | 13 | `email_exists`             | Check if email is already taken                            | Validation      | ✅ `get_by_email()`    |
# | 14 | `count_active_users`       | Count users with `is_active=True`                          | Aggregate       | ✅ `count()`           |

