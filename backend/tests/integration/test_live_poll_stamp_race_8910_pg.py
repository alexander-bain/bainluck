"""#8910 — a newer WebSocket stamp survives the two-minute poll, on real Postgres.

## the ship

Right after a goal the live headline stops jumping back to the pre-goal number:
a newer live observation of a source cannot be replaced by older data for it.

## what this file answers

CERT-3585 BLOCKED `ab20943d`: the poll compared its reading against an UNLOCKED
read, wrote the chart point, then wrote the whole column back. A WebSocket stamp
committed between that read and that write was never compared, and the write
erased it (and any sibling source stamped in the gap). The required guard is
this interleaving, forced on real Postgres with two sessions:

    poll reads -> WebSocket commits a newer stamp -> poll resumes

The poll here is the REAL beat (`_poll_live_prediction_market_prices`) with only
the venue stubbed; the WebSocket write is the WS lane's own statement
(`atomic_stamp_expression`, the server-side merge `live_blend_refresh` sends).

## the arms

* race: the poll pauses right after its compared read, just before its chart
  point; a second session sends the WS stamp for Kalshi AND Polymarket. With the
  row lock that write WAITS for the poll's commit, so the poll writes no chart
  point after a newer stamp committed, and the newer Kalshi value and the
  Polymarket sibling both survive. Without the lock (ab20943d) the WS write
  commits inside the pause and the poll erases both;
* refused: the WS stamp commits after the pass fetched but before its read — the
  poll's reading is the older observation, so neither hero stamp nor chart point
  is written (ab20943d's own arm, here on real Postgres).

Runs where `SEARCH_TEST_DATABASE_URL` is set (CI `search-recall`).
"""

from __future__ import annotations

import asyncio
import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text, update

from tests.integration.test_linked_game_price_chain_real_postgres import (
    CAPTURED,
    EXPECTED,
    LAR,
    _link_to_a_future_event,
    _run_ingest,
    _venue_event_before_the_book_opens,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #8910 stamp-race gate "
            "(CI job `search-recall` provides one)"
        ),
    ),
]

#: The socket's post-goal Kalshi price and a Polymarket sibling, both distinct
#: from the poll's reading (the captured book's home leg, 0.77).
WS_KALSHI = 0.035
WS_POLYMARKET = 0.04
#: How long the paused poll gives the socket's write to commit. The locked beat
#: holds it for the whole window; the unlocked one lets it through in ms.
WINDOW_S = 1.5


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await _run_ingest(session, _venue_event_before_the_book_opens())
        event = await _link_to_a_future_event(session)
        # In play: inside the two-minute poll's live scope.
        await session.execute(
            text(
                "UPDATE events SET status = 'live', commence_time = :t "
                " WHERE id = :id"
            ),
            {"t": datetime.now(timezone.utc) - timedelta(minutes=40), "id": event.id},
        )
        await session.commit()
        event_id = event.id

    yield Session, event_id
    await engine.dispose()


async def _ws_stamp(Session, event_id: int) -> None:
    """The WS lane's write, from its own session: Kalshi, then Polymarket."""
    from app.models.models import Event
    from app.tasks.live_blend_refresh import atomic_stamp_expression

    async with Session() as ws:
        for source, value in (("kalshi", WS_KALSHI), ("polymarket", WS_POLYMARKET)):
            await ws.execute(
                update(Event)
                .where(Event.id == event_id)
                .values(
                    win_probability_sources=atomic_stamp_expression(source, value)
                )
            )
        await ws.commit()


