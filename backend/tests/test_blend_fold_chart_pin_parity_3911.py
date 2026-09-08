"""#3911 repair — `HERO-BLEND-FOLD-CHART-PIN-PARITY-3911`.

Fold A (#3810 acceptance 1) made the hero read the twin rows we decline to
print. `_pin_blend_edge` did not move with it, and that is a two-number
user-visible regression rather than a missing improvement:

    canonical  polymarket 0.60          hero  = weighted median(0.60, 0.40) = 0.40
    twin       kalshi     0.40          edge  = compute_aggregate_probability(raw
                                                canonical) = 0.60

Both are rendered at the same minute on the same screen — the big number says
40% and the curve under it ends at 60%. That is exactly #3898's shape, rebuilt
by the fix for its sibling, and it is why the repair is a parity guard across
BOTH routes rather than another assertion inside `get_event`.

🔴 THE MUTANT THIS FILE EXISTS FOR: pass the raw `event` to `_pin_blend_edge`
instead of the folded view and `test_the_chart_edge_and_the_hero_are_one_number`
fails. The submitted #3911 guards all passed on that mutant (91/91 on the
composed tree), because every one of them read a single route.

CLOCK: every timestamp here comes from `_now()`, which reads the wall clock when
it is CALLED. Not a calendar literal, and not a module-level `datetime.now()`
either — the pre-match arm of the pin only fires while the newest bucket is
younger than `_PREMATCH_EDGE_MAX_AGE` (2 minutes), and pytest imports a shard's
modules at collection and runs them minutes later. Either kind of stored anchor
therefore makes this file PASS vacuously rather than fail, which is #3895
(`EXPIRING-TEST-ANCHORS`) with the sign flipped. `TestTheFixtureCannotExpire`
pins both, and the second one is not hypothetical: it is why the first push of
this repair went red in CI shard 3/4 and green in isolation.
"""

import asyncio
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes.events import get_event, get_event_odds_history
from app.utils.aggregation import compute_aggregate_probability

from tests.test_series_fold_3810 import is_blend_fold, is_series_fold


# The production pair #3810 was filed on.
CANON_ID = 15305016
GHOST_ID = 15304989
S_TENNIS = 77

def _now():
    """The fixture anchor, read from the wall clock AT CALL TIME.

    🔴 NOT a module-level constant, and the difference is not stylistic. The
    pre-match pin stands down once the newest bucket is older than
    `_PREMATCH_EDGE_MAX_AGE` (2 minutes), and pytest imports every module in a
    shard at COLLECTION and runs them minutes later — so an anchor frozen at
    import is stale by the time the request is served, the pin declines, and the
    parity assertion is graded on an unpinned line. Measured: this file went red
    in CI shard 3/4 (358 files) for exactly that reason while passing alone.

    Truncated to the minute because the pin buckets at 60s and compares parsed
    datetimes; a fixture carrying microseconds sits a hair PAST its own bucket.
    """
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


#: The two readings from the BLOCK, one per row. Equal stamps on purpose: the
#: aggregator's staleness decay is measured against the freshest stamp on the
#: event, so a fixture whose sources are minutes apart would be testing decay
#: rather than the fold.
CANON_PROB = 0.60
TWIN_PROB = 0.40
#: What the two blend to, and therefore what BOTH surfaces must say. Named, not
#: inlined, so the assertions read as "one number" instead of a repeated 0.4.
BLENDED = 0.40

#: 🔴 The SERIES tells a different story from the CURRENT readings, deliberately.
#: Both curves end high while the live source dict says 0.60/0.40, so an UNPINNED
#: right edge cannot coincidentally equal the hero. Without this the parity test
#: passes whenever the pin silently declines — which is exactly how a stale
#: fixture anchor hid the regression this file exists for.
SERIES_CANON_EDGE = 0.90
SERIES_TWIN_EDGE = 0.85


def _sources(now, **readings):
    return {
        key: {"value": value, "updated_at": now.isoformat()}
        for key, value in readings.items()
    }


def _event_row(now):
    """SCHEDULED, and starting soon.

    Not `completed`: `_EXCLUDE_WHEN_COMPLETED` drops kalshi and polymarket from
    the blend once a game is over, so a settled fixture would agree with itself
    with the repair deleted. Not `live` either — the live arm of the pin APPENDS
    a point, which would hide a wrong value at the end of the line behind a new
    one. Pre-match OVERWRITES the last bucket, which is the sharpest place to
    read the disagreement.
    """
    event = Event(
        id=CANON_ID,
        sport_id=S_TENNIS,
        home_team_name="Ben Shelton",
        away_team_name="Stefanos Tsitsipas",
        commence_time=now + timedelta(hours=1),
        status="scheduled",
        win_probability_sources=_sources(now, polymarket=CANON_PROB),
    )
    event.sport = Sport(id=S_TENNIS, key="tennis_atp_us_open", name="US Open")
    return event


