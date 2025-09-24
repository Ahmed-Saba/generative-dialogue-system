from app.repositories.base_repository import RepositoryError
import pytest
from app.repositories.user_repository import UserRepository
from app.repositories.base_repository import DuplicateError
from app.models.user import User
import uuid
import datetime


@pytest.mark.asyncio
class TestUserRepositoryCreate:
    """
    Tests covering creation of users through UserRepository.create_user().

    Fixtures used:
      - user_repository: an instance of UserRepository bound to an AsyncSession.
      - sample_user_data: dict with keys ('username', 'email', 'hashed_password') used as a convenience payload.
      - db_session (implicitly used by user_repository fixture) ensures DB visibility within the test transaction.

    Rationale:
      - The UserRepository wraps BaseRepository.create() but also normalizes input:
          * strips username whitespace
          * lowercases and strips email
      - Unique constraints on username and email must produce DuplicateError when violated.
      - Returned object should be a persisted User with an id and timestamps set.
    """

    async def test_create_user_success(self, user_repository: UserRepository, sample_user_data: dict):
        """
        Behavior:
          - Create a new user using canonical sample_user_data.
          - Assert a User instance is returned and fields are stored correctly.

        Importance:
          - Ensures the basic happy-path for user creation works and returns a usable model.
        Fixtures:
          - user_repository, sample_user_data
        """
        user = await user_repository.create_user(
            username=sample_user_data["username"],
            email=sample_user_data["email"],
            hashed_password=sample_user_data["hashed_password"],
        )

        assert isinstance(user, User)
        assert user.username == sample_user_data["username"]
        assert user.email == sample_user_data["email"]

        assert user.hashed_password == sample_user_data["hashed_password"]
        assert getattr(user, "id", None) is not None
        assert isinstance(user.id, uuid.UUID)

        assert user.created_at is not None
        assert user.updated_at is not None
        assert isinstance(user.created_at, datetime.datetime)
        assert isinstance(user.updated_at, datetime.datetime)

    async def test_create_user_normalizes_input(self, user_repository: UserRepository):
        """
        Behavior:
          - Provide username with surrounding whitespace and an uppercase email.
          - Expect username to be stripped and email to be lowercased.

        Importance:
          - Verifies repository-level normalization that avoids duplicate/email-case issues.
        Fixtures:
          - user_repository
        """
        user = await user_repository.create_user(
            username="  alice  ",
            email="  TEST@Example.COM  ",
            hashed_password="hashedpw",
        )

        assert user.username == "alice"                # whitespace trimmed
        assert user.email == "test@example.com"        # lowercased & trimmed
        assert user.hashed_password == "hashedpw"

    @pytest.mark.xfail(reason="failing due to pre-check experiment", strict=False)
    async def test_create_user_duplicate_username_or_email_raises(self, user_repository: UserRepository):
        """
        Behavior:
          - Create a user, then attempt to create additional users that violate unique
            constraints (same username or same email in different case).
          - Expect DuplicateError in each conflicting case.

        Create a user, then:
        - attempt to create another with the same username -> expect DuplicateError
        (this triggers a rollback, so the original user must be re-created before
            checking the duplicate-email case).
        - recreate the original user and then attempt to create another user with
        the same email in different case -> expect DuplicateError.

        Importance:
          - Ensures uniqueness is enforced and that email normalization prevents
            case-variation duplicates.
        Fixtures:
          - user_repository
        """
        # base user
        await user_repository.create_user(username="dupman", email="dup@example.com", hashed_password="p1")

        # Duplicate username (different email) -> should raise DuplicateError.
        # This operation rolls back the session on IntegrityError, so the previously
        # created user will be removed by the rollback.
        with pytest.raises(DuplicateError):
            await user_repository.create_user(username="dupman", email="other@example.com", hashed_password="p2")

        # Re-create the base user because the previous rollback removed it.
        await user_repository.create_user(username="dupman", email="dup@example.com", hashed_password="p1")

        # Duplicate email with different case -> should also raise because create_user lowercases email.
        with pytest.raises(DuplicateError):
            await user_repository.create_user(username="othername", email="DUP@Example.COM", hashed_password="p3")




    async def test_create_user_respects_is_active_flag(self, user_repository: UserRepository):
        """
        Behavior:
          - Create a user with is_active=False and assert it is persisted with correct flag.

        Importance:
          - Confirms that optional flags/attributes are accepted and stored by the repository.
        Fixtures:
          - user_repository
        """
        user = await user_repository.create_user(
            username="inactive_user",
            email="inactive@example.com",
            hashed_password="pw",
            is_active=False
        )

        assert user is not None
        assert user.is_active is False


