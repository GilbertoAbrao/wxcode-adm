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
    JWT_KID: str = "v1"  # Static key ID for Phase 2 (single-key rotation)
    ACCESS_TOKEN_TTL_HOURS: int = 24
    REFRESH_TOKEN_TTL_DAYS: int = 7

    # --- Super-admin seed ---
    SUPER_ADMIN_EMAIL: str
    SUPER_ADMIN_PASSWORD: SecretStr

    # --- SMTP (fastapi-mail, defaults for Mailpit in development) ---
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@wxcode.io"
    SMTP_FROM_NAME: str = "WXCODE"
    SMTP_TLS: bool = False
    SMTP_SSL: bool = False

    # --- CORS ---
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3060"]

    # --- Stripe (Phase 4 -- Billing) ---
    STRIPE_SECRET_KEY: SecretStr
    STRIPE_PUBLISHABLE_KEY: str
    STRIPE_WEBHOOK_SECRET: SecretStr

    # --- Audit Log (Phase 5 -- Platform Security) ---
    AUDIT_LOG_RETENTION_DAYS: int = 365

    # --- Rate Limiting (Phase 5 -- Platform Security) ---
    RATE_LIMIT_AUTH: str = "5/minute"    # Strict limit for auth endpoints (brute-force protection)
    RATE_LIMIT_GLOBAL: str = "60/minute"  # Global default for all other endpoints

    # --- Frontend ---
    FRONTEND_URL: str = "http://localhost:3060"


# Module-level singleton — raises ValidationError at import if env vars missing
settings = Settings()
