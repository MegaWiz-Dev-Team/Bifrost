# Multi-stage build for Bifrost RL Governance Backend
# Build requires mimir-core-ai local dependency
# Invoke from parent directory: docker build -f Bifrost/Dockerfile -t bifrost:latest .

# Stage 1: Build Rust binary (latest stable required for all dependency versions)
FROM rust:latest AS builder

WORKDIR /build

# Copy workspace structure (Bifrost + Mimir)
COPY Bifrost ./Bifrost
COPY Mimir ./Mimir

WORKDIR /build/Bifrost

# Build with SQLX_OFFLINE to skip database validation at build time
ENV SQLX_OFFLINE=true
ENV RUST_LOG=info
ENV CARGO_NET_OFFLINE=false

# Build release binary
RUN cargo build --package bifrost --release 2>&1 | tail -50

# Stage 1b: Frontend assets (React dashboard)
# Copy pre-built assets from Bifrost/dashboard/dist
FROM node:lts-slim AS frontend
COPY Bifrost/dashboard/dist /dashboard-dist

# Stage 2: Runtime image
FROM debian:bookworm-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy binary from builder
COPY --from=builder /build/Bifrost/target/release/bifrost /app/bifrost

# Copy frontend assets from frontend stage
COPY --from=frontend /dashboard-dist /app/public

# Set environment
ENV RUST_LOG=info
ENV LISTEN_ADDR=0.0.0.0:8100

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1

# Run bifrost
CMD ["/app/bifrost"]
