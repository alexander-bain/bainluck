"""#4976 repair — `4976-KEEP-UNKNOWN-STATUS-HERO-CHART-DECAY-IN-LOCKSTEP`.

CERT-3112 blocked the #4976 ship on a two-number page, not on a missing
improvement. `pregame_boundary`'s first draft handed an UNKNOWN status the
started branch and said so out loud in its docstring: "this bucket is earlier
than the listed start" is a fact about the clock and does not need the status to
be legible. That reasoning holds for an event that has started. For one that has
not, every bucket ever drawn is earlier than the listed start — so the exemption
covered the newest bucket too, and the chart's right edge stopped agreeing with
the big number above it:

    betting 0.62, quoted hours ago      hero  0.36   (decayed — #1999's monotone
    kalshi  0.36, quoted just now               default for an unreadable status)
    status  unknown, kickoff in an hour  edge  0.62   (whole line exempt from decay)

Both paths said 0.36 before this ship existed. One number per question is the
standing ruling, so the exemption now stops at the hero's own gate.

🔴 WHY THIS FILE IS A ROUTE PAIR AND NOT A UNIT TEST. `pregame_boundary`'s truth
table is asserted in `test_pregame_buckets_do_not_decay_4976.py` and every one of
those assertions passed on the blocked sha — they read ONE side. The defect is
only visible when the two routes a reader gets on one screen are asked about the
same instant and compared, which is the same lesson `test_blend_fold_chart_pin_
parity_3911.py` was written for (#3911), and this rig is modelled on it.

🔴 THE PIN MUST DECLINE HERE, OR THIS FILE IS DECORATION. `_pin_blend_edge`
overwrites the last bucket with the served hero when the line's newest point is
younger than `_PREMATCH_EDGE_MAX_AGE` (2 minutes) — and a pinned edge equals the
hero no matter what the decay did. The fixture's newest bucket is deliberately
`_EDGE_AGE` old so the pin stands down and the edge is the aggregator's own
answer. `test_STRAWMAN_the_blocked_boundary_serves_two_numbers` is what proves
that: it reverts the repair and the parity assertion must FAIL.

CLOCK: read from `_now()` at CALL time, never a literal and never a module-level
`datetime.now()` — the pin's arms are measured in minutes against the wall clock,
and pytest imports a shard's modules at collection and runs them minutes later
(#3895; it is why #3911's first push went red in shard 3 and green alone).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.models import Event, Sport
from app.routes.events import get_event, get_event_odds_history
from app.utils import aggregation
from app.utils.aggregation import pregame_boundary

from tests.test_series_fold_3810 import is_blend_fold, is_series_fold


EVENT_ID = 15313430
S_TENNIS = 77

#: The two readings from the BLOCK. Betting outweighs kalshi 3.0 to 0.8, so
#: whichever of them keeps its weight IS the blend — that is what makes the
#: decay gate legible as a single number rather than a wobble.
BETTING_PROB = 0.62
KALSHI_PROB = 0.36

#: How far behind the fresh reading the sportsbook quote sits. A Saturday
#: fixture is repriced a handful of times a day; this is the ordinary case, not
#: an extreme one.
BETTING_AGE = timedelta(hours=3)

#: The newest bucket's age. > `_PREMATCH_EDGE_MAX_AGE` (2 min) so the pre-match
#: pin declines and the reader gets the aggregator's own right edge.
EDGE_AGE = timedelta(minutes=5)

#: Kickoff is AHEAD of now — the whole point. With it behind, the started branch
#: is correct and there is no divergence to find.
KICKOFF_IN = timedelta(hours=1)


def _now():
    """Wall clock at call time, truncated to the minute (the pin buckets at 60s
    and compares parsed datetimes; microseconds sit a hair past their bucket)."""
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _event_row(now):
    """Unknown status, upcoming — the cert's specimen.

    `status=None` rather than a made-up string so the row is the one the BLOCK
    executed. The truth table in the sibling file covers `""`, `"postponed"` and
    an unrecognised string; they all take the same branch.
    """
    event = Event(
        id=EVENT_ID,
        sport_id=S_TENNIS,
        home_team_name="Peyton Stearns",
        away_team_name="Sloane Stephens",
        commence_time=now + KICKOFF_IN,
        status=None,
        opening_home_probability=0.5,
        opening_away_probability=0.5,
        win_probability_sources={
            "betting": {
                "value": BETTING_PROB,
                "updated_at": (now - BETTING_AGE).isoformat(),
            },
            "kalshi": {"value": KALSHI_PROB, "updated_at": now.isoformat()},
        },
    )
    event.sport = Sport(id=S_TENNIS, key="tennis_wta", name="WTA")
    return event


def _snap(now, source, minutes_ago, home_prob):
    return SimpleNamespace(
        event_id=EVENT_ID,
        source=source,
        captured_at=now - timedelta(minutes=minutes_ago),
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state=None,
    )


def _snapshots(now):
    """Both curves FLAT, and both sources carried through `win_prob_snapshots`.

    Flat on purpose: if either source moved, a change in the served edge could
    be the source moving rather than the decay gate, and the comparison would
    prove nothing. `betting` is served here rather than through `odds_snapshots`
    because the aggregator keys on the source STRING and this keeps one row
    shape in the rig; the weight it draws (3.0) is the real one.
    """
    edge_min = int(EDGE_AGE.total_seconds() // 60)
    betting_min = int(BETTING_AGE.total_seconds() // 60)
    return [
        _snap(now, "betting", betting_min + 30, BETTING_PROB),
        _snap(now, "betting", betting_min, BETTING_PROB),
        _snap(now, "kalshi", edge_min + 30, KALSHI_PROB),
        _snap(now, "kalshi", edge_min, KALSHI_PROB),
    ]


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


class _RouteSession:
    """One fake session answering both routes off one event.

    No twin: the folds return empty, so nothing here depends on #3810 and a
    failure is about the decay gate and nothing else.
    """

    def __init__(self, now):
        self.now = now
        self.event = _event_row(now)

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())

        if "FROM win_prob_snapshots" in sql:
            rows = _snapshots(self.now)
            if "min(" in sql:
                return _Result([min(s.captured_at for s in rows)])
            return _Result(sorted(rows, key=lambda s: s.captured_at))
        if "FROM odds_snapshots" in sql:
            return _Result([])
        if is_blend_fold(sql):  # longer projection first (see #3911's rig)
            return _Result([])
        if is_series_fold(sql):
            return _Result([])
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


@pytest.fixture()
def both_routes(monkeypatch):
    from app.routes import events as events_route

    async def _no_percentiles(_db):
        return {}

    async def _no_teams(_db, _names):
        return {}

    async def _no_drain(_db, _event_id):
        return None

    monkeypatch.setattr(events_route, "_load_gei_percentiles", _no_percentiles)
    monkeypatch.setattr(events_route, "_build_team_lookup", _no_teams)
    monkeypatch.setattr(events_route, "resolve_market_born_duplicate", _no_drain)

    def _serve():
        """One reader's page load: the hero, then the chart under it."""
        events_route._event_detail_cache.clear()
        # ONE anchor for the pair — the two routes must be asked about the same
        # instant, and that instant must be now.
        now = _now()
        detail = asyncio.run(get_event(EVENT_ID, db=_RouteSession(now)))
        history = asyncio.run(
            get_event_odds_history(
                event_id=EVENT_ID,
                hours=720,
                response=MagicMock(headers={}),
                db=_RouteSession(now),
            )
        )
        return detail, history

    return _serve


