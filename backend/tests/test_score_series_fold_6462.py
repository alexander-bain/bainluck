"""#6462 — the SCORE series folds across a proven duplicate, like every other.

`get_event_odds_history` folds its odds series (#6399) and its win-probability
series (#3810) across the rows we decline to print, and read `score_snapshots`
on the canonical's id alone. On the two NFL pairs where the score series lives
on the suppressed twin, the page therefore drew a price curve, ten sportsbooks,
and no score at all.

Measured on production 2026-09-16, `GET /api/events/{id}/history?hours=720`:

    canonical 15196980   score_history  0   history 14   bookmaker_history 11
    ghost     15191796   score_history  8   history 91   bookmaker_history 11

WHY THIS RAIL IS NOT JUST ONE MORE SERIES
=========================================

`score_snapshots` has no source column, so an unfolded read does not drop a
venue out of a legend the way the odds fold did — it drops the whole line. And
`score_history` is read for more than the line: `lib/eventKeyStats.ts` calls it
the most direct in-game series and derives `computeRealStartTime` and
`defaultChartTimeRange` from it, while `ScoreDifferentialChart.hasPostStartData`
reads it to choose the game window over "all". An empty one also widens the
chart off the real game duration.

WHAT THESE TESTS GUARD, AND WHY EACH ONE EXISTS
===============================================

The ship is one line (`== event_id` → `.in_(series_event_ids)`), and on its own
that line is WRONG: it unions two rows' recordings of one game, which splices a
stale reading into a monotonic line and draws a score going BACKWARDS. So the
picker is as load-bearing as the widening, and both directions are mutated
below rather than asserted once.

The rig is `test_price_table_fold_6390._HistoryRouteSession`, subclassed rather
than copied — it is already hardened against the two fail-opens that let a
reverted `events.py` pass (its `_requested_ids` reads the scalar bind form as
well as the list one), and a second rig is how two readings of one route start
to disagree.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.models.models import Event, ScoreSnapshot, Sport
from tests.test_price_table_fold_6390 import _HistoryResult, _HistoryRouteSession

#: The production specimen — Raiders at Cardinals, 2026-08-13, completed.
CANON_ID = 15196980
GHOST_ID = 15191796
S_NFL = 90_006_462

KICKOFF = datetime(2026, 8, 13, 0, 0, tzinfo=timezone.utc)


def _score(event_id, *, minutes, home, away, snap_id=None):
    """One livescore reading. `captured_at` is what an interleave sorts on."""
    return ScoreSnapshot(
        id=snap_id if snap_id is not None else abs(hash((event_id, minutes))) % 10**6,
        event_id=event_id,
        captured_at=KICKOFF + timedelta(minutes=minutes),
        home_score=home,
        away_score=away,
    )


#: The fold's projection, `(id, home_team_name, away_team_name)`. Its own rows
#: rather than the price fold's, because `orientation_agrees` compares NAMES:
#: reusing the Ligue 1 pair's tuples against an NFL event refuses every fold and
#: turns all of this green for the wrong reason.
#:
#: The ghost spells the home side short, which is what production holds and what
#: the subset rule is for.
ALIGNED_GHOST = [
    (CANON_ID, "Arizona Cardinals", "Las Vegas Raiders"),
    (GHOST_ID, "Cardinals", "Las Vegas Raiders"),
]

#: The pair the orientation gate exists for: the ghost calls the Raiders home.
CROSSED_GHOST = [
    (CANON_ID, "Arizona Cardinals", "Las Vegas Raiders"),
    (GHOST_ID, "Las Vegas Raiders", "Arizona Cardinals"),
]

UNFOLDED = [(CANON_ID, "Arizona Cardinals", "Las Vegas Raiders")]

#: The ghost's full recording: eight readings, monotonic, spanning the game.
GHOST_SERIES = [
    _score(GHOST_ID, minutes=m, home=h, away=a, snap_id=6000 + i)
    for i, (m, h, a) in enumerate(
        [(0, 0, 0), (15, 7, 0), (30, 7, 3), (45, 7, 10),
         (60, 14, 10), (75, 14, 17), (90, 21, 17), (105, 21, 20)]
    )
]

#: The canonical's stale two-point stub, timestamped INSIDE the ghost's span and
#: still reading 0-0. Union the two and the drawn line falls from 14-10 back to
#: 0-0 and climbs again: the defect the picker exists to prevent, and one that
#: raises nothing.
CANON_STUB = [
    _score(CANON_ID, minutes=62, home=0, away=0, snap_id=7000),
    _score(CANON_ID, minutes=64, home=0, away=0, snap_id=7001),
]


class _ScoreHistorySession(_HistoryRouteSession):
    """`_HistoryRouteSession` that also answers the `score_snapshots` read.

    🔴 IT HONOURS THE FILTER, for the reason the parent's docstring gives: a
    fake that hands back every score row regardless answers the UNFOLDED query
    with the ghost's rows too, and the mutant that reverts this ship passes.
    The parent returns an empty `_HistoryResult` for this table, which would
    make every assertion below read zero and none of them fail.
    """

    def __init__(self, event, fold_rows, snapshots, score_snapshots):
        super().__init__(event, fold_rows, snapshots)
        self.score_snapshots = list(score_snapshots)
        #: Every id set the route asked `score_snapshots` for, so a test can
        #: assert the WIDENING itself and not only its visible effect.
        self.score_id_filters: list[set | None] = []

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())
        if "score_snapshots" in sql:
            ids = self._requested_ids(statement)
            self.score_id_filters.append(ids)
            rows = [
                s for s in self.score_snapshots if ids is None or s.event_id in ids
            ]
            return _HistoryResult(sorted(rows, key=lambda s: s.captured_at))
        return await super().execute(statement, *_a, **_kw)


def _route_event():
    """The specimen: a COMPLETED NFL fixture, which is what both pairs are."""
    return Event(
        id=CANON_ID,
        sport_id=S_NFL,
        home_team_name="Arizona Cardinals",
        away_team_name="Las Vegas Raiders",
        commence_time=KICKOFF,
        status="completed",
        home_score=20,
        away_score=21,
        completed_at=KICKOFF + timedelta(hours=3),
    )


def _history(fold_rows, score_snapshots, event=None):
    from app.routes import events as events_route

    event = event or _route_event()
    event.sport = Sport(id=S_NFL, key="americanfootball_nfl", name="NFL")
    session = _ScoreHistorySession(event, fold_rows, [], score_snapshots)
    payload = asyncio.run(
        events_route.get_event_odds_history(CANON_ID, hours=24, db=session)
    )
    return payload, session


def _drawn(payload):
    """`(home, away)` in drawn order — what the chart plots."""
    return [(p["home_score"], p["away_score"]) for p in payload["score_history"]]


class TestTheShip:
    def test_the_empty_score_chart_gains_the_ghosts_series(self):
        """The ship, on the production specimen's shape."""
        payload, _ = _history(ALIGNED_GHOST, GHOST_SERIES)

        assert len(payload["score_history"]) == len(GHOST_SERIES)
        assert _drawn(payload)[0] == (0, 0)
        assert _drawn(payload)[-1] == (21, 20), "the final score the page shows"

    def test_the_route_asks_score_snapshots_for_both_rows(self):
        """The widening itself, not only its visible effect."""
        _, session = _history(ALIGNED_GHOST, GHOST_SERIES)

        assert session.score_id_filters, "the route never queried score_snapshots"
        assert all(
            ids == {CANON_ID, GHOST_ID} for ids in session.score_id_filters
        ), session.score_id_filters

    def test_an_untagged_event_asks_for_exactly_its_own_id(self):
        """The no-op proof: an unfolded page compiles to the read it had."""
        _, session = _history(UNFOLDED, GHOST_SERIES)

        assert session.score_id_filters
        assert all(ids == {CANON_ID} for ids in session.score_id_filters)

    def test_an_untagged_events_own_series_is_served_unchanged(self):
        """The no-op is a no-op in the payload too, point for point.

        `score_id_filters` proving the narrow read would be satisfied by a
        route that then dropped every row on the floor — which is precisely
        what the picker does if it is reached with the wrong key.
        """
        own = [
            _score(CANON_ID, minutes=m, home=h, away=a, snap_id=8000 + i)
            for i, (m, h, a) in enumerate([(0, 0, 0), (30, 7, 0), (60, 7, 7)])
        ]
        payload, _ = _history(UNFOLDED, own)

        assert _drawn(payload) == [(0, 0), (7, 0), (7, 7)]


