"""#10190, second half — the oil card reads its ladder AFTER the group fold.

The first half (231d2dc214, live 13:16Z 2026-10-02) made `_oil_row` read a
bare-price "closes above ___" ladder, and its guards called `_oil_row` on the
wrapper alone. Production never does that: `get_economics` runs
`group_markets_by_group_id` first, and Polymarket lists the question as a
wrapper plus one Yes/No binary per rung under one `group_id`. The fold merges
the binaries' "Yes" and "No" onto the wrapper, the grammar refuses
`$87 … $97, Yes, No`, and the 13:25Z rebuild still printed "WTI $87 · 35.4%".

These fixtures are production's rows at 13:25Z: market ids, the shared
`polymarket:1113496`, leg names and prices (db-query, same minute). Every
outcome carries its own `market_id`, as a loaded row does — the fold moves
legs between markets and that column is the only record of where one came from.
"""

from decimal import Decimal

from app.models import FuturesMarket, FuturesOutcome
from app.routes import economics as econ
from app.routes.economics import _oil_row
from app.utils.cross_source_matching import group_markets_by_group_id

GROUP = "polymarket:1113496"
WRAPPER_ID = 63605723
WRAPPER_NAME = "WTI Crude Oil (WTI) closes above ___ on October 2?"
WRAPPER_LEGS = [
    ("$87", "0.831"), ("$88", "0.7545"), ("$89", "0.485"), ("$91", "0.13"),
    ("$92", "0.065"), ("$93", "0.028"), ("$94", "0.02"), ("$95", "0.0185"),
    ("$97", "0.0095"), ("$96", "0.0075"), ("$90", None),
]
# One Yes/No binary per rung; Yes is the rung's price. Volumes are production's
# (the fold folds in the Yes/No of the busiest sibling — here the unpriced $90).
VOLUMES = {
    87: 1985, 97: 1456, 96: 1235, 95: 2202, 94: 1966, 93: 2873, 92: 2777,
    91: 2668, 90: 2941, 89: 1357, 88: 1479,
}
BINARY_IDS = {
    87: 63647846, 97: 63699337, 96: 63699338, 95: 63699339, 94: 63699340,
    93: 63699341, 92: 63699342, 91: 63699343, 90: 63699344, 89: 63699345,
    88: 63699346,
}


def _outcome(name, price, *, market_id, rank):
    return FuturesOutcome(
        name=name,
        external_id=f"{market_id}:{name}",
        current_probability=None if price is None else Decimal(price),
        market_id=market_id,
        rank=rank,
    )


def _wrapper():
    m = FuturesMarket(
        id=WRAPPER_ID, name=WRAPPER_NAME, source="polymarket",
        group_id=GROUP, volume_24h=22939,
    )
    m.outcomes = [
        _outcome(n, p, market_id=WRAPPER_ID, rank=i + 1)
        for i, (n, p) in enumerate(WRAPPER_LEGS)
    ]
    return m


def _binaries(volumes=VOLUMES):
    prices = {int(n[1:]): p for n, p in WRAPPER_LEGS}
    out = []
    for strike, mid in BINARY_IDS.items():
        yes = prices[strike]
        no = None if yes is None else str(Decimal(1) - Decimal(yes))
        m = FuturesMarket(
            id=mid,
            name=f"WTI Crude Oil (WTI) closes above ${strike} on October 2?",
            source="polymarket", group_id=GROUP, volume_24h=volumes[strike],
        )
        m.outcomes = [
            _outcome("Yes", yes, market_id=mid, rank=1),
            _outcome("No", no, market_id=mid, rank=2),
        ]
        out.append(m)
    return out


def _folded(volumes=VOLUMES):
    (rep,) = group_markets_by_group_id([_wrapper(), *_binaries(volumes)])
    return rep


class TestTheFoldIsTheSpecimen:
    def test_the_fold_keeps_the_wrapper_and_adds_a_siblings_yes_and_no(self):
        rep = _folded()
        assert rep.id == WRAPPER_ID
        names = [o.name for o in rep.outcomes]
        assert names[-2:] == ["Yes", "No"]
        assert {o.market_id for o in rep.outcomes[-2:]} <= set(BINARY_IDS.values())

    def test_the_old_reading_refused_the_folded_ladder(self):
        # What production did at 13:25Z: the ladder test over EVERY leg.
        rep = _folded()
        rows = [{"name": o.name} for o in rep.outcomes]
        assert econ.cumulative_outcome_ladder(rows, question=rep.name) is None


class TestTheCardReadsTheFoldedLadder:
    def test_prints_the_rung_the_venue_quotes(self):
        row = _oil_row(_folded())
        assert row is not None
        assert row["market_id"] == WRAPPER_ID
        assert row["leader"] == "Above $88"
        assert row["prob"] == 75.4
        assert row["src"] == "polymarket"

    def test_a_folded_yes_is_never_the_rung(self):
        # When the busiest sibling is the median rung's own binary, its Yes ties
        # $88 at .7545 and sorts first (rank 1): the rung pick must skip it.
        busiest_88 = {**VOLUMES, 88: 9999}
        rep = _folded(busiest_88)
        assert [o.market_id for o in rep.outcomes[-2:]] == [BINARY_IDS[88]] * 2
        row = _oil_row(rep)
        assert row["leader"] == "Above $88"
        assert row["prob"] == 75.4

    def test_the_wrapper_alone_reads_the_same(self):
        # The fold must not change the answer — it only adds legs the card ignores.
        assert _oil_row(_folded()) == _oil_row(_wrapper())


class TestAMarketsOwnYesNoIsUntouched:
    """#3004's contaminated binary: its Yes/No are ITS legs, so they still count."""

    def _own(self, market_id):
        m = FuturesMarket(id=900, name="WTI above $85 on Oct 2?", source="kalshi")
        m.outcomes = [
            _outcome("Yes", "0.5", market_id=market_id, rank=1),
            _outcome("No", "0.5", market_id=market_id, rank=2),
            _outcome("$87", "0.3", market_id=market_id, rank=3),
            _outcome("$88", "0.2", market_id=market_id, rank=4),
        ]
        return m

    def test_own_yes_no_is_not_treated_as_folded(self):
        assert econ._folded_sibling_binary_legs(self._own(900)) == set()

    def test_own_yes_no_routes_exactly_as_an_unloaded_row_does(self):
        # market_id None = the first half's fixtures; 900 = a loaded row.
        assert _oil_row(self._own(900)) == _oil_row(self._own(None))
