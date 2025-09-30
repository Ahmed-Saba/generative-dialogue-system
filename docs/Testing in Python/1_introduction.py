r"""
# ==========================================================================================================
# Testing in Python
# ==========================================================================================================

## What Are Tests?
Tests are pieces of code that automatically check if your main code works correctly. Think of them as 
quality control - they verify that your functions and classes behave as expected under different conditions.

## Why write tests?
- Catch bugs early before users find them
- Make sure your code still works after making changes
- Document how your code is supposed to work
- Give you confidence when refactoring or adding features

# ==========================================================================================================
# A Simple Project Without Tests
# ==========================================================================================================
Let's start with a basic calculator module to understand the problem tests solve:
"""
# calculator.py - A simple calculator without tests

def add(a, b):
    """Add two numbers together"""
    return a + b

def subtract(a, b):
    """Subtract b from a"""
    return a - b

def multiply(a, b):
    """Multiply two numbers"""
    return a * b

def divide(a, b):
    """Divide a by b"""
    return a / b

def calculate_discount(price, discount_percent):
    """Calculate price after applying discount percentage"""
    
    if discount_percent < 0 or discount_percent > 100:
        return price  # Invalid discount, return original price
    
    discount_amount = price * (discount_percent / 100)
    return price - discount_amount


# Manual testing (the old way)
# if __name__ == "__main__":
#     print("Manual testing:")
#     print(f"2 + 3 = {add(2, 3)}")  # Expected: 5
#     print(f"10 - 4 = {subtract(10, 4)}")  # Expected: 6
#     print(f"5 * 6 = {multiply(5, 6)}")  # Expected: 30
#     print(f"15 / 3 = {divide(15, 3)}")  # Expected: 5.0
#     print(f"$100 with 20% discount = ${calculate_discount(100, 20)}")  # Expected: 80.0

### Problems with manual testing:
# 1. You have to run the code manually every time
# 2. You might forget to test some functions
# 3. When you change code, you have to re-test everything manually
# 4. It's hard to test edge cases systematically
# 5. No easy way to know if all tests pass at a glance


r"""
# ==========================================================================================================
# The Same Project WITH Tests
# ==========================================================================================================
Now let's see how automated tests solve these problems:
"""
# calculator.py - Same calculator, but designed with testing in mind

def add(a, b):
    """Add two numbers together"""
    return a + b

def subtract(a, b):
    """Subtract b from a"""
    return a - b

def multiply(a, b):
    """Multiply two numbers"""
    return a * b

def divide(a, b):
    """Divide a by b"""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

def calculate_discount(price, discount_percent):
    """Calculate price after applying discount percentage"""
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("Discount must be between 0 and 100")
    
    discount_amount = price * (discount_percent / 100)
    return price - discount_amount


# Import the testing framework - 'unittest' comes built-in with Python
import unittest
class TestCalculator(unittest.TestCase):
    """
    Test class for calculator functions.
    
    unittest.TestCase provides methods for testing like assertEqual, assertTrue, etc.
    Each method that starts with 'test_' will be automatically run as a test.
    """
    
    def test_add_positive_numbers(self):
        """Test adding two positive numbers"""
        # self.assertEqual(actual_result, expected_result)
        # If these don't match, the test fails
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(10, 15), 25)
    
    def test_add_negative_numbers(self):
        """Test adding negative numbers"""
        self.assertEqual(add(-5, -3), -8)
        self.assertEqual(add(-10, 5), -5)
        self.assertEqual(add(10, -3), 7)
    
    def test_add_zero(self):
        """Test adding zero (edge case)"""
        self.assertEqual(add(5, 0), 5)
        self.assertEqual(add(0, 5), 5)
        self.assertEqual(add(0, 0), 0)
    
    def test_subtract_basic(self):
        """Test basic subtraction"""
        self.assertEqual(subtract(10, 4), 6)
        self.assertEqual(subtract(0, 5), -5)
        self.assertEqual(subtract(5, 5), 0)
    
    def test_multiply_basic(self):
        """Test basic multiplication"""
        self.assertEqual(multiply(5, 6), 30)
        self.assertEqual(multiply(-3, 4), -12)
        self.assertEqual(multiply(0, 100), 0)
    
    def test_divide_basic(self):
        """Test basic division"""
        self.assertEqual(divide(15, 3), 5.0)
        self.assertEqual(divide(10, 4), 2.5)
    
    def test_divide_by_zero(self):
        """Test that dividing by zero raises an error"""
        # self.assertRaises(ExpectedError, function, arguments)
        # This test passes if the specified error IS raised
        self.assertRaises(ValueError, divide, 10, 0)
    
    def test_calculate_discount_valid(self):
        """Test discount calculation with valid percentages"""
        # Test 20% discount on $100 should give $80
        self.assertEqual(calculate_discount(100, 20), 80.0)
        
        # Test 50% discount on $200 should give $100
        self.assertEqual(calculate_discount(200, 50), 100.0)
        
        # Test 0% discount should return original price
        self.assertEqual(calculate_discount(100, 0), 100.0)
    
    def test_calculate_discount_invalid(self):
        """Test that invalid discount percentages raise errors"""
        # Negative discount should raise error
        self.assertRaises(ValueError, calculate_discount, 100, -10)
        
        # Discount over 100% should raise error
        self.assertRaises(ValueError, calculate_discount, 100, 150)


