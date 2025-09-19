from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from pathlib import Path

class Settings(BaseSettings):
    """
    Application settings loaded from environment.
    """

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
    LOG_LEVEL: str = "INFO"

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

    # class Config:
    #     env_file = str(Path(__file__).parent.parent / ".env")
    #     env_file_encoding = "utf-8"

    model_config = ConfigDict(
        # Load environment variables from the .env file located two levels up relative to this file.
        env_file=str(Path(__file__).parent.parent / ".env"),
        env_file_encoding="utf-8"
    )

def get_settings() -> Settings:
    return Settings()
