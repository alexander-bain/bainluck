"""#8910 — an older reading can no longer replace a newer one through ANY live writer.

## the ship

Right after a goal the live headline stops jumping back to the pre-goal number,
and a genuinely newer price is never held back: a newer live observation of a
source cannot be replaced by older data for it, whichever of the three writers
(the 15-minute matcher, the two-minute poll, the WebSocket lane) holds the older
copy.

## where the cases come from

The regressions are the other-writers review's counterexamples (Fable, on
`738db279ca`; independently reproduced by Codex on PG17), each forcing one
interleaving with two sessions on the REAL writer:

  CE1  matcher reads -> socket flushes + stamps the goal -> matcher resumes
  CE2  socket commits between the matcher's column read and its write
  CE3  socket reads -> poll stamps the goal under its lock -> socket resumes
  CE4  (Codex) socket re-observes its own unchanged value, then the poll stamps
       the goal, then the socket's re-stamp commits
  CE5  the socket's UPDATE WAITS on the poll's row lock while the poll commits
       the goal: the refusal must be decided at the commit, not before the wait

and the controls that must stay green:

  C1   matcher alone stamps the book
  C2   WS lane alone stamps a socket move
  C3   WS lane's unchanged re-stamp arm, poll stamps in between
  C4   (Codex's clock-domain control) reading A observed t1 and published t3;
       a genuinely newer reading B observed t2 (t1 < t2 < t3) still replaces A.
       Comparing B's observation clock with A's PUBLICATION clock refuses it.

One adaptation from the review's file, and it matters: there the socket's stamp
in CE1/CE2 was `atomic_stamp_expression` called with no observation, which the
repaired rule reads as "unknown" and does not order. Here every Kalshi stamp the
socket makes is the REAL WS lane's (`LiveBlendRefresher.refresh`), which dates
its stamp by the rows it read — the production shape. The Polymarket sibling
has no markets in this fixture, so it stays a bare stamp: its only job is to be
erasable.

Runs where `SEARCH_TEST_DATABASE_URL` is set (CI `search-recall`).
"""

from __future__ import annotations

import asyncio
import copy
import os
from collections import defaultdict
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text, update

from tests.integration.test_linked_game_price_chain_real_postgres import (
    CAPTURED,
    EXPECTED,
    LAR,
    NYG,
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
            "set SEARCH_TEST_DATABASE_URL to run the #8910 other-writers gate "
            "(CI job `search-recall` provides one)"
        ),
    ),
]

#: The book before the goal (the captured fixture's home leg) and after it.
PRE_GOAL = EXPECTED[LAR]  # 0.77
SOCKET_MOVE = 0.6  # a genuine pre-goal socket tick, so the WS lane has a write to make
POST_GOAL = 0.035
POST_GOAL_PM = 0.04


def _post_goal_book() -> list[dict]:
    """The venue's REST payload after the goal: LAR 0.02/0.05, NYG 0.95/0.98."""
    markets = copy.deepcopy(CAPTURED)
    lar, nyg = markets[LAR], markets[NYG]
    lar.update(
        yes_bid_dollars="0.0200", yes_ask_dollars="0.0500",
        no_bid_dollars="0.9500", no_ask_dollars="0.9800",
        last_price_dollars="0.0300",
    )
    nyg.update(
        yes_bid_dollars="0.9500", yes_ask_dollars="0.9800",
        no_bid_dollars="0.0200", no_ask_dollars="0.0500",
        last_price_dollars="0.9700",
    )
    return list(markets.values())


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import models as _registers_every_table  # noqa: F401
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await _run_ingest(session, _venue_event_before_the_book_opens())
        event = await _link_to_a_future_event(session)
        await session.execute(
            text("UPDATE events SET status = 'live', commence_time = :t WHERE id = :id"),
            {"t": datetime.now(timezone.utc) - timedelta(minutes=40), "id": event.id},
        )
        await session.commit()
        event_id = event.id
    # Prime: the REAL poll observes the pre-goal book once, so the outcome rows
    # hold 0.77 with a `last_updated` and Kalshi is stamped 0.77 at that
    # observation time (the state every writer starts from in production).
    await _run_poll(Session, list(CAPTURED.values()))
    primed = await _stored(Session, event_id)
    assert primed["kalshi"]["value"] == PRE_GOAL, primed
    yield Session, event_id
    await engine.dispose()


