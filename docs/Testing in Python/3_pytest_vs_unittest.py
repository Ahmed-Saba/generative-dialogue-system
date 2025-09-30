r"""
# ==========================================================================================================
# `pytest` vs `unittest` - What Real Projects Use
# ==========================================================================================================

## Quick Answer: What Do Real Projects Use?
pytest dominates in real-world projects. Here's the evidence:
    - Django (most popular Python web framework): Uses pytest
    - FastAPI (modern Python web framework): Uses pytest
    - Flask (micro web framework): Uses pytest
    - Requests (HTTP library): Uses pytest
    - Pandas (data analysis): Uses pytest
    - NumPy (scientific computing): Uses pytest
    - SQLAlchemy (database ORM): Uses pytest
Why? pytest is more powerful, easier to use, and has better tooling.



# ==========================================================================================================
# unittest vs pytest: The Same Tests Written Both Ways
# ==========================================================================================================
Let's see the difference by writing identical tests in both frameworks:
"""

# Example: Testing a User Management System
# First, here's our code to test:

class User:
    def __init__(self, username, email, age):
        self.username = username
        self.email = email
        self.age = age
        self.is_active = True
    
    def deactivate(self):
        self.is_active = False
    
    def update_email(self, new_email):
        if '@' not in new_email:
            raise ValueError("Invalid email format")
        self.email = new_email


class UserManager:
    def __init__(self):
        self.users = {}
    
    def add_user(self, username, email, age):
        if username in self.users:
            raise ValueError("Username already exists")
        if age < 13:
            raise ValueError("User must be at least 13 years old")
    
        user = User(username, email, age)
        self.users[username] = user
        return user

    def get_user(self, username):
        return self.users.get(username)

    def get_active_users(self):
        return [user for user in self.users.values() if user.is_active]


## unittest Version (The Old Way)
import unittest
class TestUser(unittest.TestCase):
    """Test the User class using unittest"""
    
    def setUp(self):
        """This runs before EACH test method"""
        self.user = User("john_doe", "john@example.com", 25)
    
    def test_user_creation(self):
        """Test that users are created correctly"""
        self.assertEqual(self.user.username, "john_doe")
        self.assertEqual(self.user.email, "john@example.com")
        self.assertEqual(self.user.age, 25)
        self.assertTrue(self.user.is_active)
    
    def test_user_deactivation(self):
        """Test user deactivation"""
        self.user.deactivate()
        self.assertFalse(self.user.is_active)
    
    def test_update_email_valid(self):
        """Test updating email with valid address"""
        self.user.update_email("newemail@example.com")
        self.assertEqual(self.user.email, "newemail@example.com")
    
    def test_update_email_invalid(self):
        """Test updating email with invalid address"""
        with self.assertRaises(ValueError) as context:
            self.user.update_email("invalid-email")
        self.assertIn("Invalid email format", str(context.exception))


class TestUserManager(unittest.TestCase):
    """Test the UserManager class using unittest"""
    
    def setUp(self):
        """This runs before EACH test method"""
        self.manager = UserManager()
    
    def test_add_user_success(self):
        """Test adding a valid user"""
        user = self.manager.add_user("jane", "jane@example.com", 20)
        self.assertEqual(user.username, "jane")
        self.assertEqual(len(self.manager.users), 1)
    
    def test_add_duplicate_user(self):
        """Test adding duplicate username"""
        self.manager.add_user("john", "john@example.com", 25)
        with self.assertRaises(ValueError) as context:
            self.manager.add_user("john", "different@example.com", 30)
        self.assertIn("Username already exists", str(context.exception))
    
    def test_add_underage_user(self):
        """Test adding user under 13"""
        with self.assertRaises(ValueError) as context:
            self.manager.add_user("kid", "kid@example.com", 10)
        self.assertIn("User must be at least 13", str(context.exception))
    
    def test_get_user_exists(self):
        """Test getting an existing user"""
        self.manager.add_user("alice", "alice@example.com", 28)
        user = self.manager.get_user("alice")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "alice")
    
    def test_get_user_not_exists(self):
        """Test getting a non-existent user"""
        user = self.manager.get_user("nonexistent")
        self.assertIsNone(user)
    
    def test_get_active_users(self):
        """Test getting only active users"""
        user1 = self.manager.add_user("active1", "active1@example.com", 25)
        user2 = self.manager.add_user("active2", "active2@example.com", 30)
        user3 = self.manager.add_user("inactive", "inactive@example.com", 35)
        
        user3.deactivate()  # Deactivate one user
        
        active_users = self.manager.get_active_users()
        self.assertEqual(len(active_users), 2)
        self.assertIn(user1, active_users)
        self.assertIn(user2, active_users)
        self.assertNotIn(user3, active_users)

# Required for unittest
# if __name__ == '__main__':
#     unittest.main()

"""
Output:
```
..........
----------------------------------------------------------------------
Ran 10 tests in 0.001s

OK
```
"""


## pytest Version (The Modern Way)
import pytest

# ---------- Test User Class ----------

@pytest.fixture
def sample_user():
    """Fixture: creates a sample user for testing (like setUp but better)"""
    return User("john_doe", "john@example.com", 25)

