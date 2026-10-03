#!/usr/bin/env python3
"""Thin wrapper: python distribution/bakeoff.py → benchmarks.bakeoff."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
runpy.run_module("benchmarks.bakeoff", run_name="__main__")
