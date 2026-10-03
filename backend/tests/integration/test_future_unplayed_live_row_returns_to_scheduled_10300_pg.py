"""A live row whose reported start is still ahead, with no play, goes back to scheduled. #10300, real Postgres.

The unit file (``tests/test_future_unplayed_live_row_returns_to_scheduled_10300.py``)
proves the decision on every clause against a fake. What a fake cannot show is
CURRENTNESS: that the decision is taken on the row the write lands on, so a
score, clock, status or start another writer commits is never overwritten by a
demotion decided on the version before it. That is a property of Postgres row
locks, so it is proved here, with two sessions:

* a writer that committed first is seen (the read is the latest committed
  version, not an earlier one);
* a writer mid-transaction on the row is SKIPPED, not waited on and not
  overwritten — the row keeps whatever that writer commits;
* while the pass holds a row it decided on, no other writer can change it
  until the pass commits (``lock_timeout`` fires on the second session).

Each case seeds real ``events`` rows, runs the real
``_transition_event_statuses_impl`` and reads the row back.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

#: The #7617 step's disposable database, which the #8755 and #9588 steps reuse.
#: This file drops and creates only the tables it names.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres #10300 "
        "currentness contract (CI job `search-recall` provisions a disposable one)"
    ),
)

TABLES = (
    "sports",
    "teams",
    "venues",
    "events",
    "event_provider_anchors",
    "odds_snapshots",
    "win_prob_snapshots",
    "futures_markets",
    "futures_outcomes",
)

WP = {"kalshi": {"home": 0.55, "away": 0.45}}


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [Base.metadata.tables[name] for name in TABLES]
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


async def _seed(maker, cases: dict) -> dict:
    """``cases``: name → Event column overrides. Returns name → id."""
    from app.models.models import Event, Sport

    now = datetime.now(timezone.utc)
    async with maker() as session:
        liiga = Sport(key="icehockey_liiga", name="Liiga")
        session.add(liiga)
        await session.flush()
        rows = {}
        for name, overrides in cases.items():
            fields = {
                "sport_id": liiga.id,
                "home_team_name": f"{name} Ässät",
                "away_team_name": f"{name} Lukko",
                "status": "live",
                "commence_time": now + timedelta(hours=6, minutes=30),
                "commence_time_source": "odds_api",
                "win_probability_sources": WP,
            }
            fields.update(overrides)
            rows[name] = Event(**fields)
        session.add_all(list(rows.values()))
        await session.commit()
        return {name: row.id for name, row in rows.items()}


async def _run_pass(maker):
    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            yield session
            await session.commit()

    from app.tasks.espn_sync import _transition_event_statuses_impl

    with patch("app.tasks.base.get_task_session", _session):
        return await asyncio.wait_for(_transition_event_statuses_impl(), timeout=60)


async def _read(maker, ids: dict) -> dict:
    from sqlalchemy import select

    from app.models.models import Event

    async with maker() as session:
        rows = (
            await session.execute(select(Event).where(Event.id.in_(list(ids.values()))))
        ).scalars().all()
    by_id = {row.id: row for row in rows}
    return {name: by_id[event_id] for name, event_id in ids.items()}


@needs_postgres
class TestTheDecisionOnRealRows:
    async def test_eligible_refused_and_controls_in_one_pass(self, db):
        now = datetime.now(timezone.utc)
        ids = await _seed(
            db,
            {
                "specimen": {},
                "nil_nil": {"home_score": 0, "away_score": 0},
                "period": {"period": "1st"},
                "clock": {"game_clock": "12:31"},
                "completed": {"completed_at": now - timedelta(minutes=5)},
                "derived": {"commence_time_source": "kalshi_ticker"},
                "unknown": {"commence_time_source": None},
                "past": {"commence_time": now - timedelta(minutes=10)},
                # Inside the hour the existing future-settled repair leaves
                # alone (it un-settles a suspended row more than 1h ahead), so
                # only this arm could move it — and it must not.
                "suspended": {
                    "status": "suspended",
                    "commence_time": now + timedelta(minutes=30),
                },
                # The same band, live: the kill control for the one above.
                "soon": {"commence_time": now + timedelta(minutes=30)},
            },
        )
        before = await _read(db, ids)
        stats = await _run_pass(db)
        after = await _read(db, ids)

        assert after["specimen"].status == "scheduled"
        assert after["soon"].status == "scheduled"
        assert stats["unstarted_future_live"] == 2
        for name in ("nil_nil", "period", "clock", "completed", "derived",
                     "unknown", "past"):
            assert after[name].status == "live", name
        assert after["suspended"].status == "suspended"
        assert stats["held_future_live_unreported_start"] == 2

        # Only the status moved: start, provenance, probability, scores.
        s0, s1 = before["specimen"], after["specimen"]
        assert s1.commence_time == s0.commence_time
        assert s1.commence_time_source == s0.commence_time_source
        assert s1.win_probability_sources == WP
        assert (s1.home_score, s1.away_score, s1.completed_at) == (None, None, None)

    async def test_the_next_pass_does_not_promote_it_back(self, db):
        """No ping-pong with the promotion arm: the start is still ahead."""
        ids = await _seed(db, {"specimen": {}})
        await _run_pass(db)
        stats = await _run_pass(db)
        assert (await _read(db, ids))["specimen"].status == "scheduled"
        assert stats["scheduled_to_live"] == 0
        assert stats["unstarted_future_live"] == 0


@needs_postgres
class TestCurrentness:
    async def test_a_writer_that_committed_first_is_seen(self, db):
        """A score committed after the row became a candidate, before the
        pass reads it, refuses the demotion."""
        from sqlalchemy import update

        from app.models.models import Event

        ids = await _seed(db, {"scored_late": {}})
        async with db() as writer:
            await writer.execute(
                update(Event)
                .where(Event.id == ids["scored_late"])
                .values(home_score=0, away_score=0)
            )
            await writer.commit()
        stats = await _run_pass(db)
        row = (await _read(db, ids))["scored_late"]
        assert row.status == "live"
        assert stats["unstarted_future_live"] == 0

    @pytest.mark.parametrize(
        "write",
        [
            {"home_score": 1, "away_score": 0},
            {"game_clock": "19:58"},
            {"status": "completed"},
            "commence_moved_back",
        ],
        ids=["score", "clock", "status", "start-and-provenance"],
    )
    async def test_a_writer_mid_transaction_is_skipped_not_overwritten(
        self, db, write
    ):
        """The writer holds the row, uncommitted, while the pass runs. The
        pass must neither wait on it nor decide on the version beneath it;
        the eligible sibling in the same pass still goes back."""
        from sqlalchemy import update

        from app.models.models import Event

        ids = await _seed(db, {"held": {}, "sibling": {}})
        if write == "commence_moved_back":
            write = {
                "commence_time": datetime.now(timezone.utc) - timedelta(minutes=20),
                "commence_time_source": "espn",
            }
        async with db() as writer:
            await writer.execute(
                update(Event).where(Event.id == ids["held"]).values(**write)
            )
            # Row lock held, not committed, while the pass runs.
            stats = await _run_pass(db)
            await writer.commit()

        after = await _read(db, ids)
        assert after["sibling"].status == "scheduled"
        assert stats["unstarted_future_live"] == 1
        held = after["held"]
        for column, value in write.items():
            assert getattr(held, column) == value, column
        if "status" not in write:
            assert held.status == "live"

    async def test_no_writer_can_land_between_the_decision_and_the_commit(self, db):
        """The pass is paused just after deciding on the row. A second
        session's score write must not land in that window — it hits
        ``lock_timeout`` — and once the pass commits the same write lands on
        top of the committed demotion, never under it."""
        from sqlalchemy import text, update

        import app.services.event_registry as registry
        from app.models.models import Event

        ids = await _seed(db, {"specimen": {}})
        decided = asyncio.Event()
        release = asyncio.Event()
        real = registry._correction_unstarts_the_row

        def _pausing(event, new_commence, now):
            verdict = real(event, new_commence, now)
            decided.set()
            return verdict

        # The pause sits AFTER the decision and BEFORE the commit: the session
        # factory's commit waits on `release`.
        @contextlib.asynccontextmanager
        async def _session(**_kwargs):
            async with db() as session:
                yield session
                await release.wait()
                await session.commit()

        from app.tasks.espn_sync import _transition_event_statuses_impl

        with patch.object(registry, "_correction_unstarts_the_row", _pausing), patch(
            "app.tasks.base.get_task_session", _session
        ):
            pass_task = asyncio.create_task(_transition_event_statuses_impl())
            await asyncio.wait_for(decided.wait(), timeout=60)

            blocked = False
            async with db() as writer:
                await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
                try:
                    await writer.execute(
                        update(Event)
                        .where(Event.id == ids["specimen"])
                        .values(home_score=1, away_score=0)
                    )
                except Exception as exc:  # asyncpg LockNotAvailableError
                    blocked = "lock" in str(exc).lower()
                    await writer.rollback()

            release.set()
            stats = await asyncio.wait_for(pass_task, timeout=60)

        assert blocked, "a writer changed the row inside the decision window"
        assert stats["unstarted_future_live"] == 1
        assert (await _read(db, ids))["specimen"].status == "scheduled"

        async with db() as writer:
            await writer.execute(
                update(Event)
                .where(Event.id == ids["specimen"])
                .values(home_score=1, away_score=0)
            )
            await writer.commit()
        row = (await _read(db, ids))["specimen"]
        assert (row.status, row.home_score, row.away_score) == ("scheduled", 1, 0)