class TestOrientation:
    def test_a_crossed_ghost_draws_nothing_rather_than_an_inverted_score(self):
        """A `ScoreSnapshot` stores `home_score`, whose meaning comes from its
        OWN row's team slots.

        Folding a twin that disagrees about which side is home does not omit a
        line, it prints the loser winning — and on a COMPLETED game that
        contradicts the final score in the hero above it. Refusing is the only
        safe answer, and it is the same gate the odds series passes through.
        """
        payload, session = _history(CROSSED_GHOST, GHOST_SERIES)

        assert all(ids == {CANON_ID} for ids in session.score_id_filters)
        assert payload["score_history"] == []


class TestNoInterleave:
    """Two rows' score snapshots are two partial recordings of ONE game.

    Concatenating them by timestamp splices a stale reading into a monotonic
    line — a score that visibly goes backwards. Nothing raises, so only an
    assertion about the DRAWN values can catch it.
    """

    def test_the_stale_stub_is_discarded_whole(self):
        payload, _ = _history(ALIGNED_GHOST, GHOST_SERIES + CANON_STUB)

        assert len(payload["score_history"]) == len(GHOST_SERIES)
        assert (0, 0) not in _drawn(payload)[1:], "the stub was spliced in"

    def test_the_drawn_score_never_goes_backwards(self):
        """The reader-visible statement of the same fact.

        Stated on the values rather than on the row count because a future
        picker could keep the right NUMBER of points and still choose badly.
        """
        payload, _ = _history(ALIGNED_GHOST, GHOST_SERIES + CANON_STUB)

        drawn = _drawn(payload)
        assert all(
            later[0] >= earlier[0] and later[1] >= earlier[1]
            for earlier, later in zip(drawn, drawn[1:])
        ), drawn

    def test_the_stub_would_otherwise_have_been_spliced_in(self):
        """Anti-vacuity: the rig really did hand the route both rows.

        Without this, the two tests above pass on a session that silently
        dropped the canonical's score rows, and they would keep passing with
        the picker deleted.
        """
        _, session = _history(ALIGNED_GHOST, GHOST_SERIES + CANON_STUB)

        served = [
            s
            for s in GHOST_SERIES + CANON_STUB
            if s.event_id in (session.score_id_filters[0] or set())
        ]
        assert len(served) == len(GHOST_SERIES) + len(CANON_STUB)


