"""Short chaos loop: kill a writer, require the flushed marker, fail closed on a bad row."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from omem import OMem
from omem.backends.sqlite import CorruptMemoryError, SQLiteBackend

ROOT = Path(__file__).resolve().parents[1]


def test_sigkill_keeps_flushed_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    out = tmp_path / "rate.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "chaos_resume.py"),
            "--iterations",
            "1",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["iterations"] == 1
    assert report["failures"] == 0
    assert report["failure_rate"] == 0.0


def test_corrupt_row_fails_closed_and_does_not_leak(tmp_path, monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    db = tmp_path / "brain.db"
    brain = OMem(db_path=str(db))
    secret = "tenant-b-secret-do-not-leak"
    public = "tenant-a-public-note"
    bad_id = brain.add("tenant-a-will-be-corrupt", namespace="org-a", force=True)
    good_id = brain.add(secret, namespace="org-b", force=True)
    brain.add(public, namespace="org-a", force=True)
    brain.brain.write_buffer.flush()

    conn = sqlite3.connect(db)
    conn.execute("UPDATE memories SET metadata = ? WHERE id = ?", ("{", bad_id))
    conn.commit()
    conn.close()

    backend = SQLiteBackend(str(db))
    with pytest.raises(CorruptMemoryError):
        backend.load(bad_id)
    loaded = backend.all()
    ids = {mem.id for mem in loaded}
    assert bad_id not in ids
    assert good_id in ids
    assert all(secret not in mem.content or mem.namespace == "org-b" for mem in loaded)

    reopened = OMem(db_path=str(db))
    leaked = reopened.recall(secret, k=5, namespace="org-a")
    assert all(secret not in hit.content for hit in leaked)
    kept = reopened.recall(secret, k=5, namespace="org-b")
    assert any(secret in hit.content for hit in kept)
