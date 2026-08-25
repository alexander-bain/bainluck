"""#1578 — Polymarket must not WRITE a probability manufactured from an untradeable book.

The durable half of #1574. UX-P011 stopped Discover from *showing* the phantom;
this asserts the poller stops *storing* it, so the number never exists on any
surface.

Every specimen below is a verbatim production row (2026-08-07 census, credentialed
db-query). The population these rules govern:

    priced Polymarket outcomes carrying a book   270,993
    spread >= 0.20                               211,290  (78%)
    spread >= 0.20 AND price IS the midpoint     179,888  (66%)

and, restricted to resolved+graded outcomes, the reason it matters:

    cohort                  n        mean stored price   actual win rate
    everything else         47,207   0.3444              0.3264
    wide-spread midpoint     1,580   0.5003              0.0013

The phantom cohort asserts 50% and wins twice in 1,580.
"""

import inspect

import pytest

from app.tasks.polymarket import (
    _poly_book_is_untradeable,
    _resolve_market_probability,
)
from app.utils.feed_market_quality import FEED_PHANTOM_MIN_SPREAD


def _market(**kwargs):
    """A PolymarketMarket with sensible defaults, overridden by kwargs."""
    from app.services.polymarket_api import PolymarketMarket

    defaults = {
        "condition_id": "0xtest",
        "question": "Test?",
        "outcomes": ["Yes", "No"],
        "outcome_prices": [],
        "best_bid": None,
        "best_ask": None,
        "last_trade_price": None,
    }
    defaults.update(kwargs)
    return PolymarketMarket(**defaults)


class TestPolyBookIsUntradeable:
    """The width predicate itself."""

    def test_penny_bid_dollar_ask_is_untradeable(self):
        assert _poly_book_is_untradeable(0.01, 0.99) is True

    def test_tight_book_is_tradeable(self):
        # 20570794 Fed ladder — the canonical healthy book.
        assert _poly_book_is_untradeable(0.55, 0.57) is False

    def test_no_book_at_all_is_not_judged(self):
        """Both sides absent means there is no order book — a model price.

        This is why the DataGolf / odds_api controls survive by CONSTRUCTION
        rather than by exemption. Returning True here would delete them.
        """
        assert _poly_book_is_untradeable(None, None) is False

    def test_missing_side_is_the_widest_quote_on_that_side(self):
        """"Nobody will buy this at any price" is a wide book, not a missing one."""
        # No bid: treated as 0.0.
        assert _poly_book_is_untradeable(None, 0.93) is True
        # No ask: treated as 1.0.
        assert _poly_book_is_untradeable(0.02, None) is True
        # ...but a missing side still resolves TIGHT when the present side is extreme.
        assert _poly_book_is_untradeable(None, 0.02) is False
        assert _poly_book_is_untradeable(0.98, None) is False

    def test_threshold_is_the_read_side_constant_not_a_restatement(self):
        """Write and read must share ONE meaning of untradeable (#1578)."""
        just_under = FEED_PHANTOM_MIN_SPREAD - 0.001
        assert _poly_book_is_untradeable(0.10, 0.10 + just_under) is False
        assert _poly_book_is_untradeable(0.10, 0.10 + FEED_PHANTOM_MIN_SPREAD) is True

    def test_agrees_with_the_read_side_predicate_on_a_midpoint(self):
        from app.utils.feed_market_quality import is_fabricated_midpoint

        for bid, ask in [(0.01, 0.99), (0.02, 0.94), (0.03, 0.82), (0.55, 0.57)]:
            midpoint = (bid + ask) / 2
            assert _poly_book_is_untradeable(bid, ask) == is_fabricated_midpoint(
                midpoint, bid, ask
            )


