#!/usr/bin/env python3
"""Kill a writer mid-SQLite write, then check the checkpoint marker survived.

Prints a failure rate. Exit 0 only when every iteration recovered the marker.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MARKER = "chaos-checkpoint-marker"


def child(db_path: str) -> None:
    os.environ.setdefault("OMEM_EMBEDDER", "hash")
    from omem import OMem

    brain = OMem(db_path=db_path)
    brain.add(MARKER, namespace="chaos", force=True, importance=0.9)
    brain.brain.write_buffer.flush()
    Path(db_path + ".ready").write_text("ok", encoding="utf-8")
    i = 0
    while True:
        brain.add(f"inflight-{i}-" + ("x" * 128), namespace="chaos", force=True)
        if i % 20 == 0:
            brain.brain.write_buffer.flush()
        i += 1


def run_once(root: Path) -> None:
    db = root / "brain.db"
    ready = Path(str(db) + ".ready")
    env = os.environ.copy()
    env["OMEM_EMBEDDER"] = "hash"
    env["OMEM_WRITE_BUFFER_WAL_PATH"] = str(root / "write_buffer.wal")
    env["OMEM_AUDIT_DB_PATH"] = str(root / "audit.db")
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--child", str(db)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        if ready.exists():
            break
        if proc.poll() is not None:
            raise RuntimeError(f"writer exited {proc.returncode} before the marker was durable")
        time.sleep(0.02)
    else:
        proc.kill()
        proc.wait(timeout=5)
        raise RuntimeError("writer never flushed the checkpoint marker")

    time.sleep(0.05)
    proc.kill()
    proc.wait(timeout=5)

    os.environ["OMEM_EMBEDDER"] = "hash"
    from omem import OMem

    brain = OMem(db_path=str(db))
    try:
        hits = brain.recall(MARKER, k=5, namespace="chaos")
    finally:
        close = getattr(brain, "close", None)
        if close:
            close()
    if not any(MARKER in (hit.content or "") for hit in hits):
        raise RuntimeError("checkpoint marker missing after SIGKILL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", default="", help=argparse.SUPPRESS)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    if args.child:
        child(args.child)
        return 0

    failures = 0
    errors: list[str] = []
    for i in range(args.iterations):
        with tempfile.TemporaryDirectory(prefix="omem-chaos-") as tmp:
            try:
                run_once(Path(tmp))
            except Exception as exc:
                failures += 1
                if len(errors) < 5:
                    errors.append(f"{i}: {exc}")
    rate = (failures / args.iterations) if args.iterations else 0.0
    report = {
        "iterations": args.iterations,
        "failures": failures,
        "failure_rate": rate,
        "errors": errors,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
