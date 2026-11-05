"""#11995 supersedes the price-mass ceiling: semantics select one-winner fields."""

from types import SimpleNamespace

import pytest

from app.routes.feed import _feed_display_scale, _normalize_feed_probabilities
from app.utils.outcome_display import normalize_display_probs


@pytest.mark.parametrize("mass", [0.8, 1.01, 1.60, 1.61, 1.86, 2.01])
def test_no_price_mass_ceiling_on_a_one_winner_field(mass):
    prices = [mass / 3] * 3
    full = [
        SimpleNamespace(id=i, name=f"Team {i}", current_probability=p)
        for i, p in enumerate(prices)
    ]
    page = [
        {"id": o.id, "name": o.name, "probability": o.current_probability} for o in full
    ]
    preview = [dict(o) for o in page]
    normalize_display_probs(page)
    _normalize_feed_probabilities(preview, full, mutually_exclusive=True)
    assert _feed_display_scale(full, mutually_exclusive=True) == pytest.approx(mass)
    assert preview == page
    assert sum(o["rendered_percent"] for o in page) == 100


@pytest.mark.parametrize("exclusive", [False])
def test_only_proved_one_winner_fields_are_divided(exclusive):
    full = [
        SimpleNamespace(name=n, current_probability=p)
        for n, p in [("Alice", 0.9), ("Bob", 0.8)]
    ]
    assert _feed_display_scale(full, mutually_exclusive=exclusive) == 1
