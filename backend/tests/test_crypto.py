"""
Unit tests for the Fernet crypto service.

Tests cover:
- Round-trip encrypt → decrypt equality
- Ciphertext differs from plaintext
- Each encryption produces a unique ciphertext (random IV)
- Wrong key raises InvalidToken (no silent corruption)
- Edge case: empty string
- Edge case: unicode / emoji
"""

import pytest
from cryptography.fernet import InvalidToken
from pydantic import SecretStr

from wxcode_adm import config as config_module
from wxcode_adm.common.crypto import decrypt_value, encrypt_value

# A known test key (arbitrary passphrase — crypto.py derives a valid Fernet key from it)
_TEST_KEY_1 = "test-key-1"
_TEST_KEY_2 = "test-key-2"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_key(monkeypatch, key: str) -> None:
    """Monkeypatch WXCODE_ENCRYPTION_KEY on the settings singleton."""
    monkeypatch.setattr(config_module.settings, "WXCODE_ENCRYPTION_KEY", SecretStr(key))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip(monkeypatch):
    """encrypt_value → decrypt_value returns the original plaintext."""
    _patch_key(monkeypatch, _TEST_KEY_1)

    original = "hello-wxcode-crypto"
    ciphertext = encrypt_value(original)
    assert decrypt_value(ciphertext) == original


def test_encrypted_value_differs_from_plaintext(monkeypatch):
    """The ciphertext must not equal the original plaintext (sanity check)."""
    _patch_key(monkeypatch, _TEST_KEY_1)

    plaintext = "secret-token"
    ciphertext = encrypt_value(plaintext)
    assert ciphertext != plaintext


def test_encrypt_produces_different_ciphertexts(monkeypatch):
    """Fernet uses a random IV so encrypting the same plaintext twice yields distinct tokens."""
    _patch_key(monkeypatch, _TEST_KEY_1)

    plaintext = "same-input-string"
    ct1 = encrypt_value(plaintext)
    ct2 = encrypt_value(plaintext)
    assert ct1 != ct2, "Fernet should produce different ciphertexts due to random IV"


def test_decrypt_with_wrong_key_fails(monkeypatch):
    """Decrypting with a different key must raise InvalidToken (not silently corrupt)."""
    _patch_key(monkeypatch, _TEST_KEY_1)
    ciphertext = encrypt_value("my-secret-data")

    # Switch to a different key before decrypting
    _patch_key(monkeypatch, _TEST_KEY_2)

    with pytest.raises(InvalidToken):
        decrypt_value(ciphertext)


def test_encrypt_empty_string(monkeypatch):
    """An empty string must round-trip correctly."""
    _patch_key(monkeypatch, _TEST_KEY_1)

    ciphertext = encrypt_value("")
    assert decrypt_value(ciphertext) == ""


def test_encrypt_unicode(monkeypatch):
    """Unicode strings including emoji must round-trip correctly."""
    _patch_key(monkeypatch, _TEST_KEY_1)

    original = "encriptacao segura \U0001f512"
    ciphertext = encrypt_value(original)
    assert decrypt_value(ciphertext) == original
