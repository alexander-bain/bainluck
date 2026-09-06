"""live/068: a settled chart that serves zero points over a table full of them.

`GET /api/events/{id}/history` caps a finished event's window at
`completed_at + 30min`, or — when `completed_at` is null — at
`commence_time + max_duration + 30min`. On the cohort live/035 found on the OPEN
side, `commence_time` is a Kalshi ticker-derived midnight stand-in (gotcha #14).
Arriving through the SETTLED door it is worse, because the stale-open escape
hatch is gated on `not is_finished` and never fires: the cap is computed from the
placeholder and there is nothing to correct it.

The specimen, measured on production 2026-09-05:

    events.id 15300276   Jodar v Bu   status 'closed'   completed_at NULL
    commence_time 2026-09-01 00:00 UTC (commence_time_source 'kalshi_ticker')
    559 Kalshi win-prob rows spanning 09-01 15:56 .. 09-02 21:03
    0 odds rows (Kalshi-only)
    cap = commence + 6.0h + 30min = 09-01 06:30  ->  0 of 559 rows served

    served: {"history": [], "points": 0, "snapshot_count": 0,
             "time_domain": {"start": "...T00:00:00Z", "end": "...T06:30:00Z"}}

The cap ends 9h26m BEFORE the first point it is supposed to bound. The reader
gets an empty graph on a match with a day and a half of price history.

These tests drive the REAL route function against a stubbed session that honours
the bind parameters it compiles, rather than re-implementing the window: a
replicated window is a window that can agree with the test and disagree with
production. The controls are the point of the file — the cap has a real job
(trimming days of post-settlement prediction-market drift) and this change must
be invisible to every event whose chart is not already empty.
"""

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.routes.events import (
    _end_cap_hides_every_point,
    get_event_odds_history,
)

UTC = timezone.utc

# The specimen's own numbers, so the fixture cannot drift away from production.
COMMENCE = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)  # the midnight placeholder
CAP = COMMENCE + timedelta(hours=6.5)  # tennis max_duration 6.0 + 30min
FIRST_POINT = datetime(2026, 9, 1, 15, 56, tzinfo=UTC)  # 9h26m after the cap
LAST_POINT = datetime(2026, 9, 2, 21, 3, tzinfo=UTC)


# ---------------------------------------------------------------------------
# A session stub that honours the bounds the route compiles
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _bounds(statement):
    """Map each compiled `captured_at` comparison to its operator.

    Reading the operator back — rather than assuming the only datetime bind is a
    cutoff — is what lets one stub serve both the lower-bound (live window) and
    upper-bound (end cap) arms without either arm silently passing.
    """
    sql = str(statement)
    try:
        params = statement.compile().params
    except Exception:  # pragma: no cover - a stub must never mask the route
        return None, None
    lower = upper = None
    for op, name in re.findall(r"captured_at\s*(>=|<=|>|<)\s*:(\w+)", sql):
        value = params.get(name)
        if not isinstance(value, datetime):
            continue
        if op.startswith(">"):
            lower = value if lower is None else max(lower, value)
        else:
            upper = value if upper is None else min(upper, value)
    return lower, upper


class _DispatchingSession:
    """Answers each query by the table it reads, applying the bounds it compiled."""

    def __init__(self, event, win_prob_rows=(), odds_rows=()):
        self.event = event
        self.win_prob_rows = list(win_prob_rows)
        self.odds_rows = list(odds_rows)
        self.win_prob_upper_bounds = []
        self.odds_upper_bounds = []

    @staticmethod
    def _apply(rows, lower, upper):
        if lower is not None:
            rows = [r for r in rows if r.captured_at >= lower]
        if upper is not None:
            rows = [r for r in rows if r.captured_at <= upper]
        return rows

    async def execute(self, statement, *_a, **_kw):
        sql = str(statement)
        # Match the FROM clause, never a bare substring: `events` carries a
        # `win_probability_sources` column, so "win_prob in sql" routes the event
        # lookup itself into the snapshot arm and the route 404s.
        for table, rows, seen in (
            ("win_prob_snapshots", self.win_prob_rows, self.win_prob_upper_bounds),
            ("odds_snapshots", self.odds_rows, self.odds_upper_bounds),
        ):
            if f"FROM {table}" not in sql:
                continue
            lower, upper = _bounds(statement)
            if "min(" in sql:
                # The live/068 probe: earliest row, unbounded by construction.
                return _Result([min((r.captured_at for r in rows), default=None)]
                               if rows else [None])
            seen.append(upper)
            return _Result(self._apply(rows, lower, upper))

        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


