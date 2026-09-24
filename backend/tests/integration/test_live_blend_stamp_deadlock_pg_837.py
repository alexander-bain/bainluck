"""Two venues' live stamps no longer deadlock each other. #837, real Postgres.

## what production showed

`worker-ws` runs the Kalshi and Polymarket consumers side by side, each with its
own `LiveBlendRefresher`, and each stamps a BATCH of live events'
`win_probability_sources` inside one transaction. Walked in join order, two
overlapping batches locked the same `events` rows in opposite orders. Postgres
log, 2026-09-24 19:38:07Z::

    ERROR:  deadlock detected
    DETAIL: Process 2268400 waits for ShareLock on transaction 22324307;
            blocked by process 2268393.
    CONTEXT: while updating tuple (3869,9) in relation "events"
    ERROR:  current transaction is aborted, commands ignored until end of
            transaction block

Five of those in 13 minutes on a nine-game Thursday slate. The second line is
the expensive one: the per-event `except` logged the victim and carried on, but
a deadlock aborts the whole transaction, so every later event in the batch
failed too and the commit discarded the stamps that HAD succeeded. The
Polymarket headline on five live games (the #837 specimen among them, market
62155959) waited for the next price instead of showing this one.

## what these cases prove, against real row locks

Both arms run the REAL `_refresh_batch` on one engine, concurrently. A barrier
inside `_oriented` (called just before each event's UPDATE) holds each arm after
its first stamp until the other arm has stamped its first — the exact
interleaving that deadlocks when the two orders disagree.

* ``test_both_arms_stamp_both_events`` is the ship: with one lock order the
  second arm simply waits for the first, and all four stamps land, 0 errors.
* ``test_a_deadlock_costs_one_event_not_the_batch`` is the control AND the
  savepoint's case: one arm is forced back into the opposite order, so the
  harness really does deadlock (the log says so), and the victim still commits
  the event it had already stamped. Before the savepoint it lost both.
"""

from __future__ import annotations

import asyncio
import builtins
import contextlib
import logging
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

#: A database of its own, for the reason `test_a_delay_is_not_silence_pg_7617.py`
#: gives: this file drops and creates the tables it touches. No fallback URL.
DB_URL = os.environ.get("BLEND_DEADLOCK_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set BLEND_DEADLOCK_DATABASE_URL to run the real-Postgres #837 stamp "
            "deadlock gate (CI job `search-recall` provisions a disposable one)"
        ),
    ),
]

#: How long an arm holds at the barrier for its sibling. In the ship case the
#: sibling is blocked on a row lock and never arrives, so this is also how long
#: that case takes; it only has to exceed scheduling noise.
BARRIER_S = 2.0


@pytest.fixture
async def maker():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in ("sports", "teams", "venues", "events", "futures_markets", "futures_outcomes")
    ]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(maker) -> list[int]:
    """Two live events, each linked to one Kalshi and one Polymarket market."""
    from app.models.models import Event, FuturesMarket, Sport

    async with maker() as session:
        sport = Sport(key="baseball_mlb", name="MLB")
        session.add(sport)
        await session.flush()
        ids = []
        for n in range(2):
            event = Event(
                sport_id=sport.id,
                home_team_name=f"Cubs {n}",
                away_team_name=f"Marlins {n}",
                commence_time=datetime.now(timezone.utc),
                status="live",
                win_probability_sources={},
            )
            session.add(event)
            await session.flush()
            ids.append(event.id)
        low, high = sorted(ids)
        # Insertion order is heap order on a fresh table, and the batch's join
        # has no ORDER BY: so the Kalshi arm meets HIGH first and the Polymarket
        # arm meets LOW first. That disagreement is production's, and it is
        # what makes the ship case fail if the batch walks join order.
        for source, event_id in (
            ("kalshi", high), ("kalshi", low), ("polymarket", low), ("polymarket", high),
        ):
            session.add(
                FuturesMarket(
                    sport_id=sport.id, event_id=event_id, source=source,
                    external_id=f"{source}-{event_id}", name=f"game {event_id}",
                )
            )
            await session.flush()  # one INSERT per row: insertion order is kept
        await session.commit()
    return [low, high]


