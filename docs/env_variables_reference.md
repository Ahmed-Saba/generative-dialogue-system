# Environment Variables Reference

## What is `ENV`?

Purpose:  

- Defines the current runtime environment of the application.

Typical Values:

- `development` — Local development environment

- `testing` or `test` — Running automated tests

- `staging` — Pre-production testing environment

- `production` — Live production environment

Usage:

- The app can change behavior based on `ENV`, such as enabling debug logs in development, or disabling detailed logging in production.

Recommended for Testing:

- Set `ENV` to `"testing"` or `"test"` when running automated tests to clearly distinguish the environment from development or production.

## What is `TESTING`?

Purpose:

- A boolean flag (true/false) indicating whether the application is running in a test mode.

Typical Values:

- `true` — The app is running tests

- `false` or not set — Normal operation mode

Effect on Behavior:

- When `TESTING=true`, the app will usually connect to a dedicated test database (`TEST_POSTGRES_DB`) instead of the production database to avoid data contamination.

Can enable mock services, disable certain production-only features, or tweak configurations for fast, isolated tests.

Recommended for Testing:

- Always set `TESTING=true` during test runs.

## How `ENV` and `TESTING` Work Together

| `ENV` Value   | `TESTING` Value  | Behavior                                        |
| ------------- | ---------------- | ----------------------------------------------- |
| `testing`     | `true`           | Uses test database, test-specific settings      |
| `testing`     | `false` or unset | Typically treated as normal operation           |
| `development` | `false` or unset | Uses development database, debug enabled        |
| `production`  | `false` or unset | Uses production database, optimizations enabled |

## What values should `ENV` and `TESTING` have during tests?

### 1. ENV

- Value during tests: `"test"` or `"development"` (optional)

- This variable is mainly for app environment awareness (like logging config). You can set it to `"test"` or `"development"` when running tests. Usually `"development"` is fine unless you want custom behavior for tests.

### 2. TESTING

- Value during tests: `True`

- This is the key flag that tells your app you’re running tests. When `TESTING=true`, your `settings.py` switches to the test database (`TEST_POSTGRES_DB`) instead of the production DB, preventing accidental data changes.

### Why is `TESTING=true` important?

Your `settings.py` uses this flag to switch the DB URL to use the test database:

```python
if self.TESTING and self.TEST_POSTGRES_DB:
    # Use the test DB in your connection URL
    ...
else:
    # Use production DB URL
```

This means your tests will use the isolated test database instead of production.

### What about `ENV` during testing?

You can set:

```env
ENV=test
TESTING=true
```

or just keep

```env
ENV=development
TESTING=true
```

`ENV` mainly controls logging config and other environment-specific behavior, so it’s okay if it’s `"development"` during testing unless you want to differentiate logs or behavior explicitly.

### Example snippet for testing environment

```env
ENV=test
TESTING=true

# Use the test database
TEST_POSTGRES_DB="test_gds_db"

# (Optional) Override regular DB vars too or leave as is if not used directly
POSTGRES_DB="gds_db"
POSTGRES_USERNAME="postgres"
POSTGRES_PASSWORD="postgresql_admin_123456"
POSTGRES_HOST="localhost"
POSTGRES_PORT=5432
POSTGRES_DRIVER="psycopg"
```

### How your test setup uses these

Your `tests/conftest.py` uses `get_settings()` which reads these env variables, and then your

```python
settings.DATABASE_URL
```

automatically returns the URL for the test DB because `TESTING=true` is set, so your tests are isolated safely.

## Common Mistakes to Avoid

- Running tests with `TESTING=false` or unset, which may connect to the production database.

- Forgetting to set `ENV=testing` in test runs, leading to unexpected behavior or logging.

- Using the same database for production and testing, risking data loss.
