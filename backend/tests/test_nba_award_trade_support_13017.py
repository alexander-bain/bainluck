"""Multi-selection basketball awards need current support for a majority price."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes import futures as route


@pytest.mark.parametrize(
    ("ticker", "ask"),
    [
        ("KXNBAROOKIE1STTEAM-27", "0.99"),
        ("KXNBAROOKIE2NDTEAM-27", "0.99"),
        ("KXNBAAWARDFIN-27ROY", "1.00"),
    ],
)
def test_philon_trade_is_refused_only_with_current_absence_of_support(ticker, ask):
    observed_at = datetime(2026, 11, 19, 2, tzinfo=timezone.utc)
    row = {
        "current_probability": Decimal("0.87"),
        "current_yes_bid": Decimal("0"),
        "current_yes_ask": Decimal(ask),
        "volume_24h": Decimal("0"),
        "volume_24h_at": observed_at,
        "last_updated": observed_at,
        "resolution_source": None,
    }
    controls = [
        {},
        {"volume_24h": Decimal("0.04")},
        {"current_yes_bid": Decimal("0.01")},
        {"volume_24h": None},
        {"volume_24h_at": observed_at - timedelta(seconds=1)},
        {"resolution_source": "api_settlement"},
        {"current_probability": Decimal("0.25")},
    ]
    outcomes = [
        SimpleNamespace(id=index, **(row | control))
        for index, control in enumerate(controls, start=1)
    ]
    market = SimpleNamespace(
        source="kalshi", external_id=ticker, market_type="field", outcomes=outcomes,
        market_metadata={"shape": {"expected_winners": 5}},
    )
    trades = {outcome.id: outcome.current_probability for outcome in outcomes}
    candidates = route._unsupported_price_candidates(market)

    assert route._unsupported_price_verdicts(market, candidates, trades) == {1}
    assert route._unsupported_price_verdicts(market, candidates, {}) == set()

    market.external_id = "KXNBAMVP-27"
    assert route._unsupported_price_verdicts(market, candidates, trades) == set()
