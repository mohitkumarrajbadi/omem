"""AES-256-GCM field-level encryption for memory content and metadata."""

from __future__ import annotations

import base64
import binascii
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class EncryptionManager:
    """AES-256-GCM encryption for sensitive memory fields.

    Only ``content`` and ``metadata`` columns are encrypted.
    ``id``, ``namespace``, ``type``, ``logical_hash`` remain plaintext
    to preserve DB indexing. Vectors are not encrypted (encrypting them
    would break ANN indexing).

    Args:
        key: 32-byte encryption key.
    """

    PREFIX = "ENC:v1:"
    MAGIC = b"ENV1"

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("Encryption key must be exactly 32 bytes (256 bits)")
        self._key = key

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string. Returns PREFIX + base64(iv + ciphertext + tag)."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        iv = os.urandom(12)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
        payload = base64.b64encode(iv + ciphertext).decode("ascii")
        return self.PREFIX + payload

    def decrypt(self, value: str) -> str:
        """Decrypt a string. Returns unchanged if no prefix (backward compat)."""
        if not value.startswith(self.PREFIX):
            return value
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw = base64.b64decode(value[len(self.PREFIX) :])
        iv, ciphertext = raw[:12], raw[12:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(iv, ciphertext, None).decode("utf-8")

    def encrypt_bytes(self, data: bytes) -> bytes:
        """Encrypt raw bytes. Prepends MAGIC + iv + ciphertext."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        iv = os.urandom(12)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(iv, data, None)
        return self.MAGIC + iv + ciphertext

    def decrypt_bytes(self, data: bytes) -> bytes:
        """Decrypt raw bytes. Returns unchanged if no MAGIC header."""
        if not data.startswith(self.MAGIC):
            return data
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        rest = data[len(self.MAGIC) :]
        iv, ciphertext = rest[:12], rest[12:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(iv, ciphertext, None)

    @staticmethod
    def parse_key_material(raw: str) -> bytes:
        """Accept base64url (32 bytes) or hex (64 chars → 32 bytes)."""
        raw = (raw or "").strip()
        if not raw:
            raise ValueError("empty encryption key")
        if len(raw) == 64 and all(c in "0123456789abcdefABCDEF" for c in raw):
            return binascii.unhexlify(raw)
        padded = raw + "=" * (-len(raw) % 4)
        try:
            key = base64.urlsafe_b64decode(padded)
        except Exception:
            key = base64.b64decode(padded)
        if len(key) != 32:
            raise ValueError(
                f"Encryption key must decode to 32 bytes, got {len(key)}. "
                "Use 64-char hex or base64url of 32 random bytes."
            )
        return key

    @classmethod
    def from_env(cls) -> Optional["EncryptionManager"]:
        """Load key from ``OMEM_ENCRYPTION_KEY`` or legacy ``OMEM_SECRET_KEY``.

        Opt-out: set ``OMEM_ENCRYPTION_DISABLED=1`` (cloud/enterprise should not).
        """
        if os.environ.get("OMEM_ENCRYPTION_DISABLED", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            logger.warning(
                "Field-level encryption DISABLED via OMEM_ENCRYPTION_DISABLED — "
                "memory content/metadata stored in plaintext"
            )
            return None
        raw = (
            os.environ.get("OMEM_ENCRYPTION_KEY", "").strip()
            or os.environ.get("OMEM_SECRET_KEY", "").strip()
        )
        if not raw:
            return None
        try:
            return cls(cls.parse_key_material(raw))
        except Exception as exc:
            logger.error("Invalid encryption key material: %s", exc)
            raise
