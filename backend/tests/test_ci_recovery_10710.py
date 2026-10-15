"""An absent gate cannot become green or authorize a blind recovery (#10710)."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "ci_recovery.py"
SPEC = importlib.util.spec_from_file_location("ci_recovery_10710", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FIXTURE = Path(__file__).parent / "fixtures" / "ci_recovery_10710.json"


@pytest.fixture
def incident():
    return json.loads(FIXTURE.read_text())


def complete(snapshot):
    """Synthetic completion of the missing aggregate on the SAME attempt."""
    data = deepcopy(snapshot)
    job = deepcopy(data["jobs"]["jobs"][0])
    job.update(id=999999999999, name="search-recall")
    data["jobs"]["jobs"].append(job)
    data["jobs"]["total_count"] += 1
    data["run"]["conclusion"] = "success"
    return data


def test_real_incident_keeps_missing_aggregate_and_prohibited_retry(incident):
    result = MODULE.disposition(incident)
    assert result["classification"] == "missing_required_job"
    assert result["missing_required_jobs"] == ["search-recall"]
    assert result["failed_jobs"] == []
    assert "no-retry" in result["action"]
    assert result["proposed_command"] is None
    assert result["merge_authorized"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_head", "b" * 40),
        ("source_open", False),
    ],
)
def test_changed_head_or_closed_pr_cannot_be_recovered(incident, field, value):
    incident[field] = value
    incident["policy"].update(retry_prohibited=False, recovery_authorized=True)
    result = MODULE.disposition(incident)
    assert result["classification"] == "stale_source"
    assert result["proposed_command"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("head_sha", "a" * 40),
        ("run_attempt", 2),
        ("id", 9),
        ("repository", {"full_name": "other/repo"}),
        ("repository", []),
    ],
)
def test_wrong_run_identity_cannot_borrow_passing_evidence(incident, field, value):
    incident["run"][field] = value
    assert MODULE.disposition(incident)["classification"] == "unknown"


@pytest.mark.parametrize(
    "field,value",
    [
        ("head_sha", "a" * 40),
        ("run_attempt", 2),
        ("run_id", 9),
        ("id", None),
        ("status", "future_status"),
        ("conclusion", "future_result"),
        ("status", []),
        ("conclusion", {}),
    ],
)
def test_wrong_attempt_or_invalid_job_refuses_diagnosis(incident, field, value):
    incident["jobs"]["jobs"][0][field] = value
    assert MODULE.disposition(incident)["classification"] == "unknown"


def test_incomplete_pagination_is_not_missing_job_diagnosis(incident):
    incident["jobs"]["total_count"] += 100
    assert MODULE.disposition(incident)["classification"] == "unknown"


def test_duplicate_job_identity_refuses_mixed_attempt_response(incident):
    incident["jobs"]["jobs"].append(deepcopy(incident["jobs"]["jobs"][0]))
    incident["jobs"]["total_count"] += 1
    assert MODULE.disposition(incident)["classification"] == "unknown"


@pytest.mark.parametrize(
    "change",
    [
        {"active_duplicate": True},
        {"active_duplicate": None},
        {"read_errors": ["GitHub API 403/rate limit"]},
        {"required_jobs": []},
        {"source_open": None},
        {"expected_head": "shortsha"},
        {"policy": {}},
    ],
)
def test_unknown_coordination_or_policy_never_authorizes_action(incident, change):
    incident.update(change)
    result = MODULE.disposition(incident)
    assert result["classification"] in {"unknown", "duplicate_or_unknown"}
    assert result["proposed_command"] is None


@pytest.mark.parametrize("conclusion", ["failure", "timed_out", "action_required"])
def test_failed_job_is_not_invented_provider_outage(incident, conclusion):
    incident["jobs"]["jobs"][0]["conclusion"] = conclusion
    incident["policy"].update(retry_prohibited=False, recovery_authorized=True)
    result = MODULE.disposition(incident)
    assert result["classification"] == "job_failure"
    assert result["proposed_command"] is None


def test_startup_failure_can_only_propose_one_explicitly_authorized_recovery(incident):
    data = complete(incident)
    data["run"]["conclusion"] = "failure"
    data["jobs"]["jobs"][0]["conclusion"] = "startup_failure"
    data["policy"].update(retry_prohibited=False, recovery_authorized=True)
    result = MODULE.disposition(data)
    assert result["classification"] == "infrastructure_startup_failure"
    assert result["proposed_command"] == [
        "gh",
        "run",
        "rerun",
        "37651724603",
        "--failed",
        "--repo",
        "alexander-bain/bainluck",
    ]
    assert result["executes_recovery"] is False
    assert result["merge_authorized"] is False
    data["policy"]["recoveries_used"] = 1
    assert MODULE.disposition(data)["proposed_command"] is None
    assert "stop" in MODULE.disposition(data)["action"]


def test_authorized_missing_job_requires_whole_run_owner_disposition(incident):
    incident["policy"].update(retry_prohibited=False, recovery_authorized=True)
    result = MODULE.disposition(incident)
    assert result["proposed_command"] is None
    incident["policy"]["provider_cause_confirmed"] = True
    result = MODULE.disposition(incident)
    assert "--failed" not in result["proposed_command"]
    assert "confirmation of infrastructure cause" in result["action"]
    incident["policy"]["recovery_authorized"] = False
    assert MODULE.disposition(incident)["proposed_command"] is None


def test_owning_no_retry_rule_overrides_authorization_flag(incident):
    incident["policy"]["recovery_authorized"] = True
    result = MODULE.disposition(incident)
    assert result["proposed_command"] is None
    assert "no-retry" in result["action"]


def test_run_startup_failure_without_jobs_never_proposes_pointless_rerun(incident):
    incident["run"]["conclusion"] = "startup_failure"
    incident["jobs"] = {"total_count": 0, "jobs": []}
    incident["policy"].update(
        retry_prohibited=False,
        recovery_authorized=True,
        provider_cause_confirmed=True,
    )
    result = MODULE.disposition(incident)
    assert result["classification"] == "workflow_startup_failure"
    assert result["proposed_command"] is None
    assert "workflow file" in result["action"]


def test_skipped_matrix_parent_does_not_become_provider_outage(incident):
    parent = deepcopy(incident["jobs"]["jobs"][0])
    parent.update(id=999999999999, name="backend-tests", conclusion="skipped")
    incident["jobs"] = {"total_count": 1, "jobs": [parent]}
    incident["policy"].update(
        retry_prohibited=False,
        recovery_authorized=True,
        provider_cause_confirmed=True,
    )
    result = MODULE.disposition(incident)
    assert result["classification"] == "scope_skipped_required_jobs"
    assert result["proposed_command"] is None
    assert "unchanged inputs" in result["action"]
    assert "backend-tests (1)" in result["missing_required_jobs"]


def test_unrelated_skipped_parent_does_not_hide_missing_aggregate(incident):
    incident["jobs"]["jobs"][0].update(name="backend-tests-old", conclusion="skipped")
    assert MODULE.disposition(incident)["classification"] == "missing_required_job"


def test_cancelled_or_unfinished_evidence_never_retries(incident):
    incident["run"]["conclusion"] = "cancelled"
    assert MODULE.disposition(incident)["classification"] == "cancelled"
    incident["run"].update(status="in_progress", conclusion=None)
    assert MODULE.disposition(incident)["classification"] == "pending"


def test_complete_workflow_with_unfinished_job_is_unknown(incident):
    incident["jobs"]["jobs"][0].update(status="in_progress", conclusion=None)
    assert MODULE.disposition(incident)["classification"] == "unknown"


def test_skipped_or_neutral_required_gate_does_not_pay_acceptance(incident):
    for conclusion in ["skipped", "neutral"]:
        data = complete(incident)
        next(j for j in data["jobs"]["jobs"] if j["name"] == "search-recall")[
            "conclusion"
        ] = conclusion
        assert (
            MODULE.disposition(data)["classification"] == "incomplete_required_evidence"
        )


def test_success_is_advisory_and_does_not_authorize_merge(incident):
    result = MODULE.disposition(complete(incident))
    assert result["classification"] == "ci_complete"
    assert result["merge_authorized"] is False
    assert result["proposed_command"] is None


def test_cli_unavailable_input_returns_explicit_unknown(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "absent")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["classification"] == "unknown"


def test_retained_incident_cli_has_no_github_or_network_dependency():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURE)],
        capture_output=True,
        text=True,
        env={"PATH": "/does-not-exist"},
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["classification"] == "missing_required_job"
    assert report["executes_recovery"] is False