def _edge(history):
    line = history.get("aggregate_line")
    assert line, "no blend line — the fixture, not the ship, is broken"
    return line[-1]["home_probability"]


def _blocked_boundary(status, commence_time, now=None):
    """`pregame_boundary` exactly as CERT-3112 graded it: an unknown status took
    the started branch whether or not the start had arrived."""
    if commence_time is None:
        return None
    if not aggregation._relative_decay_applies(status):
        return (
            max(commence_time, now)
            if now is not None
            else datetime.max.replace(tzinfo=commence_time.tzinfo)
        )
    return commence_time


def _body(history):
    """The newest bucket `_pin_blend_edge` did NOT overwrite.

    🔴 READ THIS BEFORE CHANGING AN ASSERTION BELOW. The naive form of this
    control — hero == `aggregate_line[-1]` — is VACUOUS on this specimen, and it
    passed on the blocked sha when first written. `_blend_outlives_edge` pins the
    final point to the served hero whenever the hero's newest source is at least
    as new as that bucket, which a fresh kalshi reading always is. So the edge
    equals the hero whatever the decay did, and the defect hides one point to its
    left: the curve runs flat at the undecayed sportsbook quote for its whole
    length and then drops onto the hero at the very last point.

    That cliff is the reader-visible harm and it is this ship's own thesis — a
    move no source made. So the guard reads the body and the step, not the edge.
    """
    line = history.get("aggregate_line")
    assert line and len(line) >= 2, (
        "need a bucket before the pinned edge — the fixture, not the ship, is broken"
    )
    return line[-2]["home_probability"]