# ── the other writers' own statements ────────────────────────────────────────

async def _socket_flush(Session, home_price: float) -> None:
    """(1) the Kalshi WS consumer's `flush_prices`: the two legs re-priced,
    `last_updated = now()`, committed on its own session."""
    async with Session() as ws:
        for ticker, prob in ((LAR, home_price), (NYG, 1 - home_price)):
            await ws.execute(
                text(
                    "UPDATE futures_outcomes SET current_probability = :p, "
                    "  last_updated = now(), price_changed_at = now() "
                    " WHERE external_id = :t"
                ),
                {"p": prob, "t": ticker},
            )
        await ws.commit()


async def _socket_stamp(Session, event_id: int, *, sibling: bool = True) -> None:
    """(2) the WS lane's stamp: the REAL `LiveBlendRefresher.refresh` for Kalshi
    (its own session, after the flush committed — as in production), then a
    bare Polymarket sibling stamp (no Polymarket markets in this fixture)."""
    from app.models.models import Event
    from app.tasks.live_blend_refresh import atomic_stamp_expression

    from app.tasks.live_blend_refresh import LiveBlendRefresher

    # A stamp that meets another writer's row lock is re-queued and retried on
    # the next flush — the lane's own path, taken here the same way.
    refresher = LiveBlendRefresher("kalshi")
    for _ in range(50):
        refresher, stats = await _run_ws_refresh(
            Session, event_id, refresher=refresher,
        )
        if stats["stamped"] or not stats["lock_skipped"]:
            break
        await asyncio.sleep(0.1)
    assert stats["stamped"] == 1, ("control: the socket did not stamp", stats)
    if sibling:
        async with Session() as ws:
            await ws.execute(
                update(Event).where(Event.id == event_id)
                .values(
                    win_probability_sources=atomic_stamp_expression(
                        "polymarket", POST_GOAL_PM
                    )
                )
            )
            await ws.commit()


async def _socket_flush_and_stamp(Session, event_id: int, *, sibling: bool = True):
    await _socket_flush(Session, POST_GOAL)
    await _socket_stamp(Session, event_id, sibling=sibling)


async def _run_matcher_group(Session, event_id: int, *, at_orient=None, after_column_read=None):
    """The REAL 15-minute matcher's persist step for the (event, kalshi) group."""
    from app.tasks import prediction_market_matching as pmm

    async with Session() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT m.id, m.external_id, m.name, m.status, e.commence_time, "
                    "       e.home_team_name, e.away_team_name, e.completed_at "
                    "  FROM futures_markets m JOIN events e ON e.id = m.event_id "
                    " WHERE m.source = 'kalshi' AND m.event_id = :eid ORDER BY m.id"
                ),
                {"eid": event_id},
            )
        ).fetchall()
    group = [
        pmm._LinkedMarketRef(
            market_id=r[0], source="kalshi", external_id=r[1], name=r[2],
            event_id=event_id, event_commence_time=r[4], home_team_name=r[5],
            away_team_name=r[6], status=r[3], event_has_result=r[7] is not None,
        )
        for r in rows
    ]
    assert len(group) == 1, group  # one Kalshi container, two legs

    real_orient = pmm._orient_blend_reading

    async def _orient(session, eid, reading, source):
        if at_orient is not None:
            await at_orient()
        return await real_orient(session, eid, reading, source)

    stats = defaultdict(int)
    async with Session() as session:
        if after_column_read is not None:
            real_execute = session.execute
            state = {"armed": False}

            async def _execute(stmt, *a, **kw):
                if state["armed"]:
                    state["armed"] = False
                    await after_column_read()
                result = await real_execute(stmt, *a, **kw)
                s = str(stmt)
                if s.lstrip().upper().startswith("SELECT") and "win_probability_sources" in s:
                    state["armed"] = True
                return result

            session.execute = _execute
        with patch.object(pmm, "_orient_blend_reading", _orient):
            spoke = await pmm._phase2_persist_group_reading(session, group, stats)
    return spoke, stats


