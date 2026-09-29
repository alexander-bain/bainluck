"""The final score and an open venue contract are separate facts (#9484)."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routes.events import (
    _fold_duplicate_match_winner_markets,
    _market_is_event_match_winner,
    _match_winner_side,
    resolve_binary_matchup_outcome_name,
)
from app.utils.final_game_winner_quote import final_game_winner_quotes
from app.utils.outcome_display import normalize_display_probs

NOW = datetime(2026, 9, 29, 4, 0, tzinfo=timezone.utc)


def market(id=11, **changes):
    return SimpleNamespace(**{
        "id": id, "event_id": 42, "name": "Bears vs Eagles", "source": "kalshi",
        "status": "open", "settled_at": None, "mutually_exclusive": True, **changes,
    })


def outcome(id, market_id, name, probability, **changes):
    return SimpleNamespace(**{
        "id": id, "market_id": market_id, "name": name,
        "current_probability": probability, "current_yes_bid": None,
        "current_yes_ask": None, "is_winner": False, "resolution_source": None,
        "last_updated": NOW, **changes,
    })


def legs(market_id=11, first=1):
    return [outcome(first, market_id, "Bears", Decimal("0.99")),
            outcome(first + 1, market_id, "Eagles", Decimal("0.01"))]


def build(markets=None, outcomes=None, **changes):
    return final_game_winner_quotes(**{
        "event_id": 42, "event_is_finished": True, "mapped_event_ids": [42],
        "home_name": "Bears", "away_name": "Eagles",
        "markets": [market()] if markets is None else markets,
        "outcomes": legs() if outcomes is None else outcomes,
        "observed_at": {1: NOW - timedelta(minutes=9), 2: NOW - timedelta(minutes=2)},
        "is_match_winner": _market_is_event_match_winner,
        "winner_side": _match_winner_side,
        "fold_winner_markets": _fold_duplicate_match_winner_markets,
        "resolve_outcome_name": resolve_binary_matchup_outcome_name,
        "normalize_probs": normalize_display_probs, **changes,
    })


def test_final_game_keeps_separate_open_quote_and_does_not_mutate_inputs():
    markets, outcomes = [market()], legs()
    before = deepcopy((markets, outcomes))
    body = build(markets, outcomes)
    assert (markets, outcomes) == before
    quote = body["open_winner_quote"]
    assert quote["event_id"] == 42
    assert quote["status"] == "open"
    assert [(r["side"], r["name"], r["probability"]) for r in quote["outcomes"]] == [
        ("home", "Bears", 0.99), ("away", "Eagles", 0.01),
    ]
    assert not {"home_score", "away_score", "winner", "win_probability"} & body.keys()
    assert body["closed_winner_market_ids"] == []


@pytest.mark.parametrize("finished", [False, None])
def test_unfinished_event_has_no_final_quote(finished):
    assert build(event_is_finished=finished)["open_winner_quote"] is None


@pytest.mark.parametrize("mapped_id", [None, 99])
def test_unlinked_name_time_fallback_or_foreign_event_cannot_supply_quote(mapped_id):
    assert build(markets=[market(event_id=mapped_id)])["open_winner_quote"] is None


def test_only_proven_fold_ids_can_supply_an_alias_quote():
    assert build(markets=[market(event_id=43)], mapped_event_ids=[42, 43])["open_winner_quote"]
    assert build(mapped_event_ids=[43])["open_winner_quote"] is None


@pytest.mark.parametrize("status", ["resolved", "closed", "settled", "final"])
def test_explicit_terminal_status_fences_the_contract(status):
    assert build(markets=[market(status=status)]) == {
        "open_winner_quote": None, "closed_winner_market_ids": [11],
    }


@pytest.mark.parametrize("status", [None, "suspended", "unknown"])
def test_unknown_or_suspended_is_not_open_or_terminal(status):
    assert build(markets=[market(status=status)]) == {
        "open_winner_quote": None, "closed_winner_market_ids": [],
    }


def test_settled_stamp_fences_even_when_status_is_erroneously_open():
    assert build(markets=[market(settled_at=NOW)])["closed_winner_market_ids"] == [11]


def test_kalshi_open_status_with_any_graded_winner_never_reopens():
    rows = legs()
    rows[0].is_winner = True
    assert build(outcomes=rows)["closed_winner_market_ids"] == [11]


@pytest.mark.parametrize("source", ["api_settlement", "all_losers", "game_score", "unknown_grade"])
def test_all_lost_or_voided_grade_is_terminal_even_without_a_winner(source):
    rows = legs()
    rows[1].resolution_source = source
    assert build(outcomes=rows) == {"open_winner_quote": None, "closed_winner_market_ids": [11]}


def test_retracted_grade_is_not_an_authoritative_settlement():
    rows = legs()
    rows[0].resolution_source = "ungradeable_result"
    assert build(outcomes=rows)["open_winner_quote"]


@pytest.mark.parametrize("name", [
    "Bears vs Eagles - Halftime Result", "Bears vs Eagles: First Team to Score",
    "Set 1 Winner: Bears vs Eagles", "Bears finishes higher than Eagles",
])
def test_narrower_or_season_contracts_are_not_full_game_winners(name):
    assert build(markets=[market(name=name)])["open_winner_quote"] is None


def test_mixed_parent_unknown_side_and_duplicate_side_do_not_manufacture_complete_book():
    for extra in [outcome(3, 11, "O/U 52.5", 0.5), outcome(3, 11, "Bears", 0.9)]:
        assert build(outcomes=legs() + [extra])["open_winner_quote"] is None


def test_named_draw_is_preserved_but_missing_opponent_is_not_invented():
    draw = outcome(3, 11, "Draw (Bears vs Eagles)", 0.01)
    quote = build(outcomes=legs() + [draw])["open_winner_quote"]
    assert [r["side"] for r in quote["outcomes"]] == ["home", "away", "draw"]
    assert build(outcomes=[legs()[0], draw])["open_winner_quote"] is None


def test_binary_pair_uses_existing_named_side_resolution():
    rows = [outcome(1, 11, "Yes", 0.6), outcome(2, 11, "No", 0.4)]
    quote = build(outcomes=rows)["open_winner_quote"]
    assert [row["name"] for row in quote["outcomes"]] == ["Bears", "Eagles"]


@pytest.mark.parametrize("probability", [None, float("nan"), float("inf"), -0.1, 1.1, True])
def test_a_missing_or_invalid_leg_withdraws_whole_quote_without_terminal_fence(probability):
    rows = legs()
    rows[0].current_probability = probability
    assert build(outcomes=rows) == {"open_winner_quote": None, "closed_winner_market_ids": []}


def test_real_zero_and_one_remain_quotes_without_becoming_settlement():
    rows = legs()
    rows[0].current_probability, rows[1].current_probability = 1, 0
    assert [r["probability"] for r in build(outcomes=rows)["open_winner_quote"]["outcomes"]] == [1, 0]


@pytest.mark.parametrize("price,bid,ask", [(0.5, 0, 1), (0.99, 0.39, 0.41)])
def test_existing_empty_book_and_contradictory_book_guards_survive(price, bid, ask):
    rows = legs()
    rows[0].current_probability, rows[0].current_yes_bid, rows[0].current_yes_ask = price, bid, ask
    assert build(outcomes=rows)["open_winner_quote"] is None


def test_oldest_real_observation_dates_quote_and_missing_observation_stays_unknown():
    assert build()["open_winner_quote"]["observed_at"] == (NOW - timedelta(minutes=9)).isoformat()
    quote = build(observed_at={1: NOW - timedelta(hours=20)})["open_winner_quote"]
    assert quote["observed_at"] is None
    assert quote["outcomes"][1]["observed_at"] is None
    assert NOW.isoformat() not in str(quote)  # raw last_updated cannot become freshness


def test_whole_market_fold_uses_freshness_without_blending_two_books():
    markets = [market(), market(12, source="polymarket")]
    rows = legs() + legs(12, 3)
    rows[2].current_probability, rows[3].current_probability = 0.8, 0.2
    quote = build(markets, rows, observed_at={
        1: NOW - timedelta(hours=1), 2: NOW, 3: NOW, 4: NOW,
    })["open_winner_quote"]
    assert quote["market_id"] == 12
    assert [r["probability"] for r in quote["outcomes"]] == [0.8, 0.2]
    assert [r["outcome_id"] for r in quote["outcomes"]] == [3, 4]


def test_missing_market_is_not_a_closed_contract_and_closed_foreign_market_is_ignored():
    assert build(markets=[])["closed_winner_market_ids"] == []
    assert build(markets=[market(event_id=99, status="closed")])["closed_winner_market_ids"] == []


def test_observations_and_terminal_detection_use_all_legs_before_price_filtering():
    rows = legs()
    rows[0].current_probability = None
    rows[0].resolution_source = "api_settlement"
    assert build(outcomes=rows)["closed_winner_market_ids"] == [11]


def test_existing_complete_field_normalizer_and_real_contributor_age_are_reused():
    rows = legs()
    rows[0].current_probability, rows[1].current_probability = 0.65, 0.55
    quote = build(outcomes=rows)["open_winner_quote"]
    expected = [{"probability": 0.65}, {"probability": 0.55}]
    normalize_display_probs(expected, mutually_exclusive=True, field_complete=True)
    assert [r["probability"] for r in quote["outcomes"]] == [r["probability"] for r in expected]
    assert all(r["observed_at"] == quote["observed_at"] for r in quote["outcomes"])
    unknown = build(outcomes=rows, observed_at={1: NOW})["open_winner_quote"]
    assert unknown["observed_at"] is None
    assert all(r["observed_at"] is None for r in unknown["outcomes"])


@pytest.mark.parametrize("exclusive", [False, None])
def test_unknown_or_nonexclusive_market_metadata_cannot_manufacture_a_distribution(exclusive):
    rows = legs()
    rows[0].current_probability, rows[1].current_probability = 0.65, 0.55
    quote = build(markets=[market(mutually_exclusive=exclusive)], outcomes=rows)["open_winner_quote"]
    assert [r["probability"] for r in quote["outcomes"]] == [0.65, 0.55]


@pytest.mark.parametrize("probs", [(0.99, 0.02), (0.95, 0.90), (0.01, 0.99)])
def test_existing_normalizer_refusal_bands_and_floor_are_not_redefined(probs):
    rows = legs()
    rows[0].current_probability, rows[1].current_probability = probs
    quote = build(outcomes=rows)["open_winner_quote"]
    assert [r["probability"] for r in quote["outcomes"]] == list(probs)


def test_selected_whole_market_owns_the_normalization_metadata():
    markets = [market(), market(12, source="polymarket", mutually_exclusive=False)]
    rows = legs() + legs(12, 3)
    rows[2].current_probability, rows[3].current_probability = 0.65, 0.55
    quote = build(markets, rows, observed_at={1: NOW - timedelta(hours=1), 2: NOW,
                                            3: NOW, 4: NOW})["open_winner_quote"]
    assert quote["market_id"] == 12
    assert [r["probability"] for r in quote["outcomes"]] == [0.65, 0.55]


def test_all_zero_book_has_no_quote_and_no_terminal_claim():
    rows = legs()
    rows[0].current_probability, rows[1].current_probability = 0, 0
    assert build(outcomes=rows) == {"open_winner_quote": None, "closed_winner_market_ids": []}


def test_existing_venue_field_completeness_guard_also_protects_separate_quote():
    book = market(market_metadata={"event_title": "Bears vs Eagles", "market_count": 3})
    assert build(markets=[book])["open_winner_quote"] is None
    book.market_metadata["event_title"] = "A parent with forty sibling markets"
    assert build(markets=[book])["open_winner_quote"] is not None


def test_helper_has_no_route_import_or_event_write_boundary():
    import ast
    from pathlib import Path
    from app.utils import final_game_winner_quote
    tree = ast.parse(Path(final_game_winner_quote.__file__).read_text())
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name.startswith("app.routes") for name in imports)
    assert "event" not in final_game_winner_quotes.__annotations__
