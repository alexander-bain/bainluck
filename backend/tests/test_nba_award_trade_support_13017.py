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
    observed_at = datetime.now(timezone.utc)
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


@pytest.mark.parametrize(
    ("outcome_id", "ticker", "ask", "volume_age"),
    [
        (231405445, "KXNBAROOKIE1STTEAM-27", "0.99", timedelta(0)),
        (231405405, "KXNBAROOKIE2NDTEAM-27", "0.99", timedelta(0)),
        (246258589, "KXNBAAWARDFIN-27ROY", "0.98", timedelta(days=6, hours=12)),
    ],
)
async def test_award_withholds_the_stored_book_when_newest_snapshot_has_no_trade(
    monkeypatch, outcome_id, ticker, ask, volume_age,
):
    updated = datetime.now(timezone.utc)
    fields = {
        "current_probability": Decimal("0.87"),
        "current_yes_bid": Decimal("0"),
        "current_yes_ask": Decimal(ask),
        "volume_24h": Decimal("0"),
        "volume_24h_at": updated - volume_age,
        "last_updated": updated,
        "resolution_source": None,
    }
    controls = {
        # Missing snapshot, positive activity, quoted bid, unknown volume,
        # unstamped volume, recorded result, and an unfavored player.
        1: {},
        2: {"volume_24h": Decimal("0.04")},
        3: {"current_yes_bid": Decimal("0.01")},
        4: {"volume_24h": None},
        5: {"volume_24h_at": None},
        6: {"resolution_source": "api_settlement"},
        7: {"current_probability": Decimal("0.25")},
        # An older zero-volume reading cannot overrule a positive trade.
        8: {"volume_24h_at": updated - timedelta(seconds=1)},
    }
    market = SimpleNamespace(
        source="kalshi",
        external_id=ticker,
        market_type="field",
        market_metadata={"shape": {"expected_winners": 5}},
        outcomes=[
            SimpleNamespace(id=outcome_id, **fields),
            *(SimpleNamespace(id=key, **(fields | overrides))
              for key, overrides in controls.items()),
        ],
    )
    stored = {outcome_id: None, **dict.fromkeys(range(2, 8)), 8: Decimal("0.87")}
    queries = []

    async def newest_trades(db, outcome_ids):
        queries.append(outcome_ids)
        return {key: stored[key] for key in outcome_ids if key in stored}

    monkeypatch.setattr(route, "_newest_kalshi_trades", newest_trades)

    assert await route._unsupported_price_outcome_ids(None, market) == {outcome_id}
    assert len(queries) == 1
    assert outcome_id in queries[0]

    market.external_id = "KXNBAMVP-27"
    assert await route._unsupported_price_outcome_ids(None, market) == set()
