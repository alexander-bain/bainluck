"""A venue stamp does not start a match our StatPal schedule puts later. #9588, real Postgres.

``/events/15320754`` Bublik / Shang v Cerundolo / Rinderknech read LIVE from
05:00Z 9/29, Kalshi's expiry stamp, while its own StatPal anchor
(``tennis:2638141``) had it at the next day's Beijing session. The unit file
(``tests/test_a_venue_stamp_does_not_start_a_later_session_9588.py``) hands the
loop its anchor rows. This file lets Postgres answer the read, because it rides
on SQL a fake cannot see: ``claim_context->>'statpal_start_time'`` out of JSONB,
``ANY(:event_ids)`` bound by asyncpg, and the anchor's ``source_id`` matched to
the row's current fixture.

Each case seeds real ``events`` and ``event_provider_anchors`` rows, runs the
real ``_transition_event_statuses_impl``, and reads the status back.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

#: The #7617 step's disposable database, the same one the #8755 step reuses.
#: This file drops and creates only the tables it names, after that step.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres later-session "
        "contract (CI job `search-recall` provisions a disposable one)"
    ),
)


async def _seed(session):
    from app.models.models import Event, EventProviderAnchor, Sport

    now = datetime.now(timezone.utc)
    tennis = Sport(key="tennis_atp", name="ATP")
    session.add(tennis)
    await session.flush()

    def _match(name, *, commence, source="kalshi", status="scheduled", fixture):
        return Event(
            sport_id=tennis.id,
            home_team_name=f"{name} A / B",
            away_team_name=f"{name} C / D",
            commence_time=commence,
            commence_time_source=source,
            status=status,
            statpal_fixture_id=fixture,
        )

    rows = {
        # THE SHIP: Kalshi stamp an hour ago, StatPal session tomorrow.
        "the_held_match": _match(
            "Held", commence=now - timedelta(hours=1), fixture="958801"
        ),
        # THE REPAIR: already promoted, 3h past its stamp (inside the staleness
        # arm's read), StatPal session still ahead.
        "the_promoted_match": _match(
            "Promoted",
            commence=now - timedelta(hours=3),
            status="live",
            fixture="958802",
        ),
        # THE KILL CONTROL: StatPal's session has begun, so the clock runs.
        "the_session_reached": _match(
            "Reached", commence=now - timedelta(hours=2), fixture="958803"
        ),
        # The anchor names a fixture the row no longer carries: says nothing.
        "the_stale_fixture": _match(
            "Stale", commence=now - timedelta(hours=1), fixture="958804"
        ),
        # The census counterexample: a reported start is not overruled.
        "the_reported_start": _match(
            "Reported",
            commence=now - timedelta(hours=1),
            source="odds_api",
            fixture="958805",
        ),
    }
    session.add_all(list(rows.values()))
    await session.flush()

    def _anchor(name, source_id, start):
        session.add(
            EventProviderAnchor(
                event_id=rows[name].id,
                source="statpal",
                source_id=source_id,
                id_kind="game",
                claim_context={
                    "written_by": "link_tennis_statpal_fixtures",
                    "statpal_start_time": start.isoformat(),
                },
            )
        )

    tomorrow = now + timedelta(hours=17)
    _anchor("the_held_match", "tennis:958801", tomorrow)
    _anchor("the_promoted_match", "tennis:958802", tomorrow)
    _anchor("the_session_reached", "tennis:958803", now - timedelta(minutes=10))
    _anchor("the_stale_fixture", "tennis:111111", tomorrow)
    _anchor("the_reported_start", "tennis:958805", tomorrow)

    await session.commit()
    return {name: row.id for name, row in rows.items()}


@pytest.fixture
async def seeded():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    wanted = [
        Base.metadata.tables[name]
        for name in (
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
    ]

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
        await conn.run_sync(Base.metadata.create_all, tables=wanted)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    yield maker, ids

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=wanted, checkfirst=True)
    await engine.dispose()


@pytest.fixture
async def statuses(seeded):
    import contextlib
    from unittest.mock import patch

    from sqlalchemy import select

    from app.models.models import Event

    maker, ids = seeded

    @contextlib.asynccontextmanager
    async def _session(**_kwargs):
        async with maker() as session:
            yield session
            await session.commit()

    from app.tasks.espn_sync import _transition_event_statuses_impl

    with patch("app.tasks.base.get_task_session", _session):
        stats = await _transition_event_statuses_impl()

    async with maker() as session:
        rows = (
            await session.execute(
                select(Event.id, Event.status).where(Event.id.in_(list(ids.values())))
            )
        ).all()

    by_id = {row.id: row.status for row in rows}
    return {name: by_id[event_id] for name, event_id in ids.items()}, stats


@needs_postgres
class TestAVenueStampDoesNotStartALaterSession:
    async def test_the_held_match_stays_scheduled(self, statuses):
        """THE SHIP. RED before #9588: promoted on Kalshi's stamp."""
        by_case, stats = statuses
        assert by_case["the_held_match"] == "scheduled"
        assert stats["held_statpal_later_session"] == 1

    async def test_the_promoted_match_goes_back(self, statuses):
        by_case, stats = statuses
        assert by_case["the_promoted_match"] == "scheduled"
        assert stats["demoted_statpal_later_session"] == 1

    async def test_a_reached_session_goes_live(self, statuses):
        """THE KILL CONTROL. A hold that refused every anchored Kalshi row
        passes the ship and fails here."""
        by_case, _ = statuses
        assert by_case["the_session_reached"] == "live"

    async def test_an_anchor_for_another_fixture_says_nothing(self, statuses):
        by_case, _ = statuses
        assert by_case["the_stale_fixture"] == "live"

    async def test_a_reported_start_is_not_overruled(self, statuses):
        by_case, _ = statuses
        assert by_case["the_reported_start"] == "live"
