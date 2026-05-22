"""
Database configuration and session management.
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:postgres@localhost:5432/bainluck"
)

# Convert postgres:// to postgresql+asyncpg:// if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)


# Create async engine
# For Heroku, we need SSL for production databases
connect_args = {}
if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
    # Production database - require SSL
    connect_args["ssl"] = "require"

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() == "true",
    pool_pre_ping=True,
    pool_size=20,        # Concurrent connections kept open
    max_overflow=20,     # Extra connections under burst load
    pool_recycle=1800,   # Recycle connections after 30 min (Heroku PG timeout)
    connect_args=connect_args,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


async def init_db():
    """Initialize database (create tables)."""
    async with engine.begin() as conn:
        # In production, use Alembic migrations instead
        # await conn.run_sync(Base.metadata.create_all)
        pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Read-only database session — closes without committing.

    Use for GET endpoints that only read data.  No COMMIT is issued,
    so accidental writes are silently discarded rather than persisted.

    Usage in FastAPI:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_db_rw() -> AsyncGenerator[AsyncSession, None]:
    """
    Read-write database session — commits on success, rolls back on error.

    Use for POST/PATCH/PUT/DELETE endpoints and any handler that writes
    data (session.add, execute(update/insert), etc.).

    Usage in FastAPI:
        @app.post("/items")
        async def create_item(db: AsyncSession = Depends(get_db_rw)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
