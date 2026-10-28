"""Exact compose-push provenance and meaningful refusal controls; never dispatch CI."""

from __future__ import annotations

import copy
import base64
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
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
        self.security_run = {
            **copy.deepcopy(run),
            "id": 110,
            "path": evidence.CODEQL_WORKFLOW,
            "repository": {"id": 12, "full_name": "owner/repo"},
        }
        self.rows.append(copy.deepcopy(self.security_run))
        self.security_jobs = [
            {
                **success(f"Analyze ({language})"),
                "run_attempt": 1,
                "steps": [
                    {
                        **success(name),
                        "started_at": "2026-10-15T22:30:00Z",
                        "completed_at": "2026-10-15T22:59:00Z",
                    }
                    for name in ("Perform CodeQL Analysis", *SECURITY_STEPS)
                ],
            }
            for language in evidence.SECURITY_LANGUAGES
        ]
        self.security_artifacts = [
            {"id": 900 + i, "name": f"codeql-security-1-{language}", "expired": False}
            for i, language in enumerate(evidence.SECURITY_LANGUAGES)
        ]
        self.security_receipts = {
            language: {
                "schema": 1,
                "type": "codeql_security",
                "job": "analyze",
                "role": "compose",
                "repository": "owner/repo",
                "repository_id": 12,
                "head": HEAD,
                "tree": TREE,
                "base": BASE,
                "event": "push",
                "ref": f"refs/heads/{BRANCH}",
                "run_id": 110,
                "attempt": 1,
                "language": language,
                "category": "/language:" + language,
                "analysis_key": evidence.CODEQL_ANALYSIS_KEY,
                "environment": {"language": language},
                "analysis_id": 800 + i,
                "sarif_id": f"00000000-0000-0000-0000-{i+1:012d}",
                "results_count": 3,
                "rules_count": 3,
                "qualified": True,
                "qualification": "PASS",
                "delta": {"new_alert_ids": [], "new_qualifying_ids": []},
                "baseline": {
                    "head": BASE,
                    "run_id": 90,
                    "attempt": 1,
                    "analysis_id": 700 + i,
                    "sarif_id": f"00000000-0000-0000-0000-{i+3:012d}",
                    "selection": "legacy-window",
                },
            }
            for i, language in enumerate(evidence.SECURITY_LANGUAGES)
        }
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
        if path == "actions/runs/110":
            return copy.deepcopy(self.security_run)
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
        if path.startswith("actions/runs/110/"):
            return self.security_jobs if key == "jobs" else self.security_artifacts
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
        if artifact_id in (900, 901):
            language = evidence.SECURITY_LANGUAGES[artifact_id - 900]
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(
                    "codeql-security.json", json.dumps(self.security_receipts[language])
                )
            return buffer.getvalue()
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
        api.checks.pop(
            1
        )  # Official Analyze stays mandatory; PR-only summary may be absent.
    elif mutation == "foreign_security_app":
        api.checks[1]["app"]["id"] = 999
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


SECURITY_STEPS = (
    "Record CodeQL checkout provenance",
    "Qualify compose security or record master baseline",
    "Publish CodeQL security receipt",
)
SECURITY_CONDITION = (
    "github.event_name == 'push' && (github.ref == 'refs/heads/master' || "
    "startsWith(github.ref, 'refs/heads/integrator/compose-'))"
)
READINESS_STEP = "Wait for parent master CodeQL baseline"
READINESS_CONDITION = (
    "github.event_name == 'push' && "
    "startsWith(github.ref, 'refs/heads/integrator/compose-')"
)


def test_push_security_preserves_original_pr_and_scheduled_analysis_behavior():
    """No new producer runs on PR/schedule; all original scanner inputs survive."""
    original = yaml.safe_load(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(ROOT),
                "show",
                "6fe7d197f4d6289282461585e1adb71057b7fd38:.github/workflows/codeql.yml",
            ],
            text=True,
        )
    )
    current = yaml.safe_load((ROOT / ".github/workflows/codeql.yml").read_text())
    old_job, new_job = original["jobs"]["analyze"], current["jobs"]["analyze"]
    assert original.get("on", original.get(True)) == current.get(
        "on", current.get(True)
    )
    for key in ("name", "runs-on", "permissions", "strategy"):
        assert old_job[key] == new_job[key]

    def assert_original_steps(steps):
        kept = [
            s
            for s in steps
            if s["name"] not in SECURITY_STEPS
            and not (s["name"] == READINESS_STEP and s.get("if") == READINESS_CONDITION)
        ]
        assert len(kept) == len(old_job["steps"])
        for old, new in zip(old_job["steps"], kept):
            new = copy.deepcopy(new)
            if old["name"] == "Checkout":
                checkout_options = new.pop("with")
                assert checkout_options == {
                    "fetch-depth": "${{ github.event_name == 'push' && '0' || '1' }}"
                }
            if old["name"] == "Perform CodeQL Analysis":
                analysis_step_id = new.pop("id")
                assert analysis_step_id == "codeql_analysis"
            if old["name"] == "Initialize CodeQL":
                # #10090: the one added scanner input, exact value only.
                config_file = new["with"].pop("config-file")
                assert config_file == (
                    "${{ matrix.language == 'python' && "
                    "'./.github/codeql/codeql-config.yml' || '' }}"
                )
            assert new == old

    assert_original_steps(new_job["steps"])
    # The sole exact compose-only wait is excluded, never an arbitrary fifth
    # scanner step or a wait that could execute on PR/master/scheduled jobs.
    extra = copy.deepcopy(new_job["steps"])
    extra.append({"name": "Unreviewed additional scanner step", "run": "true"})
    with pytest.raises(AssertionError):
        assert_original_steps(extra)
    for changed in ({"name": "Renamed wait"}, {"if": SECURITY_CONDITION}):
        altered = copy.deepcopy(new_job["steps"])
        next(s for s in altered if s["name"] == READINESS_STEP).update(changed)
        with pytest.raises(AssertionError):
            assert_original_steps(altered)
    assert all(
        s["if"] == SECURITY_CONDITION
        for s in new_job["steps"]
        if s["name"] in SECURITY_STEPS
    )


def test_security_qualification_and_receipt_publish_follow_paid_analysis():
    steps = yaml.safe_load((ROOT / ".github/workflows/codeql.yml").read_text())["jobs"][
        "analyze"
    ]["steps"]
    names = [s["name"] for s in steps]
    assert names.index(SECURITY_STEPS[0]) == names.index("Checkout") + 1
    assert names.count(READINESS_STEP) == 1
    assert names.index(READINESS_STEP) == names.index("Perform CodeQL Analysis") + 1
    assert steps[names.index(READINESS_STEP)]["if"] == READINESS_CONDITION
    assert names.index(SECURITY_STEPS[1]) == names.index(READINESS_STEP) + 1
    assert names.index(SECURITY_STEPS[2]) == names.index(SECURITY_STEPS[1]) + 1
    qualifier = steps[names.index(SECURITY_STEPS[1])]
    assert (
        qualifier["env"]["SECURITY_SARIF_ID"]
        == "${{ steps.codeql_analysis.outputs.sarif-id }}"
    )
    assert "${{" not in qualifier["run"]
    assert '--sarif-id "$SECURITY_SARIF_ID"' in qualifier["run"]
    publish = steps[names.index(SECURITY_STEPS[2])]
    assert publish["with"]["if-no-files-found"] == "error"
    assert (
        publish["with"]["name"]
        == "codeql-security-${{ github.run_attempt }}-${{ matrix.language }}"
    )
    assert publish["with"]["path"] == "codeql-security.json"


ANALYSES_PATH = (
    "code-scanning/analyses?ref=refs%2Fheads%2Fmaster&sort=created&direction=desc"
)


def array_api(monkeypatch, pages):
    api = evidence.API("owner/repo", "offline-test-token")
    calls = []

    def response(path, *args):
        calls.append(path)
        index = len(calls) - 1
        assert index < len(pages), "unexpected extra pagination request"
        rows, headers = pages[index]
        return json.dumps(rows).encode(), headers

    monkeypatch.setattr(api, "_response", response)
    return api, calls


def analysis_row(identity, created="2026-10-16T05:30:00Z"):
    return {"id": identity, "created_at": created}


def next_analysis_link(page):
    return (
        "<https://api.github.com/repos/owner/repo/"
        + ANALYSES_PATH
        + f'&per_page=100&page={page}>; rel="next"'
    )


def test_bootstrap_consumes_timestamp_ties_until_strictly_older_watermark(monkeypatch):
    tie = "2026-10-16T05:30:00Z"
    api, calls = array_api(
        monkeypatch,
        [
            ([analysis_row(1, tie)], {"Link": next_analysis_link(2)}),
            ([analysis_row(2, tie)], {"Link": next_analysis_link(3)}),
            (
                [analysis_row(3, "2026-10-16T05:29:59Z")],
                {"Link": next_analysis_link(4)},
            ),
        ],
    )
    assert [r["id"] for r in api.array_pages(ANALYSES_PATH, older_than=tie)] == [
        1,
        2,
        3,
    ]
    assert len(calls) == 3


@pytest.mark.parametrize(
    "bound,linked,accepted", [(12, 12, True), (12, 13, False), (None, 12, False)]
)
def test_numeric_github_pagination_route_requires_authenticated_exact_repository(
    monkeypatch, bound, linked, accepted
):
    link = next_analysis_link(2).replace(
        "/repos/owner/repo/", f"/repositories/{linked}/"
    )
    api, calls = array_api(
        monkeypatch, [([analysis_row(1)], {"Link": link}), ([analysis_row(2)], {})]
    )
    if bound is not None:
        api.bind_repository({"id": bound, "full_name": "owner/repo"})
    if accepted:
        assert len(api.array_pages(ANALYSES_PATH)) == 2
        assert all(path.startswith("code-scanning/analyses?") for path in calls)
    else:
        with pytest.raises(ValueError, match="untrusted or changed pagination link"):
            api.array_pages(ANALYSES_PATH)


