"""Cold L4 archive — S3-compatible object storage for archived memory payloads.

Postgres (or SQLite) remains the durable index; archived *content* may move
here to reduce hot-store size. Retrieval restores stubs via ``cold_storage_key``.

Encryption
----------
When ``OMEM_ENCRYPTION_KEY`` is set, payloads are AES-256-GCM encrypted before
storage (both local and S3 paths). The envelope is ``{"enc":"gcm","v":1,"blob":"<b64>"}``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _archive_encryption_key() -> Optional[bytes]:
    """Return 32-byte AES key from OMEM_ENCRYPTION_KEY/OMEM_SECRET_KEY, or None."""
    raw = (
        os.environ.get("OMEM_ENCRYPTION_KEY", "").strip()
        or os.environ.get("OMEM_SECRET_KEY", "").strip()
    )
    if not raw:
        return None
    try:
        if len(raw) == 64:
            key = bytes.fromhex(raw)
        else:
            key = base64.urlsafe_b64decode(raw + "==")
        if len(key) == 32:
            return key
    except Exception:
        pass
    return None


def _encrypt_payload(plaintext_bytes: bytes, key: bytes) -> bytes:
    """AES-256-GCM encrypt; return JSON envelope as bytes."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext_bytes, None)
    blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    return json.dumps({"enc": "gcm", "v": 1, "blob": blob}).encode("utf-8")


def _decrypt_payload(raw_bytes: bytes, key: bytes) -> bytes:
    """Decrypt an AES-256-GCM envelope; returns original plaintext bytes."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    envelope = json.loads(raw_bytes.decode("utf-8"))
    if envelope.get("enc") != "gcm":
        raise ValueError("Unknown encryption envelope")
    blob = base64.urlsafe_b64decode(envelope["blob"] + "==")
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(key).decrypt(nonce, ct, None)


@dataclass
class ColdArchiveConfig:
    """Configuration for cold object storage."""

    enabled: bool = False
    backend: str = "local"  # local | s3
    local_root: str = ""
    bucket: str = ""
    endpoint_url: Optional[str] = None
    region: str = "us-east-1"
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    prefix: str = "omem/archive/"

    @classmethod
    def from_env(cls) -> "ColdArchiveConfig":
        backend = os.getenv("OMEM_COLD_BACKEND", "local").strip().lower()
        enabled = os.getenv("OMEM_COLD_ENABLED", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        root = os.getenv(
            "OMEM_COLD_LOCAL_ROOT",
            os.path.expanduser("~/.omem/cold_archive"),
        )
        return cls(
            enabled=enabled or backend == "s3",
            backend=backend,
            local_root=root,
            bucket=os.getenv("OMEM_COLD_BUCKET", ""),
            endpoint_url=os.getenv("OMEM_COLD_ENDPOINT") or None,
            region=os.getenv("OMEM_COLD_REGION", "us-east-1"),
            access_key=os.getenv("OMEM_COLD_ACCESS_KEY") or None,
            secret_key=os.getenv("OMEM_COLD_SECRET_KEY") or None,
            prefix=os.getenv("OMEM_COLD_PREFIX", "omem/archive/"),
        )


class ColdArchive:
    """Put/get archived memory payloads (content + metadata)."""

    def __init__(self, config: Optional[ColdArchiveConfig] = None) -> None:
        self.config = config or ColdArchiveConfig.from_env()
        self._s3 = None
        if self.config.backend == "local":
            Path(self.config.local_root).mkdir(parents=True, exist_ok=True)
        elif self.config.backend == "s3" and self.config.enabled:
            self._init_s3()

    def _init_s3(self) -> None:
        try:
            import boto3

            kwargs: Dict[str, Any] = {"region_name": self.config.region}
            if self.config.endpoint_url:
                kwargs["endpoint_url"] = self.config.endpoint_url
            if self.config.access_key and self.config.secret_key:
                kwargs["aws_access_key_id"] = self.config.access_key
                kwargs["aws_secret_access_key"] = self.config.secret_key
            self._s3 = boto3.client("s3", **kwargs)
        except Exception as exc:  # pragma: no cover
            logger.warning("S3 cold archive unavailable: %s — falling back to local", exc)
            self.config.backend = "local"
            Path(self.config.local_root).mkdir(parents=True, exist_ok=True)

    def _key_for(self, memory_id: str, namespace: str = "default") -> str:
        safe_ns = namespace.replace("/", "_")
        return f"{self.config.prefix}{safe_ns}/{memory_id}.json"

    def put_payload(
        self,
        memory_id: str,
        content: str,
        *,
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store payload; returns cold_storage_key.

        Encrypts with AES-256-GCM when OMEM_ENCRYPTION_KEY is set.
        """
        key = self._key_for(memory_id, namespace)
        plaintext = json.dumps(
            {
                "memory_id": memory_id,
                "namespace": namespace,
                "content": content,
                "metadata": metadata or {},
                "archived_at": time.time(),
            }
        ).encode("utf-8")

        enc_key = _archive_encryption_key()
        body = _encrypt_payload(plaintext, enc_key) if enc_key else plaintext

        if self.config.backend == "s3" and self._s3 is not None:
            content_type = "application/octet-stream" if enc_key else "application/json"
            self._s3.put_object(
                Bucket=self.config.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        else:
            path = Path(self.config.local_root) / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        return key

    def get_payload(self, key: str) -> Optional[Dict[str, Any]]:
        """Load archived payload by key.

        Decrypts automatically when OMEM_ENCRYPTION_KEY is set and the payload
        is an encrypted envelope. Plaintext payloads are accepted transparently
        (forward compatibility when key is added after archive was written).
        """
        try:
            if self.config.backend == "s3" and self._s3 is not None:
                obj = self._s3.get_object(Bucket=self.config.bucket, Key=key)
                raw = obj["Body"].read()
            else:
                path = Path(self.config.local_root) / key
                if not path.exists():
                    # Also try key as absolute relative to root when prefix duplicated
                    path = Path(self.config.local_root) / Path(key).name
                    if not path.exists():
                        path = Path(key)
                        if not path.is_absolute():
                            path = Path(self.config.local_root) / key
                raw = path.read_bytes()

            # Attempt decryption when key is configured and payload looks encrypted
            enc_key = _archive_encryption_key()
            if enc_key:
                try:
                    envelope = json.loads(raw.decode("utf-8"))
                    if isinstance(envelope, dict) and envelope.get("enc") == "gcm":
                        raw = _decrypt_payload(raw, enc_key)
                except (json.JSONDecodeError, ValueError, KeyError):
                    pass  # Not an encrypted envelope — fall through to plaintext parse

            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            logger.warning("cold archive get failed for %s: %s", key, exc)
            return None

    def archive_memory(self, memory) -> bool:
        """Move memory content to cold storage and stub the hot record."""
        key = self.put_payload(
            memory.id,
            memory.content,
            namespace=getattr(memory, "namespace", "default"),
            metadata=getattr(memory, "metadata", None),
        )
        memory.cold_storage_key = key
        # Stub hot content to keep index small
        preview = memory.content[:120]
        memory.content = f"[archived] {preview}…" if len(memory.content) > 120 else memory.content
        memory.level = "archive"
        if hasattr(memory, "lifecycle_stage"):
            memory.lifecycle_stage = "archived"
        return True

    def hydrate_memory(self, memory) -> bool:
        """Restore full content from cold storage into ``memory.content``."""
        key = getattr(memory, "cold_storage_key", None)
        if not key:
            return False
        payload = self.get_payload(key)
        if not payload:
            return False
        memory.content = payload.get("content", memory.content)
        return True
