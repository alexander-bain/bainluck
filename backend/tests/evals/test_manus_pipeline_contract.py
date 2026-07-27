import json
from pathlib import Path


CONTRACT_PATH = (
    Path(__file__).parents[2] / "scripts" / "evals" / "manus_pipeline_contract.json"
)


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text())


def test_run_evidence_states_are_fail_closed() -> None:
    runs = {row["id"]: row for row in _contract()["runs"]}

    fresh = runs["fresh_success"]
    assert fresh["expected_state"] == "eligible_for_intake"
    for field in (
        "run_id",
        "task_id",
        "started_at",
        "completed_at",
        "target_build",
        "prompt_hash",
        "report_hash",
    ):
        assert fresh[field]
    assert fresh["status"] == "stopped"
    assert fresh["report"].strip()

    assert runs["stale_replay"]["report_hash"] == fresh["report_hash"]
    assert runs["stale_replay"]["expected_state"] == "rejected_stale_replay"
    assert (
        runs["zero_credit_ambiguous"]["expected_state"]
        == "complete_untrusted_needs_evidence"
    )
    assert runs["timeout"]["expected_state"] == "rejected_incomplete"


def test_routing_and_semantic_dedup_contract() -> None:
    contract = _contract()
    findings = {row["id"]: row for row in contract["findings"]}

    assert contract["defaults"]["alert_priority"] == "priority:p2"
    assert findings["negated_severity"]["expected_priority"] == "priority:p2"
    assert findings["negated_severity"]["expected_route"] == "needs-triage"
    assert findings["product_taste"]["expected_route"] == "alex_ruling"

    assert (
        findings["entity_alpha"]["expected_fingerprint_group"]
        != findings["entity_beta"]["expected_fingerprint_group"]
    )
    assert (
        findings["wording_original"]["expected_fingerprint_group"]
        == findings["wording_rephrased"]["expected_fingerprint_group"]
    )
    assert findings["quoted_fingerprint"]["expected_canonical_owner"] is False


def test_verification_requires_matching_build_and_successful_collection() -> None:
    rows = {row["id"]: row for row in _contract()["verifications"]}

    assert rows["wrong_build"]["verdict"] == "pass"
    assert rows["wrong_build"]["expected_state"] == "rejected_wrong_build"
    assert rows["collection_failure"]["expected_state"] == "error"
    assert rows["matching_build_pass"]["expected_state"] == "eligible_closure_evidence"
    assert (
        rows["matching_build_pass"]["requested_build"]
        == rows["matching_build_pass"]["observed_build"]
    )


def test_ground_truth_has_zero_influence_before_explicit_review() -> None:
    contract = _contract()
    rows = {row["id"]: row for row in contract["ground_truth"]}

    assert contract["defaults"]["ground_truth_authority_before_review"] == "none"
    assert rows["unreviewed_observation"]["expected_import"] == "rejected"
    assert rows["unreviewed_observation"]["expected_authority"] == "none"
    assert rows["reviewed_rejected_observation"]["expected_import"] == "rejected"
    assert rows["reviewed_accepted_observation"]["expected_import"] == "accepted"
    assert rows["reviewed_accepted_observation"]["expected_authority"] == "advisory"
