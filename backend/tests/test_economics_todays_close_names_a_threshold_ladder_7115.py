"""#7115: the TODAY'S CLOSE card stops hiding a fully-priced S&P strike ladder.

#7085 stopped this card printing `S&P 500 (SPY) closes — 0% up` for a leg the
venue had never priced, and that withholding was right. It also left the card
with a single row, because the market it dropped is the one carrying eleven
priced rungs. Read from production 2026-09-19 ~03:45Z, `futures_outcomes WHERE
market_id = 61381310` is thirteen rows:

    Yes  NULL   No  NULL          <- the only leg `_up_leg` will ever look at
    $735 90.6%  $745 89.5%  $755 83.0%  $765 19.0%  $775 10.5%
    $740 89.5%  $750 89.5%  $760 47.5%  $770 10.5%  $780 10.5%  $785 9.45%

The unpriced leg is the Polymarket EVENT stub — `61381310`'s `external_id` is
the bare numeric `1042750`, an event id rather than a condition id, which is
also why the question carries a literal blank ("closes above ___"). The eleven
rungs were already on this row before `_index_row` saw it:
`group_markets_by_group_id` picks its representative by "most outcomes" (13
against the children's 2 each) and merges the siblings in. Nothing was missing.
The row builder was reading the wrong leg.

So the card served one row, about a different index, while a complete monotone
ladder for the S&P sat one field away. It now serves:

    S&P 500 (SPY)            83% above $755
    S&P 500 (SPX)            53% up

WHY A SECOND S&P ROW IS NOT A RETURN OF #7085'S DEFECT, which is the first
objection this change should have to answer. #7085's two rows CONTRADICTED each
other — 0% and 53% for one index, one of them false. These two answer different
questions and each says which one. The label is the repair.

WHY `dir`, AND WHY NOT THE STOCKS CARD. `frontend/app/economics/page.tsx`
renders `{idx.sym}` and then `{idx.prob}% {idx.dir}` verbatim, so naming the
threshold needs no layout change and no new field — the row already had two
text slots and `dir` already carried a word. The single-stocks card renders a
bare `{prob}%` with no second slot, so the same rung there would sit at 83%
beside real up-probabilities with nothing to mark it apart. It gets no arm, and
arm 6 pins that refusal so a later "consistency" sweep cannot quietly add one.

WHAT THIS FILE PINS

  1. the production specimen serves its ladder, with the threshold named;
  2. the rung is the TIGHTEST bound still favoured, chosen on the price — the
     dearest rung ($735, 90.6%) is a ladder's loosest bound and says nothing;
  3. the four production PARTITIONS that reach the same branch are refused —
     all four are real specimens, and each is the reason the shape test is not
     just "are there priced non-binary legs";
  4. monotonicity is load-bearing: single-value rungs that rise with the strike
     are not a ladder and get no row;
  5. #7085's guards are untouched — an unpriced Yes/No market still serves
     nothing, a priced up leg still takes the old path, a priced ZERO keeps its
     row;
  6. the stocks branch gains nothing;
  7. `_ladder_rung` and the new arm share ONE rule, `_pick_rung`.
"""

from decimal import Decimal

from app.models import FuturesMarket, FuturesOutcome
from app.routes.economics import (
    _index_row,
    _index_symbol,
    _ladder_rung,
    _named_threshold_rungs,
    _pick_rung,
    _stock_row,
)


def _market(name: str, outcomes: list[tuple[str, object]], *, mid: int = 1, source: str = "polymarket"):
    """A real `FuturesMarket` with real `FuturesOutcome` rows, as in #7085's file.

    Real ORM objects rather than stand-ins: the builders read `.source` and
    `.rank` as well as `.name` and `.current_probability`.
    """
    market = FuturesMarket(id=mid, name=name, source=source)
    market.outcomes = [
        FuturesOutcome(name=n, external_id=f"{mid}-{n}", current_probability=p)
        for n, p in outcomes
    ]
    return market


def _d(x: str) -> Decimal:
    return Decimal(x)


