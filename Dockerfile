# ============================================================================
# Multi-stage Dockerfile for ai-scraper
#
# Stage 1 (builder): installs dependencies into a virtual environment
# Stage 2 (runtime): copies only the venv + source — no build tools, smaller image
#
# Usage:
#   docker build -t ai-scraper .
#   docker run --rm -v $(pwd)/output:/app/output ai-scraper \
#       --start-url https://books.toscrape.com --max-pages 50 --output output/collection.jsonl
# ============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────

FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy only dependency metadata first — Docker caches this layer
# so dependencies are only reinstalled when pyproject.toml changes.
COPY pyproject.toml .

# Create a virtual environment and install dependencies.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir .

# Now copy the source code and install the package itself.
COPY . .
RUN pip install --no-cache-dir .

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────

FROM python:3.12-slim AS runtime

WORKDIR /app

# Install only the runtime C libraries (no compiler).
RUN apt-get update && \
    apt-get install -y --no-install-recommends libxml2 libxslt1.1 && \
    rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder stage.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy source code.
COPY . .

# Create output directory.
RUN mkdir -p /app/output

# Default entrypoint is the scrape_site CLI.
# Users pass flags like --start-url, --max-pages, --output as docker run args.
ENTRYPOINT ["scrape_site"]

# Default arguments (can be overridden).
CMD ["--help"]
