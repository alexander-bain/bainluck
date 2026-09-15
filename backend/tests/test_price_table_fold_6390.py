"""#6390 — a repaired duplicate's PRICES reach the canonical's page (Fold C).

THE READER-VISIBLE DEFECT
=========================

`/events/15311919` — Brest 0-1 Paris Saint-Germain, Ligue 1, completed —
rendered a final score and then nothing at all. The duplicate half worked: one
card in search, the hidden row `15297786` correctly tagged
`provenance:duplicate-of:15311919`. The content half did not. The hidden row
held 10 bookmakers; the canonical held 0.

`#2693` folded the market book onto the canonical, `#3810` Fold B folded the
chart's series and Fold A folded the blend's sources. `odds_snapshots` is the
member of that family nobody folded — so a pair whose content happened to be
odds_api PRICES rather than `futures_markets` rows was rescued by none of them.
Brest-PSG was the worst case only because NEITHER row had market rows, which
left the odds as the whole page.

Measured on production 2026-09-15, release `d36a0bad`, all 46 tagged soccer
pairs, read on the SERVED payload:

    15311919  Brest v Paris Saint-Germain   canonical  0 books  <  ghost 10
    15310934  Mainz v Eintracht Frankfurt   canonical  0 books  <  ghost 10
    15298413  Lazio v AC Milan              canonical  1 book   <  ghost 10

WHY THE ORIENTED FOLD AND NOT `folded_event_ids`
================================================

An `odds_snapshots` row stores `home_moneyline`, `home_win_probability`,
`home_spread` — numbers whose meaning is supplied entirely by ITS OWN event
row's `home_team_name`, exactly like the `win_prob_snapshots` row #3810 reasoned
about. `folded_event_ids` deliberately does NOT check orientation, because a
market names its own outcomes and means the same thing from either row. Fed
that set, this fold would print a crossed pair's prices with the two sides
swapped: a confident, exactly inverted price instead of a missing one, which is
worse than the omission being repaired. So the caller passes
`folded_series_event_ids`, and `TestOrientation` below is what holds it there.

WHY A PICKER AND NOT JUST A WIDER `IN`
======================================

`latest_odds_per_bookmaker_query` returns the latest row per
`(event, bookmaker)` — correct for a PAGE of events, wrong for a folded pair,
where a book present on both rows comes back twice. The list feeds
`aggregate_bookmaker_odds`, so the duplicate would be counted twice in the
consensus and would inflate the `bookmaker_count` the attribution mark prints.
`TestOneRowPerBookmaker` and `test_mutant_no_dedupe_double_counts_the_book`
are that half.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event, OddsSnapshot, Sport
from app.utils.proven_duplicates import latest_snapshot_for_each_bookmaker
from tests.test_series_fold_3810 import (
    blend_fold_row,
    is_blend_fold,
    is_series_fold,
)

CANON_ID = 15311919
GHOST_ID = 15297786
S_SOCCER = 90_006_390

KICKOFF = datetime(2026, 9, 13, 19, 0, tzinfo=timezone.utc)


def _snap(event_id, bookmaker, *, minutes=0, snap_id=None, home_ml=-150):
    """One bookmaker reading. `captured_at` is the key the picker ranks on."""
    return OddsSnapshot(
        id=snap_id if snap_id is not None else abs(hash((event_id, bookmaker))) % 10**6,
        event_id=event_id,
        bookmaker=bookmaker,
        captured_at=KICKOFF - timedelta(hours=2) + timedelta(minutes=minutes),
        home_moneyline=home_ml,
        away_moneyline=130,
        home_win_probability=0.6,
        away_win_probability=0.4,
    )


# ── THE PICKER ───────────────────────────────────────────────────────────────


class TestOneRowPerBookmaker:
    def test_a_book_on_both_rows_is_returned_once(self):
        rows = [_snap(CANON_ID, "pinnacle"), _snap(GHOST_ID, "pinnacle")]
        assert [s.bookmaker for s in latest_snapshot_for_each_bookmaker(rows, CANON_ID)] == [
            "pinnacle"
        ]

    def test_the_freshest_reading_wins_regardless_of_which_row_holds_it(self):
        stale_canonical = _snap(CANON_ID, "pinnacle", minutes=0, snap_id=1)
        fresh_ghost = _snap(GHOST_ID, "pinnacle", minutes=90, snap_id=2)
        picked = latest_snapshot_for_each_bookmaker(
            [stale_canonical, fresh_ghost], CANON_ID
        )
        assert [s.id for s in picked] == [2]

    def test_the_canonical_does_not_win_on_being_canonical(self):
        """The reason this fold exists is that the canonical is the poorer row."""
        fresh_ghost = _snap(GHOST_ID, "pinnacle", minutes=90, snap_id=2)
        stale_canonical = _snap(CANON_ID, "pinnacle", minutes=0, snap_id=1)
        picked = latest_snapshot_for_each_bookmaker(
            [fresh_ghost, stale_canonical], CANON_ID
        )
        assert picked[0].event_id == GHOST_ID

    def test_a_tie_breaks_to_the_canonical(self):
        ghost = _snap(GHOST_ID, "pinnacle", minutes=10, snap_id=9)
        canonical = _snap(CANON_ID, "pinnacle", minutes=10, snap_id=1)
        for order in ([ghost, canonical], [canonical, ghost]):
            picked = latest_snapshot_for_each_bookmaker(order, CANON_ID)
            assert picked[0].event_id == CANON_ID

    def test_a_tie_between_two_ghosts_is_still_deterministic(self):
        """Order-independence is the property; which id wins matters less."""
        a = _snap(777, "pinnacle", minutes=10, snap_id=1)
        b = _snap(888, "pinnacle", minutes=10, snap_id=2)
        forward = latest_snapshot_for_each_bookmaker([a, b], CANON_ID)
        backward = latest_snapshot_for_each_bookmaker([b, a], CANON_ID)
        assert [s.id for s in forward] == [s.id for s in backward]

    def test_disjoint_books_are_unioned(self):
        rows = [
            _snap(CANON_ID, "fanduel"),
            _snap(GHOST_ID, "pinnacle"),
            _snap(GHOST_ID, "draftkings"),
        ]
        assert [s.bookmaker for s in latest_snapshot_for_each_bookmaker(rows, CANON_ID)] == [
            "draftkings",
            "fanduel",
            "pinnacle",
        ]

    def test_an_unfolded_events_list_is_unchanged_element_for_element(self):
        """The recursive walk already emits bookmaker-ascending for one event."""
        rows = [
            _snap(CANON_ID, "betmgm"),
            _snap(CANON_ID, "draftkings"),
            _snap(CANON_ID, "pinnacle"),
        ]
        assert latest_snapshot_for_each_bookmaker(rows, CANON_ID) == rows

    def test_no_snapshots_is_no_rows_rather_than_a_raise(self):
        assert latest_snapshot_for_each_bookmaker([], CANON_ID) == []


# ── THE REAL ROUTE ───────────────────────────────────────────────────────────
#
# 🔴 Everything above proves the picker works. None of it would fail if
# `get_event` never called it, or called it with the WRONG id set. The route
# tests below are what make the ship load-bearing.


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
    """Answers the reads `get_event` makes, keyed on what each statement reads."""

    def __init__(self, event, fold_rows, snapshots):
        self.event = event
        self.fold_rows = list(fold_rows)
        self.snapshots = list(snapshots)
        #: Every id set the route asked `odds_snapshots` for, so a test can
        #: assert the WIDENING itself and not only its visible effect.
        self.odds_id_filters: list[set | None] = []

    @staticmethod
    def _requested_ids(statement):
        """The event ids this statement actually asked for.

        🔴 THE RIG HONOURS THE FILTER. A fake that returns every snapshot
        regardless answers an UNFOLDED query with the ghost's rows anyway — so
        the mutant that reverts the ship still passes. `Event.id.in_(ids)`
        binds the whole list under `id_1`.
        """
        for key, value in statement.compile().params.items():
            if key.startswith("id") and isinstance(value, (list, tuple, set)):
                return set(value)
        return None

    async def execute(self, statement, *_a, **_kw):
        sql = " ".join(str(statement).split())

        # FIRST: the odds CTE selects FROM events too, so a bare "FROM events"
        # test would swallow it and the page would serve no prices at all.
        if "odds_snapshots" in sql:
            ids = self._requested_ids(statement)
            self.odds_id_filters.append(ids)
            rows = [s for s in self.snapshots if ids is None or s.event_id in ids]
            # The production statement returns the latest row per
            # (event, bookmaker) — emulated here so the rig cannot be kinder
            # than the server about the very duplication the picker removes.
            latest: dict[tuple[int, str], OddsSnapshot] = {}
            for s in rows:
                key = (s.event_id, s.bookmaker)
                best = latest.get(key)
                if best is None or (s.captured_at, s.id) > (best.captured_at, best.id):
                    latest[key] = s
            return _Result([latest[k] for k in sorted(latest)])
        if is_blend_fold(sql):
            return _Result([blend_fold_row(self.event)])
        if is_series_fold(sql):
            return _Result(self.fold_rows)
        if "FROM events" in sql:
            return _Result([self.event])
        return _Result([])


def _route_event():
    """The specimen: a COMPLETED fixture, which is what all three pairs are."""
    return Event(
        id=CANON_ID,
        sport_id=S_SOCCER,
        home_team_name="Brest",
        away_team_name="Paris Saint-Germain",
        commence_time=KICKOFF,
        status="completed",
        home_score=0,
        away_score=1,
        completed_at=KICKOFF + timedelta(hours=2),
    )


#: The ghost as the oriented fold's projection returns it. `Paris Saint Germain`
#: without the hyphen is what production actually holds on `15297786`, and it
#: agrees: punctuation is dropped before the subset test.
ALIGNED_GHOST = [
    (CANON_ID, "Brest", "Paris Saint-Germain"),
    (GHOST_ID, "Brest", "Paris Saint Germain"),
]

#: The pair the orientation gate exists for: the ghost calls PSG the home side.
CROSSED_GHOST = [
    (CANON_ID, "Brest", "Paris Saint-Germain"),
    (GHOST_ID, "Paris Saint Germain", "Brest"),
]

UNFOLDED = [(CANON_ID, "Brest", "Paris Saint-Germain")]

#: What production holds: nothing on the canonical, ten books on the ghost.
GHOST_BOOKS = [
    "betmgm",
    "betrivers",
    "bovada",
    "caesars",
    "draftkings",
    "fanduel",
    "lowvig",
    "mybookieag",
    "pinnacle",
    "williamhill_us",
]
GHOST_SNAPSHOTS = [
    _snap(GHOST_ID, book, minutes=i, snap_id=100 + i)
    for i, book in enumerate(GHOST_BOOKS)
]


@pytest.fixture()
def serve(monkeypatch):
    """`get_event` with its heavy reads stubbed, returning the real payload."""
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

    def _serve(event, fold_rows, snapshots):
        event.sport = Sport(id=S_SOCCER, key="soccer_france_ligue_one", name="Ligue 1")
        events_route._event_detail_cache.clear()
        session = _RouteSession(event, fold_rows, snapshots)
        payload = asyncio.run(events_route.get_event(CANON_ID, db=session))
        events_route._event_detail_cache.clear()
        return payload, session

    return _serve


def _books(payload):
    return [b["bookmaker"] for b in payload.get("bookmaker_odds", [])]


class TestTheRealRoute:
    def test_the_empty_page_gains_the_ghosts_ten_books(self, serve):
        """The ship: Brest-PSG stops rendering a score and nothing else."""
        payload, _ = serve(_route_event(), ALIGNED_GHOST, GHOST_SNAPSHOTS)
        assert _books(payload) == GHOST_BOOKS

    def test_the_route_asked_odds_snapshots_for_both_ids(self, serve):
        """The wiring, not merely its visible effect."""
        _, session = serve(_route_event(), ALIGNED_GHOST, GHOST_SNAPSHOTS)
        assert session.odds_id_filters == [{CANON_ID, GHOST_ID}]

    def test_a_book_on_both_rows_is_not_counted_twice(self, serve):
        """`bookmaker_count` feeds the attribution mark a reader actually reads."""
        # PREGAME like the other ten: a post-kickoff reading would be the only
        # row `filter_stale_bookmaker_snapshots` keeps, and the count would be
        # measuring that filter rather than this picker.
        both = GHOST_SNAPSHOTS + [
            _snap(CANON_ID, "pinnacle", minutes=50, snap_id=500)
        ]
        payload, _ = serve(_route_event(), ALIGNED_GHOST, both)
        assert _books(payload) == GHOST_BOOKS
        assert payload["current_odds"]["bookmaker_count"] == len(GHOST_BOOKS)

    def test_an_untagged_event_is_unchanged_through_the_real_route(self, serve):
        own = [_snap(CANON_ID, "pinnacle", snap_id=7)]
        payload, session = serve(_route_event(), UNFOLDED, own)
        assert _books(payload) == ["pinnacle"]
        assert session.odds_id_filters == [{CANON_ID}]


class TestOrientation:
    """A crossed ghost's prices are inverted. Refusing them is the whole gate."""

    def test_a_crossed_ghost_contributes_no_prices_at_all(self, serve):
        payload, _ = serve(_route_event(), CROSSED_GHOST, GHOST_SNAPSHOTS)
        assert _books(payload) == []

    def test_the_crossed_ghosts_ids_never_reach_the_odds_query(self, serve):
        """Dropped by the fold, not filtered out afterwards."""
        _, session = serve(_route_event(), CROSSED_GHOST, GHOST_SNAPSHOTS)
        assert session.odds_id_filters == [{CANON_ID}]


