"""#6696: an `/economics` row stops printing an unattributed — sometimes inverted — number.

`_market_row` took the dearest leg whatever it was called and printed the bare
percentage. That fails in two directions at once, and the second is the one a
reader cannot recover from.

Measured on the served `GET /api/economics` payload of 2026-09-17 04:45Z, joined
against `futures_outcomes` by `db-query` (71 markets served, 53 reaching a
Market row):

  A. THREE ROWS PRINTED THE PRICE OF THEIR OWN QUESTION'S `No`:

        prints  honest   question                                               outcomes
         85.5%   14.5%   Tariff increase on Canada in effect by December 31?    No .855, Yes .145
           81%     19%   Will S&P 500 (SPY) hit (HIGH) $780 in September?       No .81, Yes .19, ↑$780 .19
           50%   49.5%   Will WTI Crude Oil (WTI) hit (LOW) $90 Week of Sep 14? No .50, Yes .495, ↓$90 .495

     The first is the sharpest: it sits in TRADE & TARIFFS, in green behind a
     near-full bar, telling a reader that a Canadian tariff increase is
     near-certain when the market it quotes says 14.5%.

  B. EIGHTEEN MORE printed a real leg's price with no way to tell which leg —
     "What will the tariff rate on Canadian imports be on Jan 1, 2027?" at
     **85%** (the price of "10% or above", not a confidence in anything) and
     "Which sectors will Trump tariff in 2026?" at **97%** (Pharmaceuticals
     alone, of five sectors). A question that asks for a RATE, answered with a
     confidence, is unreadable rather than merely unlabelled.

The fix is one seam: the outcome is chosen once, and the number, the name and
the `market_id` all read that single object, so they cannot come to disagree
about what the row is about.

TWO TRAPS THIS SHIP WALKED UP TO, both pinned below.

  1. REDUNDANCY AND NEGATION ARE DIFFERENT FAULTS. `_prices_the_negation` is its
     own predicate and not a call to the "not worth naming" test, for the reason
     the weather twin documents (#2563): a leg whose name merely repeats the
     question is still the right NUMBER, and a rule that refused it would hand
     the card to an also-ran. Redundancy suppresses the name; negation is the
     only thing allowed to move the number.

  2. A STRAIGHT LIFT OF THE WEATHER RULE LEAVES #6696'S OWN SPECIMEN UNFIXED.
     "Bitcoin vs. Gold vs. S&P 500 in 2026" — named in the issue — would keep
     printing a bare 54.5%, because its leader "S&P 500" is spelled out in the
     question and the weather rule reads that as redundant. On a question that
     ENUMERATES its alternatives the winner's name is the entire answer. The
     discriminator is the market's own population, not a word list: redundant
     when the question spells out exactly one outcome, informative when it
     spells out two or more. A versus question is the second arm, because it
     enumerates by construction even where the counting arm cannot see it
     (one specimen, pinned).

What this file pins:

  1. each production specimen prints the honest number, asserted as an EQUALITY
     against the price the venue quotes — never as "not the wrong one", which a
     mutant returning 0 would satisfy;
  2. the row is STILL SERVED. This ship moves three numbers DOWN, and a
     vanished row satisfies every "the wrong number is gone" assertion as
     happily as a repair does;
  3. the healthy rows beside them do not move, and the 33 rows that correctly
     carry no name keep carrying none;
  4. each arm on its own, including the suppressions;
  5. the seam holds — `prob` is the price of the outcome `leader` names;
  6. `leader` is ALWAYS PRESENT, explicitly null. An absent key is
     indistinguishable from a cached payload built before the field existed.

Every specimen below is a real production row. Prices are the stored
`current_probability` values read the same minute as the payload.
"""

import pytest

from app.models import FuturesMarket, FuturesOutcome
from app.routes.economics import _market_row


