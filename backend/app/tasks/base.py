"""
Shared infrastructure for Celery tasks: engine, session, async helpers.
"""

import asyncio

from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.database import DATABASE_URL


def _get_task_engine():
    """Create a fresh async engine for Celery task execution.

    This creates a new engine that's bound to the current event loop,
    avoiding the 'attached to a different loop' errors when reusing
    the module-level engine across Celery task invocations.
    """
    connect_args = {}
    if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
        connect_args["ssl"] = "require"

    return create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@asynccontextmanager
async def get_task_session():
    """Create a fresh async session for Celery task execution.

    This creates a new engine and session maker bound to the current
    event loop, avoiding conflicts between Celery's forked processes
    and asyncio event loops.
    """
    engine = _get_task_engine()
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    await engine.dispose()


def run_async(coro):
    """Helper to run async code in sync context.

    Uses asyncio.run() which properly manages the event loop lifecycle,
    ensuring clean startup and shutdown of the loop and any pending tasks.
    """
    return asyncio.run(coro)
