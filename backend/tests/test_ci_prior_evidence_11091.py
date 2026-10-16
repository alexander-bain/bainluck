"""Exact compose-push provenance and meaningful refusal controls; never dispatch CI."""

from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/ci-prior-evidence.py"
spec = importlib.util.spec_from_file_location("ci_prior_evidence_11091", SCRIPT)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
TEXT = (ROOT / ".github/workflows/ci.yml").read_text()
WORKFLOW = yaml.safe_load(TEXT)
JOBS = WORKFLOW["jobs"]
HEAD, TREE, BASE = "a" * 40, "b" * 40, "c" * 40
ENV = {
    "GITHUB_SHA": HEAD,
    "GITHUB_REPOSITORY_ID": "12",
    "GITHUB_EVENT_NAME": "push",
    "GITHUB_REF": "refs/heads/master",
    "GITHUB_RUN_ID": "200",
}
BRANCH = "integrator/compose-example"


def success(name):
    return {
        "id": abs(hash(name)),
        "name": name,
        "status": "completed",
        "conclusion": "success",
    }


def fixture():
    run = {
        "id": 100,
        "head_sha": HEAD,
        "head_branch": BRANCH,
        "event": "push",
        "path": evidence.WORKFLOW,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "repository": {"id": 12},
        "head_repository": {"id": 12},
        "updated_at": "2026-10-15T23:00:00Z",
    }
    jobs = []
    for name, (kind, value, count, _) in evidence.membership(TEXT).items():
        steps = []
        for step in JOBS[kind]["steps"]:
            condition = step.get("if", "")
            if condition == "needs.change-scope.outputs.reuse == 'true'":
                continue
            if kind == "backend-tests" and "Frontend-only" in step.get("name", ""):
                continue
            if (
                "matrix.group" in condition
                and f"matrix.group == '{value}'" not in condition
            ):
                continue
            if step.get("name") == "Validate prior exact-commit evidence":
                continue
            label = step.get("name", step.get("uses"))
            label = label.replace("${{ matrix.shard }}", str(value)).replace(
                "${{ strategy.job-total }}", str(count)
            )
            steps.append(success(label))
        jobs.append({**success(name), "steps": steps})
    jobs.extend(
        [
            {**success(name), "conclusion": "skipped", "steps": []}
            for name in ("deploy", "release-required")
        ]
    )
    checks = [
        {
            **success(name),
            "check_suite": {"id": 500},
            "app": {"id": app},
            "output": {"title": None},
        }
        for name, app in [
            ("CodeQL", 57789),
            ("Analyze (python)", 15368),
            ("Analyze (javascript-typescript)", 15368),
            ("gitleaks secret scan", 15368),
        ]
    ]
    checks.append(
        {
            **success("Analyze (python)"),
            "id": 999,
            "status": "in_progress",
            "conclusion": None,
            "check_suite": {"id": 501},
            "app": {"id": 15368},
            "output": {},
        }
    )
    provenance = {
        "schema": 2,
        "head": HEAD,
        "tree": TREE,
        "base": BASE,
        "repository_id": 12,
        "run_id": 100,
        "attempt": 1,
        "event": "push",
        "ref": f"refs/heads/{BRANCH}",
    }
    return FakeAPI(run, jobs, checks, provenance)


