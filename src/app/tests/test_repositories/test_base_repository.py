import pytest
import uuid
from sqlalchemy.exc import IntegrityError
from app.repositories.base_repository import DuplicateError, NotFoundError, RepositoryError
from app.models.user import User
from app.repositories.base_repository import BaseRepository
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from types import SimpleNamespace


@pytest.mark.asyncio
class TestBaseRepositoryCreate:

    async def test_create_success(self, base_repo, sample_user_data):
        """
        Behavior:
                - Call BaseRepository.create(...) with valid data.
                - Assert the returned entity has expected fields and a generated id.

        Importance:
                - Confirms the basic happy-path of create(): object instantiation,
                        .add(), .flush(), .refresh() and return of a fully populated model.
                - Ensures the BaseRepository can persist and retrieve ORM instances correctly.

        Fixtures:
                - base_repo: repository connected to a transactional test session.
                - sample_user_data: dict used to populate required fields.

        Preconditions:
                - DB schema exists and unique constraints (username/email) are set.

        Postconditions:
                - New row is present for the duration of the test transaction (rolled back after test, leaving the DB clean).
                                        - Why this behavior works:

                                                - The `db_session` fixture (defined in `conftest.py`) sets up a database connection
                                                                                                                wrapped in a transactional context using an outer transaction + nested SAVEPOINT.
                                                - All database operations during the test are scoped to this transaction, even if
                                                                                                                your repository calls `.commit()`. After the test, the transaction is explicitly
                                                                                                                rolled back, discarding any changes made during the test.

                                        - Why this is needed:

                                                - This guarantees full **test isolation**: no data "leaks" from one test to another.
                                                - It enables you to safely test DB operations without requiring cleanup logic.
                                                - It allows assertions against real database behavior (e.g., ID generation, default timestamps)
                                                                                                                while keeping the test environment consistent and repeatable.
                                                - Prevents test flakiness caused by leftover rows, auto-increment collisions, or violated uniqueness constraints.
        """
        # Act: Create a new user using the repository with valid sample data
        user = await base_repo.create(**sample_user_data)

        # Assert: The returned object is not None
        assert user is not None

        # Assert: The generated ID is a valid UUID (ensures correct ID type and format)
        assert isinstance(user.id, uuid.UUID)

        # Assert: The user's fields match the input data
        assert user.username == sample_user_data["username"]
        assert user.email == sample_user_data["email"]
        assert user.hashed_password == sample_user_data["hashed_password"]

        # Assert: The user is active by default
        assert user.is_active == True

        # Assert: The user has a generated primary key (e.g., UUID or int ID)
        assert getattr(user, "id", None) is not None

        # What Does "Act" Mean in Testing?
        # In the context of testing — especially unit and integration tests — "Act" is part of a common test structure pattern called: Arrange – Act – Assert (AAA)
        #
        # It's a way to structure your test code clearly:
        # | Phase       | Description                                    | Example in your test                                   |
        # | ----------- | ---------------------------------------------- | ------------------------------------------------------ |
        # | **Arrange** | Set up the environment, objects, and test data | e.g., `sample_user_data`, `base_repo` from fixtures    |
        # | **Act**     | Execute the code you're testing (the action)   | `user = await base_repo.create(...)`                   |
        # | **Assert**  | Verify the outcome is as expected              | `assert user.username == sample_user_data["username"]` |
        #
        # Why Use AAA?
        #   - Makes tests easier to read and maintain
        #   - Helps others quickly understand what’s being tested
        #   - Encourages a clean structure in test files

    async def test_create_missing_required_field_raises_error(self, base_repo, sample_user_data):
        """
        Behavior:
                - Attempt to create a record missing a required field (e.g., username).
                - Expect a RepositoryError to be raised indicating the missing required field.

        Importance:
                - Ensures database constraints for required fields are enforced.
                - Prevents saving incomplete or invalid data.
                - Confirms repository correctly maps DB errors to user-facing exceptions.

        Fixtures:
                - base_repo: BaseRepository instance bound to a test transactional session.
                - sample_user_data: sample dict containing valid user data.

        Notes:
                - Relies on DB NOT NULL constraints and IntegrityError translation.
        """
        # Arrange: Remove a required field to simulate incomplete input
        incomplete_data = sample_user_data.copy()
        incomplete_data.pop("username")  # or "email", whichever is required
        incomplete_data.pop("email") 

        # Act & Assert: Creating with missing required field raises RepositoryError
        with pytest.raises(RepositoryError) as exc_info:
            await base_repo.create(**incomplete_data)

        print(exc_info)

        # Assert the exception message signals missing required field
        assert "Missing required field" in str(exc_info.value)

        # structured assertion: parsed missing field(s) should be available
        assert getattr(exc_info.value, "fields", None) == ["username", "email"]
        
        print(exc_info.value.fields)


    async def test_create_with_extra_field_raises_type_error(self, base_repo, sample_user_data):
        """
        Behavior:
                - Attempt to create a record passing an unexpected extra field.
                - Expect an error (TypeError or RepositoryError) indicating unknown keyword argument.

        Importance:
                - Defensive programming to catch typos or injection of unexpected fields.
                - Ensures the data model and repository interface remain strict and predictable.
                - Protects API boundary by rejecting unsupported inputs early.

        Fixtures:
                - base_repo: BaseRepository instance bound to a test transactional session.
                - sample_user_data: sample dict containing valid user data.

        Notes:
                - The error raised may depend on how the repository and ORM handle unexpected kwargs.
                - You can catch generic RepositoryError or more specific TypeError based on implementation.
        """
        # Arrange: Add an invalid extra fields to the input data
        invalid_data = sample_user_data.copy()
        invalid_data["unknown_field"] = "bad"
        invalid_data["unknown_field2"] = "bad2"

        # Act & Assert: Creating with unexpected field raises an error
        with pytest.raises(RepositoryError) as exc_info:
            await base_repo.create(**invalid_data)

        print(exc_info)

        # Optional: Could check the error message or type for stricter assertions
        # e.g. assert "unexpected keyword argument" in str(exc_info.value)


