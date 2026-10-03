#!/usr/bin/env python3
"""Fail if a documented claim is not tied to a proof that still exists.

Rules:
- Every ``claim:<id>`` in Markdown must have a ledger row.
- Every ledger surface must contain that tag.
- Proof and artifact paths must exist.
- ``artifact_contains`` must occur in the artifact file when set.
- If README.md has a ``## Benchmarks`` section, score rows with a percent or
  ``/100`` must carry a ``claim:`` tag (the enterprise README has no such
  section by design).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "distribution" / "claims_ledger.json"
TAG = re.compile(r"claim:([a-z0-9-]+)")
SCORE_ROW = re.compile(r"^\|.*(\d+(?:\.\d+)?%|/100).*\|")


def main() -> int:
    errors: list[str] = []
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    claims = ledger.get("claims") or []
    by_id = {}
    for claim in claims:
        cid = claim.get("id")
        if not cid or cid in by_id:
            errors.append(f"ledger has missing or duplicate id: {cid!r}")
            continue
        by_id[cid] = claim
        for rel in claim.get("surfaces") or []:
            path = ROOT / rel
            if not path.is_file():
                errors.append(f"{cid}: surface missing: {rel}")
                continue
            if f"claim:{cid}" not in path.read_text(encoding="utf-8"):
                errors.append(f"{cid}: {rel} has no claim:{cid} tag")
        proof = claim.get("proof") or ""
        proof_file = proof.split("::", 1)[0]
        if not proof_file or not (ROOT / proof_file).is_file():
            errors.append(f"{cid}: proof missing: {proof}")
        artifact = claim.get("artifact") or ""
        if artifact:
            art = ROOT / artifact
            if not art.is_file():
                errors.append(f"{cid}: artifact missing: {artifact}")
            else:
                needle = claim.get("artifact_contains") or ""
                if needle and needle not in art.read_text(encoding="utf-8"):
                    errors.append(f"{cid}: artifact lacks {needle!r}")

    used: set[str] = set()
    for path in [
        ROOT / "README.md",
        *sorted((ROOT / "docs").rglob("*.md")),
        *sorted((ROOT / "distribution").rglob("*.md")),
    ]:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for match in TAG.finditer(text):
            cid = match.group(1)
            used.add(cid)
            if cid not in by_id:
                errors.append(f"{path.relative_to(ROOT)}: unknown claim:{cid}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    bench = _section(readme, "## Benchmarks")
    for line in bench.splitlines():
        if SCORE_ROW.match(line) and "claim:" not in line:
            errors.append(f"README benchmark row has no claim tag: {line.strip()}")

    missing_use = sorted(set(by_id) - used)
    for cid in missing_use:
        errors.append(f"{cid}: ledger row is never tagged in docs")

    if errors:
        print(f"claims ledger: {len(errors)} error(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"claims ledger: {len(by_id)} claims ok")
    return 0


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    rest = text[start + len(heading) :]
    nxt = re.search(r"\n## ", rest)
    return rest[: nxt.start()] if nxt else rest


if __name__ == "__main__":
    sys.exit(main())
