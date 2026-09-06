"""#3414 — "Regulation Time" is a period of play, not a court case.

`categorize_by_rules` reads the market NAME when the ticker is unmapped, and its
legal rule matches the bare word ``regulation``. Kalshi names the ninety minutes
before extra time "Regulation Time", so "Tj Divina vs Zilina: Regulation Time
Total Goals" is a soccer market filed under ``legal`` — off every sport surface
it belongs on, and in a bucket that means "court case" to the rest of the
product.

The sports rules above it are keyed on leagues and famous names, so a Slovak
fourth-tier fixture matches none of them and falls straight through to the legal
rule. That is the mechanism, and it is not Slovak: it fires for any sport whose
series ticker is unmapped.

Measured on production 2026-09-06, `futures_markets` where the name contains
"regulation":

    llm_sport_category | "regulation time" | rows
    legal              | yes               | 1,908
    soccer             | yes               |   862   (ticker mapped, step 1 won)
    football           | yes               |   350
    baseball           | yes               |    50
    politics / tech    | NO                |     6   (the real legal sense)

Nothing in the corpus says "regulation" in the legal sense AND "Regulation
Time". The two populations are disjoint, which is why a negative lookahead is
the right instrument and a wider rewrite is not.

The second half of this file is the other end of the same tie (#3414 (b)): the
prop legs of the Slovak and KNVB cups now carry a ticker mapping, so step 1
answers them before the name is ever read.
"""

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.futures_categorization import SPORT_PATTERNS, categorize_by_rules
from app.utils.sport_keys import (
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
)


# Real production rows, read 2026-09-06 off `futures_markets` where
# `llm_sport_category = 'legal'` and the ticker is a Slovak/KNVB cup series.
MISFILED_AS_LEGAL = [
    ("KXSVKCUPSPREAD-26AUG25VISNAM",
     "Tj Visnove vs Namestovo: Regulation Time Spread"),
    ("KXSVKCUPTOTAL-26AUG25VISNAM",
     "Tj Visnove vs Namestovo: Regulation Time Total Goals"),
    ("KXSVKCUPBTTS-26AUG25VISNAM",
     "Tj Visnove vs Namestovo: Regulation Time BTTS"),
    ("KXSVKCUPSPREAD-26AUG26VKAZEM",
     "V. Kapusany vs Michalovce: Regulation Time Spread"),
    ("KXSVKCUPTOTAL-26AUG26GERLIP",
     "Gerlachov vs Liptovsky Mikulas: Regulation Time Total Goals"),
    ("KXSVKCUPTOTAL-26AUG26GECSNV",
     "FK Geca 73 vs Spisska Nova Ves: Regulation Time Total Goals"),
    ("KXSVKCUPTOTAL-26AUG26ZAHVNT",
     "SK Zahradne vs MFK Vranov Nad Topou: Regulation Time Total Goals"),
    ("KXSVKCUPTOTAL-26AUG26DIVZIL",
     "Tj Divina vs Zilina: Regulation Time Total Goals"),
]

# Markets that really are about regulation. These must not move.
GENUINELY_LEGAL = [
    "Will the EU pass the AI regulation in 2026?",
    "Will a federal regulation on gain-of-function research take effect?",
    "Will the new banking regulation be struck down?",
]