@pytest.mark.parametrize(
    "mutant",
    [
        "different-host",
        "different-path",
        "changed-ref",
        "repeated-page",
        "duplicate-next",
        "malformed-link",
        "duplicate-id",
        "ascending-time",
        "empty-successor",
        "watermark-unreachable",
    ],
)
def test_analysis_pagination_mutants_cannot_claim_complete_clean_history(
    monkeypatch, mutant
):
    first = ([analysis_row(1)], {"Link": next_analysis_link(2)})
    pages = [first, ([analysis_row(2, "2026-10-16T05:29:59Z")], {})]
    if mutant == "different-host":
        first[1]["Link"] = next_analysis_link(2).replace(
            "api.github.com", "example.invalid"
        )
    elif mutant == "different-path":
        first[1]["Link"] = next_analysis_link(2).replace("owner/repo/", "other/repo/")
    elif mutant == "changed-ref":
        first[1]["Link"] = next_analysis_link(2).replace("master", "feature")
    elif mutant == "repeated-page":
        first[1]["Link"] = next_analysis_link(1)
    elif mutant == "duplicate-next":
        first[1]["Link"] += ", " + next_analysis_link(2)
    elif mutant == "malformed-link":
        first[1]["Link"] = next_analysis_link(2).replace('rel="next"', "rel=next")
    elif mutant == "duplicate-id":
        pages[1][0][0]["id"] = 1
    elif mutant == "ascending-time":
        pages[1][0][0]["created_at"] = "2026-10-16T05:31:00Z"
    elif mutant == "empty-successor":
        pages[0] = ([], first[1])
    elif mutant == "watermark-unreachable":
        pages = [
            ([analysis_row(i)], {"Link": next_analysis_link(i + 1)})
            for i in range(1, 21)
        ]
    api, _ = array_api(monkeypatch, pages)
    with pytest.raises(ValueError):
        api.array_pages(ANALYSES_PATH, older_than="2026-10-16T05:30:00Z")


def test_sarif_larger_byte_bound_is_endpoint_specific(monkeypatch):
    api = evidence.API("owner/repo", "offline-test-token")
    calls = []

    def response(path, limit=2_000_000, accept="application/vnd.github+json"):
        calls.append((path, limit, accept))
        return b"{}", {}

    monkeypatch.setattr(api, "_response", response)
    api.sarif("code-scanning/analyses/123")
    api.get("actions/runs/123")
    assert evidence.SARIF_MAX_BYTES >= 2 * 3_540_000
    assert calls == [
        (
            "code-scanning/analyses/123",
            evidence.SARIF_MAX_BYTES,
            "application/sarif+json",
        ),
        ("actions/runs/123", 2_000_000, "application/vnd.github+json"),
    ]
    with pytest.raises(ValueError):
        api.sarif("actions/runs/123")


@pytest.mark.parametrize("endpoint", ["sarif", "ordinary"])
def test_oversized_evidence_response_refuses_instead_of_truncating(endpoint):
    api = evidence.API("owner/repo", "offline-test-token")

    class OversizeResponse:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b" " * limit

    api.opener = SimpleNamespace(open=lambda request, timeout: OversizeResponse())
    with pytest.raises(ValueError, match="oversize evidence response"):
        if endpoint == "sarif":
            api.sarif("code-scanning/analyses/123")
        else:
            api.raw("actions/runs/123")


def security_snapshot_fixture():
    metadata = {
        "commit_sha": HEAD,
        "ref": f"refs/heads/{BRANCH}",
        "tool": {"name": "CodeQL", "version": "2.27.2"},
        "category": "/language:python",
        "rules_count": 3,
        "results_count": 3,
    }
    driver = {
        "name": "CodeQL",
        "semanticVersion": "2.27.2",
        "rules": [
            {"id": "style", "defaultConfiguration": {"level": "warning"}},
        ],
    }
    extension = {
        "name": "python-queries",
        "rules": [
            {
                "id": "medium",
                "properties": {"security-severity": "4.0", "tags": ["security"]},
            },
            {"id": "error", "defaultConfiguration": {"level": "error"}},
        ],
    }
    results = []
    for aid, rule, index, component in (
        (11, "medium", 0, 0),
        (12, "error", 1, 0),
        (13, "style", 0, None),
    ):
        reference = {"id": rule, "index": index}
        if component is not None:
            reference["toolComponent"] = {"index": component}
        results.append(
            {
                "ruleId": rule,
                "rule": reference,
                "properties": {
                    "github/alertNumber": aid,
                    "github/alertUrl": f"https://api.github.com/repos/owner/repo/code-scanning/alerts/{aid}",
                },
            }
        )
    return {
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": driver, "extensions": [extension]},
                "automationDetails": {"id": "/language:python/"},
                "versionControlProvenance": [
                    {
                        "revisionId": HEAD,
                        "branch": metadata["ref"],
                        "repositoryUri": "https://github.com/owner/repo",
                    }
                ],
                "results": results,
            }
        ],
    }, metadata


def parse_security(sarif, metadata):
    return evidence.parse_security_snapshot(sarif, metadata, "owner/repo")


def test_inherited_security_and_error_findings_are_retained_without_being_called_new():
    sarif, metadata = security_snapshot_fixture()
    snapshot = parse_security(sarif, metadata)
    assert snapshot["qualifying_ids"] == [11, 12]
    assert evidence.compare_security_snapshots(snapshot, copy.deepcopy(snapshot)) == {
        "new_alert_ids": [],
        "new_qualifying_ids": [],
    }


@pytest.mark.parametrize("mutant", ["new-medium", "new-error", "reintroduced-medium"])
def test_new_or_reintroduced_native_qualifying_alert_fails_before_master_push(mutant):
    sarif, metadata = security_snapshot_fixture()
    if mutant == "reintroduced-medium":
        candidate = parse_security(sarif, metadata)
        sarif["runs"][0]["results"].pop(0)
        metadata["results_count"] -= 1
        with pytest.raises(evidence.NewFinding):
            evidence.compare_security_snapshots(
                parse_security(sarif, metadata), candidate
            )
        return
    original = parse_security(sarif, metadata)
    candidate = copy.deepcopy(sarif)
    index = 1 if mutant == "new-error" else 0
    candidate["runs"][0]["results"][index]["properties"]["github/alertNumber"] = 99
    candidate["runs"][0]["results"][index]["properties"][
        "github/alertUrl"
    ] = "https://api.github.com/repos/owner/repo/code-scanning/alerts/99"
    # An old global ID absent from this exact baseline is deliberately indistinguishable
    # from a new ID: both are newly appearing relative to the admitted source.
    with pytest.raises(evidence.NewFinding):
        evidence.compare_security_snapshots(
            original, parse_security(candidate, metadata)
        )


def test_new_nonqualifying_note_is_not_mislabeled_as_security_failure():
    sarif, metadata = security_snapshot_fixture()
    base = parse_security(sarif, metadata)
    result = copy.deepcopy(sarif["runs"][0]["results"][2])
    result["properties"] = {"github/alertNumber": 99}
    sarif["runs"][0]["results"].append(result)
    metadata["results_count"] += 1
    assert evidence.compare_security_snapshots(base, parse_security(sarif, metadata))[
        "new_alert_ids"
    ] == [99]


@pytest.mark.parametrize(
    "mutant",
    [
        "missing-native-id",
        "duplicate-native-id",
        "foreign-alert-url",
        "unknown-rule",
        "wrong-extension-index",
        "wrong-rule-index",
        "missing-results",
        "missing-rules",
        "wrong-revision",
        "wrong-ref",
        "wrong-repository",
        "wrong-category",
        "wrong-version",
        "nonfinite-score",
        "invalid-score-type",
        "missing-security-score",
        "unknown-level",
        "conflicting-legacy-rule-index",
    ],
)
def test_incomplete_or_ambiguous_sarif_cannot_qualify_security(mutant):
    sarif, metadata = security_snapshot_fixture()
    run = sarif["runs"][0]
    result = run["results"][0]
    if mutant == "missing-native-id":
        del result["properties"]["github/alertNumber"]
    elif mutant == "duplicate-native-id":
        result["properties"]["github/alertNumber"] = 12
    elif mutant == "foreign-alert-url":
        result["properties"]["github/alertUrl"] = "https://example.invalid/11"
    elif mutant == "unknown-rule":
        result["ruleId"] = "missing"
    elif mutant == "wrong-extension-index":
        result["rule"]["toolComponent"]["index"] = 5
    elif mutant == "wrong-rule-index":
        result["rule"]["index"] = 1
    elif mutant == "missing-results":
        run["results"].pop()
    elif mutant == "missing-rules":
        run["tool"]["extensions"][0]["rules"].pop()
    elif mutant == "wrong-revision":
        run["versionControlProvenance"][0]["revisionId"] = BASE
    elif mutant == "wrong-ref":
        run["versionControlProvenance"][0]["branch"] = "refs/heads/master"
    elif mutant == "wrong-repository":
        run["versionControlProvenance"][0][
            "repositoryUri"
        ] = "https://github.com/other/repo"
    elif mutant == "wrong-category":
        run["automationDetails"]["id"] = "/language:javascript/"
    elif mutant == "wrong-version":
        sarif["version"] = "2.0.0"
    elif mutant == "nonfinite-score":
        run["tool"]["extensions"][0]["rules"][0]["properties"][
            "security-severity"
        ] = "nan"
    elif mutant == "invalid-score-type":
        run["tool"]["extensions"][0]["rules"][0]["properties"][
            "security-severity"
        ] = True
    elif mutant == "missing-security-score":
        del run["tool"]["extensions"][0]["rules"][0]["properties"]["security-severity"]
    elif mutant == "unknown-level":
        result["level"] = "unknown"
    elif mutant == "conflicting-legacy-rule-index":
        result["ruleIndex"] = 99
    with pytest.raises((ValueError, KeyError)):
        parse_security(sarif, metadata)


@pytest.mark.parametrize(
    "mutant", ["tool-change", "query-change", "inherited-classification-change"]
)
def test_changed_security_profile_is_unknown_not_a_borrowed_clean_baseline(mutant):
    sarif, metadata = security_snapshot_fixture()
    base = parse_security(sarif, metadata)
    sarif, metadata = copy.deepcopy(sarif), copy.deepcopy(metadata)
    if mutant == "tool-change":
        sarif["runs"][0]["tool"]["driver"]["semanticVersion"] = "2.28.0"
        metadata["tool"]["version"] = "2.28.0"
    elif mutant == "query-change":
        sarif["runs"][0]["tool"]["extensions"][0]["rules"][0]["properties"][
            "security-severity"
        ] = "5.0"
    else:
        sarif["runs"][0]["results"][0]["level"] = "error"
    with pytest.raises(ValueError):
        evidence.compare_security_snapshots(base, parse_security(sarif, metadata))


