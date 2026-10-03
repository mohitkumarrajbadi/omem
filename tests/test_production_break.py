"""Smoke the production-break harness (tiny N, hash embeddings)."""

from benchmarks.production_break import run_suite


def test_production_break_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    report = run_suite(profile="smoke", workdir=str(tmp_path), skip_lme=True)
    assert report["profile"] == "smoke"
    assert report["failed"] == [], report
    assert report["passed"] is True
    assert "durable_restart" in report["cases"]
    assert report["cases"]["durable_restart"]["passed"] is True