class TestARegulationTimeMarketIsNotFiledAsACourtCase:
    """The class, stated on the rules engine — the layer that got it wrong."""

    @pytest.mark.parametrize("ticker,name", MISFILED_AS_LEGAL)
    def test_the_name_alone_no_longer_reads_as_legal(self, ticker, name):
        """
        Deliberately asserted with NO ticker. The ticker mapping below also
        fixes these eight rows, and asserting through it would hide whether the
        name rule was ever repaired — leaving every other sport whose series is
        unmapped still filing its period markets as court cases.
        """
        assert categorize_by_rules(name) != "legal", (
            f"{name!r} is a soccer market; 'Regulation Time' is a period of "
            "play, not the legal sense of 'regulation'"
        )

    @pytest.mark.parametrize("ticker,name", MISFILED_AS_LEGAL)
    def test_the_whole_cascade_agrees(self, ticker, name):
        assert _categorize_kalshi_market(name, None, None) != "legal"

    def test_the_phrase_is_what_is_carved_out_not_the_word(self):
        """
        The narrow instrument, asserted as the boundary. One word apart:
        "regulation time" is sport, "regulation" anywhere else is legal.
        """
        assert categorize_by_rules("Newcastle vs Arsenal: Regulation Time Result") != "legal"
        assert categorize_by_rules("Will the EU pass the AI regulation?") == "legal"

    @pytest.mark.parametrize("name", GENUINELY_LEGAL)
    def test_a_real_regulatory_market_still_lands_in_legal(self, name):
        assert categorize_by_rules(name) == "legal"

    @pytest.mark.parametrize("word", [
        "Supreme Court", "SCOTUS", "indictment", "verdict", "trial",
        "conviction", "lawsuit", "antitrust",
    ])
    def test_every_other_legal_keyword_is_untouched(self, word):
        """The lookahead was added to ONE alternative. Swept over the rest so a
        later edit to that pattern cannot quietly drop one of them."""
        assert categorize_by_rules(f"Will the {word} decision land in 2026?") == "legal"

    def test_the_lookahead_lives_on_the_regulation_alternative_and_nowhere_else(self):
        """
        Read off the compiled rule itself rather than restated as a constant, so
        it cannot drift from the code. Exactly one lookahead, and it guards
        "regulation".
        """
        legal_patterns = [
            rule.pattern for rule, category in SPORT_PATTERNS if category == "legal"
        ]
        assert legal_patterns, "the legal rules disappeared"
        with_lookahead = [p for p in legal_patterns if "(?!" in p]
        assert len(with_lookahead) == 1
        assert r"regulation(?!\s+time)" in with_lookahead[0]


class TestBothCupsAreOneSportAcrossAllFiveLegs:
    """#3414 (b) — the prop legs of a tie belong to the same competition.

    Q453 mapped the moneyline and advance legs and held the rest back. The
    residue is ~293 rows in 30 days. The property asserted here is AGREEMENT
    across the legs rather than five separate constants: if one leg is a
    different sport from another, the tie has split again, which is the failure
    Q453's own comment names ("one competition cannot be four sports").
    """

    LEGS = ["game", "advance", "total", "spread", "btts"]

    @pytest.mark.parametrize("competition", ["KXSVKCUP", "KXKNVBCUP"])
    def test_every_leg_of_a_tie_resolves_to_the_same_sport(self, competition):
        keys = {
            leg: get_sport_key_from_ticker(f"{competition}{leg.upper()}-26AUG25ABCDEF")
            for leg in self.LEGS
        }
        assert None not in keys.values(), f"unmapped legs: {keys}"
        assert len(set(keys.values())) == 1, f"the tie split across sports: {keys}"
        assert set(keys.values()) == {"soccer_other"}

    @pytest.mark.parametrize("competition", ["KXSVKCUP", "KXKNVBCUP"])
    def test_every_leg_belongs_to_a_fixture(self, competition):
        """Game-level, the same way `kxnbaspread` and `kxnfltotal` are: a
        spread, a total and a both-teams-to-score are legs OF a game."""
        for leg in self.LEGS:
            ticker = f"{competition}{leg.upper()}-26AUG25ABCDEF"
            assert is_kalshi_game_level_ticker(ticker), ticker

    @pytest.mark.parametrize("ticker,name", MISFILED_AS_LEGAL)
    def test_the_ticker_settles_it_before_the_name_is_read(self, ticker, name):
        """Step 1 is authoritative. With the series mapped, these rows would be
        soccer even if the name rule had never been repaired — the two halves of
        this ship are independent, and each is asserted on its own."""
        assert _categorize_kalshi_market(name, None, ticker) == "soccer"
