"""#9050: retiring a silent source never erases a newer live price.

Real matcher retirement and real WS writers, on disposable PostgreSQL. The
first interleaving admits either completion (broken unlocked read) or an
observed PostgreSQL lock wait (repaired read), then lets retirement finish;
it never awaits a blocked writer while keeping its blocker paused.

Uses the #8910 fixture, which recreates ALL tables. SEARCH_TEST_DATABASE_URL
must name the disposable search-recall database, never a populated database.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text, update

from app.models.models import Event, FuturesMarket, FuturesOutcome
from app.tasks import prediction_market_matching as pmm
from app.tasks.live_blend_refresh import LiveBlendRefresher
from tests.integration.test_live_writers_observation_order_8910_pg import (
    DB_URL,
    POST_GOAL,
    _run_ws_refresh,
    _socket_flush,
    _stored,
    pg as _shared_pg_fixture,
)

pg = _shared_pg_fixture

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


async def _pm_group(Session, event_id):
    async with Session() as session:
        event = (
            await session.execute(select(Event).where(Event.id == event_id))
        ).scalar_one()
        kickoff, home, away = (
            event.commence_time,
            event.home_team_name,
            event.away_team_name,
        )
        market = FuturesMarket(
            source="polymarket",
            external_id="retirement-pm",
            name=f"{home} vs. {away}",
            event_id=event_id,
            status="open",
        )
        session.add(market)
        await session.flush()
        market_id = market.id
        for rank, name, probability in ((1, home, 0.77), (2, away, 0.23)):
            session.add(
                FuturesOutcome(
                    market_id=market_id,
                    external_id=f"retirement-pm-{rank}",
                    name=name,
                    rank=rank,
                    current_probability=probability,
                    last_updated=kickoff - timedelta(minutes=30),
                )
            )
        await session.commit()
    await _run_ws_refresh(Session, event_id, refresher=LiveBlendRefresher("polymarket"))
    assert "polymarket" in await _stored(Session, event_id), (
        "fixture must hold a retireable price"
    )
    return [
        pmm._LinkedMarketRef(
            market_id=market_id,
            source="polymarket",
            external_id="retirement-pm",
            name=f"{home} vs. {away}",
            event_id=event_id,
            event_commence_time=kickoff,
            home_team_name=home,
            away_team_name=away,
            status="open",
            event_has_result=False,
        )
    ]


async def _matcher(
    Session, refs, *, before_read=None, after_read=None, inspect_return=None
):
    """Pause only the first event-column read, after the stale group was built."""
    async with Session() as session:
        real_execute = session.execute
        fired = False

        async def execute(statement, *args, **kwargs):
            nonlocal fired
            sql = str(statement)
            event_read = (
                not fired
                and sql.lstrip().startswith("SELECT")
                and "events.win_probability_sources" in sql
            )
            if event_read:
                fired = True
                if before_read:
                    await before_read()
            result = await real_execute(statement, *args, **kwargs)
            if event_read and after_read:
                await after_read()
            return result

        session.execute = execute
        stats = defaultdict(int)
        await pmm._phase2_persist_group_reading(session, refs, stats)
        if before_read or after_read:
            assert fired, "instrument did not reach the retirement event read"
        if inspect_return:
            await inspect_return()
        return stats


async def _writer_completed_or_waiting(Session, writer):
    """An actual lock wait is the handback signal, not a sleep-based guess."""
    async with asyncio.timeout(10):
        while True:
            if writer.done():
                await writer  # expose writer errors instead of calling them completion
                return False
            async with Session() as observer:
                waiting = (
                    await observer.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                            "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                            "AND wait_event_type = 'Lock' "
                            "AND query ILIKE '%UPDATE events%' "
                            "AND query ILIKE '%win_probability_sources%')"
                        )
                    )
                ).scalar_one()
            if waiting:
                return True
            await asyncio.sleep(0.01)


async def _assert_event_unlocked(Session, event_id):
    async with Session() as contender:
        await contender.execute(
            text("SELECT id FROM events WHERE id = :id FOR UPDATE NOWAIT"),
            {"id": event_id},
        )
        await contender.rollback()


async def test_a_sibling_goal_survives_retirement(pg):
    Session, event_id = pg
    refs = await _pm_group(Session, event_id)
    seen = {}

    async def goal():
        await _socket_flush(Session, POST_GOAL)
        _, stats = await _run_ws_refresh(
            Session,
            event_id,
            refresher=LiveBlendRefresher("kalshi", stamp_lock_timeout_ms=15_000),
        )
        assert stats["stamped"] == 1, stats
        seen["goal"] = (await _stored(Session, event_id))["kalshi"]

    async def after_read():
        seen["writer"] = asyncio.create_task(goal())
        seen["waited"] = await _writer_completed_or_waiting(Session, seen["writer"])

    try:
        await _matcher(Session, refs, after_read=after_read)
    finally:
        if "writer" in seen:
            await asyncio.wait_for(seen["writer"], timeout=20)
    final = await _stored(Session, event_id)
    assert final["kalshi"] == seen["goal"], {"final": final, "goal": seen["goal"]}
    assert final["kalshi"]["value"] == POST_GOAL
    assert "polymarket" not in final
    assert seen["waited"] is True, (
        "repaired retirement must serialize the real competing stamp"
    )


async def test_a_newly_eligible_target_survives_retirement(pg):
    Session, event_id = pg
    refs = await _pm_group(Session, event_id)
    seen = {}

    async def fresh():
        async with Session() as session:
            await session.execute(
                update(FuturesOutcome)
                .where(FuturesOutcome.market_id == refs[0].market_id)
                .values(last_updated=datetime.now(timezone.utc))
            )
            await session.commit()
        _, stats = await _run_ws_refresh(
            Session,
            event_id,
            refresher=LiveBlendRefresher("polymarket"),
        )
        assert stats["stamped"] == 1, stats
        seen["target"] = (await _stored(Session, event_id))["polymarket"]
        assert seen["target"]["observed_basis"]

    await _matcher(Session, refs, before_read=fresh)
    assert (await _stored(Session, event_id)).get("polymarket") == seen["target"]


async def test_retirement_alone_removes_only_the_silent_source(pg):
    Session, event_id = pg
    refs = await _pm_group(Session, event_id)
    old = await _stored(Session, event_id)
    await _matcher(Session, refs)
    final = await _stored(Session, event_id)
    assert "polymarket" not in final
    assert final["kalshi"] == old["kalshi"]


async def test_goal_committed_before_retirement_remains_intact(pg):
    Session, event_id = pg
    refs = await _pm_group(Session, event_id)
    await _socket_flush(Session, POST_GOAL)
    _, stats = await _run_ws_refresh(Session, event_id)
    assert stats["stamped"] == 1, stats
    goal = (await _stored(Session, event_id))["kalshi"]
    await _matcher(Session, refs)
    final = await _stored(Session, event_id)
    assert "polymarket" not in final
    assert final["kalshi"] == goal


async def test_fresh_merely_unpriced_book_is_not_retired(pg):
    Session, event_id = pg
    refs = await _pm_group(Session, event_id)
    old = await _stored(Session, event_id)
    async with Session() as session:
        await session.execute(
            update(FuturesOutcome)
            .where(FuturesOutcome.market_id == refs[0].market_id)
            .values(last_updated=datetime.now(timezone.utc), current_probability=None)
        )
        await session.commit()
    await _matcher(Session, refs)
    assert (await _stored(Session, event_id))["polymarket"] == old["polymarket"]


async def test_newly_linked_admissible_market_is_not_hidden_by_old_refs(pg):
    Session, event_id = pg
    refs = await _pm_group(Session, event_id)
    old = await _stored(Session, event_id)

    async def link_new_speaker():
        async with Session() as session:
            market = FuturesMarket(
                source="polymarket",
                external_id="newly-linked-pm",
                name=refs[0].name,
                event_id=event_id,
                status="open",
            )
            session.add(market)
            await session.flush()
            for rank, name, probability in (
                (1, refs[0].home_team_name, 0.6),
                (2, refs[0].away_team_name, 0.4),
            ):
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"newly-linked-{rank}",
                        name=name,
                        rank=rank,
                        current_probability=probability,
                        last_updated=datetime.now(timezone.utc),
                    )
                )
            await session.commit()

    await _matcher(Session, refs, before_read=link_new_speaker)
    assert (await _stored(Session, event_id)).get("polymarket") == old["polymarket"]


async def test_changed_kickoff_is_rechecked_instead_of_stale_ref_lifecycle(pg):
    Session, event_id = pg
    refs = await _pm_group(Session, event_id)
    old = await _stored(Session, event_id)

    async def reschedule():
        async with Session() as session:
            await session.execute(
                update(Event)
                .where(Event.id == event_id)
                .values(
                    commence_time=datetime.now(timezone.utc) + timedelta(hours=1),
                    status="scheduled",
                )
            )
            await session.commit()

    await _matcher(Session, refs, before_read=reschedule)
    assert (await _stored(Session, event_id)).get("polymarket") == old["polymarket"]


@pytest.mark.parametrize("kind", ["fresh-unpriced", "already-absent"])
async def test_retirement_noop_does_not_carry_a_lock_into_the_next_group(pg, kind):
    Session, event_id = pg
    refs = await _pm_group(Session, event_id)
    if kind == "fresh-unpriced":
        async with Session() as session:
            await session.execute(
                update(FuturesOutcome)
                .where(FuturesOutcome.market_id == refs[0].market_id)
                .values(
                    last_updated=datetime.now(timezone.utc), current_probability=None
                )
            )
            await session.commit()
    else:
        async with Session() as session:
            await session.execute(
                text(
                    "UPDATE events SET win_probability_sources = win_probability_sources - 'polymarket' "
                    "WHERE id = :id"
                ),
                {"id": event_id},
            )
            await session.commit()
    await _matcher(
        Session,
        refs,
        inspect_return=lambda: _assert_event_unlocked(Session, event_id),
    )
