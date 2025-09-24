"""
Core pytest configuration for the entire test suite.

This module provides only the essential database setup and core utilities
that are needed across ALL types of tests (repositories, models, APIs, services, auth, etc.).

Domain-specific fixtures (repositories, models, etc.) are located in:
- tests/test_fixtures/repository_fixtures.py
- tests/test_fixtures/model_fixtures.py
- tests/test_fixtures/api_fixtures.py
- tests/test_fixtures/service_fixtures.py
- tests/test_fixtures/auth_fixtures.py
- ...

This separation keeps conftest.py clean and allows for modular test organization.
"""

import os
import sys
import asyncio
import pytest
import logging

from pathlib import Path
from urllib.parse import urlparse
from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
)

from app.database.base import Base
from app.config import get_settings
from app.models import user, conversation, message  # noqa: F401 – import to register models with Base.metadata

# Configure logging
logger = logging.getLogger(__name__)

# if not logger.hasHandlers():
#     logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------------------------------------------
# Determining and Logging the Test Database URL for Tests
# ------------------------------------------------------------------------------------------------

# Load settings
settings = get_settings()

def safe_log_db_url(db_url: str) -> str:
    """
    Return a sanitized version of the database URL for safe logging.

    This function parses the database URL and reconstructs it to exclude
    sensitive information such as username and password. It keeps only
    the scheme, hostname, port, and database name for informational purposes.

    Args:
        db_url (str): The full database URL string.

    Returns:
        str: A sanitized database URL with sensitive credentials removed.
    """
    # Parse the URL into components (scheme, netloc, path, params, query, fragment)
    parsed = urlparse(db_url)

    # Rebuild the URL with only scheme, hostname, port, and path (database name)
    # Exclude username and password to avoid leaking sensitive info in logs.
    # Use lstrip('/') to clean the leading slash from the path component.
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port or ''}/{parsed.path.lstrip('/')}"

# Determine the test database URL
def get_test_database_url() -> str:
    """
    Determine the test database URL.

    This function checks multiple sources to determine which database URL to use for testing:
    1. `TEST_DATABASE_URL` environment variable (CI/CD override) - prioritized if available
    2. App's `DATABASE_URL` with `TESTING=true` - triggers a separate test database if `TESTING=True`
    3. SQLite fallback for local development - for running tests without an actual DB server

    This setup ensures flexibility, allowing it to support CI/CD pipelines, testing environments,
    and local testing with SQLite for fast, isolated tests.

    Returns:
        str: The database URL to use for testing
    """

    # Priority 1: Check if a custom test database URL is provided via the environment variable
    # Useful for CI/CD or when overriding default configurations
    if test_url := os.getenv("TEST_DATABASE_URL"):
        return test_url

    # Priority 2: Use the app's DATABASE_URL if it's in "testing" mode.
    # If TESTING=True in app settings, it will use TEST_POSTGRES_DB for the test database name.
    if settings.TESTING and settings.TEST_POSTGRES_DB:
        return settings.DATABASE_URL  # The DATABASE_URL includes TEST_POSTGRES_DB for testing

    # Priority 3: If no test database URL is provided, default to an SQLite database
    # for local development, which doesn't require any external database setup.
    return "sqlite+aiosqlite:///./test_database.db"


# Global test database configuration
TEST_DATABASE_URL = get_test_database_url()
logger.info(f"Using test DB: {safe_log_db_url(TEST_DATABASE_URL)}")

# ------------------------------------------------------------------------------------------------
# ENVIRONMENT / PLATFORM FIXES
# ------------------------------------------------------------------------------------------------

# On Windows, psycopg async needs the SelectorEventLoop (not the default ProactorEventLoop).
# Set policy early at import time so pytest-asyncio uses it.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        # older/newer python weirdness: if not available, ignore (unlikely on supported Windows)
        pass

# ------------------------------------------------------------------------------------------------
# PATH PATCHING
# ------------------------------------------------------------------------------------------------

