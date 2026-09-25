"""Guard: a listing both of whose teams were playing someone else stops printing (#7345).

THE CARD THIS EXISTS FOR. `/api/events/search?q=arkansas state`, production,
2026-09-25, served `15306765` — Arkansas State v South Alabama, Sep 12,
suspended, no score, no ids, no markets — directly under Arkansas State's real
Sep 12 final, and `/sport/football/ncaaf` printed it as "No result reported".
Both teams hold ESPN-linked finals at that exact kick-off against other
opponents (15309107 52-7 West Georgia, 15304849 Tulane 28-24).

This file is about DELIVERY: that search, the events list and the league page
call `same_instant_refuted_on_page`, drop exactly the ids it names, keep the
real finals, and serve the page when it raises. The verdict's SQL (LATERAL,
exact-instant equality, NULL-false `<>`) cannot run on a mock or on sqlite; it
is graded clause by clause against a real Postgres in
`tests/integration/test_same_instant_refutation_7345_pg.py`, which is also
where each arm is shown to be load-bearing.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.models import Event, Sport
from app.routes import league_futures
from app.routes.events import list_events, search_events
from app.services.same_instant_refutation import is_refutation_candidate_row

from tests.test_a_market_born_ghost_is_off_the_league_rails_6345 import (
    _Session,
    _engine,
)

NCAAF = Sport(
    id=760, key="americanfootball_ncaaf", name="NCAAF", group="American Football",
    active=True,
)
ARST, USA, UWG, TULANE = 15330, 17178, 17109, 15305
PHANTOM, ARST_FINAL, USA_FINAL = 15306765, 15309107, 15304849


def _kickoff() -> datetime:
    """Gotcha #44: offset first, then truncate."""
    return (datetime.now(timezone.utc) - timedelta(days=13)).replace(
        minute=0, second=0, microsecond=0
    )


def _ev(eid, home_id, away_id, home, away, **kw) -> Event:
    e = Event(
        id=eid,
        sport_id=NCAAF.id,
        home_team_id=home_id,
        away_team_id=away_id,
        home_team_name=home,
        away_team_name=away,
        commence_time=kw.pop("commence_time", _kickoff()),
        win_probability_sources={},
        **kw,
    )
    return e


def _phantom() -> Event:
    return _ev(PHANTOM, ARST, USA, "Arkansas State Red Wolves",
               "South Alabama Jaguars", status="suspended",
               commence_time_source="odds_api")


def _finals() -> list[Event]:
    k = _kickoff()
    return [
        _ev(ARST_FINAL, ARST, UWG, "Arkansas State Red Wolves",
            "West Georgia Wolves", status="completed", home_score=52,
            away_score=7, espn_id="401868241", completed_at=k + timedelta(hours=3),
            commence_time_source="espn"),
        _ev(USA_FINAL, TULANE, USA, "Tulane Green Wave", "South Alabama Jaguars",
            status="completed", home_score=28, away_score=24,
            espn_id="401864575", completed_at=k + timedelta(hours=3),
            commence_time_source="espn"),
    ]


def _with_sport(rows):
    for r in rows:
        r.sport = NCAAF
    return rows


_REFUTES = {PHANTOM: (ARST_FINAL, USA_FINAL)}


# =============================================================================
# the pure gate — a page with no candidate asks nothing
# =============================================================================


def test_the_specimen_is_a_candidate():
    assert is_refutation_candidate_row(_phantom(), datetime.now(timezone.utc))


