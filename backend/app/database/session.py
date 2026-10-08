"""Async SQLAlchemy engine for raw SQL the Supabase client can't express.

PostgREST has no way to order by pgvector distance or ts_rank, so retrieval talks
to Postgres directly over DATABASE_URL. This connection bypasses RLS, which is fine
for the shared filing corpus; chat data still goes through the Supabase client.
"""

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings


def create_engine() -> AsyncEngine:
    url = make_url(settings.database_url).set(drivername="postgresql+psycopg")
    # Small pool: the Supabase session pooler caps client connections per project.
    return create_async_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True)
