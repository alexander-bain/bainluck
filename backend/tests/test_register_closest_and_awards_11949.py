"""Tests for #11949 Orders 5 & 6: ``register_closest`` and ``awards_category_roundup``."""

from __future__ import annotations

import pytest

from app.utils.awards_category_roundup import (
    GOLDEN_GLOBES_BEST_PICTURE_SLUG,
    golden_globes_best_picture,
)
from app.utils.register_closest import (
    CLOSEST_RACES_SLUG,
    closest_races,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupRefusal,
)


def test_orders_5_and_6_registered_in_roundup_producers():
    assert CLOSEST_RACES_SLUG in ROUNDUP_PRODUCERS
    assert GOLDEN_GLOBES_BEST_PICTURE_SLUG in ROUNDUP_PRODUCERS


@pytest.mark.asyncio
async def test_register_closest_refuses_when_fewer_than_three_open_races():
    # Today only Alaska Senate (109095) is open while Kansas (109085) and others are settled.
    markets = [
        {
            "id": 109085,
            "name": "Kansas Senate winner?",
            "status": "resolved",
            "source": "kalshi",
            "settled_winner": "Roger Marshall",
            "outcomes": [
                {"id": 1090851, "name": "Roger Marshall", "probability": None, "is_winner": True, "resolution_source": "venue_settlement"},
                {"id": 1090852, "name": "Adam Hamilton", "probability": None, "is_winner": False, "resolution_source": "venue_settlement"},
            ],
        },
        {
            "id": 109095,
            "name": "Alaska Senate winner?",
            "status": "open",
            "source": "kalshi",
            "outcomes": [
                {"id": 1090951, "name": "Democratic party", "probability": 0.95},
                {"id": 1090952, "name": "Republican party", "probability": 0.05},
            ],
        },
    ]
    res = await closest_races(markets)
    assert isinstance(res, RoundupRefusal)
    assert ("register_closest", "too_few_open_races") in res.reasons


@pytest.mark.asyncio
async def test_register_closest_refuses_when_settled_in_register_still_priced_on_twin():
    markets = [
        {
            "id": 109085,
            "name": "Kansas Senate winner?",
            "status": "resolved",
            "source": "kalshi",
            "settled_winner": "Roger Marshall",
            "outcomes": [
                {"id": 1090851, "name": "Roger Marshall", "probability": None, "is_winner": True, "resolution_source": "venue_settlement"},
                {"id": 1090852, "name": "Adam Hamilton", "probability": None, "is_winner": False, "resolution_source": "venue_settlement"},
            ],
        },
        {
            # Registered Polymarket twin for 109085 is 113093 — still open and priced!
            "id": 113093,
            "name": "Kansas Senate Election Winner",
            "status": "open",
            "source": "polymarket",
            "outcomes": [
                {"id": 1130931, "name": "Roger Marshall", "probability": 0.92},
                {"id": 1130932, "name": "Adam Hamilton", "probability": 0.08},
            ],
        },
    ]
    res = await closest_races(markets)
    assert isinstance(res, RoundupRefusal)
    assert ("register_closest", "settled_in_register_still_priced:109085") in res.reasons