#: The twin as each fold's own projection returns it, oriented in agreement —
#: what production holds for all 12 pairs (measured 2026-09-07).
def _blend_fold_rows(now):
    return [(GHOST_ID, "Shelton", "Tsitsipas", _sources(now, kalshi=TWIN_PROB))]


def _series_fold_rows():
    return [
        (CANON_ID, "Ben Shelton", "Stefanos Tsitsipas"),
        (GHOST_ID, "Shelton", "Tsitsipas"),
    ]


def _snap(now, event_id, source, minutes_ago, home_prob):
    return SimpleNamespace(
        event_id=event_id,
        source=source,
        captured_at=now - timedelta(minutes=minutes_ago),
        home_win_probability=home_prob,
        away_win_probability=round(1.0 - home_prob, 4),
        draw_probability=None,
        game_state=None,
    )


def _snapshots(now):
    """Two sources, because `aggregate_line` is only computed for >1.

    The newest bucket is `now` itself, so the pre-match arm of the pin fires on
    the last point rather than declining as a genuinely-past edge — and both
    curves sit far above the current readings, so a line that was NOT pinned
    reads visibly differently from one that was.
    """
    return [
        _snap(now, CANON_ID, "polymarket", 2, SERIES_CANON_EDGE),
        _snap(now, CANON_ID, "polymarket", 0, SERIES_CANON_EDGE),
        _snap(now, GHOST_ID, "kalshi", 2, SERIES_TWIN_EDGE),
        _snap(now, GHOST_ID, "kalshi", 0, SERIES_TWIN_EDGE),
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
    """One fake session that answers BOTH routes.

    The two folds' projections are adjacent — `folded_probability_sources`
    selects `id, home_team_name, away_team_name, win_probability_sources`, which
    STARTS WITH `folded_series_event_ids`' projection — so a rig that asked
    `is_series_fold` first handed the blend fold three-tuples and
    `merge_probability_sources` unpacked a row of the wrong width. That was a
    prediction in `test_blend_fold_3810` until this repair drove both folds down
    one route and made it four red tests. `is_series_fold` is now EXCLUSIVE of
    the blend projection, so the two arms below are order-independent; they are
    still written longest-first, because a rig that reads correctly is worth
    more than one that merely runs correctly.
    """

    def __init__(self, now):
        self.now = now
        self.event = _event_row(now)
        self.blend_fold_lookups = 0
        self.series_fold_lookups = 0

    def _rows(self):
        return _snapshots(self.now)

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())

        if "FROM win_prob_snapshots" in sql:
            rows = self._rows()
            if "min(" in sql:
                return _Result([min(s.captured_at for s in rows)])
            return _Result(sorted(rows, key=lambda s: s.captured_at))
        if "FROM odds_snapshots" in sql:
            return _Result([])
        if is_blend_fold(sql):  # longer projection first — see the docstring
            self.blend_fold_lookups += 1
            return _Result(_blend_fold_rows(self.now))
        if is_series_fold(sql):
            self.series_fold_lookups += 1
            return _Result(_series_fold_rows())
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


@pytest.fixture()
def both_routes(monkeypatch):
    """Serve the detail page and its chart off one event, as a reader gets them."""
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
        events_route._event_detail_cache.clear()
        # ONE anchor for the pair, read HERE and not at import: the two routes
        # must be asked about the same instant, and that instant must be now.
        now = _now()
        detail_session = _RouteSession(now)
        history_session = _RouteSession(now)
        detail = asyncio.run(get_event(CANON_ID, db=detail_session))
        history = asyncio.run(
            get_event_odds_history(
                event_id=CANON_ID,
                hours=720,
                response=MagicMock(headers={}),
                db=history_session,
            )
        )
        return detail, history, history_session

    return _serve


def _edge(history):
    line = history.get("aggregate_line")
    assert line, "no blend line to pin — the fixture, not the ship, is broken"
    return line[-1]["home_probability"]