async def _run_poll(Session, raw_markets):
    """The REAL two-minute poll (PR #8929/#8962 tree), venue stubbed."""
    from app.services.kalshi_api import KalshiAPIService
    from app.tasks import prediction_market_matching as pmm

    service = KalshiAPIService(api_key="test-key")
    service.get_markets = AsyncMock(return_value=(raw_markets, None))
    service.close = AsyncMock()

    async with Session() as poll_session:
        @asynccontextmanager
        async def _session_cm(**_budget):
            yield poll_session

        with ExitStack() as es:
            es.enter_context(patch("app.services.kalshi_api.KalshiAPIService", return_value=service))
            es.enter_context(patch.object(pmm, "get_task_session", _session_cm))
            return await pmm._poll_live_prediction_market_prices()


async def _run_ws_refresh(
    Session, event_id: int, *, at_orient=None, refresher=None, frames=None,
):
    """The REAL WS fast lane: `LiveBlendRefresher.refresh` on its own session.

    ``frames`` collects what the lane would have published to the phones."""
    import app.tasks.base as base
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    refresher = refresher or LiveBlendRefresher("kalshi")
    real_oriented = LiveBlendRefresher._oriented

    async def _oriented(self, session, eid, home_prob, *, reading=None):
        if at_orient is not None:
            await at_orient()
        return await real_oriented(self, session, eid, home_prob, reading=reading)

    async def _publish(self, pending):
        if frames is not None:
            frames.extend(pending)

    async with Session() as ws_session:
        @asynccontextmanager
        async def _session_cm(**_budget):
            yield ws_session
            await ws_session.commit()

        with ExitStack() as es:
            es.enter_context(patch.object(base, "get_task_session", _session_cm))
            es.enter_context(patch.object(LiveBlendRefresher, "_oriented", _oriented))
            es.enter_context(patch.object(LiveBlendRefresher, "_publish", _publish))
            stats = await refresher.refresh([event_id])
    return refresher, dict(stats)


async def _ws_points(Session, event_id: int) -> list[float]:
    """The WS lane's chart points for Kalshi, oldest first."""
    async with Session() as s:
        return [
            float(p) for (p,) in (
                await s.execute(
                    text(
                        "SELECT home_win_probability FROM win_prob_snapshots "
                        " WHERE event_id = :id AND source = 'kalshi' "
                        "   AND game_state->>'poll_type' = 'ws_fast_lane' "
                        " ORDER BY id"
                    ),
                    {"id": event_id},
                )
            ).all()
        ]


async def _stored(Session, event_id: int) -> dict:
    async with Session() as s:
        return (
            await s.execute(
                text("SELECT win_probability_sources FROM events WHERE id = :id"),
                {"id": event_id},
            )
        ).scalar() or {}


def _clock(entry: dict) -> datetime:
    return datetime.fromisoformat(entry["updated_at"])


# ── CE1 / CE2 — the 15-minute matcher ────────────────────────────────────────

class TestMatcherReadsThenSocketCommitsThenMatcherResumes:
    async def test_ce1_pre_goal_price_and_older_clock_replace_the_socket_stamp(self, pg):
        Session, event_id = pg

        async def at_orient():
            # The matcher has loaded the pre-goal outcome rows (its reading is
            # dated by their `last_updated`). The goal arrives on the socket:
            # rows re-priced, Kalshi stamped at the database clock.
            await _socket_flush_and_stamp(Session, event_id)
            seen["socket"] = (await _stored(Session, event_id))["kalshi"]

        seen: dict = {}
        await _run_matcher_group(Session, event_id, at_orient=at_orient)
        stored = await _stored(Session, event_id)
        kalshi = stored["kalshi"]

        assert kalshi["value"] == POST_GOAL, (
            f"the matcher put the pre-goal price back over the socket's newer "
            f"observation, and dated it {kalshi['updated_at']} — "
            f"{(_clock(seen['socket']) - _clock(kalshi)).total_seconds():.3f}s OLDER "
            f"than the socket's {seen['socket']['updated_at']}: {kalshi}"
        )
        # (the clock on the surviving entry must not have moved backwards)
        assert stored.get("polymarket", {}).get("value") == POST_GOAL_PM, stored

    async def test_ce2_sibling_stamped_in_the_gap_is_erased(self, pg):
        Session, event_id = pg
        seen: dict = {}

        async def after_column_read():
            # Between the matcher's read of the column and its whole-column
            # write: the socket commits Kalshi AND Polymarket. Under a locked
            # read the socket's write must WAIT for the matcher's commit (as
            # the poll's gate already makes it); unlocked, it lands in the gap
            # and the matcher's copy erases it.
            seen["ws"] = asyncio.create_task(_socket_flush_and_stamp(Session, event_id))
            done, _ = await asyncio.wait({seen["ws"]}, timeout=1.5)
            seen["ws_committed_inside_the_matcher"] = bool(done)

        await _run_matcher_group(Session, event_id, after_column_read=after_column_read)
        assert "ws" in seen, "control: the matcher never read the column"
        await asyncio.wait_for(seen["ws"], timeout=10)
        stored = await _stored(Session, event_id)

        assert seen["ws_committed_inside_the_matcher"] is False, (
            "the socket's stamp committed between the matcher's column read and "
            f"its whole-column write; what the database kept: {stored}"
        )
        assert stored.get("polymarket", {}).get("value") == POST_GOAL_PM, (
            f"a sibling stamped in the gap was erased by the matcher's "
            f"whole-column write: {stored}"
        )
        assert stored["kalshi"]["value"] == POST_GOAL, stored


