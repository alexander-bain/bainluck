"""Overlapping CLOB writes/stamps reuse connections without raising the cap."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError
from sqlalchemy.pool import QueuePool

from app.tasks import base
from app.tasks.ws_consumer_sessions import ConsumerSessions


@pytest.mark.parametrize("label", ["kalshi", "polymarket"])
@pytest.mark.parametrize("concurrent", [4, 5])
async def test_consecutive_overlapping_batches_reuse_every_connection(
    monkeypatch, label, concurrent,
):
    """Exercise SQLAlchemy's real pool with the consumer's factory settings.

    SQLite avoids network I/O; overflow return/checkout behavior is QueuePool's
    and is the same for asyncpg. This proves connection reuse, not a production
    time saving.
    """
    captured = {}
    opened = []
    closed = []

    def create_local_engine(_url, **settings):
        from sqlalchemy import event

        captured.update(settings)
        sync_engine = create_engine(
            "sqlite://",
            poolclass=QueuePool,
            pool_size=settings["pool_size"],
            max_overflow=settings["max_overflow"],
            pool_pre_ping=settings["pool_pre_ping"],
            pool_recycle=settings["pool_recycle"],
            pool_timeout=0.01,
        )
        event.listen(sync_engine, "connect", lambda db, _record: opened.append(db))
        event.listen(sync_engine, "close", lambda db, _record: closed.append(db))

        async def dispose():
            sync_engine.dispose()

        return SimpleNamespace(sync_engine=sync_engine, dispose=dispose)

    monkeypatch.setattr(base, "create_async_engine", create_local_engine)
    scope = ConsumerSessions(label)
    engine = scope._engine_here()
    checked_out = []
    try:
        for _ in range(2):
            checked_out = [engine.sync_engine.connect() for _ in range(concurrent)]
            for connection in checked_out:
                assert connection.exec_driver_sql("SELECT 1").scalar() == 1
                connection.close()
            checked_out = []

        assert len(opened) == concurrent
        assert closed == []
        # More retention must not admit a sixth concurrent database operation.
        checked_out = [engine.sync_engine.connect() for _ in range(5)]
        with pytest.raises(TimeoutError):
            engine.sync_engine.connect()
        assert len(opened) == 5
        assert captured["pool_pre_ping"] is True
        assert captured["pool_recycle"] == 1800
    finally:
        for connection in checked_out:
            connection.close()
        await scope.aclose()
    assert len(closed) == len(opened) == 5
