"""The CFP successor needs venue-confirmed members and one shared card/page set."""

from copy import deepcopy
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.utils import roundup_containers as roundups
from app.utils.field_selection import (
    build_field_selection_producer,
    select_field_selection,
)
from tests.test_field_band import _make_cfp_qualifiers_market, _make_cfp_title_market


def definition():
    return {
        "slug": "roundup-cfp-selected-field-2026",
        "kind": "roundup",
        "membership": "computed-produced",
        "name": "College Football Playoff field",
        "category": "ncaaf",
        "section_title": ["Playoff field", "Title contenders"],
        "footer": "Venue-confirmed playoff field · title chances below",
        "relations": ["same_event", "same_window"],
        "level": "member",
        "enabled": False,
        "rule": {
            "producer": "field_selection",
            "field": "kalshi:KXNCAAFPLAYOFF-26",
            "second_section": "kalshi:KXNCAAF-27",
            "selected_count": 12,
            "min_field_outcomes": 24,
            "valid_from": "2026-12-06T00:00:00-08:00",
            "trigger": "settlement",
        },
    }


def confirmed_markets():
    field = _make_cfp_qualifiers_market()
    for index, outcome in enumerate(field["outcomes"]):
        outcome["is_winner"] = index < 12
        outcome["resolution_source"] = "api_settlement"
        outcome["probability"] = None
    return {227: field, 181: _make_cfp_title_market()}


def test_a_confirmed_field_precedes_title_chances_without_printing_result_probabilities():
    markets = confirmed_markets()
    before = deepcopy(markets)
    members = select_field_selection(markets, definition=definition())
    assert not isinstance(members, roundups.RoundupRefusal)
    assert [section["class"] for section in members.sections] == ["selection", "title"]
    results = members.members[0]["card"]
    assert results["status"] == "resolved"
    assert results["mutually_exclusive"] is False
    assert len(results["top_outcomes"]) == results["outcome_count"] == 12
    assert all(
        row["probability"] is None
        and row["is_winner"] is True
        and row["resolution_source"] == "api_settlement"
        for row in results["top_outcomes"]
    )
    assert members.members[1]["card"]["status"] == "open"
    assert markets == before


@pytest.mark.parametrize(
    "change,reason",
    [
        (
            lambda m: m[227]["outcomes"][0].update(resolution_source="clock_expired"),
            "venue_result_pending",
        ),
        (
            lambda m: m[227]["outcomes"][13].update(
                is_winner=False, resolution_source=None
            ),
            "venue_result_pending",
        ),
        (
            lambda m: m[227]["outcomes"][0].update(is_winner=False),
            "winner_count_11_expected_12",
        ),
        (
            lambda m: m[227]["outcomes"][12].update(is_winner=True),
            "winner_count_13_expected_12",
        ),
        (
            lambda m: m[227]["outcomes"][0].update(name="Other"),
            "invalid_outcome_identity",
        ),
        (
            lambda m: m[227]["outcomes"][1].update(id=m[227]["outcomes"][0]["id"]),
            "invalid_outcome_identity",
        ),
        (
            lambda m: m[227].update(source="polymarket"),
            "market_missing_or_wrong_source",
        ),
        (lambda m: m[227].update(mutually_exclusive=True), "incompatible_fields"),
    ],
)
def test_a_calendar_or_price_cannot_substitute_for_the_venue_result(change, reason):
    markets = confirmed_markets()
    change(markets)
    result = select_field_selection(markets, definition=definition())
    assert isinstance(result, roundups.RoundupRefusal)
    assert reason in str(result.reasons)


def test_the_set_is_reproducible_in_market_and_outcome_order():
    original = confirmed_markets()
    shuffled = deepcopy(original)
    shuffled[227]["outcomes"].reverse()
    assert select_field_selection(
        original, definition=definition()
    ) == select_field_selection(
        dict(reversed(list(shuffled.items()))), definition=definition()
    )


def test_a_settled_championship_keeps_its_winner_and_withdraws_the_prices():
    markets = confirmed_markets()
    title = markets[181]
    title["status"] = "resolved"
    for index, outcome in enumerate(title["outcomes"]):
        outcome.update(
            is_winner=index == 0, resolution_source="api_settlement", probability=None
        )
    members = select_field_selection(markets, definition=definition())
    champion = members.members[1]["card"]
    assert champion["status"] == "resolved"
    assert champion["top_outcomes"][0]["name"] == "Ohio State"
    assert champion["top_outcomes"][0]["probability"] is None
    assert members.sections[1]["title"] == "Champion"
    assert members.footer == "Venue-confirmed playoff field · Champion confirmed"


async def test_calendar_and_pending_licence_cover_both_renderings_before_cache(
    monkeypatch,
):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    roundups.reset_roundup_cache_for_tests()
    stored = definition()
    loader = AsyncMock(return_value=(confirmed_markets(), {}))
    pending = build_field_selection_producer(stored, load_markets=loader)
    boundary = datetime.fromisoformat(stored["rule"]["valid_from"]).timestamp()
    assert await roundups.evaluate_roundup_producer(
        pending, object(), now=boundary + 1
    ) == (None, None)
    loader.assert_not_awaited()
    stored["enabled"] = (
        True  # local admission fixture, pending definitions stay disabled
    )
    producer = build_field_selection_producer(stored, load_markets=loader)
    assert await roundups.evaluate_roundup_producer(
        producer, object(), now=boundary - 1
    ) == (None, None)
    loader.assert_not_awaited()
    card, page = await roundups.evaluate_roundup_producer(
        producer, object(), now=boundary
    )
    assert card["data"]["member_ids"] == [227, 181]
    assert (
        page["member_count"] == card["data"]["collection_ref"]["collection_count"] == 2
    )
    assert (
        page["relations"] == card["data"]["relations"] == ["same_event", "same_window"]
    )
    assert card["data"]["collection_ref"]["revision"] == page["revision"]
    loader.assert_awaited_once()
    roundups.reset_roundup_cache_for_tests()


async def test_normal_loader_uses_provider_occasion_ids(monkeypatch):
    from app.utils import field_band

    loader = AsyncMock(return_value=(confirmed_markets(), {}))
    monkeypatch.setattr(field_band, "_load_markets_from_db", loader)
    producer = build_field_selection_producer(definition())
    db = object()
    result = await producer.produce(db)
    assert not isinstance(result, roundups.RoundupRefusal)
    loader.assert_awaited_once_with(
        db, [], ["KXNCAAFPLAYOFF-26", "KXNCAAF-27"], sources=["kalshi", "kalshi"]
    )
