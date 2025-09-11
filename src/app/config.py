from pydantic_settings import BaseSettings

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

    # SQLAlchemy
    SQLALCHEMY_ECHO: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"

    # --- Derived settings ---
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+{self.POSTGRES_DRIVER}://"
            f"{self.POSTGRES_USERNAME}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/"
            f"{self.POSTGRES_DB}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
