from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator
from pathlib import Path
from typing import Literal
from functools import lru_cache
from ..validators.config_validators import to_uppercase, to_lowercase

class Settings(BaseSettings):
    """
    Application settings loaded from environment.
    """
    
    # Environment
    ENV: Literal["development", "testing", "staging", "production"] = "development"

    # Database configuration
    POSTGRES_DRIVER: str
    POSTGRES_USERNAME: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str

    # Test database configuration
    TEST_POSTGRES_DB: str | None = None
    TESTING: bool = False

    # SQLAlchemy
    SQLALCHEMY_ECHO: bool = False

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FORMAT: Literal["json", "text"] = "json"
    LOG_TO_STDOUT: bool = True
    LOG_DIR: Path = Path("/var/log/gds")
    LOG_MAX_BYTES: int = 10_000_000  # 10 MB
    LOG_BACKUP_COUNT: int = 5
    ENABLE_SQL_LOGGING: bool = False

    # Sentry
    SENTRY_DSN: str | None = None

    # --- Derived settings ---
    @property
    def DATABASE_URL(self) -> str:
        """
        Return the appropriate database URL based on the current environment.

        The logic is as follows:
        - If `TESTING=True` and `TEST_POSTGRES_DB` is provided, the database URL will be
        constructed using the test database (`TEST_POSTGRES_DB`) to avoid using the
        production database during tests.
        - If `TESTING=False` (or not set), the database URL will be constructed using
        the regular production database (`POSTGRES_DB`).
        
        This ensures that when running tests, a separate test database is used, preventing
        any accidental data modification in the production database.
        
        Returns:
            str: The constructed database connection URL.
        """

        # If testing and TEST_POSTGRES_DB is provided, prefer it
        if self.TESTING and self.TEST_POSTGRES_DB:
            return (
                f"postgresql+{self.POSTGRES_DRIVER}://"
                f"{self.POSTGRES_USERNAME}:{self.POSTGRES_PASSWORD}@"
                f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/"
                f"{self.TEST_POSTGRES_DB}"
            )

        # Default to the production database URL
        return (
            f"postgresql+{self.POSTGRES_DRIVER}://"
            f"{self.POSTGRES_USERNAME}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/"
            f"{self.POSTGRES_DB}"
        )

    # --- Validators ---
    @field_validator("LOG_LEVEL", mode="before")
    def normalize_log_level(cls, v: str | None) -> str | None:
        """
        Normalize the LOG_LEVEL environment variable value to uppercase.

        This validator runs before any other validation (mode="before") on the LOG_LEVEL field.
        It ensures that the logging level string is always uppercase, which is important because
        the logging system typically expects log level names in uppercase (e.g., "DEBUG", "INFO").

        Args:
            cls: The class where this validator is defined.
            v (str | None): The raw input value for LOG_LEVEL from the environment or user input.
                            May be None if the variable is unset.

        Returns:
            str | None: The normalized uppercase log level string, or None if input was None.

        Raises:
            ValidationError: If the input is invalid (handled by Pydantic automatically).
        """
        return to_uppercase(v)

    @field_validator("LOG_FORMAT", mode="before")
    def normalize_log_format(cls, v: str | None) -> str | None:
        """
        Normalize the LOG_FORMAT environment variable value to lowercase.
        """
        return to_lowercase(v)

    # --- ConfigDict settings ---
    model_config = ConfigDict(
        # Load environment variables from the .env file located two levels up relative to this file.
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8"
    )

# get_settings() takes no arguments and always returns the same settings from the environment, 
# so caching it with @lru_cache() is good for performance.
@lru_cache()
def get_settings() -> Settings:
    return Settings()
