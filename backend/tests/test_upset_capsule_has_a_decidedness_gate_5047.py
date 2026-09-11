"""#5047 — "Upset brewing" needs a DECIDEDNESS gate, not just a direction gate.

THE PRODUCTION DEFECT, measured 2026-09-11 02:51Z on `GET /api/feed?limit=40`:
Discover **rank 2**, event 14632820 (SF @ LAR, the Netflix primetime opener):

    headline  "Upset brewing"
    reason    "San Francisco 49ers leading as underdog"
    score     7-24, "12:05 - 4th Quarter"
    odds      home 0.05 now, home 0.6429 at open
    tags      [... "signal:blowout" ... "status:live", "tier:1"]

Nothing about that card is stale — #4580's fix is working, the scoreboard really
does say the pre-game underdog is ahead, and the `reason` line beside it is
correct. What is wrong is the TENSE. "Brewing" promises a reader suspense the
game no longer has, and `signal:blowout` was sitting on the identical payload,
so one card asserted both "this might happen" and "this is over".

#4580 gave the capsule a gate on DIRECTION (does the scoreboard agree the
underdog is ahead?). This adds the gate on MAGNITUDE (does the market have any
doubt left?), which is the same hole #2753 records on the settled label.

The tests below are in two halves, and the second half is the one that matters:

* the new arm fires on the specimen, and
* it does NOT fire on the cards that must keep "Upset brewing" — the live
  Orlando City specimen #4580 banked, the boundary just under the threshold, and
  every row where the price is unknown. A gate that swallows its own predecessor
  is a regression wearing a fix's name.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.feed import _DISCOVER_EVENT_EXCEPTION_KEYWORDS
from app.utils.highlights import (
    BLOWOUT_THRESHOLD,
    compute_highlight,
    get_highlight_label,
    upset_is_no_longer_in_doubt,
)

NOW = datetime(2026, 9, 11, 2, 51, tzinfo=timezone.utc)


def _live(
    *,
    home_score,
    away_score,
    opening_home_prob=0.62,
    current_home_prob=0.44,
):
    """A live game whose favourite switched on price, scored as given.

    Same shape as `test_live_reason_is_earned_4580.py`'s helper deliberately:
    these two files describe one label and must not drift into two fixtures.
    Goes through the real `compute_highlight`, so a test here breaks if the
    switch classification moves and not merely if the string does.
    """
    return compute_highlight(
        status="live",
        commence_time=NOW - timedelta(hours=2, minutes=16),
        sport_key="americanfootball_nfl",
        opening_home_prob=opening_home_prob,
        opening_away_prob=1 - opening_home_prob,
        opening_favorite="home" if opening_home_prob > 0.5 else "away",
        current_home_prob=current_home_prob,
        current_away_prob=1 - current_home_prob,
        home_score=home_score,
        away_score=away_score,
        now=NOW,
    )


def _the_specimen():
    """SF @ LAR exactly as production served it at 02:51Z."""
    return _live(
        home_score=7,
        away_score=24,
        opening_home_prob=0.6429,
        current_home_prob=0.05,
    )


class TestTheDeterminationItself:
    """`upset_is_no_longer_in_doubt` — one derivation, tri-state like its two
    siblings, and it asks about the UNDERDOG's number rather than the board's."""

    def test_the_specimen_is_past_doubt(self):
        """Away opened underdog (1 - 0.6429 = 0.3571) and is now at 0.95."""
        assert upset_is_no_longer_in_doubt(0.6429, 0.05) is True

    def test_a_home_underdog_is_read_in_the_other_direction(self):
        """Home opened the underdog at 0.38 and is now at 0.91. Symmetry is not
        decoration here: reading `current_home_prob` without checking WHICH side
        opened short is how a direction-free threshold gets it backwards."""
        assert upset_is_no_longer_in_doubt(0.38, 0.91) is True

    def test_the_orlando_specimen_still_has_doubt_in_it(self):
        """The live card #4580 banked as CORRECT: underdog at 0.70, not 0.85."""
        assert upset_is_no_longer_in_doubt(0.62, 0.30) is False

    def test_exactly_at_the_threshold_counts(self):
        """`>=`, stated as a test so the boundary cannot be tightened silently."""
        assert upset_is_no_longer_in_doubt(0.62, 1 - BLOWOUT_THRESHOLD) is True

    def test_a_hair_short_of_the_threshold_does_not(self):
        assert (
            upset_is_no_longer_in_doubt(0.62, (1 - BLOWOUT_THRESHOLD) + 0.001) is False
        )

    @pytest.mark.parametrize(
        "opening,current",
        [(None, 0.05), (0.6429, None), (None, None)],
        ids=["no-open", "no-current", "neither"],
    )
    def test_a_missing_price_is_unknown_not_false(self, opening, current):
        """Tri-state, for #4580's reason: "we cannot say" is not "no". A caller
        that collapses None into False would print "Upset underway" — or refuse
        to — about a game it cannot price."""
        assert upset_is_no_longer_in_doubt(opening, current) is None

    def test_a_pick_em_has_no_underdog_to_be_past_doubt(self):
        assert upset_is_no_longer_in_doubt(0.5, 0.95) is None

    def test_the_favourite_running_away_is_not_a_decided_upset(self):
        """THE DIRECTION TRAP the helper exists for. The pre-game favourite
        opened 0.62 and is now at 0.90 — `flags.is_blowout` is True for this
        price, and it is emphatically not an upset. This assertion is what makes
        swapping the helper for the bare flag a detectable mutation."""
        assert upset_is_no_longer_in_doubt(0.62, 0.90) is False