@pytest.mark.asyncio
async def test_register_closest_emits_three_closest_open_races_with_blend():
    markets = [
        # Maine Senate (109082 + twin 113095) -> blended leader Susan Collins 54%
        {
            "id": 109082,
            "name": "Maine Senate winner?",
            "status": "open",
            "source": "kalshi",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 1090821, "name": "Susan Collins", "probability": 0.52},
                {"id": 1090822, "name": "Troy Jackson", "probability": 0.48},
            ],
        },
        {
            "id": 113095,
            "name": "Maine Senate Election Winner",
            "status": "open",
            "source": "polymarket",
            "prices_updated_at": "2026-11-05T17:10:00Z",
            "outcomes": [
                {"id": 1130951, "name": "Susan Collins", "probability": 0.56},
                {"id": 1130952, "name": "Troy Jackson", "probability": 0.44},
            ],
        },
        # Ohio Senate (109072) -> leader Jon Husted 58%
        {
            "id": 109072,
            "name": "Ohio Senate winner?",
            "status": "open",
            "source": "kalshi",
            "prices_updated_at": "2026-11-05T17:05:00Z",
            "outcomes": [
                {"id": 1090721, "name": "Jon Husted", "probability": 0.58},
                {"id": 1090722, "name": "Sherrod Brown", "probability": 0.42},
            ],
        },
        # Michigan Senate (109081) -> leader Mike Rogers 61%
        {
            "id": 109081,
            "name": "Michigan Senate winner?",
            "status": "open",
            "source": "kalshi",
            "prices_updated_at": "2026-11-05T17:05:00Z",
            "outcomes": [
                {"id": 1090811, "name": "Mike Rogers", "probability": 0.61},
                {"id": 1090812, "name": "Abdul El-Sayed", "probability": 0.39},
            ],
        },
        # Alaska Senate (109095) -> leader Democratic party 95% (excluded as 4th closest)
        {
            "id": 109095,
            "name": "Alaska Senate winner?",
            "status": "open",
            "source": "kalshi",
            "prices_updated_at": "2026-11-05T17:05:00Z",
            "outcomes": [
                {"id": 1090951, "name": "Democratic party", "probability": 0.95},
                {"id": 1090952, "name": "Republican party", "probability": 0.05},
            ],
        },
    ]
    res = await closest_races(markets)
    assert isinstance(res, RoundupMembers)
    # Closest 3 are Maine (54%), Ohio (58%), Michigan (61%), ordered highest-first on the card
    assert [r["label"] for r in res.rows] == [
        "Michigan Senate · Mike Rogers",
        "Ohio Senate · Jon Husted",
        "Maine Senate · Susan Collins",
    ]
    assert [r["rendered_percent"] for r in res.rows] == [61, 58, 54]
    assert res.rows[2]["pair"] == {"kalshi_market_id": 109082, "polymarket_market_id": 113095}


@pytest.mark.asyncio
async def test_awards_category_roundup_pairs_nomination_and_win_and_withholds_when_nominations_absent():
    winner_field = {
        "id": 900,
        "name": "Golden Globes: Best Motion Picture - Drama Winner",
        "status": "open",
        "source": "kalshi",
        "category": "entertainment",
        "mutually_exclusive": True,
        "prices_updated_at": "2026-11-05T17:00:00Z",
        "outcomes": [
            {"id": 9001, "name": "One Battle After Another", "probability": 0.42},
            {"id": 9002, "name": "Sinners", "probability": 0.31},
            {"id": 9003, "name": "Hamnet", "probability": 0.27},
        ],
    }
    # Without nomination binaries -> withholds cleanly
    refused = await golden_globes_best_picture([winner_field])
    assert isinstance(refused, RoundupRefusal)
    assert ("awards_category", "too_few_paired_nominees") in refused.reasons

    # With 3 nomination binaries -> emits two-bar rows ordered by win probability
    nomination_binaries = [
        {
            "id": 901,
            "name": "Will One Battle After Another be nominated for Best Motion Picture - Drama?",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 9011, "name": "Yes", "probability": 0.88},
                {"id": 9012, "name": "No", "probability": 0.12},
            ],
        },
        {
            "id": 902,
            "name": "Will Sinners be nominated for Best Motion Picture - Drama?",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 9021, "name": "Yes", "probability": 0.79},
                {"id": 9022, "name": "No", "probability": 0.21},
            ],
        },
        {
            "id": 903,
            "name": "Will Hamnet be nominated for Best Motion Picture - Drama?",
            "status": "open",
            "source": "kalshi",
            "category": "entertainment",
            "prices_updated_at": "2026-11-05T17:00:00Z",
            "outcomes": [
                {"id": 9031, "name": "Yes", "probability": 0.74},
                {"id": 9032, "name": "No", "probability": 0.26},
            ],
        },
    ]
    emitted = await golden_globes_best_picture([winner_field, *nomination_binaries])
    assert isinstance(emitted, RoundupMembers)
    assert [r["label"] for r in emitted.rows] == [
        "One Battle After Another",
        "Sinners",
        "Hamnet",
    ]
    assert [r["rendered_percent"] for r in emitted.rows] == [42, 31, 27]
    assert [r["secondary_rendered_percent"] for r in emitted.rows] == [88, 79, 74]
    assert emitted.rows[0]["primary_bar_label"] == "Wins"
    assert emitted.rows[0]["secondary_bar_label"] == "Nominated"