# --------------------------------------------------------------------------
# Production specimens, read from `futures_outcomes` 2026-09-19 ~03:45Z.
# --------------------------------------------------------------------------

#: `61381310` in full — the stub pair AND the eleven rungs, in the arbitrary
#: order the join returned them, so nothing in the builder may depend on the
#: rows arriving sorted.
SPY_LADDER = (
    61381310,
    "S&P 500 (SPY) closes above ___ on September 21?",
    [
        ("$750", _d("0.895000")),
        ("Yes", None),
        ("No", None),
        ("$740", _d("0.895000")),
        ("$735", _d("0.906000")),
        ("$745", _d("0.895000")),
        ("$755", _d("0.830000")),
        ("$785", _d("0.094500")),
        ("$760", _d("0.475000")),
        ("$765", _d("0.190000")),
        ("$780", _d("0.105000")),
        ("$770", _d("0.105000")),
        ("$775", _d("0.105000")),
    ],
)

#: The healthy sibling that shares the card. Priced up leg, old path.
SPX_HEALTHY = (
    61381314,
    "S&P 500 (SPX) Up or Down on September 21?",
    [("Up", _d("0.530000"))],
)

#: The four markets that reach the index branch with an unpriced up leg and
#: priced non-binary rungs, and are NOT ladders. Every rung of every one names
#: a SPAN. `114287`'s rungs also sum to 309.6%, which is #1574's defect, not
#: this one — it must be refused here on its shape, before any sum is read.
PARTITIONS = [
    (
        109484,
        "Nasdaq-100 close price end of 2026?",
        [
            ("18,999.99 or below", _d("0.055")),
            ("33,000.01 or above", _d("0.145")),
            ("27,000 to 27,499.99", _d("0.025")),
            ("25,500 to 25,999.99", _d("0.015")),
            ("27,500 to 27,999.99", _d("0.035")),
        ],
    ),
    (
        109487,
        "S&P close price end of 2026?",
        [
            ("7,400 to 7,599.99", _d("0.125")),
            ("7,600 to 7,799.99", _d("0.145")),
            ("7,200 to 7,399.99", _d("0.065")),
            ("7,800 to 7,999.99", _d("0.170")),
        ],
    ),
    (
        114285,
        "What will S&P 500 (SPX) close at end of 2026?",
        [
            ("<$6,000", _d("0.075")),
            ("$6,500-$7,000", _d("0.100")),
            ("$7,000-$7,500", _d("0.220")),
            ("$6,000-$6,500", _d("0.065")),
            ("$7,500-$8,000", _d("0.280")),
            (">$8,000", _d("0.345")),
        ],
    ),
    (
        114287,
        "What will Nasdaq 100 (NDX) close at in December?",
        [
            (">$36,000", _d("0.1655")),
            ("$30,500-$33,000", _d("0.425")),
            ("$25,000-$26,500", _d("0.395")),
            ("$28,500-$30,500", _d("0.395")),
            ("<$23,500", _d("0.520")),
        ],
    ),
]


class TestTheLadderReachesTheCard:
    """Arm 1 — the reader-facing statement of the ship."""

    def test_the_spy_ladder_serves_a_row(self):
        mid, question, outcomes = SPY_LADDER
        row = _index_row(_market(question, outcomes, mid=mid))
        assert row is not None, "eleven priced rungs and the card shows nothing"

    def test_the_row_names_the_index_without_the_question_around_it(self):
        mid, question, outcomes = SPY_LADDER
        row = _index_row(_market(question, outcomes, mid=mid))
        assert row["sym"] == "S&P 500 (SPY)"

    def test_the_row_names_its_threshold(self):
        """`dir` is rendered verbatim after the percentage: `83% above $755`."""
        mid, question, outcomes = SPY_LADDER
        row = _index_row(_market(question, outcomes, mid=mid))
        assert row["dir"] == "above $755"
        assert row["prob"] == 83.0

    def test_the_number_never_travels_under_the_bare_word_up(self):
        """`83% up` would be a second false claim where #7085 removed the first."""
        mid, question, outcomes = SPY_LADDER
        row = _index_row(_market(question, outcomes, mid=mid))
        assert row["dir"] != "up"

    def test_both_rows_of_the_card_together(self):
        """Two S&P rows are fine when they answer different questions and say so."""
        rows = [
            _index_row(_market(q, o, mid=mid))
            for mid, q, o in (SPY_LADDER, SPX_HEALTHY)
        ]
        served = [r for r in rows if r is not None]
        assert len(served) == 2
        assert (served[0]["prob"], served[0]["dir"]) == (83.0, "above $755")
        assert (served[1]["prob"], served[1]["dir"]) == (53.0, "up")