class TestMatcherControl:
    async def test_c1_with_no_socket_write_the_matcher_stamps_the_book(self, pg):
        Session, event_id = pg
        spoke, stats = await _run_matcher_group(Session, event_id)
        assert spoke is not None
        stored = await _stored(Session, event_id)
        assert stored["kalshi"]["value"] == PRE_GOAL, stored
        assert "updated_at" in stored["kalshi"]


# ── CE3 / CE4 — the WebSocket fast lane ──────────────────────────────────────

class TestSocketReadsThenPollCommitsThenSocketResumes:
    async def test_ce3_socket_writes_the_older_price_with_the_newest_clock(self, pg):
        Session, event_id = pg
        seen = {}
        # A real socket tick before the goal (0.77 -> 0.60): rows re-priced and
        # committed; the refresh that follows is the writer under test.
        await _socket_flush(Session, SOCKET_MOVE)

        async def at_orient():
            # The WS batch has loaded the 0.60 rows. The two-minute poll
            # re-observes the venue AFTER the goal, re-prices the rows, compares
            # under FOR UPDATE (nothing newer stored) and stamps 0.035.
            seen["poll"] = await _run_poll(Session, _post_goal_book())
            seen["after_poll"] = await _stored(Session, event_id)

        frames: list = []
        refresher, stats = await _run_ws_refresh(
            Session, event_id, at_orient=at_orient, frames=frames,
        )
        assert seen["after_poll"]["kalshi"]["value"] == POST_GOAL, (
            "control: the poll did not stamp the post-goal price", seen,
        )
        poll_clock = _clock(seen["after_poll"]["kalshi"])
        stored = await _stored(Session, event_id)
        kalshi = stored["kalshi"]

        assert kalshi["value"] == POST_GOAL, (
            f"the socket wrote its pre-goal reading over the poll's newer "
            f"observation — and dated it {kalshi['updated_at']} (poll stamp "
            f"{poll_clock.isoformat()}), so every clock guard downstream now "
            f"trusts the older price: {kalshi}"
        )
        # A refusal is a refusal everywhere: no chart point, no frame to the
        # phones, and the lane does not believe the value is stored.
        assert stats["stale_readings_refused"] == 1, stats
        assert stats["stamped"] == 0, stats
        assert frames == [], f"the refused reading was published: {frames}"
        assert await _ws_points(Session, event_id) == [], "a refused chart point"
        assert event_id not in refresher._last_written_value, (
            "the refused value was recorded as written, so the next flush would "
            "skip the event as unchanged"
        )


