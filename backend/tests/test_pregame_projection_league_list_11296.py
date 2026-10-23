"""#11296 — the league page's list route serves the pregame projection the event page and search serve.

``/sports/{key}`` draws its cards from ``GET /api/events?sport=…`` (``list_events``),
not from ``/api/leagues/{sport_key}``. UX's live read on v5839 (2026-10-21
14:01Z, specimen 15330334, VfB Stuttgart 1–1 Atlético Madrid) found the event
page and the Search card printing the "Projection (90 min)" band while the
same final on ``/sports/soccer_uefa_champs_league`` printed none: the list
payload carried neither ``pregame_projection`` nor ``final_score_period``,
because ``list_events`` never called the attach. The two attach sites were
``search_events`` and ``get_event``.

Driven through ``list_events`` itself against a real (SQLite) engine, because
the whole defect is a correct helper missing from the route the page reads.
The projection statement is Postgres-only (``unnest``, recursive CTE), so the
session answers it from the rows ``PREGAME_PROJECTION_SQL`` would return and
records what it was asked; every other statement reaches the real engine.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.models import Base, Event, OddsSnapshot, Sport  # noqa: E402
from app.routes.events import list_events  # noqa: E402
from app.utils import pregame_projection as pp  # noqa: E402
from app.utils.card_projected_pair import CARD_PROJECTION_READ_CAP_MS  # noqa: E402
from app.utils.odds_math import project_scores  # noqa: E402
from tests.test_pregame_projection_routes_11296 import (  # noqa: E402,F401 — `detail` is a fixture
    FINAL_ID,
    UPCOMING_ID,
    _event as _detail_event,
    _search,
    detail,
)

UCL = "soccer_uefa_champs_league"
S_UCL, S_NFL, S_ATP = 1_129_601, 1_129_602, 1_129_603

STUTTGART = 15_330_334  # the specimen: 1–1, period "FT"
AET_FINAL = 15_330_335  # a knockout tie that went to extra time
VENUE_START = 15_330_336  # a final whose start a venue wrote, not a schedule
UPCOMING = 15_330_337
TENNIS = 15_330_338


def _kick(hours_ago=20):
    """Offset from the clock FIRST, then truncate (gotcha #44)."""
    t = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return t.replace(minute=0, second=0, microsecond=0)


def _row(event_id, sport_id, *, status="completed", period="FT", scores=(1, 1),
         source="espn", kick=None, home="VfB Stuttgart", away="Atlético Madrid"):
    kick = kick or _kick()
    settled = status == "completed"
    return Event(
        id=event_id, sport_id=sport_id,
        home_team_name=home, away_team_name=away,
        commence_time=kick, commence_time_source=source, status=status,
        home_score=scores[0] if settled else None,
        away_score=scores[1] if settled else None,
        completed_at=kick + timedelta(hours=2) if settled else None,
        period=period if settled else None,
        opening_home_probability=0.32, opening_away_probability=0.43,
        win_probability_sources={}, event_tags=[],
    )


def _snap(event_id, book, minutes, spread, total, home_p, away_p, *, kick, rid):
    """One row of what PREGAME_PROJECTION_SQL returns: a book's last pre-start row."""
    home, away = project_scores(spread, total)
    return SimpleNamespace(
        id=rid, event_id=event_id, bookmaker=book,
        captured_at=kick + timedelta(minutes=minutes),
        home_win_probability=home_p, away_win_probability=away_p,
        home_spread=spread, over_under=total,
        projected_home_score=home, projected_away_score=away,
    )


def _stuttgart_rows(event_id=STUTTGART, kick=None):
    kick = kick or _kick()
    return [
        _snap(event_id, "draftkings", -22, 0.5, 3.5, 0.32, 0.43, kick=kick, rid=event_id * 10 + 1),
        _snap(event_id, "fanduel", -4, 0.25, 3.5, 0.33, 0.42, kick=kick, rid=event_id * 10 + 2),
    ]


def _engine(*rows):
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Sport(id=S_UCL, key=UCL, name="UEFA Champions League", group="Soccer"))
        s.add(Sport(id=S_NFL, key="americanfootball_nfl", name="NFL", group="American Football"))
        s.add(Sport(id=S_ATP, key="tennis_atp", name="ATP", group="Tennis"))
        for r in rows:
            s.add(r)
        s.commit()
    return eng


