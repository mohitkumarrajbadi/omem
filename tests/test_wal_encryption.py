"""WAL encryption + _wal_remove must preserve enc1: lines."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from omem.core.utils.write_buffer import (
    WriteBuffer,
    _decrypt_wal_line,
    _encrypt_wal_line,
    _wal_encryption_key,
)
from omem.types import Memory, MemoryStatus, MemoryType


@pytest.fixture
def enc_key(monkeypatch) -> bytes:
    key = os.urandom(32)
    monkeypatch.setenv("OMEM_ENCRYPTION_KEY", key.hex())
    return key


def _mem(mid: str) -> Memory:
    return Memory(
        id=mid,
        type=MemoryType.SEMANTIC,
        content=f"content-{mid}",
        vector=np.zeros(8, dtype=np.float32),
        timestamp=1.0,
        importance=0.5,
        namespace="ns",
        source="test",
        status=MemoryStatus.ACTIVE,
    )


def test_wal_remove_keeps_encrypted_unpersisted_lines(enc_key: bytes, tmp_path: Path):
    pytest.importorskip("cryptography")
    wal = tmp_path / "test.wal"
    buf = WriteBuffer(backend=None, wal_path=str(wal))
    assert _wal_encryption_key() == enc_key

    buf._wal_append(_mem("a"))
    buf._wal_append(_mem("b"))
    raw = wal.read_text(encoding="utf-8").strip().splitlines()
    assert all(line.startswith("enc1:") for line in raw)
    assert len(raw) == 2

    buf._wal_remove({"a"})
    remaining = wal.read_text(encoding="utf-8").strip().splitlines()
    assert len(remaining) == 1
    assert remaining[0].startswith("enc1:")
    plain = _decrypt_wal_line(remaining[0], enc_key)
    assert json.loads(plain)["id"] == "b"


def test_encrypt_wal_line_roundtrip(enc_key: bytes):
    pytest.importorskip("cryptography")
    ct = _encrypt_wal_line('{"id":"x"}', enc_key)
    assert ct.startswith("enc1:")
    assert json.loads(_decrypt_wal_line(ct, enc_key))["id"] == "x"
