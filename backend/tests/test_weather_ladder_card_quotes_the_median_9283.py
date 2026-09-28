"""#9283: a /weather card on a cumulative ladder quotes the median rung, not the loosest.

Production, 2026-09-28 03:35Z, `/weather` "Hurricane markets":

    Hurricane Polo category?            100%  Category 1 or above   (Kalshi)
    How strong will Hurricane Polo be?   98%  Category 5            (Polymarket)

Polo is a Category 5 storm and Kalshi prices its "Category 5 or above" rung at
99.5%. The card said "Category 1 or above" because every rung tied at 99.5% and
the first one won. On a cumulative ladder the dearest leg is the loosest rung by
arithmetic, so the leader scan always quotes the least informative answer.

The rule: walk the priced rungs from the loosest, keep going while each is still
>= 50%, quote the last. Stop at the first rung under 50%. No rung >= 50% keeps
the ordinary leader.

Every specimen below is the stored ladder read from `futures_outcomes` when the
issue was filed; the expected rung is asserted by equality.
"""

from app.models.models import FuturesMarket, FuturesOutcome
from app.routes.weather import (
    _card_outcome,
    _card_prob,
    _ladder_median_rung,
    _leader_outcome,
    _leader_outcome_name,
)

POLO = [(f"Category {i} or above", 0.995) for i in range(1, 6)]
NOLO = [
    ("Category 1 or above", 0.995),
    ("Category 2 or above", 0.985),
    ("Category 3 or above", 0.985),
    ("Category 4 or above", 0.835),
    ("Category 5 or above", 0.24),
]
# Incoherent: Cat 3+ is dearer than Cat 2+. The walk still reads it.
LALA = [
    ("Category 1 or above", 0.88),
    ("Category 2 or above", 0.86),
    ("Category 3 or above", 0.895),
    ("Category 4 or above", 0.835),
    ("Category 5 or above", 0.015),
]
# Thin books, nothing >= 50%: the leader stands.
SIMON = [
    ("Category 1 or above", 0.265),
    ("Category 2 or above", None),
    ("Category 3 or above", None),
    ("Category 4 or above", 0.36),
    ("Category 5 or above", 0.37),
]
# Unpriced middle rungs take no part.
ISAIAS = [
    ("Category 1 or above", 0.98),
    ("Category 2 or above", None),
    ("Category 3 or above", None),
    ("Category 4 or above", 0.06),
    ("Category 5 or above", 0.04),
]
NEXT_ATLANTIC = [
    ("Before Dec 1, 2026", 0.64),
    ("Before Nov 15, 2026", 0.55),
    ("Before Nov 1, 2026", 0.12),
]
# Not a ladder: mutually exclusive categories. Untouched.
POLO_POLY = [
    ("Category 1 or weaker", 0.006),
    ("Category 2", 0.004),
    ("Category 3", 0.004),
    ("Category 4", 0.0145),
    ("Category 5", 0.979),
]


def _market(name, outcomes) -> FuturesMarket:
    m = FuturesMarket(id=1, source="kalshi", external_id="x", name=name, status="open")
    m.outcomes = [
        FuturesOutcome(id=i, market_id=1, external_id=f"o{i}", name=label,
                       current_probability=prob)
        for i, (label, prob) in enumerate(outcomes)
    ]
    return m


class TestProductionSpecimens:
    def test_polo_reads_category_5(self):
        m = _market("Hurricane Polo category?", POLO)
        assert _leader_outcome(m).name == "Category 1 or above", "the defect"
        assert _leader_outcome_name(m) == "Category 5 or above"
        assert _card_prob(m) == 100

    def test_nolo_reads_category_4_at_its_own_price(self):
        m = _market("Hurricane Nolo category?", NOLO)
        assert _leader_outcome_name(m) == "Category 4 or above"
        assert _card_prob(m) == 84

    def test_an_incoherent_ladder_still_reads_its_median(self):
        m = _market("Hurricane Lala category?", LALA)
        assert _leader_outcome_name(m) == "Category 4 or above"
        assert _card_prob(m) == 84

    def test_a_date_ladder_reads_its_earliest_likely_date(self):
        m = _market("When will the next Atlantic hurricane form?", NEXT_ATLANTIC)
        assert _leader_outcome_name(m) == "Before Nov 15, 2026"
        assert _card_prob(m) == 55


class TestTheLeaderStands:
    def test_no_rung_at_50_keeps_the_leader(self):
        m = _market("Hurricane Simon category?", SIMON)
        assert _ladder_median_rung(m) is None
        assert _card_outcome(m) is _leader_outcome(m)
        assert _card_prob(m) == 37

    def test_unpriced_rungs_are_skipped_not_a_stop(self):
        m = _market("Hurricane Isaias category?", ISAIAS)
        assert _leader_outcome_name(m) == "Category 1 or above"
        assert _card_prob(m) == 98

    def test_mutually_exclusive_categories_are_not_a_ladder(self):
        m = _market("How strong will Hurricane Polo be?", POLO_POLY)
        assert _ladder_median_rung(m) is None
        assert _leader_outcome_name(m) == "Category 5"
        assert _card_prob(m) == 98


class TestTheWalkStopsAtTheFirstUnlikelyRung:
    def test_a_later_rung_over_50_is_not_reached(self):
        """1+ 90%, 2+ 30%, 3+ 60%: 3+ cannot be "likely" over a 2+ that is not."""
        m = _market(
            "Hurricane Test category?",
            [
                ("Category 1 or above", 0.90),
                ("Category 2 or above", 0.30),
                ("Category 3 or above", 0.60),
            ],
        )
        assert _leader_outcome_name(m) == "Category 1 or above"
        assert _card_prob(m) == 90

    def test_row_order_does_not_decide(self):
        m = _market("Hurricane Nolo category?", list(reversed(NOLO)))
        assert _leader_outcome_name(m) == "Category 4 or above"


class TestTheSeamHolds:
    def test_number_name_and_outcome_are_one_row(self):
        m = _market("Hurricane Nolo category?", NOLO)
        outcome = _card_outcome(m)
        assert outcome.name == _leader_outcome_name(m)
        assert round(float(outcome.current_probability) * 100) == _card_prob(m)
