"""
Shared infrastructure for Celery tasks: engine, session, async helpers.
"""

import asyncio
import logging

from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services.database import DATABASE_URL

logger = logging.getLogger(__name__)


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
        pool_size=3,
        max_overflow=2,
        pool_recycle=1800,
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
    # engine.dispose() MUST run on every exit path — normal, exception, or the
    # caller breaking early (GeneratorExit). Previously it sat after the
    # `async with session_maker()` block with no finally, so any exception
    # propagating out of the yielded body (e.g. a query hitting its
    # statement_timeout in _compute_fair_fight_comparison) skipped it and leaked
    # the freshly-created engine's connection pool → GC-reaped "non-checked-in
    # connection" alerts (#1162, ~113/24h). The outer try/finally closes that hole.
    try:
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    finally:
        await engine.dispose()


async def tag_task_session(
    db,
    *,
    task: str,
    run_generation=None,
    owner: str | None = None,
    build: str | None = None,
) -> dict:
    """Make this backend say who it is, and report back who it turned out to be.

    Queue 300B Item 1. Two calibration backends have been pinning xmin on
    production since 2026-08-02 with an EMPTY ``application_name``, so the only
    evidence of ownership available to C127's containment contract was client
    address and age — the two forms of evidence it explicitly refuses as
    authority. Every future scheduled calibration session announces itself
    instead.

    Three deliberate choices:

    * **``set_config(..., is_local => true)``, not ``SET application_name``.**
      Transaction-scoped, so the tag evaporates at the next COMMIT or ROLLBACK.
      That is what makes it impossible for a tag to outlive its work and be
      inherited by whatever borrows the pooled connection next. A session-level
      ``SET`` would need a matching RESET on every exit path, and the exit path
      that matters here is SIGKILL, which does not run any.
    * **Bind parameter, not interpolation.** The tag can never alter what the
      statement means. ``set_config`` takes a value argument, so there is no
      reason to build this string into SQL, and one very good reason not to.
    * **Best effort.** A backend that cannot be tagged still has to run. The
      failure is logged and the caller learns the tag did not stick, rather than
      losing an hourly build over a label.

    Returns ``{"application_name", "backend_pid", "applied"}`` so the caller can
    put the *server-side* identity in its durable ledger. That is the join that
    turns a future ``pg_stat_activity`` row into a named run.
    """
    from app.utils.db_session_identity import build_session_tag, current_build_id

    tag = build_session_tag(
        task=task,
        build=build if build is not None else current_build_id(),
        run_generation=run_generation,
        owner=owner,
    )
    try:
        row = (
            await db.execute(
                text(
                    "SELECT set_config('application_name', :tag, true) AS name, "
                    "pg_backend_pid() AS pid"
                ),
                {"tag": tag},
            )
        ).first()
        return {
            "application_name": row.name if row is not None else tag,
            "backend_pid": row.pid if row is not None else None,
            "applied": True,
        }
    except Exception as exc:  # noqa: BLE001 — a label must never fail a build
        logger.warning("could not tag task session for %s: %s", task, exc)
        return {"application_name": tag, "backend_pid": None, "applied": False}


def run_async(coro):
    """Helper to run async code in sync context.

    Uses asyncio.run() which properly manages the event loop lifecycle,
    ensuring clean startup and shutdown of the loop and any pending tasks.
    """
    return asyncio.run(coro)