def _wp(when, home_prob):
    return SimpleNamespace(
        captured_at=when,
        source="kalshi",
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state={"market_name": "Jodar vs Bu"},
    )


def _odds(when, home_prob):
    return SimpleNamespace(
        captured_at=when,
        bookmaker="draftkings",
        home_probability=home_prob,
        away_probability=round(1.0 - home_prob, 4),
        valid_until=None,
    )


def _specimen_event(**overrides):
    event = SimpleNamespace(
        id=15300276,
        status="closed",
        commence_time=COMMENCE,
        completed_at=None,
        home_team_name="Jodar",
        away_team_name="Bu",
        home_score=None,
        away_score=None,
        sport=SimpleNamespace(key="tennis_atp_us_open"),
        sport_id=1,
        box_score_data=None,
        win_probability_sources={"kalshi": {"value": 0.01}},
    )
    for key, value in overrides.items():
        setattr(event, key, value)
    return event


def _curve(start, end, count=60, first=0.50, last=1.0):
    """A price curve laid between two instants, ending in a settlement."""
    span = (end - start) / max(count - 1, 1)
    step = (last - first) / max(count - 1, 1)
    return [
        _wp(start + span * i, round(first + step * i, 4)) for i in range(count)
    ]


async def _history(event, win_prob_rows=(), odds_rows=(), hours=720):
    session = _DispatchingSession(event, win_prob_rows, odds_rows)
    payload = await get_event_odds_history(
        event_id=event.id, hours=hours, response=MagicMock(headers={}), db=session
    )
    return payload, session


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------


async def test_a_cap_before_every_point_is_convicted():
    session = _DispatchingSession(
        _specimen_event(), _curve(FIRST_POINT, LAST_POINT)
    )
    assert await _end_cap_hides_every_point(session, 15300276, CAP) is True


async def test_a_cap_with_one_point_inside_it_is_left_alone():
    """The control that keeps the cap doing its job.

    A single point inside the window means the cap is trimming a tail, not
    deleting a chart — and a tail is exactly what it exists to trim.
    """
    rows = [_wp(CAP - timedelta(minutes=1), 0.5)] + _curve(FIRST_POINT, LAST_POINT)
    session = _DispatchingSession(_specimen_event(), rows)
    assert await _end_cap_hides_every_point(session, 15300276, CAP) is False


async def test_an_event_with_no_data_at_all_is_not_convicted():
    """Nothing to reveal, so nothing to widen for."""
    session = _DispatchingSession(_specimen_event())
    assert await _end_cap_hides_every_point(session, 15300276, CAP) is False


async def test_odds_rows_beyond_the_cap_also_convict_it():
    """The same defect on an event that has no win-prob rows to speak for it."""
    session = _DispatchingSession(
        _specimen_event(),
        win_prob_rows=(),
        odds_rows=[_odds(FIRST_POINT + timedelta(hours=i), 0.5) for i in range(5)],
    )
    assert await _end_cap_hides_every_point(session, 15300276, CAP) is True


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


async def test_the_specimen_serves_its_curve_instead_of_an_empty_graph():
    event = _specimen_event()
    rows = _curve(FIRST_POINT, LAST_POINT)

    payload, session = await _history(event, rows)
    served = payload["win_prob_history"].get("kalshi", [])

    assert served, (
        "the settled chart still serves zero points over a full price history"
    )
    assert len(served) == len(rows)
    assert session.win_prob_upper_bounds == [None], (
        "the win-prob query still compiled the placeholder-derived end cap"
    )
    last = datetime.fromisoformat(served[-1]["timestamp"])
    assert last > CAP, "the settlement itself must survive the window"


async def test_a_real_stale_tail_is_still_trimmed():
    """THE control. The cap's real job must be untouched.

    Same route, same shape, but the match actually played when `commence_time`
    says it did — plus five days of post-settlement prediction-market drift. The
    cap must still cut the drift, or every settled chart grows a flat tail.
    """
    real_commence = COMMENCE + timedelta(hours=13)
    event = _specimen_event(commence_time=real_commence)
    match = _curve(real_commence, real_commence + timedelta(hours=3), count=40)
    stale_tail = _curve(
        real_commence + timedelta(days=5),
        real_commence + timedelta(days=7),
        count=20,
    )

    payload, session = await _history(event, match + stale_tail)
    served = payload["win_prob_history"].get("kalshi", [])

    assert len(served) == len(match), "the stale tail was served as if it were play"
    expected_cap = real_commence + timedelta(hours=6.5)
    assert session.win_prob_upper_bounds == [expected_cap], (
        "the end cap stopped being applied to an event that never needed relaxing"
    )
    last = datetime.fromisoformat(served[-1]["timestamp"])
    assert last <= expected_cap