class FakeAPI:
    def __init__(self, run, jobs, checks, provenance):
        self.run, self.jobs, self.checks, self.provenance = (
            run,
            jobs,
            checks,
            provenance,
        )
        self.rows = [copy.deepcopy(run)]
        self.artifacts = [
            {
                "id": 700 + i,
                "name": f"compose-source-provenance-1-{identity}",
                "expired": False,
            }
            for i, identity in enumerate(
                evidence.provenance_ids(evidence.membership(TEXT))
            )
        ]
        self.identities = {
            artifact["id"]: artifact["name"].removeprefix(
                "compose-source-provenance-1-"
            )
            for artifact in self.artifacts
        }
        self.proof_overrides = {}
        self.suite_branch = BRANCH
        self.reread_move = False
        self.reads = 0

    def get(self, path):
        if path == "actions/runs/200":
            return {
                "created_at": "2026-10-15T23:01:00Z",
                "event": "push",
                "head_branch": "master",
                "head_sha": HEAD,
            }
        if path == "actions/runs/100":
            self.reads += 1
            result = copy.deepcopy(self.run)
            if self.reread_move and self.reads > 1:
                result["run_attempt"] += 1
            return result
        if path.startswith("check-suites/"):
            return {
                "head_sha": HEAD,
                "head_branch": "master" if path.endswith("501") else self.suite_branch,
            }
        raise AssertionError(path)

    def pages(self, path, key):
        if key == "workflow_runs":
            return self.rows
        if key == "jobs":
            return self.jobs
        if key == "artifacts":
            return self.artifacts
        if key == "check_runs":
            return self.checks
        raise AssertionError(path)

    def raw(self, path, limit):
        artifact_id = int(path.split("/")[-2])
        identity = self.identities[artifact_id]
        proof = {
            **self.provenance,
            "identity": identity,
            "job": (
                "backend-tests" if identity.startswith("backend-tests-") else identity
            ),
            **self.proof_overrides.get(identity, {}),
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("ci-provenance.json", json.dumps(proof))
        return buffer.getvalue()


def decide(api):
    return evidence.decide(api, ENV, TEXT, TREE, BASE)


def test_complete_exact_push_with_master_security_in_progress_is_accepted():
    result = decide(fixture())
    assert result == {
        "reuse": "true",
        "reuse_run": "100",
        "reuse_attempt": "1",
        "reuse_head": HEAD,
        "reuse_base": BASE,
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "pr_event",
        "synthetic_commit",
        "equal_tree_wrong_head",
        "base_moved",
        "wrong_tree",
        "foreign_repository",
        "old_attempt",
        "rerun_started",
        "source_not_success",
        "expired_run",
        "future_run",
        "duplicate_run",
        "missing_eighth_shard",
        "missing_fifth_database_group",
        "cancelled_job",
        "failed_job",
        "skipped_shard_tests",
        "skipped_database_tests",
        "missing_database_test",
        "skipped_verifier",
        "missing_artifact",
        "expired_artifact",
        "wrong_artifact_attempt",
        "wrong_artifact_run",
        "security_medium",
        "security_failure",
        "missing_security",
        "foreign_security_app",
        "unfinished_compose_security",
    ],
)
def test_uncertain_partial_or_refused_evidence_never_reuses(mutation):
    api = fixture()
    if mutation == "pr_event":
        api.rows[0]["event"] = "pull_request"
    elif mutation in ("synthetic_commit", "equal_tree_wrong_head"):
        api.provenance["head"] = "d" * 40
    elif mutation == "base_moved":
        api.provenance["base"] = "d" * 40
    elif mutation == "wrong_tree":
        api.provenance["tree"] = "d" * 40
    elif mutation == "foreign_repository":
        api.rows[0]["head_repository"]["id"] = 13
    elif mutation == "old_attempt":
        api.provenance["attempt"] = 2
    elif mutation == "rerun_started":
        api.reread_move = True
    elif mutation == "source_not_success":
        api.run["conclusion"] = "cancelled"
    elif mutation == "expired_run":
        api.run["updated_at"] = "2026-10-15T19:00:00Z"
    elif mutation == "future_run":
        api.run["updated_at"] = "2026-10-15T23:02:00Z"
    elif mutation == "duplicate_run":
        api.rows.append(copy.deepcopy(api.rows[0]))
    elif mutation.startswith("missing_") and mutation in (
        "missing_eighth_shard",
        "missing_fifth_database_group",
    ):
        name = (
            "backend-tests (8)"
            if mutation == "missing_eighth_shard"
            else "database-integration (shared-suffix)"
        )
        api.jobs = [j for j in api.jobs if j["name"] != name]
    elif mutation in ("cancelled_job", "failed_job"):
        api.jobs[0]["conclusion"] = (
            "cancelled" if mutation == "cancelled_job" else "failure"
        )
    elif mutation in ("skipped_database_tests", "missing_database_test"):
        job = next(j for j in api.jobs if j["name"] == "database-integration (shared)")
        step = next(s for s in job["steps"] if "real Postgres" in s["name"])
        if mutation == "missing_database_test":
            job["steps"].remove(step)
        else:
            step["conclusion"] = "skipped"
    elif mutation == "skipped_shard_tests":
        job = next(j for j in api.jobs if j["name"] == "backend-tests (8)")
        next(s for s in job["steps"] if s["name"].startswith("Run tests"))[
            "conclusion"
        ] = "skipped"
    elif mutation == "skipped_verifier":
        job = next(j for j in api.jobs if j["name"] == "shard-completeness")
        job["steps"][-1]["conclusion"] = "skipped"
    elif mutation == "missing_artifact":
        api.artifacts = []
    elif mutation == "expired_artifact":
        api.artifacts[0]["expired"] = True
    elif mutation == "wrong_artifact_attempt":
        api.artifacts[0]["name"] = "compose-source-provenance-2"
    elif mutation == "wrong_artifact_run":
        api.provenance["run_id"] = 101
    elif mutation == "security_medium":
        api.checks[0]["output"]["title"] = "5 medium security vulnerabilities"
    elif mutation == "security_failure":
        api.checks[0]["conclusion"] = "failure"
    elif mutation == "missing_security":
        api.checks.pop(0)
    elif mutation == "foreign_security_app":
        api.checks[0]["app"]["id"] = 999
    elif mutation == "unfinished_compose_security":
        api.checks[0]["status"] = "in_progress"
    else:
        raise AssertionError(mutation)
    with pytest.raises((ValueError, KeyError)):
        decide(api)


