"""A start the only source has withdrawn does not make a game LIVE. #8755, real Postgres.

``/events/15318133`` Liberty @ Lynx read LIVE from 00:30Z 9/26 with no score,
over a FanDuel line the Odds API last listed at 02:36Z 9/24 — 46h before the
row's made-up start, while the same feed kept listing every other WNBA game.
The unit file (``tests/test_a_withdrawn_listing_is_not_a_start_8755.py``) hands
the loop its two sightings; this file lets Postgres compute them, because the
decision rides on three SQL facts a fake cannot see:

* ``GREATEST(captured_at, valid_until)`` — an unchanged line is written once and
  re-sighted into ``valid_until`` (#7617), so a row the feed still lists can
  have a ``captured_at`` days old. ``the_unmoved_line`` is that row.
* the sibling sighting is PRE-GAME only. Under the quota guard's LIVE_ONLY mode
  a sport's live games keep being seen while every pre-game row goes quiet;
  ``the_live_only_sport`` proves a live-only feed never reads a real fixture as
  withdrawn.
* the sibling read is scoped to the row's sport (``the_live_only_sport`` sits
  beside a WNBA feed that IS listing pre-game).

Each case seeds real ``odds_snapshots``, runs the real
``_transition_event_statuses_impl``, and reads the status back.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

#: The #7617 step's disposable database. This file drops and creates only the
#: tables it names, the same closure that file uses plus ``odds_snapshots``, and
#: runs in its own CI step after that one.
DB_URL = os.environ.get("DELAY_CONTRACT_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set DELAY_CONTRACT_DATABASE_URL to run the real-Postgres withdrawn-"
        "listing contract (CI job `search-recall` provisions a disposable one)"
    ),
)


async def _seed(session):
    from app.models.models import Event, OddsSnapshot, Sport

    now = datetime.now(timezone.utc)
    kickoff = now - timedelta(minutes=5)

    wnba = Sport(key="basketball_wnba", name="WNBA")
    euro = Sport(key="basketball_euroleague", name="Euroleague")
    session.add_all([wnba, euro])
    await session.flush()

    def _game(sport, name, *, commence=kickoff, status="scheduled", espn_id=None):
        return Event(
            sport_id=sport.id,
            home_team_name=f"Home {name}",
            away_team_name=f"Away {name}",
            commence_time=commence,
            commence_time_source="odds_api",
            status=status,
            espn_id=espn_id,
        )

    rows = {
        # THE SHIP: last listed 46h ago, while the WNBA feed was listing its
        # sibling pre-game a minute ago.
        "the_withdrawn_listing": _game(wnba, "Withdrawn"),
        # THE KILL CONTROL: listed a minute ago, promotes.
        "the_listed_game": _game(wnba, "Listed"),
        # An unchanged line first written 3 days ago, re-sighted a minute ago.
        "the_unmoved_line": _game(wnba, "Unmoved"),
        # Same stale sighting as the ship, but ESPN knows the row.
        "the_anchored_game": _game(wnba, "Anchored", espn_id="8755-anchored"),
        # No odds at all (a scores-path row): nothing to compare, promotes.
        "the_row_with_no_odds": _game(wnba, "NoOdds"),
        # Same stale sighting as the ship, in a sport whose only recent
        # sightings are of games already in play.
        "the_live_only_sport": _game(euro, "LiveOnly"),
        # Siblings — they are the evidence, not cases. Not past their start
        # (or already live), so the promotion never selects them.
        "wnba_pregame_sibling": _game(wnba, "Sibling", commence=now + timedelta(hours=40)),
        "euro_live_sibling": _game(
            euro, "InPlay", commence=now - timedelta(hours=1), status="live"
        ),
    }
    session.add_all(list(rows.values()))
    await session.flush()

    def _snap(name, captured_at, valid_until):
        session.add(
            OddsSnapshot(
                event_id=rows[name].id,
                bookmaker="fanduel",
                captured_at=captured_at,
                valid_until=valid_until,
                home_moneyline=-300,
                away_moneyline=235,
                home_win_probability=0.7200,
                away_win_probability=0.2800,
                reading_count=1,
            )
        )

    stale = now - timedelta(hours=46)
    _snap("the_withdrawn_listing", stale - timedelta(minutes=17), stale)
    _snap("the_listed_game", now - timedelta(hours=3), now - timedelta(minutes=1))
    _snap("the_unmoved_line", now - timedelta(days=3), now - timedelta(minutes=1))
    _snap("the_anchored_game", stale - timedelta(minutes=17), stale)
    _snap("the_live_only_sport", stale - timedelta(minutes=17), stale)
    _snap("wnba_pregame_sibling", now - timedelta(hours=6), now - timedelta(minutes=1))
    # First written after its own tip-off: a live-only line.
    _snap(
        "euro_live_sibling",
        now - timedelta(minutes=55),
        now - timedelta(seconds=30),
    )

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
class TestAWithdrawnListingIsNotAStart:
    async def test_the_withdrawn_listing_stays_scheduled(self, statuses):
        """THE SHIP. RED before #8755: promoted to live at its made-up start."""
        by_case, stats = statuses
        assert by_case["the_withdrawn_listing"] == "scheduled"
        assert stats["held_withdrawn_listing"] == 1

    async def test_the_listed_game_goes_live(self, statuses):
        """THE KILL CONTROL. A hold that refused every odds_api row passes the
        ship and fails here."""
        by_case, _ = statuses
        assert by_case["the_listed_game"] == "live"

    async def test_an_unmoved_line_is_still_a_listing(self, statuses):
        """``captured_at`` alone would read this row as three days unlisted."""
        by_case, _ = statuses
        assert by_case["the_unmoved_line"] == "live"

    async def test_an_anchored_game_goes_live(self, statuses):
        by_case, _ = statuses
        assert by_case["the_anchored_game"] == "live"

    async def test_a_row_with_no_odds_goes_live(self, statuses):
        by_case, _ = statuses
        assert by_case["the_row_with_no_odds"] == "live"

    async def test_a_live_only_feed_withdraws_nothing(self, statuses):
        """The Euroleague feed's only recent line was first written after its
        game began; that is not evidence the pre-game feed dropped this row."""
        by_case, _ = statuses
        assert by_case["the_live_only_sport"] == "live"
