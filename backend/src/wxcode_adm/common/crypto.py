"""
Fernet symmetric encryption service for wxcode-adm.

Provides encrypt_value / decrypt_value for storing sensitive strings
(e.g. Claude OAuth tokens) encrypted at rest in the database.

Key derivation:
    If WXCODE_ENCRYPTION_KEY is already a valid Fernet key (exactly 44
    URL-safe base64 characters), it is used directly.  Otherwise it is
    treated as an arbitrary passphrase and a stable Fernet key is derived
    from it via SHA-256 + URL-safe base64 encoding.  This means the dev
    default ("change-me-in-production") works out of the box while
    production deployments can supply a real Fernet key from
    `Fernet.generate_key().decode()`.

Usage:
    from wxcode_adm.common.crypto import encrypt_value, decrypt_value

    ciphertext = encrypt_value("my-secret-token")
    plaintext  = decrypt_value(ciphertext)

Raises:
    cryptography.fernet.InvalidToken — if ciphertext is tampered with or
    decrypted with the wrong key.
"""

import base64
import hashlib

from cryptography.fernet import Fernet

from wxcode_adm.config import settings


def _get_fernet() -> Fernet:
    """
    Build a Fernet instance from the configured encryption key.

    Reads settings.WXCODE_ENCRYPTION_KEY each time so that tests can
    monkeypatch the value without stale module-level state.
    """
    raw_key: str = settings.WXCODE_ENCRYPTION_KEY.get_secret_value()

    # Detect whether raw_key is already a valid Fernet key:
    # Fernet keys are exactly 44 URL-safe base64 characters that decode to 32 bytes.
    is_valid_fernet_key = False
    if len(raw_key) == 44:
        try:
            decoded = base64.urlsafe_b64decode(raw_key + "==")  # padding tolerance
            if len(decoded) == 32:
                is_valid_fernet_key = True
        except Exception:
            pass

    if is_valid_fernet_key:
        fernet_key = raw_key.encode()
    else:
        # Derive a stable 32-byte key from the passphrase via SHA-256
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(digest)

    return Fernet(fernet_key)


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a UTF-8 string using Fernet symmetric encryption.

    Args:
        plaintext: The string to encrypt.

    Returns:
        A URL-safe base64-encoded ciphertext string (Fernet token).
    """
    fernet = _get_fernet()
    token: bytes = fernet.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a Fernet ciphertext string back to UTF-8 plaintext.

    Args:
        ciphertext: A Fernet token string produced by encrypt_value.

    Returns:
        The original plaintext string.

    Raises:
        cryptography.fernet.InvalidToken: If the ciphertext is invalid,
            tampered with, or was encrypted with a different key.
    """
    fernet = _get_fernet()
    plaintext_bytes: bytes = fernet.decrypt(ciphertext.encode("utf-8"))
    return plaintext_bytes.decode("utf-8")
