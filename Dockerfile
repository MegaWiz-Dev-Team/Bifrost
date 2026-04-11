# ⚡ Bifrost — Agent Runtime Engine (Native Rust)

# -------------------------
# Build Stage
# -------------------------
FROM rust:latest as builder

# Install required build dependencies
RUN apt-get update && apt-get install -y pkg-config libssl-dev gcc libc6-dev curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Mimir bridge workspace so Bifrost can build the relative dependency inherited workspace
COPY Mimir/ro-ai-bridge ./Mimir/ro-ai-bridge

# Copy Bifrost manifests
COPY Bifrost/Cargo.toml Bifrost/Cargo.lock ./Bifrost/

# Create dummy main.rs to cache dependency build
RUN mkdir -p Bifrost/src \
    && echo "fn main() {println!(\"Dummy cache target\");}" > Bifrost/src/main.rs

WORKDIR /app/Bifrost
RUN cargo build --release \
    && rm -rf src/main.rs target/release/deps/bifrost*

# Return to root and copy the actual source code
WORKDIR /app
COPY Bifrost/src ./Bifrost/src

# Build the real application binary
WORKDIR /app/Bifrost
RUN cargo build --release

# -------------------------
# Runtime Stage
# -------------------------
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates curl libssl3 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the compiled binary from the builder stage
COPY --from=builder /app/Bifrost/target/release/bifrost /app/bifrost

# Ensure data directory exists for Memvid
RUN mkdir -p /app/data

EXPOSE 8100

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8100/healthz || exit 1

CMD ["/app/bifrost"]
