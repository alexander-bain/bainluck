"""A tour-wide anchor must not swallow the next tournament. #2927 Phase 2.

THE PRODUCTION SHAPES THIS FILE IS BUILT FROM, all measured 2026-09-06 against
`futures_markets` (and confirmed at the venue's own API, standing notice 26):

* The 42 open `KXATPDOUBLES` rows we hold are for **2026-09-18 → 09-20** — the
  week AFTER the US Open. A `series` anchor is a whole tour, so "US Open 2026 ›
  Men's Doubles" anchored to it and left unbounded collects next week's tour
  and looks, from outside, like a container working unusually well.
* **All 29 open Kalshi tennis match markets carry a `commence_time` exactly 14
  days after their own ticker date.** `KXWTAMATCH-26SEP06SWIZHE` — Swiatek
  vs Zheng, played 2026-09-06, the match standing notice 27 names — is stored
  as `2026-09-20 15:00`. That is Kalshi's close time, not the match (gotcha
  #14). Kalshi's own `/markets?series_ticker=KXWTAMATCH&status=open` lists it
  with `close_time 2026-09-20T15:00:00Z`, so the +14 days is the venue's and
  not ours to argue with; ours is only which of the two dates we believe.

Both are pinned below as literal rows. The second is the one that matters: a
window test that trusted `commence_time` would have thrown tomorrow's final out
of the US Open and filed it under the tournament after — a wrong answer that
looks exactly like a right one, which is the failure class this whole program
exists to end.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest

from app.tasks.container_assembly import (
    WINDOW_IN,
    WINDOW_OUTSIDE,
    WINDOW_UNDATED,
    VenueHarvest,
    gather_venue_candidates,
    member_window_verdict,
)

# The US Open 2026 window, as a container would carry it.
USO_START = datetime(2026, 8, 24, tzinfo=timezone.utc)
USO_END = datetime(2026, 9, 8, tzinfo=timezone.utc)


def _t(y, m, d, hh=15, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# The window verdict — pure, graded by a table of real rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "external_id,commence,resolution,expected,why",
    [
        # THE ROW THIS FIX EXISTS FOR. Ticker says 9/6 (in window); the stored
        # commence says 9/20 (out). The ticker wins, so tomorrow's final is a
        # member of the tournament it was played in.
        (
            "KXWTAMATCH-26SEP06SWIZHE-SWI",
            _t(2026, 9, 20),
            _t(2026, 9, 20),
            WINDOW_IN,
            "Swiatek-Zheng, played 9/6, stored +14 days",
        ),
        (
            "KXATPMATCH-26SEP07GEAVAN",
            _t(2026, 9, 21),
            _t(2026, 9, 21),
            WINDOW_IN,
            "men's draw 9/7, stored +14 days",
        ),
        (
            "KXWTAMATCH-26SEP04OSAMER",
            _t(2026, 9, 18),
            _t(2026, 9, 18),
            WINDOW_IN,
            "9/4 fourth round, stored +14 days",
        ),
        # The other edition. Ticker says 9/18, which is after the window, so it
        # is refused however friendly its stored dates look.
        (
            "KXATPDOUBLES-26SEP18ABCDEF",
            _t(2026, 9, 18, 16, 10),
            _t(2026, 9, 18, 16, 10),
            WINDOW_OUTSIDE,
            "next week's tour, the 42 rows measured on production",
        ),
        (
            "KXWTADOUBLES-26SEP21ABCDEF",
            _t(2026, 9, 21),
            _t(2026, 9, 21),
            WINDOW_OUTSIDE,
            "the far end of next week's tour",
        ),
        # An earlier edition of the same series.
        (
            "KXATPMATCH-25SEP06ABCDEF",
            _t(2025, 9, 20),
            _t(2025, 9, 20),
            WINDOW_OUTSIDE,
            "last year's US Open, same series ticker",
        ),
        # Boundary days are inclusive at both ends: a ticker date equal to the
        # window's first or last calendar day is IN.
        ("KXATPMATCH-26AUG24ABCDEF", None, None, WINDOW_IN, "first day"),
        ("KXATPMATCH-26SEP08ABCDEF", None, None, WINDOW_IN, "last day"),
        ("KXATPMATCH-26AUG23ABCDEF", None, None, WINDOW_OUTSIDE, "day before"),
        ("KXATPMATCH-26SEP09ABCDEF", None, None, WINDOW_OUTSIDE, "day after"),
    ],
)
def test_ticker_date_decides_membership(external_id, commence, resolution, expected, why):
    assert (
        member_window_verdict(external_id, commence, resolution, USO_START, USO_END)
        == expected
    ), why


def test_ticker_outranks_the_stored_time_in_both_directions():
    """Not just "ticker in, column out" — the reverse is refused too.

    A guard that only checked the friendly direction would pass on a rule that
    read "admit if EITHER the ticker or the column is in the window", which
    admits every one of next week's markets whose close time happens to land
    inside our window.
    """
    # Ticker outside, stored times comfortably inside: still OUT.
    assert (
        member_window_verdict(
            "KXATPMATCH-26SEP18ABCDEF", _t(2026, 9, 1), _t(2026, 9, 2), USO_START, USO_END
        )
        == WINDOW_OUTSIDE
    )


@pytest.mark.parametrize(
    "commence,resolution,expected",
    [
        # No ticker date: fall back to the interval the stored times describe.
        (_t(2026, 9, 1), _t(2026, 9, 1), WINDOW_IN),
        (_t(2026, 6, 1), _t(2026, 9, 7), WINDOW_IN),  # outright: spans in
        (_t(2026, 6, 1), _t(2026, 6, 2), WINDOW_OUTSIDE),
        (_t(2026, 10, 1), _t(2026, 10, 2), WINDOW_OUTSIDE),
        (None, _t(2026, 9, 1), WINDOW_IN),  # one-sided is enough
        (_t(2026, 9, 1), None, WINDOW_IN),
        (None, None, WINDOW_UNDATED),
    ],
)
def test_interval_fallback_when_the_id_carries_no_date(commence, resolution, expected):
    assert (
        member_window_verdict("us-open-2026-mens-final", commence, resolution, USO_START, USO_END)
        == expected
    )


def test_undated_is_never_folded_into_outside():
    """Two findings, two fixes; one bucket would hide the second one forever."""
    assert (
        member_window_verdict("no-date-here", None, None, USO_START, USO_END)
        == WINDOW_UNDATED
    )
    assert WINDOW_UNDATED != WINDOW_OUTSIDE


def test_an_open_window_end_does_not_reject_the_future():
    """A container with a start and no end is still bounded on the left only."""
    assert (
        member_window_verdict("KXATPMATCH-26DEC01ABCDEF", None, None, USO_START, None)
        == WINDOW_IN
    )
    assert (
        member_window_verdict("KXATPMATCH-26JAN01ABCDEF", None, None, USO_START, None)
        == WINDOW_OUTSIDE
    )


# ---------------------------------------------------------------------------
# The gatherer — a fake session, so the SQL's shape is fixed but the decisions
# are the ones the code makes
# ---------------------------------------------------------------------------


@dataclass
class FakeAnchor:
    provider: str
    provider_id: str
    id_kind: str
    sport: Optional[str] = "tennis"


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeSession:
    """Returns the rows it was given, and records what it was asked."""

    def __init__(self, rows):
        self._rows = rows
        self.statements = []
        self.params = []

    async def execute(self, sql, params=None):
        self.statements.append(str(sql))
        self.params.append(params or {})
        return FakeResult(list(self._rows))


def _row(mid, name, external_id, commence, resolution, source="kalshi", mtype="binary"):
    return (mid, name, external_id, source, mtype, commence, resolution)


# The eight rows below are the real production shapes: six US Open match
# markets stored +14 days, and two of next week's tour.
_MIXED_SERIES_ROWS = [
    _row(1, "Iga Swiatek wins", "KXWTAMATCH-26SEP06SWIZHE-SWI", _t(2026, 9, 20), _t(2026, 9, 20)),
    _row(2, "Qinwen Zheng wins", "KXWTAMATCH-26SEP06SWIZHE-ZHE", _t(2026, 9, 20), _t(2026, 9, 20)),
    _row(3, "Coco Gauff wins", "KXWTAMATCH-26SEP07JOVGAU-GAU", _t(2026, 9, 21), _t(2026, 9, 21)),
    _row(4, "Iva Jovic wins", "KXWTAMATCH-26SEP07JOVGAU-JOV", _t(2026, 9, 21), _t(2026, 9, 21)),
    _row(5, "Naomi Osaka wins", "KXWTAMATCH-26SEP04OSAMER-OSA", _t(2026, 9, 18), _t(2026, 9, 18)),
    _row(6, "Elise Mertens wins", "KXWTAMATCH-26SEP04OSAMER-MER", _t(2026, 9, 18), _t(2026, 9, 18)),
    _row(7, "Next tour A", "KXWTAMATCH-26SEP18AAABBB-A", _t(2026, 10, 2), _t(2026, 10, 2)),
    _row(8, "Next tour B", "KXWTAMATCH-26SEP18AAABBB-B", _t(2026, 10, 2), _t(2026, 10, 2)),
]


@pytest.mark.asyncio
async def test_a_series_anchor_keeps_this_edition_and_drops_the_next():
    session = FakeSession(_MIXED_SERIES_ROWS)
    anchor = FakeAnchor("kalshi", "KXWTAMATCH", "series")

    harvest = await gather_venue_candidates(
        session, [anchor], window_start=USO_START, window_end=USO_END
    )

    assert isinstance(harvest, VenueHarvest)
    assert sorted(c.child_id for c in harvest.candidates) == [1, 2, 3, 4, 5, 6]
    account = harvest.by_anchor[0]
    assert account["matched"] == 8
    assert account["selected"] == 6
    assert account["outside_window"] == 2
    assert account["bounded_by_window"] is True
    assert harvest.summary()["outside_window"] == 2


@pytest.mark.asyncio
async def test_a_coarse_anchor_without_a_window_collects_nothing():
    """Fail closed. The alternative is a hub holding a whole tour."""
    session = FakeSession(_MIXED_SERIES_ROWS)
    anchor = FakeAnchor("kalshi", "KXATPDOUBLES", "series")

    harvest = await gather_venue_candidates(session, [anchor])

    assert harvest.candidates == []
    assert harvest.by_anchor == []
    assert harvest.refused_anchors == [
        {
            "provider": "kalshi",
            "id_kind": "series",
            "provider_id": "KXATPDOUBLES",
            "reason": "coarse_anchor_needs_window",
        }
    ]
    # And it did not even ask the database.
    assert session.statements == []


@pytest.mark.asyncio
async def test_an_exact_anchor_needs_no_window_and_is_not_filtered():
    """A Polymarket event slug already names one edition; the window adds nothing."""
    rows = [
        _row(11, "Alcaraz wins", "0xabc", None, None, source="polymarket"),
        _row(12, "Sinner wins", "0xdef", _t(2027, 1, 1), _t(2027, 1, 1), source="polymarket"),
    ]
    session = FakeSession(rows)
    anchor = FakeAnchor("polymarket", "us-open-mens-final", "event_slug")

    harvest = await gather_venue_candidates(session, [anchor])

    assert sorted(c.child_id for c in harvest.candidates) == [11, 12]
    assert harvest.refused_anchors == []
    assert harvest.by_anchor[0]["bounded_by_window"] is False
    assert harvest.by_anchor[0]["outside_window"] == 0


@pytest.mark.asyncio
async def test_undated_rows_under_a_coarse_anchor_are_counted_not_admitted():
    rows = [
        _row(21, "No date at all", "KXWTAMATCH-NODATE-A", None, None),
        _row(22, "Iga Swiatek wins", "KXWTAMATCH-26SEP06SWIZHE-SWI", None, None),
    ]
    session = FakeSession(rows)
    harvest = await gather_venue_candidates(
        session,
        [FakeAnchor("kalshi", "KXWTAMATCH", "series")],
        window_start=USO_START,
        window_end=USO_END,
    )

    assert [c.child_id for c in harvest.candidates] == [22]
    assert harvest.by_anchor[0]["undated"] == 1
    assert harvest.by_anchor[0]["outside_window"] == 0


@pytest.mark.asyncio
async def test_saturation_is_reported_rather_than_silently_truncating():
    rows = [
        _row(i, f"m{i}", f"KXWTAMATCH-26SEP06AAABBB-{i}", None, None)
        for i in range(1, 6)
    ]
    session = FakeSession(rows)

    harvest = await gather_venue_candidates(
        session,
        [FakeAnchor("kalshi", "KXWTAMATCH", "series")],
        window_start=USO_START,
        window_end=USO_END,
        limit=3,
    )

    assert harvest.truncated is True
    assert harvest.by_anchor[0]["truncated"] is True
    assert harvest.by_anchor[0]["matched"] == 3
    assert len(harvest.candidates) == 3
    assert harvest.summary()["truncated"] is True


@pytest.mark.asyncio
async def test_the_fetch_is_ordered_and_asks_for_one_row_past_the_cap():
    """Deterministic truncation, and a cap that can be SEEN to have filled."""
    session = FakeSession([])
    await gather_venue_candidates(
        session,
        [FakeAnchor("kalshi", "KXWTAMATCH", "series")],
        window_start=USO_START,
        window_end=USO_END,
        limit=100,
    )

    assert "ORDER BY fm.id" in session.statements[0]
    assert session.params[0]["limit"] == 101
    # The ticker date is read from a column, so the column must be selected.
    assert "fm.commence_time" in session.statements[0]
    assert "fm.resolution_date" in session.statements[0]


@pytest.mark.asyncio
async def test_a_wildcard_in_a_ticker_cannot_widen_the_pattern():
    session = FakeSession([])
    await gather_venue_candidates(
        session,
        [FakeAnchor("kalshi", "KX_ATP%MATCH", "series")],
        window_start=USO_START,
        window_end=USO_END,
    )
    assert session.params[0]["pattern"] == "KX\\_ATP\\%MATCH-%"


@pytest.mark.asyncio
async def test_an_anchor_kind_with_no_grouping_column_is_skipped_not_refused():
    """A `tournament` anchor belongs to the authority gatherer, not this one."""
    session = FakeSession(_MIXED_SERIES_ROWS)
    harvest = await gather_venue_candidates(
        session,
        [FakeAnchor("espn", "1234", "tournament")],
        window_start=USO_START,
        window_end=USO_END,
    )
    assert harvest.candidates == []
    assert harvest.refused_anchors == []
    assert harvest.by_anchor == []
    assert session.statements == []