class TestSocketStampWaitsOnThePollsLock:
    async def test_ce5_the_decision_is_taken_at_the_commit_not_before_the_wait(
        self, pg
    ):
        """CE5. The socket's stamping UPDATE is ISSUED while the poll holds the
        event row with the post-goal stamp written but not committed. It waits;
        the poll commits; the UPDATE must now refuse. A comparison made in a
        read before the UPDATE — or one that did not re-evaluate against the
        committed row — writes the pre-goal price here."""
        from app.models.models import Event
        from app.tasks.live_blend_refresh import (
            LiveBlendRefresher, atomic_stamp_expression,
        )

        Session, event_id = pg
        await _socket_flush(Session, SOCKET_MOVE)
        seen: dict = {}

        seen["poll_wrote"] = asyncio.Event()

        async def poll_commits_once_the_socket_waits(poll):
            # Commit only once the socket's STAMP (the guarded UPDATE) is
            # blocked on this row — proves the refusal is decided after the wait.
            # Started before the poll writes, so it runs (and closes the poll's
            # session) even if the write itself fails.
            try:
                await asyncio.wait_for(seen["poll_wrote"].wait(), timeout=10)
            except asyncio.TimeoutError:
                await poll.rollback()
                await poll.close()
                return
            async with Session() as probe:
                for _ in range(200):
                    waiting = (
                        await probe.execute(
                            text(
                                "SELECT query FROM pg_stat_activity "
                                " WHERE wait_event_type = 'Lock' "
                                "   AND query ILIKE '%%UPDATE events%%' "
                                "   AND query ILIKE '%%jsonb_each%%'"
                            )
                        )
                    ).scalars().all()
                    if waiting:
                        seen["socket_waited"] = True
                        break
                    await asyncio.sleep(0.02)
            await poll.commit()
            await poll.close()

        async def at_orient():
            # The socket has loaded its 0.60 rows. The poll re-observes the
            # venue after the goal and stamps under the event row — and is
            # still holding that row when the socket reaches its UPDATE.
            poll = Session()
            seen["poll"] = asyncio.create_task(
                poll_commits_once_the_socket_waits(poll)
            )
            observed = (
                await poll.execute(
                    text(
                        "UPDATE futures_outcomes SET current_probability = "
                        "  CASE WHEN external_id = :lar THEN :p ELSE 1 - :p END, "
                        "  last_updated = clock_timestamp() "
                        " WHERE external_id IN (:lar, :nyg) "
                        "RETURNING id, extract(epoch FROM last_updated)"
                    ),
                    {"lar": LAR, "nyg": NYG, "p": POST_GOAL},
                )
            ).all()
            await poll.execute(
                update(Event).where(Event.id == event_id).values(
                    win_probability_sources=atomic_stamp_expression(
                        "kalshi", POST_GOAL,
                        observed_basis={str(i): float(t) for i, t in observed},
                    )
                )
            )
            seen["poll_wrote"].set()

        refresher = LiveBlendRefresher("kalshi", stamp_lock_timeout_ms=10_000)
        frames: list = []
        try:
            refresher, stats = await _run_ws_refresh(
                Session, event_id, at_orient=at_orient, refresher=refresher,
                frames=frames,
            )
        finally:
            # Always let the poll finish and close, pass or fail: a session left
            # open in a transaction blocks the next case's schema reset forever.
            if "poll" in seen:
                await asyncio.wait_for(seen["poll"], timeout=15)
        stored = await _stored(Session, event_id)

        assert seen.get("socket_waited") is True, (
            "control: the socket's guarded UPDATE never waited on the poll's "
            "row lock, so this case did not test the commit-time decision"
        )
        assert stored["kalshi"]["value"] == POST_GOAL, (
            f"the socket's UPDATE waited on the poll, then wrote the pre-goal "
            f"price over the post-goal stamp the poll committed: {stored}"
        )
        assert stats["stale_readings_refused"] == 1, stats
        assert frames == [], frames
        assert await _ws_points(Session, event_id) == []