class TestResolveDeclinesThePhantom:
    """Production specimens must not yield a stored price."""

    def test_spacex_every_rung_fifty_percent(self):
        """57782305 — 16 rungs, bid 0.01 / ask 0.99, Gamma price 0.500, sum 8.0."""
        m = _market(outcome_prices=[0.50, 0.50], best_bid=0.01, best_ask=0.99)
        assert _resolve_market_probability(m) is None

    def test_netflix_interior_bucket(self):
        """57782215 — bid 0.02 / ask 0.94 -> 0.480. Six of these summed to 289%."""
        m = _market(outcome_prices=[0.48, 0.52], best_bid=0.02, best_ask=0.94)
        assert _resolve_market_probability(m) is None

    def test_netflix_bucket_with_no_bid_at_all(self):
        """57782215 $100-$110 — bid NULL / ask 0.93 -> 0.465.

        The rung that would leak if a missing side were read as "no book".
        """
        m = _market(outcome_prices=[0.465, 0.535], best_ask=0.93)
        assert _resolve_market_probability(m) is None

    def test_oscars_phantom_outranked_the_real_leader(self):
        """58492238 — bid 0.03 / ask 0.82 -> 0.425, shown above a real 14%."""
        m = _market(outcome_prices=[0.425, 0.575], best_bid=0.03, best_ask=0.82)
        assert _resolve_market_probability(m) is None

    def test_computed_midpoint_fallback_is_guarded_too(self):
        """No Gamma price: we would compute the midpoint ourselves. Don't."""
        m = _market(best_bid=0.01, best_ask=0.99)
        assert _resolve_market_probability(m) is None


class TestRealTradeBeatsAWideBook:
    """Somebody actually transacted — that is a belief, whatever the quotes say."""

    def test_wide_book_with_a_real_last_trade_keeps_the_trade_price(self):
        m = _market(
            outcome_prices=[0.50, 0.50],
            best_bid=0.01,
            best_ask=0.99,
            last_trade_price=0.17,
        )
        assert _resolve_market_probability(m) == pytest.approx(0.17)

    def test_the_trade_price_is_used_not_the_phantom_midpoint(self):
        m = _market(
            outcome_prices=[0.48, 0.52],
            best_bid=0.02,
            best_ask=0.94,
            last_trade_price=0.06,
        )
        assert _resolve_market_probability(m) == pytest.approx(0.06)

    def test_degenerate_trade_prices_are_not_a_fallback(self):
        for bad in (0.0, 1.0):
            m = _market(
                outcome_prices=[0.50, 0.50],
                best_bid=0.01,
                best_ask=0.99,
                last_trade_price=bad,
            )
            assert _resolve_market_probability(m) is None


class TestBothDirectionGuard:
    """gotcha #43 — the other direction. Suppression is the sharp edge."""

    def test_tight_book_still_writes_its_price(self):
        """20570794 Fed ladder, bid 0.55 / ask 0.57."""
        m = _market(outcome_prices=[0.56, 0.44], best_bid=0.55, best_ask=0.57)
        assert _resolve_market_probability(m) == pytest.approx(0.56)

    def test_no_book_model_price_is_untouched(self):
        """58036836 golf field — DataGolf/odds_api rows carry no book at all."""
        m = _market(outcome_prices=[0.12, 0.88], last_trade_price=0.12)
        assert _resolve_market_probability(m) == pytest.approx(0.12)

    def test_real_edge_bucket_survives(self):
        """57782215's edge buckets: bid 0.01 / ask 0.02 -> 0.015. REAL."""
        m = _market(outcome_prices=[0.015, 0.985], best_bid=0.01, best_ask=0.02)
        assert _resolve_market_probability(m) == pytest.approx(0.015)

    def test_151_ask_only_evidence_still_works(self):
        """A real sub-max ask with no bid stays trusted.

        The book is wide (0.0 -> 0.52), but Gamma's 0.50 is NOT its midpoint
        (0.26), so this is not the phantom class and the #151 evidence gate
        remains the judge. A width-only write rule would have deleted it — this
        test is the reason the shipped predicate requires midpoint-equality.
        """
        m = _market(outcome_prices=[0.50, 0.50], best_ask=0.52)
        assert _resolve_market_probability(m) == pytest.approx(0.50)

    def test_a_wide_book_price_that_is_not_the_midpoint_is_not_declined(self):
        m = _market(outcome_prices=[0.20, 0.80], best_bid=0.01, best_ask=0.99,
                    last_trade_price=0.20)
        assert _resolve_market_probability(m) == pytest.approx(0.20)


