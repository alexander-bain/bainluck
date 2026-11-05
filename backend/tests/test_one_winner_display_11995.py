"""The served full field owns normalization and whole-percent allocation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.routes.feed import _apply_card_percents, _normalize_feed_probabilities
from app.utils.outcome_display import normalize_display_probs


@pytest.mark.parametrize(
    "prices",
    [[0.50, 0.50], [0.52, 0.51], [0.45, 0.4, 0.35], [0.985, 0.015]],
)
def test_every_complete_one_winner_field_sums_to_one_and_prints_100(prices):
    rows = [
        {"id": i, "name": f"Candidate {i}", "probability": p}
        for i, p in enumerate(prices)
    ]
    normalize_display_probs(rows)
    assert [o["probability"] for o in rows] == pytest.approx(
        [p / sum(prices) for p in prices]
    )
    assert sum(o["probability"] for o in rows) == pytest.approx(1)
    assert sum(o["rendered_percent"] for o in rows) == 100


def test_preview_keeps_full_divisor_and_allocation_including_overflow():
    full = [
        SimpleNamespace(id=i, name=f"Candidate {i}", current_probability=p)
        for i, p in enumerate([0.36, 0.34, 0.2, 0.1, 0.05])
    ]
    page = [
        {"id": o.id, "name": o.name, "probability": o.current_probability} for o in full
    ]
    normalize_display_probs(page)
    preview = [
        {"id": o.id, "name": o.name, "probability": o.current_probability}
        for o in full[:3]
    ]
    _normalize_feed_probabilities(preview, full, mutually_exclusive=True)
    _apply_card_percents(preview)
    assert preview == page[:3]
    assert sum(o["rendered_percent"] for o in preview) < 100
    assert sum(o["rendered_percent"] for o in page) == 100


@pytest.mark.parametrize(
    "kwargs", [{"mutually_exclusive": False}, {"field_complete": False}]
)
def test_nonexclusive_or_withheld_field_stays_raw(kwargs):
    rows = [{"name": n, "probability": p} for n, p in [("Alice", 0.8), ("Bob", 0.7)]]
    before = deepcopy(rows)
    assert normalize_display_probs(rows, **kwargs) is False
    assert rows == before


@pytest.mark.parametrize("prices", [[None, 0.7], [float("nan"), 0.7], [0.0, 0.0]])
def test_unknown_or_empty_mass_never_becomes_a_distribution(prices):
    rows = [{"name": f"Candidate {i}", "probability": p} for i, p in enumerate(prices)]
    assert normalize_display_probs(rows) is False
    assert all("rendered_percent" not in row for row in rows)


def test_cumulative_ladder_is_raw_even_with_a_bad_exclusivity_flag():
    rows = [
        {"name": n, "probability": p} for n, p in [("Above 50", 0.8), ("Above 60", 0.6)]
    ]
    before = deepcopy(rows)
    assert normalize_display_probs(rows, mutually_exclusive=True) is False
    assert rows == before


def test_whole_allocation_does_not_depend_on_card_order():
    rows = [{"id": i, "name": f"Candidate {i}", "probability": 0.4} for i in range(3)]
    backwards = list(reversed(deepcopy(rows)))
    normalize_display_probs(rows)
    normalize_display_probs(backwards)
    assert {o["id"]: o["rendered_percent"] for o in rows} == {
        o["id"]: o["rendered_percent"] for o in backwards
    }
    assert sum(o["rendered_percent"] for o in rows) == 100


def test_search_preview_keeps_the_detail_full_field_divisor():
    from app.routes.events import _build_search_top_outcomes
    from app.routes.futures import _format_market_detail
    from tests.test_midterms_complete_outcome_prices_11948 import _detail_field

    market = _detail_field()
    page = _format_market_detail(market)
    preview = _build_search_top_outcomes(market, limit=5)
    full = {o["name"]: o for o in page["outcomes"]}
    assert len(preview) == 5
    for row in preview:
        assert row["probability"] == full[row["name"]]["probability"]
        assert row.get("rendered_percent") == full[row["name"]].get("rendered_percent")


@pytest.mark.parametrize(
    "result",
    [
        {"is_winner": True, "resolution_source": "api_settlement"},
        {"is_winner": True, "resolution_source": "datagolf_settlement"},
    ],
)
def test_a_declared_winner_is_not_scaled_back_into_an_uncertain_price(result):
    rows = [
        {"name": "Winner", "probability": 1.0, **result},
        {"name": "Loser", "probability": 0.003},
    ]
    before = deepcopy(rows)
    assert normalize_display_probs(rows) is False
    assert rows == before


def test_a_refused_history_tick_does_not_turn_unknown_mass_into_zero():
    from datetime import datetime, timedelta, timezone
    from app.utils.futures_history_basis import devigged_consensus_by_time

    start = datetime(2026, 11, 4, tzinfo=timezone.utc)
    full = {1: 0.45, 2: 0.4, 3: 0.35}
    partial = {2: 0.4, 3: 0.35}
    result = devigged_consensus_by_time(
        {
            start: {"polymarket": full},
            start + timedelta(minutes=1): {"polymarket": partial},
        },
        mutually_exclusive=True,
        incomplete_times={start + timedelta(minutes=1)},
    )
    assert sum(result[start].values()) == pytest.approx(1)
    assert result[start + timedelta(minutes=1)] == partial


@pytest.mark.parametrize("prices", [[0.4, 0.39], [0.9, 0.8, 0.7]])
def test_suspect_or_missing_mass_is_never_made_into_a_complete_field(prices):
    rows = [{"name": f"Candidate {i}", "probability": p} for i, p in enumerate(prices)]
    before = deepcopy(rows)
    assert normalize_display_probs(rows) is False
    assert rows == before


def test_floor_upper_bounds_never_receive_a_complete_field_allocation():
    rows = [{"name": f"Candidate {i}", "probability": p}
            for i, p in enumerate([0.985, 0.015] + [0.01] * 51)]
    before = deepcopy(rows)
    assert normalize_display_probs(rows) is False
    assert rows == before


def test_event_row_alias_preserves_ladder_semantics_and_rounding_identity():
    ladder = [
        {"outcome_name": "Above 50", "probability": 0.8},
        {"outcome_name": "Above 60", "probability": 0.6},
    ]
    before = deepcopy(ladder)
    assert normalize_display_probs(ladder) is False
    assert ladder == before
    rows = [{"outcome_name": name, "probability": 0.4} for name in ("Zoe", "Alice", "Bob")]
    page = [{"name": row["outcome_name"], "probability": row["probability"]} for row in reversed(rows)]
    normalize_display_probs(rows)
    normalize_display_probs(page)
    assert {r["outcome_name"]: r["rendered_percent"] for r in rows} == {
        r["name"]: r["rendered_percent"] for r in page
    }


def test_distribution_rows_copy_the_same_full_field_allocation_after_classification():
    from app.routes.feed import _annotate_distribution_allocations

    prices = [0.255, 0.255, 0.25, 0.24]
    outcomes = [SimpleNamespace(id=i, name=name, external_id=None, current_probability=p)
                for i, (name, p) in enumerate(zip(["Alice", "Bob", "Casey", "Dani"], prices))]
    card = {"suggested_format": "outcome_distribution", "field_is_a_race": True,
            "distribution_outcomes": [{"label": o.name, "probability": o.current_probability} for o in outcomes]}
    before = deepcopy(card)
    _annotate_distribution_allocations(card, outcomes, "Winner", mutually_exclusive=True, field_complete=True)
    assert [r["rendered_percent"] for r in card["distribution_outcomes"]] == [26, 25, 25, 24]
    assert sum(r["rendered_percent"] for r in card["distribution_outcomes"]) == 100
    assert card["suggested_format"] == before["suggested_format"]
    for row, original in zip(card["distribution_outcomes"], before["distribution_outcomes"]):
        assert {k: v for k, v in row.items() if k != "rendered_percent"} == original


def test_feed_divisor_and_allocation_keep_an_authoritative_winner_as_a_result():
    from app.routes.feed import _feed_display_scale

    outcomes = [
        SimpleNamespace(id=1, name="Winner", current_probability=1.0, is_winner=True, resolution_source="api_settlement"),
        SimpleNamespace(id=2, name="Loser", current_probability=0.003, is_winner=False, resolution_source="api_settlement"),
    ]
    assert _feed_display_scale(outcomes, mutually_exclusive=True) == 1
    rows = [{"id": o.id, "name": o.name, "probability": o.current_probability} for o in outcomes]
    assert _normalize_feed_probabilities(rows, outcomes, mutually_exclusive=True) == rows
    assert rows[0]["probability"] == 1.0
    assert all("rendered_percent" not in r for r in rows)


def test_feed_allocation_matches_humanized_rows_by_id():
    outcomes = [SimpleNamespace(id=1, name="Yes", current_probability=0.505),
                SimpleNamespace(id=2, name="No", current_probability=0.495)]
    top = [{"id": 1, "name": "Will it happen?", "probability": 0.505},
           {"id": 2, "name": "It will not happen", "probability": 0.495}]
    _normalize_feed_probabilities(top, outcomes, mutually_exclusive=True)
    assert [o["rendered_percent"] for o in top] == [50, 50]