class TestSocketUnchangedRestampArm:
    async def test_c3_an_unobserved_restamp_is_still_skipped(self, pg):
        """CONTROL. The lane has NOT re-read its rows since its own stamp, so
        #5661's rule skips the re-stamp before it gets anywhere near the poll's
        newer stamp. (This does not make the arm safe in general — CE4.)"""
        from app.tasks.live_blend_refresh import LiveBlendRefresher

        Session, event_id = pg
        refresher = LiveBlendRefresher(
            "kalshi", min_refresh_interval_s=0, unchanged_restamp_interval_s=0,
        )
        await _socket_flush(Session, SOCKET_MOVE)
        refresher, first = await _run_ws_refresh(Session, event_id, refresher=refresher)
        assert first["stamped"] == 1, first
        seen = {}

        async def at_orient():
            seen["poll"] = await _run_poll(Session, _post_goal_book())

        refresher, stats = await _run_ws_refresh(
            Session, event_id, at_orient=at_orient, refresher=refresher,
        )
        stored = await _stored(Session, event_id)
        assert stats["unobserved_skipped"] == 1, stats
        assert stored["kalshi"]["value"] == POST_GOAL, stored

    async def test_ce4_a_reobserved_unchanged_value_cannot_restamp_over_the_poll(
        self, pg
    ):
        """CE4, Codex's counterexample to the review's "the re-stamp arm cannot
        regress": the socket re-observes its OWN unchanged 0.60 (so #5661 lets
        the re-stamp through), then the poll stamps the goal before the
        re-stamp commits. Unguarded, 0.60 goes back over 0.035."""
        from app.tasks.live_blend_refresh import LiveBlendRefresher

        Session, event_id = pg
        refresher = LiveBlendRefresher(
            "kalshi", min_refresh_interval_s=0, unchanged_restamp_interval_s=0,
        )
        await _socket_flush(Session, SOCKET_MOVE)
        refresher, first = await _run_ws_refresh(Session, event_id, refresher=refresher)
        assert first["stamped"] == 1, first
        # The same price observed again after the lane's own stamp.
        await _socket_flush(Session, SOCKET_MOVE)
        seen = {}

        async def at_orient():
            seen["poll"] = await _run_poll(Session, _post_goal_book())
            seen["after_poll"] = await _stored(Session, event_id)

        frames: list = []
        refresher, stats = await _run_ws_refresh(
            Session, event_id, at_orient=at_orient, refresher=refresher,
            frames=frames,
        )
        stored = await _stored(Session, event_id)
        assert seen["after_poll"]["kalshi"]["value"] == POST_GOAL, seen
        assert stats["unobserved_skipped"] == 0, (
            "control: the re-observation did not reach the re-stamp arm", stats,
        )
        assert stored["kalshi"]["value"] == POST_GOAL, {
            "stored": stored, "after_poll": seen["after_poll"], "stats": stats,
        }
        assert stats["stale_readings_refused"] == 1, stats
        assert frames == [], frames


