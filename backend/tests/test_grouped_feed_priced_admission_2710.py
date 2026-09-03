"""#2710 — the grouped feed stops spending a card slot on a market with no price.

THE DEFECT, MEASURED. Alex, on mobile ``/sports`` 2026-09-02 15:40: "every
outcome is a dash ... Rule: a card with no number is not shown." The props strip
renders one card per grouped-feed row and had no admission of any kind, so a
market arriving with ``outcomes: []`` became a full-height card whose body was
the words "No outcomes available", and a market whose outcomes were all unpriced
became a column of dashes. Measured on the served payload at the page's own
``limit: 20`` (which is what ``app/sports/page.tsx`` requests) on 2026-09-03:
**2 of 20 rows carried ``outcomes: []``**.

WHY THE FILTER IS ABOVE THE SLICE. Dropping these after ``[:limit]`` would leave
the reader with 18 cards instead of 20; dropping them before backfills the slots
from the ``limit * 5`` markets the route has already loaded. Same reason #2789
sorted above its own truncation rather than below it. ``select_ungrouped_markets``
exists as a named function purely so that ordering is a testable property rather
than a claim about a comprehension.

THE ARM THAT WOULD HAVE BROKEN EVERYTHING, and it is the reason this file leads
with types rather than with counts. ``FuturesOutcome.probability`` is a property
returning ``current_probability``, whose column is ``Numeric(7, 6)`` — so the
value in ``market_dicts`` is a ``decimal.Decimal``, NOT a float, despite the
``Mapped[Optional[float]]`` annotation. ``isinstance(x, (int, float))`` is False
for a Decimal, and so is ``isinstance(x, numbers.Real)``; Decimal registers only
as ``numbers.Number``. Either spelling would have admitted **nothing** and
emptied the strip on every request. Same Decimal-on-this-endpoint seam as #2554.

WHAT THIS SUITE DOES NOT COVER, said plainly: the three GROUPED arms
(``threshold`` / ``stat_prop`` / ``playoff_progression``) are not filtered here.
The measured defect was in the ungrouped market arm, and the renderer-side guard
(``frontend/lib/sports/propStripAdmission.ts``) fails closed on all four, which
is also what covers a warm Redis entry written before this deploy. A backend
filter for the other three is a follow-up, not a silent omission.
"""

import ast
import inspect
from decimal import Decimal

import pytest

import app.routes.futures as futures_module
from app.routes.futures import (
    _market_has_priced_outcome,
    select_ungrouped_markets,
)


def market(market_id: int, *probabilities):
    """A ``market_dicts`` row in the shape the route builds it."""
    return {
        "id": market_id,
        "name": f"Market {market_id}",
        "outcomes": [
            {"id": market_id * 100 + i, "name": f"O{i}", "probability": p}
            for i, p in enumerate(probabilities)
        ],
    }


class TestPricedOutcomeDetection:
    def test_a_decimal_is_a_price(self):
        """THE LOAD-BEARING CASE: this is what the ORM actually hands us."""
        assert _market_has_priced_outcome(market(1, Decimal("0.925"))) is True

    def test_a_float_is_a_price(self):
        assert _market_has_priced_outcome(market(1, 0.925)) is True

    def test_an_int_is_a_price(self):
        assert _market_has_priced_outcome(market(1, 1)) is True

    def test_a_genuine_zero_is_a_price(self):
        """A truthiness test would drop a real, printable 0%."""
        assert _market_has_priced_outcome(market(1, Decimal("0"))) is True
        assert _market_has_priced_outcome(market(1, 0.0)) is True

    def test_no_outcomes_at_all_is_not_a_price(self):
        """The measured row: 2 of 20 on the served payload."""
        assert _market_has_priced_outcome(market(1)) is False

    def test_every_outcome_unpriced_is_not_a_price(self):
        """Alex's 'Yes -, No -'."""
        assert _market_has_priced_outcome(market(1, None, None)) is False

    def test_one_priced_outcome_is_enough(self):
        assert _market_has_priced_outcome(market(1, None, Decimal("0.31"))) is True

    def test_a_stringified_probability_is_not_a_price(self):
        """#2554's shape. A string is truthy and the card cannot render it."""
        assert _market_has_priced_outcome(market(1, "0.682560")) is False

    def test_a_bool_is_not_a_price(self):
        """``isinstance(True, int)`` is True, so this needs saying explicitly."""
        assert _market_has_priced_outcome(market(1, True)) is False

    @pytest.mark.parametrize("missing", [{}, {"outcomes": None}, {"outcomes": []}])
    def test_a_malformed_row_is_refused_rather_than_raising(self, missing):
        assert _market_has_priced_outcome({"id": 1, **missing}) is False