class TestTheHeroAndTheChartAreOneNumber:
    def test_the_curve_does_not_step_onto_the_hero_at_its_final_point(
        self, both_routes
    ):
        """🔴 THE REPAIR. Reverting `pregame_boundary`'s un-started refusal
        fails here and nowhere else in the #4976 suite."""
        detail, history = both_routes()

        assert _body(history) == pytest.approx(_edge(history)), (
            "the blend line jumps at its own right edge: everything before the "
            "last point is exempt from decay and the last point is the hero"
        )
        assert detail["hero_probability"] == pytest.approx(_body(history)), (
            "the big number and the curve under it are the same question"
        )

    def test_they_agree_on_the_number_the_HERO_reached_not_the_stale_quote(
        self, both_routes
    ):
        """Parity alone is satisfiable by dragging the hero up to the stale
        sportsbook quote, which would be the wrong repair — #1999 decays an
        unreadable status on purpose. Pin the value, not just the agreement."""
        detail, history = both_routes()

        assert detail["hero_probability"] == pytest.approx(KALSHI_PROB, abs=0.02)
        assert _body(history) == pytest.approx(KALSHI_PROB, abs=0.02)
        assert _body(history) != pytest.approx(BETTING_PROB, abs=0.02)

    def test_STRAWMAN_the_blocked_boundary_prints_a_cliff_no_source_made(
        self, both_routes, monkeypatch
    ):
        """🔴 LOAD-BEARING. With the graded boundary restored the served line
        must carry the cliff — otherwise the fixture cannot see CERT-3112 and
        every assertion above is decoration that passes on the blocked sha.

        Both sources are flat across the whole window, so a step of this size in
        the served line is manufactured by the decay gate and by nothing else.
        """
        monkeypatch.setattr(aggregation, "pregame_boundary", _blocked_boundary)

        detail, history = both_routes()

        assert _body(history) == pytest.approx(BETTING_PROB, abs=0.02)
        assert _edge(history) == pytest.approx(detail["hero_probability"])
        assert abs(_edge(history) - _body(history)) > 0.2, (
            "expected the blocked boundary's ~26pp drop at the final point"
        )

    def test_the_pin_is_firing_so_the_edge_alone_cannot_grade_this(
        self, both_routes
    ):
        """Named so that a future change which makes the pin DECLINE here
        reports itself, rather than silently turning `_body` into an
        unrelated assertion about the middle of the curve."""
        _detail, history = both_routes()

        assert history.get("blend_edge_pinned") is True, (
            "the pre-match pin no longer fires on this fixture — re-read "
            "`_body`'s docstring and re-derive which point the guard must read"
        )


class TestTheStartedCaseIsUntouched:
    """The ship itself — point 1 of `pregame_boundary`'s docstring — is the
    pre-kickoff SEGMENT of an already-started chart, and CERT-3112 did not
    question it. Asserted here so the repair is visibly narrow."""

    def test_a_started_event_still_exempts_its_pre_kickoff_segment(self):
        kick = _now() - timedelta(hours=2)
        assert pregame_boundary("live", kick, _now()) == kick
        assert pregame_boundary("completed", kick, _now()) == kick

    def test_a_scheduled_event_is_still_exempt_all_the_way_to_now(self):
        kick = _now() - timedelta(hours=2)
        assert pregame_boundary("scheduled", kick, _now()) == _now()
