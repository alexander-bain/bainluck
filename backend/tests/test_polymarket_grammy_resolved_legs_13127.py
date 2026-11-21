"""An authoritative No on an open winner field cannot reappear as an old trade."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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


@pytest.mark.parametrize(
    ("source", "external_id", "grammy"),
    [
        ("polymarket", "805158", True),
        ("polymarket", "another_board", False),
        ("kalshi", "KXGRAMMY-SOTY69", True),
        ("kalshi", "KXGRAMMY-ROTY69", True),
        ("kalshi", "KXGRAMAOTY-69", True),
        ("kalshi", "KXGRAMBNA-69", True),
        ("kalshi", "KXOTHER-FIELD", False),
    ],
)
def test_detail_puts_the_graded_grammy_loss_after_contenders(
    source, external_id, grammy, monkeypatch
):
    from datetime import datetime, timezone

    from app.routes import futures

    observed = datetime(2026, 11, 20, 22, 12, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return observed.astimezone(tz) if tz else observed.replace(tzinfo=None)

    monkeypatch.setattr(futures, "datetime", FrozenDatetime)

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
        source=source,
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
            outcome(5, "Tie", 0.2),
            outcome(6, "Unknown result", 0.0, "ungradeable_result"),
        ],
    )
    response = futures._format_market_detail(market, normalize_numbers=False)
    rows = {row["id"]: row for row in response["outcomes"]}
    assert rows[1]["probability"] == 0.2405
    assert rows[3]["probability"] == 0.1165
    assert rows[4]["probability"] == 0.004
    assert not rows[4].get("is_out")
    assert not rows[6].get("is_out")
    if grammy and source == "kalshi":
        assert response["outcomes"][-2]["id"] == 5
        assert rows[5]["name"] == "Tie (co-winners)"
        assert rows[5]["probability"] == 0.2
    eliminated = rows[2]
    if grammy:
        assert response["outcomes"][-1]["id"] == 2
        from app.utils.settled_price import SETTLED_NO_PRICE

        assert eliminated["is_out"] is True
        assert eliminated["probability"] == float(SETTLED_NO_PRICE)
        assert eliminated["source_mark"]["settled"]["result"] == "Out"
        assert eliminated["source_mark"]["settled"]["at"] is None
        for field in (
            "rank", "rank_change_24h", "american_odds", "opening_probability",
            "probability_change_24h", "last_updated", "price_changed_at",
        ):
            assert eliminated[field] is None
    else:
        assert not eliminated.get("is_out")
        assert eliminated["probability"] == 0.01
        assert eliminated["last_updated"] == observed.isoformat()


@pytest.mark.parametrize("requested_id", [58492243, 100])
async def test_grammy_detail_keeps_its_address_and_never_blends_the_two_boards(
    monkeypatch, requested_id,
):
    from app.routes import futures

    old = SimpleNamespace(id=58492243, source="polymarket", external_id="805158", outcomes=[])
    current = SimpleNamespace(
        id=100, source="kalshi", external_id="KXGRAMMY-SOTY69",
        outcomes=[SimpleNamespace(id=oid) for oid in (900, 901, 902)],
    )
    legacy_request = requested_id == old.id
    db_result = Mock()
    db_result.unique.return_value = db_result
    db_result.scalar_one_or_none.return_value = old if legacy_request else current
    db = SimpleNamespace(execute=AsyncMock(return_value=db_result))
    fields = {old.id: current} if legacy_request else {}
    monkeypatch.setattr(futures, "grammy_nominee_fields", AsyncMock(return_value=fields))
    monkeypatch.setattr(futures, "grammy_pre_nomination_board", AsyncMock(return_value=old))
    source_read = AsyncMock(return_value=(["kalshi"], []))
    monkeypatch.setattr(futures, "_load_market_sources", source_read)
    for name, result in (
        ("_withheld_price_outcome_ids", set()),
        ("_fleet_newest_observation", None),
        ("_game_container_leg_sides", {}),
        ("_game_container_lead_leg", None),
        ("_game_container_of_event_id", None),
        ("out_legs_by_market", {}),
    ):
        monkeypatch.setattr(futures, name, AsyncMock(return_value=result))
    blend = AsyncMock()
    monkeypatch.setattr(futures, "_resolve_verified_title", blend)

    def detail(market, *args, **kwargs):
        if market is current:
            rows = [
                {"id": 900, "name": "the cure", "probability": 0.22, "source_mark": "kalshi"},
                {"id": 901, "name": "Tie (co-winners)", "probability": 0.01},
                {"id": 902, "name": "Aperture", "is_out": True, "rank": None},
            ]
        else:
            rows = [
                {"id": 1, "name": "the cure", "probability": 0.30},
                {"id": 2, "name": "I Just Might", "is_out": True, "rank": None},
                {"id": 3, "name": "APERTURE – Harry Styles", "is_out": True, "rank": None},
                {"id": 4, "name": "the cure - Olivia Rodrigo", "is_out": True, "rank": None},
                {"id": 5, "name": "Aperture - Remix - Harry Styles", "is_out": True, "rank": None},
            ]
        return {"id": market.id, "source": market.source, "outcomes": rows}

    monkeypatch.setattr(futures, "_format_market_detail", detail)
    result = await futures.get_futures_market(
        requested_id, db, representation=futures.REPRESENTATION_VERIFIED_TITLE,
    )
    assert result["id"] == requested_id and result["source"] == "kalshi"
    assert result["outcome_count"] == 5
    assert [row["id"] for row in result["outcomes"]] == [900, 901, 902, 2, 5]
    assert result["outcomes"][0]["probability"] == 0.22
    assert result["outcomes"][0]["source_mark"] == "kalshi"
    assert result["outcomes"][-1]["rank"] is None
    source_read.assert_awaited_once_with(db, 100, [900, 901, 902])
    blend.assert_not_awaited()


@pytest.mark.parametrize(
    ("endpoint", "requested_id"),
    [("history", 58492243), ("timeline", 58492243), ("timeline", 100)],
)
async def test_grammy_chart_reads_the_nominee_field_at_either_address(
    monkeypatch, endpoint, requested_id,
):
    from app.routes import futures

    legacy = SimpleNamespace(id=58492243, source="polymarket", external_id="805158", outcomes=[])
    field = SimpleNamespace(
        id=100, source="kalshi", external_id="KXGRAMMY-SOTY69", status="open",
        name="Song of the Year", outcomes=[], commence_time=None, market_metadata={},
    )
    market_row = legacy if requested_id == legacy.id else field
    market_result = Mock()
    market_result.unique.return_value = market_result
    market_result.scalar_one_or_none.return_value = market_row
    snapshots = Mock()
    snapshots.scalars.return_value.all.return_value = []
    db = SimpleNamespace(execute=AsyncMock(side_effect=[market_result, snapshots]))
    fields = {legacy.id: field} if market_row is legacy else {}
    monkeypatch.setattr(futures, "grammy_nominee_fields", AsyncMock(return_value=fields))
    screen = AsyncMock(return_value=set())
    monkeypatch.setattr(futures, "_withheld_price_outcome_ids", screen)
    blend = AsyncMock()
    monkeypatch.setattr(futures, "_resolve_verified_title", blend)

    if endpoint == "timeline":
        monkeypatch.setattr(futures, "_format_market_detail", Mock(return_value={"outcomes": []}))
        result = await futures.get_probability_timeline(
            requested_id, top=10, hours=168, db=db,
            representation=futures.REPRESENTATION_VERIFIED_TITLE,
        )
    else:
        monkeypatch.setattr(futures, "out_legs_by_market", AsyncMock(return_value={}))
        monkeypatch.setattr(
            futures, "_load_generic_venue_history",
            AsyncMock(return_value=futures._GenericVenueHistory()),
        )
        result = await futures.get_futures_history(
            requested_id, outcome_id=None, hours=8760, top_n=10, champion=None, db=db,
        )
        snapshot_query = db.execute.await_args_list[1].args[0]
        assert snapshot_query.compile().params["market_id_1"] == field.id

    assert result["market_id"] == requested_id
    assert result["market_name"] == field.name
    screen.assert_awaited_once_with(db, field)
    blend.assert_not_awaited()