def test_projection_matches_yaml_all_eight_shards_and_five_db_groups():
    projection = evidence.membership(TEXT)
    assert {v[1] for v in projection.values() if v[0] == "backend-tests"} == {
        str(i) for i in JOBS["backend-tests"]["strategy"]["matrix"]["shard"]
    }
    assert {v[1] for v in projection.values() if v[0] == "database-integration"} == set(
        JOBS["database-integration"]["strategy"]["matrix"]["group"]
    )
    for name, (_, _, _, block) in projection.items():
        assert block
    assert len(projection) == 19


@pytest.mark.parametrize("mutation", ["short", "changed_total", "duplicate"])
def test_complete_pagination_refuses_inconsistent_snapshot(mutation):
    api = object.__new__(evidence.API)
    calls = []

    def get(path):
        calls.append(path)
        if mutation == "short":
            return {"total_count": 101, "rows": [{"id": 1}]}
        if len(calls) == 1:
            return {"total_count": 101, "rows": [{"id": i} for i in range(100)]}
        return {
            "total_count": 102 if mutation == "changed_total" else 101,
            "rows": [{"id": 0}],
        }

    api.get = get
    with pytest.raises(ValueError):
        api.pages("example", "rows")


def test_decision_interface_turns_exception_into_false_and_success_exit(tmp_path):
    event, output = tmp_path / "event.json", tmp_path / "output"
    event.write_text("{broken")
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env={"GITHUB_EVENT_PATH": str(event), "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert output.read_text() == "reuse=false\n"
    assert "running full CI" in result.stdout


@pytest.mark.parametrize("failure", [PermissionError, TimeoutError, KeyError])
def test_api_permission_timeout_or_shape_failure_takes_full_path(
    monkeypatch, tmp_path, failure
):
    output, event = tmp_path / "output", tmp_path / "event.json"
    event.write_text(json.dumps({"before": BASE}))
    for key, value in {
        **ENV,
        "GITHUB_OUTPUT": str(output),
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_REPOSITORY": "owner/repo",
        "GH_TOKEN": "do-not-log-this-token",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["ci-prior-evidence.py"])
    monkeypatch.setattr(evidence, "git", lambda *args: HEAD)

    def refused(*args):
        raise failure("do-not-log-this-token")

    monkeypatch.setattr(evidence, "API", refused)
    evidence.main()
    assert output.read_text() == "reuse=false\n"


def test_reuse_conditions_are_an_explicit_addition_to_every_paid_step():
    reuse = "needs.change-scope.outputs.reuse != 'true'"
    for name in (
        "backend-tests",
        "database-integration",
        "shard-completeness",
        "frontend-build",
    ):
        for step in JOBS[name]["steps"]:
            if step.get(
                "name"
            ) == "Reused exact-commit test evidence" or "Frontend-only" in step.get(
                "name", ""
            ):
                continue
            if step.get("name") in (
                "Record compose checkout provenance",
                "Publish compose checkout provenance",
            ):
                assert name == "backend-tests" and step["if"].startswith(
                    "needs.change-scope.outputs.scope != 'frontend' && " + reuse
                )
                continue
            assert step.get("if", "").endswith(reuse), (name, step)
    # Contract fixture work itself is never paid by reused credit.
    assert all(
        "reuse" not in step.get("if", "") for step in JOBS["e2e-contract"]["steps"]
    )


def test_unknown_db_condition_is_not_silently_excluded_from_coverage():
    api = fixture()
    bad = TEXT.replace(
        "matrix.group == 'shared' && needs.change-scope.outputs.reuse != 'true'",
        "matrix.group != 'isolated' && needs.change-scope.outputs.reuse != 'true'",
        1,
    )
    with pytest.raises(ValueError, match="unreviewed step condition"):
        evidence.decide(api, ENV, bad, TREE, BASE)


@pytest.mark.parametrize(
    "identity", [f"backend-tests-{i}" for i in range(1, 9)] + ["golden-baseline-floor"]
)
def test_each_history_reader_must_observe_the_recorded_master_A_not_later_B(identity):
    api = fixture()
    assert api.provenance["base"] == BASE
    api.proof_overrides[identity] = {"base": "d" * 40}
    with pytest.raises(ValueError, match="provenance source/base mismatch"):
        decide(api)


@pytest.mark.parametrize("identity", ["backend-tests-8", "golden-baseline-floor"])
def test_history_reader_cannot_borrow_change_scope_provenance(identity):
    api = fixture()
    api.artifacts = [a for a in api.artifacts if not a["name"].endswith("-" + identity)]
    with pytest.raises(ValueError, match="missing/ambiguous/expired provenance"):
        decide(api)


@pytest.mark.parametrize("job_name", ["frontend-build", "shard-completeness"])
@pytest.mark.parametrize(
    "mode", ["empty", "missing_executing_step", "only_one_named_step"]
)
def test_complete_named_execution_proof_is_required_not_all_empty(job_name, mode):
    api = fixture()
    job = next(j for j in api.jobs if j["name"] == job_name)
    if mode == "empty":
        job["steps"] = []
    elif mode == "only_one_named_step":
        job["steps"] = job["steps"][:1]
    else:
        job["steps"].pop()
    with pytest.raises(ValueError, match="unpaid executing step"):
        decide(api)


def test_provenance_is_captured_immediately_after_each_history_reader_checkout():
    for kind in ("backend-tests", "golden-baseline-floor"):
        steps = JOBS[kind]["steps"]
        checkout = next(
            i
            for i, step in enumerate(steps)
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        assert steps[checkout + 1]["name"] == "Record compose checkout provenance"
        assert steps[checkout + 2]["name"] == "Publish compose checkout provenance"


@pytest.mark.parametrize("index", range(4))
@pytest.mark.parametrize(
    "unpaid", ["cancelled", "timed_out", "skipped", "action_required", "neutral", None]
)
def test_old_security_success_cannot_pay_a_completed_unpaid_rerun(index, unpaid):
    api = fixture()
    rerun = copy.deepcopy(api.checks[index])
    rerun["id"] = 1000 + index
    rerun["conclusion"] = unpaid
    api.checks.append(rerun)
    with pytest.raises(ValueError, match="unpaid compose security check"):
        decide(api)


def test_all_old_security_successes_plus_all_cancelled_reruns_are_refused():
    api = fixture()
    for index in range(4):
        rerun = copy.deepcopy(api.checks[index])
        rerun["id"] = 1000 + index
        rerun["conclusion"] = "cancelled"
        api.checks.append(rerun)
    with pytest.raises(ValueError, match="unpaid compose security check"):
        decide(api)


@pytest.mark.parametrize("unpaid", ["missing", "skipped"])
def test_new_datagolf_execution_unit_cannot_borrow_the_shared_tail_green(unpaid):
    api = fixture()
    job = next(j for j in api.jobs if j["name"] == "database-integration (shared-tail)")
    name = "#994 a DataGolf bucket drill-in returns the rows the published chain admits (real Postgres)"
    step = next(s for s in job["steps"] if s["name"] == name)
    if unpaid == "missing":
        job["steps"].remove(step)
    else:
        step["conclusion"] = "skipped"
    with pytest.raises(ValueError, match="unpaid executing step"):
        decide(api)


@pytest.mark.parametrize(
    "job_name,unit_name",
    [
        (
            "database-integration (shared-tail)",
            "#1853 a settled Kalshi event's archived legs are graded by an attended, undoable repair (real Postgres)",
        ),
        (
            "database-integration (shared-tail)",
            "#2722 the nine archived Kalshi questions settle through an attended, undoable first repair (real Postgres)",
        ),
        (
            "database-integration (shared-suffix)",
            "#1911 the sentinel's events published aggregate is the curve's own admission (real Postgres)",
        ),
    ],
)
@pytest.mark.parametrize("unpaid", ["missing", "skipped"])
def test_new_master_execution_units_require_their_own_complete_proof(
    job_name, unit_name, unpaid
):
    api = fixture()
    job = next(j for j in api.jobs if j["name"] == job_name)
    step = next(s for s in job["steps"] if s["name"] == unit_name)
    if unpaid == "missing":
        job["steps"].remove(step)
    else:
        step["conclusion"] = "skipped"
    with pytest.raises(ValueError, match="unpaid executing step"):
        decide(api)
