"""#11296 — the event page and search serve the same pregame projection, through the real routes.

The helper's own file proves selection. This one proves wiring: that the
object reaches ``GET /api/events/{id}`` and ``GET /api/events/search`` beside
an in-play ``current_odds`` pair it must not be confused with, and that the
probability prior's ``source`` is left alone.

The specimen is UX's 15328569 shape (2026-10-19 22:24Z): kick-off 17:00Z, the
newest sportsbook rows at 20:25Z projecting 31.2 / 23.8. ``current_odds``
keeps serving that pair (it is the latest reading); the pregame projection is
what the books said before 17:00Z.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, OddsSnapshot, Sport
from app.utils.odds_math import project_scores
from tests.test_series_fold_3810 import blend_fold_row, is_blend_fold, is_series_fold

KICK = datetime(2026, 10, 18, 17, 0, tzinfo=timezone.utc)
NFL = Sport(id=90_011_296, key="americanfootball_nfl", name="NFL")
FINAL_ID = 15_328_569
UPCOMING_ID = 15_328_570


def _event(event_id, *, status="completed", source="odds_api", home="Tampa Bay Buccaneers",
           commence=KICK):
    e = Event(
        id=event_id, sport_id=NFL.id,
        home_team_name=home, away_team_name="Green Bay Packers",
        commence_time=commence, commence_time_source=source, status=status,
        home_score=31 if status == "completed" else None,
        away_score=38 if status == "completed" else None,
        completed_at=KICK + timedelta(hours=3, minutes=30) if status == "completed" else None,
        opening_home_probability=0.58, opening_away_probability=0.42,
        win_probability_sources={}, event_tags=[],
    )
    e.sport = NFL
    return e


def _snap(event_id, book, minutes, spread, total, home_p, rid):
    home, away = project_scores(spread, total)
    return OddsSnapshot(
        id=rid, event_id=event_id, bookmaker=book,
        captured_at=KICK + timedelta(minutes=minutes),
        home_win_probability=home_p, away_win_probability=round(1 - home_p, 4),
        home_spread=spread, over_under=total,
        projected_home_score=home, projected_away_score=away, reading_count=1,
    )


def _in_play(event_id):
    """The latest row per book: 20:25Z, the 31.2 / 23.8 pair."""
    return [
        _snap(event_id, "draftkings", 205, -7.4, 55.0, 0.9, 11),
        _snap(event_id, "fanduel", 205, -7.4, 55.0, 0.9, 12),
    ]


def _pregame(event_id):
    """What PREGAME_PROJECTION_SQL returns: each book's last row before 17:00Z."""
    return [
        _snap(event_id, "draftkings", -10, -3.5, 48.0, 0.6, 1),   # 25.8 / 22.2
        _snap(event_id, "fanduel", -30, -2.5, 47.5, 0.58, 2),     # 25.0 / 22.5
    ]


def _is_projection_read(sql: str) -> bool:
    return "WITH RECURSIVE bounds" in sql


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _Nested:
    async def commit(self):
        return None

    async def rollback(self):
        return None


class _DetailSession:
    def __init__(self, event, pregame_rows):
        self.event = event
        self.pregame_rows = pregame_rows
        self.projection_reads = 0

    async def begin_nested(self):
        return _Nested()

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())
        if _is_projection_read(sql):
            self.projection_reads += 1
            return _Result(self.pregame_rows)
        if "odds_snapshots" in sql:
            return _Result(_in_play(self.event.id))
        if is_blend_fold(sql):
            return _Result([blend_fold_row(self.event)])
        if is_series_fold(sql):
            return _Result([])
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


@pytest.fixture()
def detail(monkeypatch):
    from app.routes import events as events_route

    async def _none(*_a, **_kw):
        return {}

    async def _no_drain(_db, _event_id):
        return None

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _none)
    monkeypatch.setattr(events_route, "_build_team_lookup", _none)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", _no_drain)

    def _serve(event, pregame_rows):
        session = _DetailSession(event, pregame_rows)
        events_route._event_detail_cache.clear()
        try:
            payload = asyncio.run(events_route.get_event(event.id, db=session))
        finally:
            events_route._event_detail_cache.clear()
        return payload, session

    return _serve


