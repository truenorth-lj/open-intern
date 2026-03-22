"""Fernet encryption utility for secrets stored in DB."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def get_encryption_key() -> bytes:
    """Read ENCRYPTION_KEY from environment. Returns raw bytes for Fernet."""
    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY not set. Generate with: "
            "python -c 'from cryptography.fernet import "
            "Fernet; print(Fernet.generate_key().decode())'"
        )
    return key.encode()


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext string, return base64 ciphertext. Returns empty string for empty input."""
    if not plaintext:
        return ""
    f = Fernet(get_encryption_key())
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt base64 ciphertext, return plaintext. Returns empty string for empty input."""
    if not ciphertext:
        return ""
    f = Fernet(get_encryption_key())
    return f.decrypt(ciphertext.encode()).decode()
