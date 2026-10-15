#!/usr/bin/env python3
"""Read-only CI disposition for #10710. Never retries or changes a GitHub check.

Consume an identity-bound snapshot (see docs/ci-recovery.md), including the
complete jobs of ONE attempt. A usable diagnosis is not merge authorization.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


SHA = re.compile(r"[0-9a-f]{40}")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
STATUSES = {"queued", "in_progress", "completed", "waiting", "pending", "requested"}
CONCLUSIONS = {
    "success",
    "failure",
    "neutral",
    "cancelled",
    "skipped",
    "timed_out",
    "action_required",
    "startup_failure",
    "stale",
}


def positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def valid_state(record: dict[str, Any]) -> bool:
    status, conclusion = record.get("status"), record.get("conclusion")
    if not isinstance(status, str) or status not in STATUSES:
        return False
    if status == "completed":
        return isinstance(conclusion, str) and conclusion in CONCLUSIONS
    return conclusion is None


def disposition(snapshot: Any) -> dict[str, Any]:
    """Fail closed on missing, partial, inconsistent or identity-mixed evidence."""
    result: dict[str, Any] = {
        "classification": "unknown",
        "merge_authorized": False,
        "executes_recovery": False,
        "owner": "Integrator",
        "action": "Obtain complete, current evidence; keep the existing merge hold.",
        "reason": "Invalid snapshot.",
        "missing_required_jobs": [],
        "failed_jobs": [],
        "proposed_command": None,
    }

    def finish(kind: str, reason: str, action: str) -> dict[str, Any]:
        result.update(classification=kind, reason=reason, action=action)
        return result

    if not isinstance(snapshot, dict) or snapshot.get("read_errors") != []:
        return result
    required = snapshot.get("required_jobs")
    if (
        not isinstance(required, list)
        or not required
        or any(not isinstance(x, str) or not x.strip() for x in required)
        or len(set(required)) != len(required)
    ):
        result["reason"] = "Required job set is absent, empty or malformed."
        return result
    repo = snapshot.get("repository")
    expected = snapshot.get("expected_head")
    current = snapshot.get("current_head")
    run = snapshot.get("run")
    jobs = snapshot.get("jobs")
    if (
        not isinstance(repo, str)
        or not REPO.fullmatch(repo)
        or not isinstance(expected, str)
        or not SHA.fullmatch(expected)
        or not isinstance(current, str)
        or not SHA.fullmatch(current)
        or not isinstance(run, dict)
        or not isinstance(jobs, dict)
        or not positive_int(snapshot.get("expected_run_id"))
        or not positive_int(snapshot.get("expected_attempt"))
    ):
        result["reason"] = (
            "Repository, full source SHA, run or attempt identity is missing."
        )
        return result
    run_repo = run.get("repository")
    if (
        not isinstance(run_repo, dict)
        or not positive_int(run.get("id"))
        or not positive_int(run.get("run_attempt"))
        or run.get("id") != snapshot["expected_run_id"]
        or run.get("run_attempt") != snapshot["expected_attempt"]
        or run.get("head_sha") != expected
        or run_repo.get("full_name") != repo
    ):
        result["reason"] = (
            "Run repository, SHA, ID or attempt does not match the requested subject."
        )
        return result
    result["identity"] = {
        "repository": repo,
        "head_sha": expected,
        "run_id": run["id"],
        "run_attempt": run["run_attempt"],
    }
    if current != expected or snapshot.get("source_open") is False:
        return finish(
            "stale_source",
            "The source changed or its PR is no longer open.",
            "Use the current candidate's existing checks; do not retry this subject.",
        )
    if snapshot.get("source_open") is not True:
        result["reason"] = "Current source/PR eligibility was not established."
        return result
    if snapshot.get("active_duplicate") is not False:
        return finish(
            "duplicate_or_unknown",
            "An active duplicate exists or duplicate state is unknown.",
            "Read the current owner/run disposition; do not start a competing recovery.",
        )
    policy = snapshot.get("policy")
    if (
        not isinstance(policy, dict)
        or type(policy.get("recoveries_used")) is not int
        or policy["recoveries_used"] < 0
        or type(policy.get("retry_prohibited")) is not bool
        or type(policy.get("recovery_authorized")) is not bool
    ):
        result["reason"] = "Recovery history or explicit owner policy is unknown."
        return result
    rows = jobs.get("jobs")
    if (
        not isinstance(rows, list)
        or type(jobs.get("total_count")) is not int
        or jobs["total_count"] != len(rows)
        or jobs["total_count"] < 0
    ):
        result["reason"] = "Attempt job pagination is incomplete or malformed."
        return result
    names: set[str] = set()
    ids: set[int] = set()
    for job in rows:
        if not isinstance(job, dict):
            result["reason"] = "Malformed job record."
            return result
        name = job.get("name")
        if (
            not isinstance(name, str)
            or not name.strip()
            or name in names
            or not positive_int(job.get("id"))
            or job["id"] in ids
            or not positive_int(job.get("run_id"))
            or not positive_int(job.get("run_attempt"))
            or job.get("run_id") != run["id"]
            or job.get("run_attempt") != run["run_attempt"]
            or job.get("head_sha") != expected
            or not valid_state(job)
        ):
            result["reason"] = "Duplicate, inconsistent or wrong-attempt job evidence."
            return result
        names.add(name)
        ids.add(job["id"])
    status, conclusion = run.get("status"), run.get("conclusion")
    if not valid_state(run):
        result["reason"] = "Run status/conclusion is malformed."
        return result
    missing = sorted(set(required) - names)
    result["missing_required_jobs"] = missing
    failures = [
        j
        for j in rows
        if j["conclusion"]
        in {
            "failure",
            "timed_out",
            "action_required",
            "startup_failure",
            "stale",
        }
    ]
    result["failed_jobs"] = [
        {
            "id": j["id"],
            "name": j["name"],
            "conclusion": j["conclusion"],
        }
        for j in failures
    ]
    if status != "completed":
        return finish(
            "pending",
            "The workflow is still active.",
            "Wait on this run; preserve completed evidence.",
        )
    if any(j["status"] != "completed" for j in rows):
        result["reason"] = (
            "A completed workflow contains unfinished jobs; refresh evidence."
        )
        return result
    if conclusion == "startup_failure":
        return finish(
            "workflow_startup_failure",
            "The workflow itself could not start; passing or absent jobs do not establish a provider outage.",
            "Inspect workflow validation/the workflow file and provider status; do not retry an unchanged invalid workflow or propose job recovery.",
        )
    if conclusion == "cancelled" or any(j["conclusion"] == "cancelled" for j in rows):
        return finish(
            "cancelled",
            "Workflow or job was cancelled; cancellation is not success.",
            "Owner dispositions the cancellation; no blind retry.",
        )
    # Never reclassify an ordinary failed test or a timeout as a provider outage.
    if any(j["conclusion"] != "startup_failure" for j in failures):
        return finish(
            "job_failure",
            "A job failed, timed out or requires action; infrastructure cause is unproven.",
            "Inspect the exact failed job/step and correct its demonstrated cause; preserve passing evidence.",
        )
    skipped_parents = sorted(
        {
            job["name"]
            for job in rows
            if job["conclusion"] == "skipped"
            and any(
                name.startswith(job["name"] + " (") and name.endswith(")")
                for name in missing
            )
        }
    )
    if skipped_parents:
        return finish(
            "scope_skipped_required_jobs",
            "Required matrix contexts were not created behind skipped parents: "
            + ", ".join(skipped_parents),
            "Inspect change-scope/job if conditions and the existing required-context contract; a rerun with unchanged inputs cannot create these contexts. Keep the hold for Integrator's disposition.",
        )
    by_name = {j["name"]: j for j in rows}
    skipped = [
        x for x in required if x in by_name and by_name[x]["conclusion"] != "success"
    ]
    if not missing and not failures and not skipped and conclusion == "success":
        return finish(
            "ci_complete",
            "All supplied required jobs completed successfully.",
            "Return to the existing merge gate; this diagnostic grants no merge or product acceptance.",
        )
    if not failures and not missing:
        return finish(
            "incomplete_required_evidence",
            "A required job did not succeed, or the workflow result contradicts its jobs.",
            "Keep the hold and inspect the aggregate/workflow; do not publish a substitute green check.",
        )
    kind = "infrastructure_startup_failure" if failures else "missing_required_job"
    reason = (
        "GitHub reports startup_failure."
        if failures
        else "A required job has no execution record; executed siblings do not pay that gate."
    )
    action = "Integrator verifies provider cause and the exact candidate before selecting any recovery."
    if policy["retry_prohibited"]:
        action = "Existing no-retry directive takes precedence; return the exact hold to its owner."
    elif policy["recoveries_used"] >= 1:
        action = (
            "One recovery was already used; stop and return recurrence to Integrator."
        )
    elif not policy["recovery_authorized"]:
        action = "Integrator must explicitly authorize one diagnosed recovery; no execution is authorized by this report."
    elif missing:
        # Failed-jobs cannot recreate a job for which GitHub has no record.
        action = "Provider-supported whole-run recovery requires owner confirmation of infrastructure cause; failed-jobs recovery cannot target an absent job."
        if policy.get("provider_cause_confirmed") is True:
            result["proposed_command"] = [
                "gh",
                "run",
                "rerun",
                str(run["id"]),
                "--repo",
                repo,
            ]
    else:
        action = "Owner may use one failed-jobs recovery after a fresh identity/attempt/duplicate check; read back the required check afterward."
        result["proposed_command"] = [
            "gh",
            "run",
            "rerun",
            str(run["id"]),
            "--failed",
            "--repo",
            repo,
        ]
    return finish(kind, reason, action)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    try:
        if args.snapshot.stat().st_size > 8_000_000:
            raise ValueError("snapshot exceeds 8 MB")
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        result = disposition(snapshot)
    except (OSError, UnicodeError, ValueError) as error:
        result = disposition(None)
        result["reason"] = f"Snapshot unavailable: {error}"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result["classification"] in {"unknown", "duplicate_or_unknown"} else 0


if __name__ == "__main__":
    sys.exit(main())
