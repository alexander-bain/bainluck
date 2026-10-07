"""#10693 — fake task sessions for the Kalshi consumer's price pipeline.

The consumer now writes each price phase through the run's
``KalshiPricePipeline`` (``app/utils/kalshi_price_pipeline.py``), installed on
the engine its session is bound to — the run's one ``ConsumerSessions`` engine
(#2471). Every consumer test replaces ``get_task_session`` with a fake that
drops the ``engine=`` it is lent, so its sessions are bound to nothing and the
pipeline (correctly) refuses them.

``bind_sessions`` wraps such a fake: each session it yields is bound to the
engine the consumer actually lent, so the identity check, the install and the
listener's removal before that engine is disposed are all the real ones. The
fake has no asyncpg cursor, so a multi-row phase selects the ordinary path —
one ``session.execute`` per row, the statement and binds the file already
captures — on every installed SQLAlchemy/asyncpg pair. The pipelined path is
the utility's own real-Postgres tests' business, not a fake's.

The ordinary path reads the RETURNING rows, never a fake ``rowcount``: a row
the UPDATE took is a row it returned. ``returned`` builds one.

``pre_10693_write_phase`` is the consumer's per-row loop as it stood before
#10693 (``kalshi_ws.py`` at 2cafa8f56a, verbatim apart from its scaffolding) —
FROZEN. It is the comparator the consumer's output is held to; never edit it to
match a change.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from app.utils.kalshi_price_statement import (
    KALSHI_PRICE_STATEMENTS,
    kalshi_price_parameters,
)

STAMP = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


class _NoDriverConnection:
    """What a fake session lends for the pipeline's preflight: no cursor."""

    async def get_raw_connection(self):
        return SimpleNamespace(dbapi_connection=None)


async def _no_driver_connection(*_a, **_kw):
    return _NoDriverConnection()


def consumer_engine():
    """A real, never-connected AsyncEngine — for rigs that build no engine.

    The pipeline installs its listener on ``engine.sync_engine``, so a rig
    that execs the flush on its own needs a real engine to lend; nothing here
    ever connects.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine("postgresql+asyncpg://fake-kalshi-consumer/none")


def bind_session(session, engine):
    """Bind one fake session to ``engine``; leave a fake's own bind alone."""
    if getattr(session, "bind", None) is None:
        session.bind = engine
    if not hasattr(session, "connection"):
        session.connection = _no_driver_connection
    return session


def bind_sessions(factory):
    """Wrap a fake ``get_task_session`` so its sessions carry the lent engine."""

    @asynccontextmanager
    async def get_task_session(*args, engine=None, **kwargs):
        async with factory(*args, engine=engine, **kwargs) as session:
            yield bind_session(session, engine)

    return get_task_session


def is_price_write(stmt) -> bool:
    """The consumer's price UPDATE — one of the two #10689 templates."""
    return any(stmt is s for s in KALSHI_PRICE_STATEMENTS.values())


def returned(outcome_id, *, market_id=1, last_updated=STAMP, quote_moved=True):
    """One RETURNING row of the price UPDATE (``kalshi_price_statement``)."""
    return SimpleNamespace(
        id=outcome_id,
        market_id=market_id,
        last_updated=last_updated,
        quote_moved=quote_moved,
    )


async def pre_10693_write_phase(session, phase, *, stats, queue_market_change):
    """FROZEN: the pre-#10693 per-row price loop. Returns (declined, written).

    Same statement selection, binds, order, decline count, written ids and
    market invalidations as ``kalshi_ws.py`` at 2cafa8f56a.
    """
    declined = 0
    written_outcome_ids = []
    for outcome_id, (prob, yes_bid, yes_ask) in phase.items():
        tick_has_book = yes_bid is not None and yes_ask is not None
        result = await session.execute(
            KALSHI_PRICE_STATEMENTS[tick_has_book],
            kalshi_price_parameters(outcome_id, prob, yes_bid, yes_ask),
        )
        if result.rowcount == 0:
            declined += 1
        else:
            written_outcome_ids.append(outcome_id)
        for row in result.all():
            if not row.quote_moved:
                stats["quotes_unchanged"] += 1
                continue
            queue_market_change(
                session,
                market_id=row.market_id,
                source="kalshi",
                outcome_observed_at={row.id: row.last_updated},
            )
    return declined, written_outcome_ids
