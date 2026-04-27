FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install deps before copying app code for better layer caching.
# Keep these in sync with pyproject.toml [project.dependencies].
COPY pyproject.toml .
RUN uv pip install --system --no-cache \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.30.0" \
    "pydantic>=2.9.0" \
    "pydantic-settings>=2.6.0" \
    "sqlalchemy[asyncio]>=2.0" \
    "asyncpg>=0.29" \
    "alembic>=1.13" \
    "redis[asyncio]>=5.0" \
    "pyyaml>=6.0" \
    "pytest>=8.0" \
    "pytest-asyncio>=0.24" \
    "httpx>=0.27" \
    "bcrypt>=4.0" \
    "itsdangerous>=2.0" \
    "authlib>=1.3"

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY alembic/ ./alembic/
COPY tests/ ./tests/
COPY alembic.ini .
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8000
CMD ["./start.sh"]