@pytest.mark.asyncio
class TestBaseRepositoryCreateDuplicates:

    async def test_create_duplicate_raises_duplicate_error(self, base_repo, sample_user_data):
        """
        Behavior:
                - Create a user successfully.
                - Attempt to create another user with identical unique fields (username/email).
                - Expect a DuplicateError to be raised to signal uniqueness violation.

        Importance:
                - Ensures integrity constraint violations at the DB level are translated into
                        the repository's DuplicateError so higher layers can handle them uniformly.

        Fixtures:
                - base_repo: BaseRepository instance bound to a test transactional session.
                - sample_user_data: sample dict containing valid user data.

        Notes:
                - The underlying DB (Postgres) enforces uniqueness; SQLAlchemy raises IntegrityError
                        which BaseRepository catches and re-raises as DuplicateError.
        """
        # Arrange: Create initial user to occupy unique keys (first creation succeeds)
        await base_repo.create(**sample_user_data)

        # Act & Assert: Creating another with identical unique fields raises DuplicateError
        with pytest.raises(DuplicateError) as exc_info:
            await base_repo.create(**sample_user_data)

        print(exc_info)            

        # Assert the exception message contains expected text
        assert "already exists" in str(exc_info.value)

        # structured assertion that the duplicate field was detected and attached
        assert getattr(exc_info.value, "fields", None) == sorted(["username", "email"])
        # also assert error_code
        assert getattr(exc_info.value, "error_code", None) == "duplicate"
        
        print(exc_info.value.error_code)


    # You can write separate tests to confirm duplicates in each unique field raise DuplicateError.

    async def test_create_duplicate_username_raises_duplicate_error(self, base_repo, sample_user_data):
        # Create first user with initial data
        await base_repo.create(**sample_user_data)

        # Try to create another user with same username but different email
        # Create a copy to avoid mutating the original fixture (sample_user_data)
        duplicate_data = sample_user_data.copy()
        duplicate_data["email"] = "different@example.com"


        with pytest.raises(DuplicateError) as exc_info:
            await base_repo.create(**duplicate_data)

        print(exc_info)            

    async def test_create_duplicate_email_raises_duplicate_error(self, base_repo, sample_user_data):
        # Create first user with initial data
        await base_repo.create(**sample_user_data)

        # Try to create another user with same email but different username
        duplicate_data = sample_user_data.copy()
        duplicate_data["username"] = "differentusername"

        with pytest.raises(DuplicateError) as exc_info:
            await base_repo.create(**duplicate_data)

        print(exc_info)            

    # | Test                                                    | Covers                            | Redundant? |
    # | ------------------------------------------------------- | --------------------------------- | ---------- |
    # | `test_create_duplicate_raises_duplicate_error`          | Full duplicate (username + email) | ❌ No      |
    # | `test_create_duplicate_username_raises_duplicate_error` | Username-only constraint          | ❌ No      |
    # | `test_create_duplicate_email_raises_duplicate_error`    | Email-only constraint             | ❌ No      |

    # 1. `test_create_duplicate_raises_duplicate_error`
    #   What it tests:
    #     - Creating two users with the exact same data → triggers duplicate key error (on both username and email).
    #   Value:
    #     - Confirms the general behavior: duplicate combination of fields leads to DuplicateError.
    #     - It's a broad/high-level test, asserting any unique constraint violation gets mapped correctly.
    #   It's your catch-all, sanity-check for uniqueness.
    #
    # 2. `test_create_duplicate_username_raises_duplicate_error`
    #   What it tests:
    #     - Duplicate username
    #     - Different email
    #   Value:
    #     - Confirms that username alone has a uniqueness constraint.
    #     - If you later removed the unique index on username, this test would fail, catching a schema regression.
    #   Verifies field-specific constraints (not just combinations).
    #
    # 3. test_create_duplicate_email_raises_duplicate_error
    #   What it tests:
    #     - Duplicate email
    #     - Different username
    #   Value:
    #     - Confirms email also has its own unique constraint.
    #     - Complements the username-specific test above.
    #   Same reason: checks individual uniqueness, not combined behavior.

    async def test_create_populates_timestamps(self, base_repo, sample_user_data):
        """
        Behavior:
                -  Create a user and assert that server-side/default timestamp columns
                        (created_at and updated_at) are populated.

        Importance:
                - Confirms that .refresh() pulled DB-generated defaults back onto the model.
                - Useful as a regression check that the model and DB defaults are wired correctly.
                - Prevents bugs where timestamps are incorrectly null or out-of-sync.

        Fixtures:
                - base_repo: Generic BaseRepository bound to a test DB session.
                - sample_user_data: Dict of valid user fields.

        Preconditions:
                - The model includes `created_at` and `updated_at` columns.
                - These columns have database defaults (e.g., `DEFAULT now()` in PostgreSQL).

        Postconditions:
                - created_at and updated_at should both be not None and logically ordered
                        (created_at <= updated_at).
        """
        # Act: Create a user via the repository
        user = await base_repo.create(**sample_user_data)

        # Assert: Timestamps are populated
        assert user.created_at is not None, "created_at should be populated"
        assert user.updated_at is not None, "updated_at should be populated"

        # Assert: created_at is not after updated_at (they can be equal, but not reversed)
        assert user.created_at <= user.updated_at, (
            f"Timestamps invalid: created_at={user.created_at}, updated_at={user.updated_at}"
        )

    async def test_concurrent_create_raises_duplicate(self, async_engine):
        """
        Behavior:
                - Simulate a race condition where two independent sessions try to insert
                        a user with the same unique fields (username/email).
                - Expect a DuplicateError when the second insert violates the uniqueness constraint.

        Importance:
                - Simulates a common real-world race condition where concurrent clients attempt
                        to insert the same unique key.
                - Ensures that uniqueness constraints are enforced at the DB level and
                        surfaced through the repository's DuplicateError.
                - Helps prevent hard-to-debug issues caused by race conditions in production.

        Fixtures:
                - async_engine: low-level AsyncEngine (not session-scoped); used here to create separate *independent*
                                                                                sessions to simulate concurrency. This avoids re-using the test's single
                                                                                session (which would automatically see uncommitted changes).
        """
        # Create a session factory manually (not using the test db_session fixture)
        maker = async_sessionmaker(
            bind=async_engine, class_=AsyncSession, expire_on_commit=False
        )

        # Create two *independent* sessions (simulating separate concurrent clients)
        async with maker() as session1, maker() as session2:
            # Create repository instances bound to each session
            repo1 = BaseRepository(User, session1)
            repo2 = BaseRepository(User, session2)

            # Arrange: Create a user in session1 and commit it to persist it to the DB
            await repo1.create(
                username="race",
                email="race@example.com",
                hashed_password="pw"
            )
            await session1.commit()

            # Act & Assert: Attempting to create the same user from session2 should raise DuplicateError
            with pytest.raises(DuplicateError) as exc_info:
                await repo2.create(
                    username="race",
                    email="race@example.com",
                    hashed_password="pw2"
                )

            print(exc_info)            


            # Optional: Confirm the error message is meaningful
            assert "already exists" in str(exc_info.value)

        # Key Concepts This Test Validates
        # | Concept                  | Purpose                                                                      |
        # | ------------------------ | ---------------------------------------------------------------------------- |
        # | Two independent sessions | Simulates realistic concurrent DB access                                     |
        # | Manual `commit()`        | Ensures that the first user is flushed to the DB before second insert        |
        # | Repository wrapping      | Makes sure the repository handles the IntegrityError properly                |
        # | `pytest.raises()`        | Confirms the raised exception is correctly transformed into `DuplicateError` |

        # NOTE:
        # This is not redundant with your earlier duplicate tests.
        #   - Your earlier tests tested duplicates in the same session.
        #   - This one tests it across committed sessions, which is a different context and more realistic in production.
        # Production value:
        #   - In high-concurrency environments (e.g., APIs, background jobs), this kind of race is common.
        #   - Validating the error path helps build confidence in your transactional boundaries and error handling.

    async def test_create_handles_integrity_error(self, monkeypatch, base_repo):
        """
        Behavior:
                - Simulate an IntegrityError during session.flush().
                - Verify that BaseRepository.create() raises DuplicateError.
                - Confirm that the session is rolled back and remains usable afterward by performing a successful create.

        Importance:
                - Tests repository error-path robustness:
                        * That IntegrityError is mapped to DuplicateError for callers.
                        * That the repository performs the necessary rollback so the session can continue
                                to execute further statements (important for test isolation and caller resilience).

        Fixtures:
                - monkeypatch: pytest fixture used to temporarily override base_repo.db.flush to simulate a DB error
                - base_repo: repository under test, bound to a transactional session.

        Implementation detail:
                - A custom `fake_flush` raises an IntegrityError only on its first call.
                        After that, it delegates to the real flush, mimicking recovery.
        """

        # Save the original flush method to call after the simulated failure
        orig_flush = base_repo.db.flush
        state = {"called": 0}

        async def fake_flush(*args, **kwargs):
            # Simulate an IntegrityError on the first call only
            if state["called"] == 0:
                state["called"] += 1
                # Fake 'orig' with a pgcode for duplicate error (23505)
                fake_orig = SimpleNamespace(
                    pgcode="23505",
                    diag=SimpleNamespace(constraint_name="users_username_key")
                )

                raise IntegrityError("fake", params={}, orig=fake_orig)
            # On subsequent calls, delegate to the real flush method
            return await orig_flush(*args, **kwargs)

        # Monkeypatch the flush method of the session
        monkeypatch.setattr(base_repo.db, "flush", fake_flush)

        # Act & Assert: First attempt should raise DuplicateError (our custom wrapper)
        with pytest.raises(DuplicateError) as exc_info:
            await base_repo.create(
                username="x",
                email="x@example.com",
                hashed_password="pw"
            )

        assert "already exists" in str(exc_info.value)

        # Act: Try again with valid and unique data — should succeed
        user = await base_repo.create(
            username="ok",
            email="ok@example.com",
            hashed_password="pw"
        )

        # Assert: Confirm that session is usable after rollback and error recovery
        assert user is not None
        assert user.username == "ok"

        # NOTES:
        # - This test is especially important if your repository may be reused across multiple operations
        # in a request or service. It protects you from InvalidRequestError or PendingRollbackError that
        # can arise if sessions are not properly rolled back after exceptions.
        #
        # - You may want to test similar rollback recovery for other exceptions later (e.g., NotNullViolation,
        # generic SQLAlchemyError), but for now this test is strong.