class TestMutants:
    """The two substitutions a later reader is most likely to make."""

    def test_mutant_a_picker_that_names_no_row_draws_nothing(self, monkeypatch):
        """`.get()` returning None must empty the series, never union it.

        Patched on `proven_duplicates`, not on `routes.events`: the route
        imports the helper INSIDE the function, so the name is resolved from
        its own module on every call and a patch on `routes.events` would
        create an attribute nothing reads — a mutant that cannot fail.
        """
        monkeypatch.setattr(
            "app.utils.proven_duplicates.series_row_for_each_source",
            lambda _counts, _canon: {},
        )
        payload, _ = _history(ALIGNED_GHOST, GHOST_SERIES + CANON_STUB)

        drawn = _drawn(payload)
        assert drawn == [], (
            "a picker returning no row must draw nothing, never the union: "
            f"{drawn}"
        )

    def test_mutant_canonical_first_keeps_the_stub_over_the_real_series(
        self, monkeypatch
    ):
        """RICHEST, not CANONICAL — the substitution that reads as safer.

        "Prefer the canonical" is the rule a later reader reaches for, and on
        this fold it is backwards: the canonical is the poorer row by
        construction — that is the defect — so the page would keep a stale
        two-point stub over the ghost's real eight-point series.
        """
        monkeypatch.setattr(
            "app.utils.proven_duplicates.series_row_for_each_source",
            lambda _counts, canon: {"score": canon},
        )
        payload, _ = _history(ALIGNED_GHOST, GHOST_SERIES + CANON_STUB)

        assert _drawn(payload) == [(0, 0), (0, 0)], (
            "the canonical-first mutant should keep the stub — if this reads as "
            "the ghost's series the picker is not being consulted at all"
        )
