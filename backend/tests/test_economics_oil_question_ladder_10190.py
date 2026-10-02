"""#10190: the /economics Crude Oil card prints the oil price the market quotes, not a rescaled bucket.

Seen at 390px on production 2026-10-02 11:15Z. Two of the card's four rows were
#3004's defect again, on ladders #3004's gate cannot see:

    market                                            card          the venue
    63605723 WTI ... closes above ___ on October 2?   WTI $87  28%  $87 at .865
    16756821 Oil Price (WTI) on Election Day ...?      WTI $96  18%  median `$91 or above` .50

`_oil_row` keeps the sentence path only for a ladder `_is_cumulative_ladder`
recognises, and that reads the outcome NAMES alone. The first market writes its
comparator once, in the QUESTION, over a blank; its legs are bare prices. The
second mixes `Above $59.99` with `$73 or above`. Both fell through to the
composite `{sym} {range}` row: the first rescaled eleven nested rungs as if
they were a partition, and the second was differenced into buckets with the
modal one printed under a label that had lost its date.

What this file pins:

  1. RED HALF: the unchanged old helpers reproduce the served numbers from
     these fixtures, so the specimens are the defect and not a straw version;
  2. each repaired row prints the rung price the venue quotes, as an EQUALITY,
     with its question, and with no `sym`/`range` (only their absence makes the
     page print `q`);
  3. a bare price under a question that carries "above ___" is served as
     "Above $89", because the cleaned question (#10084) no longer says "above";
  4. what is left alone: the Kalshi daily bracket partition (`62481245`) and an
     exclusive `at ___` question with bare prices still take the composite path;
  5. the wiring, by source scan.

Fixtures are the stored `current_probability` values read by `db-query` at
2026-10-02 11:16Z.
"""

import re
from pathlib import Path

from app.models import FuturesMarket, FuturesOutcome
from app.routes import economics as econ
from app.routes.economics import _oil_row


def _market(name, outcomes, *, mid, source="kalshi"):
    market = FuturesMarket(id=mid, name=name, source=source)
    market.outcomes = [
        FuturesOutcome(name=n, external_id=n, current_probability=p)
        for n, p in outcomes
    ]
    return market


BLANK_NAME = "WTI Crude Oil (WTI) closes above ___ on October 2?"
BLANK_LEGS = [
    ('$87', 0.8055), ('$88', 0.7405), ('$89', 0.545), ('$90', 0.335), ('$91', 0.19),
    ('$92', 0.1), ('$93', 0.0375), ('$94', 0.0235), ('$95', 0.018), ('$96', 0.01),
    ('$97', 0.01),
]

ELECTION_NAME = "Oil Price (WTI) on Election Day (November 3, 2026)?"
ELECTION_LEGS = [
    ('$73 or above', 0.865), ('$74 or above', 0.845), ('$75 or above', 0.85),
    ('$76 or above', 0.855), ('$77 or above', 0.84), ('$78 or above', 0.795),
    ('$79 or above', 0.79), ('$80 or above', 0.73), ('$81 or above', 0.66),
    ('$82 or above', 0.74), ('$83 or above', 0.725), ('$84 or above', 0.66),
    ('$85 or above', 0.61), ('$86 or above', 0.6), ('$87 or above', 0.605),
    ('$88 or above', 0.57), ('$89 or above', 0.645), ('$90 or above', 0.51),
    ('$91 or above', 0.5), ('$92 or above', 0.495), ('$94 or above', 0.445),
    ('$95 or above', 0.385), ('$96 or above', 0.385), ('$93 or above', 0.405),
    ('$106 or above', 0.13), ('$103 or above', 0.135), ('$101 or above', 0.215),
    ('$97 or above', 0.21), ('$105 or above', 0.14), ('$104 or above', 0.17),
    ('$98 or above', 0.215), ('$110 or above', 0.09), ('$111 or above', 0.065),
    ('$100 or above', 0.225), ('$107 or above', 0.115), ('$102 or above', 0.235),
    ('$109 or above', 0.085), ('$112 or above', 0.07), ('$99 or above', 0.22),
    ('$114 or above', 0.075), ('$115 or above', 0.065), ('$108 or above', 0.14),
    ('$113 or above', 0.08), ('$117 or above', 0.05), ('$116 or above', 0.055),
    ('Above $66.49', 0.915), ('Above $64.49', 0.935), ('Above $70.49', 0.94),
    ('Above $69.49', 0.895), ('Above $65.49', 0.9), ('Above $62.99', 0.9),
    ('Above $71.49', 0.915), ('Above $64.99', 0.9), ('Above $72.49', 0.885),
    ('Above $68.99', 0.905), ('Above $63.99', 0.95), ('Above $69.99', 0.935),
    ('Above $65.99', 0.9), ('Above $68.49', 0.9), ('Above $63.49', 0.905),
    ('Above $67.99', 0.895), ('Above $71.99', 0.89), ('Above $70.99', 0.94),
    ('Above $66.99', 0.895), ('Above $67.49', 0.905), ('Above $57.99', 0.925),
    ('Above $58.49', 0.92), ('Above $58.99', 0.915), ('Above $59.49', 0.91),
    ('Above $59.99', 0.965), ('Above $60.49', 0.905), ('Above $60.99', 0.905),
    ('Above $61.49', 0.905), ('Above $61.99', 0.9), ('Above $62.49', 0.9),
]