def _market(name: str, outcomes: list[tuple[str, float | None]], *, mid: int = 1):
    """A real `FuturesMarket` carrying real `FuturesOutcome` rows.

    Real ORM objects rather than stand-ins on purpose: `_market_row` reads
    `.source` as well as `.name` and `.outcomes`, and a hand-rolled double that
    carries only the fields today's body happens to touch turns the next column
    read into an AttributeError in the guard instead of a finding in the code.
    """
    market = FuturesMarket(id=mid, name=name, source="kalshi")
    market.outcomes = [
        FuturesOutcome(name=n, external_id=n, current_probability=p)
        for n, p in outcomes
    ]
    return market


# --------------------------------------------------------------------------
# The production specimens, by market id.
# --------------------------------------------------------------------------

CANADA_TARIFF_INCREASE = (
    47061869,
    "Tariff increase on Canada in effect by December 31, 2026?",
    [("No", 0.855), ("Yes", 0.145)],
)
SPY_780 = (
    59545884,
    "Will S&P 500 (SPY) hit (HIGH) $780 in September?",
    [("No", 0.81), ("Yes", 0.19), ("↑ $780", 0.19), ("↑ $810", 0.0405)],
)
WTI_90 = (
    60787563,
    "Will WTI Crude Oil (WTI) hit (LOW) $90 Week of September 14 2026?",
    [("No", 0.50), ("Yes", 0.495), ("↓ $90", 0.495), ("↓ $65", 0.055)],
)

NEGATED = [CANADA_TARIFF_INCREASE, SPY_780, WTI_90]


class TestTheNoLegIsNeverTheAnswer:
    """Arm A — the price of the question's negation may not be the row's number."""

    @pytest.mark.parametrize(
        "mid,question,outcomes,honest",
        [
            (*CANADA_TARIFF_INCREASE, 14.5),
            (*SPY_780, 19.0),
            (*WTI_90, 49.5),
        ],
    )
    def test_the_row_prints_the_honest_price(self, mid, question, outcomes, honest):
        row = _market_row(_market(question, outcomes, mid=mid))
        assert row is not None, "the row vanished — see test_the_row_is_still_served"
        assert row["prob"] == honest

    @pytest.mark.parametrize("mid,question,outcomes", NEGATED)
    def test_the_row_is_still_served(self, mid, question, outcomes):
        """A dropped row satisfies 'the wrong number is gone' as well as a fix."""
        row = _market_row(_market(question, outcomes, mid=mid))
        assert row is not None
        assert row["q"] == question
        assert row["market_id"] == mid

    @pytest.mark.parametrize("mid,question,outcomes", NEGATED)
    def test_a_yes_no_binary_is_not_given_a_name(self, mid, question, outcomes):
        """The honest leg here is "Yes", which only restates the question."""
        row = _market_row(_market(question, outcomes, mid=mid))
        assert row["leader"] is None

    def test_the_canada_row_no_longer_reads_as_near_certain(self):
        """The reader-facing statement of the defect, in one assertion.

        85.5% behind a near-full green bar and 14.5% are opposite claims about
        the same question, and this is the row that made them on production.
        """
        mid, question, outcomes = CANADA_TARIFF_INCREASE
        row = _market_row(_market(question, outcomes, mid=mid))
        assert row["prob"] < 50, "a reader must not be told this is more likely than not"