class TestForwardOnlyByConstruction:
    """gotcha #21: this change must be incapable of rewriting a stored price.

    That is a structural property, not a behavioural one, so it is asserted
    structurally. Every upsert call site reads `prob = ...` immediately followed
    by `if prob is None or prob <= 0: continue` — declining to price an outcome
    SKIPS it, so no UPDATE and no snapshot row is ever issued for it, and the
    existing stored value is left exactly as it was.
    """

    def test_every_resolver_call_site_skips_rather_than_writing_null(self):
        from app.tasks import polymarket

        src = inspect.getsource(polymarket)
        # BOTH entry points count. CAL-P094 added
        # `_resolve_market_probability_with_source`, which returns the same price
        # plus the label of the source that produced it, and moved the sub-market
        # loop onto it; the plain name is now a wrapper. Matching only the old
        # spelling would have silently dropped this count from 3 to 2 and reported
        # green — an audit that stops seeing a call site it still needs to audit is
        # worse than no audit, so the matcher tracks the family, not one name.
        #
        # The wrapper's own one-line delegation is excluded by its exact text. It
        # is not a write path — it has no upsert after it and nothing to skip — and
        # counting it would make this guard's "3" mean "2 write paths plus a
        # forwarding line", which is the sort of drift that makes a structural
        # count stop being readable.
        DELEGATION = "prob, _source = _resolve_market_probability_with_source(market)"
        call_sites = [
            i for i, line in enumerate(src.splitlines())
            if ("_resolve_market_probability(market)" in line
                or "_resolve_market_probability_with_source(market)" in line)
            and not line.lstrip().startswith("def ")
            and line.strip() != DELEGATION
        ]
        assert len(call_sites) == 3, (
            f"expected 3 resolver call sites, found {len(call_sites)} — a new "
            "Polymarket write path must be audited against #1578"
        )
        lines = src.splitlines()
        for i in call_sites:
            window = "\n".join(lines[i : i + 5])
            assert "if prob is None or prob <= 0:" in window and "continue" in window, (
                f"call site at line {i + 1} does not skip on None — it may be "
                "nulling an existing stored price (gotcha #21)"
            )

    def test_parent_market_path_no_longer_bypasses_the_guard(self):
        """Path 4 — the least-guarded write, per the #1578 audit."""
        from app.tasks import polymarket

        src = inspect.getsource(polymarket)
        marker = "# Also keep parent market outcomes"
        assert marker in src
        block = src[src.index(marker) : src.index(marker) + 1400]
        assert "is_fabricated_midpoint(" in block, (
            "the parent-market pass takes Gamma's raw outcome_prices[0]; it must "
            "apply the #1578 phantom test"
        )

    def test_websocket_price_stream_is_guarded(self):
        """Path 5 — the only path that UPDATEs directly rather than upserting.

        An unguarded wide quote arriving here would overwrite a GOOD stored price
        with a phantom, which is the one way this class of bug could still cause a
        rewrite. Returning early leaves the stored value untouched.
        """
        from app.tasks import polymarket_ws

        src = inspect.getsource(polymarket_ws)
        handler = src[src.index("async def handle_price") :]
        handler = handler[: handler.index("async def handle_trade")]

        assert "_poly_book_is_untradeable" in handler, (
            "handle_price must not buffer a midpoint from an untradeable book — "
            "this is the only Polymarket path that overwrites a stored price"
        )
        assert handler.index("_poly_book_is_untradeable") < handler.index(
            "(bid_f + ask_f) / 2"
        ), "the width test must precede the midpoint computation"

    def test_kalshi_guard_is_not_touched(self):
        """#1578 guardrail: Kalshi is already guarded and must stay at 0.50."""
        from app.tasks.kalshi import _KALSHI_TIGHT_SPREAD_MAX

        assert _KALSHI_TIGHT_SPREAD_MAX == 0.50
