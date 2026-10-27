import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = 5432

    REDIS_HOST: str = "localhost"
    REDIS_PORT: str = 6379
    REDIS_PASSWORD: str

    FIRST_ADMIN_DEFAULT_NAME: str = "Admin"
    FIRST_ADMIN_DEFAULT_USER_NAME: str = "admin"
    FIRST_ADMIN_DEFAULT_PASSWORD: str

    HTTPS: bool = False  # Set to True in production
    CORS_ALLOWED_ORIGINS: list[str]

    JWT_TOKEN_KEY: str
    JWT_EXPIRES_TIME: int = 60 * 10
    JWT_ALGORITHM: str = "HS256"

    REFRESH_TOKEN_KEY: str
    REFRESH_EXPIRES_TIME: int = 3600 * 24 * 7

    @property
    def POSTGRES_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="forbid",
    )


settings = Settings()
