"""#11296 / #9483 — a LIVE event page keeps the forecast retained from before the scheduled start.

PILLARS: FORMATTING / TRUTH. SHIP: a live event headline can compare its current
projected final with the genuine forecast retained before scheduled start.

The producer used to ask settled rows only, so a live page could never carry
the retained pair its headline needs. ``live_detail=True`` (the event page's
call alone) adds a row that PRINTS ``"live"``; every list, search and feed
caller keeps the default. The rig is the route file's: the same 15328569 shape
(kick-off 17:00Z, pregame rows at 16:30Z and 16:50Z, in-play rows at 20:25Z),
here served while the game is still being played. Every row is a constructed
CONTROL, not a production reading.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from app.models.models import Event, OddsSnapshot, Sport
from app.utils import pregame_projection as pp
from app.utils.odds_math import project_scores
from app.utils.start_placeholder import start_placeholder_tag
from tests.test_pregame_projection_11296 import KICK, _FakeDb, event, row, sport_of
from tests.test_pregame_projection_routes_11296 import (
    FINAL_ID,
    _DetailSession,
    _event,
    _pregame,
    _search,
    detail,  # noqa: F401 — the route file's fixture, used by name below
)
from tests.test_series_fold_3810 import blend_fold_row, is_blend_fold, is_series_fold

LIVE_ID = FINAL_ID


def live(**kw):
    kw.setdefault("status", "live")
    return event(**kw)


def plan(events, **kw):
    return pp.plan_pregame_projections(events, sport_of, **kw)


# ── the producer: who is asked ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "sport, unit, period",
    [
        ("americanfootball_nfl", "points", "full_game"),
        ("basketball_nba", "points", "full_game"),
        ("soccer_epl", "goals", "regulation"),
    ],
)
def test_a_live_row_is_asked_only_with_the_detail_opt_in(sport, unit, period):
    rows = [row("draftkings", -10, -0.5, 2.5), row("draftkings", 40, -1.5, 3.5)]
    # Control: the default is unchanged, a live row is not asked at all.
    assert plan([live(sport=sport)]) == (None, {})
    binds, answers = plan([live(sport=sport)], live_detail=True)
    assert answers == {}
    assert binds["ids"] == [1] and binds["cutoffs"] == [KICK]
    projection = pp.answers_from_rows(binds, rows)[1][pp.PROJECTION_KEY]
    # The pregame row only: 1.5 / 1.0 from -0.5 / 2.5, never the 40-minute row.
    assert (projection["projected_home_score"], projection["projected_away_score"]) == (1.5, 1.0)
    assert (projection["unit"], projection["period"]) == (unit, period)
    assert projection["kind"] == "last_before_scheduled_start"
    assert projection["boundary"] == "scheduled_start"
    assert projection["boundary_at"] == KICK.isoformat()
    assert projection["latest_captured_at"] == (KICK - timedelta(minutes=10)).isoformat()


@pytest.mark.parametrize(
    "status", ["scheduled", "suspended", "canceled", "postponed", "in_progress", "LIVE", None]
)
def test_the_opt_in_adds_exactly_live_and_no_other_unsettled_status(status):
    assert plan([event(status=status)], live_detail=True) == (None, {})


def test_settled_rows_are_planned_identically_with_and_without_the_opt_in():
    events = [
        event(1),
        event(2, status="closed", commence=KICK + timedelta(days=1)),
        event(3, sport="tennis_atp"),
        event(4, source="kalshi"),
        event(5, status="scheduled"),
    ]
    assert plan(events, live_detail=True) == plan(events)


@pytest.mark.parametrize(
    "kw, reason",
    [
        ({"sport": "baseball_mlb"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": "icehockey_nhl"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": "tennis_atp_us_open"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": "mma_mixed_martial_arts"}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"sport": None}, pp.REASON_FORMAT_UNSUPPORTED),
        ({"commence": None}, pp.REASON_NO_START),
        ({"source": "kalshi"}, pp.REASON_START_NOT_FROM_SCHEDULE),
        ({"source": None}, pp.REASON_START_NOT_FROM_SCHEDULE),
        ({"tags": [start_placeholder_tag(KICK)]}, pp.REASON_START_IS_PLACEHOLDER),
    ],
)
def test_a_live_row_is_refused_before_any_read_for_the_same_reasons(kw, reason):
    binds, answers = plan([live(**kw)], live_detail=True)
    assert binds is None
    assert answers == {1: {pp.UNAVAILABLE_KEY: reason}}


def test_a_live_row_whose_published_start_is_still_ahead_is_not_asked():
    # Only a stored-status caller can hold this (the served status downgrades a
    # live claim before its start): every row before that start may be in-play.
    future = live(commence=KICK + timedelta(hours=1))
    assert plan([future], live_detail=True, now=KICK) == (None, {})
    binds, _ = plan([future], live_detail=True, now=KICK + timedelta(hours=1))
    assert binds["ids"] == [1]  # at the start itself it is asked
    # The settled arm is untouched by the clock, as before.
    settled = event(commence=KICK + timedelta(hours=1))
    assert plan([settled], live_detail=True, now=KICK)[0]["ids"] == [1]


# ── the producer: what is read ───────────────────────────────────────────────


def test_only_in_play_rows_never_become_the_baseline():
    # The first in-play readings are exactly what a live page sees most of: if
    # the bound slipped, one of them would be served as "before the start".
    binds, _ = plan([live()], live_detail=True)
    rows = [row("draftkings", 0, -3.5, 48.0), row("fanduel", 1, -2.5, 47.5)]
    assert pp.answers_from_rows(binds, rows) == {
        1: {pp.UNAVAILABLE_KEY: pp.REASON_NO_PREGAME_READING}
    }


def test_a_live_soccer_row_never_serves_a_final_score_period():
    # Even a stored full-time detail on a row that still prints live: the
    # baseline does not wait for a final witness, and none is invented.
    e = live(sport="soccer_epl")
    e.period = "FT"
    db = _FakeDb([row("draftkings", -10, -0.5, 2.5)])
    answers = asyncio.run(
        pp.read_pregame_projections(db, [e], sport_of, live_detail=True)
    )
    assert set(answers[1]) == {pp.PROJECTION_KEY}
    assert answers[1][pp.PROJECTION_KEY]["period"] == "regulation"


def test_one_statement_serves_the_live_row_beside_the_settled_ones():
    events = [event(1), live(eid=2), event(3, status="scheduled")]
    db = _FakeDb([row("draftkings", -5, -3.0, 47.0, event_id=i) for i in (1, 2)])
    answers = asyncio.run(
        pp.read_pregame_projections(db, events, sport_of, live_detail=True)
    )
    assert len(db.executed) == 1
    sql, params = db.executed[0]
    assert sql == pp.PREGAME_PROJECTION_SQL
    assert params["ids"] == [1, 2]
    assert set(answers) == {1, 2}
    assert answers[1] == answers[2]


def test_a_failed_live_read_answers_read_failed_and_never_raises():
    db = _FakeDb(fail=True)
    answers = asyncio.run(
        pp.read_pregame_projections(
            db, [live(), live(eid=2, sport="baseball_mlb")], sport_of, live_detail=True
        )
    )
    assert answers == {
        1: {pp.UNAVAILABLE_KEY: pp.REASON_READ_FAILED},
        2: {pp.UNAVAILABLE_KEY: pp.REASON_FORMAT_UNSUPPORTED},
    }
    assert db.savepoint_ends == ["rollback"]


def test_a_cancelled_live_read_propagates_as_itself():
    class _Cancelled(_FakeDb):
        async def execute(self, statement, params=None):
            raise asyncio.CancelledError()

    db = _Cancelled()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(pp.read_pregame_projections(db, [live()], sport_of, live_detail=True))
    assert db.savepoint_ends == ["rollback"]


# ── the event page ───────────────────────────────────────────────────────────


def _nfl_live():
    e = _event(LIVE_ID, status="live")
    e.home_score, e.away_score, e.period = 14, 7, "3rd Quarter"
    return e


class TestTheLiveEventPage:
    def test_the_live_page_serves_the_retained_pair_beside_the_separate_in_play_pair(self, detail):
        payload, session = detail(_nfl_live(), _pregame(LIVE_ID))
        assert payload["status"] == "live"
        assert session.projection_reads == 1
        baseline = payload["pregame_projection"]
        assert baseline == {
            "projected_home_score": 25.4,
            "projected_away_score": 22.4,
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": (KICK - timedelta(minutes=30)).isoformat(),
            "latest_captured_at": (KICK - timedelta(minutes=10)).isoformat(),
            "boundary": "scheduled_start",
            "boundary_at": KICK.isoformat(),
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 2,
            "unit": "points",
            "period": "full_game",
        }
        # The in-play pair is its own object, untouched, on the other side of
        # the same boundary.
        current = payload["current_odds"]["live_projection"]
        assert current["kind"] == "in_play"
        assert (current["projected_home_score"], current["projected_away_score"]) == (31.2, 23.8)
        assert current["boundary_at"] == baseline["boundary_at"]
        assert current["earliest_confirmed_at"] >= baseline["boundary_at"] > baseline["latest_captured_at"]
        assert (current["unit"], current["period"]) == (baseline["unit"], baseline["period"])
        assert payload["current_odds"]["projected_home_score"] == 31.2
        assert "pregame_projection_unavailable" not in payload
        assert "final_score_period" not in payload

    def test_a_live_page_with_only_in_play_rows_says_so(self, detail):
        payload, session = detail(_nfl_live(), [])
        assert session.projection_reads == 1
        assert "pregame_projection" not in payload
        assert payload["pregame_projection_unavailable"] == "no_pregame_reading"
        # The current pair is not promoted into the missing baseline.
        assert payload["current_odds"]["live_projection"]["kind"] == "in_play"

    def test_a_live_page_on_a_venue_derived_start_is_refused_without_a_read(self, detail):
        e = _nfl_live()
        e.commence_time_source = "kalshi"
        payload, session = detail(e, _pregame(LIVE_ID))
        assert session.projection_reads == 0
        assert "pregame_projection" not in payload
        assert payload["pregame_projection_unavailable"] == "start_not_from_schedule"

    def test_a_live_page_whose_start_is_still_ahead_serves_neither_key(self, detail):
        # Stored live before its start: the page prints `scheduled`, so the
        # opt-in does not reach it.
        e = _nfl_live()
        e.commence_time = KICK + timedelta(days=3650)
        payload, session = detail(e, _pregame(LIVE_ID))
        assert payload["status"] == "scheduled"
        assert session.projection_reads == 0
        assert "pregame_projection" not in payload
        assert "pregame_projection_unavailable" not in payload

    def test_the_finished_page_is_unchanged(self, detail):
        payload, session = detail(_event(LIVE_ID), _pregame(LIVE_ID))
        assert session.projection_reads == 1
        assert payload["pregame_projection"]["projected_home_score"] == 25.4
        assert "live_projection" not in payload["current_odds"]


# ── soccer and an unsupported sport on the live page ─────────────────────────

EPL = Sport(id=90_011_297, key="soccer_epl", name="EPL")
MLB = Sport(id=90_011_298, key="baseball_mlb", name="MLB")


def _live_on(sport, period):
    e = Event(
        id=LIVE_ID, sport_id=sport.id,
        home_team_name="Arsenal", away_team_name="Chelsea",
        commence_time=KICK, commence_time_source="espn", status="live",
        home_score=1, away_score=1, period=period,
        opening_home_probability=0.5, opening_away_probability=0.26,
        win_probability_sources={}, event_tags=[],
    )
    e.sport = sport
    return e


def _soccer_snap(book, minutes, spread, total, rid):
    home, away = project_scores(spread, total)
    return OddsSnapshot(
        id=rid, event_id=LIVE_ID, bookmaker=book,
        captured_at=KICK + timedelta(minutes=minutes),
        home_win_probability=0.55, away_win_probability=0.2,
        home_spread=spread, over_under=total,
        projected_home_score=home, projected_away_score=away, reading_count=1,
    )


SOCCER_PREGAME = [
    _soccer_snap("draftkings", -15, -0.5, 2.5, 1),  # 1.5 / 1.0
    _soccer_snap("fanduel", -40, -0.5, 2.5, 2),
]
SOCCER_IN_PLAY = [
    _soccer_snap("draftkings", 60, -0.5, 3.5, 11),  # 2.0 / 1.5
    _soccer_snap("fanduel", 60, -0.5, 3.5, 12),
]


class _SoccerSession(_DetailSession):
    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())
        if "WITH RECURSIVE bounds" in sql:
            self.projection_reads += 1
            return _Rows(self.pregame_rows)
        if "odds_snapshots" in sql:
            return _Rows(SOCCER_IN_PLAY)
        if is_blend_fold(sql):
            return _Rows([blend_fold_row(self.event)])
        if is_series_fold(sql):
            return _Rows([])
        if "FROM events" in sql:
            return _Rows([self.event])
        return _Rows([])


class _Rows:
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


@pytest.fixture()
def soccer_detail(monkeypatch):
    from app.routes import events as events_route

    async def _none(*_a, **_kw):
        return {}

    async def _no_drain(_db, _event_id):
        return None

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _none)
    monkeypatch.setattr(events_route, "_build_team_lookup", _none)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", _no_drain)

    def _serve(event, pregame_rows):
        session = _SoccerSession(event, pregame_rows)
        events_route._event_detail_cache.clear()
        try:
            payload = asyncio.run(events_route.get_event(event.id, db=session))
        finally:
            events_route._event_detail_cache.clear()
        return payload, session

    return _serve


class TestLiveSoccerAndUnsupported:
    def test_regulation_play_serves_both_pairs_on_the_same_90_minute_basis(self, soccer_detail):
        payload, session = soccer_detail(_live_on(EPL, "2nd Half"), SOCCER_PREGAME)
        assert payload["status"] == "live" and session.projection_reads == 1
        baseline = payload["pregame_projection"]
        assert (baseline["projected_home_score"], baseline["projected_away_score"]) == (1.5, 1.0)
        assert (baseline["unit"], baseline["period"]) == ("goals", "regulation")
        current = payload["current_odds"]["live_projection"]
        assert (current["projected_home_score"], current["projected_away_score"]) == (2.0, 1.5)
        assert (current["unit"], current["period"]) == ("goals", "regulation")
        assert "final_score_period" not in payload

    def test_extra_time_keeps_the_labelled_baseline_and_withholds_the_current_pair(self, soccer_detail):
        # The baseline is a 90-minute forecast and stays one; the current pair's
        # own regulation gate withholds it, so nothing claims the two compare.
        payload, _ = soccer_detail(_live_on(EPL, "Extra Time"), SOCCER_PREGAME)
        assert payload["status"] == "live"
        assert payload["pregame_projection"]["period"] == "regulation"
        assert "live_projection" not in payload["current_odds"]
        assert "final_score_period" not in payload

    def test_a_live_baseball_page_is_refused_by_format_without_a_read(self, soccer_detail):
        payload, session = soccer_detail(_live_on(MLB, "Top 5th"), SOCCER_PREGAME)
        assert payload["status"] == "live"
        assert session.projection_reads == 0
        assert "pregame_projection" not in payload
        assert payload["pregame_projection_unavailable"] == "format_unsupported"


# ── list surfaces keep settled-only ──────────────────────────────────────────


def test_search_still_does_not_ask_a_live_row():
    final = _event(FINAL_ID)
    playing = _event(FINAL_ID + 1, status="live", home="Chicago Bears")
    cards, reads = _search([final, playing], _pregame(FINAL_ID))
    assert len(reads) == 1 and reads[0]["ids"] == [FINAL_ID]
    assert "pregame_projection" not in cards[FINAL_ID + 1]
    assert "pregame_projection_unavailable" not in cards[FINAL_ID + 1]


def test_only_the_event_page_passes_the_opt_in():
    # Every other caller of the reader keeps the default. Read from source so a
    # new list caller that copies the event page's line is caught here.
    import inspect

    from app.routes import events as events_route
    from app.routes import feed as feed_route
    from app.routes import league_futures as league_route

    detail_src = inspect.getsource(events_route.get_event)
    assert detail_src.count("live_detail=True") == 1
    for module in (events_route, feed_route, league_route):
        src = inspect.getsource(module)
        expected = 1 if module is events_route else 0
        assert src.count("live_detail=True") == expected, module.__name__