class TestTheRungIsTheTightestBoundStillFavoured:
    """Arm 2 — chosen on the price, never on the label."""

    def test_not_the_dearest_rung(self):
        """`above $735, 91%` is the loosest bound on the ladder."""
        mid, question, outcomes = SPY_LADDER
        row = _index_row(_market(question, outcomes, mid=mid))
        assert row["prob"] != 90.6
        assert row["dir"] != "above $735"

    def test_not_the_tightest_rung_outright(self):
        """`above $785, 9%` is a bound the market does not expect to hold."""
        mid, question, outcomes = SPY_LADDER
        row = _index_row(_market(question, outcomes, mid=mid))
        assert row["prob"] != 9.5
        assert row["dir"] != "above $785"

    def test_the_last_rung_above_the_coin_flip_wins(self):
        """$760 is 47.5% — under the line — so $755 at 83.0% is the answer."""
        mid, question, outcomes = SPY_LADDER
        _, rungs = _named_threshold_rungs(_market(question, outcomes, mid=mid))
        assert (_pick_rung(rungs).name, _pick_rung(rungs).current_probability) == (
            "$755",
            _d("0.830000"),
        )

    def test_a_ladder_favouring_nothing_falls_back_to_its_dearest_rung(self):
        """The best available statement about a ladder that is long odds throughout."""
        market = _market(
            "S&P 500 (SPY) closes above ___ on September 21?",
            [("Yes", None), ("$900", _d("0.30")), ("$950", _d("0.20")), ("$1000", _d("0.05"))],
        )
        row = _index_row(market)
        assert (row["prob"], row["dir"]) == (30.0, "above $900")

    def test_one_rule_shared_with_the_oil_card(self):
        """`_ladder_rung` and the threshold arm must not drift into two answers."""
        ladder = _market(
            "Number of US oil rigs at end of 2026?",
            [("At least 370", _d("0.97")), ("At least 450", _d("0.57")), ("At least 500", _d("0.12"))],
        )
        priced = [o for o in ladder.outcomes if o.current_probability is not None]
        assert _ladder_rung(ladder) is _pick_rung(priced)


class TestThePartitionsAreRefused:
    """Arm 3 — the four real markets the shape test exists to keep out."""

    def test_no_production_partition_is_read_as_a_ladder(self):
        for mid, question, outcomes in PARTITIONS:
            market = _market(question, outcomes, mid=mid)
            assert _named_threshold_rungs(market) is None, question

    def test_no_production_partition_reaches_the_card(self):
        """Even the two whose questions could be read as threshold-shaped."""
        for mid, question, outcomes in PARTITIONS:
            market = _market(question, outcomes, mid=mid)
            assert _index_row(market) is None, question

    def test_a_span_rung_alone_is_enough_to_refuse(self):
        """The shape test reads labels, so it does not need the sum or the name."""
        market = _market(
            "S&P 500 (SPY) closes above ___ on September 21?",
            [("Yes", None), ("$735", _d("0.90")), ("$740", _d("0.88")), ("$745-$750", _d("0.40"))],
        )
        assert _named_threshold_rungs(market) is None