class _Session:
    """The real engine behind `list_events`, except the Postgres-only projection read."""

    def __init__(self, session, pregame_rows, *, fail=False):
        self._s = session
        self.pregame_rows = list(pregame_rows)
        self.fail = fail
        self.projection_reads: list[dict] = []
        self.timeouts: list[str] = []
        self.savepoints = 0
        self.rollbacks = 0

    async def begin_nested(self):
        self.savepoints += 1
        outer = self

        class _Nested:
            async def rollback(self):
                outer.rollbacks += 1

        return _Nested()

    async def execute(self, statement, *args, **kwargs):
        sql = " ".join(str(statement).split())
        if "statement_timeout" in sql:
            self.timeouts.append(sql)
            return SimpleNamespace(all=lambda: [])
        if "WITH RECURSIVE bounds" in sql:
            params = args[0] if args else kwargs
            self.projection_reads.append(params)
            if self.fail:
                raise RuntimeError("canceling statement due to statement timeout")
            ids = set(params["ids"])
            rows = [r for r in self.pregame_rows if r.event_id in ids]
            return SimpleNamespace(all=lambda: rows)
        return self._s.execute(statement, *args)


def _portable_odds_query(event_ids):
    """The odds enrichment read in a form SQLite parses (no stored snapshots here)."""
    return select(OddsSnapshot).where(OddsSnapshot.event_id.in_(event_ids))


def _list(rows, pregame_rows=(), *, sport=UCL, fail=False, **params):
    eng = _engine(*rows)
    call = {"sport": sport, "status": None, "days": 7, "past_days": 7, "limit": 200, "offset": 0}
    call.update(params)
    with (
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events._build_team_lookup", new=AsyncMock(return_value={})),
        patch("app.routes.events.latest_odds_per_bookmaker_query", new=_portable_odds_query),
        Session(eng) as s,
    ):
        session = _Session(s, pregame_rows, fail=fail)
        payload = asyncio.run(list_events(db=session, **call))
    return {card["id"]: card for card in payload["events"]}, session


def _direct(row, pregame_rows, sport_key=UCL):
    """What `read_pregame_projections` answers for the row on its own: the helper the
    page and search attach through."""
    class _Db:
        async def begin_nested(self):
            async def _end():
                return None
            return SimpleNamespace(rollback=_end)

        async def execute(self, statement, params=None):
            ids = set((params or {}).get("ids") or [])
            return SimpleNamespace(all=lambda: [r for r in pregame_rows if r.event_id in ids])

    return asyncio.run(
        pp.read_pregame_projections(_Db(), [row], lambda _e: sport_key)
    )[row.id]


# ── the ship ─────────────────────────────────────────────────────────────────


