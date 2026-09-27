"""#8951 — a finished fight's chart ends on the result, not on the loser's pre-fight price.

Seen on production 2026-09-26 22:05Z, ``/events/15314294`` (UFC Fight Night,
Vanessa Demopoulos v Yazmin Jauregui, 21:10Z). The header read
**"Settled · Yazmin Jauregui wins"** and every prop was graded, but the Bain
Luck line ended on **Demopoulos 14%**:

    time (Z)   Kalshi   sportsbooks (`history`)   `aggregate_line`
    21:13      0.125    0.1361 (2 books)          0.1361
    21:14:51   0.01     —                         0.1361
    21:15–24   0.01     —                         0.1361 every bucket
    21:28      0.01     0.1413 (betmgm only)      0.1413   ← last point

The row is ``suspended`` with no score and no ``completed_at``, so the
terminal-result point — which only ever fired on ``is_finished`` AND a score —
never fired, and a two-source weighted median hands the tail to the heavier
sportsbook verbatim. The venue's grade is the result the page already prints,
so the chart now ends on it through the same terminal point a scored final gets.

The rig below executes ``get_event_odds_history`` itself. The venue read is
answered at its ROW shape — the six graded legs production holds for this
event, read 2026-09-26 23:3xZ — so the real ``settlement_from_graded_rows`` /
``choose_settled_winner`` decide the side; nothing here stubs the answer.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import get_event_odds_history, venue_settled_home_won
from tests.test_history_window_stale_open_event import _Result, _ScalarResult
from tests.test_series_fold_3810 import (
    blend_fold_row,
    fold_row,
    is_blend_fold,
    is_series_fold,
)

UTC = timezone.utc
EVENT_ID = 15314294
HOME = "Vanessa Demopoulos"
AWAY = "Yazmin Jauregui"

#: `(market name, external id, outcome)` — the specimen's positive venue grades,
#: verbatim from production. Only the KXUFCFIGHT leg is a moneyline; the other
#: five are props, and `choose_settled_winner` must ignore them.
SPECIMEN_GRADES = [
    ("Vanessa Demopoulos vs. Yazmin Jauregui: Round of Victory",
     "KXUFCVICROUND-26SEP26DEMJAU", "Yazmin Jauregui to win in Round 1"),
    ("Fight Night: Demopoulos vs Jauregui", "KXUFCFIGHT-26SEP26DEMJAU",
     "Yazmin Jauregui"),
    ("Vanessa Demopoulos vs Yazmin Jauregui: Round of Finish",
     "KXUFCROUNDS-26SEP26DEMJAU", "Fight ends before round 3"),
    ("Vanessa Demopoulos vs Yazmin Jauregui: Round of Finish",
     "KXUFCROUNDS-26SEP26DEMJAU", "Fight ends before round 2"),
    ("Vanessa Demopoulos vs. Yazmin Jauregui: Method of Finish",
     "KXUFCMOF-26SEP26DEMJAU", "KO/TKO/DQ"),
    ("Vanessa Demopoulos vs Yazmin Jauregui: Method of Victory",
     "KXUFCMOV-26SEP26DEMJAU", "Yazmin Jauregui by KO/TKO/DQ"),
]


def _kickoff():
    """Two hours ago, to the minute. Offset first, truncate second (gotcha #44)."""
    return (datetime.now(UTC) - timedelta(hours=2)).replace(second=0, microsecond=0)


def _moneylines(p):
    price = round(100 * (1 - p) / p)
    return price, -price


def _book(bookmaker, captured_at, valid_until, p, snap_id):
    home_ml, away_ml = _moneylines(p)
    return SimpleNamespace(
        id=snap_id,
        event_id=EVENT_ID,
        bookmaker=bookmaker,
        captured_at=captured_at,
        valid_until=valid_until,
        home_moneyline=home_ml,
        away_moneyline=away_ml,
        home_win_probability=p,
        away_win_probability=round(1 - p, 4),
        draw_probability=None,
        home_spread=None,
        away_spread=None,
        home_spread_odds=None,
        away_spread_odds=None,
        over_under=None,
        over_odds=None,
        under_odds=None,
        projected_home_score=None,
        projected_away_score=None,
    )


def _specimen_books(k):
    """Books quoting the pre-fight line, silent after K+3, plus betmgm's carry.

    betmgm's only snapshot predates the 24h window, so the route draws it at the
    cutoff AND at its `valid_until` (K+18) — the 21:28 one-book point.
    """
    rows = []
    snap_id = 1
    for book, p in (
        ("betonlineag", 0.1287), ("betus", 0.1355), ("williamhill_us", 0.137),
        ("bovada", 0.137), ("draftkings", 0.137), ("betrivers", 0.1412),
    ):
        rows.append(_book(book, k - timedelta(minutes=30), k + timedelta(minutes=3), p, snap_id))
        snap_id += 1
    rows.append(_book("draftkings", k + timedelta(minutes=3), k + timedelta(minutes=19), 0.1266, snap_id))
    rows.append(_book("betrivers", k + timedelta(minutes=3), k + timedelta(minutes=19), 0.1455, snap_id + 1))
    rows.append(_book("betmgm", k - timedelta(hours=23, minutes=30), k + timedelta(minutes=18), 0.1413, snap_id + 2))
    return rows


def _kalshi(when, p):
    return SimpleNamespace(
        event_id=EVENT_ID,
        captured_at=when,
        source="kalshi",
        home_win_probability=p,
        away_win_probability=round(1 - p, 4),
        draw_probability=None,
        game_state={"market_name": "Fight Night: Demopoulos vs Jauregui"},
    )


def _specimen_kalshi(k, *, until_minutes=18):
    """0.125 before the knockout, 0.01 from K+4:51 on every read to K+18:18."""
    rows = [_kalshi(k - timedelta(minutes=60 - 2 * i), 0.125) for i in range(32)]
    rows.append(_kalshi(k + timedelta(minutes=4, seconds=51), 0.01))
    rows += [
        _kalshi(k + timedelta(minutes=m, seconds=18), 0.01)
        for m in range(6, until_minutes + 1)
    ]
    return rows


def _event(k, *, status="suspended", home_score=None, away_score=None, completed_at=None):
    return SimpleNamespace(
        id=EVENT_ID,
        status=status,
        commence_time=k,
        completed_at=completed_at,
        home_team_name=HOME,
        away_team_name=AWAY,
        home_score=home_score,
        away_score=away_score,
        sport=SimpleNamespace(key="mma_mixed_martial_arts"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.01}},
    )


