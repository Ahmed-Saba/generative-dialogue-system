r"""
# ==========================================================================================================
# Faker
# ==========================================================================================================
There is a more professional, scalable, and maintainable way to generate fake data for testing 
than hardcoding it manually.

The industry-standard approach is to use a library like `Faker` — often combined with factory functions 
or factory libraries like `factory_boy`.

Why use a data factory or Faker?
❌ Manually hardcoding test data is:
    - Repetitive
    - Not scalable
    - Hard to randomize or expand

✅ Using Faker or a factory pattern is:
    - Clean and reusable
    - Easier to customize per test
    - Better for simulating real-world data
    - Often used in real-world applications
"""

# ---------------------------------------------------------------------------
# Hardcoded Sample Data
# ---------------------------------------------------------------------------
import pytest
from typing import Any
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

# Pros:
#   - Predictable and consistent — The test data never changes, which makes debugging easier.
#   - Good for deterministic unit tests — You can assert exact values (user['email'] == 'user1@example.com').
#   - No dependencies — Doesn’t rely on external libraries like faker.

# Cons:
#   - Less realistic — Doesn't mimic the variability of real-world data.
#   - Limited scale — Tedious if you want to scale to more users or vary the data.

# Use When:
#   - You need stable, repeatable test results.
#   - You're testing logic that depends on exact values.
#   - Simplicity and speed are priorities.


# ---------------------------------------------------------------------------
# Basic Example Using faker Only
# ---------------------------------------------------------------------------

# conftest.py or test_utils.py
import pytest
from faker import Faker

fake = Faker()

@pytest.fixture
def sample_users():
    """Generate a list of fake users using Faker."""
    return [
        {
            "id": i,
            "email": fake.email(),
            "username": fake.user_name(),
            "is_active": fake.boolean(chance_of_getting_true=75)
        }
        for i in range(1, 4)
    ]

# Pros:
#   - Realistic and dynamic — Better simulates real-world data formats and edge cases.
#   - Scalable — Easier to generate large or varied datasets.
#   - Useful for fuzz testing — Helps surface bugs that only occur with unexpected inputs.

# Cons:
#   - Less predictable — Makes test failures harder to debug unless you control randomness.
#   - Not deterministic — Test outcomes can vary unless you fix the Faker seed.
#   - Adds dependency — Requires the faker library.

# Use When:
#   - You want to simulate real-world input.
#   - You're testing for data validation, input handling, or edge cases.
#   - Determinism isn't critical, or you set a fixed seed (`fake.seed_instance(123)`).


# Recommendation
# | Use Case                                                      | Recommended Fixture                             |
# | ------------------------------------------------------------- | ----------------------------------------------- |
# | **Simple unit tests** where exact values matter               |  Hardcoded                                      |
# | **Integration tests** or tests involving **data variability** |  Faker                                          |
# | Wanting the best of both worlds                               | Use Faker **with a fixed seed** for consistency |

# Best Practice (Optional Hybrid)
# If you go with Faker, consider setting a seed for repeatability:
@pytest.fixture
def sample_users():
    """Generate a list of fake users using Faker with a fixed seed."""
    fake = Faker()
    fake.seed_instance(42)
    return [
        {
            "id": i,
            "email": fake.email(),
            "username": fake.user_name(),
            "is_active": fake.boolean(chance_of_getting_true=75)
        }
        for i in range(1, 4)
    ]


# ---------------------------------------------------------------------------
# Going One Step Further: Custom Factory Function
# ---------------------------------------------------------------------------
def make_fake_user(id: int = 1, is_active: bool = True) -> dict:
    return {
        "id": id,
        "email": fake.email(),
        "username": fake.user_name(),
        "is_active": is_active,
    }

@pytest.fixture
def sample_users():
    fake.seed_instance(42)  # Ensures deterministic output
    return [
        make_fake_user(id=1, is_active=True),
        make_fake_user(id=2, is_active=True),
        make_fake_user(id=3, is_active=False),
    ]
    
# This makes your code more flexible and readable — especially if user creation logic gets more complex.
# | Feature               | Description                                                             |
# | --------------------- | ----------------------------------------------------------------------- |
# | ✔️ **Realistic data** | Uses `Faker`, so the generated emails and usernames resemble real ones. |
# | ✔️ **Deterministic**  | With a fixed seed, the generated data is consistent across test runs.   |
# | ✔️ **Customizable**   | You can easily override fields (like `id` or `is_active`) as needed.    |
# | ✔️ **Reusable**       | The factory can be reused in other tests or fixtures.                   |
# | ✔️ **Readable**       | Test data is clearly defined and understandable at a glance.            |


# ---------------------------------------------------------------------------
# Use factory_boy with ORM models
# ---------------------------------------------------------------------------
# If you're testing SQLAlchemy models, `factory_boy` is commonly used.
# It’s essentially a test data factory tool, often used in Django, SQLAlchemy, or other ORM-based projects, 
# but it's not limited to ORMs — you can use it with plain Python objects too.