class TestTheLeagueListCard:
    def test_the_stuttgart_final_carries_the_period_and_the_regulation_forecast(self):
        kick = _kick()
        rows = _stuttgart_rows(kick=kick)
        cards, session = _list([_row(STUTTGART, S_UCL, kick=kick)], rows)
        card = cards[STUTTGART]
        assert card["final_score_period"] == "regulation"
        projection = card["pregame_projection"]
        assert projection["period"] == "regulation"
        assert projection["unit"] == "goals"
        assert projection["boundary_at"] == kick.isoformat()
        assert projection["latest_captured_at"] < projection["boundary_at"]
        assert projection["bookmaker_count"] == 2
        assert "pregame_projection_unavailable" not in card
        # The actual result is the one the row stores, untouched.
        assert (card["home_score"], card["away_score"]) == (1, 1)
        assert card["status"] == "completed"
        assert len(session.projection_reads) == 1

    def test_the_list_card_is_the_same_object_the_helper_gives_the_page(self):
        kick = _kick()
        rows = _stuttgart_rows(kick=kick)
        cards, _ = _list([_row(STUTTGART, S_UCL, kick=kick)], rows)
        expected = _direct(_row(STUTTGART, S_UCL, kick=kick), rows)
        assert cards[STUTTGART]["pregame_projection"] == expected[pp.PROJECTION_KEY]
        assert cards[STUTTGART]["final_score_period"] == expected[pp.SCORE_PERIOD_KEY]

    def test_an_nfl_final_matches_the_event_page_and_search_card(self, detail):  # noqa: F811 — pytest fixture
        """The three doors serve one object for one row."""
        kick = _kick(hours_ago=30)
        rows = [
            _snap(FINAL_ID, "draftkings", -10, -3.5, 48.0, 0.6, 0.4, kick=kick, rid=1),
            _snap(FINAL_ID, "fanduel", -30, -2.5, 47.5, 0.58, 0.42, kick=kick, rid=2),
        ]
        nfl_final = _row(FINAL_ID, S_NFL, kick=kick, source="odds_api", period=None,
                         scores=(31, 38), home="Tampa Bay Buccaneers", away="Green Bay Packers")
        cards, _ = _list([nfl_final], rows, sport="americanfootball_nfl")
        page, _ = detail(_detail_event(FINAL_ID, commence=kick), rows)
        search_cards, _ = _search(
            [_detail_event(FINAL_ID, commence=kick),
             _detail_event(UPCOMING_ID, status="scheduled", home="Chicago Bears",
                           commence=kick + timedelta(days=7))],
            rows,
        )
        list_projection = cards[FINAL_ID]["pregame_projection"]
        assert list_projection == page["pregame_projection"] == search_cards[FINAL_ID]["pregame_projection"]
        assert (list_projection["projected_home_score"], list_projection["projected_away_score"]) == (25.4, 22.4)
        # Football's final is the full game: no soccer period key on any door.
        assert "final_score_period" not in cards[FINAL_ID]
        assert "final_score_period" not in page

    def test_each_card_keeps_its_own_forecast(self):
        """Matched by id, never by position: two finals, two different forecasts."""
        kick_a, kick_b = _kick(hours_ago=20), _kick(hours_ago=44)
        other = 15_330_399
        rows = _stuttgart_rows(kick=kick_a) + [
            _snap(other, "draftkings", -15, -1.25, 2.5, 0.6, 0.2, kick=kick_b, rid=91),
        ]
        cards, session = _list(
            [_row(STUTTGART, S_UCL, kick=kick_a),
             _row(other, S_UCL, kick=kick_b, home="Bayern Munich", away="Club Brugge", scores=(3, 0))],
            rows,
        )
        assert len(session.projection_reads) == 1
        assert sorted(session.projection_reads[0]["ids"]) == sorted([STUTTGART, other])
        assert cards[STUTTGART]["pregame_projection"] == _direct(
            _row(STUTTGART, S_UCL, kick=kick_a), rows)[pp.PROJECTION_KEY]
        b = cards[other]["pregame_projection"]
        assert b["boundary_at"] == kick_b.isoformat()
        assert b["bookmaker_count"] == 1
        assert b != cards[STUTTGART]["pregame_projection"]


# ── refusals and absences ────────────────────────────────────────────────────