class TestTheRowNamesTheLegItPrints:
    """Arm B — a percentage under a multi-outcome question needs its referent."""

    @pytest.mark.parametrize(
        "mid,question,outcomes,prob,leader",
        [
            (
                56914133,
                "What will the tariff rate on Canadian imports be on Jan 1, 2027?",
                [("10% or above", 0.85), ("20% or above", 0.405), ("30% or above", 0.255)],
                85.0,
                "10% or above",
            ),
            (
                56914129,
                "What will the tariff rate on Chinese imports be on Jan 1, 2027?",
                [
                    ("10% or above", 0.965),
                    ("20% or above", 0.80),
                    ("30% or above", 0.325),
                    ("50% or above", 0.135),
                    ("100% or above", 0.045),
                ],
                96.5,
                "10% or above",
            ),
            (
                109271,
                "Which sectors will Trump tariff in 2026?",
                [
                    ("Pharmaceuticals", 0.97),
                    ("Critical minerals", 0.30),
                    ("Wind turbines", 0.27),
                    ("Canadian aircraft", 0.215),
                    ("Foreign-made films", 0.0555),
                ],
                97.0,
                "Pharmaceuticals",
            ),
            (
                59164875,
                "Texas crude oil production in 2026",
                [("Above 5.6 million barrels/day", 0.955), ("Above 6.0 million barrels/day", 0.30)],
                95.5,
                "Above 5.6 million barrels/day",
            ),
        ],
    )
    def test_the_leader_is_named(self, mid, question, outcomes, prob, leader):
        row = _market_row(_market(question, outcomes, mid=mid))
        assert (row["prob"], row["leader"]) == (prob, leader)

    def test_a_rate_question_is_not_answered_with_a_bare_confidence(self):
        """The issue's headline row: "85%" alone is not an answer to "what rate?"."""
        mid, question, outcomes, _, _ = (
            56914133,
            "What will the tariff rate on Canadian imports be on Jan 1, 2027?",
            [("10% or above", 0.85), ("20% or above", 0.405), ("30% or above", 0.255)],
            None,
            None,
        )
        row = _market_row(_market(question, outcomes, mid=mid))
        assert row["leader"], "a rate question answered by a bare percentage"


class TestNothingWorthNaming:
    """The suppressions, each on its own. A name earns its place by ADDING."""

    def test_a_yes_leg_only_restates_the_question(self):
        row = _market_row(_market("Will the S&P finish positive this year?",
                                  [("Yes", 0.855), ("No", 0.145)]))
        assert (row["prob"], row["leader"]) == (85.5, None)

    def test_a_placeholder_is_not_a_name(self):
        """And its price is about nothing the reader can see, so it is negation."""
        row = _market_row(_market("Which option wins?",
                                  [("Option A", 0.7), ("Ontario", 0.3)]))
        assert (row["prob"], row["leader"]) == (30.0, "Ontario")

    def test_a_leader_already_spelled_out_in_the_question_is_not_repeated(self):
        """Rendering the same words twice in two type sizes adds nothing.

        The weather twin's case (#2563): the dearest leg repeats the question
        word for word. Its NAME is worthless and its NUMBER is exactly right —
        so the name is dropped and the number is untouched.
        """
        row = _market_row(_market(
            "Will Tropical Storm Lowell strengthen to a hurricane?",
            [("Tropical Storm Lowell strengthen to a hurricane", 0.88),
             ("Stays a tropical storm", 0.10)],
        ))
        assert row["prob"] == 88.0, "redundancy must never move the number"
        assert row["leader"] is None

    def test_a_short_name_is_not_found_inside_a_longer_word(self):
        """Whole tokens, not substrings: "0" must not be found inside "2026"."""
        row = _market_row(_market(
            "How many large volcano eruptions (VEI >=4) in 2026?",
            [("0", 0.715), ("1", 0.20), ("2", 0.05)],
        ))
        assert row["leader"] == "0"


class TestAQuestionThatEnumeratesItsOwnAlternatives:
    """Trap 2 — the arm without which #6696's own specimen stays broken."""

    def test_the_issues_versus_row_names_its_winner(self):
        """"Bitcoin vs. Gold vs. S&P 500 in 2026 — 55%" names none of the three."""
        row = _market_row(_market(
            "Bitcoin vs. Gold vs. S&P 500 in 2026",
            [("S&P 500", 0.545), ("Gold", 0.23), ("Bitcoin", 0.185)],
            mid=113891,
        ))
        assert (row["prob"], row["leader"]) == (54.5, "S&P 500")

    def test_two_spelled_out_outcomes_defeat_the_redundancy_rule(self):
        """The counting arm alone, with no versus token to fall back on."""
        row = _market_row(_market(
            "Will Alice or Bob be named first?",
            [("Alice", 0.6), ("Bob", 0.4)],
        ))
        assert row["leader"] == "Alice"

    def test_a_versus_question_names_its_side_when_only_one_is_spelled_out(self):
        """The versus arm alone.

        The rival is written "S&P 500" in the question and "S&P 500 Index" in
        the outcome, so the counting arm reaches 1 and would suppress the
        leader on a question whose whole point is which of two things won.
        This is the arm's ONLY specimen in the served population.
        """
        row = _market_row(_market(
            "Annual Return: S&P 500 vs. S&P 500 Equal Weight Index",
            [("S&P 500 Equal Weight Index", 0.645), ("S&P 500 Index", 0.385)],
            mid=29208024,
        ))
        assert (row["prob"], row["leader"]) == (64.5, "S&P 500 Equal Weight Index")

    def test_the_versus_arm_cannot_reach_a_question_without_one(self):
        """The control. Same shape, no versus token, suppression still applies."""
        row = _market_row(_market(
            "Will Gold rise in 2026?",
            [("Gold", 0.62), ("Something else entirely", 0.38)],
        ))
        assert row["leader"] is None

    def test_vs_is_matched_on_whole_tokens(self):
        """"vs" inside a word is not a versus question."""
        row = _market_row(_market(
            "Will Vsevolod Ivanov win?",
            [("Vsevolod Ivanov", 0.62), ("Someone else", 0.38)],
        ))
        assert row["leader"] is None


