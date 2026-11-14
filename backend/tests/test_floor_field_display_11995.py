"""Israel's 17 no-bid bounds must not print as 17 extra points of chance."""

from copy import deepcopy
import json
import math
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
    return [{"id": r["id"], "name": r["name"],
             "probability": r["stored_probability"]} for r in SPECIMEN["outcomes"]]


def assert_display(actual):
    expected = {r["id"]: r for r in SPECIMEN["outcomes"]}
    assert len(actual) == 21
    assert sum(r["rendered_percent"] for r in actual) == 100
    assert sum(r["rendered_percent"] == 0 for r in actual) == 17
    for r in actual:
        assert r["rendered_percent"] == expected[r["id"]]["rendered_percent"]
        # Open bounds are encoded below 1% for the formatter already installed.
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
    assert _installed_5704_probability(preview[-1]) == "<1%"
    assert [o.current_probability for o in market.outcomes] == [
        r["stored_probability"] for r in SPECIMEN["outcomes"]
    ]


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


def _installed_5704_probability(row):
    """The shipped ios-1.0.6-5704 formatProbability boundary, before this PR."""
    pct = row["probability"] * 100
    if pct < 1:
        return "<1%"
    if pct > 99:
        return ">99%"
    return f"{row.get('rendered_percent', math.floor(pct + 0.5))}%"


def test_installed_5704_prints_all_seventeen_israel_bounds_after_json_transport():
    actual = rows()
    normalize_display_probs(actual)
    wire = json.loads(json.dumps(actual))
    labels = [_installed_5704_probability(row) for row in wire]
    assert labels.count("<1%") == 17
    assert "0%" not in labels
    assert sum(int(label[:-1]) for label in labels if label != "<1%") == 100


@pytest.mark.parametrize("mass", [1.0, 1.02])
def test_installed_bounds_stay_below_one_percent_at_and_above_unit_mass(mass):
    actual = [{"id": 1, "name": "A", "probability": 0.6 * mass},
              {"id": 2, "name": "B", "probability": 0.4 * mass},
              {"id": 3, "name": "C", "probability": 0.01}]
    normalize_display_probs(actual)
    assert 0 < actual[-1]["probability"] < 0.01
    assert _installed_5704_probability(actual[-1]) == "<1%"
    assert sum(row["rendered_percent"] for row in actual) == 100


def test_installed_underround_field_remains_refused_instead_of_printing_zero():
    actual = [{"name": "A", "probability": 0.57},
              {"name": "B", "probability": 0.38},
              {"name": "C", "probability": 0.01}]
    before = deepcopy(actual)
    assert normalize_display_probs(actual) is False
    assert actual == before
    assert _installed_5704_probability(actual[-1]) == "1%"


def test_bound_encoding_does_not_change_the_historical_scale_or_stored_legs():
    actual = rows()
    source = deepcopy(actual)
    assert normalize_display_probs(actual) is False
    assert actual[:4] == [dict(row, rendered_percent=expected["rendered_percent"])
                          for row, expected in zip(source[:4], SPECIMEN["outcomes"][:4])]
    for row in actual[4:]:
        assert 0 < 0.01 - row["probability"] <= math.ulp(0.01)
    # The one-ULP bound encoding is not a new scaling basis or a stored-price edit.
    assert all(row["probability"] == 0.01 for row in source[4:])
    encoded = deepcopy(actual)
    assert normalize_display_probs(actual) is False
    assert actual == encoded


def test_settled_field_does_not_receive_the_open_bound_encoding():
    actual = [{"name": "Winner", "probability": 1.0, "is_winner": True,
               "resolution_source": "api_settlement"},
              {"name": "Loser", "probability": 0.0},
              {"name": "Unpriced", "probability": 0.01}]
    before = deepcopy(actual)
    assert normalize_display_probs(actual) is False
    assert actual == before
