import os
import shutil

from setuptools import setup

# Suppress PyO3 python version compatibility check on Python 3.13+
os.environ["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"

# Only add the Rust extension when rustc is present AND the user did not
# opt into a pure-Python install. Pre-built wheels on PyPI already ship the
# extension; sdist installs should not fail because a half-configured Rust
# toolchain is on PATH (common pip error on Mac/Windows/Linux).
#
# Force pure Python:
#   OMEM_PURE_PYTHON=1 pip install omem-os
#   (also: OMEM_SKIP_RUST=1)
rust_extensions = []
_pure = os.environ.get("OMEM_PURE_PYTHON", "").strip().lower() in {
    "1",
    "true",
    "yes",
} or os.environ.get("OMEM_SKIP_RUST", "").strip().lower() in {"1", "true", "yes"}
try:
    from setuptools_rust import Binding, RustExtension

    if not _pure and shutil.which("rustc") is not None:
        rust_extensions = [
            RustExtension(
                "omem_rust",
                path="rust/Cargo.toml",
                binding=Binding.PyO3,
            )
        ]
except ImportError:
    pass

setup(rust_extensions=rust_extensions)