class _Session:
    """Answers each read by the table it names, honouring captured_at bounds."""

    def __init__(self, event, books, kalshi, grades):
        self.event = event
        self.books = books
        self.kalshi = kalshi
        self.grades = grades
        self.grade_reads = 0

    @staticmethod
    def _bounds(statement):
        import re

        params = statement.compile().params
        out = []
        for op, key in re.findall(r"captured_at\s*(<=|>=|<|>)\s*:(\w+)", str(statement)):
            when = params.get(key)
            if isinstance(when, datetime):
                out.append((op, when))
        return out

    @staticmethod
    def _keep(row, bounds):
        for op, when in bounds:
            got = row.captured_at
            if (op == "<" and not got < when) or (op == "<=" and not got <= when):
                return False
            if (op == ">" and not got > when) or (op == ">=" and not got >= when):
                return False
        return True

    async def execute(self, statement, *_a, **_kw):
        sql = str(statement)
        if is_series_fold(sql):
            return _Result([fold_row(self.event)])
        if "AS silent" in sql:
            return _ScalarResult(False)
        if is_blend_fold(sql):
            return _Result([blend_fold_row(self.event)])
        if "futures_outcomes" in sql and "is_winner" in sql:
            self.grade_reads += 1
            return _Result(self.grades)
        if "odds_snapshots" in sql:
            bounds = self._bounds(statement)
            rows = sorted(
                (r for r in self.books if self._keep(r, bounds)),
                key=lambda r: r.captured_at,
            )
            return _Result(rows)
        if "win_prob_snapshots" in sql:
            bounds = self._bounds(statement)
            params = [v for v in statement.compile().params.values() if isinstance(v, datetime)]
            if bounds:
                rows = [r for r in self.kalshi if self._keep(r, bounds)]
            elif params:
                cutoff = min(params)
                rows = [r for r in self.kalshi if r.captured_at >= cutoff]
            else:
                rows = list(self.kalshi)
            return _Result(rows)
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


def _serve(event, books, kalshi, grades):
    session = _Session(event, books, kalshi, grades)
    payload = asyncio.run(
        get_event_odds_history(
            event_id=EVENT_ID, hours=24, response=MagicMock(headers={}), db=session
        )
    )
    return payload, session