async def test_a_trustworthy_completed_at_still_bounds_the_window():
    """The cap is only ever relaxed when there is nothing inside it.

    An event that settled normally keeps `completed_at + 30min`, so the relaxation
    cannot leak into the ordinary settled path.
    """
    real_commence = COMMENCE + timedelta(hours=13)
    completed = real_commence + timedelta(hours=2)
    event = _specimen_event(commence_time=real_commence, completed_at=completed)
    match = _curve(real_commence, completed, count=30)
    tail = _curve(completed + timedelta(hours=4), completed + timedelta(days=2), 10)

    payload, session = await _history(event, match + tail)
    served = payload["win_prob_history"].get("kalshi", [])

    assert len(served) == len(match)
    assert session.win_prob_upper_bounds == [completed + timedelta(minutes=30)]


async def test_a_trustworthy_completion_with_TAIL_ONLY_points_stays_empty():
    """CERT-2002's BLOCK. The repair, and the reason the relaxation is scoped.

    `completed_at` is authoritative here — a statement that the match ended at
    15:00Z — and every stored point falls after the 15:30Z cap. Those points are
    post-settlement drift, so the empty chart is the CORRECT answer and the cap
    must hold. Relaxing on "the cap hides every point" ALONE served all of them
    and widened the axis by two days, manufacturing a journey out of a stale tail
    — the exact thing the cap exists to prevent.

    The distinguishing fact is the cap's PROVENANCE, not its arithmetic: only a
    commence-derived cap can be a midnight placeholder artefact (gotcha #14).
    """
    commence = COMMENCE + timedelta(hours=13)
    completed = commence + timedelta(hours=2)  # authoritative: after commence
    cap = completed + timedelta(minutes=30)
    event = _specimen_event(commence_time=commence, completed_at=completed)
    tail_only = _curve(cap + timedelta(hours=1), cap + timedelta(days=2), count=10)

    payload, session = await _history(event, tail_only)
    served = payload["win_prob_history"].get("kalshi", [])

    assert served == [], (
        "post-settlement drift was served as the match journey on an event whose "
        "completion time is trustworthy"
    )
    assert session.win_prob_upper_bounds == [cap], (
        "an authoritative completed_at cap was relaxed; only the commence "
        "fallback may be widened"
    )
    domain_end = datetime.fromisoformat(payload["time_domain"]["end"])
    assert domain_end <= cap, "the axis was widened onto post-settlement drift"


async def test_an_INVERTED_completed_at_still_relaxes_like_the_specimen():
    """The other half of the provenance split, so the scope is not over-tight.

    An inverted `completed_at` (< commence) is corrupt (gotcha #32 family), so
    `_finished_event_end_cap` already ignores it and falls back to the commence
    cap. That fallback is the untrustworthy one, so this row must still be
    rescued — gating on `completed_at is not None` instead of on its
    authoritativeness would strand it.
    """
    event = _specimen_event(completed_at=COMMENCE - timedelta(hours=41))
    rows = _curve(FIRST_POINT, LAST_POINT)

    payload, session = await _history(event, rows)
    served = payload["win_prob_history"].get("kalshi", [])

    assert len(served) == len(rows)
    assert session.win_prob_upper_bounds == [None]


async def test_the_axis_contains_the_curve_it_is_the_axis_for():
    """A relaxed cap was also the axis end; leaving it there hides the new line.

    The specimen is Kalshi-only, so the odds-derived fallback is empty and the
    domain came back null — a chart with points and no axis to draw them on.
    """
    event = _specimen_event()
    rows = _curve(FIRST_POINT, LAST_POINT)

    payload, _session = await _history(event, rows)
    domain = payload["time_domain"]
    served = payload["win_prob_history"]["kalshi"]

    assert domain is not None, "a chart with points came back with no axis"
    start = datetime.fromisoformat(domain["start"])
    end = datetime.fromisoformat(domain["end"])
    assert start <= datetime.fromisoformat(served[0]["timestamp"])
    assert end >= datetime.fromisoformat(served[-1]["timestamp"])
    assert end > CAP, "the axis still ends at the cap that hid every point"
