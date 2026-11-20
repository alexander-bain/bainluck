"""An authoritative No on an open winner field cannot reappear as an old trade."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.polymarket_api import PolymarketEvent, PolymarketMarket
from app.tasks.futures_price_refresh import _fetch_polymarket_prices
from app.tasks.polymarket import _parent_outcome_data, _unpriced_leg_external_ids


def _field():
    def leg(condition_id, title, prices, bid, ask, last, **evidence):
        return PolymarketMarket(
            condition_id=condition_id,
            question=f"Will {title} win Song of the Year?",
            group_item_title=title,
            outcomes=["Yes", "No"],
            outcome_prices=prices,
            best_bid=bid,
            best_ask=ask,
            last_trade_price=last,
            **evidence,
        )

    eliminated = leg(
        "eliminated",
        "I Just Might",
        [0, 1],
        None,
        0.008,
        0.01,
        closed=True,
        uma_resolution_status="resolved",
    )
    proposed = eliminated.model_copy(
        update={
            "condition_id": "proposed",
            "group_item_title": "Proposed No",
            "uma_resolution_status": "proposed",
        }
    )
    nominee = leg("nominee", "the cure", [0.2405, 0.7595], 0.157, 0.324, 0.143)
    return PolymarketEvent(
        id="805158",
        title="Grammy Winner: Song of the Year",
        markets=[eliminated, proposed, nominee],
        neg_risk=True,
    )


@pytest.mark.asyncio
async def test_discovery_and_id_refresh_keep_the_nominee_and_skip_the_graded_loss():
    event = _field()
    discovery = {row["external_id"]: row["prob"] for row in _parent_outcome_data(event)}
    assert discovery == {"nominee": pytest.approx(0.2405), "proposed": 0.01}
    assert "eliminated" not in _unpriced_leg_external_ids(event)

    venue = SimpleNamespace(
        get_events_by_ids=AsyncMock(return_value=[event]),
        _parse_event=lambda value: value,
    )
    priced, unpriced = await _fetch_polymarket_prices(venue, [event.id])
    assert {
        row["external_id"]: row["probability"] for row in priced[event.id]
    } == discovery
    assert "eliminated" not in unpriced[event.id]


@pytest.mark.parametrize("external_id", ["805158", "another_board"])
def test_detail_puts_the_graded_grammy_loss_after_contenders(external_id):
    from datetime import datetime, timezone

    from app.routes.futures import _format_market_detail

    observed = datetime(2026, 11, 20, 22, 12, tzinfo=timezone.utc)

    def outcome(oid, name, value, authority=None):
        return SimpleNamespace(
            id=oid,
            name=name,
            external_id=f"condition-{oid}",
            current_probability=value,
            current_american_odds=500,
            current_yes_bid=None,
            current_yes_ask=None,
            rank=oid,
            rank_change_24h=1,
            probability_change_24h=0.001,
            opening_probability=0.01,
            opening_american_odds=9990,
            is_winner=False,
            resolution_source=authority,
            last_updated=observed,
            price_changed_at=observed,
        )

    market = SimpleNamespace(
        id=58492243,
        name="Grammys 2027: Song of the Year Winner",
        description=None,
        category="award",
        source="polymarket",
        external_id=external_id,
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=3,
        llm_sport_category="entertainment",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=observed,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        image_url=None,
        category_tags=[],
        market_metadata={},
        outcomes=[
            outcome(1, "the cure", 0.2405),
            outcome(2, "I Just Might", 0.01, "api_settlement"),
            outcome(3, "Man I Need", 0.1165),
            outcome(4, "A live long shot", 0.004),
        ],
    )
    response = _format_market_detail(market, normalize_numbers=False)
    rows = {row["id"]: row for row in response["outcomes"]}
    assert rows[1]["probability"] == 0.2405
    assert rows[3]["probability"] == 0.1165
    assert rows[4]["probability"] == 0.004
    assert not rows[4].get("is_out")
    eliminated = rows[2]
    if external_id == "805158":
        assert response["outcomes"][-1]["id"] == 2
        assert eliminated["is_out"] is True
        assert eliminated["source_mark"]["settled"]["result"] == "Out"
        assert eliminated["source_mark"]["settled"]["at"] is None
        for field in (
            "probability", "american_odds", "opening_probability",
            "probability_change_24h", "last_updated", "price_changed_at",
        ):
            assert eliminated[field] is None
    else:
        assert not eliminated.get("is_out")
        assert eliminated["probability"] == 0.01
        assert eliminated["last_updated"] == observed.isoformat()