async def _run_poll(Session, *, before_read=None, at_chart_point=None):
    """The REAL beat on its own session; only the venue is stubbed."""
    from app.services.kalshi_api import KalshiAPIService
    from app.tasks import prediction_market_matching as pmm
    from app.tasks import snapshots as _snapshots

    # The real service (its parser reads the venue's current dialect); only
    # the network call is stubbed, returning the venue's captured bytes.
    service = KalshiAPIService(api_key="test-key")
    service.get_markets = AsyncMock(return_value=(list(CAPTURED.values()), None))
    service.close = AsyncMock()

    real_point = _snapshots._create_or_update_win_prob_snapshot
    real_orient = pmm._orient_blend_reading

    async def _point(session, event_id, source, *a, **kw):
        if at_chart_point is not None and source == "kalshi":
            await at_chart_point()
        return await real_point(session, event_id, source, *a, **kw)

    async def _orient(session, event_id, reading, source):
        if before_read is not None and source == "kalshi":
            await before_read()
        return await real_orient(session, event_id, reading, source)

    async with Session() as poll_session:

        @asynccontextmanager
        async def _session_cm(**_budget):
            yield poll_session

        with ExitStack() as es:
            es.enter_context(
                patch("app.services.kalshi_api.KalshiAPIService", return_value=service)
            )
            es.enter_context(
                patch.object(pmm, "get_task_session", _session_cm)
            )
            es.enter_context(
                patch.object(_snapshots, "_create_or_update_win_prob_snapshot", _point)
            )
            es.enter_context(patch.object(pmm, "_orient_blend_reading", _orient))
            stats = await pmm._poll_live_prediction_market_prices()
    return stats


async def _stored(Session, event_id: int) -> dict:
    async with Session() as s:
        return (
            await s.execute(
                text("SELECT win_probability_sources FROM events WHERE id = :id"),
                {"id": event_id},
            )
        ).scalar() or {}


async def _kalshi_points(Session, event_id: int) -> list[float]:
    async with Session() as s:
        rows = await s.execute(
            text(
                "SELECT home_win_probability FROM win_prob_snapshots "
                " WHERE event_id = :id AND source = 'kalshi' ORDER BY id"
            ),
            {"id": event_id},
        )
        return [float(r[0]) for r in rows.fetchall()]


class TestPollReadThenSocketCommitThenPollResumes:
    async def test_the_newer_stamp_and_its_sibling_survive_and_no_stale_point(
        self, pg
    ):
        Session, event_id = pg
        seen: dict = {}

        async def at_chart_point():
            # The poll has made its comparison and holds its reading. Now the
            # socket writes a newer price for this source (and a sibling).
            seen["ws"] = asyncio.create_task(_ws_stamp(Session, event_id))
            done, _ = await asyncio.wait({seen["ws"]}, timeout=WINDOW_S)
            seen["ws_committed_inside_the_poll"] = bool(done)

        stats = await _run_poll(Session, at_chart_point=at_chart_point)
        await asyncio.wait_for(seen["ws"], timeout=10)

        assert "ws" in seen, "control: the poll never reached its chart point"
        assert stats["stale_readings_refused"] == 0, stats
        assert seen["ws_committed_inside_the_poll"] is False, (
            "the socket's newer stamp committed between the poll's comparison and "
            "its write: the poll then writes a chart point older than the stored "
            "stamp and erases the stamp with its whole-column copy"
        )
        stored = await _stored(Session, event_id)
        assert stored["kalshi"]["value"] == WS_KALSHI, (
            f"the newer Kalshi observation was replaced by the poll's: {stored}"
        )
        assert stored.get("polymarket", {}).get("value") == WS_POLYMARKET, (
            f"a sibling stamped in the gap was erased: {stored}"
        )
        # The poll's point exists and was committed BEFORE the socket's stamp
        # (the socket waited on it), so it was the newest observation when it
        # was written.
        assert await _kalshi_points(Session, event_id) == [EXPECTED[LAR]]


class TestSocketCommitBeforeTheReadIsRefused:
    async def test_the_older_reading_writes_neither_stamp_nor_point(self, pg):
        Session, event_id = pg

        async def before_read():
            await _ws_stamp(Session, event_id)

        stats = await _run_poll(Session, before_read=before_read)

        assert stats["stale_readings_refused"] == 1, stats
        stored = await _stored(Session, event_id)
        assert stored["kalshi"]["value"] == WS_KALSHI, stored
        assert stored["polymarket"]["value"] == WS_POLYMARKET, stored
        assert await _kalshi_points(Session, event_id) == []

    async def test_control_with_no_socket_write_the_poll_stamps(self, pg):
        Session, event_id = pg

        stats = await _run_poll(Session)

        assert stats["stale_readings_refused"] == 0, stats
        stored = await _stored(Session, event_id)
        assert stored["kalshi"]["value"] == EXPECTED[LAR], stored
        assert await _kalshi_points(Session, event_id) == [EXPECTED[LAR]]
