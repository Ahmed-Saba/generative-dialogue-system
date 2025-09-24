"""Fixtures for repository tests."""

import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.repositories.base_repository import BaseRepository
from app.repositories.user_repository import UserRepository

# NOTE: All fixtures in this file depend on the `db_session` fixture defined in conftest.py
# The `db_session` provides a transactional, rollback-capable database session for tests.


@pytest.fixture
async def base_repo(db_session: AsyncSession) -> BaseRepository[User]:
    """
    Provide a BaseRepository instance configured for the User model.

    Usage:
        - Injected into tests that need to perform generic repository operations
          like create, update, delete, get_by_id, etc. on User entities.
        - Ensures all DB actions are performed within the test transaction
          managed by the `db_session` fixture.

    Fixtures used:
      - db_session: async SQLAlchemy session provided by conftest.py (expire_on_commit=False recommended).

    Returns:
        BaseRepository[User]: Repository instance for User with async DB session bound.
    """
    return BaseRepository(User, db_session)



@pytest.fixture
async def user_repository(db_session: AsyncSession) -> UserRepository:
    """
    Return a UserRepository bound to the same test session.

    This is used by the UserRepository tests.
    """
    return UserRepository(db_session)



@pytest.fixture
def sample_user_data() -> dict[str, str]:
    """
    Simple, deterministic sample payload used by many tests.
    Kept synchronous because it does not touch the DB.

    Usage:
        - Used as input data for repository `create()` calls.
        - Ensures consistency across tests needing a basic user payload.
        - Can be extended or overridden in specific tests if different data is needed.

    Returns:
        dict: User creation fields (username, email, hashed_password).
    """
    return {
        "username": "testuser",
        "email": "testuser@example.com",
        "hashed_password": "s3cret",
    }


@pytest.fixture
async def create_user(base_repo: BaseRepository[User]):
    """
    A small factory helper that tests can call to create users with optional overrides.

    Usage:
        user = await create_user(username="bob")
    """
    async def _create(**overrides):
        data = {
            "username": f"user_{uuid.uuid4().hex[:8]}" ,
            "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
            "hashed_password": "pw",
            "is_active": True
        }
        data.update(overrides)
        return await base_repo.create(**data)

    return _create


@pytest.fixture
async def created_user(create_user, sample_user_data) -> User:
    """
    Create and return a single persisted user (attached to the test session).

    Fixtures:
      - create_user factory
    """
    return await create_user(**sample_user_data)


@pytest.fixture
async def multiple_users(create_user) -> list[User]:
    """
    Create and return a small list of unique User entities (default: 3).

    Usage:
        - Supports tests requiring several users to test pagination, ordering,
          bulk queries, or existence checks.
        - Each user has a unique username and email generated with a UUID snippet
          to avoid conflicts and ensure uniqueness in the test database.
        - The list can be used to reference specific users by index or iterate over
          a set of test users.

    Returns:
        list[User]: List of persisted User instances with unique credentials.
    """
    users = []
    for idx in range(3):
        u = await create_user(username=f"user_{idx}_{uuid.uuid4().hex[:6]}")
        users.append(u)
    return users

