r"""
# ==========================================================================================================
# Pytest Fixtures
# ==========================================================================================================
# Fixtures are a powerful way to set up test data, database connections, or any resources your tests need. 
# They promote code reuse and clean test organization.
"""

# ---------------------------------------------------------------------------
# Basic Fixtures
# ---------------------------------------------------------------------------
# tests/conftest.py
"""
conftest.py is a special file where you define fixtures that can be used
across multiple test files in the same directory and subdirectories.
"""
import pytest
from typing import Any

@pytest.fixture
def sample_user() -> dict[str, Any]:
    """
    A fixture that provides sample user data.
    This can be used by any test function that includes 'sample_user' as a parameter.
    """
    return {
        "id": 1,
        "email": "test@example.com",
        "username": "testuser",
        "is_active": True
    }

@pytest.fixture
def sample_users() -> list[dict[str, Any]]:
    """
    A fixture that provides multiple sample users.
    Useful for testing operations that work with multiple records.
    """
    return [
        {"id": 1, "email": "user1@example.com", "username": "user1", "is_active": True},
        {"id": 2, "email": "user2@example.com", "username": "user2", "is_active": True},
        {"id": 3, "email": "user3@example.com", "username": "user3", "is_active": False},
    ]

@pytest.fixture
def mock_database():
    """
    A fixture that provides a mock database.
    This is a simple example - we'll see more complex database fixtures later.
    """
    # Setup: Create mock database
    database = {}
    
    # Yield the database to the test
    yield database
    
    # Teardown: Clean up after test (optional)
    database.clear()


## Using Fixtures in Tests
# tests/test_with_fixtures.py
import pytest

def test_user_data_access(sample_user):
    """
    Test that demonstrates how to use a fixture.
    The 'sample_user' parameter will automatically receive the data
    from the `sample_user` fixture defined in `conftest.py`
    """
    # The fixture provides the user data
    assert sample_user["email"] == "test@example.com"
    assert sample_user["username"] == "testuser"
    assert sample_user["is_active"] is True

def test_multiple_users(sample_users):
    """Test working with multiple user records."""
    # Verify we have the expected number of users
    assert len(sample_users) == 3
    
    # Test filtering active users
    active_users = [user for user in sample_users if user["is_active"]]
    assert len(active_users) == 2
    
    # Test finding specific user
    user1 = next(user for user in sample_users if user["username"] == "user1")
    assert user1["email"] == "user1@example.com"

def test_mock_database_operations(mock_database):
    """Test using a mock database fixture."""
    # Initially empty
    assert len(mock_database) == 0
    
    # Add some data
    mock_database["users"] = ["user1", "user2"]
    assert len(mock_database) == 1
    assert "users" in mock_database
    
    # The database will be cleaned up automatically after this test


# ---------------------------------------------------------------------------
# Fixture Scopes
# ---------------------------------------------------------------------------
# Fixtures can have different scopes that control when they're created and destroyed:

# tests/conftest.py (additional fixtures)
@pytest.fixture(scope="function")  # Default scope - created for each test function
def function_scoped_data():
    """This fixture is created fresh for each test function."""
    print("Setting up function-scoped data")
    return {"data": "fresh_for_each_test"}

@pytest.fixture(scope="class")  # Created once per test class
def class_scoped_data():
    """This fixture is created once per test class."""
    print("Setting up class-scoped data")
    return {"expensive_setup": "shared_across_class"}

@pytest.fixture(scope="module")  # Created once per test module (.py file)
def module_scoped_data():
    """This fixture is created once per test module."""
    print("Setting up module-scoped data")
    return {"very_expensive_setup": "shared_across_module"}

@pytest.fixture(scope="session")  # Created once per test session
def session_scoped_data():
    """This fixture is created once per entire test session."""
    print("Setting up session-scoped data")
    return {"extremely_expensive_setup": "shared_across_all_tests"}

# The scope tells pytest:
#   - "How long should this fixture live?"
#   - "How often should it be created and destroyed?"

# There are 4 main scopes you can use:
# | Scope      | Lives for...                           | Created...                  |
# | ---------- | -------------------------------------- | --------------------------- |
# | `function` | One **test function**                  | For **every** test function |
# | `class`    | One **test class** (group of tests)    | Once per test class         |
# | `module`   | One **test file** (e.g. `test_xyz.py`) | Once per test file          |
# | `session`  | The **entire test session**            | Once per test run           |

# Think of it like this:
#   - function: Fresh for every test (default, most commonly used)
#   - class: Shared between all tests inside a single test class
#   - module: Shared between all tests in one .py file
#   - session: Shared across all tests (good for expensive setups)

# Real-Life Analogy: Imagine you're baking cookies:
#   - function scope: You bake a new batch for each person (every test).
#   - class scope: You bake one batch and share it with a small group (one class).
#   - module scope: One batch per kitchen (test file).
#   - session scope: One batch for the whole event (all tests).

