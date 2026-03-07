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

    # --- OAuth (Phase 6 -- OAuth and MFA) ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: SecretStr = SecretStr("")
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: SecretStr = SecretStr("")
    # SessionMiddleware secret for authlib state + PKCE code_verifier storage
    # REQUIRED — no default; generate a strong random value for production
    SESSION_SECRET_KEY: SecretStr

    # --- MFA (Phase 6 -- OAuth and MFA) ---
    MFA_PENDING_TTL_SECONDS: int = 300  # 5 minutes for MFA pending token
    TRUSTED_DEVICE_TTL_DAYS: int = 30

    # --- Phase 7 -- User Account ---
    GEOLITE2_DB_PATH: str = ""  # empty string = geolocation disabled (no crash if MMDB missing)
    WXCODE_CODE_TTL: int = 30  # one-time authorization code TTL in seconds
    AVATAR_UPLOAD_DIR: str = "/app/avatars"  # local filesystem path for avatar storage

    # --- Phase 8 -- Super-admin ---
    # Comma-separated IP addresses allowed to access /api/v1/admin/login.
    # Empty string = no IP restriction (dev-friendly default).
    # Example: "1.2.3.4,5.6.7.8"
    ADMIN_ALLOWED_IPS: str = ""

    # --- Phase 20 -- Crypto Service ---
    # Fernet encryption key for storing sensitive values (e.g. OAuth tokens) at rest.
    # In production, generate a real Fernet key: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # The crypto service accepts any string and derives a valid key via SHA-256 if needed.
    WXCODE_ENCRYPTION_KEY: SecretStr = SecretStr("change-me-in-production")


# Module-level singleton — raises ValidationError at import if env vars missing
settings = Settings()