def _tail(payload):
    line = payload["aggregate_line"] or []
    assert line, "the rig must serve a blend line at all"
    return line[-1]


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_the_specimens_chart_ends_on_the_venues_result():
    k = _kickoff()
    payload, session = _serve(_event(k), _specimen_books(k), _specimen_kalshi(k), SPECIMEN_GRADES)

    tail = _tail(payload)
    assert tail["home_probability"] <= 0.05, (
        f"the settled fight's line still ends on Demopoulos at {tail['home_probability']}"
    )
    assert tail["home_probability"] == 0.0
    assert datetime.fromisoformat(tail["timestamp"]) > k + timedelta(minutes=18), (
        "the result point must come after every reading, not rewrite one"
    )
    assert session.grade_reads == 1


def test_the_rig_reproduces_the_defect_when_the_venue_has_not_graded():
    """The BEFORE, on the same rows: no grade ⇒ the tail is the sportsbook 14%.

    If this ever reads ≤ 0.05 the rig stopped reproducing #8951 and the headline
    test above would pass for a reason that is not this fix.
    """
    k = _kickoff()
    payload, _ = _serve(_event(k), _specimen_books(k), _specimen_kalshi(k), [])

    assert _tail(payload)["home_probability"] > 0.10


def test_every_series_the_chart_draws_ends_on_the_same_result():
    """One number per question: Kalshi's trace and the book line end where the blend does."""
    k = _kickoff()
    payload, _ = _serve(_event(k), _specimen_books(k), _specimen_kalshi(k), SPECIMEN_GRADES)

    terminal = _tail(payload)["timestamp"]
    assert payload["win_prob_history"]["kalshi"][-1]["timestamp"] == terminal
    assert payload["win_prob_history"]["kalshi"][-1]["home_probability"] == 0.0
    assert payload["history"][-1]["timestamp"] == terminal
    assert payload["history"][-1]["home_probability"] == 0.0
    assert payload["history"][-1]["bookmaker_count"] == 0


def test_a_home_win_ends_at_one_hundred():
    """Orientation: the side comes from the sentence, never from a price."""
    k = _kickoff()
    grades = [("Fight Night: Demopoulos vs Jauregui", "KXUFCFIGHT-26SEP26DEMJAU", HOME)]
    payload, _ = _serve(_event(k), _specimen_books(k), _specimen_kalshi(k), grades)

    assert _tail(payload)["home_probability"] == 1.0


def test_props_alone_do_not_decide_the_chart():
    """Five graded props and no moneyline leg: the venue named no winner."""
    k = _kickoff()
    props_only = [g for g in SPECIMEN_GRADES if not g[1].startswith("KXUFCFIGHT-")]
    payload, _ = _serve(_event(k), _specimen_books(k), _specimen_kalshi(k), props_only)

    assert _tail(payload)["home_probability"] > 0.10


# ---------------------------------------------------------------------------
# Controls — what must not move
# ---------------------------------------------------------------------------


def test_a_live_row_is_never_ended_by_a_grade():
    """`live` is outside the askable scope (the route passes no flatness read),
    so a live fight's chart keeps following its sources — the Castaneda shape.
    """
    k = _kickoff()
    payload, session = _serve(
        _event(k, status="live"), _specimen_books(k), _specimen_kalshi(k), SPECIMEN_GRADES
    )

    assert session.grade_reads == 0
    assert all(h.get("bookmaker_count") != 0 for h in payload["history"])


def test_a_scored_final_keeps_its_score_path_and_never_asks_the_venue():
    k = _kickoff()
    payload, session = _serve(
        _event(k, status="completed", home_score=1, away_score=0,
               completed_at=k + timedelta(minutes=20)),
        _specimen_books(k), _specimen_kalshi(k), SPECIMEN_GRADES,
    )

    assert session.grade_reads == 0
    assert _tail(payload)["home_probability"] == 1.0, "the score decides, not the grade"


def test_the_sentence_mapping_reads_only_our_own_winner_sentence():
    assert venue_settled_home_won(f"{HOME} wins", HOME, AWAY) is True
    assert venue_settled_home_won(f"{AWAY} wins", HOME, AWAY) is False
    # A score sentence is the venue's own outcome name — not parsed.
    assert venue_settled_home_won(f"{AWAY} wins 2-0", HOME, AWAY) is None
    assert venue_settled_home_won("Draw", HOME, AWAY) is None
    assert venue_settled_home_won(None, HOME, AWAY) is None
    assert venue_settled_home_won("X wins", "X", "X") is None
    assert venue_settled_home_won("X wins", "X", None) is None

