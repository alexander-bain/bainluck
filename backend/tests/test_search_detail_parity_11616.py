"""#11616: shared input yields the destination's probability and result state.

Synthetic identical inputs at real serializer/refusal seams. Reader and cache
integration are separate gates; no network or production data is used here.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from contextlib import ExitStack
from unittest.mock import patch

from app.routes import events, futures

from tests import test_futures_detail_empty_book_6757 as rig

STAMP = datetime(2026, 10, 25, 6, 40, tzinfo=timezone.utc)
NAMES = [
    "Victor Wembanyama",
    "Shai Gilgeous-Alexander",
    "Nikola Jokic",
    "Luka Doncic",
    "Anthony Edwards",
    "Jalen Brunson",
]


def market(prices, *, exclusive=True, old=False, old_leg=False, settled=False):
    m = rig._market()
    m.id = 11616
    m.name = "NBA 2027 MVP winner"
    m.mutually_exclusive = exclusive
    m.outcomes = m.outcomes[: len(prices)]
    m.updated_at = STAMP
    m.resolution_date = datetime(2099, 1, 1, tzinfo=timezone.utc)
    for i, (o, p) in enumerate(zip(m.outcomes, prices)):
        o.name = NAMES[i]
        o.external_id = f"synthetic-11616-{i}"
        o.current_probability = p
        o.current_yes_bid = max(0, p - 0.01) if p is not None else None
        o.current_yes_ask = min(1, p + 0.01) if p is not None else None
        o.last_updated = (
            STAMP - timedelta(days=45) if old or (old_leg and i == 0) else STAMP
        )
        if settled:
            o.is_winner = i == 0
            o.resolution_source = "api_settlement"
    return m


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return STAMP.astimezone(tz) if tz else STAMP.replace(tzinfo=None)


def outputs(m, *, withheld=None, query_terms=None):
    original = deepcopy(m)
    with ExitStack() as stack:
        for module in [events, futures]:
            stack.enter_context(patch.object(module, "datetime", FixedDatetime))
        detail = futures._format_market_detail(
            m, unsupported_price_outcome_ids=withheld
        )
        full = events._build_search_top_outcomes(
            m, limit=5, lean=False, withheld=withheld, query_terms=query_terms
        )
        lean = events._build_search_top_outcomes(
            m, limit=3, lean=True, withheld=withheld, query_terms=query_terms
        )
    assert m == original, "serializer mutated its input"
    return {
        "detail": detail["outcomes"],
        "search": full,
        "typeahead": lean,
        "prices_withheld": detail["prices_withheld"],
    }


def cases():
    complete = market([0.31, 0.26, 0.20, 0.18, 0.15, 0.10])
    return {
        "full_field": outputs(complete),
        "pinned_lower_outcome": outputs(
            complete, query_terms=[("jalen", None), ("brunson", None)]
        ),
        "shared_withholding": outputs(market([0.80, 0.60, 0.20]), withheld={3}),
        "stale_observation": outputs(market([0.60, 0.25, 0.15], old_leg=True)),
        "uniformly_old_control": outputs(market([0.60, 0.25, 0.15], old=True)),
        "stale_settled": outputs(market([0.995, 0.005], old_leg=True, settled=True)),
        "nonexclusive_control": outputs(market([0.8, 0.6, 0.2], exclusive=False)),
        "zero_null_control": outputs(market([0.7, 0.3, 0, None])),
        "unscaled_control": outputs(market([0.6, 0.25, 0.15])),
    }


@pytest.fixture(scope="module")
def observed():
    return cases()


@pytest.mark.parametrize(
    "case",
    [
        "full_field",
        "pinned_lower_outcome",
        "shared_withholding",
        "stale_observation",
        "stale_settled",
    ],
)
@pytest.mark.parametrize("surface", ["search", "typeahead"])
def test_same_input_has_same_displayed_price_or_withheld_state(observed, case, surface):
    payload = observed[case]
    detail = {o["name"]: o for o in payload["detail"]}
    assert payload[surface], "fixture must produce real displayed outcomes"
    for outcome in payload[surface]:
        assert outcome["name"] in detail
        assert outcome["probability"] == detail[outcome["name"]]["probability"]


@pytest.mark.parametrize(
    "case",
    [
        "nonexclusive_control",
        "zero_null_control",
        "uniformly_old_control",
        "unscaled_control",
    ],
)
@pytest.mark.parametrize("surface", ["search", "typeahead"])
def test_supported_controls_retain_parity(observed, case, surface):
    payload = observed[case]
    detail = {o["name"]: o for o in payload["detail"]}
    assert payload[surface]
    for outcome in payload[surface]:
        assert outcome["probability"] == detail[outcome["name"]]["probability"]


@pytest.mark.parametrize("surface", ["search", "typeahead"])
def test_query_pin_changes_selection_not_shared_outcome_values(observed, surface):
    before = {o["name"]: o["probability"] for o in observed["full_field"][surface]}
    after = {
        o["name"]: o["probability"] for o in observed["pinned_lower_outcome"][surface]
    }
    assert "Jalen Brunson" not in before and "Jalen Brunson" in after
    assert before["Victor Wembanyama"] == after["Victor Wembanyama"]


def test_withholding_does_not_erase_confirmed_result(observed):
    payload = observed["stale_settled"]
    for surface in ["detail", "search", "typeahead"]:
        winner = next(o for o in payload[surface] if o["name"] == "Victor Wembanyama")
        assert winner["is_winner"] is True
        assert winner["resolution_source"] == "api_settlement"


async def test_actual_search_refusal_union_covers_relative_observation_age():
    m = market([0.60, 0.25, 0.15], old_leg=True)
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    result.scalars.return_value.all.return_value = []
    result.scalar.return_value = None
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    withheld = await events._search_withheld_price_ids(db, m)
    assert m.outcomes[0].id in withheld
    assert m.outcomes[1].id not in withheld


@pytest.mark.parametrize("surface", ["search", "typeahead"])
def test_transformed_field_does_not_keep_a_raw_movement_claim(observed, surface):
    payload = observed["full_field"]
    assert payload["detail"][0]["probability_change_24h"] is None
    assert payload[surface][0]["movement"] is None


@pytest.mark.parametrize("limit", [1, 2, 3, 5, 6, 20])
@pytest.mark.parametrize("lean", [False, True])
def test_selection_limit_does_not_change_full_field_value(limit, lean):
    m = market([0.31, 0.26, 0.20, 0.18, 0.15, 0.10])
    with patch.object(events, "datetime", FixedDatetime):
        out = events._build_search_top_outcomes(m, limit=limit, lean=lean)
    assert out[0]["probability"] == 0.2583
    assert out[0]["movement"] is None
    assert len(out) == min(limit, 6)


def test_detail_policy_retains_full_field_rounding_and_withholding(observed):
    assert [o["probability"] for o in observed["full_field"]["detail"]] == [
        0.2583,
        0.2167,
        0.1667,
        0.15,
        0.125,
        0.0833,
    ]
    assert [o["probability"] for o in observed["shared_withholding"]["detail"]] == [
        0.8,
        0.6,
        None,
    ]
    assert observed["shared_withholding"]["prices_withheld"] == 1
