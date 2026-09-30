"""A /politics CARD'S "+N MORE" COUNTS THE RUNGS ITS PAGE SHOWS — #9109 follow-up.

#9109 stopped the card printing dead rungs, and the badge beside it was left on
`outcome_count - 3` — every rung the ladder ever had, including the passed ones
the page behind the card has dropped since #7784, less three rows the card may
no longer show.
Measured on production 2026-09-27 12:25Z (the first `/api/politics` build after
#9109 went live), 15 of the 25 cards that wore a badge over-counted:

    "When will the Senate vote on the SAVE America Act?"   (5466697)
        card:  Before Nov 3, 2026 7% · Before Oct 1, 2026 1% · "+9 more"
        page:  the same two rungs (`/api/futures/5466697`, 10 dropped)

The rungs below are production's, read from `futures_outcomes` that minute.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.politics import _market_row

NOW = datetime(2026, 9, 27, 12, 25, 0, tzinfo=timezone.utc)

# (name, current_probability, last_updated)
SAVE_ACT = [
    ("Before May 1, 2026", 0.0, "2026-06-09T08:47:04+00:00"),
    ("Before Apr 15, 2026", 0.0, "2026-06-09T08:47:04+00:00"),
    ("Before Apr 1, 2026", 0.0, "2026-06-07T04:47:01+00:00"),
    ("Before Mar 27, 2026", 0.0, "2026-05-31T02:47:22+00:00"),
    ("Before Mar 24, 2026", 0.0, "2026-05-28T08:47:00+00:00"),
    ("Before Mar 20, 2026", 0.0, "2026-05-26T04:47:09+00:00"),
    ("Before Aug 8, 2026", 0.0, "2026-09-27T11:40:02+00:00"),
    ("Before Jun 27, 2026", 0.0, "2026-08-28T20:50:07+00:00"),
    ("Before Jun 13, 2026", 0.0, "2026-08-18T22:52:21+00:00"),
    ("Before May 23, 2026", 0.0, "2026-07-22T22:51:53+00:00"),
    ("Before Nov 3, 2026", 0.065, "2026-09-27T06:55:06+00:00"),
    ("Before Oct 1, 2026", 0.01, "2026-09-27T06:55:06+00:00"),
]
GALLEGO = [
    ("Before Nov 3, 2026", 0.045, "2026-09-27T10:52:39+00:00"),
    ("Before Sep 1, 2026", 0.0, "2026-09-27T09:39:51+00:00"),
    ("Before Jun 1, 2026", 0.0, "2026-08-02T19:34:10+00:00"),
    ("Before Oct 1, 2026", 0.01, "2026-09-27T10:52:39+00:00"),
    ("Before Aug 1, 2026", 0.0, "2026-09-27T09:39:51+00:00"),
]
# One live rung carries no price: the card cannot show it, the page does.
MIFEPRISTONE = [
    ("27JAN", 0.12, "2026-09-25T14:48:51+00:00"),
    ("Before Jul 1, 2026", 0.0, "2026-09-01T22:49:00+00:00"),
    ("Before Jun 1, 2026", 0.0, "2026-07-09T18:49:38+00:00"),
    ("27", None, "2026-09-25T14:48:51+00:00"),
]

# (rungs, rows the card shows, rungs `/api/futures/{id}` served that minute)
SPECIMENS = {
    "save america act (5466697)": (SAVE_ACT, 2, 2),
    "gallego out (11617619)": (GALLEGO, 2, 2),
}
# A badge the old sum got right by coincidence. `4 - 3` — its page has one row
# more than the card — so it is the control that the new count keeps it right.
CONTROL = {"mifepristone (25926800)": (MIFEPRISTONE, 1, 2)}


def _market(rungs):
    return SimpleNamespace(
        id=1,
        name="When will it happen?",
        source="kalshi",
        external_id="kxtest",
        outcomes=[
            SimpleNamespace(
                id=i + 1,
                name=n,
                current_probability=p,
                probability_change_24h=None,
                rank=None,
                last_updated=t,
                is_winner=False,
            )
            for i, (n, p, t) in enumerate(rungs)
        ],
    )


def _row(rungs):
    return _market_row(_market(rungs), now=NOW)


class TestTheDefectReproduces:
    """🔴 RED-FIRST: the badge the card rendered, `outcome_count - 3`, over the
    row #9109 serves. Every specimen promised rungs its page does not have."""

    @pytest.mark.parametrize("specimen", sorted(SPECIMENS))
    def test_the_old_badge_over_counted(self, specimen):
        rungs, shown, page = SPECIMENS[specimen]
        row = _row(rungs)
        assert len(row["top_outcomes"]) == shown
        assert row["outcome_count"] - 3 > page - shown


class TestTheShip:
    @pytest.mark.parametrize("specimen", sorted({**SPECIMENS, **CONTROL}))
    def test_more_is_the_pages_rungs_the_card_does_not_show(self, specimen):
        rungs, shown, page = {**SPECIMENS, **CONTROL}[specimen]
        assert _row(rungs)["more_count"] == page - shown

    def test_save_act_no_longer_says_nine_more(self):
        assert _row(SAVE_ACT)["more_count"] == 0

    def test_an_unpriced_live_rung_is_still_more(self):
        """The page lists `27` with no price; the card cannot. A count taken
        over the priced rungs alone would hide that the page has another row."""
        row = _row(MIFEPRISTONE)
        assert row["outcome_count"] - 3 == 1  # the old badge, right by luck
        assert [o["name"] for o in row["top_outcomes"]] == ["27JAN"]
        assert row["more_count"] == 1

    def test_an_unpriced_dead_rung_is_not_more(self):
        """The page reads expiry over every rung and drops a passed date whether
        or not it was ever priced. A priced-only read would count it here."""
        rungs = [
            ("Before Jan 1, 2027", 0.2, None),
            ("Before Dec 1, 2026", 0.1, None),
            ("Before Nov 1, 2026", 0.05, None),
            ("Before Oct 15, 2026", 0.02, None),
            ("Before Jun 1, 2026", None, None),
            ("Before Jul 1, 2026", None, None),
        ]
        assert _row(rungs)["more_count"] == 1

    def test_outcome_count_keeps_the_ladders_arity(self):
        assert _row(SAVE_ACT)["outcome_count"] == 12


class TestControls:
    def test_an_undated_board_keeps_the_old_number(self):
        """A 30-name election has no deadlines: the badge reads as it always has."""
        rungs = [(f"Nominee {chr(65 + i)}", 0.3 - i * 0.01, None) for i in range(26)]
        rungs += [(f"Nominee A{i}", 0.01, None) for i in range(4)]
        row = _row(rungs)
        assert row["more_count"] == row["outcome_count"] - 3 == 27

    def test_a_ladder_whose_rungs_all_passed_is_never_emptied(self):
        """The page's "never the whole board": it lists all five, the card three."""
        rungs = [
            (f"Before {m} 1, 2026", 0.05, "2026-01-01T00:00:00+00:00")
            for m in ("Feb", "Mar", "Apr", "May", "Jun")
        ]
        row = _row(rungs)
        assert len(row["top_outcomes"]) == 3
        assert row["more_count"] == 2

    def test_a_live_ladder_longer_than_the_card(self):
        rungs = [
            ("Before Oct 15, 2026", 0.02, None),
            ("Before Nov 1, 2026", 0.04, None),
            ("Before Dec 1, 2026", 0.08, None),
            ("Before Jan 1, 2027", 0.12, None),
            ("Before Aug 1, 2026", 0.0, None),
        ]
        assert _row(rungs)["more_count"] == 1