@pytest.mark.parametrize(
    "overrides",
    [
        {"home_score": 0},
        {"completed_at": datetime.now(timezone.utc)},
        {"espn_id": "401869933"},
        {"statpal_fixture_id": "12345"},
        {"home_team_id": None},
        {"away_team_id": None},
        {"commence_time": datetime.now(timezone.utc) + timedelta(hours=2)},
    ],
)
def test_each_gate_clause_refuses(overrides):
    row = SimpleNamespace(
        id=PHANTOM, home_team_id=ARST, away_team_id=USA, commence_time=_kickoff(),
        home_score=None, away_score=None, completed_at=None, espn_id=None,
        statpal_fixture_id=None,
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    assert not is_refutation_candidate_row(row, datetime.now(timezone.utc))


def test_the_refuting_finals_are_never_candidates():
    now = datetime.now(timezone.utc)
    assert not any(is_refutation_candidate_row(e, now) for e in _finals())


# =============================================================================
# search and the events list
# =============================================================================


def _mock_db(events):
    db = AsyncMock()

    def result(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.fetchall.return_value = []
        r.all.return_value = []
        r.scalar.return_value = len(events)
        r.scalar_one_or_none.return_value = None
        return r

    async def execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "count(" in s or "futures_markets" in s or "odds_snapshots" in s:
            return result([])
        if "teams" in s or "win_prob_snapshots" in s or "event_provider_anchors" in s:
            return result([])
        if "from events" in s:
            return result(events)
        return result([])

    db.execute = AsyncMock(side_effect=execute)
    return db


_ROUTE_PATCHES = (
    "app.routes.events._load_gei_percentiles",
    "app.routes.events._build_team_lookup",
    "app.routes.events.folded_probability_sources_batch",
)


async def _search(rows, verdict):
    rc = MagicMock()
    rc.get.return_value = None
    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch(_ROUTE_PATCHES[0], new=AsyncMock(return_value={})),
        patch(_ROUTE_PATCHES[1], new=AsyncMock(return_value={})),
        patch(_ROUTE_PATCHES[2], new=AsyncMock(return_value={})),
        patch("app.routes.events._record_trending", new=MagicMock()),
        patch("app.routes.events.same_instant_refuted_on_page", new=verdict),
    ):
        payload = await search_events(
            request=MagicMock(), response=MagicMock(), q="arkansas state",
            sport=None, tags=None, page=1, per_page=25, days_back=30,
            include_upcoming=True, debug_timing=False, current_user=None,
            db=_mock_db(rows),
        )
    return [r["id"] for r in payload["results"]]


async def _list(rows, verdict):
    with (
        patch(_ROUTE_PATCHES[0], new=AsyncMock(return_value={})),
        patch(_ROUTE_PATCHES[1], new=AsyncMock(return_value={})),
        patch(_ROUTE_PATCHES[2], new=AsyncMock(return_value={})),
        patch("app.routes.events.same_instant_refuted_on_page", new=verdict),
    ):
        payload = await list_events(
            sport=None, status=None, days=30, limit=200, offset=0,
            db=_mock_db(rows),
        )
    return [r["id"] for r in payload["events"]], payload["count"]


@pytest.mark.asyncio
async def test_search_stops_serving_the_phantom_and_keeps_both_finals():
    verdict = AsyncMock(return_value=_REFUTES)
    ids = await _search(_with_sport([_phantom(), *_finals()]), verdict)
    assert PHANTOM not in ids, f"search still serves the phantom: {ids}"
    assert {ARST_FINAL, USA_FINAL} <= set(ids)
    verdict.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_serves_the_row_when_the_verdict_names_nothing():
    """Without this the drop above could be any other stage's doing."""
    ids = await _search(_with_sport([_phantom(), *_finals()]),
                        AsyncMock(return_value={}))
    assert PHANTOM in ids


@pytest.mark.asyncio
async def test_a_failing_verdict_serves_the_search_page():
    ids = await _search(_with_sport([_phantom(), *_finals()]),
                        AsyncMock(side_effect=RuntimeError("boom")))
    assert {PHANTOM, ARST_FINAL, USA_FINAL} <= set(ids)


@pytest.mark.asyncio
async def test_the_events_list_drops_it_and_counts_what_it_served():
    ids, count = await _list(_with_sport([_phantom(), *_finals()]),
                             AsyncMock(return_value=_REFUTES))
    assert PHANTOM not in ids
    assert {ARST_FINAL, USA_FINAL} <= set(ids)
    assert count == len(ids)


@pytest.mark.asyncio
async def test_a_failing_verdict_serves_the_events_list():
    ids, _ = await _list(_with_sport([_phantom(), *_finals()]),
                         AsyncMock(side_effect=RuntimeError("boom")))
    assert PHANTOM in ids


# =============================================================================
# the league page — "No result reported · Sep 12"
# =============================================================================


def _league(verdict) -> dict:
    eng = _engine(
        Sport(id=NCAAF.id, key=NCAAF.key, name="NCAAF", group="American Football"),
        _phantom(), *_finals(),
    )
    with Session(eng) as s, patch.object(
        league_futures, "same_instant_refuted_on_page", new=verdict
    ):
        return asyncio.run(league_futures.build_league(NCAAF.key, _Session(s)))


def _all_rail_ids(payload) -> set[int]:
    return {
        c["id"]
        for key in ("games", "recent_results", "unreported_games")
        for c in payload.get(key) or []
    }


def test_the_league_page_stops_printing_no_result_reported_for_it():
    before = _league(AsyncMock(return_value={}))
    assert PHANTOM in {c["id"] for c in before["unreported_games"]}, (
        "rig: the phantom must reach the unreported rail without the verdict, "
        "or the assertion below is vacuous"
    )
    after = _league(AsyncMock(return_value=_REFUTES))
    assert PHANTOM not in _all_rail_ids(after)
    assert {ARST_FINAL, USA_FINAL} <= {c["id"] for c in after["recent_results"]}


def test_a_failing_verdict_serves_the_league_page():
    payload = _league(AsyncMock(side_effect=RuntimeError("boom")))
    assert PHANTOM in {c["id"] for c in payload["unreported_games"]}