class TestTheEventPage:
    def test_the_final_serves_the_pregame_pair_beside_the_in_play_current_pair(self, detail):
        payload, session = detail(_event(FINAL_ID), _pregame(FINAL_ID))
        assert session.projection_reads == 1
        # current_odds is the latest reading and is unchanged by this ship.
        assert payload["current_odds"]["projected_home_score"] == 31.2
        assert payload["current_odds"]["projected_away_score"] == 23.8
        projection = payload["pregame_projection"]
        assert (projection["projected_home_score"], projection["projected_away_score"]) == (25.4, 22.4)
        assert projection["kind"] == "last_before_scheduled_start"
        assert projection["latest_captured_at"] == (KICK - timedelta(minutes=10)).isoformat()
        assert projection["earliest_captured_at"] == (KICK - timedelta(minutes=30)).isoformat()
        assert "pregame_projection_unavailable" not in payload

    def test_the_priors_source_is_its_own_and_is_not_inherited(self, detail):
        payload, _ = detail(_event(FINAL_ID), _pregame(FINAL_ID))
        assert payload["prematch_odds"]["source"] == "books"
        assert "projected_home_score" not in payload["prematch_odds"]
        assert payload["pregame_projection"]["source"] == "sportsbooks"

    def test_a_final_with_no_pregame_row_says_so_and_prints_no_pair(self, detail):
        payload, _ = detail(_event(FINAL_ID), [])
        assert "pregame_projection" not in payload
        assert payload["pregame_projection_unavailable"] == "no_pregame_reading"

    def test_a_venue_derived_start_is_refused_without_a_read(self, detail):
        payload, session = detail(_event(FINAL_ID, source="kalshi"), _pregame(FINAL_ID))
        assert session.projection_reads == 0
        assert payload["pregame_projection_unavailable"] == "start_not_from_schedule"

    def test_an_upcoming_game_is_not_asked(self, detail):
        payload, session = detail(_event(UPCOMING_ID, status="scheduled"), _pregame(UPCOMING_ID))
        assert session.projection_reads == 0
        assert "pregame_projection" not in payload
        assert "pregame_projection_unavailable" not in payload


# ── search ───────────────────────────────────────────────────────────────────


def _search_db(events, pregame_rows, reads):
    db = AsyncMock()

    def make_result(rows=(), *, grouped=None, scalars=None):
        r = MagicMock()
        r.scalars.return_value.all.return_value = list(scalars or rows)
        r.scalars.return_value.unique.return_value.all.return_value = list(scalars or rows)
        r.scalars.return_value.first.return_value = None
        r.fetchall.return_value = []
        r.all.return_value = grouped or []
        r.scalar.return_value = len(events)
        r.scalar_one_or_none.return_value = None
        r.first.return_value = None
        r.mappings.return_value.all.return_value = []
        return r

    async def execute(stmt, *a, **k):
        try:
            s = str(stmt)
        except Exception:  # noqa: BLE001
            return make_result()
        if _is_projection_read(" ".join(s.split())):
            reads.append(a[0] if a else k)
            return make_result(grouped=pregame_rows)
        low = s.lower()
        if "count(" in low and "futures_markets" not in low:
            return make_result(grouped=[(NFL.key, NFL.name, len(events))] if events else [])
        if "odds_snapshots" in low:
            return make_result(scalars=[s for e in events for s in _in_play(e.id)])
        if "futures_markets" in low or "teams" in low:
            return make_result()
        if "from events" in low:
            return make_result(events)
        return make_result()

    db.execute = AsyncMock(side_effect=execute)
    db.begin_nested = AsyncMock(return_value=AsyncMock())
    return db


def _search(events, pregame_rows):
    reads: list = []
    rc = MagicMock()
    rc.get.return_value = None
    from app.routes.events import search_events

    with (
        patch("app.tasks.redis_state.get_redis_client", return_value=rc),
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch(
            "app.routes.events.folded_probability_sources_batch",
            new=AsyncMock(return_value={}),
        ),
        patch("app.routes.events._record_trending", new=MagicMock()),
    ):
        payload = asyncio.run(
            search_events(
                request=MagicMock(), response=MagicMock(), q="packers",
                db=_search_db(events, pregame_rows, reads),
                sport=None, tags=None, page=1, per_page=25, days_back=30,
                include_upcoming=True, debug_timing=False, current_user=None,
            )
        )
    return {card["id"]: card for card in payload["results"]}, reads


class TestSearch:
    def test_the_search_card_serves_the_same_object_as_the_page(self, detail):
        final = _event(FINAL_ID)
        upcoming = _event(UPCOMING_ID, status="scheduled", home="Chicago Bears",
                          commence=KICK + timedelta(days=7))
        cards, reads = _search([final, upcoming], _pregame(FINAL_ID))
        assert len(reads) == 1 and reads[0]["ids"] == [FINAL_ID]
        card = cards[FINAL_ID]
        assert card["current_odds"]["projected_home_score"] == 31.2
        page, _ = detail(_event(FINAL_ID), _pregame(FINAL_ID))
        assert card["pregame_projection"] == page["pregame_projection"]
        assert "pregame_projection" not in cards[UPCOMING_ID]
        assert "pregame_projection_unavailable" not in cards[UPCOMING_ID]

    def test_a_search_final_with_only_in_play_rows_says_so(self):
        cards, _ = _search([_event(FINAL_ID)], [])
        assert "pregame_projection" not in cards[FINAL_ID]
        assert cards[FINAL_ID]["pregame_projection_unavailable"] == "no_pregame_reading"
