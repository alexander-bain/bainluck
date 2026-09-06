"""The period-marker domain guard, driven through the REAL history route (#3348).

`tests/test_period_markers.py` guards the helper. This file exists because the
helper is not the contract — `GET /api/events/{id}/history` is, and CERT-1984
blocked the first cut of this fix on exactly that gap: the guard looked right in
isolation and still shipped the defect, because the route assembles series shapes
a utility test never sees.

Two shapes, both named by that review, both driven end to end here:

1. **A timestamped row is not a drawn line.** The route appends a `history` row
   for every odds bucket whether or not `aggregate_bookmaker_odds()` found a
   probability — a book quoting only a total produces `home_probability: None`.
   The web still renders `OddsChart` for those rows (the page's empty-state gate
   is `history.length === 0`), so a marker that survives on their timestamps is
   drawn over a blank plot. That IS #3348, arriving through the guard meant to
   stop it.

2. **The score chart is a line too.** One `period_markers` array is handed to
   both `OddsChart` and `ScoreDifferentialChart`. `score_history` is a series the
   second one draws, and leaving it out of the span throws away truthful MEASURED
   innings on an event whose score chart is perfectly fine.

The session stub dispatches by table and returns exactly what each query asks
for; the route does its own assembling. Nothing here re-implements the guard —
a replicated guard is one that can agree with the test and disagree with
production.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import get_event_odds_history
from app.utils.period_markers import SOURCE_ESTIMATED, SOURCE_STATPAL

UTC = timezone.utc


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _DispatchingSession:
    """Answers each query by the table named in its SQL. Everything else is empty.

    Deliberately literal: the point of these tests is that the ROUTE turns rows
    into series and markers, so the stub's only job is to hand over rows.
    """

    def __init__(self, event, *, odds=(), scores=(), scoring_plays=()):
        self.event = event
        self.odds = list(odds)
        self.scores = list(scores)
        self.scoring_plays = list(scoring_plays)

    async def execute(self, statement, *_a, **_kw):
        sql = str(statement)
        if "FROM events" in sql:
            return _Result([self.event])
        if "odds_snapshots" in sql:
            return _Result(self.odds)
        if "score_snapshots" in sql:
            return _Result(self.scores)
        if "scoring_plays" in sql:
            return _Result(self.scoring_plays)
        return _Result([])


def _event(now, **kw):
    """A completed soccer match — the cohort #3348 was measured on."""
    base = dict(
        id=15298122,
        status="completed",
        commence_time=now - timedelta(hours=4),
        completed_at=now - timedelta(hours=2),
        home_team_name="Ajax",
        away_team_name="Union SG",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="soccer_uefa_champs_league"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _totals_only_snapshot(when):
    """A real production shape: a book quoting a TOTAL and no moneyline.

    `aggregate_bookmaker_odds()` returns `home_probability: None` for this, and
    the route appends the `history` row anyway. Timestamp, no probability line.
    """
    return SimpleNamespace(
        captured_at=when,
        bookmaker="draftkings",
        home_win_probability=None,
        away_win_probability=None,
        over_under=2.5,
        home_spread=None,
        projected_home_score=None,
        projected_away_score=None,
        valid_until=None,
    )


def _score_snapshot(when, home, away):
    return SimpleNamespace(captured_at=when, home_score=home, away_score=away)


def _scoring_play_period(period, first_seen):
    """A row of the tier-1 `ScoringPlay` group-by: an OBSERVED period start."""
    return SimpleNamespace(period=period, first_seen=first_seen)


async def _history(session, event_id, hours=48):
    return await get_event_odds_history(
        event_id=event_id, hours=hours, response=MagicMock(headers={}), db=session
    )


# ---------------------------------------------------------------------------
# 1. A timestamped row is not a drawn line
# ---------------------------------------------------------------------------


async def test_null_only_probability_history_serves_no_period_marker():
    """The blocking case. Rows exist, ink does not, so no chip may be placed.

    Without the value check this event serves two `estimated` soccer chips that
    the web draws as dashed gridlines over an empty probability plot — the
    screenshot on #3348.
    """
    now = datetime.now(UTC)
    kickoff = now - timedelta(hours=4)
    session = _DispatchingSession(
        _event(now),
        odds=[
            _totals_only_snapshot(kickoff - timedelta(hours=1)),
            _totals_only_snapshot(kickoff + timedelta(minutes=30)),
            _totals_only_snapshot(kickoff + timedelta(hours=2)),
        ],
    )

    payload = await _history(session, 15298122)

    assert payload["history"], (
        "fixture no longer produces the shape under test — the route must still "
        "emit timestamped rows here, or this proves nothing"
    )
    assert all(p["home_probability"] is None for p in payload["history"]), (
        "fixture drifted: these rows are supposed to carry NO probability"
    )
    assert payload["period_markers"] == [], (
        "a period chip survived on a chart with no probability line"
    )


async def test_the_control_a_real_probability_line_keeps_its_chips():
    """The other direction, and the one that makes the test above mean anything.

    Identical event, identical markers — the ONLY change is that the books
    quoted a moneyline. A guard that passed the case above by dropping
    everything fails here.
    """
    now = datetime.now(UTC)
    kickoff = now - timedelta(hours=4)

    def quoted(when):
        snap = _totals_only_snapshot(when)
        snap.home_win_probability = 0.58
        snap.away_win_probability = 0.42
        return snap

    session = _DispatchingSession(
        _event(now),
        odds=[
            quoted(kickoff - timedelta(hours=1)),
            quoted(kickoff + timedelta(minutes=30)),
            quoted(kickoff + timedelta(hours=2)),
        ],
    )

    payload = await _history(session, 15298122)

    assert [m["period"] for m in payload["period_markers"]] == ["1H", "2H"]
    assert all(
        m["source"] == SOURCE_ESTIMATED for m in payload["period_markers"]
    ), "these are arithmetic on kickoff and must say so (#3336)"


# ---------------------------------------------------------------------------
# 2. The score chart is a line too
# ---------------------------------------------------------------------------


async def test_score_only_history_keeps_its_measured_period_marker():
    """CERT-1984's second finding. `score_history` is a line, so it is a domain.

    No odds at all, so the probability chart draws nothing — but the score
    differential chart draws the whole match, and the marker is a MEASURED
    observation from the scoring-plays table. Dropping it would delete truth
    from a chart that renders fine.
    """
    now = datetime.now(UTC)
    kickoff = now - timedelta(hours=4)
    observed = kickoff + timedelta(minutes=52)
    session = _DispatchingSession(
        _event(now),
        scores=[
            _score_snapshot(kickoff, 0, 0),
            _score_snapshot(observed, 1, 0),
            _score_snapshot(kickoff + timedelta(hours=2), 2, 1),
        ],
        scoring_plays=[_scoring_play_period("2H", observed)],
    )

    payload = await _history(session, 15298122)

    assert payload["history"] == [], "fixture drifted: this event has no odds line"
    assert payload["score_history"], "fixture drifted: the score line is the point"
    assert [m["period"] for m in payload["period_markers"]] == ["2H"]
    assert payload["period_markers"][0]["source"] == SOURCE_STATPAL


async def test_a_marker_off_the_score_line_too_is_still_dropped():
    """The control for the clause above: the score span WIDENS the guard, it does
    not switch it off. Same score-only event, marker two days past the last
    score."""
    now = datetime.now(UTC)
    kickoff = now - timedelta(hours=4)
    session = _DispatchingSession(
        _event(now),
        scores=[
            _score_snapshot(kickoff, 0, 0),
            _score_snapshot(kickoff + timedelta(hours=2), 2, 1),
        ],
        scoring_plays=[
            _scoring_play_period("2H", kickoff - timedelta(days=2)),
        ],
    )

    payload = await _history(session, 15298122)

    assert payload["score_history"], "fixture drifted: the score line is the point"
    assert payload["period_markers"] == [], (
        "a chip landed on neither the probability line nor the score line and "
        "was served anyway"
    )
