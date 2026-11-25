"""A Discover field needs enough coverage to name a leader."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.routes import feed
from app.utils.futures_field_coverage import (
    field_leader_is_unsupported,
    field_winner_places,
    grouped_field_leader_is_unsupported,
)
from app.utils.personalization import PersonalizationContext
from tests.test_card_and_page_share_the_withheld_set_7632 import (
    _SportsBoard,
    _SportsLeg,
    _sports_db,
)


CUP = "NBA: Team to reach 2026 NBA Cup Championship Game"
ABU_DHABI = "Abu Dhabi Grand Prix: Driver Winner"


def test_places_come_from_the_contract():
    assert field_winner_places(CUP, False) == 2
    assert field_winner_places(ABU_DHABI, True) == 1
    assert field_winner_places("Top 5 Most Searched Movies", False) == 5
    assert field_winner_places("Top Five Most Searched Athletes", False) == 5
    assert field_winner_places("Team to Qualify for the Big Ten Championship Game", False) == 2
    assert field_winner_places("Team to advance to the 2027 World Series", False) == 2
    assert field_winner_places("Team to reach the Final Four", False) is None
    assert field_winner_places("Team to reach a semifinal", False) is None
    assert field_winner_places("Finish in the top 3", False, 3) == 3


def test_group_coverage_uses_the_full_field_after_price_composition():
    detail = {
        "status": "open",
        "market_type": "field",
        "name": "Award winner",
        "source": "kalshi",
        "mutually_exclusive": True,
        "prices_withheld": 1,
        "outcomes": [
            {"name": name, "probability": price}
            for name, price in zip(("Alice", "Beatrice", "Carmen", "Diana"), (0.20, 0.19, 0.17, 0.15))
        ],
    }
    assert not grouped_field_leader_is_unsupported(detail, expected_winners=None, group_type=None)
    detail["outcomes"][-1]["probability"] = None
    assert grouped_field_leader_is_unsupported(detail, expected_winners=None, group_type=None)


@pytest.mark.parametrize(
    ("probabilities", "places", "missing", "unsupported"),
    [
        ([0.0525, 0.025, 0.025, 0.01, 0.0065, 0.0065, 0.006], 2, True, True),
        ([0.05, 0.05] + [0.005] * 16, 1, True, True),
        ([0.26, 0.26, 0.1, None], 1, False, True),
        ([0.51, 0.1, None], 1, False, False),
        ([0.6, 0.39], 2, False, True),
        ([0.6, 0.4], 2, False, False),
        ([0.18, 0.16, 0.14] + [0.065] * 8, 1, False, False),
        ([Decimal("0.49"), None], 1, False, True),
        ([0.2, None, None], None, False, True),
        ([0.2, None], None, False, False),
        ([0.2, 0.1], None, False, False),
        ([None], 0, True, False),
    ],
)
def test_coverage_uses_full_unscaled_field_and_possible_missing_leader(
    probabilities, places, missing, unsupported
):
    assert (
        field_leader_is_unsupported(
            probabilities,
            places,
            open_outcome_count=len(probabilities),
            omitted_contender=missing,
        )
        is unsupported
    )


def _board(market_id, name, category, exclusive, quoted, unpriced=()):
    rows = [_SportsLeg(index, name, price) for index, (name, price) in enumerate(quoted, 1)]
    rows += [
        _SportsLeg(index, name, None)
        for index, name in enumerate(unpriced, len(rows) + 1)
    ]
    board = _SportsBoard(market_id, name, rows)
    board.source = "polymarket"
    board.external_id = str(market_id)
    board.llm_sport_category = category
    board.canonical_market_key = None
    board.market_type = "field"
    board.mutually_exclusive = exclusive
    return board


@pytest.mark.parametrize(("open_outcome_count", "unsupported"), [(7, True), (6, False)])
def test_unknown_winner_count_uses_all_open_rows(open_outcome_count, unsupported):
    board = _board(
        70239540,
        "Who will appear in a Big Game commercial?",
        "entertainment",
        False,
        [("Alice", 0.9), ("Beatrice", 0.86), ("Carmen", 0.57)],
        [f"Unpriced {i}" for i in range(open_outcome_count - 3)],
    )
    item = {
        "data": {
            "status": "open",
            "market_type": "field",
            "discover_card": {"suggested_format": "outcome_distribution"},
        },
    }
    feed._withhold_unsupported_field_leader(
        item, board, board.outcomes[:3], field_incomplete=True
    )
    assert item["data"]["field_price_coverage_incomplete"] is unsupported


@pytest.mark.parametrize("path", ["discover", "sports", "price_refresh"])
async def test_fresh_feed_drops_the_field_and_refresh_retires_its_leader(monkeypatch, path):
    cup = _board(
        65677910, CUP, "basketball", False,
        [
            ("Brooklyn Nets", 0.0525), ("Memphis Grizzlies", 0.025),
            ("Washington Wizards", 0.025), ("Indiana Pacers", 0.01),
            ("Phoenix Suns", 0.0065), ("Chicago Bulls", 0.0065),
            ("Los Angeles Clippers", 0.006),
        ],
        ("Boston Celtics", "Oklahoma City Thunder", "Detroit Pistons", "Denver Nuggets"),
    )
    abu_dhabi = _board(
        69512106, ABU_DHABI, "motorsports", True,
        [
            ("Oscar Piastri", 0.05), ("Isack Hadjar", 0.05), ("Pierre Gasly", 0.005),
            ("Nico Hulkenberg", 0.005), ("Albon", 0.005),
        ],
        ("Max Verstappen", "Lando Norris", "George Russell"),
    )
    qatar = _board(
        68445052, "Qatar Grand Prix: Driver Winner", "motorsports", True,
        [
            ("Max Verstappen", 0.36), ("Kimi Antonelli", 0.21),
            ("Lando Norris", 0.14), ("Oscar Piastri", 0.12),
            ("George Russell", 0.1), ("Charles Leclerc", 0.07),
        ],
    )
    markets = [cup, abu_dhabi, qatar]
    withheld = {
        board.id: {row.id for row in board.outcomes if row.current_probability is None}
        for board in markets
    }
    for board in markets:
        board.withheld_outcome_ids = list(withheld[board.id])
    monkeypatch.setattr(feed, "_get_canonical_source_counts", AsyncMock(return_value={}))
    monkeypatch.setattr(feed, "_team_names_by_id", AsyncMock(return_value={}))
    monkeypatch.setattr(feed, "out_legs_by_market", AsyncMock(return_value={}))
    monkeypatch.setattr(feed, "graded_out_leg_ids_by_market", AsyncMock(return_value={}))
    monkeypatch.setattr(
        feed, "withheld_price_outcome_ids_for_markets", AsyncMock(return_value=withheld)
    )
    args = (_sports_db(markets), datetime.now(timezone.utc), None, PersonalizationContext())
    if path == "sports":
        items = await feed._score_sports_mode_futures(*args)
    else:
        items = await feed._score_futures(
            *args, preloaded_base={"markets": markets, "curator_ids": set()},
            price_refresh=path == "price_refresh",
        )
    by_id = {item["data"]["id"]: item for item in items}
    if path == "price_refresh":
        for board in (cup, abu_dhabi):
            item = by_id[board.id]
            data = item["data"]
            assert data["name"] == board.name
            assert data["outcome_count"] == len(board.outcomes)
            assert data["field_price_coverage_incomplete"] is True
            assert data["top_outcomes"] == []
            assert "discover_card" not in data
            assert data["hook_description"] is None
            assert item["headline"] is None
            assert item["context_summary"] == "Limited price coverage"
        assert feed._suppress_zero_probability_cards(items) == ([by_id[qatar.id]], 2)
    else:
        assert list(by_id) == [qatar.id]
    qatar_data = by_id[qatar.id]["data"]
    assert qatar_data["field_price_coverage_incomplete"] is False
    assert qatar_data["top_outcomes"][0]["name"] == "Max Verstappen"
    assert qatar_data["top_outcomes"][0]["probability"] == pytest.approx(0.36)
