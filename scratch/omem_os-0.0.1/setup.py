from setuptools import setup
from setuptools_rust import Binding, RustExtension

setup(
    rust_extensions=[
        RustExtension("omem_rust", path="rust/Cargo.toml", binding=Binding.PyO3)

    ],
)
