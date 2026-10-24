"""The event wrapper and its condition-backed duel are one PM contract."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as Row

import pytest

from app.utils.live_blend import (
    MarketOutcomes, compute_source_home_probability, has_proven_home_orientation,
)

CONDITION = "0x" + "20" * 32
HOME, AWAY = "Reynolds / Watt", "Behar / Paris"


def graph():
    now = datetime.now(timezone.utc)
    def outcome(id, name, price, external_id, rank=1):
        return Row(id=id, name=name, current_probability=price, external_id=external_id,
                   rank=rank, last_updated=now - timedelta(seconds=2),
                   is_winner=None, resolution_source=None)
    def market(id, external_id):
        return Row(id=id, source="polymarket", external_id=external_id,
                   name="Lyon Open (Doubles): Reynolds/Watt vs Behar/Paris",
                   status="open", market_metadata={})
    wrapper = MarketOutcomes(market(66750258, "1224422"), [
        outcome(250757591, "Reynolds/Watt — Reynolds/Watt", .295, CONDITION),
    ], now - timedelta(hours=3), False)
    duel = MarketOutcomes(market(66756997, CONDITION), [
        outcome(250776126, "Reynolds/Watt", .46, CONDITION),
        outcome(250776127, "Behar/Paris", .54, CONDITION + "_side1", 2),
    ], now - timedelta(hours=3), False)
    return wrapper, duel


@pytest.mark.parametrize("reverse", [False, True])
def test_same_contract_wrapper_does_not_dilute_or_owe_a_second_observation(reverse):
    wrapper, duel = graph()
    reading = compute_source_home_probability([duel, wrapper] if reverse else [wrapper, duel], HOME, AWAY)
    assert reading.home_probability == .46
    assert reading.market.id == duel.market.id
    assert not reading.devigged
    assert has_proven_home_orientation(reading)
    assert [r.id for r in reading.contributing_outcomes] == [250776126]
    assert wrapper.outcomes[0].current_probability == .295  # no row mutation


@pytest.mark.parametrize("missing", ["wrapper", "outcome", "condition", "different", "suffix", "not_pm"])
def test_missing_or_different_identity_does_not_guess_a_duplicate(missing):
    wrapper, duel = graph()
    if missing == "wrapper":
        wrapper.market.external_id = "unknown"
    elif missing == "outcome":
        wrapper.outcomes[0].external_id = None
    elif missing == "condition":
        duel.market.external_id = "unknown"
    elif missing == "different":
        wrapper.outcomes[0].external_id = "0x" + "30" * 32
    elif missing == "suffix":
        wrapper.outcomes[0].external_id += "_yes"
    else:
        wrapper.market.source = duel.market.source = "other"
    reading = compute_source_home_probability([wrapper, duel], HOME, AWAY)
    assert reading.home_probability == .3775
    assert reading.devigged


def test_actual_distinct_pm_contracts_keep_existing_arithmetic():
    wrapper, duel = graph()
    wrapper.market.external_id = "0x" + "30" * 32
    assert compute_source_home_probability([wrapper, duel], HOME, AWAY).home_probability == .3775


@pytest.mark.parametrize("refusal", ["settled", "no_price", "derivative", "unknown_away", "unobserved"])
def test_unusable_child_cannot_displace_parent(refusal):
    wrapper, duel = graph()
    if refusal == "settled":
        duel.outcomes[0].is_winner = True
        duel.outcomes[0].resolution_source = "polymarket"
    elif refusal == "no_price":
        duel.outcomes[0].current_probability = None
    elif refusal == "derivative":
        duel.market.name += " - Set 1 Winner"
    elif refusal == "unobserved":
        for row in duel.outcomes:
            row.last_updated = duel.event_commence_time - timedelta(seconds=1)
    else:
        duel.outcomes[1].name = "Unknown team"
    reading = compute_source_home_probability([wrapper, duel], HOME, AWAY)
    assert reading.market.id == wrapper.market.id


def test_multi_outcome_parent_is_not_removed_by_one_matching_child():
    wrapper, duel = graph()
    wrapper.outcomes.append(Row(**{**vars(wrapper.outcomes[0]), "id": 999,
                                  "name": "Draw", "external_id": "0x" + "40" * 32}))
    reading = compute_source_home_probability([wrapper, duel], HOME, AWAY)
    assert reading.market.id == wrapper.market.id


def test_parent_without_a_child_keeps_its_existing_reading():
    wrapper, _ = graph()
    reading = compute_source_home_probability([wrapper], HOME, AWAY)
    assert reading.home_probability == .295


def test_exact_condition_hex_identity_is_case_insensitive():
    wrapper, duel = graph()
    wrapper.outcomes[0].external_id = "0x" + "AB" * 32
    duel.market.external_id = "0x" + "ab" * 32
    assert compute_source_home_probability([wrapper, duel], HOME, AWAY).home_probability == .46