@pytest.mark.asyncio
class TestBaseRepositoryRead:

    async def test_get_by_id_returns_entity(self, base_repo, created_user):
        """
        Test get_by_id() returns the correct entity or None if not found.

        Behavior:
                - Attempts to retrieve an existing user using get_by_id().
                - Ensures the method safely returns the correct entity (or None if not found).

        Importance:
                - Validates the non-raising path for entity retrieval.
                - Important for flows that handle optional existence (e.g., soft lookups).

        Fixtures:
                - base_repo: repository with session.
                - created_user: known user inserted into the DB before the test.

Preconditions:
        - created_user exists in DB for the duration of the test transaction.

        """
        # Act: Attempt to retrieve the user by their UUID
        got = await base_repo.get_by_id(created_user.id)

        # Assert: Entity should exist and match the one inserted
        assert got is not None
        assert got.id == created_user.id

    async def test_get_by_id_or_raise_returns_entity(self, base_repo, created_user):
        """
        Test get_by_id_or_raise() returns entity or raises NotFoundError if missing.

        Behavior:
                - Attempts to retrieve an existing user using get_by_id_or_raise().
                - Expects the method to return the user object directly.

        Importance:
                - Validates strict retrieval flow where absence is treated as an error.
                - Supports fail-fast patterns in service or API layers (e.g., returning 404s).

        Fixtures:
                - base_repo: repository bound to an async session.
                - created_user: pre-seeded user entity.

Preconditions:
        - created_user exists in DB for the duration of the test transaction.

        """
        # Act: Attempt to retrieve the user; should return without raising
        got = await base_repo.get_by_id_or_raise(created_user.id)

        # Assert: Returned user must match the expected one
        assert got.id == created_user.id

    async def test_get_by_id_returns_none_for_missing(self, base_repo):
        """
        Behavior:
                - Call get_by_id() with a random UUID that does not exist in the database.
                - Assert it returns None instead of raising an error.

        Importance:
                - Confirms that get_by_id follows a non-raising behavior pattern for missing records.
                - Makes the contract of the method explicit and test-enforced, separate from get_by_id_or_raise.

        Fixtures:
                - base_repo: repository instance bound to a test session.
        """
        # Arrange: Generate a UUID that does not correspond to any existing record
        random_id = uuid.uuid4()

        # Act & Assert: get_by_id should return None for a non-existent entity
        assert await base_repo.get_by_id(random_id) is None

    async def test_get_by_id_or_raise_not_found(self, base_repo):
        """
        Behavior:
                - Call get_by_id_or_raise() with a random UUID that does not exist.
                - Expect NotFoundError.

        Importance:
                - Validates the repository correctly signals missing resources in the 'raise' variant,
                which higher-level code relies on for control flow (e.g., 404 responses).

        Fixtures:
                - base_repo
        """
        # Arrange: Generate a UUID that is guaranteed not to exist in the test DB
        random_id = uuid.uuid4()

        # Act & Assert: get_by_id_or_raise should raise NotFoundError for missing entity
        with pytest.raises(NotFoundError):
            await base_repo.get_by_id_or_raise(random_id)

    async def test_find_by_field_and_invalid_field(self, base_repo, created_user):
        """
        Behavior:
                        - Use find_by_field() to search by a valid field (email) and assert it returns the entity.
                        - Call find_by_field() with an invalid field name and assert it raises RepositoryError.

        Importance:
                        - Confirms dynamic field lookup works for legitimate fields.
                        - Ensures repository defends against invalid attribute names, avoiding surprising SQL generation.

        Fixtures:
                        - base_repo
                        - created_user
        """
        # Act: Search by a valid field ('email') that exists in the model
        got = await base_repo.find_by_field("email", created_user.email)

        # Assert: The correct user is returned
        assert got is not None
        assert got.email == created_user.email

        # Act & Assert: Using an invalid field name should raise a RepositoryError
        with pytest.raises(RepositoryError):
            await base_repo.find_by_field("nonexistent_field", "value")

    async def test_find_by_field_multiple_results_raises(self, base_repo):
        """
        Behavior:
                        - Create two rows that match the same field value (non-unique).
                        - Call find_by_field() which uses scalar_one_or_none() internally.
                        - Expect a RepositoryError because the repository wraps DB exceptions
                                        (MultipleResultsFound -> RepositoryError).

        Importance:
                        - Ensures the repository surface is consistent: underlying SQLAlchemy exceptions
                                        are caught and mapped to repository-level exceptions so callers don't need
                                        to depend on SQLAlchemy internals.

        Fixtures:
                        - base_repo
        """
        # Arrange: Create two users with the same hashed_password (non-unique field)
        await base_repo.create(username="a1", email="a1@example.com", hashed_password="pw")
        await base_repo.create(username="a2", email="a2@example.com", hashed_password="pw")

        # Act & Assert:
        # - The underlying scalar_one_or_none will raise MultipleResultsFound due to duplicates
        # - The repository layer should catch and re-raise it as a RepositoryError
        with pytest.raises(RepositoryError):
            await base_repo.find_by_field("hashed_password", "pw")

    async def test_get_all_order_by_field(self, base_repo):
        """
        Behavior:
                        - Insert two users with known usernames.
                        - Call get_all(order_by='username') and assert the returned list is ordered by username.

        Importance:
                        - Verifies that the `order_by` argument is respected when valid, enabling predictable
                                        ordering for listing endpoints and pagination.

        Fixtures:
                        - base_repo
        """
        # Arrange: Create two users with distinct usernames for ordering check
        u1 = await base_repo.create(username="a", email="a@example.com", hashed_password="pw")
        u2 = await base_repo.create(username="b", email="b@example.com", hashed_password="pw")

        # Act: Retrieve all users ordered by the 'username' field (ascending by default)
        res = await base_repo.get_all(order_by="username")

        # Assert: Ensure ordering by username is correct
        assert [r.username for r in res][:2] == ["a", "b"]

    async def test_get_all_ignores_invalid_order_by(self, base_repo, multiple_users):
        """
        Behavior:
                - Call get_all() with an invalid order_by field name.
                - Confirm that no exception is raised.
                - Ensure the method returns a list of entities as usual.

        Importance:
                - Verifies that the repository gracefully handles invalid ordering parameters,
                  preventing crashes or unhandled errors.
                - Protects against regression if the order_by validation logic changes.

        Fixtures:
                - base_repo
                - multiple_users: existing user records to query against

        Notes:
                - The invalid 'order_by' field should be ignored with a warning, not a failure.
        """
        # Act: Call get_all with an invalid order_by field
        res = await base_repo.get_all(order_by="this_field_does_not_exist")

        # Assert: The call should not raise and return a list (possibly empty)
        assert isinstance(res, list)

    async def test_pagination_edges(self, base_repo, multiple_users):
        """
        Behavior:
                - Call get_all() with an extremely large offset to test that it returns an empty list.
                - Call get_all() with limit=0 to test that it returns an empty list.

        Importance:
                - Validates that pagination handles edge cases gracefully without errors.
                - Confirms that requests beyond the available dataset do not break the system.
                - Ensures defensive behavior when limit is zero, preventing unexpected results.

        Fixtures:
                - base_repo
                - multiple_users (a pre-populated collection of user entities)

        Notes:
                - Such tests help guarantee robust and predictable pagination behavior in APIs or UI lists.
        """
        # Large offset beyond dataset should return empty list
        assert await base_repo.get_all(offset=99999, limit=10) == []

        # Limit set to zero should defensively return empty list
        assert await base_repo.get_all(offset=0, limit=0) == []