# Code Example Explained
# ```
# @pytest.fixture(scope="function")  # Created every time a test calls it
# def function_scoped_data():
#     print("Setting up function-scoped data")
#     return {"data": "fresh_for_each_test"}
# ```
# If you have 3 test functions using this fixture, it will print `Setting up...` 3 times (once for each test).
# 
# ```
# @pytest.fixture(scope="module")  # Created once per test file
# def module_scoped_data():
#     print("Setting up module-scoped data")
#     return {"very_expensive_setup": "shared_across_module"}
# ```
# Even if 10 test functions in the same file use this, it's created once, then reused.


## Let’s go through each scope with when and why to use it:

# 1. function scope (default)
# - What it means: The fixture is created fresh for every single test function.
# - When to use:
#     - Most common and safest option.
#     - When each test needs clean, isolated data.
#     - For simple setup/teardown that isn't expensive.
# 
# - Use when:
#     - You want to avoid shared state between tests.
#     - Each test should start from a clean slate.

# 2. class scope
# - What it means: The fixture is created once per test class.
# - When to use:
#   - When a group of tests inside a class can share the same setup.
#   - When setup is a little expensive but not global.
# 
# - Use when:
#   - You have tests grouped in a class.
#   - They use shared data or setup (e.g. mock user session).
#   - The setup doesn't need to reset for each test.

# 3. module scope
#   - What it means: The fixture is created once per test file (module).
#   - When to use:
#   - For expensive setup that is safe to reuse across all tests in the same file.
#   - When tests don't interfere with each other.
# 
# - Use when:
#   - Setup is slow (e.g. loading a test database).
#   - All tests in the file can safely share it.
#   - You want to reduce redundant setup calls.

# 4. session scope
# - What it means: The fixture is created once per entire test session.
# - When to use:
#   - For very expensive setup that should only happen once per run.
#   - Usually used for external systems: DBs, APIs, servers.
# 
# - Use when:
#   - You're starting a Docker container, server, or seeded test DB.
#   - All tests across files need this resource.
#   - You're OK with shared state (use carefully!).

# 🚫 Be Careful With Larger Scopes
# Larger scopes (class/module/session) can speed up tests, but...
#   - They can also cause test flakiness if tests modify shared data.
#   - Avoid shared state unless it's read-only or reset between tests.

# Summary Table
# | Scope      | Created          | Destroyed       | When to use                                    |
# | ---------- | ---------------- | --------------- | ---------------------------------------------- |
# | `function` | Before each test | After each test | Default. Clean, isolated setup for every test. |
# | `class`    | Once per class   | After class     | Shared setup for grouped tests (in a class).   |
# | `module`   | Once per file    | After file      | Shared setup for all tests in a file.          |
# | `session`  | Once per run     | End of run      | Global setup. Expensive or external systems.   |


# ---------------------------------------------------------------------------
# Difference Between `@pytest.mark.parametrize` and `@pytest.fixture`
# ---------------------------------------------------------------------------

# | Feature          | `@pytest.mark.parametrize`                               | `@pytest.fixture`                                        |
# | ---------------- | -------------------------------------------------------- | -------------------------------------------------------- |
# | **Purpose**      | Run the same test with different inputs                  | Provide reusable setup code for tests                    |
# | **Focus**        | Testing **function behavior** with various input/output  | Setting up **test environment or data**                  |
# | **How it works** | Injects **test parameters** into a test function         | Injects **predefined setup objects** into test functions |
# | **When to use**  | When testing multiple cases of input/output combinations | When you need reusable logic like DB setup, config, etc. |


## Can You Use Them Together?
# ✅ Yes! You can absolutely use fixtures and parametrization together.
# This is very common and useful when:
#   - You want to test the same logic using different inputs,
#   - While also using shared setup (like a fixture).

## Simple Example: Using Both
# Let's say you have a function to format a username, and you want to test it using:
#   - A fixture that gives you a base prefix (like an app config),
#   - And parametrized inputs for different user names.

# your_app/utils.py
def format_username(prefix, name):
    return f"{prefix}_{name.lower()}"

# tests/test_utils.py
import pytest
# from your_app.utils import format_username

# Fixture provides the prefix used in formatting
@pytest.fixture
def username_prefix():
    return "user"

# Parametrize different names and expected results
@pytest.mark.parametrize("name, expected", [
    ("Alice", "user_alice"),
    ("BOB", "user_bob"),
    ("Charlie", "user_charlie"),
])
def test_format_username(username_prefix, name, expected):
    result = format_username(username_prefix, name)
    assert result == expected

# What’s Happening Here:
#   - `@pytest.fixture`: `username_prefix` returns "user" → this is used as a setup value.
#   - `@pytest.mark.parametrize`: gives the test function different names and expected outputs.
#   - Pytest automatically injects both: the fixture and the parameter values.
# 
# Pro Tip: You can combine multiple fixtures and multiple parameter values — pytest will handle the combinations for you.

