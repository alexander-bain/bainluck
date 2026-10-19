"""#11295 — the list cards' projected pair equals the event page's, on real Postgres.

`/api/events/{id}` serves `current_odds.projected_home_score / _away_score` from
the latest row per sportsbook. `/api/feed` and `/api/leagues/{sport}` now read the
same rows for their game cards in one batched statement
(`app/utils/card_projected_pair.py`). This file seeds one game, asks the real
detail route for its pair through the real app, and asserts the feed and league
attach steps put the SAME pair on their cards.

The seed has to be able to tell the right answer from the plausible wrong ones:

* deep history on one book whose OLDER rows project a different score, so a read
  of every row, or of the oldest, gives a different mean;
* a book with mirrored moneylines, which detail leaves out of the consensus;
* a book with a moneyline but no spread/total, which contributes no pair.

`test_the_seed_can_tell_the_wrong_answers_apart` asserts each of those changes the
answer, so a green run here is not vacuous.

The feed read carries its own server-side bound (lane1b's C1 on c3fe360688):
SAVEPOINT → ``SET LOCAL statement_timeout`` → read → ROLLBACK TO SAVEPOINT. On
real Postgres this file proves the session's own ``statement_timeout`` is the
same after the read as before it, and that a read outlasting the bound is
cancelled by the SERVER and leaves the session usable.

Opt-in on ``SEARCH_TEST_DATABASE_URL`` like its neighbours, and named by a step
in the ``database-integration`` CI job (a ``*_pg.py`` nobody names runs nowhere).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.models import Event, OddsSnapshot, Sport
from app.utils.odds_math import aggregate_bookmaker_odds, project_scores

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres card projected "
            "pair gate (the database-integration CI job provides one)"
        ),
    ),
]

# Kickoff far enough ahead that the detail route's own clock sees a scheduled
# game; every capture is an offset from a fixed anchor (gotcha #44).
_KICKOFF = datetime(2099, 1, 1, 20, 25, tzinfo=timezone.utc)
_SPORT_KEY = "americanfootball_nfl"
GAME = 911_295_01
FINAL = 911_295_02

#: (book, home prob, spread, total, minutes before kickoff). Latest per book wins.
_ROWS = [
    # deep history: the old rows project 27.0 / 24.0, the latest 30.0 / 22.0
    ("draftkings", 0.62, -3.0, 51.0, -600),
    ("draftkings", 0.64, -3.0, 51.0, -300),
    ("draftkings", 0.72, -8.0, 52.0, -30),
    ("fanduel", 0.71, -7.0, 51.0, -25),
    ("betmgm", 0.73, -8.0, 53.0, -20),
    ("caesars", 0.72, -7.5, 52.0, -15),
    # mirrored moneyline AND mirrored spread: detail leaves it out
    ("bovada", 0.28, 7.5, 52.0, -12),
    # a moneyline only: in the probability count, not in the pair
    ("pinnacle", 0.72, None, None, -10),
]


def _proj(spread, total):
    if spread is None or total is None:
        return None, None
    return project_scores(spread, total)


@pytest.fixture
async def pg_engine():
    """Function-scoped: `pytest.ini` leaves the fixture loop scope unset."""
    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(sync, checkfirst=True)
        )
    yield engine
    async with engine.begin() as conn:
        await conn.execute(
            delete(OddsSnapshot).where(OddsSnapshot.event_id.in_([GAME, FINAL]))
        )
        await conn.execute(delete(Event).where(Event.id.in_([GAME, FINAL])))
    await engine.dispose()


@pytest.fixture
def no_redis(monkeypatch):
    """Every Redis touch on the detail route degrades to a miss."""
    from app.routes import events as events_route
    from app.tasks import redis_state

    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: None)
    events_route._event_detail_cache.clear()
    yield
    events_route._event_detail_cache.clear()


@pytest.fixture
async def client(pg_engine, monkeypatch):
    """httpx over the REAL app, `get_db` handing out sessions on the test DB."""
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _real_get_db():
        async with AsyncSession(pg_engine, expire_on_commit=False) as session:
            yield session

    async def _no_user():
        return None

    app.dependency_overrides[get_db] = _real_get_db
    app.dependency_overrides[get_db_rw] = _real_get_db
    app.dependency_overrides[get_optional_user] = _no_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()


async def _seed(pg_engine):
    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        sport_id = (
            await s.execute(select(Sport.id).where(Sport.key == _SPORT_KEY))
        ).scalar_one_or_none()
        if sport_id is None:
            sport = Sport(key=_SPORT_KEY, name="NFL", active=True)
            s.add(sport)
            await s.flush()
            sport_id = sport.id
        await s.execute(
            delete(OddsSnapshot).where(OddsSnapshot.event_id.in_([GAME, FINAL]))
        )
        await s.execute(delete(Event).where(Event.id.in_([GAME, FINAL])))
        for event_id, status, kickoff in (
            (GAME, "scheduled", _KICKOFF),
            (FINAL, "completed", datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)),
        ):
            s.add(
                Event(
                    id=event_id,
                    sport_id=sport_id,
                    external_id=f"pg11295-{event_id}",
                    home_team_name="San Francisco 49ers",
                    away_team_name="Washington Commanders",
                    commence_time=kickoff,
                    status=status,
                    home_score=31 if status == "completed" else None,
                    away_score=38 if status == "completed" else None,
                    completed_at=(
                        (kickoff + timedelta(hours=3))
                        if status == "completed"
                        else None
                    ),
                )
            )
            await s.flush()
            for book, prob, spread, total, minutes in _ROWS:
                ph, pa = _proj(spread, total)
                captured = kickoff + timedelta(minutes=minutes)
                s.add(
                    OddsSnapshot(
                        event_id=event_id,
                        bookmaker=book,
                        captured_at=captured,
                        valid_until=captured,
                        home_win_probability=prob,
                        away_win_probability=round(1 - prob, 4),
                        home_spread=spread,
                        over_under=total,
                        projected_home_score=ph,
                        projected_away_score=pa,
                        reading_count=1,
                    )
                )
        await s.commit()


def _cards(status="scheduled", event_id=GAME, kickoff=_KICKOFF):
    return {
        "id": event_id,
        "stored_status": status,
        "served_status": status,
        "commence_time": kickoff,
        "sport_key": _SPORT_KEY,
    }


async def test_feed_and_league_cards_carry_the_detail_pages_pair(
    pg_engine, client, no_redis
):
    from app.routes import feed, league_futures

    await _seed(pg_engine)

    detail = (await client.get(f"/api/events/{GAME}")).json()["current_odds"]
    detail_pair = (detail["projected_home_score"], detail["projected_away_score"])
    # Hand-computed from the latest rows of the four honest books with a pair:
    # 30.0/22.0, 29.0/22.0, 30.5/22.5, 29.8/22.2 (29.75 rounds half-even to 29.8).
    assert detail_pair == (29.8, 22.2)

    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        events = (
            (await s.execute(select(Event).where(Event.id == GAME))).scalars().all()
        )
        item = {
            "type": "event",
            "data": {
                "id": GAME,
                "status": "scheduled",
                "sport": _SPORT_KEY,
                "current_odds": {"home_probability": 0.71, "away_probability": 0.29},
            },
        }
        before = (await s.execute(text("SHOW statement_timeout"))).scalar_one()
        await feed._attach_card_projected_pairs(s, [item], events, remaining_s=20.0)
        # Rolled back, never released: the bound does not outlive the read.
        assert (await s.execute(text("SHOW statement_timeout"))).scalar_one() == before
        brief = {
            "id": GAME,
            "status": "scheduled",
            "sport": _SPORT_KEY,
            "current_odds": {"home_probability": 0.71, "away_probability": 0.29},
        }
        await league_futures._attach_card_projected_pairs(s, events, [brief])

    for odds in (item["data"]["current_odds"], brief["current_odds"]):
        assert (
            odds["projected_home_score"],
            odds["projected_away_score"],
        ) == detail_pair
        assert odds["projection_captured_at"] == detail["captured_at"]
        assert (odds["home_probability"], odds["away_probability"]) == (0.71, 0.29)
        assert "captured_at" not in odds


async def test_a_finished_game_card_carries_no_pair_though_detail_still_serves_one(
    pg_engine, client, no_redis
):
    from app.utils.card_projected_pair import read_card_projected_pairs

    await _seed(pg_engine)
    detail = (await client.get(f"/api/events/{FINAL}")).json()["current_odds"]
    # The control: the row really does carry a pair on detail.
    assert detail["projected_home_score"] is not None

    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        pairs = await read_card_projected_pairs(
            s,
            [
                _cards(
                    "completed",
                    FINAL,
                    datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc),
                ),
                _cards(),
            ],
        )
    assert set(pairs) == {GAME}


async def test_the_seed_can_tell_the_wrong_answers_apart(pg_engine):
    await _seed(pg_engine)
    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        rows = (
            (await s.execute(select(OddsSnapshot).where(OddsSnapshot.event_id == GAME)))
            .scalars()
            .all()
        )
    honest = [r for r in rows if r.bookmaker != "bovada"]
    latest = {}
    for r in sorted(honest, key=lambda r: r.captured_at):
        latest[r.bookmaker] = r

    def pair(snaps):
        agg = aggregate_bookmaker_odds(list(snaps))
        return agg["projected_home_score"], agg["projected_away_score"]

    right = pair(latest.values())
    assert right == (29.8, 22.2)
    # every row, not the latest per book
    assert pair(honest) != right
    # the mirrored book left in
    assert (
        pair([*latest.values(), next(r for r in rows if r.bookmaker == "bovada")])
        != right
    )
    # the oldest row per book
    oldest = {}
    for r in sorted(honest, key=lambda r: r.captured_at, reverse=True):
        oldest[r.bookmaker] = r
    assert pair(oldest.values()) != right


async def test_a_read_outlasting_its_bound_is_cancelled_by_the_server_and_cards_stay(
    pg_engine, monkeypatch
):
    """C1: the bound is Postgres's, not asyncio's, and running out costs the pair.

    The read is swapped for a 5 s sleep on the same session; the bound is the
    floor (`remaining_s` leaves 100 ms after the margin). The server cancels the
    statement, the savepoint takes the failure, and the card keeps its
    probabilities with no pair — in well under the sleep.
    """
    from app.routes import feed
    from app.utils import card_projected_pair as cpp

    await _seed(pg_engine)
    slept: list[str] = []

    async def _slow_read(db, cards):
        slept.append((await db.execute(text("SHOW statement_timeout"))).scalar_one())
        await db.execute(text("SELECT pg_sleep(5)"))
        return {}

    monkeypatch.setattr(cpp, "read_card_projected_pairs", _slow_read)

    async with AsyncSession(pg_engine, expire_on_commit=False) as s:
        events = (
            (await s.execute(select(Event).where(Event.id == GAME))).scalars().all()
        )
        before = (await s.execute(text("SHOW statement_timeout"))).scalar_one()

        # The helper itself: the server's cancel (SQLSTATE 57014, query_canceled).
        with pytest.raises(DBAPIError) as caught:
            await cpp.read_card_projected_pairs_bounded(s, [_cards()], timeout_ms=100)
        assert caught.value.orig.pgcode == "57014"
        assert slept == ["100ms"]

        # Through the feed attach: no exception, no pair, probabilities intact.
        item = {
            "type": "event",
            "data": {
                "id": GAME,
                "status": "scheduled",
                "sport": _SPORT_KEY,
                "current_odds": {"home_probability": 0.71, "away_probability": 0.29},
            },
        }
        remaining = (cpp.CARD_PROJECTION_DEADLINE_MARGIN_MS + 100) / 1000
        started = datetime.now(timezone.utc)
        await feed._attach_card_projected_pairs(
            s, [item], events, remaining_s=remaining
        )
        took = (datetime.now(timezone.utc) - started).total_seconds()
        assert slept == ["100ms", "100ms"]
        assert took < 3.0
        assert item["data"]["current_odds"] == {
            "home_probability": 0.71,
            "away_probability": 0.29,
        }
        # The session is usable and its own timeout is untouched.
        assert (await s.execute(text("SELECT 1"))).scalar_one() == 1
        assert (await s.execute(text("SHOW statement_timeout"))).scalar_one() == before
