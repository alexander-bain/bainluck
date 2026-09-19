"""#7085: the `/economics` TODAY'S CLOSE card stops printing an absent price as `0%`.

Measured on the served `GET /api/economics` payload, 2026-09-18 ~01:05Z —
`themes.markets.today`, the card badged **LIVE**, held exactly two rows:

    S&P 500 (SPY) closes     0%  up      <- market 61381310
    S&P 500 (SPX)           53%  up

Two rows for one index, the first asserting there is no chance the S&P closes
up. It is not a zero. Market `61381310` — *"S&P 500 (SPY) closes above ___ on
September 21?"* — has `current_probability` **NULL** on its `Yes` leg behind a
live two-sided book (`current_yes_bid` 0.5500, `current_yes_ask` 0.7800,
`last_updated` 2026-09-18 13:15:32Z). The builder read that absence as
`float(o.current_probability or 0)` and printed the result as a real
probability. `0%` is worse than a blank because it is a confident claim.

Same class as #6996 / #7016 / #7037: a value that is not known is withheld,
never rendered as a number.

WHY THE ROW IS DROPPED RATHER THAN NULLED, since the opposite is the obvious
first instinct and it is wrong here. `frontend/app/economics/page.tsx` renders
each row as `{idx.prob}% {idx.dir}` with no null arm, so serving
`{"prob": null}` would print `"% up"` — a repair that makes the screen worse.
On a LIST surface withholding removes the item; that is the same call #7016
made when a boxing-hub card lost every price. The end state where every index
leg is unpriced is an ABSENT card (the page guards on `today.length > 0`),
which is honest-empty (ruling 027), not a regression.

WHY THE REFUSAL IS `is None` AND NOT `or 0`. `current_probability` is
`Numeric(7, 6)`, so a genuine priced zero arrives as `Decimal("0.000000")`,
which is FALSY. A market that has been priced at zero — the venue saying "no" —
is data and keeps its row. Only NULL is the absence of data. `_market_row` in
the same file carries this reasoning already; these two builders are the ones
that never got it. Arm 3 below is the whole reason the predicate is spelled
that way, and it is the arm a careless rewrite fails.

WHAT THIS FILE PINS

  1. the production specimen serves NO row, and the healthy sibling beside it
     still serves 53.0 — a fix that emptied the card would satisfy "the 0% is
     gone" exactly as happily as a repair does, so the surviving row is
     asserted as an EQUALITY, not as "not zero";
  2. the single-stocks branch, which carries the identical coercion one `elif`
     down onto a card that prints a bare `{prob}%`;
  3. a priced zero KEEPS its row at 0.0 — the falsy-Decimal arm;
  4. the leg scan is unchanged: first matching leg wins, no substitution of a
     priced sibling for an unpriced one, and a market with no up/yes leg at all
     still yields nothing;
  5. the surviving fields — `sym`, `dir`, `range`, `src`, the `[:20]`/`[:6]`
     truncations — are byte-for-byte what the inline bodies produced, because
     this ship hoisted them into named functions and a hoist that quietly
     reshapes the payload is a second change hiding inside the first.
"""

import pytest
from decimal import Decimal

from app.models import FuturesMarket, FuturesOutcome
from app.routes.economics import _index_row, _stock_row, _up_leg


def _market(name: str, outcomes: list[tuple[str, object]], *, mid: int = 1, source: str = "polymarket"):
    """A real `FuturesMarket` carrying real `FuturesOutcome` rows.

    Real ORM objects rather than stand-ins: the builders read `.source` and
    `.rank` as well as `.name` and `.current_probability`, and a double that
    carries only today's fields turns tomorrow's column read into an
    AttributeError in the guard instead of a finding in the code.
    """
    market = FuturesMarket(id=mid, name=name, source=source)
    market.outcomes = [
        FuturesOutcome(name=n, external_id=f"{mid}-{n}", current_probability=p)
        for n, p in outcomes
    ]
    return market


# --------------------------------------------------------------------------
# The two production rows of the card, by market id.
# --------------------------------------------------------------------------

#: The defect. NULL `Yes` price behind a live 0.55/0.78 book.
SPY_PLACEHOLDER = (
    61381310,
    "S&P 500 (SPY) closes above ___ on September 21?",
    [("Yes", None), ("No", None)],
)

#: The healthy row printed directly beneath it on the same card.
SPX_HEALTHY = (
    61340001,
    "S&P 500 (SPX) Up or Down on September 18?",
    [("Up", Decimal("0.530000")), ("Down", Decimal("0.470000"))],
)


class TestTheUnpricedIndexRowIsWithheld:
    """Arm 1 — the reader-facing statement of the defect."""

    def test_the_spy_placeholder_serves_no_row(self):
        mid, question, outcomes = SPY_PLACEHOLDER
        assert _index_row(_market(question, outcomes, mid=mid)) is None

    def test_the_healthy_sibling_still_serves_its_real_price(self):
        """A card emptied by the fix satisfies arm 1 as well as a repair does."""
        mid, question, outcomes = SPX_HEALTHY
        row = _index_row(_market(question, outcomes, mid=mid))
        assert row is not None, "the fix must not take the whole card with it"
        assert row["prob"] == 53.0

    def test_the_card_no_longer_claims_the_sp_cannot_close_up(self):
        """The two rows as the reader met them, asserted together.

        The surviving card says one thing about the S&P instead of two
        contradictory ones.
        """
        rows = [
            _index_row(_market(q, o, mid=mid))
            for mid, q, o in (SPY_PLACEHOLDER, SPX_HEALTHY)
        ]
        served = [r for r in rows if r is not None]
        assert len(served) == 1
        assert served[0]["prob"] == 53.0
        assert not any(r["prob"] == 0.0 for r in served)


