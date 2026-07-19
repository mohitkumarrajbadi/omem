"""End-to-end field-level encryption: ciphertext at rest + plaintext roundtrip."""

from __future__ import annotations

import os
import sqlite3

import pytest

cryptography = pytest.importorskip("cryptography")

from omem import AgentState, OMem  # noqa: E402
from omem.governance.encryption import EncryptionManager  # noqa: E402


@pytest.fixture
def aes_key_hex() -> str:
    return os.urandom(32).hex()


class TestEncryptionManagerUnit:
    def test_roundtrip(self, aes_key_hex):
        enc = EncryptionManager(EncryptionManager.parse_key_material(aes_key_hex))
        cipher = enc.encrypt("secret fact")
        assert cipher.startswith(EncryptionManager.PREFIX)
        assert "secret fact" not in cipher
        assert enc.decrypt(cipher) == "secret fact"

    def test_plaintext_passthrough(self, aes_key_hex):
        enc = EncryptionManager(EncryptionManager.parse_key_material(aes_key_hex))
        assert enc.decrypt("legacy plaintext") == "legacy plaintext"

    def test_from_env(self, aes_key_hex, monkeypatch):
        monkeypatch.setenv("OMEM_ENCRYPTION_KEY", aes_key_hex)
        monkeypatch.delenv("OMEM_ENCRYPTION_DISABLED", raising=False)
        enc = EncryptionManager.from_env()
        assert enc is not None
        assert enc.decrypt(enc.encrypt("x")) == "x"


class TestSQLiteCiphertextAtRest:
    def test_content_encrypted_on_disk(self, aes_key_hex, tmp_path):
        db = str(tmp_path / "enc.db")
        secret = "PCI cardholder preference: never store PAN in memory"
        m = OMem(backend="sqlite", db_path=db, encryption_key=aes_key_hex)
        mid = m.add(secret, metadata={"tier": "restricted"})
        m.brain.write_buffer.flush()

        # Raw SQLite must show ENC:v1: prefix, not the plaintext secret
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT content, metadata FROM memories WHERE id = ?", (mid,)
        ).fetchone()
        conn.close()
        assert row is not None
        content_raw, meta_raw = row
        assert content_raw.startswith(EncryptionManager.PREFIX)
        assert secret not in content_raw
        assert meta_raw.startswith(EncryptionManager.PREFIX)
        assert "restricted" not in meta_raw

        # API roundtrip returns plaintext
        loaded = m.brain.backend.load(mid)
        assert loaded is not None
        assert loaded.content == secret
        assert loaded.metadata.get("tier") == "restricted"

    def test_search_works_when_encrypted(self, aes_key_hex, tmp_path):
        db = str(tmp_path / "search.db")
        m = OMem(backend="sqlite", db_path=db, encryption_key=aes_key_hex)
        m.add("Alpha prefers PostgreSQL for multi-tenant isolation")
        m.add("Beta uses SQLite for local agents")
        m.brain.write_buffer.flush()
        hits = m.brain.backend.search("PostgreSQL", limit=5)
        assert len(hits) == 1
        assert "PostgreSQL" in hits[0].content


class TestAgentStateEncryption:
    def test_remember_recall_with_key(self, aes_key_hex, tmp_path):
        db = str(tmp_path / "agent.db")
        agent = AgentState(
            session_id="enc-agent",
            backend="sqlite",
            db_path=db,
            encryption_key=aes_key_hex,
        )
        mid = agent.remember("Auditor asked: prove what the agent knew at T0")
        agent._omem.brain.write_buffer.flush()
        hits = agent.recall("auditor prove", k=3)
        assert any("Auditor asked" in h.content for h in hits)

        # Ciphertext still on disk
        conn = sqlite3.connect(db)
        raw = conn.execute(
            "SELECT content FROM memories WHERE id = ?", (mid,)
        ).fetchone()
        conn.close()
        assert raw is not None
        assert raw[0].startswith(EncryptionManager.PREFIX)

    def test_config_encryption_key(self, aes_key_hex, tmp_path):
        from omem.agent_config import AgentConfig

        cfg = AgentConfig(
            session_id="cfg-enc",
            backend="sqlite",
            db_path=str(tmp_path / "cfg.db"),
            encryption_key=aes_key_hex,
        )
        assert "encryption_key" not in cfg.to_dict()
        agent = AgentState(config=cfg)
        agent.remember("Governed memory fact")
        assert agent.recall("Governed", k=1)