async def _run_both_arms(maker, monkeypatch, *, reverse_arm=None):
    """Run the real `_refresh_batch` for both venues at once, return (stats, frames)."""
    from app.tasks import live_blend_refresh as lbr
    from app.utils import live_blend

    event_ids = await _seed(maker)
    price = {"kalshi": 0.55, "polymarket": 0.57}

    def _reading(group, home, away):
        source = group[0].market.source
        return SimpleNamespace(home_probability=price[source], eligibility=None)

    monkeypatch.setattr(live_blend, "compute_source_home_probability", _reading)

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            yield session
            await session.commit()

    monkeypatch.setattr("app.tasks.base.get_task_session", _session)

    if reverse_arm is not None:
        # The control: this one arm walks its batch in the opposite order, which
        # is what join order did to one of the two arms in production.
        def _sorted(xs, *a, **k):
            out = builtins.sorted(xs, *a, **k)
            task = asyncio.current_task()
            return out[::-1] if task and task.get_name() == reverse_arm else out

        monkeypatch.setattr(lbr, "sorted", _sorted, raising=False)

    holding = {"kalshi": asyncio.Event(), "polymarket": asyncio.Event()}
    frames = {"kalshi": [], "polymarket": []}
    arms = {}
    for source in ("kalshi", "polymarket"):
        arm = lbr.LiveBlendRefresher(source)
        calls = {"n": 0}
        other = "polymarket" if source == "kalshi" else "kalshi"

        async def _oriented(session, event_id, home_prob, _calls=calls, _me=source, _other=other):
            _calls["n"] += 1
            if _calls["n"] == 2:  # first event's UPDATE is done: its row is locked
                holding[_me].set()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(holding[_other].wait(), BARRIER_S)
            return home_prob

        async def _publish(batch, _me=source):
            frames[_me].extend(batch)

        arm._oriented = _oriented
        arm._publish = _publish
        # No chart points here: this gate is about the stamp's locks.
        now_mark = float("inf")
        arm._last_snapshot_at = {eid: now_mark for eid in event_ids}
        arms[source] = arm

    tasks = [
        asyncio.create_task(arms[s].refresh(event_ids), name=s)
        for s in ("kalshi", "polymarket")
    ]
    await asyncio.wait_for(asyncio.gather(*tasks), 30)

    from sqlalchemy import select

    from app.models.models import Event

    async with maker() as session:
        stored = dict(
            (
                await session.execute(
                    select(Event.id, Event.win_probability_sources).where(
                        Event.id.in_(event_ids)
                    )
                )
            ).all()
        )
    written = {s: dict(arms[s]._last_written_value) for s in arms}
    return event_ids, {s: {**arms[s].stats, "written": written[s]} for s in arms}, frames, stored


async def test_both_arms_stamp_both_events(maker, monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="app.tasks.live_blend_refresh")
    event_ids, stats, frames, stored = await _run_both_arms(maker, monkeypatch)

    assert not [r for r in caplog.records if "deadlock" in str(r.exc_info).lower()]
    for source in ("kalshi", "polymarket"):
        assert stats[source]["errors"] == 0, stats[source]
        assert stats[source]["stamped"] == 2, stats[source]
        assert sorted(f["event_id"] for f in frames[source]) == event_ids
    for eid in event_ids:
        assert set(stored[eid]) == {"kalshi", "polymarket"}, stored[eid]


async def test_a_deadlock_costs_one_event_not_the_batch(maker, monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="app.tasks.live_blend_refresh")
    event_ids, stats, frames, stored = await _run_both_arms(
        maker, monkeypatch, reverse_arm="kalshi"
    )

    # The control half: opposite orders really do deadlock in this harness.
    deadlocks = [r for r in caplog.records if "deadlock detected" in str(r.exc_info)]
    assert len(deadlocks) == 1, [str(r.exc_info)[-300:] for r in caplog.records]
    assert stats["kalshi"]["errors"] + stats["polymarket"]["errors"] == 1

    # The savepoint half: the victim lost ONE event and kept the other.
    victim = "kalshi" if stats["kalshi"]["errors"] else "polymarket"
    survivor = "polymarket" if victim == "kalshi" else "kalshi"
    assert stats[victim]["stamped"] == 1, stats[victim]
    assert len(stats[victim]["written"]) == 1, "a rolled-back stamp must not read as written"
    assert len(frames[victim]) == 1, "the victim must still publish the event it kept"
    assert stats[survivor]["stamped"] == 2
    stamped_keys = sum(len(stored[eid]) for eid in event_ids)
    assert stamped_keys == 3, stored