# This allows us to run the tests directly: python test_calculator.py
# if __name__ == "__main__":
#     unittest.main()


"""
## Execution Output:
```
.........
----------------------------------------------------------------------
Ran 9 tests in 0.002s

OK
``` 

## Output Explained:
✅ .........
- Each . represents one successful test case.
- So ......... = 9 tests ran, all passed.

✅ Ran 9 tests in 0.002s
- Exactly 9 test methods that start with test_ were discovered and executed.
- The whole test suite finished in 0.002 seconds.

✅ OK
- All tests passed — no errors, no failures, no skipped tests.
- This is exactly what you want to see


## What would failures look like?

If a test failed, you'd see something like this:

```
.F.......
======================================================================
FAIL: test_add_negative_numbers (__main__.TestCalculator.test_add_negative_numbers)
Test adding negative numbers
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
AssertionError: -7 != -8
----------------------------------------------------------------------
Ran 9 tests in 0.002s

FAILED (failures=1)
```

The F in place of a dot would indicate a failed test, and you'd get detailed output about what failed and why.
"""

### Benefits of automated tests:
# 1. Fast: Run all tests with one command
# 2. Reliable: Tests run exactly the same way every time
# 3. Comprehensive: Easy to test many scenarios and edge cases
# 4. Confidence: Know immediately if changes break existing functionality
# 5. Documentation: Tests show how your code is meant to be used



r"""
# ==========================================================================================================
# Automatic Test Discovery
# ==========================================================================================================
Functions inside a `unittest.TestCase` class must start with `test_` in order to be automatically discovered 
and run as tests.

## Why `test_` is required
- The unittest framework uses naming conventions to detect which methods are tests. It:
    - Scans for any method in a subclass of `unittest.TestCase`
    - Runs only those whose names start with `test_`
- If you name your method anything else (like `check_addition()` or `verify_something()`), it will not be run automatically.

## 🎯 “Run automatically” means:
When you execute your test file using Python (e.g., via `python test_calculator.py` or similar), 
the unittest framework will automatically discover and execute any method that:
    - Is inside a class that inherits from `unittest.TestCase`
    - Has a name that starts with `test_`
You do not need to manually call those methods.


## Example — Automatic vs Manual

✅ Automatic test discovery
```
import unittest

class TestMath(unittest.TestCase):
    def test_add(self):
        self.assertEqual(1 + 2, 3)

if __name__ == '__main__':
    unittest.main()
```

When you run this file (`python test_file.py`), the output will be:
```
.
----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
```
Even though you did not call `test_add()` manually, Python found it and ran it for you — that's what "automatically" means.

❌ What if method doesn't start with `test_`?
```
class TestMath(unittest.TestCase):
    def check_add(self):
        self.assertEqual(1 + 2, 3)
```

If you run the file, nothing will happen — `unittest` ignores this method because it doesn't follow 
the `test_` naming convention:
```
----------------------------------------------------------------------
Ran 0 tests in 0.000s

OK
```
So: no error, but your test is silently skipped.


✅ TL;DR:
“Automatically” means unittest will find and run test methods for you, as long as they're named starting 
with `test_`, without you needing to call them manually.
"""

