"""Source marks on raw and reverified cumulative-deadline contracts."""

from copy import deepcopy
from decimal import Decimal

import pytest

from app.utils.deadline_family_story import (
    DEADLINE_RULE_CONTRACT_KEY,
    _validate_member_contract_dict,
    build_deadline_member_contract,
    extract_polymarket_deadline_rule_contract,
)
from tests.test_deadline_family_story_9878 import (
    DEC31_RESOLUTION_ISO,
    DEC31_RULE_DESCRIPTION,
    RETAINED_NOW,
    _make_dec31_outcomes,
)


def member(*, outcomes=None, **overrides):
    args = dict(
        market_id=65678074,
        name="Zacharia issues public apology by December 31?",
        source="polymarket",
        external_id="cond-dec",
        group_id="polymarket:256241",
        resolution_date=DEC31_RESOLUTION_ISO,
        description=DEC31_RULE_DESCRIPTION,
        outcomes=outcomes if outcomes is not None else _make_dec31_outcomes(),
        now=RETAINED_NOW,
    )
    contract = build_deadline_member_contract(**(args | overrides))
    assert contract is not None
    return contract


def verified(contract):
    rebuilt, reason = _validate_member_contract_dict(contract, now=RETAINED_NOW)
    assert reason is None
    assert rebuilt is not None
    return rebuilt


def test_independent_inputs_and_unknown_ages_survive_reverification():
    no, yes = _make_dec31_outcomes()
    no["current_probability"] = Decimal("0.73")
    yes["current_probability"] = Decimal("0.245")
    initial = member(outcomes=[no, yes])
    for row in (initial, verified(initial)):
        for key, value in (("source_mark", 0.245), ("no_source_mark", 0.73)):
            mark = row[key]
            assert mark["state"] == "single"
            assert mark["sources"] == [
                {
                    "key": "polymarket",
                    "name": "Polymarket",
                    "probability": value,
                    "observed_at": None,
                    "reason": "observation_unknown",
                }
            ]
        assert row["price_observed_at"] is not None


@pytest.mark.parametrize(
    "hidden,missing,present",
    [
        (246879007, "source_mark", "no_source_mark"),
        (246879008, "no_source_mark", "source_mark"),
    ],
)
def test_withheld_leg_never_uses_its_sibling(hidden, missing, present):
    original = member(withheld_outcome_ids={hidden})
    for row in (original, verified(original)):
        assert row[missing] == {
            "state": "none",
            "sources": [],
            "reason": "no_probability",
        }
        assert row[present]["state"] == "single"


@pytest.mark.parametrize(
    "authority,official",
    [
        ("clob_authoritative", True),
        ("api_settlement", True),
        ("box_score", True),
        ("settlement_sync", False),
        ("clean_resolution", False),
        (None, False),
    ],
)
def test_verified_grade_keeps_its_actual_authority(authority, official):
    no, yes = _make_dec31_outcomes()
    no.update(is_winner=True, resolution_source=authority)
    initial = member(outcomes=[no, yes], status="resolved")
    for row in (initial, verified(initial), verified(verified(initial))):
        for key, result in (("source_mark", "Lost"), ("no_source_mark", "Won")):
            if official:
                assert row[key] == {
                    "state": "settled",
                    "sources": [],
                    "settled": {"source": authority, "result": result, "at": None},
                }
            else:
                assert row[key]["state"] == "none"
                assert row[key]["reason"] == "result_unknown"


def test_legacy_verified_payload_does_not_certify_a_synthetic_api_grade():
    no, yes = _make_dec31_outcomes()
    no.update(is_winner=True, resolution_source="settlement_sync")
    legacy = member(outcomes=[no, yes], status="resolved")
    legacy.pop("source_mark", None)
    legacy.pop("no_source_mark", None)
    # Earlier bundle verification labeled reconstructed winners api_settlement.
    legacy["settlement"]["authoritative_source"] = "api_settlement"
    rebuilt = verified(legacy)
    for row in (rebuilt, verified(rebuilt)):
        assert row["settlement"]["result"] == "No"
        assert row["source_mark"]["reason"] == "result_unknown"
        assert row["no_source_mark"]["reason"] == "result_unknown"


@pytest.mark.parametrize("side", ["Yes", "No"])
def test_gamma_declared_result_binds_both_marks_to_its_condition(side):
    record = extract_polymarket_deadline_rule_contract(
        question="Zacharia issues public apology by December 31?",
        description=DEC31_RULE_DESCRIPTION,
        group_item_title="December 31",
        end_date=DEC31_RESOLUTION_ISO,
        condition_id="cond-dec",
        closed=True,
        uma_resolution_status="resolved",
        outcomes=["Yes", "No"],
        outcome_prices=[1.0, 0.0] if side == "Yes" else [0.0, 1.0],
    )
    assert record is not None
    for condition in ("cond-dec", None, "different-condition"):
        held = {**record, "condition_id": condition}
        original = member(market_metadata={DEADLINE_RULE_CONTRACT_KEY: held})
        if condition == "cond-dec":
            for row in (original, verified(original)):
                for key, leg in (("source_mark", "Yes"), ("no_source_mark", "No")):
                    assert row[key]["settled"] == {
                        "source": "polymarket",
                        "result": "Won" if side == leg else "Lost",
                        "at": None,
                    }
        else:
            assert original["source_mark"]["reason"] == "result_unknown"
            assert original["no_source_mark"]["reason"] == "result_unknown"


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"status": "closed"}, "trading_closed"),
        ({"status": "void"}, "void"),
        ({"status": "resolved"}, "result_unknown"),
        ({"source": "unrecognized"}, "source_evidence_incomplete"),
    ],
)
def test_unproved_sources_or_results_keep_the_reason(changes, reason):
    row = member(**changes)
    for key in ("source_mark", "no_source_mark"):
        assert row[key] == {"state": "none", "sources": [], "reason": reason}


def test_persisted_deadline_passed_does_not_become_a_current_quote():
    legacy = member()
    legacy["settlement"].update(state="deadline_passed", status="open")
    rebuilt = verified(legacy)
    assert rebuilt["settlement"]["state"] == "deadline_passed"
    assert rebuilt["source_mark"]["reason"] == "deadline_passed"
    assert rebuilt["no_source_mark"]["reason"] == "deadline_passed"


def test_displayed_percent_uses_the_bound_yes_row_and_preserves_inputs():
    no, yes = _make_dec31_outcomes()
    no["current_probability"] = 0.70
    yes["current_probability"] = 0.40
    top = [
        {"id": no["id"], "rendered_percent": 64, "probability": 0.63636364},
        {"id": yes["id"], "rendered_percent": 36, "probability": 0.36363636},
    ]
    snapshot = deepcopy(top)
    original = member(outcomes=[no, yes], top_outcomes_data=top)
    for row in (original, verified(original)):
        assert row["yes_probability"] == 0.40
        assert row["yes_rendered_percent"] == 36
        assert row["source_mark"]["sources"][0]["probability"] == 0.40
        assert "total 100%" in row["source_mark"]["method"]
        assert row["no_source_mark"]["sources"][0]["probability"] == 0.70
    assert top == snapshot
    top[1]["rendered_percent"] = 89
    inconsistent = member(outcomes=[no, yes], top_outcomes_data=top)
    assert verified(inconsistent)["source_mark"]["reason"] == "display_basis_conflict"
    top[1].update(rendered_percent=40, probability=0.2)
    inconsistent = member(outcomes=[no, yes], top_outcomes_data=top)
    for row in (inconsistent, verified(inconsistent)):
        assert row["source_mark"]["reason"] == "display_basis_conflict"