# Ensure 'src' on sys.path so `import app...` works when running tests
SRC = Path(__file__).resolve().parents[2]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ------------------------------------------------------------------------------------------------
# DATABASE FIXTURES
# ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="session")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL, echo=False, future=True, pool_pre_ping=True
    )

    # create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # teardown
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture()
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create a transaction-per-test using a SAVEPOINT (nested transaction).
    This gives full test isolation even if code calls `commit()`.

    Pattern:
      - acquire a connection
      - begin an outer transaction on that connection
      - begin a nested transaction (SAVEPOINT)
      - bind an AsyncSession to the connection
      - install event listener that recreates SAVEPOINT after commits
      - yield session to test
      - cleanup: close session and rollback outer transaction
    """
    # Acquire a single raw connection for the test
    async with async_engine.connect() as connection:
        # Outer transaction (will be rolled back at test end)
        await connection.begin()

        # Begin a nested transaction (SAVEPOINT)
        await connection.begin_nested()

        # Create a session factory bound to the *connection*
        maker = async_sessionmaker(
            bind=connection, class_=AsyncSession, expire_on_commit=False)
        session: AsyncSession = maker()

        # Event handler to restart savepoint after commits that end nested transactions.
        # This mirrors the example from SQLAlchemy docs.
        def _restart_savepoint(sync_session, transaction):
            # `transaction` is the SyncTransaction; only restart for SAVEPOINT-end events.
            if transaction.nested and not getattr(transaction._parent, "nested", False):
                # Begin a new nested transaction on the sync_session (this is sync API)
                sync_session.begin_nested()

        # Attach the listener to the session's underlying synchronous session object
        event.listen(session.sync_session,
                     "after_transaction_end", _restart_savepoint)

        try:
            yield session
            # After test, ensure the session state is clean
            await session.rollback()
        finally:
            # Remove the listener to avoid leaking it to other sessions
            try:
                event.remove(session.sync_session,
                             "after_transaction_end", _restart_savepoint)
            except Exception:
                # ignore if removal fails for any reason
                pass

            # Close the session (if not already closed)
            await session.close()

            # Roll back the outer transaction so all changes in the test are undone
            # (this also drops the nested savepoint)
            await connection.rollback()



# Repository test fixtures
from .test_fixtures.repository_fixtures import (
    base_repo,
    user_repository,
    sample_user_data,
    create_user,
    created_user,
    multiple_users,
)


# @pytest.fixture()
# async def db_session(async_engine):
#     maker = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

#     async with maker() as session:
#         yield session
#         await session.rollback()


r"""
# ====================================================================
# when should you import fixtures from `test_fixtures` in `conftest.py`
# ====================================================================

Option 1: Fixtures in conftest.py for global/shared access

    If you want fixtures to be available automatically across your entire test suite (without imports), 
    put them in conftest.py.

    ```
    # conftest.py
    @pytest.fixture
    def db_session():
        ...
    ````
    Any test file can now use `db_session` without importing it.
    

Option 2: Fixtures in test_fixtures/ for local/explicit use

    If you put fixtures in `tests/test_fixtures/repository_fixtures.py`, they are not automatically available 
    in other test files.

    To use them, you must import them explicitly:
    ```
    # test_repositories.py
    from tests.test_fixtures.repository_fixtures import sample_users
    ```
    This keeps fixture scope modular and controlled.
    

Option 3: Import them (`test_fixtures/`) in `conftest.py` if you want them globally available

    You can import fixtures from `test_fixtures/` into conftest.py if you want to register them globally 
    without duplicating code.

    ```
    # conftest.py
    from tests.test_fixtures.repository_fixtures import sample_users
    ```
    Now any test file can use `sample_users` without importing it themselves.

    
Best Practices Summary:
| Use Case                              | Best Practice                                 |
| ------------------------------------- | --------------------------------------------- |
| Fixture used across many test files   | Move to `conftest.py` or import it there      |
| Fixture used in only 1-2 test files   | Keep in module and import directly            |
| Want to keep fixtures modular/scoped  | Keep in their own file (like `test_fixtures`) |
| Want global access to custom fixtures | Import them into `conftest.py`                |
"""