@pytest.mark.asyncio
class TestBaseRepositoryQuerying:

    async def test_get_all_pagination_order_and_count_exists(self, base_repo, multiple_users):
        """
        Behavior:
                        - Call get_all(offset=0, limit=10) and verify it returns a list.
                        - Check that at least the number of users created by the `multiple_users` fixture are present.
                        - Call count() and verify it returns an integer >= the number of created users.
                        - Use exists() to verify a known id is present, and a random UUID is not present.

        Importance:
                        - get_all() is commonly used by list endpoints; this test ensures pagination
                                        and retrieval returns sensible results.
                        - count() is important for pagination metadata (total rows).
                        - exists() is a lightweight existence check used frequently to validate references
                                        before heavier operations (avoid fetching entire rows when unnecessary).

        Fixtures:
                        - base_repo: repository bound to transactional session.
                        - multiple_users: pre-populated list of users (at least 3 in the fixture implementation).

        Preconditions:
                        - The `multiple_users` fixture has created multiple rows and they are visible
                                        in the current transactional context.

        Postconditions:
                        - No permanent DB changes — test session is rolled back by fixture teardown.
        """
        # multiple_users fixture created 3 users in the test DB
        all_items = await base_repo.get_all(offset=0, limit=10)
        # Assert the result is a list of entities
        assert isinstance(all_items, list)
        # Assert that at least 3 users (from the fixture) are returned
        assert len(all_items) >= 3

        # Call count() with no filter to get total number of users
        cnt = await base_repo.count()
        # Assert count returns an integer
        assert isinstance(cnt, int)
        # Assert the count is at least the number of users created by the fixture
        assert cnt >= 3

        # Check existence of a known user's ID (from fixture data)
        exists = await base_repo.exists(multiple_users[0].id)
        # Assert the user exists in the DB
        assert exists is True

        # Check existence of a random UUID that should not be present
        assert (await base_repo.exists(uuid.uuid4())) is False

    async def test_count_with_filters(self, base_repo):
        """
        Behavior:
                        - Create two users: one active and one inactive.
                        - Assert that count() returns total rows and that count(is_active=True) filters correctly.
                        - Also call count() with an invalid filter key (nonexistent_field) and assert it
                                        returns an int rather than raising.

        Importance:
                        - Validates dynamic filter application in count(): useful for building filtered
                                        list endpoints (e.g., only active users).
                        - Ensures resilience to unexpected/invalid filter keys (it should ignore them
                                        rather than throw unhandled exceptions).

        Fixtures:
                        - base_repo

        Notes:
                        - The current implementation of `BaseRepository.count` only applies filters when
                                        the field exists on the model. Invalid filter keys are ignored (and that's what
                                        this test asserts).
        """
        # create a couple of users with different is_active values
        await base_repo.create(username="c1", email="c1@example.com", hashed_password="pw")
        await base_repo.create(username="c2", email="c2@example.com", hashed_password="pw", is_active=False)

        # total count should be >= 2
        assert await base_repo.count() >= 2

        # filtered count (only active users) should be at least 1
        assert await base_repo.count(is_active=True) >= 1

        # invalid field must be ignored; should still return an integer
        assert isinstance(await base_repo.count(nonexistent_field="x"), int)

    async def test_count_multiple_filters(self, base_repo):
        """
        Behavior:
                - Create two users with different 'is_active' statuses.
                - Call count() with a valid filter (is_active=True) and assert it returns a count >= 1.
                - Call count() with multiple filters including an invalid one (nonexistent) and ensure it
                does not raise and returns an integer count.

        Importance:
                - Validates that count() correctly applies multiple filters and gracefully ignores invalid keys,
                ensuring robust filter handling in query construction.

        Fixtures:
                - base_repo: repository bound to transactional session.

        Preconditions:
                - Test runs in isolated transactional context.
        """
        # Create a user with is_active=True
        await base_repo.create(username="f1", email="f1@example.com", hashed_password="pw", is_active=True)
        # Create a user with is_active=False
        await base_repo.create(username="f2", email="f2@example.com", hashed_password="pw", is_active=False)

        # Assert that count with filter is_active=True returns at least one user
        assert await base_repo.count(is_active=True) >= 1

        # Assert that count with an invalid filter key (nonexistent) does not raise and returns an int
        assert isinstance(await base_repo.count(is_active=True, nonexistent="x"), int)