class TestMonotonicityIsLoadBearing:
    """Arm 4 — what makes a set of rungs cumulative rather than a partition."""

    def test_rungs_that_rise_with_the_strike_are_not_a_ladder(self):
        market = _market(
            "S&P 500 (SPY) closes above ___ on September 21?",
            [("Yes", None), ("$735", _d("0.20")), ("$740", _d("0.60")), ("$745", _d("0.30"))],
        )
        assert _named_threshold_rungs(market) is None
        assert _index_row(market) is None

    def test_a_flat_ladder_is_still_a_ladder(self):
        """Equal neighbouring rungs are ordinary — $740/$745/$750 are all 89.5%."""
        market = _market(
            "S&P 500 (SPY) closes above ___ on September 21?",
            [("Yes", None), ("$735", _d("0.60")), ("$740", _d("0.60")), ("$745", _d("0.60"))],
        )
        assert _named_threshold_rungs(market) is not None

    def test_two_rungs_are_not_enough(self):
        market = _market(
            "S&P 500 (SPY) closes above ___ on September 21?",
            [("Yes", None), ("$735", _d("0.90")), ("$740", _d("0.80"))],
        )
        assert _named_threshold_rungs(market) is None

    def test_the_question_must_carry_a_threshold_word(self):
        """Bare strikes under a question that never says "above" are unreadable."""
        market = _market(
            "S&P 500 (SPY) on September 21?",
            [("Yes", None), ("$735", _d("0.90")), ("$740", _d("0.80")), ("$745", _d("0.70"))],
        )
        assert _named_threshold_rungs(market) is None

    def test_the_threshold_word_printed_is_the_market_s_own(self):
        for word in ("above", "over", "at least"):
            market = _market(
                f"Dow Jones (DJIA) closes {word} ___ on September 21?",
                [("Yes", None), ("$735", _d("0.90")), ("$740", _d("0.80")), ("$745", _d("0.70"))],
            )
            row = _index_row(market)
            # $745 at 70% is the tightest of the three bounds still favoured.
            assert row["dir"] == f"{word} $745", word
            assert row["sym"] == "Dow Jones (DJIA)", word


class TestThe7085GuardsStayGreen:
    """Arm 5 — the withholding this ship is built on top of."""

    def test_an_unpriced_yes_no_market_still_serves_nothing(self):
        market = _market(
            "S&P 500 (SPY) closes above ___ on September 21?",
            [("Yes", None), ("No", None)],
        )
        assert _index_row(market) is None

    def test_a_priced_up_leg_still_takes_the_old_path(self):
        """The ladder arm is reachable ONLY through the unpriced-leg refusal."""
        market = _market(
            "S&P 500 (SPY) closes above ___ on September 21?",
            [("Yes", _d("0.610000")), ("$735", _d("0.90")), ("$740", _d("0.80")), ("$745", _d("0.70"))],
        )
        row = _index_row(market)
        assert (row["prob"], row["dir"]) == (61.0, "up")

    def test_a_priced_zero_keeps_its_row(self):
        """The falsy-Decimal arm: a market that has been priced at zero is data."""
        market = _market(
            "Dow Jones (DJIA) Up or Down on September 21?",
            [("Up", _d("0.000000"))],
        )
        row = _index_row(market)
        assert row is not None and row["prob"] == 0.0


class TestTheStocksCardGetsNothing:
    """Arm 6 — a rung on a card with one text slot is worse than absence."""

    def test_the_same_ladder_serves_no_stock_row(self):
        mid, question, outcomes = SPY_LADDER
        assert _stock_row(_market(question, outcomes, mid=mid)) is None


class TestTheSymbol:
    """Arm 7 — the left column, which is the half a reader reads first."""

    def test_the_verb_is_dropped_with_the_threshold_clause(self):
        market = _market("S&P 500 (SPY) closes above ___ on September 21?", [])
        assert _index_symbol(market, "above") == "S&P 500 (SPY)"

    def test_a_symbol_with_no_verb_survives_intact(self):
        market = _market("Bitcoin above ___ on September 21?", [])
        assert _index_symbol(market, "above") == "Bitcoin"

    def test_the_symbol_is_truncated_like_every_other_row(self):
        market = _market(
            "An extremely long index name that runs on closes above ___?", []
        )
        assert len(_index_symbol(market, "above")) <= 20
