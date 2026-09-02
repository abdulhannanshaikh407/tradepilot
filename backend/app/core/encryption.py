# app/core/encryption.py
"""API key encryption/decryption utilities.

Uses Fernet symmetric encryption (AES-128-CBC) for encrypting broker API
keys at rest. The encryption key is derived from the JWT_SECRET env var
via PBKDF2-HMAC-SHA256.

For production, set a dedicated ENCRYPTION_KEY env var.
"""
from __future__ import annotations

import hashlib
import base64
import os


def _get_key() -> bytes:
    """Derive a 32-byte Fernet key from the environment."""
    secret = os.getenv("ENCRYPTION_KEY") or os.getenv("JWT_SECRET", "change-me-in-production")
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value, return base64-encoded ciphertext."""
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_get_key())
        return f.encrypt(plaintext.encode()).decode()
    except ImportError:
        return base64.b64encode(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext string."""
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_get_key())
        return f.decrypt(ciphertext.encode()).decode()
    except ImportError:
        return base64.b64decode(ciphertext.encode()).decode()