BRACKET_NAME = "Oil Price (WTI) on Oct 2, 2026?"
BRACKET_LEGS = [
    ('$94.00 to $94.99', 0.035), ('$95.00 to $95.99', 0.03),
    ('$96.00 to $96.99', 0.025), ('$97.00 to $97.99', 0.02), ('Above $104.99', 0.04),
    ('$91.00 to $91.99', 0.11), ('$92.00 to $92.99', 0.05),
    ('$93.00 to $93.99', 0.055), ('$90.00 to $90.99', 0.175),
    ('$98.00 to $98.99', 0.02), ('$99.00 to $99.99', 0.03),
    ('$88.00 to $88.99', 0.205), ('$89.00 to $89.99', 0.22),
    ('$100.00 to $100.99', 0.03), ('$86.00 to $86.99', 0.055),
    ('$87.00 to $87.99', 0.125), ('$80.00 to $80.99', 0.03),
    ('$81.00 to $81.99', 0.03), ('Below $80.00', 0.03), ('$82.00 to $82.99', 0.01),
    ('$83.00 to $83.99', 0.02), ('$84.00 to $84.99', 0.01),
    ('$85.00 to $85.99', 0.025), ('$101.00 to $101.99', 0.02),
    ('$102.00 to $102.99', 0.03), ('$103.00 to $103.99', 0.03),
    ('$104.00 to $104.99', 0.03),
]


def _blank():
    return _market(BLANK_NAME, BLANK_LEGS, mid=63605723, source="polymarket")


def _election():
    return _market(ELECTION_NAME, ELECTION_LEGS, mid=16756821)


def _bracket():
    return _market(BRACKET_NAME, BRACKET_LEGS, mid=62481245)


def _old_composite(market):
    """The energy branch's pre-#10190 fallback, run with its unchanged helpers."""
    outcomes = econ._outcomes_sorted(market)
    if econ._reads_as_cumulative(outcomes):
        brackets = econ._cumulative_to_discrete(outcomes, max_buckets=6)
    else:
        brackets = econ._brackets_from_outcomes(market)
    _, prob, label = econ._modal_bracket(brackets)
    return prob, label


class TestTheDefectTheseSpecimensReproduce:
    def test_the_blank_ladder_was_rescaled_into_a_bucket(self):
        assert _old_composite(_blank()) == (28.6, "$87")  # `WTI $87 · 28%` on the page
        assert not econ._is_cumulative_ladder(_blank())

    def test_the_mixed_affix_ladder_was_differenced_into_a_bucket(self):
        assert _old_composite(_election()) == (17.5, "$96")  # `WTI $96 · 18%`
        assert not econ._is_cumulative_ladder(_election())


class TestTheBlankLadder:
    def test_prints_the_rung_price_the_venue_quotes(self):
        row = _oil_row(_blank())
        assert row is not None
        assert row["prob"] == 54.5  # `$89` .545: the tightest rung still favoured
        assert row["leader"] == "Above $89"
        assert row["q"] == BLANK_NAME
        assert "sym" not in row and "range" not in row

    def test_the_served_question_reads_as_a_sentence_with_the_leader(self):
        payload = econ.clean_served_questions({"oil": [_oil_row(_blank())]})
        row = payload["oil"][0]
        assert row["q"] == "How high will WTI Crude Oil (WTI) close on October 2?"
        assert row["leader"] == "Above $89"


class TestTheMixedAffixLadder:
    def test_prints_the_median_rung_with_its_dated_question(self):
        row = _oil_row(_election())
        assert row is not None
        assert row["prob"] == 50.0
        assert row["leader"] == "$91 or above"  # the leg already carries its comparator
        assert row["q"] == ELECTION_NAME
        assert "sym" not in row and "range" not in row


class TestWhatIsLeftAlone:
    def test_the_kalshi_daily_bracket_partition_keeps_the_composite_path(self):
        assert _oil_row(_bracket()) is None

    def test_an_exclusive_at_blank_with_bare_prices_is_not_read_as_a_ladder(self):
        # `closes at ___` is a bucket field; only a comparator over the blank
        # says the legs nest (#7674's discriminator).
        at = _market(
            "WTI Crude Oil (WTI) closes at ___ on October 2?",
            [("$87", 0.2), ("$88", 0.3), ("$89", 0.3), ("$90", 0.2)],
            mid=1,
            source="polymarket",
        )
        assert _oil_row(at) is None

    def test_a_leader_that_already_names_its_comparator_is_not_prefixed(self):
        assert econ._with_question_comparator(_blank(), "Above $89") == "Above $89"
        assert econ._with_question_comparator(_blank(), None) is None

    def test_a_question_with_no_blank_adds_no_comparator(self):
        assert econ._with_question_comparator(_bracket(), "$89") == "$89"


class TestTheWiring:
    SRC = Path(econ.__file__).read_text()

    def test_oil_row_asks_the_widened_ladder_gate(self):
        body = self.SRC.split("def _oil_row(", 1)[1].split("\ndef ", 1)[0]
        assert re.search(r"\bif _oil_is_ladder\(market\):", body)
        assert re.search(r"\b_with_question_comparator\(", body)

    def test_the_gate_asks_the_question_grammar(self):
        body = self.SRC.split("def _oil_is_ladder(", 1)[1].split("\ndef ", 1)[0]
        assert re.search(r"\bcumulative_outcome_ladder\(rows, question=market\.name\)", body)
