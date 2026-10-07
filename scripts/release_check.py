#!/usr/bin/env python3
"""Validate naming / versioning conventions before cutting a release.

Usage:
  python scripts/release_check.py
  python scripts/release_check.py --expect 0.0.3
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"

PACKAGE_NAME = "omem-os"
IMPORT_NAME = "omem"
TAG_RE = re.compile(r"^v?\d+\.\d+\.\d+([.-][0-9A-Za-z.-]+)?$")


def _read_pyproject() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect",
        default="",
        help="Expected release version without leading v (e.g. 0.0.3)",
    )
    args = parser.parse_args(argv)
    errors: list[str] = []

    text = _read_pyproject()
    if f'name = "{PACKAGE_NAME}"' not in text:
        errors.append(f"pyproject.toml must set project.name = {PACKAGE_NAME!r}")
    if 'name = "omem-oss"' in text or 'name = "omem"' in text:
        errors.append("pyproject.toml must not use omem / omem-oss as the PyPI name")

    fb = re.search(r'fallback_version\s*=\s*"([^"]+)"', text)
    if not fb:
        errors.append("setuptools_scm fallback_version missing")
    elif args.expect and fb.group(1) != args.expect:
        # fallback may already be next-patch after a release; only warn when expect set
        print(f"note: fallback_version={fb.group(1)} expect={args.expect}")

    if not CHANGELOG.exists():
        errors.append("CHANGELOG.md missing")
    else:
        cl = CHANGELOG.read_text(encoding="utf-8")
        if args.expect:
            heading = f"## [{args.expect}]"
            if heading not in cl and f"## [{args.expect}] " not in cl:
                # allow Unreleased targeting note
                if f"targeting {args.expect}" not in cl and heading not in cl:
                    errors.append(
                        f"CHANGELOG.md should contain a section for {args.expect} "
                        f"(or 'targeting {args.expect}' under Unreleased)"
                    )

    if args.expect and not TAG_RE.match(args.expect):
        errors.append(f"invalid --expect version: {args.expect!r}")

    # Import package name sanity (optional if not installed)
    try:
        import omem  # type: ignore

        if omem.__name__ != IMPORT_NAME:
            errors.append(f"import name is {omem.__name__!r}, expected {IMPORT_NAME!r}")
        print(f"import ok: omem.__version__={getattr(omem, '__version__', '?')}")
    except Exception as exc:
        print(f"note: could not import omem ({exc})")

    if errors:
        print("release_check FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"release_check OK (package={PACKAGE_NAME}, import={IMPORT_NAME})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
