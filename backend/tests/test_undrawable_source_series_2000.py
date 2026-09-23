"""#2000: the chart legend stops naming a source it cannot draw.

`OddsChart.tsx:861` admits a source to the legend on `points.length === 0` — the
only series it refuses is an empty one — and every series is stroked
`dot={false}` (`OddsChart.tsx:1941, 2604, 2654, 2687, 2704, 2720`). So a series
of ONE point renders literally nothing and is named in the legend regardless.

🔴 THE ONE POINT IS USUALLY NOT THE SOURCE'S OWN READING, which is why this is a
truth defect and not a tidy-up. The terminal point (`events.py:24584`) is
appended to every non-empty series and carries OUR resolved result;
`_omit_pre_kickoff_points` then removes the pre-kick-off readings that made the
series non-empty. A source that stopped quoting at kick-off therefore reaches
the reader as a single synthesised point in that source's colour, and the legend
credits a venue for a number the venue never published.

Measured on production 2026-09-23, `?range=since_start` (the view a finished
game opens on), 50 recent completed events / 134 served source-series:

    polymarket   1 point   4 series   <- every one of them, zero rows at kickoff+
    polymarket   2+        14
    kalshi       2+        49
    espn         2+        23
    stat_model   2+        28
    mlb          2+        16

All four one-point series had **zero** `win_prob_snapshots` rows at or after
kick-off, so each was the synthesised point alone; `15316869` and `15316876`
hold 386 and 450 pre-kick-off readings apiece. Specimen `15011303` (Real
Sociedad 4-1 Real Betis) is the same shape on kalshi — its one surviving row is
a 2026-07-10 reading of 0.01 left behind by the mis-link #2000's first repair
moved away — and its expanded legend on production named "Kalshi" above a plot
carrying no Kalshi mark.

🔴 THE DEFECT CANNOT BE READ OFF THE SERVED PAYLOAD. `_project_served_game_state`
narrows `game_state` to `_SERVED_GAME_STATE_KEYS`, which does not contain
`final`, so the terminal point's `{"final": True}` is served as `None` and is
indistinguishable from a real reading. The first cut of the production
measurement keyed on that flag and reported "synthetic: None" for all four —
a column that could never read True. The discriminator is `win_prob_snapshots`.

🔴 WHY THESE ARE NOT VACUOUS — the specimen travels the REAL seam. The rig feeds
`win_prob_snapshots` rows to the route and lets the route build the series,
append its own terminal point and run its own trim; nothing is injected into
`win_prob_history` after the fact. That is deliberate: the sibling ship on this
branch was BLOCKED (CERT-3324) for a guard that placed its specimen downstream
of the selection it claimed to prove.

Mutated back individually on the finished module and re-run (`/tmp/mut2000.py`,
2026-09-23; each mutant asserted to be a real textual change before it counted,
and the module restored byte-identical afterwards):

    M1  withhold never called by the route        -> 3 red  (the ship)
    M2  `len(points) >= 2` widened to `> 2`       -> 3 red  (the controls bite)
    M3  series popped instead of emptied          -> 5 red  (the shape contract)
    M4  `snapshot_count` left at 1                -> 1 red  (the rendered count)
    M5  called BEFORE the trim instead of after   -> 3 red  (since_start specimen)

M2 is the one that matters: it is the shape in which this ship could delete a
series a reader is being drawn today, and the two-reading controls catch it.
M5 is the ordering claim — run ahead of the trim, the helper sees the
pre-kick-off reading still in the series, judges it drawable and leaves the
reader exactly where they started.

The controls are green before and after the fix by design: a control that goes
red under the fix was testing the fix instead of guarding it.

Clock: anchors come from `test_history_window_budget_6921`, which is swept
12/12; gotcha #44 is why `_kickoff()` has no `if` in it.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta, timezone

from app.models.models import WinProbSnapshot
from app.routes.events import (
    EVENT_HISTORY_RANGE_SINCE_START,
    _withhold_undrawable_source_series,
    get_event_odds_history,
)
from tests.test_history_window_budget_6921 import (
    EVENT_ID,
    _finished_event,
    _kickoff,
)
from tests.test_price_table_fold_6390 import (
    _HistoryResult,
    _HistoryRouteSession,
)

UTC = timezone.utc


class _WinProbRouteSession(_HistoryRouteSession):
    """`_HistoryRouteSession`, plus the `win_prob_snapshots` read it answers empty.

    🔴 IT HONOURS THE TIME BOUNDS, for the reason the parent's
    `_captured_at_bounds` docstring gives about the odds read: the route bounds
    this query with `captured_at >= cutoff` and, on a finished event,
    `<= end_cap`. A stub that returns every row regardless cannot witness a
    route that dropped a bound, and — worse here — would hand the since_start
    specimen its pre-kick-off row back after the trim had removed it, which is
    precisely the state this ship is about.
    """

    def __init__(self, event, fold_rows, snapshots, wp_snapshots):
        super().__init__(event, fold_rows, snapshots)
        self.wp_snapshots = list(wp_snapshots)
        self.wp_reads = 0

    async def execute(self, statement, *a, **kw):
        sql = " ".join(str(statement).split())
        if "CAST(events.event_tags AS VARCHAR) LIKE" in sql:
            # `folded_probability_sources` — this specimen has no tagged twin.
            # It must be answered BEFORE the parent's `FROM events` branch,
            # which hands back the Event entity; this query selects four
            # columns and unpacks them, so the entity raises `TypeError:
            # cannot unpack non-iterable Event object` four frames down.
            # Reached only once a second source puts points on the aggregate
            # line, which is why it surfaced on one test and not the others.
            #
            # 🔴 THE PREDICATE, NOT THE COLUMNS. Keying on `event_tags` and
            # `win_probability_sources` appearing together also matched
            # `select(Event)` — both are Event columns — and swallowed the
            # route's own event fetch, turning one red into seven. Only the
            # WHERE clause is unique to the fold.
            return _HistoryResult([])
        if "win_prob_snapshots" in sql:
            self.wp_reads += 1
            bounds = self._captured_at_bounds(statement)
            ids = self._requested_ids(statement)
            rows = [
                s
                for s in self.wp_snapshots
                if (ids is None or s.event_id in ids)
                and self._within_bounds(s, bounds)
            ]
            rows.sort(key=lambda s: s.captured_at)
            return _HistoryResult(rows)
        return await super().execute(statement, *a, **kw)


def _wp(when, *, source="kalshi", home=0.62, snap_id):
    return WinProbSnapshot(
        id=snap_id,
        event_id=EVENT_ID,
        source=source,
        captured_at=when,
        home_win_probability=home,
        away_win_probability=round(1.0 - home, 4),
        draw_probability=None,
        game_state=None,
        reading_count=1,
        valid_until=None,
    )


def _serve(wp_snapshots, *, chart_range=None):
    """Run the real route over a finished event carrying these readings."""
    kickoff = _kickoff()
    event = _finished_event(kickoff)
    session = _WinProbRouteSession(event, [], [], wp_snapshots)
    kwargs = {"chart_range": chart_range} if chart_range else {}
    payload = asyncio.run(
        get_event_odds_history(EVENT_ID, hours=48, db=session, **kwargs)
    )
    return payload, session, kickoff


def _kalshi(payload):
    return payload["win_prob_history"].get("kalshi")


def _count(payload):
    return payload["win_prob_sources"].get("kalshi", {}).get("snapshot_count")


# ---------------------------------------------------------------------------
# The ship
# ---------------------------------------------------------------------------


def test_a_source_stranded_on_the_synthesised_final_point_is_not_offered():
    """The specimen. One pre-kick-off reading, trimmed away, terminal point left.

    This is `15011303`'s shape: the only real kalshi row predates kick-off, the
    reader's default view removes it, and what remains is the result we resolved
    ourselves wearing Kalshi's colour.
    """
    kickoff = _kickoff()
    stranded = [_wp(kickoff - timedelta(days=47), home=0.01, snap_id=8_094_979)]

    payload, _, _ = _serve(stranded, chart_range=EVENT_HISTORY_RANGE_SINCE_START)

    assert _kalshi(payload) == [], (
        "a series of one point draws nothing (`dot={false}`) and must not be "
        "offered as a source"
    )


def test_the_legend_entry_goes_with_the_series():
    """`snapshot_count` is rendered, so it may not still advertise the point."""
    kickoff = _kickoff()
    stranded = [_wp(kickoff - timedelta(days=47), home=0.01, snap_id=8_094_979)]

    payload, _, _ = _serve(stranded, chart_range=EVENT_HISTORY_RANGE_SINCE_START)

    assert _count(payload) == 0


def test_the_series_is_emptied_and_not_popped():
    """The shape contract this route already keeps for a hollowed-out series.

    `_omit_pre_kickoff_points` and #1828's `_filter_state_bearing_rows` both
    empty rather than remove, so no client meets a shape this route does not
    already serve. It is load-bearing here because `win_prob_sources` has a
    second consumer that never reads the series at all —
    `app/events/[id]/models/page.tsx:145` iterates the metadata with no count
    filter — so popping the key would drop a card off that page as well: a
    second, unmeasured change riding a chart fix.
    """
    kickoff = _kickoff()
    stranded = [_wp(kickoff - timedelta(days=47), home=0.01, snap_id=8_094_979)]

    payload, _, _ = _serve(stranded, chart_range=EVENT_HISTORY_RANGE_SINCE_START)

    assert "kalshi" in payload["win_prob_history"], "the key stays"
    assert "kalshi" in payload["win_prob_sources"], "the metadata entry stays"


def test_the_route_really_did_build_the_one_point_series_first():
    """The reachability claim, stated against the rig rather than assumed.

    Without this the four assertions above are also satisfied by a route that
    never built a kalshi series at all — a rig whose `win_prob_snapshots` read
    returned nothing would pass every one of them. On the untrimmed range the
    same population yields TWO points: the reading and the appended terminal.
    """
    kickoff = _kickoff()
    stranded = [_wp(kickoff - timedelta(days=47), home=0.01, snap_id=8_094_979)]

    payload, session, _ = _serve(stranded)

    assert session.wp_reads == 1, "the route read win_prob_snapshots exactly once"
    assert len(_kalshi(payload)) == 2, (
        "the reading plus the terminal point the route appends for a finished game"
    )
    assert _kalshi(payload)[-1]["home_probability"] == 1.0, (
        "the terminal point carries OUR resolved result (home won 24-21)"
    )


# ---------------------------------------------------------------------------
# Controls — green before AND after the fix
# ---------------------------------------------------------------------------


def test_a_source_with_two_in_game_readings_is_drawn_and_kept():
    """The opposite branch of the gate: a series that CAN draw is untouched."""
    kickoff = _kickoff()
    healthy = [
        _wp(kickoff + timedelta(minutes=10), home=0.55, snap_id=9_000_001),
        _wp(kickoff + timedelta(minutes=70), home=0.71, snap_id=9_000_002),
    ]

    payload, _, _ = _serve(healthy, chart_range=EVENT_HISTORY_RANGE_SINCE_START)

    assert len(_kalshi(payload)) == 3, "two readings plus the terminal point"
    assert _count(payload) == 3


def test_one_in_game_reading_still_draws_because_the_terminal_joins_it():
    """The boundary, and the reason the rule counts SERVED points.

    A single in-window reading is not the defect: the terminal point lands
    in-window too, so the pair draws a real segment from the source's own last
    quote to the result. Only a series whose companion was trimmed away is left
    undrawable.
    """
    kickoff = _kickoff()
    one_in_game = [_wp(kickoff + timedelta(minutes=30), home=0.64, snap_id=9_000_003)]

    payload, _, _ = _serve(one_in_game, chart_range=EVENT_HISTORY_RANGE_SINCE_START)

    assert len(_kalshi(payload)) == 2
    assert _count(payload) == 2


def test_a_second_source_is_judged_on_its_own_points():
    """Withholding one series may not disturb a sibling in the same payload."""
    kickoff = _kickoff()
    mixed = [
        _wp(kickoff - timedelta(days=47), home=0.01, snap_id=8_094_979),
        _wp(kickoff + timedelta(minutes=10), source="espn", home=0.58, snap_id=9_100_001),
        _wp(kickoff + timedelta(minutes=70), source="espn", home=0.66, snap_id=9_100_002),
    ]

    payload, _, _ = _serve(mixed, chart_range=EVENT_HISTORY_RANGE_SINCE_START)

    assert _kalshi(payload) == []
    assert len(payload["win_prob_history"]["espn"]) == 3, "the sibling is untouched"


# ---------------------------------------------------------------------------
# The helper on its own — the branches the route cannot reach cheaply
# ---------------------------------------------------------------------------


def test_an_already_empty_series_is_not_counted_as_withheld():
    """Nothing was withheld from a reader who was never going to see it."""
    history = {"kalshi": []}
    meta = {"kalshi": {"snapshot_count": 0}}

    assert _withhold_undrawable_source_series(history, meta) == 0
    assert history == {"kalshi": []}
    assert meta["kalshi"]["snapshot_count"] == 0


def test_the_return_value_counts_only_the_series_it_emptied():
    history = {
        "kalshi": [{"timestamp": "t1"}],
        "polymarket": [{"timestamp": "t1"}, {"timestamp": "t2"}],
        "espn": [],
    }
    meta = {
        "kalshi": {"snapshot_count": 1},
        "polymarket": {"snapshot_count": 2},
        "espn": {"snapshot_count": 0},
    }

    assert _withhold_undrawable_source_series(history, meta) == 1
    assert history["kalshi"] == []
    assert len(history["polymarket"]) == 2, "the drawable series is untouched"
    assert meta["polymarket"]["snapshot_count"] == 2


def test_a_series_with_no_metadata_entry_is_still_emptied():
    """The two dicts are built separately; the series is the thing that draws."""
    history = {"kalshi": [{"timestamp": "t1"}]}

    assert _withhold_undrawable_source_series(history, {}) == 1
    assert history["kalshi"] == []