class TestTheSeamHolds:
    """`prob` and `leader` must read one outcome, or the row prices a stranger."""

    @pytest.mark.parametrize(
        "question,outcomes",
        [
            ("What will the tariff rate on Indian imports be on Jan 1, 2027?",
             [("10% or above", 0.825), ("20% or above", 0.40), ("30% or above", 0.18)]),
            ("Bitcoin vs. Gold vs. S&P 500 in 2026",
             [("S&P 500", 0.545), ("Gold", 0.23), ("Bitcoin", 0.185)]),
            ("Which sectors will Trump tariff in 2026?",
             [("Pharmaceuticals", 0.97), ("Wind turbines", 0.27)]),
        ],
    )
    def test_prob_is_the_price_of_the_outcome_leader_names(self, question, outcomes):
        row = _market_row(_market(question, outcomes))
        named = [p for n, p in outcomes if n == row["leader"]]
        assert named, f"leader {row['leader']!r} is not an outcome of this market"
        assert row["prob"] == pytest.approx(round(named[0] * 100, 1))


class TestTheFieldIsAlwaysPresent:
    """An absent key reads as a pre-field cached payload, not as 'nothing to name'."""

    @pytest.mark.parametrize(
        "question,outcomes",
        [
            ("Will the S&P finish positive this year?", [("Yes", 0.855), ("No", 0.145)]),
            ("Which sectors will Trump tariff in 2026?", [("Pharmaceuticals", 0.97)]),
        ],
    )
    def test_leader_is_present_even_when_null(self, question, outcomes):
        assert "leader" in _market_row(_market(question, outcomes))


class TestTheRefusalsAreUnchanged:
    """This ship must not widen or narrow which markets reach a row (#2950)."""

    def test_more_than_five_outcomes_is_still_refused(self):
        outcomes = [(f"Bracket {i}", 0.1) for i in range(6)]
        assert _market_row(_market("Six brackets?", outcomes)) is None

    def test_a_market_with_no_priced_outcome_is_still_refused(self):
        """#2950: the page must not print a confident 0% for a market it has no
        price for."""
        assert _market_row(_market("No prices?", [("Yes", None), ("No", None)])) is None

    def test_a_priced_zero_is_data_and_is_still_served(self):
        """`Decimal("0.000000")` is falsy; a priced zero is the market saying no."""
        row = _market_row(_market("Will it happen?", [("Yes", 0.0), ("Maybe", 0.0)]))
        assert row is not None and row["prob"] == 0.0


class TestTheFallbackHasNoProductionSpecimen:
    """Manufactured, and pinned as such.

    Over the served population every row with a negated dearest leg has a
    non-negated priced leg to fall to, so this path has zero production
    specimens. It preserves today's number rather than shipping an unexercised
    withholding path across nine theme lists.
    """

    def test_a_market_whose_every_leg_is_negation_keeps_its_number(self):
        row = _market_row(_market("Will it happen?", [("No", 0.9)]))
        assert row is not None
        assert (row["prob"], row["leader"]) == (90.0, None)
