FROM rust:1.75-slim-bullseye AS rust-builder

WORKDIR /build

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY rust/ ./rust/
WORKDIR /build/rust
RUN cargo build --release

FROM python:3.11-slim-bullseye

LABEL maintainer="mohitkumarrajbadi@gmail.com"
LABEL description="OMem - AI Memory Operating System"
LABEL version="1.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=rust-builder /build/rust/target/release/*.so /app/rust/
COPY omem/ ./omem/
COPY pyproject.toml ./

RUN pip install -e .

RUN mkdir -p /data && chmod 755 /data

ENV OMEM_DB_PATH=/data/brain.db \
    OMEM_LOG_LEVEL=INFO \
    OMEM_CACHE_SIZE=128000 \
    OMEM_POOL_SIZE=5

VOLUME ["/data"]

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD omem health || exit 1

CMD ["omem", "serve"]
