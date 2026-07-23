"""The settled-events backfill must build the missing index on
``futures_outcomes(external_id)`` at task runtime.

Root cause: ``_backfill_from_settled_events`` runs several UPDATEs per page that
filter ``futures_outcomes.external_id = ANY(:tickers)``. ``futures_outcomes`` has
~1.23M rows and had NO ``external_id`` index (only PK, ``market_id``, the
composite unique ``(market_id, external_id)`` which cannot serve an
``external_id``-only lookup, and a trigram on ``name``), so each UPDATE
seq-scanned the whole table and tripped the 90s statement_timeout.

The fix builds the index at runtime (gotcha #31: NOT in an Alembic migration,
which would hang Heroku's ~5min release phase). It must:
  * be guarded by a bounded-Redis flag so it does real work at most once,
  * open a SEPARATE autocommit connection (CONCURRENTLY can't run in a txn),
  * issue the CREATE INDEX exactly once when unguarded,
  * never raise into the backfill if the DDL fails.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.kalshi import _ensure_futures_outcomes_external_id_index


def _make_engine():
    """Build a mock async engine whose connect() yields an autocommit conn."""
    conn = AsyncMock()
    conn.execution_options = AsyncMock(return_value=conn)
    conn.execute = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    engine = MagicMock()
    engine.connect = MagicMock(return_value=cm)
    engine.dispose = AsyncMock()
    return engine, conn


def test_helper_exists_and_is_async():
    assert inspect.iscoroutinefunction(_ensure_futures_outcomes_external_id_index)


async def test_flag_set_skips_all_ddl():
    """When the Redis guard flag is already set, NO DDL connection is opened."""
    rc = MagicMock()
    rc.get = MagicMock(return_value=b"1")  # flag present → skip

    engine_factory = MagicMock()  # _get_task_engine must NOT be called

    with patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
         patch("app.tasks.base._get_task_engine", engine_factory):
        await _ensure_futures_outcomes_external_id_index()

    engine_factory.assert_not_called()


async def test_flag_unset_creates_index_once_and_sets_flag():
    """Unset flag → CREATE INDEX CONCURRENTLY issued exactly once on an
    AUTOCOMMIT connection, then the guard flag is persisted."""
    rc = MagicMock()
    rc.get = MagicMock(return_value=None)  # flag absent → build
    rc.setex = MagicMock()

    engine, conn = _make_engine()

    with patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
         patch("app.tasks.base._get_task_engine", return_value=engine):
        await _ensure_futures_outcomes_external_id_index()

    # AUTOCOMMIT was requested
    conn.execution_options.assert_awaited_once_with(isolation_level="AUTOCOMMIT")

    # exactly one execute, and it is the CREATE INDEX CONCURRENTLY statement
    assert conn.execute.await_count == 1
    stmt = str(conn.execute.await_args.args[0])
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in stmt
    assert "ix_futures_outcomes_external_id" in stmt
    assert "futures_outcomes (external_id)" in stmt

    # guard flag persisted with a TTL so future runs skip
    rc.setex.assert_called_once()
    assert rc.setex.call_args.args[0] == "bainluck:idx:futures_outcomes_external_id"

    engine.dispose.assert_awaited_once()


async def test_ddl_failure_is_swallowed():
    """A failure building the index must NEVER raise into the backfill."""
    rc = MagicMock()
    rc.get = MagicMock(return_value=None)
    rc.setex = MagicMock()

    engine, conn = _make_engine()
    conn.execute = AsyncMock(side_effect=RuntimeError("boom: index build failed"))

    with patch("app.tasks.redis_state.get_redis_client", return_value=rc), \
         patch("app.tasks.base._get_task_engine", return_value=engine):
        # must not raise
        await _ensure_futures_outcomes_external_id_index()

    # flag NOT set on failure (so we retry next run), engine still disposed
    rc.setex.assert_not_called()
    engine.dispose.assert_awaited_once()


async def test_redis_unavailable_still_attempts_build():
    """If Redis is unavailable, the helper still attempts the build best-effort
    and does not raise."""
    engine, conn = _make_engine()

    with patch("app.tasks.redis_state.get_redis_client",
               side_effect=RuntimeError("redis down")), \
         patch("app.tasks.base._get_task_engine", return_value=engine):
        await _ensure_futures_outcomes_external_id_index()

    assert conn.execute.await_count == 1


def test_called_from_backfill_before_statement_timeout():
    """The helper is invoked inside the backfill, before statement_timeout is set
    (so the index build isn't killed by the 90s cap)."""
    from app.tasks.kalshi import _backfill_from_settled_events

    src = inspect.getsource(_backfill_from_settled_events)
    assert "_ensure_futures_outcomes_external_id_index()" in src
    call_idx = src.index("_ensure_futures_outcomes_external_id_index()")
    timeout_idx = src.index("SET statement_timeout")
    assert call_idx < timeout_idx, (
        "index helper must be called before statement_timeout is set"
    )
