"""#7792 — a 2027 board's "Part of:" link must not open the settled 2026 tournament.

The sibling of #7782 in the two domains that have no edition CONFIG to compare
against. `derive_market_concept_key` resolves tennis and F1 by `clean_slug(name)`
and golf majors by a year-less display slug, and all three destination resolvers
drop the year before computing identity (`_TENNIS_STOPWORDS` / `_F1_STOPWORDS`
list 2024..2027; `_golf_major_concept_key` never carries a year). So a key derived
from a 2027 board could only ever mean the edition in play.

Measured on production 2026-09-21, the three reader-visible specimens pinned here:

  * 61308736 "2027 US Open Men's Singles Winner" (open) drew
    "Part of: 2027 US Open Men's Singles ->" at `/event/tennis/2027-us-open-men-s-
    singles-winner`, which the API folds to `event:tennis:us-open-men-s-singles-
    winner`: SETTLED, "Ends Sep 13", "Final result: Alexander Zverev — WON".
  * 61064200 "2027 US Open Women's Singles Winner" (open) — the same.
  * 61056094 "2027 The Masters Champion" (open) drew "Part of: 2027 The Masters ->"
    at `/event/golf/the-masters`: settled, dated 2026-04-09 -> 2026-04-12.

Behaviour only — every assertion goes through the public deriver with an INJECTED
clock (gotcha #44: an anchor that reads the calendar inverts on New Year's Day).
"""

from datetime import datetime, timezone

import pytest

from app.utils.concept_links import (
    _names_a_foreign_edition,
    derive_market_concept_key,
    derive_market_hub_slug,
)

NOW_2026 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
NOW_2027 = datetime(2027, 3, 1, 12, 0, tzinfo=timezone.utc)

# The three production rows, verbatim (id, external_id, name, category, outcomes).
TENNIS_MEN_2027 = (61308736, "KXATP-27USO", "2027 US Open Men's Singles Winner", "tennis", 26)
TENNIS_WOMEN_2027 = (61064200, "KXWTA-27USO", "2027 US Open Women's Singles Winner", "tennis", 25)
GOLF_MASTERS_2027 = (61056094, "KXPGATOUR-MAST27", "2027 The Masters Champion", "golf", 51)


def _key(row, now):
    _id, external_id, name, cat, n_outcomes = row
    return derive_market_concept_key(external_id, name, cat, n_outcomes, now=now)


class TestTheShip:
    """A board naming an edition that is not in play gets no concept link."""

    @pytest.mark.parametrize(
        "row",
        [TENNIS_MEN_2027, TENNIS_WOMEN_2027, GOLF_MASTERS_2027],
        ids=["tennis-men-2027", "tennis-women-2027", "golf-masters-2027"],
    )
    def test_a_2027_board_does_not_link_into_the_2026_edition(self, row):
        assert _key(row, NOW_2026) is None

    @pytest.mark.parametrize(
        "row,hub",
        [(TENNIS_MEN_2027, "tennis"), (GOLF_MASTERS_2027, "golf")],
        ids=["tennis", "golf"],
    )
    def test_the_refused_board_still_has_an_up_link(self, row, hub):
        """"No concept link" is the honest gap, not a dead end: the hub link that
        sits below it in the mesh is untouched, so the reader still gets out."""
        assert _key(row, NOW_2026) is None
        assert derive_market_hub_slug(row[3]) == hub