class TestTheCapsule:
    """`get_highlight_label` — the two words on the card."""

    def test_the_specimen_no_longer_says_brewing(self):
        """THE DEFECT. Discover rank 2, 24-7, 4th quarter, favourite at 5%."""
        result = _the_specimen()
        assert result.flags.favorite_switched is True, (
            "fixture no longer reproduces the defect — the card only reached the "
            "upset capsule because the favourite switched on price"
        )
        assert result.flags.underdog_is_leading is True, (
            "fixture no longer reproduces the defect — #4580's direction gate is "
            "what admits this card to the branch at all"
        )
        assert get_highlight_label(result) != "Upset brewing"

    def test_the_specimen_says_what_is_actually_true(self):
        assert get_highlight_label(_the_specimen()) == "Upset underway"

    def test_the_row_that_says_blowout_does_not_also_say_brewing(self):
        """The self-contradiction, asserted as one statement: `signal:blowout`
        comes from `flags.is_blowout`, and it was on the same payload as the
        word "brewing"."""
        result = _the_specimen()
        assert result.flags.is_blowout is True
        assert "brewing" not in (get_highlight_label(result) or "").lower()

    def test_the_orlando_card_keeps_its_label(self):
        """THE KEEPER. Orlando City 3-1 at Atlanta United, served on production
        2026-09-10 and CORRECT, at `current_home_prob=0.30`. If this flips, the
        gate is not a gate, it is a deletion."""
        result = _live(
            home_score=1, away_score=3, opening_home_prob=0.62, current_home_prob=0.30
        )
        assert result.flags.underdog_is_leading is True
        assert get_highlight_label(result) == "Upset brewing"

    def test_a_price_we_cannot_read_keeps_brewing_rather_than_claiming_more(self):
        """`current_home_prob=None` cannot reach the capsule at all today
        (`favorite_switched` needs a price), so this pins the helper's own
        contract instead: unknown must not be read as decided."""
        assert upset_is_no_longer_in_doubt(0.6429, None) is None

    def test_the_direction_gate_from_4580_still_holds(self):
        """Belt and braces across the two files: a price switch over a level or
        favourite-led game is still "Odds moved", not either upset sentence."""
        assert get_highlight_label(_live(home_score=0, away_score=0)) == "Odds moved"
        assert get_highlight_label(_live(home_score=3, away_score=1)) == "Odds moved"


class TestTheRankDoesNotMove:
    """A copy fix that quietly re-ranks the card is not a copy fix.

    `_is_discover_event_demotion_exception` reads the headline as a lowercased
    string and matches `_DISCOVER_EVENT_EXCEPTION_KEYWORDS` by substring
    (`routes/feed.py`). "Upset underway" keeps the word, so the specimen keeps
    its exception — but that is a fact about the string, and a string is exactly
    the kind of thing a later rename breaks without noticing.
    """

    @pytest.mark.parametrize("label", ["Upset brewing", "Upset underway"])
    def test_both_capsules_still_match_the_exception_keywords(self, label):
        assert any(kw in label.lower() for kw in _DISCOVER_EVENT_EXCEPTION_KEYWORDS), (
            f"{label!r} matches no keyword in {_DISCOVER_EVENT_EXCEPTION_KEYWORDS} — "
            "the Discover demotion exception would stop firing and the card would "
            "be capped to 35 and cut by the noise filter (#4898's mechanism)"
        )

    def test_the_specimen_carries_the_keyword_through_the_real_function(self):
        label = get_highlight_label(_the_specimen())
        assert any(kw in label.lower() for kw in _DISCOVER_EVENT_EXCEPTION_KEYWORDS)