r"""
# ==========================================================================================================
# Understanding Test Structure
# ==========================================================================================================
Let's break down the anatomy of a test:
```
def test_add_positive_numbers(self):

    # A test method must:
    # 1. Start with 'test_' (so unittest can find it)
    # 2. Take 'self' as parameter (it's a class method)
    # 3. Have a descriptive name
    
    # ARRANGE: Set up test data
    number1 = 2
    number2 = 3
    expected_result = 5
    
    # ACT: Call the function being tested
    actual_result = add(number1, number2)
    
    # ASSERT: Check if the result is what we expected
    self.assertEqual(actual_result, expected_result)
```
This is called the AAA pattern:
    - Arrange: Set up your test data
    - Act: Execute the code(function) you're testing
    - Assert: Verify the results are correct

# ==========================================================================================================
# Common Assertion Methods
# ==========================================================================================================
unittest provides many assertion methods:
"""
class TestAssertionExamples(unittest.TestCase):
    
    def test_assertion_examples(self):
        """Examples of different assertion methods"""
        
        # Check if two values are equal
        self.assertEqual(add(2, 3), 5)
        
        # Check if two values are NOT equal
        self.assertNotEqual(add(2, 3), 6)
        
        # Check if something is True
        self.assertTrue(5 > 3)
        
        # Check if something is False
        self.assertFalse(5 < 3)
        
        # Check if a value is None
        self.assertIsNone(None)
        
        # Check if a value is NOT None
        self.assertIsNotNone("hello")
        
        # Check if an exception is raised
        self.assertRaises(ValueError, divide, 10, 0)
        
        # Check if a string contains another string
        self.assertIn("hello", "hello world")
        
        # Check if a value is in a list
        self.assertIn(3, [1, 2, 3, 4])
        
        # Check floating point numbers (they can have tiny differences)
        self.assertAlmostEqual(divide(10, 3), 3.333333, places=6)
        
        # Check if object is an instance of a class
        # assertIsInstance(obj, cls)
        self.assertIsInstance(123, int)
        
        # Check if object is **not** an instance of a class 
        # assertNotIsInstance(obj, cls)
        self.assertNotIsInstance(123, str)
        

# if __name__ == '__main__':
#     # Run only the specified test class
#     # In this case, it will run only the tests in TestAssertionExamples
#     # instead of discovering and running all test cases in the file
#     unittest.main(defaultTest='TestAssertionExamples')

r"""
Useful Assertions You Haven't Used Yet
| Method                          | Description                                                             |
| ------------------------------- | ----------------------------------------------------------------------- |
| `assertIs(a, b)`                | `a is b` — same object (identity)                                       |
| `assertIsNot(a, b)`             | `a is not b`                                                            |
| `assertNotIn(a, b)`             | `a not in b`                                                            |
| `assertGreater(a, b)`           | `a > b`                                                                 |
| `assertLess(a, b)`              | `a < b`                                                                 |
| `assertGreaterEqual(a, b)`      | `a >= b`                                                                |
| `assertLessEqual(a, b)`         | `a <= b`                                                                |
| `assertDictEqual(d1, d2)`       | Two dicts have same keys and values                                     |
| `assertListEqual(l1, l2)`       | Two lists have same elements                                            |
| `assertTupleEqual(t1, t2)`      | Two tuples are equal                                                    |
| `assertSetEqual(s1, s2)`        | Two sets are equal                                                      |
| `assertMultiLineEqual(a, b)`    | Compares two strings and shows line-by-line diff (great for multi-line) |
| `assertRegex(text, regex)`      | `re.search(regex, text)` is True                                        |
| `assertNotRegex(text, regex)`   | `re.search(regex, text)` is False                                       |


# ==========================================================================================================
# Using `with` for `assertRaises`
# ==========================================================================================================
You can also use `assertRaises` as a context manager (more flexible):
```
with self.assertRaises(ValueError):
    divide(10, 0)
```


# ==========================================================================================================
# Testing Edge Cases
# ==========================================================================================================
Good tests cover edge cases - unusual or extreme inputs:
"""
class TestEdgeCases(unittest.TestCase):
    """Examples of testing edge cases"""
    
    def test_empty_inputs(self):
        """Test with empty or None inputs"""
        # What happens with empty strings?
        # What happens with None values?
        # These tests help you think about these scenarios
        pass

    def test_empty_inputs_with_assertions(self):
        """Test with empty or None inputs
        
        This ensures your functions either:
            - Raise helpful errors (TypeError, etc.)
            - Or handle edge types gracefully (if you decide to add input validation later)
        """

        # Note that we use `with self.assertRaises()` here, it's a context manager
        with self.assertRaises(TypeError):
            add(None, 5)

        with self.assertRaises(TypeError):
            subtract("", 3)

        with self.assertRaises(TypeError):
            multiply(None, None)

        with self.assertRaises(TypeError):
            divide("", "")

        with self.assertRaises(TypeError):
            calculate_discount(None, 10)

    def test_very_large_numbers(self):
        """Test with very large numbers"""
        large_num = 999999999999999
        self.assertEqual(add(large_num, 1), 1000000000000000)
    
    def test_very_small_numbers(self):
        """Test with very small decimal numbers"""
        small_num = 0.0000001
        result = add(small_num, small_num)
        self.assertAlmostEqual(result, 0.0000002, places=7)
    
    def test_boundary_conditions(self):
        """Test boundary conditions for discount function"""
        # Test exactly 0% discount
        self.assertEqual(calculate_discount(100, 0), 100.0)
        
        # Test exactly 100% discount
        self.assertEqual(calculate_discount(100, 100), 0.0)
        
        # Test just inside valid range
        self.assertEqual(calculate_discount(100, 1), 99.0)
        self.assertEqual(calculate_discount(100, 99), 1.0)

    def test_floating_point_imprecision(self):
        """Test imprecise floating-point behavior"""
        result = add(0.1, 0.2)
        self.assertAlmostEqual(result, 0.3, places=7)  # 0.30000000000000004

    # 📈 Stress Test / Performance (Optional for Large Inputs)
    # You could test for performance with massive inputs, just to see if the function chokes (e.g., large list operations, 
    # deep recursion — not applicable now, but good habit).