class TestBaseRepositoryUpdate:

    async def test_update_changes_field(self, base_repo, created_user):
        """
        Behavior:
                        - Update a simple field (username) on an existing entity.
                        - Assert the returned entity reflects the new value.

        Importance:
                        - Basic correctness check: the update() method must persist field changes
                                        and return the fresh entity for immediate use.

        Fixtures:
                        - base_repo
                        - created_user (existing user id used as target)
        """
        new_username = "updated_username"

        # Act: perform update on the existing user's username
        updated = await base_repo.update(created_user.id, username=new_username)

        # Assert: ensure update returned a non-None entity
        assert updated is not None

        # Assert: the username is correctly updated
        assert updated.username == new_username

    async def test_update_no_valid_data_returns_same(self, base_repo, created_user):
        """
        Behavior:
                        - Call update() with only None or empty-string values.
                        - Expect the repository to detect "no meaningful update" and return the current entity unchanged.

        Importance:
                        - Avoids accidentally overwriting fields with null/empty values.
                        - Provides a predictable no-op behavior when callers pass optional fields that are not present.

        Fixtures:
                        - base_repo
                        - created_user
        """
        # pass only None or empty values (no meaningful data) -> should return current entity unchanged
        same = await base_repo.update(created_user.id, username=None, email="")

        # Assert: The returned entity should still exist (not None)
        assert same is not None

        # Assert: The entity ID should remain the same, indicating no change
        assert same.id == created_user.id

    async def test_update_duplicate_raises(self, base_repo):
        """
        Behavior:
                        - Create two users with distinct unique fields.
                        - Attempt to update the second user so that it conflicts (same email) with the first user.
                        - Expect DuplicateError to be raised.

        Importance:
                        - Ensures update operations that would violate unique constraints are detected
                                        and converted to DuplicateError so calling code can handle them consistently.

        Fixtures:
                        - base_repo
        """
        # Arrange: create two users with unique emails
        u1 = await base_repo.create(username="u_dup_1", email="dup1@example.com", hashed_password="pw1")
        u2 = await base_repo.create(username="u_dup_2", email="dup2@example.com", hashed_password="pw2")

        # Act & Assert: updating u2’s email to u1’s email should raise DuplicateError due to uniqueness violation
        with pytest.raises(DuplicateError):
            await base_repo.update(u2.id, email=u1.email)

    async def test_update_sets_updated_at(self, base_repo, created_user):
        """
        Behavior:
                        - Update a field and assert that `updated_at` has been set/advanced.

        Importance:
                        - Verifies that the repository correctly sets the `updated_at` timestamp
                                        (via func.now()) so callers and consumers can rely on last-modified metadata.

        Fixtures:
                        - base_repo
                        - created_user
        """
        # Capture the old updated_at timestamp before the update
        old_updated = created_user.updated_at

        # Perform update on username field
        updated = await base_repo.update(created_user.id, username="newname")

        # Assert updated_at is set (not None)
        assert updated.updated_at is not None

        # Assert updated_at is newer or equal to previous timestamp
        assert updated.updated_at >= old_updated

    async def test_update_with_invalid_field_raises(self, base_repo, created_user):
        """
        Behavior:
                        - Attempt to update with a non-existent/invalid field name.
                        - Expect RepositoryError because the repository wraps DB-level exceptions.

        Importance:
                        - Ensures invalid usage is signaled with a repository-level error rather than
                                        leaking raw SQLAlchemy exceptions to higher layers.
                        - Encourages callers to validate field names before calling update, or to rely
                                        on the repository to convert DB errors into consistent domain errors.

        Fixtures:
                        - base_repo
                        - created_user
        """
        # Attempt update with a field that does not exist on the model
        # Should raise RepositoryError as repository converts DB exceptions
        with pytest.raises(RepositoryError):
            await base_repo.update(created_user.id, non_existent_field="x")

    async def test_update_not_found_returns_none(self, base_repo):
        """
        Behavior:
                        - Attempt to update an entity by a UUID that does not exist in the database.
                        - Expect the update() method to return None, indicating no rows were affected.

        Importance:
                        - Ensures callers receive a consistent and predictable response when updating missing records.
                        - Prevents unexpected errors or side effects when the target entity is not found.

        Fixtures:
                        - base_repo

        Preconditions:
                        - The random UUID does not exist in the database.

        Postconditions:
                        - No changes are made to the database.
        """
        # Generate a random UUID guaranteed not to exist in the DB
        random_id = uuid.uuid4()

        # Attempt update on non-existent entity; expect None result
        result = await base_repo.update(random_id, username="noone")

        # Assert update returns None indicating no rows were updated
        assert result is None


