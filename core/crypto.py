"""Fernet encryption utility for secrets stored in DB."""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet

from core.exceptions import ConfigurationError


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Get a cached Fernet instance (avoids recreating on every call)."""
    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        raise ConfigurationError(
            "ENCRYPTION_KEY not set. Generate with: "
            "python -c 'from cryptography.fernet import "
            "Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode())


def reset_fernet_cache() -> None:
    """Clear the cached Fernet instance (for testing or key rotation)."""
    _get_fernet.cache_clear()


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext string, return base64 ciphertext. Returns empty string for empty input."""
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt base64 ciphertext, return plaintext. Returns empty string for empty input."""
    if not ciphertext:
        return ""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