class TestSelectionHappensBeforeTruncation:
    def test_the_freed_slots_are_backfilled(self):
        """THE PROPERTY THAT MAKES THIS A FIX RATHER THAN A DELETION.

        Twenty asked for; the first two carry no price. Filtering first must
        still yield twenty cards, all of them priced — not eighteen.
        """
        markets = [market(1), market(2)] + [
            market(i, Decimal("0.5")) for i in range(3, 40)
        ]
        selected = select_ungrouped_markets(markets, set(), 20)
        assert len(selected) == 20
        assert all(_market_has_priced_outcome(m) for m in selected)
        assert [m["id"] for m in selected] == list(range(3, 23))

    def test_filtering_after_the_slice_would_have_shipped_fewer(self):
        """COUNTER-CASE, run rather than asserted.

        The fix a reader would improvise — filter the already-sliced list —
        yields 18 where 20 were asked for. Pinning the difference is what stops
        a later 'simplification' from moving the filter below the slice.
        """
        markets = [market(1), market(2)] + [
            market(i, Decimal("0.5")) for i in range(3, 40)
        ]
        sliced_then_filtered = [
            m for m in markets[:20] if _market_has_priced_outcome(m)
        ]
        assert len(sliced_then_filtered) == 18
        assert len(select_ungrouped_markets(markets, set(), 20)) == 20

    def test_grouped_markets_are_still_excluded(self):
        """CONTROL: green before this change too.

        The pre-existing responsibility of this selection is to skip markets
        already rendered by a grouped kernel. If this goes red the fix has
        replaced the old rule instead of adding to it.
        """
        markets = [market(i, Decimal("0.5")) for i in range(1, 6)]
        selected = select_ungrouped_markets(markets, {2, 4}, 10)
        assert [m["id"] for m in selected] == [1, 3, 5]

    def test_the_limit_is_still_honoured(self):
        """CONTROL: green before this change too."""
        markets = [market(i, Decimal("0.5")) for i in range(1, 40)]
        assert len(select_ungrouped_markets(markets, set(), 7)) == 7

    def test_an_all_priced_input_is_untouched(self):
        """CONTROL: green before this change too — the filter narrows, never shrinks."""
        markets = [market(i, Decimal("0.5")) for i in range(1, 6)]
        selected = select_ungrouped_markets(markets, set(), 20)
        assert [m["id"] for m in selected] == [1, 2, 3, 4, 5]


class TestTheRouteActuallyUsesIt:
    """Without this class the suite is green on the bug, and I measured that.

    Reverting only the route's call site — leaving the two helpers in place and
    tested — left the other 17 tests **all passing**, because they exercise a
    pure function nothing was obliged to call. That is a guard stopping one step
    short of the thing the reader sees. This is the arm that goes red.

    Read by AST rather than by grepping `inspect.getsource`: the route's comment
    block names `select_ungrouped_markets` in prose, so a substring scan is
    satisfied by the explanation of the fix even when the fix is not wired in.
    """

    @staticmethod
    def _grouped_feed_ast() -> ast.AST:
        tree = ast.parse(inspect.getsource(futures_module))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "grouped_feed"
            ):
                # Drop the docstring so prose about the fix cannot satisfy a
                # check about the code (the #2038-family trap).
                body = list(node.body)
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    body = body[1:]
                return ast.Module(body=body, type_ignores=[])
        raise AssertionError("grouped_feed route not found in app.routes.futures")

    def test_the_route_calls_the_selector(self):
        called = {
            n.func.id
            for n in ast.walk(self._grouped_feed_ast())
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "select_ungrouped_markets" in called, (
            "grouped_feed no longer routes its ungrouped markets through the "
            "priced-outcome selector — the strip is free to ship cards with no "
            "number again (#2710)."
        )

    def test_the_route_does_not_re_derive_the_selection_inline(self):
        """The old shape was an inline comprehension over `grouped_market_ids`.

        If one reappears in the route body, the selection has been restated
        rather than called, and the two can drift — which is how the filter
        would silently end up below the truncation again.
        """
        inline = [
            n
            for n in ast.walk(self._grouped_feed_ast())
            if isinstance(n, ast.ListComp)
            and any(
                isinstance(sub, ast.Name) and sub.id == "grouped_market_ids"
                for sub in ast.walk(n)
            )
        ]
        assert inline == [], (
            "the ungrouped selection is spelled inline in the route again; it "
            "belongs in select_ungrouped_markets so the filter cannot drift "
            "below the truncation"
        )
