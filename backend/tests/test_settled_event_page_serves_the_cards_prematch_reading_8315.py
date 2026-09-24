"""#8315 — a settled event page serves the pre-game reading its Discover card prints.

Measured 2026-09-24 00:00Z, production, Nationals @ Tigers (final):

    /api/feed          prematch_odds {home .61, away .39, away_rendered 39, 'kalshi'}
    /api/events/15317535   opening_odds {home .6007, away .3993}, NO prematch_odds

The card said "won as a 39% underdog"; tapping it, the page's settled hero said
"Upset · 40% pregame". The card follows Alex's ladder (Kalshi → Polymarket →
sportsbooks); the page could only read the sportsbook median because that is all
this route served.

These guard the backend half: the route serves `prematch_odds`, and it is the
SAME object the feed serializer builds from the same inputs — one ladder, not two.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.models import Event, Sport
from app.routes import events as events_route
from app.routes.events import _settled_prematch_odds, get_event
from app.utils.feed_scoring import format_event_data
from app.utils.prematch_reading import PREMATCH_PRIOR_SQL

from tests.test_series_fold_3810 import is_blend_fold, is_series_fold

EVENT_ID = 15317535
KICKOFF = datetime(2026, 9, 23, 17, 10, tzinfo=timezone.utc)


def _event(*, status="completed", sport_key="baseball_mlb", home=0.6007, away=0.3993):
    event = Event(
        id=EVENT_ID,
        external_id="x",
        sport_id=1,
        home_team_name="Detroit Tigers",
        away_team_name="Washington Nationals",
        commence_time=KICKOFF,
        status=status,
        home_score=2,
        away_score=5,
        opening_home_probability=home,
        opening_away_probability=away,
        win_probability_sources=None,
    )
    event.sport = Sport(id=1, key=sport_key, name=sport_key)
    return event


def _row(source, home, away, draw=None):
    return SimpleNamespace(
        event_id=EVENT_ID,
        source=source,
        home_win_probability=home,
        away_win_probability=away,
        draw_probability=draw,
    )


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    def unique(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None


class _Savepoint:
    def __init__(self, log):
        self.log = log

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")


class _PrematchSession:
    """Answers the pre-match statement only; anything else is a test failure."""

    def __init__(self, rows=(), *, fail=False):
        self.rows = list(rows)
        self.fail = fail
        self.calls: list[dict] = []
        self.savepoint_log: list[str] = []

    async def begin_nested(self):
        return _Savepoint(self.savepoint_log)

    async def execute(self, statement, binds=None, *_a, **_kw):
        assert " ".join(str(statement).split()) == " ".join(PREMATCH_PRIOR_SQL.split())
        self.calls.append(binds)
        if self.fail:
            raise RuntimeError("canceling statement due to statement timeout")
        return _Result(self.rows)


def _feed_prematch(event, rows):
    """What `/api/feed` serves for the same event: `routes/feed.py`'s own
    inputs — `prematch_row_to_reading` per row keyed on source, the opening
    columns through the same truthiness test, the sport key."""
    from app.utils.prematch_reading import prematch_row_to_reading

    by_source = {r.source: prematch_row_to_reading(r) for r in rows}
    data = format_event_data(
        event_id=event.id,
        external_id=event.external_id,
        sport_key=event.sport.key,
        sport_name=event.sport.name,
        home_team=event.home_team_name,
        away_team=event.away_team_name,
        commence_time=event.commence_time,
        status=event.status,
        home_score=event.home_score,
        away_score=event.away_score,
        current_home_prob=None,
        current_away_prob=None,
        opening_home_prob=(
            float(event.opening_home_probability)
            if event.opening_home_probability
            else None
        ),
        opening_away_prob=(
            float(event.opening_away_probability)
            if event.opening_away_probability
            else None
        ),
        opening_favorite=None,
        win_probability_sources=None,
        prob_source=None,
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
        prematch_by_source=by_source or None,
    )
    return data.get("prematch_odds")


# ── The specimen ─────────────────────────────────────────────────────────────


def test_the_specimen_serves_the_kalshi_39_not_the_books_40():
    event = _event()
    db = _PrematchSession([_row("kalshi", 0.61, 0.39)])

    served = asyncio.run(_settled_prematch_odds(db, event, "baseball_mlb"))

    assert served == {
        "home_probability": 0.61,
        "away_probability": 0.39,
        "home_rendered_percent": 61,
        "away_rendered_percent": 39,
        "source": "kalshi",
    }
    # The read is bound to THIS event's kickoff — the cutoff is the whole guard
    # against a settled market's ~100% leaking back as a forecast.
    assert db.calls == [
        {"ids": [EVENT_ID], "cutoffs": [KICKOFF], "sources": ["kalshi", "polymarket"]}
    ]
    assert db.savepoint_log == ["commit"]


# ── One ladder: the page's object IS the card's object ───────────────────────


@pytest.mark.parametrize(
    "sport_key, opening, rows",
    [
        ("baseball_mlb", (0.6007, 0.3993), [_row("kalshi", 0.61, 0.39)]),
        (
            "baseball_mlb",
            (0.6007, 0.3993),
            [_row("kalshi", 0.61, 0.39), _row("polymarket", 0.66, 0.34)],
        ),
        ("baseball_mlb", (0.6007, 0.3993), [_row("polymarket", 0.575, 0.425)]),
        ("baseball_mlb", (0.6007, 0.3993), []),
        # a draw-priced sport's books rung: the de-vigged pair falls short of 1
        # and the shortfall is the draw (#7514) — kept, not re-complemented
        ("soccer_epl", (0.545, 0.21), []),
        # the same sport with a complement pair — rebuilt as 1 - home
        ("soccer_epl", (0.545, 0.455), []),
        # a three-way venue reading that carries its draw (#6277)
        ("soccer_epl", (0.545, 0.21), [_row("kalshi", 0.495, 0.245, 0.26)]),
        # no opening columns at all, venue only
        ("baseball_mlb", (None, None), [_row("kalshi", 0.52, 0.48)]),
    ],
)
def test_the_page_and_the_card_serve_one_object(sport_key, opening, rows):
    event = _event(sport_key=sport_key, home=opening[0], away=opening[1])

    page = asyncio.run(_settled_prematch_odds(_PrematchSession(rows), event, sport_key))

    assert page == _feed_prematch(event, rows)
    assert page is not None


def test_nothing_held_serves_nothing():
    """`None` is the only answer that licenses an empty space on the hero."""
    event = _event(home=None, away=None)
    assert asyncio.run(_settled_prematch_odds(_PrematchSession([]), event, "baseball_mlb")) is None


# ── The read's boundaries ────────────────────────────────────────────────────


def test_an_unsettled_event_never_reads_the_snapshot_table():
    event = _event(status="scheduled")
    db = _PrematchSession([_row("kalshi", 0.61, 0.39)])

    served = asyncio.run(_settled_prematch_odds(db, event, "baseball_mlb"))

    assert db.calls == []
    assert served["source"] == "books"


def test_a_failed_venue_read_costs_the_key_its_venue_rung_not_the_page():
    """The savepoint is rolled back (so the route's transaction is not left
    aborted for every query after this one) and the books rung answers."""
    event = _event()
    db = _PrematchSession(fail=True)

    served = asyncio.run(_settled_prematch_odds(db, event, "baseball_mlb"))

    assert db.savepoint_log == ["rollback"]
    assert served["source"] == "books"
    assert served["home_probability"] == pytest.approx(0.6007)


# ── Through the route ────────────────────────────────────────────────────────


class _RouteSession:
    def __init__(self, event, prematch_rows):
        self.event = event
        self.prematch_rows = prematch_rows
        self.prematch_reads = 0

    async def begin_nested(self):
        return _Savepoint([])

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())
        if "CROSS JOIN LATERAL" in sql and "win_prob_snapshots" in sql and "unnest" in sql:
            self.prematch_reads += 1
            return _Result(self.prematch_rows)
        if "FROM win_prob_snapshots" in sql or "FROM odds_snapshots" in sql:
            return _Result([])
        if is_blend_fold(sql) or is_series_fold(sql):
            return _Result([])
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


@pytest.fixture()
def route(monkeypatch):
    async def _none(*_a, **_kw):
        return None

    async def _empty(*_a, **_kw):
        return {}

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _empty)
    monkeypatch.setattr(events_route, "_build_team_lookup", _empty)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", _none)

    def _serve(event, rows):
        events_route._event_detail_cache.clear()
        db = _RouteSession(event, rows)
        return asyncio.run(get_event(EVENT_ID, db=db)), db

    yield _serve
    events_route._event_detail_cache.clear()


def test_the_route_serves_prematch_odds_on_a_settled_event(route):
    body, db = route(_event(), [_row("kalshi", 0.61, 0.39)])

    assert db.prematch_reads == 1
    assert body["prematch_odds"]["source"] == "kalshi"
    assert body["prematch_odds"]["away_rendered_percent"] == 39
    # `opening_odds` is untouched: the margin tile, the opened line and three
    # clients read it, and none of them is asking this question.
    assert body["opening_odds"]["home_probability"] == pytest.approx(0.6007)


def test_the_route_serves_no_prematch_odds_before_the_game(route):
    event = _event(status="scheduled")
    event.commence_time = datetime.now(timezone.utc) + timedelta(hours=3)

    body, db = route(event, [_row("kalshi", 0.61, 0.39)])

    assert db.prematch_reads == 0
    assert "prematch_odds" not in body