# Why Use factory_boy?
# In unit and integration testing, you often need to create a lot of test data. Writing that manually becomes 
# tedious, repetitive, and hard to maintain.
# 
# `factory_boy` helps you:
#   - Generate realistic test data (via Faker integration)
#   - Avoid boilerplate by reusing factories
#   - Easily override just the fields you need
#   - Define complex relationships between models (e.g., users and profiles)

# Example
import factory
from faker import Faker

fake = Faker()

# Let's say you have a simple User model class
class User:
    def __init__(self, id, email, username, is_active):
        self.id = id
        self.email = email
        self.username = username
        self.is_active = is_active

# Factory definition
class UserFactory(factory.Factory):
    class Meta:
        model = User

    id = factory.Sequence(lambda n: n + 1)
    email = factory.LazyAttribute(lambda _: fake.email())
    username = factory.LazyAttribute(lambda _: fake.user_name())
    is_active = factory.Faker("boolean", chance_of_getting_true=75)

# Usage in tests
user = UserFactory()
inactive_user = UserFactory(is_active=False)
users = UserFactory.create_batch(3)

# How to use with pytest
@pytest.fixture
def sample_users():
    return UserFactory.build_batch(3)


# | Method              | `build_batch()`                    | `create_batch()`                        |
# | ------------------- | ---------------------------------  | --------------------------------------- |
# | **Creates...**      | Python objects **in memory only**  | Fully saved objects in the **database** |
# | **For use with...** | Unit tests (no DB access needed)   | Integration tests (need DB interaction) |
# | **Database write?** | ❌ No (objects are not persisted)  | ✅ Yes (objects are saved to DB)       |
# | **Performance**     | ⚡ Faster (no DB hit)              | 🐢 Slower (hits the DB)                |

# When to use which:
# ✅ build_batch():
#   - You’re testing pure Python logic
#   - You don’t need the data saved to the database
#   - Faster and cleaner
# 
# ✅ create_batch():
#   - You’re testing DB-related behavior (queries, views, APIs)
#   - You want data available in the test DB
# 
# Examples:
# ```
# users = UserFactory.build_batch(3)     # → 3 unsaved User objects (like user.id is None)
# users = UserFactory.create_batch(3)    # → 3 User objects saved to DB (user.id is set)
# ```


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------
# TL;DR:
#   - `Faker` and `factory_boy` generate realistic and valid data by default.
#   - They do not automatically generate edge cases, invalid, or malicious inputs.
#   - But you can configure them to do so manually.

# What Each Tool Does by Default:
# | Tool              | Default Behavior                         | Edge/Invalid Case Support               |
# | ----------------- | ---------------------------------------- | --------------------------------------  |
# | **`Faker`**       | Generates **valid**, realistic data      | ❌ Not automatic, but you can customize |
# | **`factory_boy`** | Builds objects with **valid Faker data** | ❌ Not automatic, but allows overrides  |

# Examples of What They Generate by Default:
# ```
# fake.email()         # e.g. 'john.doe@example.com'
# fake.name()          # e.g. 'Alice Smith'
# fake.user_name()     # e.g. 'coolguy99'
# ```
# All clean and valid.


## How to Generate Edge Cases or Invalid Data
# You must manually define overrides or custom fields. Here's how:

# 1. Invalid Email Example (with Faker)
fake_email = "not-an-email"

# 2. Invalid Email Example (with factory_boy)
class UserFactory(factory.Factory):
    class Meta:
        model = User

    email = factory.Faker("email")
    username = factory.Faker("user_name")
    is_active = True

# Override with invalid data
bad_user = UserFactory(email="invalid-email", username="!@#$", is_active="maybe")

# 3. You can even make a special “bad factory”:
class InvalidUserFactory(UserFactory):
    email = "not-an-email"
    username = ""
    is_active = "not-a-boolean"


## Tip: Build Your Own Edge-Case Data Generators
# 
# You can write a utility like:
# ```
# def edge_case_emails():
#     return [
#         "", "plainaddress", "missing@domain", "user@.com", "user@domain..com"
#     ]
# ```
# 
# And test using:
# ```
# @pytest.mark.parametrize("email", edge_case_emails())
# def test_invalid_emails(email):
#     with pytest.raises(ValidationError):
#         validate_email(email)
# ```


# Summary
# | Task                          | Tool                        | Support               |
# | ----------------------------- | --------------------------- | --------------------  |
# | Generate valid fake data      | Faker + factory\_boy        | ✅ Yes                |
# | Generate invalid/edge data    | Manual configuration needed | ⚠️ Yes (with effort)  |
# | Automated fuzzing or mutation | ❌ Not built-in             | ❌                    |


# If you're looking to automatically generate edge cases or malformed inputs, 
# look into property-based testing with tools like:
#   - hypothesis (https://hypothesis.readthedocs.io/en/latest/)
#       - excellent for generating a wide range of inputs including edge cases automatically.