class TestTheTwoRoutesAgree:
    def test_the_chart_edge_and_the_hero_are_one_number(self, both_routes):
        """🔴 THE REPAIR. Standing ruling #1 across the route PAIR.

        Reverting `_pin_blend_edge`'s second argument to the raw `event` fails
        here and nowhere else in the #3911 suite.
        """
        detail, history, _ = both_routes()

        assert detail["hero_probability"] == pytest.approx(BLENDED)
        assert _edge(history) == pytest.approx(BLENDED)
        assert detail["hero_probability"] == pytest.approx(_edge(history))

        # 🔴 And the edge got there by being PINNED, not by the series happening
        # to end where the blend is. The bucket before the edge is drawn from
        # curves sitting at 0.85/0.90, so an unpinned line ends nowhere near
        # `BLENDED` — without this, the test passes whenever the pin silently
        # declines, and a stale fixture anchor makes it decline.
        line = history["aggregate_line"]
        assert len(line) >= 2, "need a bucket before the edge to compare against"
        assert line[-2]["home_probability"] > 0.8, (
            "the series itself must disagree with the point-in-time blend, or "
            "this test cannot tell a pinned edge from an unpinned one"
        )

    def test_the_unfolded_edge_would_have_been_the_canonicals_own_reading(self):
        """The negative control, computed rather than asserted from memory.

        Without this repair the pin's input is the raw row, whose only reading
        is polymarket — so the edge lands on 0.60 against a 0.40 hero. Pinning
        the number here means a future change to the aggregator that made the
        two coincide could not make the test above pass for the wrong reason.
        """
        raw = compute_aggregate_probability(_event_row(_now()), event_status="scheduled")

        assert raw == pytest.approx(CANON_PROB)
        assert raw != pytest.approx(BLENDED)

    def test_the_history_route_issued_the_blend_fold_lookup(self, both_routes):
        """The wiring, not only its effect.

        The effect above could in principle be produced by a chart that never
        folded but happened to blend to the same number; this cannot.
        """
        _, _, history_session = both_routes()

        assert history_session.blend_fold_lookups == 1
        assert history_session.series_fold_lookups >= 1

    def test_a_chart_with_no_blend_line_pays_no_lookup(self, monkeypatch):
        """The cost side of the repair, stated as a test.

        `_pin_blend_edge` returns on the first line for an empty
        `aggregate_line`, so a single-source chart — the common case — must not
        buy a fold it cannot use.
        """
        from app.routes import events as events_route

        class _OneSourceSession(_RouteSession):
            def _rows(self):
                return [s for s in _snapshots(self.now) if s.source == "polymarket"]

        session = _OneSourceSession(_now())
        history = asyncio.run(
            get_event_odds_history(
                event_id=CANON_ID,
                hours=720,
                response=MagicMock(headers={}),
                db=session,
            )
        )

        assert history.get("aggregate_line") is None
        assert session.blend_fold_lookups == 0
        assert events_route is not None  # import kept honest


class TestTheFixtureCannotExpire:
    """#3895 (`EXPIRING-TEST-ANCHORS`) — and here the failure is SILENT.

    The pre-match pin stands down once the newest bucket is older than
    `_PREMATCH_EDGE_MAX_AGE` (2 minutes), so an anchor this file cannot keep
    fresh does not turn the parity test red. It stops the pin ever firing, and
    two unpinned numbers can agree for the wrong reason.

    Two ways to get that wrong, and both have already happened in this repo:

      1. a calendar literal — a `datetime(...)` constructor with a written-out
         year, #3887's class. (This sentence deliberately does not SPELL one:
         the scan below would flag its own remedy text — the docstring-is-the
         -regression trap.)
      2. `datetime.now()` at MODULE level, which looks clock-tracking and is
         not. Pytest imports a shard's modules at collection and runs them
         minutes later; this file went red in CI shard 3/4 (358 files) on its
         first push and green in isolation, which is why `_now()` is a call.
    """

    def test_the_anchor_is_a_call_and_not_a_stored_instant(self):
        """Read the file: neither kind of stored anchor survives a slow shard."""
        source = Path(__file__).read_text()

        assert re.search(r"^def _now\(\):", source, re.M), "the anchor is a call"
        assert not re.search(r"datetime\(\s*\d{4}\s*,", source), (
            "a calendar literal anchors this file to a date it will outlive"
        )
        assert not re.search(r"^[A-Z_]+ = .*datetime\.now\(", source, re.M), (
            "a module-level `datetime.now()` is frozen at COLLECTION, not at "
            "run: it reads as clock-tracking and expires inside one pytest run"
        )

    def test_the_anchor_moves_between_calls(self):
        """`_now()` reports the wall clock, not a value it captured once."""
        first = _now()
        with patch(
            "tests.test_blend_fold_chart_pin_parity_3911.datetime"
        ) as fake:
            fake.now.return_value = first + timedelta(hours=3)
            later = _now()

        assert later - first == timedelta(hours=3)