class TestANewerObservationPublishedLaterStillWins:
    async def test_c4_newer_b_beats_older_a_published_after_b_was_observed(self, pg):
        """CONTROL — Codex's clock-domain case. The reference prototype failed
        it by comparing B's observation clock (t2) with A's PUBLICATION clock
        (t3). B saw the rows after A did; B must replace A."""
        Session, event_id = pg

        async def observed_clock():
            async with Session() as session:
                return (await session.execute(text(
                    "SELECT min(last_updated) FROM futures_outcomes"
                ))).scalar_one()

        # A sees 60% first. Its real writer is paused after loading the rows.
        await _socket_flush(Session, SOCKET_MOVE)
        t1 = await observed_clock()
        seen = {}

        async def newer_quote_arrives_before_a_publishes():
            await _socket_flush(Session, 0.40)
            seen["t2"] = await observed_clock()

        _, a_stats = await _run_ws_refresh(
            Session, event_id, at_orient=newer_quote_arrives_before_a_publishes,
        )
        after_a = await _stored(Session, event_id)
        assert after_a["kalshi"]["value"] == SOCKET_MOVE, (after_a, a_stats)
        t3 = _clock(after_a["kalshi"])
        async with Session() as session:
            t4 = (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()

        _, b_stats = await _run_ws_refresh(Session, event_id)
        final = await _stored(Session, event_id)
        evidence = {"t1": t1, "t2": seen["t2"], "t3": t3, "t4": t4,
                    "after_a": after_a, "final": final, "b_stats": b_stats}
        assert t1 < seen["t2"] < t3 < t4, evidence
        assert final["kalshi"]["value"] == 0.40, evidence
        assert b_stats.get("stale_readings_refused", 0) == 0, evidence


class TestSocketControl:
    async def test_c2_with_no_poll_write_the_socket_stamps_the_book(self, pg):
        Session, event_id = pg
        await _socket_flush(Session, SOCKET_MOVE)
        _r, stats = await _run_ws_refresh(Session, event_id)
        assert stats["stamped"] == 1, stats
        stored = await _stored(Session, event_id)
        assert stored["kalshi"]["value"] == SOCKET_MOVE, stored
        assert "updated_at" in stored["kalshi"]


async def _bind_a_future_basis(Session, event_id: int, bound: str) -> None:
    """Store Kalshi as {value: bound, observed_value: bound, observed_basis:
    every Kalshi row seen far in the future} — a basis that refuses every
    reading IF it is trusted."""
    async with Session() as s:
        await s.execute(
            text(
                "UPDATE events SET win_probability_sources = "
                "  win_probability_sources || jsonb_build_object('kalshi', "
                "    jsonb_build_object('value', CAST(:b AS jsonb), "
                "      'observed_value', CAST(:b AS jsonb), "
                "      'observed_basis', (SELECT jsonb_object_agg(o.id::text, 9999999999) "
                "         FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
                "        WHERE m.source = 'kalshi' AND m.event_id = :id))) "
                " WHERE id = :id"
            ),
            {"b": bound, "id": event_id},
        )
        await s.commit()


class TestTheStampExpressionInSql:
    async def test_an_undated_stamp_removes_the_previous_basis(self, pg):
        """`atomic_stamp_expression`'s strip, on the server: a value written
        with no basis must not inherit the last reading's observation."""
        from app.models.models import Event
        from app.tasks.live_blend_refresh import atomic_stamp_expression
        from app.utils.aggregation import OBSERVED_BASIS_KEY, OBSERVED_VALUE_KEY

        Session, event_id = pg
        async with Session() as s:
            for basis in ({"2": 1.0}, None):
                await s.execute(
                    update(Event).where(Event.id == event_id).values(
                        win_probability_sources=atomic_stamp_expression(
                            "kalshi", 0.5, observed_basis=basis,
                        )
                    )
                )
            await s.commit()
        kalshi = (await _stored(Session, event_id))["kalshi"]
        assert kalshi["value"] == 0.5
        assert OBSERVED_BASIS_KEY not in kalshi and OBSERVED_VALUE_KEY not in kalshi, kalshi

    @pytest.mark.parametrize(
        "malformed",
        ['"garbage"', '{"2": "2026-09-26T19:51:00Z"}', '[1, 2]', 'null'],
        ids=["string", "clock-as-text", "array", "json-null"],
    )
    async def test_a_malformed_stored_basis_neither_aborts_nor_refuses(
        self, pg, malformed
    ):
        """The guard never casts a stored clock that is not a JSON number."""
        Session, event_id = pg
        async with Session() as s:
            await s.execute(
                text(
                    "UPDATE events SET win_probability_sources = jsonb_set("
                    "  jsonb_set(win_probability_sources, '{kalshi,observed_basis}', "
                    "            CAST(:m AS jsonb)), "
                    "  '{kalshi,observed_value}', win_probability_sources->'kalshi'->'value') "
                    " WHERE id = :id"
                ),
                {"m": malformed, "id": event_id},
            )
            await s.commit()
        await _socket_flush(Session, SOCKET_MOVE)
        _r, stats = await _run_ws_refresh(Session, event_id)
        assert stats["errors"] == 0 and stats["stamped"] == 1, stats
        assert (await _stored(Session, event_id))["kalshi"]["value"] == SOCKET_MOVE

    @pytest.mark.parametrize(
        "bound", ['"0.6"', "true", "null"], ids=["string", "bool", "json-null"],
    )
    async def test_a_non_numeric_binding_is_not_trusted_as_in_python(
        self, pg, bound
    ):
        """Parity with `stored_observation_basis` (Codex, on 30162c4dd6): a
        binding is only believed on a NUMERIC value. JSON equality alone would
        trust `"0.6" = "0.6"` and refuse the write that repairs the entry."""
        from app.utils.aggregation import stored_observation_basis

        Session, event_id = pg
        await _bind_a_future_basis(Session, event_id, bound)
        assert stored_observation_basis(await _stored(Session, event_id), "kalshi") is None
        await _socket_flush(Session, SOCKET_MOVE)
        _r, stats = await _run_ws_refresh(Session, event_id)
        assert stats["stale_readings_refused"] == 0 and stats["stamped"] == 1, stats
        assert (await _stored(Session, event_id))["kalshi"]["value"] == SOCKET_MOVE

    async def test_control_a_numeric_binding_with_a_later_basis_refuses(self, pg):
        """The same rig with a numeric binding: the basis IS trusted, so the
        parity cases above pass for the binding's type and nothing else."""
        Session, event_id = pg
        await _bind_a_future_basis(Session, event_id, "0.6")
        await _socket_flush(Session, SOCKET_MOVE)
        _r, stats = await _run_ws_refresh(Session, event_id)
        assert stats["stale_readings_refused"] == 1, stats
        assert (await _stored(Session, event_id))["kalshi"]["value"] == 0.6
