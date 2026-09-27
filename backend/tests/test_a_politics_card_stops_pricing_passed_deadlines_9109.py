"""A /politics CARD STOPS PRICING DEADLINES THAT HAVE PASSED — #9109.

Seen on production 2026-09-27 at 390px (`/api/politics` built 09:25:01Z):

    "When will Nick Adams be confirmed as Ambassador of Malaysia?"
        card:  Yes 0.8% · Before Apr 1, 2026 3% · Before Jul 1, 2026 0%
        page:  Yes 0.8%                      (`/api/futures/109434`, 2 dropped)

#3758 sorted an expired rung below the live ones but kept it, so a ladder with
fewer than three live rungs filled the card's spare slots with dead dates. #7784
then made the page the card opens DROP them through the same helper. The card
now shows what the page shows.

The rungs below are the served ones, read off the payload that day.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.politics import _market_row
from app.utils.market_staleness import expired_ladder_rungs

NOW = datetime(2026, 9, 27, 9, 55, 0, tzinfo=timezone.utc)

# (served rungs, what the card may show)
SPECIMENS = {
    "nick adams malaysia (109434)": (
        [("Yes", 0.008), ("Before Apr 1, 2026", 0.03), ("Before Jul 1, 2026", 0.0)],
        ["Yes"],
    ),
    "farm bill (54171486)": (
        [
            ("Before Jan 1, 2027", 0.155),
            ("Before Jun 1, 2026", 0.0),
            ("Before Jul 1, 2026", 0.0),
        ],
        ["Before Jan 1, 2027"],
    ),
    "schumer out (112806)": (
        [("Before Nov 3, 2026", 0.0215), ("Before 2026", 0.01), ("Before July 2026", 0.0)],
        ["Before Nov 3, 2026"],
    ),
    "trump visit iran (2168068)": (
        [
            ("Before Jan 1, 2027", 0.029),
            ("Before Apr 1, 2026", 0.01),
            ("Before May 1, 2026", 0.009),
        ],
        ["Before Jan 1, 2027"],
    ),
}

# Live ladders on the same payload: nothing about them may move.
CONTROLS = {
    "natalie harp (59693666)": [
        ("Before Jan 1, 2027", 0.185),
        ("Before Dec 1, 2026", 0.115),
        ("Before Oct 1, 2026", 0.06),
    ],
    "kash patel (8817578)": [
        ("Before Dec 1, 2026", 0.17),
        ("Before Nov 1, 2026", 0.075),
        ("Before Oct 1, 2026", 0.015),
    ],
}


def _market(rungs, *, winners=()):
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
                last_updated=None,
                is_winner=n in winners,
            )
            for i, (n, p) in enumerate(rungs)
        ],
    )


def _names(rungs, **kw):
    row = _market_row(_market(rungs, **kw), now=NOW)
    return [o["name"] for o in row["top_outcomes"]], row


class TestTheDefectReproduces:
    """🔴 RED-FIRST: #3758's demote-only order, hand-written, over the same
    rungs. Every specimen put a dead date on the card under it."""

    @pytest.mark.parametrize("specimen", sorted(SPECIMENS))
    def test_the_demote_only_card_showed_a_passed_date(self, specimen):
        rungs, _ = SPECIMENS[specimen]
        expired = expired_ladder_rungs(rungs, NOW)
        old = sorted(rungs, key=lambda r: (r[0] in expired, -r[1]))[:3]
        assert any(n in expired for n, _ in old)


class TestTheShip:
    @pytest.mark.parametrize("specimen", sorted(SPECIMENS))
    def test_the_card_shows_only_rungs_that_can_still_happen(self, specimen):
        rungs, want = SPECIMENS[specimen]
        names, row = _names(rungs)
        assert names == want
        assert row["prob"] == row["top_outcomes"][0]["prob"]

    def test_nick_adams_no_longer_offers_three_percent_on_april(self):
        names, row = _names(SPECIMENS["nick adams malaysia (109434)"][0])
        assert "Before Apr 1, 2026" not in names
        assert all(o["prob"] != 3.0 for o in row["top_outcomes"])

    @pytest.mark.parametrize("specimen", sorted(CONTROLS))
    def test_a_live_ladder_is_untouched(self, specimen):
        rungs = CONTROLS[specimen]
        names, _ = _names(rungs)
        assert names == [n for n, _ in sorted(rungs, key=lambda r: -r[1])]

    @pytest.mark.parametrize("specimen", sorted(SPECIMENS))
    def test_the_arity_still_counts_every_rung(self, specimen):
        rungs, _ = SPECIMENS[specimen]
        _, row = _names(rungs)
        assert row["outcome_count"] == len(rungs)

    def test_never_the_whole_board(self):
        rungs = [("Before Apr 1, 2026", 0.03), ("Before Jul 1, 2026", 0.015)]
        names, _ = _names(rungs)
        assert names == ["Before Apr 1, 2026", "Before Jul 1, 2026"]

    def test_a_graded_winner_on_a_passed_date_is_kept(self):
        """CERT-3236's clause rides the helper: a rung the venue declared the
        winner is not a dead option, whatever its date."""
        rungs = [("Before Jan 1, 2027", 0.99), ("Before Sep 1, 2026", 0.99)]
        names, _ = _names(rungs, winners=("Before Sep 1, 2026",))
        assert "Before Sep 1, 2026" in names

    def test_the_card_and_the_page_agree_on_which_rungs_are_real(self):
        """The contract #9109 restores, stated against the helper both routes
        call: nothing the card shows is in the page's dropped set, unless every
        rung is."""
        for rungs, _ in SPECIMENS.values():
            names, _ = _names(rungs)
            assert not set(names) & expired_ladder_rungs(rungs, NOW)