class TestTheSingleStocksBranchToo:
    """Arm 2 — the identical coercion one `elif` down."""

    def test_an_unpriced_stock_serves_no_row(self):
        assert _stock_row(_market("Meta Platforms (META) Up or Down on September 18?", [("Up", None)])) is None

    def test_a_priced_stock_still_serves(self):
        row = _stock_row(_market("Meta Platforms (META) Up or Down on September 18?", [("Up", Decimal("0.610000"))]))
        assert row is not None
        assert row["prob"] == 61.0
        assert row["sym"] == "META"


class TestAPricedZeroIsDataAndKeepsItsRow:
    """Arm 3 — the falsy-`Decimal` arm, and the reason the test is `is None`.

    `Decimal("0.000000")` is falsy, so the natural rewrite — refusing on
    `not o.current_probability`, or keeping `or 0` and dropping the row when the
    result is 0 — throws away a market the venue HAS priced, at zero, alongside
    the ones it has not priced at all. These two cases print the same `0%` and
    mean opposite things.
    """

    def test_an_index_priced_at_zero_keeps_its_row(self):
        row = _index_row(_market("Dow Up or Down on September 18?", [("Up", Decimal("0.000000"))]))
        assert row is not None
        assert row["prob"] == 0.0

    def test_a_stock_priced_at_zero_keeps_its_row(self):
        row = _stock_row(_market("Tesla (TSLA) Up or Down on September 18?", [("Up", Decimal("0.000000"))]))
        assert row is not None
        assert row["prob"] == 0.0

    def test_float_zero_is_also_data(self):
        """Not every caller hands these builders a `Decimal`."""
        row = _index_row(_market("VIX Up or Down on September 18?", [("Up", 0.0)]))
        assert row is not None
        assert row["prob"] == 0.0


class TestTheLegScanIsUnchanged:
    """Arm 4 — the hoist moved the loop; it did not renegotiate it."""

    @pytest.mark.parametrize("leg_name", ["Up", "up", "Yes", "yes", ""])
    def test_every_name_the_inline_loop_matched_still_matches(self, leg_name):
        market = _market("NASDAQ Up or Down on September 18?", [(leg_name, Decimal("0.42"))])
        assert _up_leg(market) is not None
        assert _index_row(market)["prob"] == 42.0

    def test_a_market_with_no_up_or_yes_leg_yields_nothing(self):
        market = _market("VIX Up or Down on September 18?", [("Down", Decimal("0.70"))])
        assert _up_leg(market) is None
        assert _index_row(market) is None
        assert _stock_row(market) is None

    def test_an_unpriced_first_leg_is_not_swapped_for_a_priced_later_one(self):
        """The row must not silently start answering a different question.

        A fallthrough would make the card print a number again, which looks
        like a better fix and is a worse one: the substituted leg is a
        different claim wearing the first one's row.
        """
        market = _market(
            "S&P 500 (SPY) closes above ___ on September 21?",
            [("Yes", None), ("Yes", Decimal("0.77"))],
        )
        assert _index_row(market) is None


class TestTheHoistDidNotReshapeThePayload:
    """Arm 5 — every surviving field is what the inline bodies produced."""

    def test_the_index_row_keys_and_constants(self):
        mid, question, outcomes = SPX_HEALTHY
        row = _index_row(_market(question, outcomes, mid=mid))
        assert set(row) == {"sym", "prob", "dir", "range", "src"}
        assert row["dir"] == "up"
        assert row["range"] == ""
        assert row["src"] == "polymarket"

    def test_the_stock_row_keys_and_constants(self):
        row = _stock_row(_market("Apple (AAPL) Up or Down on September 18?", [("Up", Decimal("0.5"))], source="kalshi"))
        assert set(row) == {"sym", "prob", "delta", "src"}
        assert row["delta"] is None
        assert row["src"] == "kalshi"

    @pytest.mark.parametrize(
        "question,sym",
        [
            ("S&P 500 (SPX) Up or Down on September 18?", "S&P 500 (SPX)"),
            ("NASDAQ Up or Down on September 18?", "NASDAQ"),
            ("Dow up or down on September 18?", "Dow"),
            # The `[:20]` truncation, unchanged.
            ("S&P 500 (SPX) closes higher on September 18 than it did yesterday?", "S&P 500 (SPX) closes"),
        ],
    )
    def test_the_index_symbol_is_derived_exactly_as_before(self, question, sym):
        assert _index_row(_market(question, [("Up", Decimal("0.5"))]))["sym"] == sym

    @pytest.mark.parametrize(
        "question,sym",
        [
            ("Meta Platforms (META) Up or Down?", "META"),
            # No parenthesis: the first whitespace token, truncated to six.
            ("Microsoft Up or Down?", "Micros"),
        ],
    )
    def test_the_stock_symbol_is_derived_exactly_as_before(self, question, sym):
        assert _stock_row(_market(question, [("Up", Decimal("0.5"))]))["sym"] == sym
