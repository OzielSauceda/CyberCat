from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Phase 19: explicit pool config sized for laptop-scale workloads.
# - pool_size + max_overflow keeps total connections under the laptop Postgres
#   default of max_connections=100, leaving headroom for the agent + smoke tests.
# - pool_recycle proactively replaces idle connections every 30 minutes so we
#   don't accumulate stale connections that survive a Postgres restart.
# - pool_timeout caps the wait when the pool is saturated; 10s lets the
#   ingest path 503 cleanly under unexpected load instead of hanging.
# - pool_pre_ping validates a connection on checkout (cheap; covers the common
#   case where Postgres restarted while connections sat idle).
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    pool_recycle=1800,
    pool_timeout=10,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
