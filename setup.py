import shutil

from setuptools import setup

# Only add the Rust extension when rustc is actually present on PATH.
# This lets `pip install omem-os` succeed from the sdist on machines without
# the Rust toolchain — the package falls back to its pure-Python paths.
# Pre-built wheels on PyPI already contain the compiled extension, so most
# users never reach this sdist build path at all.
rust_extensions = []
try:
    from setuptools_rust import Binding, RustExtension

    if shutil.which("rustc") is not None:
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