@pytest.mark.asyncio
class TestBaseRepositoryDelete:

    async def test_delete_success_and_no_longer_exists(self, base_repo):
        """
        Behavior:
                        - Create a User.
                        - Delete it via BaseRepository.delete(user_id).
                        - Assert delete() returns True and a subsequent exists() returns False.

        Importance:
                        - Confirms that delete() actually removes the row from the database
                                        (within the transactional scope used for testing).
                        - Validates that exists() can be used to efficiently confirm deletion without fetching full rows.

        Fixtures:
                        - base_repo

        Preconditions:
                        - The created user exists in the test transaction.

        Postconditions:
                        - The user is removed for the duration of the transaction (rolled back by fixture teardown).
        """
        # Create a new user to be deleted later
        u = await base_repo.create(username="to_delete", email="to_delete@example.com", hashed_password="pw")

        # Delete the user by ID, expecting True on successful deletion
        deleted = await base_repo.delete(u.id)
        assert deleted is True

        # Verify that the user no longer exists in the database (after deletion, exists should be False)
        assert (await base_repo.exists(u.id)) is False

    async def test_delete_not_found_returns_false(self, base_repo):
        """
        Behavior:
                        - Call delete() with a random UUID that does not correspond to any record.
                        - Expect delete() to return False (indicating nothing was deleted).

        Importance:
                        - Ensures the delete() method gracefully handles attempts to remove non-existent resources
                                        instead of throwing unexpected exceptions. This makes higher-level code simpler (no need for try/except).

        Fixtures:
                        - base_repo
        """
        # Generate a random UUID guaranteed not to exist in the DB
        random_id = uuid.uuid4()

        # Attempt deletion; expect False because no matching record exists
        assert (await base_repo.delete(random_id)) is False

    async def test_delete_idempotent(self, base_repo):
        """
        Behavior:
                        - Create a User.
                        - Delete it and assert True is returned.
                        - Attempt to delete the same id again and assert False is returned.

        Importance:
                        - Confirms idempotency: repeated delete operations are safe and produce expected results.
                        - Idempotent delete is a common expectation for RESTful APIs and simplifies retry logic.

        Fixtures:
                        - base_repo
        """
        # Create a temporary user to delete
        u = await base_repo.create(username="tmp", email="tmp@example.com", hashed_password="pw")

        # First deletion should succeed and return True
        assert await base_repo.delete(u.id) is True

        # Second deletion of the same ID should return False, indicating nothing to delete
        assert await base_repo.delete(u.id) is False
