r"""
# ==========================================================================================================
# Pytest Markers
# ==========================================================================================================

What Are Pytest Markers?
Markers in pytest are labels or tags you can add to your test functions to:
    - Group or filter tests
    - Add metadata to tests
    - Control how tests are run (e.g., expected failures, skipping, parametrization)

Basic Syntax
```
@pytest.mark.<marker_name>
def test_something():
    ...
```

You can also pass arguments:
```
@pytest.mark.some_marker(reason="testing a flag")
```
"""

# ---------------------------------------------------------------------------
# Common Built-in Pytest Markers
# ---------------------------------------------------------------------------

## 1. `@pytest.mark.skip`
# Skip this test unconditionally. 

import pytest
@pytest.mark.skip(reason="Not implemented yet")
def test_login():
    assert False

## 2. `@pytest.mark.skipif(condition, reason=...)`
# Skip the test if the condition is True.
import sys
@pytest.mark.skipif(sys.platform == "win32", reason="Does not run on Windows")
def test_unix_only_feature():
    ...

## 3. `@pytest.mark.xfail`
# Mark test as expected to fail (e.g., known bugs, features not done).
@pytest.mark.xfail(reason="Bug #123 still open")
def test_feature_under_bug():
    assert 1 == 2
    
# Optional:
#   - strict=True: Make the test fail if it passes unexpectedly.


## 4. `@pytest.mark.parametrize`
# Run the same test with different inputs.
@pytest.mark.parametrize("a,b,result", [
    (1, 2, 3),
    (2, 3, 5),
    (10, 5, 15)
])
def test_addition(a, b, result):
    assert a + b == result

# You can also parametrize fixtures or custom markers.


# ---------------------------------------------------------------------------
# Custom Markers
# ---------------------------------------------------------------------------
# You can define your own markers to group or label tests.
@pytest.mark.api
def test_api_get():
    ...
# Then run only tests with that marker:
#   `pytest -m api`
# Or skip them:
#   `pytest -m "not api"`


## Registering Custom Markers (Best Practice)
# To avoid warnings, register your custom markers in pytest.ini:
# 
# pytest.ini
# ```
#   [pytest]
#   markers =
#       api: mark a test as part of the API suite
#       slow: marks tests as slow
#       db: tests that require the database
# ```


# ---------------------------------------------------------------------------
## Examples of Use Cases
# ---------------------------------------------------------------------------
# 1. Grouping Slow Tests
@pytest.mark.slow
def test_big_data_processing():
    ...
# Run only slow tests: `pytest -m slow`


# 2. Combining Markers
# Example 1
@pytest.mark.api
@pytest.mark.db
def test_api_with_db():
    ...

# Example 2
@pytest.mark.repository
@pytest.mark.integration
class TestBaseRepositoryCreate:
    ...
# This tells Pytest:
#   "This whole class belongs to the `repository` group and is also part of the `integration` tests."
# 
# These markers let you do things like:
# ```
#   pytest -m "integration"
#   # or
#   pytest -m "repository and integration"
# ```
# So you only run specific kinds of tests!

# ---------------------------------------------------------------------------
# Viewing Markers in a Test Run
# ---------------------------------------------------------------------------
# To see what markers are available:
# ```
#   pytest --markers
# ```

# Pro Tips:
# | Tip                                             | Description                                           |
# | ----------------------------------------------- | ----------------------------------------------------- |
# | ✅ Use `pytest.ini`                             | Register your custom markers to avoid warnings.       |
# | ✅ Combine with `-k` or `-m`                    | Run tests by keyword or marker for selective testing. |
# | ✅ Use `xfail` for known bugs                   | Avoid broken CI runs for expected failures.           |
# | ✅ Use `parametrize` to reduce code duplication | Cleaner and more scalable testing.                    |

