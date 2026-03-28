"""Application configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database - use SQLite for local testing if MySQL unavailable
    DATABASE_URL: str = "sqlite:////tmp/nl_test.db"

    # LLM
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"

    # App
    APP_TITLE: str = "NL Test Framework"
    SCREENSHOT_DIR: str = "./screenshots"
    MAX_CONCURRENT_TESTS: int = 3
    DEFAULT_TIMEOUT_MS: int = 15000

    class Config:
        env_file = ".env"


settings = Settings()
