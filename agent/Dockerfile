FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install deps before copying app code for better layer caching.
# Keep these in sync with pyproject.toml [project.dependencies].
COPY pyproject.toml .
RUN uv pip install --system --no-cache \
    "httpx>=0.27" \
    "pydantic>=2.9" \
    "pydantic-settings>=2.6"

COPY cct_agent/ ./cct_agent/

# Default checkpoint dir; override CCT_CHECKPOINT_PATH in compose env if needed.
RUN mkdir -p /var/lib/cct-agent

CMD ["python", "-m", "cct_agent"]
