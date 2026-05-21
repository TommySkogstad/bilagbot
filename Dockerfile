FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Claude CLI
RUN npm install -g @anthropic-ai/claude-code

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
