"""#7494 — "Fed & Rates" must seat only markets its own question asks about.

Measured on production 2026-09-20 13:29Z: a bundle titled **Fed & Rates**,
captioned **"What does the Fed do next?"**, seated

    - Fed decision in Oct 2026?
    - September Inflation US - Monthly
    - Argentina Monthly Inflation - September     <- not the Fed, not a US rate
    - Core CPI YoY - September 2026
    - September Inflation US - Annual

Argentina's monthly CPI is not an answer to the question printed above it, and
at a story cap of 3 it also displaced a real Fed/US-rates row. `ecb` sat in the
same alternation, so an ECB decision landed there by the same route: the defect
is that the membership predicate was one jurisdiction wider than the caption,
not that one country slipped through.

The two directions this file holds:

1.  a market naming a NON-US jurisdiction is not a member — and is not re-homed
    into some other container we have not authored a sentence for, it simply
    keeps no story key;
2.  every US member the card actually has is STILL a member. This is the half
    that is easy to lose. The issue recommended requiring a positive `\\bus\\b`
    anchor; measured against the 206 open markets this predicate matches, that
    would have evicted "Core CPI YoY - September 2026", "CPI core in October"
    and ~30 more unprefixed US prints — the card's real content. A foreign print
    names its country; a US one usually does not.

The last test is the one that fires when someone changes the OTHER half of the
pair: the predicate is only correct while the caption stays US-specific.
"""

from app.utils.discover_bundles import AUTHORED_STORY_QUESTIONS, AUTHORED_STORY_TITLES
from app.utils.feed_market_quality import _story_key

MACRO = "story:macro_rates"
ECONOMICS = "economics"


# Every one of these is a real open market name read off production 2026-09-20.
US_MEMBERS = [
    # The specimen bundle's own surviving rows.
    "Fed decision in Oct 2026?",
    "September Inflation US - Monthly",
    "September Inflation US - Annual",
    # 🪤 Unprefixed US prints. These carry no "US" token at all, so a positive
    # US anchor would delete them. They are the majority of the card.
    "Core CPI YoY - September 2026",
    "CPI core in October",
    "CPI year-over-year in Dec 2026",
    "PPI YoY in September",
    "How many Fed rate cuts in 2026?",
    "What will the Fed rate be at the end of 2026?",
    "Number of rate cuts in 2026?",
    "US shelter CPI in September",
]

NON_US_MARKETS = [
    # The specimen defect.
    "Argentina Monthly Inflation - September",
    # The same defect via the `ecb` term that used to be in the alternation.
    "ECB Interest Rates: October 2026",
    "ECB rate cut in 2026?",
    "Eurozone Annual Inflation 2026",
    # Other live jurisdictions, all of which were members before this change.
    "Brazil Annual Inflation 2026",
    "September Inflation China - Annual",
    "September Inflation UK - Annual",
    "U.K. Annual Inflation 2026",
    "Number of Bank of Canada rate cuts in 2026?",
    "South Africa inflation rate MoM for August",
    "India Annual Inflation 2026",
    "Will Japan's inflation rate be above Singapore's in August?",
    # Cross-country comparisons. "Will US core inflation be above UK core
    # inflation?" names the US, but it is a comparison of two countries and not
    # an answer to "What does the Fed do next?" — excluded on purpose, so that
    # the rule is "the card's jurisdiction", not "the string US appears".
    "Will Canada inflation be above Euro Area inflation in September?",
    "Will US core inflation be above UK core inflation in September?",
]


class TestTheCardKeepsItsOwnMembers:
    def test_us_and_fed_markets_are_still_members(self):
        misrouted = [n for n in US_MEMBERS if _story_key(n, ECONOMICS) != MACRO]
        assert misrouted == [], (
            "these US/Fed markets are the card's actual content and must not be "
            f"evicted by the jurisdiction rule: {misrouted}"
        )

    def test_the_fed_wins_outright_even_beside_another_central_bank(self):
        # Naming the Fed makes it a Fed question whatever else it mentions; the
        # negative test must not swallow the arm it is there to protect.
        assert _story_key("Will the Fed cut before the ECB?", ECONOMICS) == MACRO


class TestTheCardStopsSeatingOtherJurisdictions:
    def test_non_us_markets_are_not_seated_under_the_fed_question(self):
        seated = [n for n in NON_US_MARKETS if _story_key(n, ECONOMICS) == MACRO]
        assert seated == [], (
            "these markets are not answers to 'What does the Fed do next?' and "
            f"must not be members of that bundle: {seated}"
        )

    def test_the_specimen_row_keeps_no_story_key_at_all(self):
        # 🪤 The fall-through is a claim this change makes, so it is asserted
        # rather than assumed: an evicted market is NOT quietly re-homed into
        # another authored container. It carries no story key and competes as
        # its own card, still bounded by its family key.
        for name in (
            "Argentina Monthly Inflation - September",
            "ECB Interest Rates: October 2026",
            "September Inflation UK - Annual",
        ):
            assert _story_key(name, ECONOMICS) is None, name


class TestThePredicateAndTheCaptionAreOnePair:
    def test_the_container_is_still_the_us_specific_one_this_rule_assumes(self):
        # The exclusion rule is only right because the sentence over the members
        # is about the Fed. If someone retitles this story to something
        # jurisdiction-neutral, the rule above becomes the wrong rule and this
        # test is where they find that out.
        assert AUTHORED_STORY_TITLES[MACRO] == "Fed & Rates"
        assert AUTHORED_STORY_QUESTIONS[MACRO] == "What does the Fed do next?"