class TestTheGuardIsNotAYearBan:
    """It reads the edition in play; it does not hardcode one."""

    @pytest.mark.parametrize(
        "row,expected",
        [
            (TENNIS_MEN_2027, "event:tennis:2027-us-open-men-s-singles-winner"),
            (TENNIS_WOMEN_2027, "event:tennis:2027-us-open-women-s-singles-winner"),
            (GOLF_MASTERS_2027, "event:golf:the-masters"),
        ],
        ids=["tennis-men", "tennis-women", "golf-masters"],
    )
    def test_the_same_board_links_once_its_edition_is_the_one_in_play(self, row, expected):
        assert _key(row, NOW_2027) == expected

    def test_a_board_naming_the_current_edition_keeps_its_link(self):
        assert (
            derive_market_concept_key(
                "KXPGATOUR-MAST26", "2026 The Masters Champion", "golf", 50, now=NOW_2026
            )
            == "event:golf:the-masters"
        )

    def test_a_board_naming_no_edition_keeps_its_link(self):
        """The commonest shape in the corpus: a bare winner field, no year token.
        An empty edition claim is "no claim", never "claims nothing matches"."""
        assert (
            derive_market_concept_key(
                "kalshi:KXATP-USO", "US Open Men's Singles Winner", "tennis", 48, now=NOW_2026
            )
            == "event:tennis:us-open-men-s-singles-winner"
        )
        assert (
            derive_market_concept_key(
                "kalshi:KXATP-USO", "US Open Men's Singles Winner", "tennis", 48, now=NOW_2027
            )
            == "event:tennis:us-open-men-s-singles-winner"
        )


class TestF1IsTheSameShape:
    """`_F1_STOPWORDS` drops the year exactly as the tennis adapter does, so the
    motorsports branch is gated on the same rule. No such row is open today — this
    pins the class before one arrives, which is how #7782 got in."""

    def test_a_future_edition_grand_prix_gets_no_link(self):
        assert (
            derive_market_concept_key(
                "KXF1RACE-BRIGP27", "2027 British Grand Prix Winner", "motorsports", 20, now=NOW_2026
            )
            is None
        )

    def test_a_year_less_grand_prix_is_untouched(self):
        assert (
            derive_market_concept_key(
                "KXF1RACE-BRIGP26", "British Grand Prix Winner", "motorsports", 20, now=NOW_2026
            )
            == "event:f1:british-grand-prix-winner"
        )


class TestTheGuardIsScopedToTheEditionBlindDomains:
    """Controls. The domains that resolve their OWN edition must not lose links to
    a rule written for the ones that cannot."""

    def test_soccer_keeps_its_configured_edition_on_a_later_clock(self):
        """#7782's fix compares against `cfg.edition`, which is a real claim about
        the destination — the calendar must not override it."""
        assert (
            derive_market_concept_key(
                "KXWC-26", "2026 FIFA World Cup Champion", "soccer", 32, now=NOW_2027
            )
            == "event:soccer:world-cup-2026"
        )

    def test_an_awards_ticker_is_authoritative_regardless_of_the_clock(self):
        assert (
            derive_market_concept_key(
                "KXOSCARBP-26", "Best Picture 2026", "entertainment", 10, now=NOW_2027
            )
            == "event:awards:oscars"
        )

    def test_a_tennis_matchup_still_gets_no_link(self):
        """Pre-existing refusal, unchanged: the guard must not be the only reason
        a non-winner market is refused."""
        assert (
            derive_market_concept_key(None, "Gauff vs Sabalenka", "tennis", 2, now=NOW_2026)
            is None
        )


class TestTheEditionReader:
    def test_it_reports_no_claim_for_a_name_with_no_year(self):
        assert _names_a_foreign_edition("US Open Men's Singles Winner", NOW_2026) is False
        assert _names_a_foreign_edition(None, NOW_2026) is False
        assert _names_a_foreign_edition("", NOW_2026) is False

    def test_a_name_that_includes_the_current_edition_is_not_foreign(self):
        """A range name ("2026 or 2027") claims the edition in play among others,
        so it keeps its link rather than being refused on the other token."""
        assert _names_a_foreign_edition("2026 or 2027 US Open Winner", NOW_2026) is False

    def test_only_a_four_digit_year_is_an_edition_claim(self):
        """Tour tiers and set counts are not editions: "ATP 1000 Montreal" and
        "Set 3 Games" must not read as a foreign edition and lose their link."""
        assert _names_a_foreign_edition("ATP 1000 Montreal: Winner", NOW_2026) is False
        assert _names_a_foreign_edition("2027 US Open Men's Singles Winner", NOW_2026) is True
