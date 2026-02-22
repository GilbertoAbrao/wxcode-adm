from pydantic import PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- App ---
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_PORT: int = 8060

    # --- Database ---
    # Must be full DSN: postgresql+asyncpg://user:pass@host:5432/db
    DATABASE_URL: PostgresDsn

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- JWT (Phase 2, declared here to fail fast if missing) ---
    JWT_PRIVATE_KEY: SecretStr  # RSA PEM, multi-line, set as env var
    JWT_PUBLIC_KEY: SecretStr

    # --- Super-admin seed ---
    SUPER_ADMIN_EMAIL: str
    SUPER_ADMIN_PASSWORD: SecretStr

    # --- CORS ---
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3060"]


# Module-level singleton — raises ValidationError at import if env vars missing
settings = Settings()
