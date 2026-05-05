FROM python:3.11-slim

WORKDIR /app

# Install uv via pip (avoids ghcr.io pull)
RUN pip install --no-cache-dir uv

# Copy dependency files first (layer cache)
COPY pyproject.toml uv.lock ./

# Install production deps only (no dev group)
RUN uv sync --frozen --no-dev

# Copy application source
COPY app/ ./app/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