def test_real_push_security_needs_no_pr_only_summary_check():
    api = fixture()
    api.checks = [c for c in api.checks if c["name"] != "CodeQL"]
    assert decide(api)["reuse"] == "true"


@pytest.mark.parametrize(
    "mutant",
    [
        "missing-language",
        "expired-receipt",
        "duplicate-receipt",
        "old-artifact-attempt",
        "receipt-head",
        "receipt-tree",
        "receipt-base",
        "receipt-run",
        "receipt-attempt",
        "receipt-language",
        "receipt-repository",
        "receipt-upload",
        "receipt-baseline-head",
        "receipt-unqualified",
        "receipt-has-new-finding",
        "source-cancelled",
        "source-running",
        "source-attempt-moved",
        "source-completed-after-master-push",
        "partial-language-job",
        "skipped-qualifier",
        "missing-publish",
    ],
)
def test_unpaid_security_receipt_or_attempt_cannot_borrow_complete_test_green(mutant):
    api = fixture()
    receipt = api.security_receipts["python"]
    if mutant == "missing-language":
        api.security_artifacts.pop()
    elif mutant == "expired-receipt":
        api.security_artifacts[0]["expired"] = True
    elif mutant == "duplicate-receipt":
        api.security_artifacts.append(copy.deepcopy(api.security_artifacts[0]))
    elif mutant == "old-artifact-attempt":
        api.security_artifacts[0]["name"] = "codeql-security-0-python"
    elif mutant == "receipt-head":
        receipt["head"] = BASE
    elif mutant == "receipt-tree":
        receipt["tree"] = BASE
    elif mutant == "receipt-base":
        receipt["base"] = HEAD
    elif mutant == "receipt-run":
        receipt["run_id"] = 111
    elif mutant == "receipt-attempt":
        receipt["attempt"] = 2
    elif mutant == "receipt-language":
        receipt["language"] = "javascript-typescript"
    elif mutant == "receipt-repository":
        receipt["repository"] = "other/repo"
    elif mutant == "receipt-upload":
        receipt["sarif_id"] = "unknown"
    elif mutant == "receipt-baseline-head":
        receipt["baseline"]["head"] = HEAD
    elif mutant == "receipt-unqualified":
        receipt["qualified"] = False
    elif mutant == "receipt-has-new-finding":
        receipt["delta"]["new_qualifying_ids"] = [99]
    elif mutant == "source-cancelled":
        api.security_run["conclusion"] = "cancelled"
    elif mutant == "source-running":
        api.security_run["status"] = "in_progress"
    elif mutant == "source-attempt-moved":
        api.security_run["run_attempt"] = 2
    elif mutant == "source-completed-after-master-push":
        api.security_run["updated_at"] = "2026-10-15T23:02:00Z"
    elif mutant == "partial-language-job":
        api.security_jobs.pop()
    elif mutant == "skipped-qualifier":
        next(
            s for s in api.security_jobs[0]["steps"] if s["name"] == SECURITY_STEPS[1]
        )["conclusion"] = "skipped"
    elif mutant == "missing-publish":
        api.security_jobs[0]["steps"] = [
            s for s in api.security_jobs[0]["steps"] if s["name"] != SECURITY_STEPS[2]
        ]
    with pytest.raises((ValueError, KeyError)):
        decide(api)


@pytest.mark.parametrize(
    "role,outcome",
    [
        ("compose", "unknown"),
        ("master", "unknown"),
        ("compose", "new-finding"),
    ],
)
def test_security_cli_failure_is_visible_nonzero_and_removes_stale_pass(
    monkeypatch, tmp_path, capsys, role, outcome
):
    proof = tmp_path / "provenance.json"
    proof.write_text("{}")
    output = tmp_path / "codeql-security.json"
    output.write_text('{"qualified":true}')
    monkeypatch.setenv(
        "GITHUB_REF",
        "refs/heads/master" if role == "master" else f"refs/heads/{BRANCH}",
    )
    monkeypatch.setenv("GITHUB_RUN_ID", "110")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "offline-test-token")
    if role == "master":
        event = tmp_path / "push.json"
        event.write_text(
            json.dumps({"before": BASE, "after": HEAD, "ref": "refs/heads/master"})
        )
        monkeypatch.setenv("GITHUB_SHA", HEAD)
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setattr(evidence, "API", lambda *args: object())

    def refuse(*args):
        raise (
            evidence.NewFinding("99")
            if outcome == "new-finding"
            else ValueError("incomplete")
        )

    monkeypatch.setattr(evidence, "qualify_security", refuse)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--security-qualify",
            str(proof),
            "--security-output",
            str(output),
            "--sarif-id",
            "00000000-0000-0000-0000-000000000001",
            "--language",
            "python",
        ],
    )
    with pytest.raises(SystemExit) as result:
        evidence.main()
    assert result.value.code == 1
    assert not output.exists()
    text = capsys.readouterr().out
    assert (
        "SECURITY NEW-FINDING" in text
        if outcome == "new-finding"
        else "SECURITY EVIDENCE INCOMPLETE" in text
    )
    if outcome == "unknown":
        assert "fresh full attempt" in text
        assert "Re-run ALL jobs" in text
        assert "historical failed checks still force full master CI" in text
        assert "Never re-stamp the same tree" in text
        assert "UNKNOWN again, do not land" in text
        assert "reviewed fix or revert" in text
        assert f"exact {role} CodeQL run 110" in text
        assert (
            "legacy bootstrap" in text
            if role == "master"
            else "full test run does not clear" in text
        )
    else:
        assert "new exact candidate" in text
    assert "offline-test-token" not in text


@pytest.mark.parametrize(
    "mutant",
    [
        "wrong-upload",
        "wrong-head",
        "wrong-ref",
        "wrong-key",
        "wrong-category",
        "wrong-environment",
        "wrong-tool",
        "processing-error",
        "processing-warning",
        "missing-rules",
        "negative-results",
        "invalid-created-time",
    ],
)
def test_unqualified_analysis_identity_or_processing_never_pays_security(mutant):
    _, metadata = security_snapshot_fixture()
    upload = "00000000-0000-0000-0000-000000000001"
    metadata.update(
        {
            "id": 123,
            "sarif_id": upload,
            "analysis_key": evidence.CODEQL_ANALYSIS_KEY,
            "environment": '{"language":"python"}',
            "error": "",
            "warning": "",
            "created_at": "2026-10-16T05:30:00Z",
        }
    )
    if mutant == "wrong-upload":
        metadata["sarif_id"] = "00000000-0000-0000-0000-000000000002"
    elif mutant == "wrong-head":
        metadata["commit_sha"] = BASE
    elif mutant == "wrong-ref":
        metadata["ref"] = "refs/heads/master"
    elif mutant == "wrong-key":
        metadata["analysis_key"] = ".github/workflows/other.yml:analyze"
    elif mutant == "wrong-category":
        metadata["category"] = "/language:other"
    elif mutant == "wrong-environment":
        metadata["environment"] = '{"language":"swift"}'
    elif mutant == "wrong-tool":
        metadata["tool"]["name"] = "other"
    elif mutant == "processing-error":
        metadata["error"] = "incomplete"
    elif mutant == "processing-warning":
        metadata["warning"] = "partial extraction"
    elif mutant == "missing-rules":
        metadata["rules_count"] = 0
    elif mutant == "negative-results":
        metadata["results_count"] = -1
    elif mutant == "invalid-created-time":
        metadata["created_at"] = "not-a-time"
    with pytest.raises(ValueError):
        evidence._validate_analysis(
            metadata, HEAD, f"refs/heads/{BRANCH}", "python", sarif_id=upload
        )