# if __name__ == '__main__':
#     unittest.main(defaultTest='TestEdgeCases')


"""
### Consider Using Subtests
Subtests make failures easier to debug when looping over similar cases:
```
def test_discount_boundaries(self):

    # Test discount at boundary values
    for price, discount, expected in [
        (100, 0, 100.0),
        (100, 100, 0.0),
        (100, 1, 99.0),
        (100, 99, 1.0),
    ]:
        with self.subTest(discount=discount):
            self.assertEqual(calculate_discount(price, discount), expected)
```


# ==========================================================================================================
# What Makes a Good Test?
# ==========================================================================================================
Good tests are:
    1. Independent: Each test should work on its own
    2. Repeatable: Should give same result every time
    3. Fast: Should run quickly
    4. Clear: Easy to understand what's being tested
    5. Focused: Test one specific behavior

Bad test example:
```
def test_everything_at_once(self):
    # DON'T DO THIS - tests too many things at once
    self.assertEqual(add(2, 3), 5)
    self.assertEqual(subtract(10, 5), 5)
    self.assertEqual(multiply(3, 4), 12)
    # If any one of these fails, you won't know which one without investigating
````

Good test examples:
```
def test_add_returns_correct_sum(self):
    # GOOD - tests one specific behavior clearly
    self.assertEqual(add(2, 3), 5)

def test_subtract_returns_correct_difference(self):
    # GOOD - separate test for separate behavior
    self.assertEqual(subtract(10, 5), 5)
```


# ==========================================================================================================
# How to Run the Tests from the Command Line
# ==========================================================================================================

After uncomment the `if __name__ == '__main__':` block

Option 1: Run from CLI
-----------------------
$ python test_file.py
# Example: python "Testing in Python/1_introduction.py"

Option 2: Run a specific class
------------------------------
$ python test_file.py TestEdgeCases
# Example: python "Testing in Python/1_introduction.py" TestEdgeCases

Option 3: Use unittest discovery
-------------------------------
$ python -m unittest discover

All tests must be named like `test_*.py` and reside in the same folder or a `tests/` subfolder.


# ==========================================================================================================
# When `unittest` Is Used in the Real World
# ==========================================================================================================
unittest is:
    - part of the Python standard library (no external dependencies)
    - robust and well-documented
    - compatible with most CI/CD tools
    - enough for many basic and intermediate testing needs

It's often used in:
    - small to medium-sized applications
    - internal tools and utilities
    - enterprise projects that prefer no third-party libraries
    - legacy codebases that started with unittest
    - educational and training materials (due to its built-in availability)

❗️But... It's not always the first choice
In modern Python projects, many teams prefer more expressive and feature-rich test frameworks, such as:
| Tool                                        | Why it's often preferred                                                          |
| ------------------------------------------- | --------------------------------------------------------------------------------- |
| **`pytest`**                                | Less boilerplate, better output, fixtures, plugins, supports `unittest` tests too |
| **`nose2`**                                 | Successor to `nose`, supports `unittest`-style tests                              |
| **`hypothesis`**                            | Property-based testing — generates test inputs automatically                      |
| **`tox`**                                   | Test across multiple Python environments                                          |
| **`pytest-django`, `pytest-fastapi`**, etc. | Add testing support for web frameworks                                            |


🔄 Compatibility Note
pytest can run unittest-based tests too. That means you can:
    - Start with unittest for simplicity
    - Gradually migrate to pytest if your needs grow

Real-World Scenarios
| Project Type                       | What They Use                                                         |
| ---------------------------------- | --------------------------------------------------------------------  |
| ✅ **Internal API at a bank**       | `unittest` for compliance, simplicity, and stability                 |
| ✅ **IoT firmware testing**         | `unittest` for basic correctness checks                              |
| ✅ **Data pipeline in Python**      | Started with `unittest`, added `pytest` later                        |
| ❌ **Large-scale SaaS web app**     | Usually uses `pytest` or a combo of `pytest + unittest.mock`         |
| ✅ **Machine learning experiments** | Quick `unittest` or `pytest` test suites to verify training pipeline |

🧠 So Should You Use It?
Yes, as a beginner or early-stage developer, using `unittest` is:
    - Totally professional
    - Widely understood by teams
    - Great for learning core testing skills (assertions, test structure, automation)
If your project becomes more complex, you'll have no trouble transitioning to `pytest` — and your `unittest` experience 
will transfer directly.

| Feature      | `unittest`                                      | `pytest`                                |
| ------------ | ----------------------------------------------- | --------------------------------------- |
| Built-in?    | Yes (standard library)                          | No (third-party package)                |
| Installation | No install needed                               | `pip install pytest` required           |
| Ease of use  | More boilerplate                                | Less boilerplate, simpler syntax        |
| Popularity   | Common, especially for beginners or legacy code | Very popular for modern Python projects |


# ==========================================================================================================
# Common Job Titles for a Tester Role:
# ==========================================================================================================
| Title                                            | Description                                                                           |
| ------------------------------------------------ | ------------------------------------------------------------------------------------- |
| **Software Tester**                              | Tests applications manually or with automation to find bugs.                          |
| **QA Engineer** (Quality Assurance)              | Broader than testing — includes planning, designing, and maintaining test processes.  |
| **Test Engineer**                                | Similar to QA, often focused more on automation or technical tests.                   |
| **SDET** (Software Development Engineer in Test) | A hybrid role — writes code to test other code, often builds test frameworks.         |
| **Automation Tester**                            | Specializes in writing automated test scripts (e.g., with Selenium, Pytest, etc.).    |
| **Manual Tester**                                | Focuses on user-side or black-box testing without writing code.                       |
| **Quality Analyst / QA Analyst**                 | Sometimes more business-oriented — works closely with requirements and test planning. |


Key Skills for a Tester Role
| Skill Area          | Examples                                                          |
| ------------------- | ----------------------------------------------------------------- |
| ✅ **Testing Types** | Unit, Integration, System, Acceptance, Regression, Smoke          |
| ✅ **Test Design**   | Writing test cases, scenarios, test plans                         |
| ✅ **Tools**         | JIRA, TestRail, Selenium, Postman, Pytest, Playwright, Cypress    |
| ✅ **Automation**    | Python (unittest, pytest), JavaScript, Java, etc.                 |
| ✅ **CI/CD Testing** | GitHub Actions, Jenkins, GitLab CI                                |
| ✅ **Bug Reporting** | Clear bug writing, repro steps, priority/severity                 |
| ✅ **Mindset**       | Detail-oriented, curious, able to think like a user and developer |

🧭 Career Paths for a Tester
- Manual Tester → Automation Tester → SDET → QA Lead → QA Manager
- Or even:
    - Tester → Developer (if you get into coding)
    - Tester → Product Owner (deep knowledge of user behavior helps)
    - Tester → DevOps (some overlap when working on release pipelines)

💼 Are There Jobs That Are Just Testing?
Yes. Many companies hire testers exclusively for:
- Regression testing
- Manual exploratory testing
- Writing and maintaining test suites
- Building automated testing pipelines
- Mobile or API testing
- Ensuring quality before deployment
- Even large tech companies like Microsoft, Amazon, and Google have QA/SDET positions. Startups and mid-size companies usually have dedicated testers too.

🧠 Bonus — How to Search for These Roles
Search job platforms like LinkedIn or Indeed for:
- "QA Engineer"
- "Software Tester"
- "Manual QA"
- "SDET"
- "Test Automation Engineer"
- Filter by entry-level if you're just starting out.
"""