class TestMutants:
    """Each reverts one half of the ship; each must go RED."""

    def test_mutant_unfolded_query_loses_every_price(self, serve, monkeypatch):
        """The ship itself: back to `[event_id]` and the page is empty again."""
        async def _unfolded(_db, canonical_event_id):
            return [canonical_event_id]

        # The string form, so this module never imports `proven_duplicates` both
        # as a module and by name (CodeQL `py/import-and-import-from`).
        monkeypatch.setattr(
            "app.utils.proven_duplicates.folded_series_event_ids", _unfolded
        )
        payload, _ = serve(_route_event(), ALIGNED_GHOST, GHOST_SNAPSHOTS)
        assert _books(payload) == []

    def test_mutant_unoriented_fold_admits_the_crossed_ghost(
        self, serve, monkeypatch
    ):
        """Swap in the MARKET fold and a crossed pair's prices are served
        inverted. Nothing else in the system would catch this."""
        async def _market_fold(_db, canonical_event_id):
            return [canonical_event_id, GHOST_ID]

        monkeypatch.setattr(
            "app.utils.proven_duplicates.folded_series_event_ids", _market_fold
        )
        payload, _ = serve(_route_event(), CROSSED_GHOST, GHOST_SNAPSHOTS)
        assert _books(payload) == GHOST_BOOKS  # the defect the real fold refuses

    def test_mutant_no_dedupe_double_counts_the_book(self, serve, monkeypatch):
        """Drop the picker and Pinnacle is printed twice and counted twice."""
        monkeypatch.setattr(
            "app.utils.proven_duplicates.latest_snapshot_for_each_bookmaker",
            lambda snaps, _canon: list(snaps),
        )
        # PREGAME like the other ten: a post-kickoff reading would be the only
        # row `filter_stale_bookmaker_snapshots` keeps, and the count would be
        # measuring that filter rather than this picker.
        both = GHOST_SNAPSHOTS + [
            _snap(CANON_ID, "pinnacle", minutes=50, snap_id=500)
        ]
        payload, _ = serve(_route_event(), ALIGNED_GHOST, both)
        assert _books(payload).count("pinnacle") == 2
        assert payload["current_odds"]["bookmaker_count"] == len(GHOST_BOOKS) + 1