@pytest.mark.parametrize(
    "mutant",
    ["pull-request", "schedule", "other-branch", "other-job", "other-language"],
)
def test_security_provenance_is_exclusive_to_official_master_or_compose_push(
    monkeypatch, mutant
):
    env = {
        **ENV,
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_JOB": "analyze",
        "GITHUB_REF": f"refs/heads/{BRANCH}",
    }
    language = "python"
    monkeypatch.setattr(
        evidence,
        "git",
        lambda *args: (
            TREE
            if args[-1] == "HEAD^{tree}"
            else BASE if args[-1] == "origin/master" else HEAD
        ),
    )
    monkeypatch.setattr(
        evidence.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    if mutant == "pull-request":
        env["GITHUB_EVENT_NAME"] = "pull_request"
    elif mutant == "schedule":
        env["GITHUB_EVENT_NAME"] = "schedule"
    elif mutant == "other-branch":
        env["GITHUB_REF"] = "refs/heads/feature"
    elif mutant == "other-job":
        env["GITHUB_JOB"] = "backend-tests"
    elif mutant == "other-language":
        language = "swift"
    with pytest.raises(ValueError):
        evidence.security_record(env, language)


class BaseSecurityAPI:
    """Complete tiny official run/snapshot specimen; no network or policy stubs."""

    def __init__(self, declared=False):
        self.deadline = evidence.time.monotonic() + 75
        source = fixture()
        self.run = {
            **source.security_run,
            "id": 90,
            "head_sha": BASE,
            "head_branch": "master",
        }
        self.runs = [copy.deepcopy(self.run)]
        self.jobs = copy.deepcopy(source.security_jobs)
        if not declared:
            for job in self.jobs:
                job["steps"] = [
                    s for s in job["steps"] if s["name"] == "Perform CodeQL Analysis"
                ]
        text = (
            (ROOT / ".github/workflows/codeql.yml").read_text()
            if declared
            else "name: CodeQL\n"
        )
        self.content = {
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(text.encode()).decode(),
        }
        self.metadata, self.snapshots = {}, {}
        for index, language in enumerate(evidence.SECURITY_LANGUAGES):
            sarif, meta = security_snapshot_fixture()
            meta.update(
                {
                    "id": 500 + index,
                    "sarif_id": f"00000000-0000-0000-0000-{index+1:012d}",
                    "commit_sha": BASE,
                    "ref": "refs/heads/master",
                    "analysis_key": evidence.CODEQL_ANALYSIS_KEY,
                    "category": "/language:" + language,
                    "environment": json.dumps({"language": language}),
                    "error": "",
                    "warning": "",
                    "created_at": "2026-10-15T22:45:00Z",
                }
            )
            run = sarif["runs"][0]
            run["automationDetails"]["id"] = meta["category"]
            run["versionControlProvenance"][0].update(
                {"revisionId": BASE, "branch": "refs/heads/master"}
            )
            self.metadata[meta["id"]] = meta
            self.snapshots[meta["id"]] = sarif
        self.history = list(copy.deepcopy(self.metadata).values())
        self.array_calls = 0
        self.reads = 0
        self.move_after_read = False

    def pages(self, path, key):
        if key == "workflow_runs":
            return copy.deepcopy(self.runs)
        if key == "jobs":
            return copy.deepcopy(self.jobs)
        if key == "artifacts":
            return []
        raise AssertionError(path)

    def get(self, path):
        if path.startswith("contents/"):
            return copy.deepcopy(self.content)
        if path.startswith("actions/runs/"):
            self.reads += 1
            value = copy.deepcopy(self.run)
            if self.move_after_read and self.reads > 1:
                value["run_attempt"] += 1
            return value
        if path.startswith("code-scanning/analyses/"):
            return copy.deepcopy(self.metadata[int(path.split("/")[-1])])
        raise AssertionError(path)

    def array_pages(self, path, *, older_than=None):
        self.array_calls += 1
        assert older_than == "2026-10-15T22:30:00Z"
        return copy.deepcopy(self.history)

    def sarif(self, path):
        return copy.deepcopy(self.snapshots[int(path.split("/")[-1])])


def test_legacy_bootstrap_requires_the_exact_official_base_window_and_both_languages():
    api = BaseSecurityAPI()
    selected = evidence.select_base_security(api, BASE, 12, "python")
    assert selected["selection"] == "legacy-window"
    assert selected["run"]["id"] == 90
    assert selected["snapshot"]["qualifying_ids"] == [11, 12]
    assert api.array_calls == 1


@pytest.mark.parametrize(
    "mutant",
    [
        "missing-language",
        "duplicate-analysis",
        "outside-step-window",
        "wrong-analysis-key",
        "failed-processing",
        "missing-job",
        "skipped-analysis",
        "cancelled-run",
        "ambiguous-run",
        "stale-attempt",
        "attempt-moves-on-reread",
    ],
)
def test_legacy_bootstrap_mutants_never_pay_an_unknown_baseline(mutant):
    api = BaseSecurityAPI()
    if mutant == "missing-language":
        api.history.pop()
    elif mutant == "duplicate-analysis":
        api.history.append(copy.deepcopy(api.history[0]))
    elif mutant == "outside-step-window":
        api.history[0]["created_at"] = "2026-10-15T23:30:00Z"
    elif mutant == "wrong-analysis-key":
        api.history[0]["analysis_key"] = "other:analyze"
    elif mutant == "failed-processing":
        api.history[0]["error"] = "incomplete"
    elif mutant == "missing-job":
        api.jobs.pop()
    elif mutant == "skipped-analysis":
        api.jobs[0]["steps"][0]["conclusion"] = "skipped"
    elif mutant == "cancelled-run":
        api.run["conclusion"] = "cancelled"
    elif mutant == "ambiguous-run":
        api.runs.append(copy.deepcopy(api.runs[0]))
    elif mutant == "stale-attempt":
        api.run["run_attempt"] = 2
    elif mutant == "attempt-moves-on-reread":
        api.move_after_read = True
    with pytest.raises(ValueError):
        evidence.select_base_security(api, BASE, 12, "python")


def test_declared_producer_missing_receipts_never_escapes_into_legacy_bootstrap():
    api = BaseSecurityAPI(declared=True)
    with pytest.raises(evidence.SecurityIncomplete) as result:
        evidence.select_base_security(api, BASE, 12, "python")
    assert api.array_calls == 0
    assert "exact master CodeQL run 90" in result.value.recovery
    assert "fresh full attempt" in result.value.recovery


class ComposeSecurityAPI(BaseSecurityAPI):
    def __init__(self, language="python", attempt=1):
        super().__init__()
        self.current = {
            **self.run,
            "id": 110,
            "head_sha": HEAD,
            "head_branch": BRANCH,
            "run_attempt": attempt,
            "status": "in_progress",
            "conclusion": None,
        }
        index = evidence.SECURITY_LANGUAGES.index(language)
        self.candidate = copy.deepcopy(self.metadata[500 + index])
        self.candidate.update(
            {
                "id": 600 + index,
                "commit_sha": HEAD,
                "ref": f"refs/heads/{BRANCH}",
                "sarif_id": f"00000000-0000-0000-0000-{index+7:012d}",
            }
        )
        self.metadata[600 + index] = self.candidate
        sarif = copy.deepcopy(self.snapshots[500 + index])
        sarif["runs"][0]["versionControlProvenance"][0].update(
            {"revisionId": HEAD, "branch": f"refs/heads/{BRANCH}"}
        )
        self.snapshots[600 + index] = sarif
        self.env = {
            **ENV,
            "GITHUB_RUN_ID": "110",
            "GITHUB_RUN_ATTEMPT": str(attempt),
            "GITHUB_REF": f"refs/heads/{BRANCH}",
            "GITHUB_JOB": "analyze",
            "GITHUB_REPOSITORY": "owner/repo",
        }
        self.proof = {
            **evidence._security_context(self.env, language),
            "tree": TREE,
            "base": BASE,
        }
        self.language = language
        self.current_jobs = copy.deepcopy(self.jobs)
        for index, job in enumerate(self.current_jobs):
            job["id"] = 800 + index
            job["run_attempt"] = attempt
            for number, step in enumerate(job["steps"], 6):
                step["number"] = number

    def get(self, path):
        if path == "actions/runs/110":
            return copy.deepcopy(self.current)
        return super().get(path)

    def pages(self, path, key):
        if path.startswith("actions/runs/110/") and key == "jobs":
            return copy.deepcopy(self.current_jobs)
        return super().pages(path, key)

    def array_pages(self, path, *, older_than=None):
        if "sarif_id=" in path:
            return [copy.deepcopy(self.candidate)]
        return super().array_pages(path, older_than=older_than)

    def qualify(self):
        return evidence.qualify_security(
            self, self.env, self.proof, self.candidate["sarif_id"], self.language
        )


def test_complete_compose_producer_emits_source_bound_qualified_receipt():
    api = ComposeSecurityAPI()
    receipt = api.qualify()
    assert receipt["qualified"] is True
    assert receipt["qualification"] == "PASS"
    assert (
        receipt["head"] == HEAD and receipt["tree"] == TREE and receipt["base"] == BASE
    )
    assert receipt["baseline"]["run_id"] == 90
    assert receipt["baseline"]["selection"] == "legacy-window"


@pytest.mark.parametrize(
    "mutant",
    [
        "wrong-checkout-base",
        "wrong-checkout-head",
        "stale-provenance-attempt",
        "wrong-current-head",
        "wrong-upload",
        "new-finding",
        "upload-outside-current-step",
        "skipped-current-analysis",
        "old-current-job-attempt",
    ],
)
def test_producer_context_and_native_findings_cannot_become_passing_receipts(mutant):
    api = ComposeSecurityAPI()
    if mutant == "wrong-checkout-base":
        api.proof["base"] = "unknown"
    elif mutant == "wrong-checkout-head":
        api.proof["head"] = BASE
    elif mutant == "stale-provenance-attempt":
        api.proof["attempt"] = 2
    elif mutant == "wrong-current-head":
        api.current["head_sha"] = BASE
    elif mutant == "wrong-upload":
        api.candidate["sarif_id"] = "unknown"
    elif mutant == "new-finding":
        result = api.snapshots[600]["runs"][0]["results"][0]
        result["properties"] = {"github/alertNumber": 99}
    elif mutant == "upload-outside-current-step":
        api.candidate["created_at"] = "2026-10-15T22:29:59Z"
    elif mutant == "skipped-current-analysis":
        api.current_jobs[0]["steps"][0]["conclusion"] = "skipped"
    elif mutant == "old-current-job-attempt":
        api.current_jobs[0]["run_attempt"] = 2
    with pytest.raises(ValueError):
        api.qualify()


def test_successful_unknown_recovery_still_takes_full_master_tests_on_historical_failure(
    monkeypatch, tmp_path
):
    # Fresh successful security attempt earns receipts, while the conservative
    # historical-check policy still disallows test reuse for this same head.
    api = fixture()
    for language in evidence.SECURITY_LANGUAGES:
        recovered = ComposeSecurityAPI(language, attempt=2).qualify()
        api.security_receipts[language] = recovered
    api.security_run["run_attempt"] = 2
    api.rows[1]["run_attempt"] = 2
    for job in api.security_jobs:
        job["run_attempt"] = 2
    for artifact in api.security_artifacts:
        artifact["name"] = artifact["name"].replace("-1-", "-2-")
    evidence.validate_security_receipts(api, api.rows, HEAD, TREE, BASE, 12, BRANCH)
    failed = copy.deepcopy(api.checks[1])
    failed.update({"id": 9999, "conclusion": "failure"})
    api.checks.append(failed)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": BASE}))
    output = tmp_path / "outputs"
    for key, value in {
        **ENV,
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_OUTPUT": str(output),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(evidence, "API", lambda *args: api)
    monkeypatch.setattr(
        evidence, "git", lambda *args: TREE if args[-1] == "HEAD^{tree}" else HEAD
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    assert evidence.main() is None
    assert output.read_text() == "reuse=false\n"


def test_historical_failed_check_refusal_stays_byte_identical():
    source = SCRIPT.read_text()
    assert 'api.pages(f"commits/{head}/check-runs?filter=all", "check_runs")' in source
    assert (
        """        require(
            check["conclusion"] != "failure"
            and not REFUSAL.search((check.get("output") or {}).get("title") or ""),
            "security/check refusal",
        )"""
        in source
    )


def test_rerunning_only_one_language_cannot_pay_current_security_attempt():
    producer = ComposeSecurityAPI(attempt=2)
    producer.current_jobs[1]["run_attempt"] = 1
    with pytest.raises(ValueError, match="mixed producer attempts"):
        producer.qualify()
    consumer = fixture()
    consumer.security_run["run_attempt"] = 2
    consumer.rows[1]["run_attempt"] = 2
    for job in consumer.security_jobs:
        job["run_attempt"] = 2
    for artifact in consumer.security_artifacts:
        artifact["name"] = artifact["name"].replace("-1-", "-2-")
    consumer.security_receipts["python"]["attempt"] = 2
    with pytest.raises(ValueError, match="security receipt source/run mismatch"):
        decide(consumer)


@pytest.mark.parametrize(
    "fault,checkpoint,detail",
    [
        ("attempt", "run-validation", "attempt=2"),
        ("job", "producer-job", "conclusion=failure"),
        ("matrix", "matrix-attempts", "job_attempt=2"),
        ("step", "analysis-step", "conclusion=cancelled"),
        ("upload", "upload-count", "upload_count=0"),
    ],
)
def test_qualifier_diagnostics_identify_early_refusal_without_a_receipt(
    monkeypatch, tmp_path, capsys, fault, checkpoint, detail
):
    api = ComposeSecurityAPI()
    if fault == "attempt":
        api.current["run_attempt"] = 2
    elif fault == "job":
        api.current_jobs[0]["status"] = "completed"
        api.current_jobs[0]["conclusion"] = "failure"
    elif fault == "matrix":
        api.current_jobs[1]["run_attempt"] = 2
    elif fault == "step":
        api.current_jobs[0]["steps"][0]["conclusion"] = "cancelled"
    elif fault == "upload":
        monkeypatch.setattr(api, "array_pages", lambda *args, **kwargs: [])
    # Return an offline fake without replacing API's class identity; the real
    # qualifier and all its existing validations execute through the CLI.
    monkeypatch.setattr(evidence.API, "__new__", staticmethod(lambda cls, *args: api))
    for key, value in api.env.items():
        monkeypatch.setenv(key, value)
    proof = tmp_path / "provenance.json"
    proof.write_text(json.dumps(api.proof))
    output = tmp_path / "codeql-security.json"
    output.write_text('{"qualified":true}')
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--security-qualify",
            str(proof),
            "--security-output",
            str(output),
            "--sarif-id",
            api.candidate["sarif_id"],
            "--language",
            "python",
        ],
    )
    with pytest.raises(SystemExit) as result:
        evidence.main()
    assert result.value.code == 1
    assert not output.exists()
    text = capsys.readouterr().out
    checkpoints = [
        line for line in text.splitlines() if line.startswith("SECURITY CHECKPOINT")
    ]
    assert checkpoints[-1].startswith("SECURITY CHECKPOINT " + checkpoint)
    assert detail in checkpoints[-1]
    assert "SECURITY EVIDENCE INCOMPLETE (ValueError)" in text
    assert "SECURITY PASS" not in text


def test_security_diagnostics_never_render_untrusted_field_values(capsys):
    unsafe = "https://evil.invalid/private?token=SECRET\n::error::INJECT"
    evidence._security_diagnostic(
        "producer-job",
        language=unsafe,
        job_id=unsafe,
        job_attempt=True,
        status=unsafe,
        conclusion=unsafe,
        token=unsafe,
        matrix_count=10**30,
        attempt=-1,
        run_id={"body": unsafe},
    )
    text = capsys.readouterr().out
    assert unsafe not in text
    assert "SECRET" not in text and "INJECT" not in text and "token=" not in text
    assert text.count("\n") == 1
    assert "status=untrusted" in text and "job_attempt=untrusted" in text


def test_untrusted_run_status_is_sanitized_before_real_qualifier_refusal(capsys):
    api = ComposeSecurityAPI()
    api.current["status"] = "https://evil.invalid/TOKEN\nUNSAFE"
    with pytest.raises(ValueError, match="producer attempt unpaid"):
        api.qualify()
    text = capsys.readouterr().out
    assert "TOKEN" not in text and "UNSAFE" not in text
    assert "SECURITY CHECKPOINT run-validation" in text
    assert "status=untrusted" in text


class ReadinessClock:
    def __init__(self):
        self.now = 100.0
        self.waits = []

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.waits.append(delay)
        self.now += delay


def readiness_api(monkeypatch, *, pending_reads=1, latency=0):
    clock = ReadinessClock()
    monkeypatch.setattr(evidence.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(evidence.time, "sleep", clock.sleep)
    api = ComposeSecurityAPI()
    original = api.pages
    api.job_reads = 0
    api.mutate_snapshot = lambda jobs, index: None

    def pages(path, key):
        jobs = original(path, key)
        if path.startswith("actions/runs/110/") and key == "jobs":
            api.job_reads += 1
            clock.now += latency
            if api.job_reads <= pending_reads:
                jobs[0].update(status="in_progress", conclusion=None)
                jobs[0]["steps"][0].update(
                    status="in_progress", conclusion=None, completed_at=None
                )
            api.mutate_snapshot(jobs, api.job_reads)
        return jobs

    monkeypatch.setattr(api, "pages", pages)
    return api, clock


@pytest.mark.parametrize(
    "pending_reads,waits", [(0, []), (1, [1]), (2, [1, 2]), (3, [1, 2, 4])]
)
def test_only_observed_analysis_readiness_can_wait_then_qualify(
    monkeypatch, pending_reads, waits
):
    api, clock = readiness_api(monkeypatch, pending_reads=pending_reads)
    receipt = api.qualify()
    assert receipt["qualified"] is True
    assert clock.waits == waits and api.job_reads == pending_reads + 1
    assert api.deadline == 175.0


@pytest.mark.parametrize(
    "pending_reads,waits", [(4, [1, 2, 4, 4]), (8, [1, 2, 4] + [4] * 5)]
)
def test_analysis_completing_after_the_old_seven_second_window_qualifies(
    monkeypatch, pending_reads, waits
):
    """#11445: master 25cf8271d9 CodeQL 39784328013 refused twice with the
    analysis step still in_progress/null after the 1/2/4 s rereads. A valid
    pending step that turns completed/success later, inside the original
    deadline, is the same paid analysis and qualifies."""
    api, clock = readiness_api(monkeypatch, pending_reads=pending_reads)
    receipt = api.qualify()
    assert receipt["qualified"] is True and receipt["qualification"] == "PASS"
    assert clock.waits == waits and api.job_reads == pending_reads + 1
    assert sum(clock.waits) > 7 and clock.now < api.deadline == 175.0


@pytest.mark.parametrize("pending_reads", [20, 99])
def test_endless_pending_refuses_at_the_original_deadline_without_reset(
    monkeypatch, pending_reads
):
    api, clock = readiness_api(monkeypatch, pending_reads=pending_reads)
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    # Reads at 100, 101, 103, then every 4 s to 171; 171 + 4 reaches 175.
    assert clock.waits == [1, 2, 4] + [4] * 16 and api.job_reads == 20
    assert clock.now == 171.0 and api.deadline == 175.0


def test_request_time_counts_toward_the_readiness_deadline(monkeypatch):
    api, clock = readiness_api(monkeypatch, pending_reads=99, latency=3)
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    # Each jobs read costs 3 s: reads end at 103, 107, 112, then every 7 s
    # to 168; the read started at 172 ends at the deadline and is refused.
    assert clock.waits == [1, 2, 4] + [4] * 8 and api.job_reads == 12
    assert clock.now == 175.0 and api.deadline == 175.0


def test_a_wait_never_starts_when_the_read_itself_used_the_remaining_budget(
    monkeypatch,
):
    api, clock = readiness_api(monkeypatch, pending_reads=99, latency=3)
    api.deadline = clock.now + 3.5
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    # The 3 s read leaves 0.5 s: a 1 s wait measured from the read's start
    # would fit, but measured from its return it would cross the deadline.
    assert clock.waits == [] and api.job_reads == 1 and clock.now == 103.0


def test_slow_reads_still_qualify_a_late_completion_inside_the_deadline(monkeypatch):
    api, clock = readiness_api(monkeypatch, pending_reads=8, latency=3)
    receipt = api.qualify()
    assert receipt["qualified"] is True
    assert clock.waits == [1, 2, 4] + [4] * 5 and api.job_reads == 9
    assert clock.now == 154.0  # 9 reads x 3 s + 27 s of waits


def test_pending_rereads_stay_finite_when_the_clock_does_not_advance(monkeypatch):
    api, clock = readiness_api(monkeypatch, pending_reads=99)
    monkeypatch.setattr(evidence.time, "sleep", clock.waits.append)
    with pytest.raises(ValueError, match="analysis step is unpaid"):
        api.qualify()
    assert clock.waits == [1, 2, 4] + [4] * 17 and api.job_reads == 21
    assert clock.now == 100.0 and api.deadline == 175.0


@pytest.mark.parametrize(
    "fault",
    [
        "job-failed",
        "step-failed",
        "step-cancelled",
        "step-null-success",
        "step-queued",
        "duplicate-step",
        "missing-step",
        "job-id",
        "step-start",
        "attempt",
    ],
)
def test_late_reads_refuse_every_unpaid_or_moved_state_without_waiting_on(
    monkeypatch, fault
):
    api, clock = readiness_api(monkeypatch, pending_reads=99)

    def mutate(jobs, index):
        if index != 6:
            return
        job, step = jobs[0], jobs[0]["steps"][0]
        if fault == "job-failed":
            job.update(status="completed", conclusion="failure")
            step.update(status="completed", conclusion="success")
            step["completed_at"] = "2026-10-15T22:40:00Z"
        elif fault == "step-failed":
            step.update(status="completed", conclusion="failure")
        elif fault == "step-cancelled":
            step.update(status="completed", conclusion="cancelled")
        elif fault == "step-null-success":
            step["conclusion"] = "success"
        elif fault == "step-queued":
            step["status"] = "queued"
        elif fault == "duplicate-step":
            job["steps"].append(copy.deepcopy(step))
        elif fault == "missing-step":
            job["steps"] = [s for s in job["steps"] if s is not step]
        elif fault == "job-id":
            job["id"] += 1
        elif fault == "step-start":
            step["started_at"] = "2026-10-15T22:31:00Z"
        else:
            jobs[1]["run_attempt"] += 1

    api.mutate_snapshot = mutate
    with pytest.raises(ValueError):
        api.qualify()
    assert clock.waits == [1, 2, 4, 4, 4] and api.job_reads == 6


@pytest.mark.parametrize(
    "fault",
    ["job-id", "other-job-id", "step-number", "step-start", "attempt", "step-name"],
)
def test_pending_readiness_identity_cannot_move(monkeypatch, fault):
    api, clock = readiness_api(monkeypatch, pending_reads=1)

    def mutate(jobs, index):
        if index != 2:
            return
        if fault == "job-id":
            jobs[0]["id"] += 1
        elif fault == "other-job-id":
            jobs[1]["id"] += 1
        elif fault == "step-number":
            jobs[0]["steps"][0]["number"] += 1
        elif fault == "step-start":
            jobs[0]["steps"][0]["started_at"] = "2026-10-15T22:31:00Z"
        elif fault == "attempt":
            jobs[1]["run_attempt"] += 1
        else:
            jobs[0]["steps"][0]["name"] = "Different analysis"

    api.mutate_snapshot = mutate
    with pytest.raises(ValueError):
        api.qualify()
    assert clock.waits == [1] and api.job_reads == 2


@pytest.mark.parametrize(
    "fault",
    [
        "number",
        "job-id",
        "start",
        "completed",
        "job-terminal",
        "step-queued",
        "step-failed",
        "step-null-success",
        "duplicate-step",
    ],
)
def test_unobserved_or_malformed_pending_states_never_wait(monkeypatch, fault):
    api, clock = readiness_api(monkeypatch)

    def mutate(jobs, index):
        job, step = jobs[0], jobs[0]["steps"][0]
        if fault == "number":
            step["number"] = True
        elif fault == "job-id":
            job["id"] = "800"
        elif fault == "start":
            step["started_at"] = "not-a-timestamp"
        elif fault == "completed":
            step["completed_at"] = "not-a-timestamp"
        elif fault == "job-terminal":
            job.update(status="completed", conclusion="success")
        elif fault == "step-queued":
            step["status"] = "queued"
        elif fault == "step-failed":
            step.update(status="completed", conclusion="failure")
        elif fault == "step-null-success":
            step["conclusion"] = "success"
        else:
            job["steps"].append(copy.deepcopy(step))

    api.mutate_snapshot = mutate
    with pytest.raises((ValueError, KeyError)):
        api.qualify()
    assert clock.waits == [] and api.job_reads == 1


@pytest.mark.parametrize(
    "remaining,expected_reads,waits",
    [
        (0, 0, []),
        (1, 1, []),
        (2.5, 2, [1]),
        (6, 3, [1, 2]),
        (20, 7, [1, 2, 4, 4, 4, 4]),
    ],
)
def test_readiness_waits_share_the_original_deadline(
    monkeypatch, remaining, expected_reads, waits
):
    api, clock = readiness_api(monkeypatch, pending_reads=99)
    api.deadline = clock.now + remaining
    fixed_deadline = api.deadline
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    assert api.job_reads == expected_reads and clock.waits == waits
    assert api.deadline == fixed_deadline


def test_api_error_on_pending_reread_has_no_recovery_retry(monkeypatch):
    api, clock = readiness_api(monkeypatch, pending_reads=99)

    def fail(jobs, index):
        if index == 2:
            raise RuntimeError("offline response error")

    api.mutate_snapshot = fail
    with pytest.raises(RuntimeError):
        api.qualify()
    assert api.job_reads == 2 and clock.waits == [1]
    assert api.deadline == 175.0


def test_readiness_does_not_poll_upload_visibility(monkeypatch):
    api, clock = readiness_api(monkeypatch, pending_reads=0)
    calls = []

    def empty_upload(*args, **kwargs):
        calls.append(args)
        return []

    monkeypatch.setattr(api, "array_pages", empty_upload)
    with pytest.raises(ValueError, match="actual SARIF upload"):
        api.qualify()
    assert len(calls) == 1 and api.job_reads == 1 and clock.waits == []


@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize(
    "fault", ["contradictory-job", "duplicate-job-id", "bool-attempt", "string-attempt"]
)
def test_ready_and_pending_jobs_refuse_contradictory_or_malformed_identity(
    monkeypatch, pending, fault
):
    api, clock = readiness_api(monkeypatch, pending_reads=99 if pending else 0)

    def mutate(jobs, index):
        if fault == "contradictory-job":
            jobs[0].update(status="in_progress", conclusion="failure")
        elif fault == "duplicate-job-id":
            jobs[1]["id"] = jobs[0]["id"]
        elif fault == "bool-attempt":
            jobs[1]["run_attempt"] = True
        else:
            jobs[1]["run_attempt"] = "1"

    api.mutate_snapshot = mutate
    with pytest.raises(ValueError):
        api.qualify()
    assert api.job_reads == 1 and clock.waits == []


def test_successful_snapshot_cannot_arrive_after_original_deadline(monkeypatch):
    api, clock = readiness_api(monkeypatch, pending_reads=0)

    def consume_budget(jobs, index):
        clock.now = api.deadline

    api.mutate_snapshot = consume_budget
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    assert clock.waits == [] and api.job_reads == 1


def run_readiness_api(
    monkeypatch,
    *,
    queued_reads=99,
    pending_reads=0,
    latency=0,
    attempt=1,
    witness=True,
):
    """The real qualifier reads its own run; the first reads say `queued`.

    With `witness`, the jobs carry the real jobs-API identity fields and the
    producer's own job is executing, as 39793061366's JavaScript job was when
    its qualifier read the run `queued` (#11445).
    """
    api, clock = readiness_api(monkeypatch, pending_reads=pending_reads)
    if attempt != 1:
        api.current["run_attempt"] = attempt
        api.env["GITHUB_RUN_ATTEMPT"] = str(attempt)
        api.proof["attempt"] = attempt
        for job in api.current_jobs:
            job["run_attempt"] = attempt
    if witness:
        for job in api.current_jobs:
            job.update(
                run_id=110,
                head_sha=HEAD,
                head_branch=BRANCH,
                started_at="2026-10-15T22:29:00Z",
            )
        api.current_jobs[0].update(status="in_progress", conclusion=None)
    original = api.get
    api.run_reads = 0
    api.mutate_run = lambda run, index: None

    def get(path):
        run = original(path)
        if path == "actions/runs/110":
            api.run_reads += 1
            clock.now += latency
            if api.run_reads <= queued_reads:
                run.update(status="queued", conclusion=None)
            api.mutate_run(run, api.run_reads)
        return run

    monkeypatch.setattr(api, "get", get)
    return api, clock


@pytest.mark.parametrize("attempt", [1, 2])
@pytest.mark.parametrize(
    "pending_reads,waits", [(0, []), (3, [1, 2, 4]), (18, [1, 2, 4] + [4] * 15)]
)
def test_run_queued_for_the_whole_budget_qualifies_only_on_its_live_own_job_witness(
    monkeypatch, capsys, attempt, pending_reads, waits
):
    """#11445: master 40fb61c6e3 CodeQL 39793061366 JavaScript read its run
    `status=queued conclusion=null` 5 and 10 minutes into attempts 1 and 2
    while its own job ran. Here every run read is queued for the whole 75 s
    decision window; only the producer's own executing job and its completed
    analysis step, read fresh and rebound at the final reread, let every
    existing check run and pay."""
    api, clock = run_readiness_api(
        monkeypatch, pending_reads=pending_reads, attempt=attempt
    )
    receipt = api.qualify()
    assert receipt["qualified"] is True and receipt["qualification"] == "PASS"
    assert receipt["attempt"] == attempt and receipt["baseline"]["run_id"] == 90
    assert receipt["delta"] is not None
    assert clock.waits == waits and clock.now < api.deadline == 175.0
    # One validated run read, then the existing final reread; both queued.
    assert api.run_reads == 2
    # Witness reads until the step completes, then exactly one rebind read.
    assert api.job_reads == pending_reads + 2
    lines = capsys.readouterr().out.splitlines()
    assert not [x for x in lines if "run-readiness-wait" in x]
    assert [x for x in lines if "CHECKPOINT run-validation " in x] == [
        f"SECURITY CHECKPOINT run-validation attempt={attempt} conclusion=null "
        f"expected_attempt={attempt} run_id=110 status=queued"
    ]
    assert [x for x in lines if "CHECKPOINT run-revalidation " in x] == [
        f"SECURITY CHECKPOINT run-revalidation attempt={attempt} conclusion=null "
        f"expected_attempt={attempt} run_id=110 status=queued"
    ]
    assert [x for x in lines if "liveness-witness" in x] == [
        f"SECURITY CHECKPOINT liveness-witness conclusion=null "
        f"job_attempt={attempt} job_id=800 status=in_progress"
    ] * (pending_reads + 1)
    order = [x.split()[2] for x in lines if x.startswith("SECURITY CHECKPOINT ")]
    tail = ["analysis-reread", "run-reread", "run-revalidation", "liveness-rebind"]
    assert order[-5:] == tail + ["qualified"]
    for paid in ("upload-window", "candidate-snapshot", "baseline", "alert-comparison"):
        assert paid in order


def test_queued_run_without_a_live_own_job_never_pays(monkeypatch):
    """A queued read alone is never paid: jobs that do not carry the witness
    refuse at the first jobs read, with no wait."""
    api, clock = run_readiness_api(monkeypatch, witness=False)
    with pytest.raises(ValueError, match="liveness witness unpaid"):
        api.qualify()
    assert clock.waits == [] and api.run_reads == 1 and api.job_reads == 1


def test_queued_run_with_endless_pending_analysis_refuses_at_the_one_deadline(
    monkeypatch,
):
    api, clock = run_readiness_api(monkeypatch, pending_reads=99)
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    assert clock.waits == [1, 2, 4] + [4] * 16 and api.job_reads == 20
    assert api.run_reads == 1 and clock.now == 171.0 and api.deadline == 175.0


def test_queued_run_never_pays_a_pending_analysis_on_a_frozen_clock(monkeypatch):
    api, clock = run_readiness_api(monkeypatch, pending_reads=99)
    monkeypatch.setattr(evidence.time, "sleep", clock.waits.append)
    with pytest.raises(ValueError, match="analysis step is unpaid"):
        api.qualify()
    assert clock.waits == [1, 2, 4] + [4] * 17 and api.job_reads == 21
    assert api.run_reads == 1 and clock.now == 100.0


def _witness_fault(jobs, fault):
    own, sibling = jobs[0], jobs[1]
    step = own["steps"][0]
    if fault == "own-job-missing":
        own["name"] = "Analyze (ruby)"
    elif fault == "own-job-duplicated":
        sibling["name"] = own["name"]
    elif fault == "foreign-run":
        own["run_id"] = 111
    elif fault == "foreign-sibling-run":
        sibling["run_id"] = 111
    elif fault == "foreign-head":
        own["head_sha"] = BASE
    elif fault == "foreign-sibling-head":
        sibling["head_sha"] = BASE
    elif fault == "foreign-branch":
        own["head_branch"] = "master"
    elif fault == "missing-run-id":
        del own["run_id"]
    elif fault == "moved-attempt":
        for job in jobs:
            job["run_attempt"] += 1
    elif fault == "mixed-attempt":
        sibling["run_attempt"] += 1
    elif fault == "job-failed":
        own.update(status="completed", conclusion="failure")
    elif fault == "job-cancelled":
        own.update(status="completed", conclusion="cancelled")
    elif fault == "job-no-longer-executing":
        own.update(status="completed", conclusion="success")
    elif fault == "job-not-started":
        own.update(status="queued", conclusion=None, started_at=None)
    elif fault == "job-start-missing":
        own["started_at"] = None
    elif fault == "job-start-malformed":
        own["started_at"] = "not-a-timestamp"
    elif fault == "job-started-after-analysis":
        own["started_at"] = "2026-10-15T22:31:00Z"
    elif fault == "analysis-missing":
        step["name"] = "Upload results"
    elif fault == "analysis-failed":
        step.update(status="completed", conclusion="failure")
    elif fault == "analysis-cancelled":
        step.update(status="completed", conclusion="cancelled")
    elif fault == "analysis-not-started":
        step.update(status="queued", conclusion=None, completed_at=None)
    else:
        raise AssertionError(fault)


MATRIX = "wrong producer matrix membership"
MIXED = "mixed producer attempts"
WITNESS = "producer liveness witness unpaid"
JOB = "producer job belongs to an unpaid attempt"
STEP = "producer analysis step is unpaid"
WITNESS_FAULTS = {
    "own-job-missing": MATRIX,
    "own-job-duplicated": MATRIX,
    "foreign-run": WITNESS,
    "foreign-sibling-run": WITNESS,
    "foreign-head": WITNESS,
    "foreign-sibling-head": WITNESS,
    "foreign-branch": WITNESS,
    "missing-run-id": "run_id",
    "moved-attempt": MIXED,
    "mixed-attempt": MIXED,
    "job-failed": JOB,
    "job-cancelled": JOB,
    "job-no-longer-executing": WITNESS,
    "job-not-started": JOB,
    "job-start-missing": WITNESS,
    "job-start-malformed": "isoformat",
    "job-started-after-analysis": WITNESS,
    "analysis-missing": STEP,
    "analysis-failed": STEP,
    "analysis-cancelled": STEP,
    "analysis-not-started": STEP,
}


@pytest.mark.parametrize("fault,refusal", WITNESS_FAULTS.items())
def test_queued_run_witness_refuses_missing_foreign_moved_or_unpaid_job_at_once(
    monkeypatch, capsys, fault, refusal
):
    api, clock = run_readiness_api(monkeypatch)
    api.mutate_snapshot = lambda jobs, read: _witness_fault(jobs, fault)
    with pytest.raises((ValueError, KeyError), match=refusal):
        api.qualify()
    assert clock.waits == [] and api.run_reads == 1 and api.job_reads == 1
    assert "CHECKPOINT upload-lookup" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "fault,refusal",
    list(WITNESS_FAULTS.items())
    + [
        ("moved-job", "readiness identity moved"),
        ("moved-step-number", "readiness identity moved"),
        ("moved-step-start", "readiness identity moved"),
        ("moved-completion", "liveness witness moved"),
        ("analysis-pending-again", STEP),
    ],
)
def test_final_queued_reread_refuses_unless_the_same_witness_rebinds_fresh(
    monkeypatch, capsys, fault, refusal
):
    """The final reread is not skipped and does not reuse the first witness:
    a fresh jobs read must show the same live job and the same completed
    analysis step, on its first read, with no wait."""
    api, clock = run_readiness_api(monkeypatch)

    def mutate(jobs, read):
        if read != 2:
            return
        own = jobs[0]
        if fault == "moved-job":
            own["id"] = 850
        elif fault == "moved-step-number":
            own["steps"][0]["number"] = 9
        elif fault == "moved-step-start":
            own["steps"][0]["started_at"] = "2026-10-15T22:29:30Z"
        elif fault == "moved-completion":
            own["steps"][0]["completed_at"] = "2026-10-15T22:58:00Z"
        elif fault == "analysis-pending-again":
            own["steps"][0].update(
                status="in_progress", conclusion=None, completed_at=None
            )
        else:
            _witness_fault(jobs, fault)

    api.mutate_snapshot = mutate
    with pytest.raises((ValueError, KeyError), match=refusal):
        api.qualify()
    assert clock.waits == [] and api.run_reads == 2 and api.job_reads == 2
    out = capsys.readouterr().out
    assert "CHECKPOINT liveness-rebind" in out
    assert "CHECKPOINT qualified" not in out


@pytest.mark.parametrize("index", [1, 2])
@pytest.mark.parametrize(
    "fault",
    [
        "attempt-moved",
        "run-id",
        "head",
        "branch",
        "workflow",
        "event",
        "repository",
        "head-repository",
        "queued-cancelled",
        "queued-success",
        "waiting",
        "pending",
        "requested",
        "completed-failure",
        "completed-cancelled",
        "completed-null",
        "untrusted-status",
        "missing-conclusion",
    ],
)
def test_queued_run_refuses_every_other_foreign_or_terminal_bad_state(
    monkeypatch, capsys, index, fault
):
    """Read 1 is run-validation, read 2 the existing final reread."""
    api, clock = run_readiness_api(monkeypatch)

    def mutate(run, read):
        if read != index:
            return
        if fault == "attempt-moved":
            run["run_attempt"] = 2
        elif fault == "run-id":
            run["id"] = 0
        elif fault == "head":
            run["head_sha"] = BASE
        elif fault == "branch":
            run["head_branch"] = "master"
        elif fault == "workflow":
            run["path"] = ".github/workflows/ci.yml"
        elif fault == "event":
            run["event"] = "pull_request"
        elif fault == "repository":
            run["repository"] = {**run["repository"], "id": 7}
        elif fault == "head-repository":
            run["head_repository"] = {**run["head_repository"], "id": 7}
        elif fault == "queued-cancelled":
            run["conclusion"] = "cancelled"
        elif fault == "queued-success":
            run["conclusion"] = "success"
        elif fault in ("waiting", "pending", "requested"):
            run["status"] = fault
        elif fault == "completed-failure":
            run.update(status="completed", conclusion="failure")
        elif fault == "completed-cancelled":
            run.update(status="completed", conclusion="cancelled")
        elif fault == "completed-null":
            run.update(status="completed", conclusion=None)
        elif fault == "untrusted-status":
            run["status"] = "https://evil.invalid/TOKEN"
        else:
            del run["conclusion"]

    api.mutate_run = mutate
    with pytest.raises((ValueError, KeyError)):
        api.qualify()
    assert clock.waits == [] and api.run_reads == index
    assert api.job_reads == index - 1
    assert "CHECKPOINT qualified" not in capsys.readouterr().out


def test_final_queued_reread_after_an_in_progress_read_needs_a_fresh_witness(
    monkeypatch,
):
    api, clock = run_readiness_api(monkeypatch, queued_reads=0)
    api.mutate_run = lambda run, read: (
        run.update(status="queued", conclusion=None) if read == 2 else None
    )
    assert api.qualify()["qualified"] is True
    assert clock.waits == [] and api.run_reads == 2 and api.job_reads == 2


def test_final_queued_reread_without_witness_still_refuses(monkeypatch):
    api, clock = run_readiness_api(monkeypatch, queued_reads=0, witness=False)
    api.mutate_run = lambda run, read: (
        run.update(status="queued", conclusion=None) if read == 2 else None
    )
    with pytest.raises(ValueError, match="liveness witness unpaid"):
        api.qualify()
    assert clock.waits == [] and api.run_reads == 2 and api.job_reads == 2


def test_final_in_progress_reread_of_a_witnessed_queued_run_needs_no_rebind(
    monkeypatch,
):
    api, clock = run_readiness_api(monkeypatch, queued_reads=1)
    assert api.qualify()["qualified"] is True
    assert api.run_reads == 2 and api.job_reads == 1


def test_a_rebind_cannot_arrive_after_the_original_deadline(monkeypatch, capsys):
    api, clock = run_readiness_api(monkeypatch)

    def consume_budget(jobs, read):
        if read == 2:
            clock.now = api.deadline

    api.mutate_snapshot = consume_budget
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    assert api.run_reads == 2 and api.job_reads == 2
    assert "CHECKPOINT qualified" not in capsys.readouterr().out


def test_queued_run_read_time_counts_toward_the_same_deadline(monkeypatch):
    api, clock = run_readiness_api(monkeypatch, latency=3)
    api.deadline = clock.now + 3
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    assert clock.waits == [] and api.run_reads == 1 and api.job_reads == 0


def test_an_in_progress_run_cannot_arrive_after_original_deadline(monkeypatch, capsys):
    api, clock = run_readiness_api(monkeypatch, queued_reads=0, latency=3)
    api.deadline = clock.now + 3
    with pytest.raises(ValueError, match="decision deadline"):
        api.qualify()
    assert clock.waits == [] and api.run_reads == 1 and api.job_reads == 0
    out = capsys.readouterr().out
    assert "CHECKPOINT run-validation" not in out
    assert "CHECKPOINT repository-binding" not in out


@pytest.mark.parametrize("read", [1, 2])
def test_api_error_on_a_witness_or_rebind_read_has_no_retry(monkeypatch, read):
    api, clock = run_readiness_api(monkeypatch)

    def fail(jobs, index):
        if index == read:
            raise RuntimeError("offline response error")

    api.mutate_snapshot = fail
    with pytest.raises(RuntimeError):
        api.qualify()
    assert api.job_reads == read and api.run_reads == read and clock.waits == []


def test_api_error_on_a_queued_run_read_has_no_retry(monkeypatch):
    api, clock = run_readiness_api(monkeypatch)

    def fail(run, read):
        raise RuntimeError("offline response error")

    api.mutate_run = fail
    with pytest.raises(RuntimeError):
        api.qualify()
    assert api.run_reads == 1 and clock.waits == [] and api.job_reads == 0


class TransitionBaselineAPI(BaseSecurityAPI):
    """Authenticated-shape specimens exercise the real transition validators."""

    def __init__(self):
        super().__init__(declared=True)
        self.run.update(
            id=evidence.TRANSITION_MASTER_RUN,
            head_sha=evidence.TRANSITION_BASE,
            run_attempt=evidence.TRANSITION_MASTER_ATTEMPT,
            status="completed",
            conclusion="failure",
            repository={
                "id": evidence.TRANSITION_REPOSITORY_ID,
                "full_name": evidence.TRANSITION_REPOSITORY,
            },
            head_repository={"id": evidence.TRANSITION_REPOSITORY_ID},
        )
        self.runs = [copy.deepcopy(self.run)]
        self.compose = {
            **self.run,
            "id": evidence.TRANSITION_RUN,
            "run_attempt": evidence.TRANSITION_ATTEMPT,
            "head_branch": evidence.TRANSITION_BRANCH,
            "conclusion": "success",
        }
        self.ref = {
            "ref": "refs/heads/master",
            "object": {"type": "commit", "sha": evidence.TRANSITION_BASE},
        }
        self.ref_reads = 0
        self.compose_reads = 0
        self.move_master = False
        self.move_compose = False
        self.move_analysis = False
        self.receipts = {}
        self.artifacts = []
        for i, lang in enumerate(evidence.SECURITY_LANGUAGES):
            meta = self.metadata[500 + i]
            meta.update(
                commit_sha=evidence.TRANSITION_BASE,
                ref="refs/heads/" + evidence.TRANSITION_BRANCH,
            )
            sarif = self.snapshots[500 + i]
            sarif["runs"][0]["versionControlProvenance"][0].update(
                revisionId=evidence.TRANSITION_BASE,
                branch=meta["ref"],
                repositoryUri="https://github.com/" + evidence.TRANSITION_REPOSITORY,
            )
            for result in sarif["runs"][0]["results"]:
                identity = result["properties"]["github/alertNumber"]
                result["properties"]["github/alertUrl"] = (
                    f"https://api.github.com/repos/{evidence.TRANSITION_REPOSITORY}"
                    f"/code-scanning/alerts/{identity}"
                )
            snapshot = evidence.parse_security_snapshot(
                sarif, meta, evidence.TRANSITION_REPOSITORY
            )
            receipt = copy.deepcopy(fixture().security_receipts[lang])
            receipt.update(
                repository=evidence.TRANSITION_REPOSITORY,
                repository_id=evidence.TRANSITION_REPOSITORY_ID,
                head=evidence.TRANSITION_BASE,
                tree=evidence.TRANSITION_TREE,
                base=evidence.TRANSITION_PARENT,
                ref=meta["ref"],
                run_id=evidence.TRANSITION_RUN,
                attempt=1,
                analysis_id=meta["id"],
                sarif_id=meta["sarif_id"],
                sarif_digest=snapshot["sarif_digest"],
                qualifying_count=len(snapshot["qualifying_ids"]),
                results_count=meta["results_count"],
                rules_count=meta["rules_count"],
            )
            receipt["baseline"]["head"] = evidence.TRANSITION_PARENT
            self.receipts[lang] = receipt
            self.artifacts.append(
                {"id": 900 + i, "name": "codeql-security-1-" + lang, "expired": False}
            )

    def get(self, path):
        if path == "git/ref/heads/master":
            self.ref_reads += 1
            value = copy.deepcopy(self.ref)
            if self.move_master and self.ref_reads > 1:
                value["object"]["sha"] = HEAD
            return value
        if path == "git/commits/" + evidence.TRANSITION_BASE:
            return {
                "sha": evidence.TRANSITION_BASE,
                "tree": {"sha": evidence.TRANSITION_TREE},
            }
        if path == f"actions/runs/{evidence.TRANSITION_RUN}":
            self.compose_reads += 1
            value = copy.deepcopy(self.compose)
            if self.move_compose and self.compose_reads > 1:
                value["run_attempt"] += 1
            return value
        value = super().get(path)
        if self.move_analysis and path.startswith("code-scanning/"):
            self.reads += 1
            if self.reads % 2:
                value["sarif_id"] = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        return value

    def pages(self, path, key):
        if key == "artifacts":
            return copy.deepcopy(self.artifacts)
        return super().pages(path, key)

    def raw(self, path, limit):
        i = int(path.split("/")[-2]) - 900
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "codeql-security.json",
                json.dumps(self.receipts[evidence.SECURITY_LANGUAGES[i]]),
            )
        return buffer.getvalue()

    def select(self):
        return evidence.select_base_security(
            self, evidence.TRANSITION_BASE, evidence.TRANSITION_REPOSITORY_ID, "python"
        )


