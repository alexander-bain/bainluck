"""The served full field owns normalization and whole-percent allocation."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.routes.feed import _apply_card_percents, _normalize_feed_probabilities
from app.utils.outcome_display import normalize_display_probs


@pytest.mark.parametrize(
    "prices",
    [[0.40, 0.39], [0.52, 0.51], [0.9, 0.8, 0.7], [0.985, 0.015] + [0.01] * 51],
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
        for i, p in enumerate([0.51, 0.51, 0.51, 0.3, 0.2])
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
        assert row["rendered_percent"] == full[row["name"]]["rendered_percent"]
