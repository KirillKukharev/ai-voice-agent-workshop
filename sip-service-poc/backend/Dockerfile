FROM python:3.12-slim

WORKDIR /app

# Install uv and dependencies (copy pyproject first for cache)
COPY backend/pyproject.toml ./
RUN set -eux; \
    apt-get update && apt-get install -y --no-install-recommends curl gcc && rm -rf /var/lib/apt/lists/*; \
    curl -LsSf https://astral.sh/uv/install.sh | sh; \
    export PATH="/root/.local/bin:$PATH"; \
    uv sync --no-dev --extra main --no-install-project; \
    apt-get purge -y curl 2>/dev/null || true

# Copy application code
COPY backend/__init__.py backend/main.py backend/schemas.py backend/events.py backend/websocket_manager.py ./

ENV PATH="/root/.local/bin:$PATH"
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