def test_exact_transition_keeps_compose_role_and_failed_master_unpaid():
    api = TransitionBaselineAPI()
    result = api.select()
    assert result["selection"] == evidence.TRANSITION_SELECTION
    assert result["run"]["id"] == evidence.TRANSITION_RUN
    assert result["snapshot"]["qualifying_ids"] == [11, 12]
    assert api.run["conclusion"] == "failure"
    assert all(r["role"] == "compose" for r in api.receipts.values())
    assert api.ref_reads == 2


@pytest.mark.parametrize(
    "fault",
    [
        "master-moved",
        "master-attempt",
        "master-cancelled",
        "wrong-repository",
        "wrong-compose-head",
        "wrong-compose-attempt",
        "compose-failed",
        "compose-moves",
        "missing-language",
        "expired-receipt",
        "wrong-receipt-role",
        "wrong-tree",
        "wrong-receipt-attempt",
        "wrong-upload",
        "wrong-analysis-ref",
        "bad-digest",
        "bad-count",
        "qualifying-delta",
        "failed-analysis-step",
        "malformed-sarif",
        "wrong-baseline-parent",
        "listing-attempt",
        "api-error",
    ],
)
def test_transition_refuses_malformed_moved_unpaid_or_foreign_evidence(fault):
    api = TransitionBaselineAPI()
    receipt = api.receipts["javascript-typescript"]
    if fault == "master-moved":
        api.move_master = True
    elif fault == "master-attempt":
        api.run["run_attempt"] += 1
    elif fault == "master-cancelled":
        api.run["conclusion"] = "cancelled"
    elif fault == "wrong-repository":
        api.run["repository"]["id"] = 1
    elif fault == "wrong-compose-head":
        api.compose["head_sha"] = HEAD
    elif fault == "wrong-compose-attempt":
        api.compose["run_attempt"] += 1
    elif fault == "compose-failed":
        api.compose["conclusion"] = "failure"
    elif fault == "compose-moves":
        api.move_compose = True
    elif fault == "missing-language":
        api.artifacts.pop()
    elif fault == "expired-receipt":
        api.artifacts[1]["expired"] = True
    elif fault == "wrong-receipt-role":
        receipt["role"] = "baseline"
    elif fault == "wrong-tree":
        receipt["tree"] = TREE
    elif fault == "wrong-receipt-attempt":
        receipt["attempt"] = 2
    elif fault == "wrong-upload":
        receipt["sarif_id"] = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    elif fault == "wrong-analysis-ref":
        api.metadata[501]["ref"] = "refs/heads/master"
    elif fault == "bad-digest":
        receipt["sarif_digest"] = "0" * 64
    elif fault == "bad-count":
        receipt["qualifying_count"] += 1
    elif fault == "qualifying-delta":
        receipt["delta"]["new_qualifying_ids"] = [99]
    elif fault == "failed-analysis-step":
        api.jobs[1]["steps"][0]["conclusion"] = "failure"
    elif fault == "malformed-sarif":
        api.snapshots[501]["version"] = "unknown"
    elif fault == "wrong-baseline-parent":
        receipt["base"] = HEAD
    elif fault == "listing-attempt":
        api.runs[0]["run_attempt"] = 1
    elif fault == "api-error":

        def refused(*args):
            raise ValueError("API failed")

        api.get = refused
    with pytest.raises(ValueError):
        api.select()


