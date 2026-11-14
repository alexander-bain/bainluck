"""Israel's 17 no-bid bounds must not print as 17 extra points of chance."""

from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.routes.feed import _normalize_feed_probabilities, _apply_card_percents
from app.routes.futures import _format_market_detail
from app.utils.outcome_display import normalize_display_probs
from tests.test_floor_tail_is_not_vig_8595 import _market, MEASURED_AT


SPECIMEN = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/one_winner_floor_field_11995.json")
    .read_text()
)


def rows():
    return [{k: r[k] for k in ("id", "name", "probability")} for r in SPECIMEN["outcomes"]]


def assert_display(actual):
    expected = {r["id"]: r for r in SPECIMEN["outcomes"]}
    assert len(actual) == 21
    assert sum(r["rendered_percent"] for r in actual) == 100
    assert sum(r["rendered_percent"] == 0 for r in actual) == 17
    for r in actual:
        assert r["rendered_percent"] == expected[r["id"]]["rendered_percent"]
        # Numeric upper bounds retain their meaning; no invented zero prices.
        assert r["probability"] == expected[r["id"]]["probability"]


def test_israel_full_field_allocates_100_without_shrinking_its_leaders():
    actual = rows()
    assert sum(r["probability"] for r in actual) == pytest.approx(1.17)
    assert normalize_display_probs(actual) is False  # only the display changed
    assert_display(actual)


def test_reordering_the_field_keeps_each_candidates_number():
    actual = list(reversed(rows()))
    normalize_display_probs(actual)
    assert_display(actual)


def test_full_detail_and_feed_preview_receive_the_same_bound_allocations():
    market = _market([(r["id"], r["name"], r["probability"]) for r in rows()])
    market.id, market.name = SPECIMEN["market_id"], SPECIMEN["market_name"]
    # The fixture is a recorded observation; freshness uses that same clock.
    with patch("app.routes.futures.datetime") as clock:
        clock.now.return_value = MEASURED_AT
        detail = _format_market_detail(market)
    assert_display(detail["outcomes"])
    preview = rows()[:5]
    _normalize_feed_probabilities(
        preview, market.outcomes, market.name, mutually_exclusive=True
    )
    _apply_card_percents(preview)
    by_id = {r["id"]: r for r in detail["outcomes"]}
    for r in preview:
        assert r["rendered_percent"] == by_id[r["id"]]["rendered_percent"]
    assert preview[-1]["rendered_percent"] == 0


@pytest.mark.parametrize("kwargs", [
    {"mutually_exclusive": False}, {"field_complete": False},
])
def test_bounds_do_not_override_distribution_refusals(kwargs):
    actual = rows()
    before = deepcopy(actual)
    normalize_display_probs(actual, **kwargs)
    assert actual == before


def test_a_real_subcent_tail_still_counts_toward_the_field():
    actual = rows()
    for r in actual[4:]:
        r["probability"] = 0.006
    normalize_display_probs(actual)
    assert sum(r["probability"] for r in actual) == pytest.approx(1, abs=1e-7)
    assert sum(r["rendered_percent"] for r in actual) == 100
    assert actual[0]["probability"] < 0.495