class TestRefusalsSurviveTheListRoute:
    def test_an_extra_time_final_serves_no_period(self):
        kick = _kick()
        cards, _ = _list(
            [_row(AET_FINAL, S_UCL, kick=kick, period="AET", scores=(2, 1))],
            _stuttgart_rows(AET_FINAL, kick=kick),
        )
        card = cards[AET_FINAL]
        assert "final_score_period" not in card
        assert (card["home_score"], card["away_score"]) == (2, 1)

    def test_a_venue_written_start_is_refused_without_being_read(self):
        kick = _kick()
        cards, session = _list(
            [_row(STUTTGART, S_UCL, kick=kick),
             _row(VENUE_START, S_UCL, kick=kick, source="kalshi", home="Lille", away="Como")],
            _stuttgart_rows(kick=kick) + _stuttgart_rows(VENUE_START, kick=kick),
        )
        assert session.projection_reads[0]["ids"] == [STUTTGART]
        assert "pregame_projection" not in cards[VENUE_START]
        assert cards[VENUE_START]["pregame_projection_unavailable"] == "start_not_from_schedule"
        # The forecast is refused; what the score covers is decided by the row alone.
        assert cards[VENUE_START]["final_score_period"] == "regulation"

    def test_a_final_with_no_pregame_row_says_so(self):
        cards, _ = _list([_row(STUTTGART, S_UCL)], [])
        assert "pregame_projection" not in cards[STUTTGART]
        assert cards[STUTTGART]["pregame_projection_unavailable"] == "no_pregame_reading"
        assert cards[STUTTGART]["final_score_period"] == "regulation"

    def test_an_unsupported_sport_is_refused_without_a_read(self):
        cards, session = _list(
            [_row(TENNIS, S_ATP, home="Sinner", away="Alcaraz", scores=(2, 1), period=None)],
            [], sport="tennis_atp",
        )
        assert session.projection_reads == []
        assert session.savepoints == 0
        assert cards[TENNIS]["pregame_projection_unavailable"] == "format_unsupported"
        assert "pregame_projection" not in cards[TENNIS]

    def test_an_upcoming_card_gains_nothing(self):
        kick = _kick()
        cards, session = _list(
            [_row(STUTTGART, S_UCL, kick=kick),
             _row(UPCOMING, S_UCL, status="scheduled", kick=_kick(hours_ago=-30),
                  home="Bayern Munich", away="Club Brugge")],
            _stuttgart_rows(kick=kick),
        )
        assert session.projection_reads[0]["ids"] == [STUTTGART]
        for key in ("pregame_projection", "pregame_projection_unavailable", "final_score_period"):
            assert key not in cards[UPCOMING]


# ── cost ─────────────────────────────────────────────────────────────────────


class TestTheCost:
    def test_a_page_with_no_final_issues_no_statement(self):
        cards, session = _list(
            [_row(UPCOMING, S_UCL, status="scheduled", kick=_kick(hours_ago=-30),
                  home="Bayern Munich", away="Club Brugge")],
            [],
        )
        assert UPCOMING in cards
        assert session.projection_reads == []
        assert session.savepoints == 0
        assert session.timeouts == []

    def test_the_read_carries_its_own_server_side_bound_inside_a_rolled_back_savepoint(self):
        cards, session = _list([_row(STUTTGART, S_UCL)], _stuttgart_rows())
        assert "pregame_projection" in cards[STUTTGART]
        assert session.savepoints == 1 and session.rollbacks == 1
        assert session.timeouts == [f"SET LOCAL statement_timeout = '{CARD_PROJECTION_READ_CAP_MS}ms'"]

    def test_a_failed_read_costs_the_forecast_and_nothing_else(self):
        kick = _kick()
        cards, session = _list(
            [_row(STUTTGART, S_UCL, kick=kick),
             _row(UPCOMING, S_UCL, status="scheduled", kick=_kick(hours_ago=-30),
                  home="Bayern Munich", away="Club Brugge")],
            _stuttgart_rows(kick=kick), fail=True,
        )
        assert len(session.projection_reads) == 1
        assert set(cards) == {STUTTGART, UPCOMING}
        assert "pregame_projection" not in cards[STUTTGART]
        assert cards[STUTTGART]["pregame_projection_unavailable"] == "read_failed"
        assert cards[STUTTGART]["final_score_period"] == "regulation"
        assert (cards[STUTTGART]["home_score"], cards[STUTTGART]["away_score"]) == (1, 1)