def test_transition_is_inert_when_exact_master_has_paid_baseline():
    api = TransitionBaselineAPI()
    api.run.update(run_attempt=3, conclusion="success")
    api.runs = [copy.deepcopy(api.run)]
    for job in api.jobs:
        job["run_attempt"] = 3
    for artifact in api.artifacts:
        artifact["name"] = artifact["name"].replace("-1-", "-3-")
    for i, lang in enumerate(evidence.SECURITY_LANGUAGES):
        api.metadata[500 + i]["ref"] = "refs/heads/master"
        api.snapshots[500 + i]["runs"][0]["versionControlProvenance"][0][
            "branch"
        ] = "refs/heads/master"
        api.receipts[lang].update(
            role="baseline",
            qualified=False,
            qualification="BASELINE",
            baseline=None,
            delta=None,
            run_id=evidence.TRANSITION_MASTER_RUN,
            attempt=3,
            ref="refs/heads/master",
        )
    result = api.select()
    assert result["selection"] == "receipt"
    assert result["run"]["id"] == evidence.TRANSITION_MASTER_RUN
    assert api.compose_reads == 0 and api.ref_reads == 0


def test_transition_receipts_force_full_master_tests(monkeypatch, tmp_path):
    api = fixture()
    monkeypatch.setattr(evidence, "TRANSITION_BASE", BASE)
    monkeypatch.setattr(evidence, "TRANSITION_RUN", 90)
    for receipt in api.security_receipts.values():
        receipt["baseline"]["selection"] = evidence.TRANSITION_SELECTION
    with pytest.raises(ValueError, match="requires full master tests"):
        decide(api)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"before": BASE}))
    output = tmp_path / "outputs"
    for key, value in {
        **ENV,
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_OUTPUT": str(output),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(evidence, "API", lambda *args: api)
    monkeypatch.setattr(
        evidence, "git", lambda *args: TREE if args[-1] == "HEAD^{tree}" else HEAD
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    assert evidence.main() is None
    assert output.read_text() == "reuse=false\n"


@pytest.mark.parametrize(
    "before,stop", [(evidence.TRANSITION_BASE, True), (BASE, False)]
)
def test_transition_master_failure_stops_without_second_transition(
    tmp_path, before, stop
):
    path = tmp_path / "event.json"
    path.write_text(
        json.dumps({"before": before, "after": HEAD, "ref": "refs/heads/master"})
    )
    result = evidence._security_recovery({**ENV, "GITHUB_EVENT_PATH": str(path)})
    assert result.startswith("STOP:") is stop
    if stop:
        assert "No retry or second transition" in result


def test_missing_master_recovery_context_never_advises_unapproved_retry():
    assert evidence._security_recovery(ENV).startswith("STOP:")
