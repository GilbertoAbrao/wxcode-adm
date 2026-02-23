"""
Password hashing utilities using Argon2 via pwdlib.

Uses a module-level singleton PasswordHash instance with the recommended
configuration (Argon2id). This avoids re-initializing the hasher on every
request.

Security notes:
- Argon2id is the current best practice for password hashing (OWASP 2024).
- pwdlib.PasswordHash.recommended() uses Argon2id with secure defaults.
- Never store or log plain-text passwords — only pass them to hash_password/verify_password.
"""

from pwdlib import PasswordHash

# Module-level singleton — thread-safe, initialized once at import time.
pwd_context = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    """
    Hash a plain-text password using Argon2id.

    Args:
        plain: The plain-text password to hash.

    Returns:
        An Argon2id hash string suitable for storage in the database.
    """
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plain-text password against an Argon2id hash.

    Args:
        plain: The plain-text password to check.
        hashed: The stored Argon2id hash from the database.

    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain, hashed)