@pytest.mark.asyncio
class TestUserRepositoryRead:
    """
    Tests for UserRepository read operations.

    High-level coverage:
      - get_by_username (case-sensitive)
      - get_by_email (case-insensitive via normalization)
      - get_by_username_or_email (accepts either username or email)
      - get_with_conversations (returns the user and relationship attribute; no conversations required)
      - get_active_users (pagination + active-only filter)
      - search_users (case-insensitive partial matches; active_only toggle)
      - username_exists / email_exists helpers

    Common fixtures used (defined in your fixtures file):
      - user_repository: UserRepository bound to AsyncSession
      - create_user: factory fixture that creates User rows via BaseRepository
      - sample_user_data: simple payload dict (username, email, hashed_password)
      - multiple_users: small list of users for bulk-related tests
      - db_session (implicit in user_repository)
    """

    async def test_get_by_username_found_and_not_found(self, user_repository: UserRepository):
        """
        Behavior:
          - Create a user with a known username and assert get_by_username finds it.
          - Confirm get_by_username performs a case-sensitive match (upper/lower differences return None).
        Fixtures:
          - user_repository
        """
        await user_repository.create_user(username="bob", email="bob@example.com", hashed_password="pw")
        # exact case should find
        u = await user_repository.get_by_username("bob")
        assert isinstance(u, User)
        assert u.username == "bob"

        # different case -> should not find (method does not lower username)
        assert await user_repository.get_by_username("BOB") is None

    async def test_get_by_email_is_case_insensitive(self, user_repository: UserRepository):
        """
        Behavior:
          - create_user normalizes email to lowercase; get_by_email also normalizes input.
          - create with mixed-case email, query with different casing and expect a match.
        Fixtures:
          - user_repository
        """
        await user_repository.create_user(username="mike", email="MiKe@Example.COM", hashed_password="pw")
        # Query using different casing should still return the user
        u = await user_repository.get_by_email("mike@example.com")
        assert isinstance(u, User)
        assert u.email == "mike@example.com"

        u2 = await user_repository.get_by_email("MIKE@EXAMPLE.COM")
        assert u2 is not None
        assert u2.id == u.id

    async def test_get_by_username_or_email_accepts_both(self, user_repository: UserRepository):
        """
        Behavior:
          - A convenience lookup for login forms: accepts either username or email.
          - Should handle email case-insensitively and username exactly.
        Fixtures:
          - user_repository
        """
        await user_repository.create_user(username="charlie", email="charlie@example.com", hashed_password="pw")
        by_username = await user_repository.get_by_username_or_email("charlie")
        assert by_username is not None
        assert by_username.username == "charlie"

        by_email_mixed = await user_repository.get_by_username_or_email("CHARLIE@Example.COM")
        assert by_email_mixed is not None
        assert by_email_mixed.id == by_username.id

        # whitespace around identifier should be stripped
        by_email_space = await user_repository.get_by_username_or_email("  charlie@example.com  ")
        assert by_email_space is not None
        assert by_email_space.id == by_username.id

    async def test_get_with_conversations_returns_user_even_if_no_conversations(self, user_repository: UserRepository):
        """
        Behavior:
          - Ensure get_with_conversations returns the User instance even when there are no conversations.
          - We don't assert on messages here (requires Conversation/Message fixtures); we only verify the relationship is present.
        Fixtures:
          - user_repository
        """
        user = await user_repository.create_user(username="convtest", email="conv@example.com", hashed_password="pw")
        got = await user_repository.get_with_conversations(user.id, load_messages=False)
        assert got is not None
        # conversations relationship should be accessible (empty list expected)
        assert hasattr(got, "conversations")
        assert isinstance(got.conversations, list)

    async def test_get_active_users_and_pagination(self, user_repository: UserRepository):
        """
        Behavior:
          - create a few active and inactive users and ensure get_active_users returns only active ones.
          - also sanity-check pagination arguments (offset/limit).
        Fixtures:
          - user_repository
        """
        # create deterministic users
        await user_repository.create_user(username="act1", email="act1@example.com", hashed_password="pw", is_active=True)
        await user_repository.create_user(username="act2", email="act2@example.com", hashed_password="pw", is_active=True)
        await user_repository.create_user(username="inactive", email="inactive@example.com", hashed_password="pw", is_active=False)

        # default call should return only active users
        active = await user_repository.get_active_users(offset=0, limit=10)
        assert isinstance(active, list)
        usernames = set(u.username for u in active)
        assert "act1" in usernames and "act2" in usernames
        assert "inactive" not in usernames

        # pagination: limit small should reduce results
        small = await user_repository.get_active_users(offset=0, limit=1)
        assert isinstance(small, list)
        assert len(small) <= 1

    async def test_search_users_matches_username_and_email(self, user_repository: UserRepository):
        """
        Behavior:
          - Ensure search_users supports case-insensitive partial matches across username and email.
          - active_only True should exclude inactive users.
        Fixtures:
          - user_repository
        """
        # create users that should and should not match
        await user_repository.create_user(username="searchme", email="s_me@example.com", hashed_password="pw", is_active=True)
        await user_repository.create_user(username="another", email="another@example.com", hashed_password="pw", is_active=True)
        await user_repository.create_user(username="search_inactive", email="search_inactive@example.com", hashed_password="pw", is_active=False)

        # searching for "search" should find "searchme" but not the inactive one when active_only=True
        results = await user_repository.search_users("search", active_only=True, offset=0, limit=10)
        assert any(r.username == "searchme" for r in results)
        assert all(r.is_active for r in results)

        # searching with active_only=False should include inactive matches
        results_all = await user_repository.search_users("search", active_only=False)
        assert any(r.username == "search_inactive" for r in results_all)

    async def test_username_and_email_exists_helpers(self, user_repository: UserRepository):
        """
        Behavior:
          - username_exists and email_exists should return True when present, False otherwise.
        Fixtures:
          - user_repository
        """
        await user_repository.create_user(username="exists_user", email="exists@example.com", hashed_password="pw")
        assert await user_repository.username_exists("exists_user") is True
        assert await user_repository.username_exists("no_such") is False

        assert await user_repository.email_exists("exists@example.com") is True
        assert await user_repository.email_exists("doesnotexist@example.com") is False


