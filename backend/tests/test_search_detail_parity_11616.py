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


@pytest.mark.parametrize("lean", [False, True])
def test_supported_result_survives_without_any_prediction_price(lean):
    m = market([None, None], settled=True)
    selected = events._build_search_top_outcomes(m, lean=lean)
    assert selected[0]["name"] == NAMES[0]
    assert selected[0]["is_winner"] is True
    assert selected[0]["resolution_source"] == "api_settlement"
    assert all(row["probability"] is None for row in selected)
    assert not events._futures_card_has_no_answer(m)


@pytest.mark.parametrize("source", [None, "ungradeable_result", "unknown_source"])
def test_no_price_without_supported_result_keeps_the_old_navigation_rule(source):
    m = market([None, None], settled=True)
    for outcome in m.outcomes:
        outcome.resolution_source = source
    assert events._build_search_top_outcomes(m) == []
    assert events._futures_card_has_no_answer(m)


def test_missing_polymarket_settlement_price_does_not_invent_a_result():
    m = market([None, None], settled=True)
    m.status = "resolved"
    assert events._search_supported_result_ids(m) == set()
    detail = futures._format_market_detail(m)
    assert all(
        row["settlement_display"]["verdict"] == "unknown" for row in detail["outcomes"]
    )
    assert events._futures_card_has_no_answer(m)


def test_query_pins_a_supported_result_without_inventing_price_rank():
    m = market([None] * 6, exclusive=False)
    for index in (0, 5):
        m.outcomes[index].is_winner = True
        m.outcomes[index].resolution_source = "api_settlement"
    selected = events._build_search_top_outcomes(
        m, limit=1, query_terms=[("jalen", None)]
    )
    assert len(selected) == 1
    assert selected[0]["name"] == "Jalen Brunson"
    assert selected[0]["query_match"] is True
    assert selected[0]["matched_rank"] is None
    assert selected[0]["probability"] is None


def test_withheld_and_old_prediction_cannot_withdraw_a_supported_result():
    m = market([0.995, 0.005], settled=True)
    m.source = "kalshi"
    m.external_id = "KXEARNINGSMENTIONTFC-26APR17"
    for outcome in m.outcomes:
        outcome.last_updated = STAMP - timedelta(days=100)
    refused = {o.id for o in m.outcomes}
    assert not events._futures_market_prices_all_withheld(m, refused)
    assert not events._search_market_is_past_and_frozen(m, now=STAMP)
    selected = events._build_search_top_outcomes(m, withheld=refused)
    assert selected[0]["is_winner"] is True
    assert selected[0]["probability"] is None


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


@pytest.mark.parametrize(
    "exclusive,prices,expected",
    [
        (True, [0.605, 0.395], [61, 39]),
        (True, [0.395, 0.605], [39, 61]),
        (False, [0.605, 0.395], [61, 40]),
        (False, [0.605, 0.395, 0.2], [61, 40, 20]),
        (True, [0.605, 0.395, None], [61, 40, None]),
        (True, [0.0, 0.999], [0, 100]),
    ],
)
def test_full_field_integer_decision_survives_every_search_limit(
    exclusive, prices, expected
):
    m = market(prices, exclusive=exclusive)
    payload = outputs(m)
    by_name = {name: integer for name, integer in zip(NAMES, expected)}
    assert {
        row["name"]: row["rendered_percent"] for row in payload["detail"]
    } == by_name
    for lean in [False, True]:
        for limit in [1, 2, 3, 5]:
            rows = events._build_search_top_outcomes(m, limit=limit, lean=lean)
            assert rows
            assert all(row["rendered_percent"] == by_name[row["name"]] for row in rows)


def test_query_pinned_nonleader_keeps_full_field_integer():
    m = market([0.605, 0.395, 0.2], exclusive=False)
    rows = events._build_search_top_outcomes(
        m, limit=2, lean=False, query_terms=[("nikola", None), ("jokic", None)]
    )
    assert any(row.get("query_match") for row in rows)
    expected = dict(zip(NAMES, [61, 40, 20]))
    assert all(row["rendered_percent"] == expected[row["name"]] for row in rows)


def test_withheld_probability_has_no_integer_even_when_result_survives():
    payload = outputs(market([0.995, 0.005], settled=True), withheld={1})
    for surface in ["detail", "search", "typeahead"]:
        winner = next(row for row in payload[surface] if row["name"] == NAMES[0])
        assert winner["probability"] is None
        assert winner["rendered_percent"] is None
        assert winner["is_winner"] is True
