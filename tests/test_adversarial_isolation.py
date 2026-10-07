"""Cross-namespace recall and audit must not return the other tenant."""

from omem import OMem


def test_recall_and_audit_do_not_cross_namespaces(tmp_path, monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    brain = OMem(
        db_path=str(tmp_path / "brain.db"),
        audit_db_path=str(tmp_path / "audit.db"),
    )
    secret = "org-b-only-wire-token-88421"
    secret_id = brain.add(secret, namespace="org-b", force=True, importance=0.99)
    brain.add("org-a lunch order", namespace="org-a", force=True)
    brain.brain.write_buffer.flush()
    brain._audit.flush()

    leaked = brain.recall(secret, k=5, namespace="org-a")
    assert all(secret not in hit.content for hit in leaked)
    assert all(hit.namespace == "org-a" for hit in leaked)

    audit_a = brain._audit.get_audit_log(namespace="org-a", limit=50)
    assert all(row.get("memory_id") != secret_id for row in audit_a)
    audit_b = brain._audit.get_audit_log(namespace="org-b", limit=50)
    assert any(row.get("memory_id") == secret_id for row in audit_b)