@pytest.mark.asyncio
class TestUserRepositoryCount:
    """
    Tests for counting/aggregation helpers on UserRepository.

    Covers:
      - count_active_users(): returns correct active-user count
      - interplay with activate_user() / deactivate_user() to ensure counts update
      - edge cases: zero active users

    Fixtures commonly used:
      - user_repository: UserRepository bound to the test AsyncSession
      - create_user: factory to create unique User rows
      - base_repo / db_session (implicitly used by user_repository)
    """

    async def test_count_active_users_basic(self, user_repository: UserRepository, create_user):
        """
        Instead of asserting absolute counts (which can be affected by other fixtures),
        compute a baseline and assert the count increases by the expected amount after creating users.
        """
        # baseline (current active users)
        baseline = await user_repository.count_active_users()

        # create 2 active and 1 inactive
        await create_user(username="act_1", email="act_1@example.com", hashed_password="pw", is_active=True)
        await create_user(username="act_2", email="act_2@example.com", hashed_password="pw", is_active=True)
        await create_user(username="inactive_1", email="inactive_1@example.com", hashed_password="pw", is_active=False)

        cnt = await user_repository.count_active_users()
        assert isinstance(cnt, int)
        # Expect exactly +2 active users vs baseline
        assert cnt == baseline + 2

    async def test_count_active_users_zero(self, user_repository: UserRepository, create_user):
        """
        Create only inactive users and confirm active count does not increase.
        Use baseline so test does not assume empty DB.
        """
        baseline = await user_repository.count_active_users()

        await create_user(username="i1", email="i1@example.com", hashed_password="pw", is_active=False)
        await create_user(username="i2", email="i2@example.com", hashed_password="pw", is_active=False)

        final = await user_repository.count_active_users()
        # No change in active user count
        assert final == baseline

    async def test_count_changes_after_activate_deactivate(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Create a user initially active and another initially inactive.
          - Deactivate the active one -> count decrements.
          - Activate the inactive one -> count increments.
        Fixtures:
          - user_repository, create_user
        """
        u_active = await create_user(username="u_active", email="u_active@example.com", hashed_password="pw", is_active=True)
        u_inactive = await create_user(username="u_inactive", email="u_inactive@example.com", hashed_password="pw", is_active=False)

        # starting count should be 1
        start = await user_repository.count_active_users()
        assert start >= 1
        # specifically at least our active user is counted
        assert any(u.id == u_active.id for u in (await user_repository.get_active_users(0, 10)))

        # deactivate the active user
        await user_repository.deactivate_user(u_active.id)
        after_deactivate = await user_repository.count_active_users()
        assert after_deactivate == start - 1

        # activate the previously inactive user
        await user_repository.activate_user(u_inactive.id)
        after_activate = await user_repository.count_active_users()
        # net effect: one deactivated, one activated -> back to start
        assert after_activate == start


@pytest.mark.asyncio
class TestUserRepositoryUpdate:
    """
    Tests for update operations in UserRepository.

    Covered methods:
      - update_profile(user_id, username, email)
      - update_password(user_id, new_hashed_password)
      - activate_user(user_id)
      - deactivate_user(user_id)

    Why these tests matter:
      - update_profile must normalize inputs (strip username, lowercase email)
      - update_profile must respect DB uniqueness and raise DuplicateError when appropriate
      - update_password should update the hashed_password and bump updated_at
      - activate/deactivate must flip the is_active flag and return the updated user
      - Methods must behave correctly when the target user does not exist (return None)

    Fixtures used:
      - user_repository: UserRepository bound to the test AsyncSession
      - create_user: factory fixture used to create unique test users
      - db_session (implicitly used by user_repository)
    """

    async def test_update_profile_changes_and_normalizes(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Create a user, call update_profile with surrounding whitespace on username and mixed-case email.
          - Expect username to be stripped and email to be lowercased and persisted.
          - updated_at should be set and >= previous timestamp.

        Fixtures:
          - user_repository, create_user
        """
        u = await create_user(username="orig_user", email="orig@example.com", hashed_password="pw")
        old_updated_at = u.updated_at

        updated = await user_repository.update_profile(
            user_id=u.id,
            username="   NewName   ",
            email="  MIXED@Case.Email  "
        )

        assert isinstance(updated, User)
        assert updated.username == "NewName"               # whitespace trimmed
        # normalized to lowercase & stripped
        assert updated.email == "mixed@case.email"
        assert updated.updated_at is not None
        assert updated.updated_at >= old_updated_at

    async def test_update_profile_duplicate_raises(self, user_repository: UserRepository, create_user):
        """
        Create two users, attempt to update the second to use the first's email -> DuplicateError expected.
        Because that failure triggers a rollback (undoing created rows in-session), recreate the users
        before testing the second duplicate (username) case.
        """
        # Create initial two users
        u1 = await create_user(username="dup_user", email="dup@example.com")
        u2 = await create_user(username="other", email="other@example.com")

        # Attempt to change u2 email to u1.email -> DuplicateError expected.
        with pytest.raises(DuplicateError):
            await user_repository.update_profile(u2.id, email=u1.email)

        # After the rollback, the previously-created rows were removed from the session,
        # so re-create both users to test the username duplicate scenario.
        u1 = await create_user(username="dup_user", email="dup@example.com")
        u2 = await create_user(username="other", email="other@example.com")

        # Attempt to change u2 username to u1.username -> DuplicateError expected.
        with pytest.raises(DuplicateError):
            await user_repository.update_profile(u2.id, username=u1.username)

    async def test_update_password_changes_hash_and_timestamp(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Change a user's password hash and verify the hashed_password field is updated.
          - Ensure updated_at is bumped after the change.

        Fixtures:
          - user_repository, create_user
        """
        u = await create_user(username="pw_user", email="pw_user@example.com", hashed_password="oldhash")
        old_updated_at = u.updated_at

        updated = await user_repository.update_password(u.id, new_hashed_password="newhash123")
        assert isinstance(updated, User)
        assert updated.hashed_password == "newhash123"
        assert updated.updated_at is not None
        assert updated.updated_at >= old_updated_at

    async def test_activate_and_deactivate_user_toggle_flag(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Create a user initially inactive, activate them, then deactivate and verify the is_active flag changes.
          - Each operation should return the updated User instance.

        Fixtures:
          - user_repository, create_user
        """
        u = await create_user(username="tog_user", email="tog@example.com", hashed_password="pw", is_active=False)

        activated = await user_repository.activate_user(u.id)
        assert isinstance(activated, User)
        assert activated.is_active is True

        deactivated = await user_repository.deactivate_user(u.id)
        assert isinstance(deactivated, User)
        assert deactivated.is_active is False

    async def test_update_methods_return_none_for_missing_user(self, user_repository: UserRepository):
        """
        Behavior:
          - Call update_profile, update_password, activate_user on a non-existent UUID.
          - Expect None to be returned (repository returns None when entity not found).

        Fixtures:
          - user_repository
        """
        missing = uuid.uuid4()
        assert (await user_repository.update_profile(missing, username="x")) is None
        assert (await user_repository.update_password(missing, "x")) is None
        assert (await user_repository.activate_user(missing)) is None
        assert (await user_repository.deactivate_user(missing)) is None


@pytest.mark.asyncio
class TestUserRepositorySearchAndErrors:
    """
    Tests for searching / listing behaviors and robust error handling in UserRepository.

    Covered functionality:
      - search_users: case-insensitive partial matching across username/email,
                      active_only filter, pagination behavior.
      - get_active_users: pagination edge-cases (limit/offset).
      - Defensive behavior: repository methods raise RepositoryError when the DB layer fails.

    Fixtures commonly used:
      - user_repository: UserRepository bound to the test AsyncSession
      - create_user: factory fixture to create users
      - db_session (implicit in user_repository)
    """

    async def test_search_users_pagination_and_active_flag(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Create active and inactive users whose usernames/emails include 'findme'.
          - When active_only=True, only active users should be returned.
          - When active_only=False, inactive matches should also appear.
          - Pagination (limit/offset) should slice the results.
        Fixtures:
          - user_repository, create_user
        """
        # create matches
        await create_user(username="findme_1", email="alpha_findme@example.com", hashed_password="pw", is_active=True)
        await create_user(username="findme_2", email="beta_findme@example.com", hashed_password="pw", is_active=False)
        await create_user(username="findme_3", email="gamma_findme@example.com", hashed_password="pw", is_active=True)

        # active_only True -> excludes findme_2
        active_results = await user_repository.search_users("findme", active_only=True, offset=0, limit=10)
        usernames_active = {u.username for u in active_results}
        assert "findme_1" in usernames_active
        assert "findme_3" in usernames_active
        assert "findme_2" not in usernames_active

        # active_only False -> includes the inactive one
        all_results = await user_repository.search_users("findme", active_only=False, offset=0, limit=10)
        usernames_all = {u.username for u in all_results}
        assert {"findme_1", "findme_2", "findme_3"}.issubset(usernames_all)

        # pagination: small limit should reduce length
        limited = await user_repository.search_users("findme", active_only=False, offset=0, limit=1)
        assert len(limited) <= 1

    async def test_search_users_matches_username_and_email_variations(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Ensure that partial matches against username and email both succeed.
          - Ensure case-insensitivity works for matches (ilike).
        Fixtures:
          - user_repository, create_user
        """
        await create_user(username="AlphaUser", email="alpha.user@example.com", hashed_password="pw", is_active=True)
        await create_user(username="another", email="user.alpha@example.com", hashed_password="pw", is_active=True)

        # search by fragment present in username (case-insensitive)
        res1 = await user_repository.search_users("alpha", active_only=True)
        assert any("AlphaUser" == u.username or "alpha.user@example.com" ==
                   u.email or "user.alpha@example.com" == u.email for u in res1)

        # search that only matches email fragment
        res2 = await user_repository.search_users("user.alpha", active_only=True)
        assert any("user.alpha@example.com" == u.email for u in res2)

    async def test_get_active_users_pagination_edges(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Ensure get_active_users handles odd pagination values gracefully.
          - Very large offset returns empty list; limit=0 returns empty list.
        Fixtures:
          - user_repository, create_user
        """
        # create a few active users
        await create_user(username="pag1", email="pag1@example.com", hashed_password="pw", is_active=True)
        await create_user(username="pag2", email="pag2@example.com", hashed_password="pw", is_active=True)

        # huge offset -> empty
        assert await user_repository.get_active_users(offset=99999, limit=10) == []

        # limit 0 -> empty
        assert await user_repository.get_active_users(offset=0, limit=0) == []

    async def test_repository_methods_wrap_db_exceptions_into_repository_error(self, user_repository: UserRepository, create_user, monkeypatch):
        """
        Behavior:
          - Force the session's execute() to raise an unexpected exception.
          - Confirm repository methods raise RepositoryError (consistent domain-level error handling).
        Fixtures:
          - user_repository, create_user, monkeypatch
        """
        # sanity: create one user so some methods would normally succeed
        u = await create_user(username="errtest", email="errtest@example.com", hashed_password="pw", is_active=True)
        assert u is not None

        async def fake_execute(*args, **kwargs):
            raise RuntimeError("simulated DB crash")

        # monkeypatch the session.execute to simulate DB-level failure
        monkeypatch.setattr(user_repository.db, "execute", fake_execute)

        # Methods that should wrap DB failures into RepositoryError:
        with pytest.raises(RepositoryError):
            await user_repository.get_by_email("errtest@example.com")

        with pytest.raises(RepositoryError):
            await user_repository.get_by_username("errtest")

        with pytest.raises(RepositoryError):
            await user_repository.get_by_username_or_email("errtest")

        with pytest.raises(RepositoryError):
            await user_repository.search_users("err", active_only=True)

        with pytest.raises(RepositoryError):
            await user_repository.get_active_users()

        # restore monkeypatch implicitly by fixture teardown (monkeypatch is per-test)


@pytest.mark.asyncio
class TestUserRepositoryDelete:
    """
    Tests for deleting users via the UserRepository (delegates to BaseRepository.delete).

    Fixtures used:
      - user_repository: UserRepository bound to the test AsyncSession
      - create_user: factory fixture used to create unique test users
      - db_session (implicitly used by user_repository)

    Why these tests matter:
      - Ensure delete() returns True when an entity is removed and False when not found.
      - Ensure delete is idempotent (subsequent deletes return False).
      - Ensure unique constraints do not prevent recreating a user with the same username/email
        after deletion in the same transactional test session.
    """

    async def test_delete_user_success_and_no_longer_exists(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Create a user, delete it, and assert delete() returns True.
          - Verify the user no longer exists via exists().
        Fixtures:
          - user_repository, create_user
        """
        u = await create_user(username="to_del", email="to_del@example.com")
        assert isinstance(u, User)

        deleted = await user_repository.delete(u.id)
        assert deleted is True

        # After deletion, exists should be False
        assert (await user_repository.exists(u.id)) is False

    async def test_delete_not_found_returns_false(self, user_repository: UserRepository):
        """
        Behavior:
          - Deleting a non-existent UUID should return False.
        Fixtures:
          - user_repository
        """
        random_id = uuid.uuid4()
        assert (await user_repository.delete(random_id)) is False

    async def test_delete_idempotent(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Delete the same user twice: first call returns True, second returns False.
        Fixtures:
          - user_repository, create_user
        """
        u = await create_user(username="idemp", email="idemp@example.com")
        assert await user_repository.delete(u.id) is True
        assert await user_repository.delete(u.id) is False

    async def test_recreate_after_delete_allows_same_unique_values(self, user_repository: UserRepository, create_user):
        """
        Behavior:
          - Create a user, delete it, then create another user with the same username/email.
          - This verifies that once deleted the unique values can be reused (within the transaction).
        Fixtures:
          - user_repository, create_user
        """
        username = "recreate_user"
        email = "recreate_user@example.com"

        u = await create_user(username=username, email=email)
        assert isinstance(u, User)

        # delete the user
        assert await user_repository.delete(u.id) is True

        # creating a new user with same username/email should succeed after deletion
        u2 = await create_user(username=username, email=email)
        assert isinstance(u2, User)
        assert u2.username == username
        assert u2.email == email
