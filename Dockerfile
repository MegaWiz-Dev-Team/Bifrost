# ⚡ Bifrost — Agent Runtime Engine
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Copy everything and install
COPY . .
RUN pip install --no-cache-dir -e .

RUN mkdir -p data

EXPOSE 8100

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8100/health || exit 1

CMD ["uvicorn", "bifrost.main:app", "--host", "0.0.0.0", "--port", "8100"]