def test_user_creation(sample_user):
    """Test that users are created correctly"""
    # Look how clean this is! No self.assertEqual needed
    assert sample_user.username == "john_doe"
    assert sample_user.email == "john@example.com" 
    assert sample_user.age == 25
    assert sample_user.is_active == True

def test_user_deactivation(sample_user):
    """Test user deactivation"""
    sample_user.deactivate()
    assert sample_user.is_active == False

def test_update_email_valid(sample_user):
    """Test updating email with valid address"""
    sample_user.update_email("newemail@example.com")
    assert sample_user.email == "newemail@example.com"

def test_update_email_invalid(sample_user):
    """Test updating email with invalid address"""
    # pytest's exception testing is cleaner
    with pytest.raises(ValueError, match="Invalid email format"):
        sample_user.update_email("invalid-email")

# ---------- Test UserManager Class ----------

@pytest.fixture
def user_manager():
    """Fixture: creates a fresh UserManager for each test"""
    return UserManager()

def test_add_user_success(user_manager):
    """Test adding a valid user"""
    user = user_manager.add_user("jane", "jane@example.com", 20)
    assert user.username == "jane"
    assert len(user_manager.users) == 1

def test_add_duplicate_user(user_manager):
    """Test adding duplicate username"""
    user_manager.add_user("john", "john@example.com", 25)
    with pytest.raises(ValueError, match="Username already exists"):
        user_manager.add_user("john", "different@example.com", 30)

def test_add_underage_user(user_manager):
    """Test adding user under 13"""
    with pytest.raises(ValueError, match="User must be at least 13"):
        user_manager.add_user("kid", "kid@example.com", 10)

def test_get_user_exists(user_manager):
    """Test getting an existing user"""
    user_manager.add_user("alice", "alice@example.com", 28)
    user = user_manager.get_user("alice")
    assert user is not None
    assert user.username == "alice"

def test_get_user_not_exists(user_manager):
    """Test getting a non-existent user"""
    user = user_manager.get_user("nonexistent")
    assert user is None

def test_get_active_users(user_manager):
    """Test getting only active users"""
    user1 = user_manager.add_user("active1", "active1@example.com", 25)
    user2 = user_manager.add_user("active2", "active2@example.com", 30)
    user3 = user_manager.add_user("inactive", "inactive@example.com", 35)
    
    user3.deactivate()  # Deactivate one user
    
    active_users = user_manager.get_active_users()
    assert len(active_users) == 2
    assert user1 in active_users
    assert user2 in active_users
    assert user3 not in active_users

# ---------- Advanced pytest Features ----------

@pytest.mark.parametrize("username,email,age,should_pass", [
    ("valid_user", "valid@email.com", 20, True),          # Valid case
    ("", "valid@email.com", 20, False),                   # Empty username
    ("user", "invalid-email", 20, False),                 # Invalid email
    ("user", "valid@email.com", 5, False),                # Too young
    ("valid_user", "valid@email.com", 13, True),          # Minimum age
])
def test_add_user_various_inputs(user_manager, username, email, age, should_pass):
    """Test multiple scenarios with one test function"""
    if should_pass:
        user = user_manager.add_user(username, email, age)
        assert user.username == username
    else:
        with pytest.raises(ValueError):
            user_manager.add_user(username, email, age)

# No if __name__ == '__main__' needed!
# run by: pytest "Testing in Python/3_pytest_vs_unittest.py"


"""
Key Differences Explained

1. Syntax Simplicity

unittest:
```
self.assertEqual(actual, expected)
self.assertTrue(condition)
self.assertRaises(ValueError, func, args)
```

pytest:
```
pythonassert actual == expected
assert condition
with pytest.raises(ValueError):
    func(args)
```

Winner: pytest - Natural Python syntax, easier to read and write.

2. Test Discovery

unittest:
```
# You need to specify the module
python -m unittest test_module.py

# Or use discovery (finds test_*.py files)
python -m unittest discover
```

pytest:
```
# Just run pytest - it finds everything automatically
pytest

# Run specific file
pytest test_file.py

# Run tests matching pattern
pytest -k "test_user"
```

3. Fixtures vs setUp/tearDown

unittest:
```
class TestSomething(unittest.TestCase):
    def setUp(self):
        # Runs before EVERY test method in this class
        self.data = create_test_data()
    
    def tearDown(self):
        # Runs after EVERY test method in this class
        cleanup()
```


pytest:
```
@pytest.fixture
def test_data():
    # More flexible - can be used by any test that needs it
    data = create_test_data()
    yield data  # This runs before the test
    cleanup()   # This runs after the test (if needed)

def test_something(test_data):  # Just add it as parameter
    assert test_data.is_valid()
```
Winner: pytest - More flexible, reusable, and can be shared across files.


4. Parameterized Tests

unittest:
```
# You have to write separate test methods or use loops
def test_add_various_numbers(self):
    test_cases = [(2, 3, 5), (10, 5, 15), (-1, 1, 0)]
    for a, b, expected in test_cases:
        with self.subTest(a=a, b=b):
            self.assertEqual(add(a, b), expected)
```

pytest:
```
@pytest.mark.parametrize("a,b,expected", [
    (2, 3, 5),
    (10, 5, 15),
    (-1, 1, 0),
])
def test_add_various_numbers(a, b, expected):
    assert add(a, b) == expected
```

Winner: pytest - Much cleaner, each parameter combination shows as separate test.

"""
