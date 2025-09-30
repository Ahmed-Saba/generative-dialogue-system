r"""
# ==========================================================================================================
# What is Pytest?
# ==========================================================================================================
Pytest is a powerful testing framework for Python that makes it easy to write simple and scalable test cases. 
It's particularly well-suited for testing web applications like those built with FastAPI.

Key benefits:
    - Simple syntax (just use `assert` statements)
    - Automatic test discovery
    - Powerful fixtures for setup/teardown
    - Rich ecosystem of plugins
    - Excellent error reporting

# ==========================================================================================================
# Test Discovery
# ==========================================================================================================
Pytest automatically finds tests by looking for:
    - Files named `test_*.py` or `*_test.py`
    - Functions named `test_*()`
    - Classes named `Test*` with methods named `test_*()`

```
# Run all tests
pytest

# Run specific file
pytest tests/test_users.py

# Run specific test
pytest tests/test_users.py::test_create_user

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=app
```

# ==========================================================================================================
# Simple Test Examples
# ==========================================================================================================
Let's start with basic examples to understand pytest fundamentals.
"""

# ---------------------------------------------------------------------------
## Example 1: Basic Function Testing
# ---------------------------------------------------------------------------

# app/utils.py
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b

def validate_email(email: str) -> bool:
    """Simple email validation."""
    return "@" in email and "." in email

def calculate_discount(price: float, discount_percent: int) -> float:
    """Calculate discounted price."""
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("Discount percent must be between 0 and 100")
    return price * (1 - discount_percent / 100)


# tests/test_utils.py
import pytest
# from app.utils import add_numbers, validate_email, calculate_discount

def test_add_numbers():
    """Test the add_numbers function with basic cases."""
    # Test positive numbers
    assert add_numbers(2, 3) == 5
    
    # Test negative numbers
    assert add_numbers(-1, 1) == 0
    
    # Test zero
    assert add_numbers(0, 5) == 5

def test_validate_email():
    """Test email validation function."""
    # Test valid emails
    assert validate_email("user@example.com") == True
    assert validate_email("test.email@domain.org") == True
    
    # Test invalid emails
    assert validate_email("notanemail") == False
    assert validate_email("missing@domain") == False

def test_calculate_discount():
    """Test discount calculation with various scenarios."""
    # Test normal discount
    assert calculate_discount(100.0, 10) == 90.0
    assert calculate_discount(50.0, 20) == 40.0
    
    # Test no discount
    assert calculate_discount(100.0, 0) == 100.0
    
    # Test 100% discount
    assert calculate_discount(100.0, 100) == 0.0

def test_calculate_discount_invalid_input():
    """Test that invalid discount percentages raise ValueError."""
    # Test negative discount - should raise ValueError
    with pytest.raises(ValueError, match="Discount percent must be between 0 and 100"):
        calculate_discount(100.0, -5)
    
    # Test discount over 100% - should raise ValueError
    with pytest.raises(ValueError, match="Discount percent must be between 0 and 100"):
        calculate_discount(100.0, 150)


# ---------------------------------------------------------------------------
# Example 2: Parametrized Tests
# ---------------------------------------------------------------------------
# Parametrized tests allow you to run the same test with different inputs:

# tests/test_utils_parametrized.py
import pytest
# from app.utils import add_numbers, validate_email

# Test the same function with multiple input combinations
@pytest.mark.parametrize("a, b, expected", [
    (1, 2, 3),           # Basic positive numbers
    (-1, 1, 0),          # Negative and positive
    (0, 0, 0),           # Both zero
    (-5, -3, -8),        # Both negative
    (100, -50, 50),      # Large numbers
])

def test_add_numbers_parametrized(a, b, expected):
    """Test add_numbers with multiple parameter combinations."""
    assert add_numbers(a, b) == expected

# Test email validation with multiple examples
@pytest.mark.parametrize("email, expected", [
    ("user@example.com", True),
    ("test.email@domain.org", True),
    ("simple@test.co", True),
    ("notanemail", False),
    ("missing@domain", False),
    ("user@", False),
    ("", False),
])

def test_validate_email_parametrized(email, expected):
    """Test email validation with multiple examples."""
    assert validate_email(email) == expected


# The `@pytest.mark.parametrize` decorator in pytest is used to run the same test function multiple times 
# with different input values. This is extremely useful when you want to test a function against a variety 
# of inputs without writing separate test functions for each case.

# Example 1: Testing add_numbers(a, b)
# ```
# @pytest.mark.parametrize("a, b, expected", [
#     (1, 2, 3),
#     (-1, 1, 0),
#     (0, 0, 0),
#     (-5, -3, -8),
#     (100, -50, 50),
# ])
# def test_add_numbers_parametrized(a, b, expected):
#     assert add_numbers(a, b) == expected
# ```
# 
# This test function is automatically run 5 times, once for each (a, b, expected) combination. For example:
#   - add_numbers(1, 2) should return 3
#   - add_numbers(-1, 1) should return 0
#   - and so on.
# Instead of writing 5 different test functions, pytest.mark.parametrize lets you handle all of them in a single function.

# NOTE: The function that comes after `@pytest.mark.parametrize` is the test function that calls the function being tested.
# In our example, 
# - `add_numbers()` is the function being tested (this lives in your application code).
# - `test_add_numbers_parametrized()` is the test function, and it is decorated with `@pytest.mark.parametrize`.
# - So `@pytest.mark.parametrize` tells pytest: “Run this test function multiple times with different inputs.” 

# Summary:
# `@pytest.mark.parametrize` is a powerful tool for:
#   - Running the same test logic with different data.
#   - Improving test coverage.
#   - Keeping your test code clean and DRY (Don't Repeat Yourself).
