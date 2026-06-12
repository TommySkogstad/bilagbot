# Pinn base-image til multi-arch manifest-digest for reproduserbare bygg.
# Oppdater bevisst: docker buildx imagetools inspect python:3.12-slim --format '{{.Manifest.Digest}}'
FROM python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94

# System dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI — pinnet eksakt versjon mot supply-chain-risiko ved auto-rebuild.
RUN npm install -g @anthropic-ai/claude-code@2.1.175

WORKDIR /app

# Install uv for fast Python package management
RUN pip install --no-cache-dir uv

# Copy project files and install dependencies
COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --no-dev --frozen

# Data directory
RUN mkdir -p /data/uploads

ENV BILAGBOT_DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

EXPOSE 8086

HEALTHCHECK --interval=10s --timeout=5s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:8086/api/health || exit 1

CMD ["uv", "run", "uvicorn", "bilagbot.web:app", "--host", "0.0.0.0", "--port", "8086"]
