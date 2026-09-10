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


# #3776 (ship #4456, "no query outlives its job"): the RESTING statement_timeout
# of every connection. Read from production `pg_settings` on 2026-09-09:
#
#     name              setting  source   boot_val  reset_val
#     statement_timeout  10000    session   0         0
#
# `boot_val = reset_val = 0` — the server-wide default is NO TIMEOUT, and
# `pg_db_role_setting` carries none either. The `10000` was `db-query`'s own
# session, not a global; #3776's "statement_timeout is 10s globally" was read
# through that rail and is false. So before this constant existed, an unarmed
# statement had no bound at all, and every `SET LOCAL` reverted to `reset_val`
# — unbounded — the moment its transaction ended. A worker SIGKILLed by a
# Heroku release (which happens on every master merge, D45) therefore left its
# Postgres backend grinding forever: three measured orphans on the calibration
# population CTE alone — 28h41m (7/28), 2d18h (9/5), 3h04m (9/7) — each pinning
# the global xmin horizon so autovacuum reclaimed nothing database-wide
# (`events` reached 602% dead tuples; Discover took ~8 s on Alex's phone).
#
# This is a RESTING value, not a ceiling. `statement_timeout` is USERSET, so
# every existing `SET LOCAL` still raises or lowers it freely inside its own
# transaction — the calibration main build's 1500 s arm is unaffected. What
# changes is only what an UNARMED statement gets, and what an armed one falls
# back to when its transaction ends: 30 minutes instead of forever.
#
# 30 min is the generous end of #3776's own ask, and is deliberately above the
# longest a SCHEDULED statement may legitimately run — the calibration beat's
# Celery hard limit, 1,560 s — pinned in
# `tests/test_db_resting_statement_timeout_3776.py`, which fails if this drops
# below that limit or is widened back toward "effectively forever".
#
# One path deliberately arms ABOVE it and is unaffected, because raising is what
# `SET LOCAL` is for: `calibration_published_twin_worker.ONE_OFF_MAX_TIMEOUT_MS`
# is 90 minutes, reachable only by an operator passing it on a one-off dyno
# (never from the beat or the admin endpoint). A resting bound is the value a
# statement gets when nobody has said otherwise; it is not a ceiling on what an
# operator may ask for.
DB_STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", str(30 * 60 * 1000)))


def build_connect_args(
    url: str = None,
    *,
    statement_timeout_ms: int | None = None,
    lock_timeout_ms: int | None = None,
) -> dict:
    """Driver-level connect arguments shared by EVERY engine in the app.

    One home rather than a copy per engine (ruling 005): the task engine in
    ``app/tasks/base.py`` grew as a character-for-character duplicate of the web
    engine's two lines, which is exactly how it came to be missing the
    ``statement_timeout`` above — a hardening applied to one engine and not the
    other is a hardening that is only half applied.

    ``server_settings`` is asyncpg's startup-parameter channel, so the timeout is
    set by the CONNECTION rather than by any statement: it survives commit,
    rollback and ``RESET``, which a ``SET LOCAL`` by construction does not.
    Skipped for non-asyncpg URLs (sqlite in tests), which have no such channel.

    #4482 — THE PER-JOB BUDGET USES THE SAME CHANNEL, AND HAS TO. Eight task
    call sites armed a tighter budget than the resting one with a bare ``SET``
    at the top of their session, on the assumption stated verbatim at
    ``app/tasks/kalshi.py`` — *"SET (not SET LOCAL) persists across the
    incremental commits on this one connection"*. It is one connection only by
    luck. Measured on ``sqlalchemy.pool`` + ``Session`` (three statements, a
    commit after each): ``checkedout`` drops to 0 at **every** commit, and with
    the pool's recycle age reached the next checkout is a different DBAPI
    connection — 3 distinct ids where the healthy run has 1. That new connection
    is unarmed, silently: the statement bound falls back to the resting 30
    minutes and ``lock_timeout``, which has no resting value, falls back to
    UNBOUNDED. ``pool_recycle=1800`` and ``pool_pre_ping=True`` both do this.

    ``SET LOCAL`` is not the repair — it is strictly worse at those five sites,
    because it would end at the first commit of every run rather than at an
    unlucky one. A budget that must outlive commits has to be attached to the
    connection, which is what this channel is.

    Both overrides are milliseconds and are per-ENGINE, so they only reach the
    connections that engine creates (``get_task_session`` builds a fresh one per
    call). Omitted ⇒ today's behaviour exactly: the resting statement bound and
    no lock bound.
    """
    resolved = DATABASE_URL if url is None else url
    args: dict = {}
    if "localhost" not in resolved and "127.0.0.1" not in resolved:
        # Production database - require SSL
        args["ssl"] = "require"
    if "asyncpg" in resolved:
        statement_ms = (
            DB_STATEMENT_TIMEOUT_MS
            if statement_timeout_ms is None
            else int(statement_timeout_ms)
        )
        settings = {"statement_timeout": str(statement_ms)}
        if lock_timeout_ms is not None:
            settings["lock_timeout"] = str(int(lock_timeout_ms))
        args["server_settings"] = settings
    return args


# Create async engine
# For Heroku, we need SSL for production databases
connect_args = build_connect_args()

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() == "true",
    pool_pre_ping=True,
    pool_size=10,        # 1 web dyno × 20 max = 20 connections (within Heroku 120 limit)
    max_overflow=10,
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
