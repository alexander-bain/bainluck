"""#940 phase-1: published-calibration liquidity filter (Kalshi never-bid/never-traded).

Covers the canonical predicate behavior, that the production SQL embeds the
Kalshi-only never-bid/never-traded exclusion + transparency counts, and that the
route fallback keeps the response shape consistent (liquidity_filter key present).
"""

from types import SimpleNamespace

import pytest

from app.routes import calibration
from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    KALSHI_LIQUIDITY_EXISTS,
    KALSHI_LIQUIDITY_RULE_TEXT,
    outcome_is_calibration_liquid,
)


class TestLiquidityPredicate:
    """Canonical definition of the rule: liquid iff ever a real bid OR trade."""

    def test_never_bid_never_traded_excluded(self):
        assert outcome_is_calibration_liquid(0, 0) is False
        assert outcome_is_calibration_liquid(None, None) is False
        assert outcome_is_calibration_liquid(0, None) is False
        assert outcome_is_calibration_liquid(None, 0) is False

    def test_ever_bid_included(self):
        assert outcome_is_calibration_liquid(1, 0) is True
        assert outcome_is_calibration_liquid(0.5, None) is True

    def test_ever_traded_included(self):
        assert outcome_is_calibration_liquid(0, 1) is True
        assert outcome_is_calibration_liquid(None, 0.02) is True

    def test_either_signal_is_sufficient(self):
        # bid-but-never-traded markets (volume==0 but a real bid existed) ARE
        # price-discovered and must be INCLUDED — this is why volume alone is not
        # a faithful proxy (69% agreement vs the snapshot signal in production).
        assert outcome_is_calibration_liquid(0.3, 0) is True


class TestLiquiditySQL:
    def test_predicate_is_kalshi_only_and_uses_bid_and_trade(self):
        assert "vm.source <> 'kalshi'" in KALSHI_LIQUIDITY_EXISTS
        assert "futures_odds_snapshots" in KALSHI_LIQUIDITY_EXISTS
        assert "yes_bid > 0" in KALSHI_LIQUIDITY_EXISTS
        assert "last_price > 0" in KALSHI_LIQUIDITY_EXISTS
        assert "fos.outcome_id = fo.id" in KALSHI_LIQUIDITY_EXISTS

    def test_rule_text_describes_the_filter(self):
        assert "bid" in KALSHI_LIQUIDITY_RULE_TEXT.lower()
        assert "trade" in KALSHI_LIQUIDITY_RULE_TEXT.lower()
        assert "kalshi" in KALSHI_LIQUIDITY_RULE_TEXT.lower()

    def test_main_precompute_query_embeds_filter_and_counts(self):
        import inspect

        src = inspect.getsource(precompute_calibration._precompute_calibration_main)
        # Filter applied as a materialized per-outcome flag, excluded from buckets.
        assert "ranked_outcomes AS MATERIALIZED" in src
        assert "is_liquid" in src
        assert "WHERE ro.is_liquid AND" in src
        # Transparency counts surfaced in the payload.
        assert "kalshi_included" in src
        assert "kalshi_excluded" in src
        assert '"liquidity_filter"' in src


class _FakeResult:
    def __init__(self, *, rows=None, scalar_value=None, one_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self._one_value = one_value

    def all(self):
        return self._rows

    def scalar(self):
        return self._scalar_value

    def one(self):
        return self._one_value


class _FakeDB:
    def __init__(self):
        self._results = [
            _FakeResult(rows=[]),  # main futures
            _FakeResult(rows=[]),  # events
            _FakeResult(rows=[]),  # spreads
            _FakeResult(rows=[]),  # totals
            _FakeResult(scalar_value=0),  # total markets
            _FakeResult(
                one_value=SimpleNamespace(
                    has_closing=0, needs_closing=0, total_completed=0
                )
            ),
        ]

    async def execute(self, statement):
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_route_fallback_includes_liquidity_filter_key():
    # Cold-cache fallback serves liquidity_filter=None for shape consistency;
    # the authoritative filtered numbers come from the precompute->Redis path.
    calibration._cache = {"data": None, "timestamp": 0}
    resp = await calibration.public_calibration(db=_FakeDB(), bust=1)
    assert "liquidity_filter" in resp
    assert resp["liquidity_filter"] is None
