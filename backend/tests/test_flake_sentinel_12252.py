"""#12252 item 2: the flake sentinel, the quarantine it feeds, and the canary that reports it.

A test that fails and then passes on the same commit twice within 7 days gets ONE
`Flaky: <test id>` issue (reopened, never duplicated); while that issue is open the
required jobs do not fail on it and the non-required `flaky-canary` job runs it.
"""

from __future__ import annotations

import importlib.util
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.tasks.sentinel_filing import declared_fingerprints

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("flake_sentinel", ROOT / "backend" / "scripts" / "flake_sentinel.py")
fs = importlib.util.module_from_spec(SPEC)
sys.modules["flake_sentinel"] = fs  # dataclasses resolve the module by name
SPEC.loader.exec_module(fs)

T1 = "tests/integration/test_dnpl_reservation_relimit_10090_pg.py::test_relimit_admits_more_other_events_and_rolls_back"
T2 = "tests/test_kalshi_idle_wake_10090.py::test_owed_stamp_work_spends_the_budget_and_a_quote_waits_for_it"


def _ev(test, at, run=1, sha="a" * 40, kind="rerun"):
    return fs.Event(test, sha, run, 1, "database-integration (shared-tail)", at, kind)


# --- reading the evidence ---------------------------------------------------

def test_a_log_names_its_failed_and_errored_tests_in_both_pytest_formats():
    log = (
        "2026-11-06T03:59:33Z \x1b[31mtests/integration/test_a_pg.py::test_x[True] FAILED\x1b[0m [ 12%]\n"
        "2026-11-06T03:59:34Z FAILED tests/test_b.py::TestC::test_y - AssertionError: no\n"
        "2026-11-06T03:59:35Z ERROR tests/test_c.py::test_z - RuntimeError\n"
        "2026-11-06T03:59:36Z tests/test_d.py::test_ok PASSED\n"
    )
    assert fs.failed_test_ids(log) == {
        "tests/integration/test_a_pg.py::test_x[True]",
        "tests/test_b.py::TestC::test_y",
        "tests/test_c.py::test_z",
    }


def test_only_re_runs_and_commits_with_a_failure_and_a_pass_are_read_job_by_job():
    runs = [
        {"id": 1, "head_sha": "s1", "run_attempt": 1, "conclusion": "failure"},
        {"id": 2, "head_sha": "s1", "run_attempt": 1, "conclusion": "success"},
        {"id": 3, "head_sha": "s2", "run_attempt": 2, "conclusion": "success"},
        {"id": 4, "head_sha": "s3", "run_attempt": 1, "conclusion": "success"},
        {"id": 5, "head_sha": "s4", "run_attempt": 1, "conclusion": "failure"},
    ]
    assert fs.candidate_run_ids(runs) == {1, 2, 3}


def test_a_job_flaked_only_when_a_later_job_of_the_same_name_passed_on_that_commit():
    jobs = [
        {"name": "backend-tests (8)", "conclusion": "failure", "started_at": "2026-11-06T01:00:00Z", "id": 1},
        {"name": "backend-tests (8)", "conclusion": "success", "started_at": "2026-11-06T02:00:00Z", "id": 2},
        {"name": "backend-tests (3)", "conclusion": "success", "started_at": "2026-11-06T01:00:00Z", "id": 3},
        {"name": "backend-tests (3)", "conclusion": "failure", "started_at": "2026-11-06T02:00:00Z", "id": 4},
        {"name": "frontend-build", "conclusion": "failure", "started_at": "2026-11-06T01:00:00Z", "id": 5},
    ]
    assert [j["id"] for j in fs.failed_then_passed(jobs)] == [1]


def test_two_events_in_the_window_flag_a_test_and_one_does_not():
    events = [_ev(T1, "2026-11-05T01:00:00Z"), _ev(T1, "2026-11-06T01:00:00Z", run=2), _ev(T2, "2026-11-06T01:00:00Z")]
    assert set(fs.flaky(events)) == {T1}
    assert fs.flaky(events, since="2026-11-05T12:00:00Z") == {}


def test_the_issue_body_declares_the_fingerprint_the_rail_dedups_on():
    body = fs.issue_body(T1, [_ev(T1, "2026-11-06T01:00:00Z")])
    assert (fs.MARKER_KEY, fs.fingerprint(T1)) in declared_fingerprints(body)
    assert "flaky-canary" in body and "Close this issue when the rig is fixed" in body


def test_a_redirect_to_signed_storage_never_carries_the_token():
    handler = fs._DropAuthOnRedirect()
    req = urllib.request.Request("https://api.github.com/repos/x/actions/jobs/1/logs",
                                 headers={"Authorization": "Bearer secret"})
    new = handler.redirect_request(req, None, 302, "Found", {}, "https://example.blob.core.windows.net/logs?sig=k")
    assert not new.has_header("Authorization")
    same = handler.redirect_request(req, None, 302, "Found", {}, "https://api.github.com/other")
    assert same.has_header("Authorization")
    assert fs._where("https://example.blob.core.windows.net/logs/job.txt?sig=KEY") == "example.blob.core.windows.net/logs/job.txt"


# --- filing: file, comment only on new evidence, reopen, never duplicate ----

class FakeApi:
    def __init__(self, open_issues=(), closed_issues=()):
        self.issues = {"open": list(open_issues), "closed": list(closed_issues)}
        self.writes = []

    def get(self, path):
        state = "open" if "state=open" in path else "closed"
        return self.issues[state] if "page=1" in path else []

    def write(self, method, path, data):
        self.writes.append((method, path, data))
        return {}


def _issue(number, test, closed_at=None):
    return {"number": number, "title": f"Flaky: {test}", "body": fs.issue_body(test, []), "closed_at": closed_at}


@pytest.fixture
def filed(monkeypatch):
    calls = []

    def reconcile_issue(**kw):
        calls.append(kw)
        return {"action": "filed", "issue": 900}

    import app.tasks.sentinel_filing as rail

    monkeypatch.setattr(rail, "reconcile_issue", reconcile_issue)
    return calls


NOW = fs.dt.datetime(2026, 11, 7, 15, 40, tzinfo=fs.dt.timezone.utc)


def test_a_new_flaky_test_is_filed_once_through_the_rail(filed):
    api = FakeApi()
    lines = fs.file_flakes(api, [_ev(T1, "2026-11-05T01:00:00Z"), _ev(T1, "2026-11-07T01:00:00Z", run=2)], NOW, dry=False)
    assert len(filed) == 1 and filed[0]["title"] == f"Flaky: {T1}" and filed[0]["red"] is True
    assert filed[0]["marker_key"] == fs.MARKER_KEY and fs.QUARANTINE_LABEL in filed[0]["labels"]
    assert api.writes == [] and "file" in lines[0]


def test_an_open_issue_is_commented_only_when_there_is_new_evidence(filed):
    old = [_ev(T1, "2026-11-02T01:00:00Z"), _ev(T1, "2026-11-03T01:00:00Z", run=2)]
    api = FakeApi(open_issues=[_issue(501, T1)])
    fs.file_flakes(api, old, NOW, dry=False)
    assert filed == []
    fs.file_flakes(api, old + [_ev(T1, "2026-11-07T10:00:00Z", run=3)], NOW, dry=False)
    assert len(filed) == 1 and "run 3" in filed[0]["red_comment"]


def test_a_closed_issue_is_reopened_not_duplicated_after_two_new_flakes(filed):
    api = FakeApi(closed_issues=[_issue(502, T1, closed_at="2026-11-04T00:00:00Z")])
    before_close = [_ev(T1, "2026-11-02T01:00:00Z"), _ev(T1, "2026-11-03T01:00:00Z", run=2)]
    fs.file_flakes(api, before_close + [_ev(T1, "2026-11-06T01:00:00Z", run=3)], NOW, dry=False)
    assert filed == [] and api.writes == []  # one flake since the close is not two
    fs.file_flakes(api, before_close + [_ev(T1, "2026-11-06T01:00:00Z", run=3), _ev(T1, "2026-11-07T01:00:00Z", run=4)],
                   NOW, dry=False)
    assert api.writes == [("PATCH", f"/repos/{fs.REPO}/issues/502", {"state": "open"})]
    assert len(filed) == 1


def test_a_dry_run_writes_nothing(filed):
    api = FakeApi()
    lines = fs.file_flakes(api, [_ev(T1, "2026-11-05T01:00:00Z"), _ev(T1, "2026-11-07T01:00:00Z", run=2)], NOW, dry=True)
    assert filed == [] and api.writes == [] and "would file" in lines[0]


def test_the_report_names_tests_seen_once_and_says_partial_when_the_read_stopped():
    api = SimpleNamespace(calls=7)
    text = fs.report([_ev(T1, "2026-11-06T01:00:00Z")], [{"name": "search-recall"}], [], api, "90 GitHub calls left")
    assert "PARTIAL" in text and T1 in text and "search-recall: 1" in text


# --- the quarantine (conftest) ----------------------------------------------

def _rep(when="call", failed=True, nodeid=T1):
    return SimpleNamespace(when=when, failed=failed, nodeid=nodeid)


def test_a_quarantined_failure_is_forgiven_in_a_required_job_only():
    from tests.conftest import quarantine_forgives

    q = frozenset({T1})
    assert quarantine_forgives(_rep(), q, mode="")
    assert quarantine_forgives(_rep(when="teardown"), q, mode="")
    assert not quarantine_forgives(_rep(when="setup"), q, mode="")  # no fixtures: never forgiven
    assert not quarantine_forgives(_rep(), q, mode="canary")  # the canary sees every outcome
    assert not quarantine_forgives(_rep(nodeid=T2), q, mode="")
    assert not quarantine_forgives(_rep(failed=False), q, mode="")


def test_an_unreadable_quarantine_is_empty_so_every_test_still_blocks(monkeypatch):
    from tests.conftest import quarantined_tests

    for bad in ("nope", '{"a": 1}', ""):
        monkeypatch.setenv("CI_QUARANTINE", bad)
        assert quarantined_tests() == frozenset()
    monkeypatch.setenv("CI_QUARANTINE", f'["{T1}", 3]')
    assert quarantined_tests() == frozenset({T1})


# --- the wiring (ci.yml + the scheduled workflow) ---------------------------

def _ci() -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())


def test_ci_reads_the_quarantine_and_hands_it_to_every_required_test_job():
    jobs = _ci()["jobs"]
    scope = jobs["change-scope"]
    assert scope["permissions"]["issues"] == "read"
    assert scope["outputs"]["quarantine"] == "${{ steps.quarantine.outputs.ids }}"
    step = next(s for s in scope["steps"] if s.get("id") == "quarantine")
    assert "labels=flaky-quarantine" in step["run"] and "ids='[]'" in step["run"]
    for job in ("fast-gate", "backend-tests", "native-backend-readers", "database-integration"):
        assert jobs[job]["env"]["CI_QUARANTINE"] == "${{ needs.change-scope.outputs.quarantine }}", job


def test_the_canary_runs_the_quarantine_and_can_never_block():
    jobs = _ci()["jobs"]
    canary = jobs["flaky-canary"]
    assert canary["continue-on-error"] is True
    assert "quarantine != '[]'" in canary["if"]
    assert "flaky-canary.sh" in canary["steps"][-1]["run"]
    for name, job in jobs.items():
        needs = job.get("needs") or []
        assert "flaky-canary" not in ([needs] if isinstance(needs, str) else needs), name
    script = (ROOT / ".github" / "scripts" / "flaky-canary.sh").read_text()
    assert "CI_QUARANTINE_MODE=canary" in script


def test_the_shared_tail_uploads_its_retries_for_the_sentinel():
    job = _ci()["jobs"]["database-integration"]
    assert job["env"]["FLAKY_RETRIES_FILE"] == "/tmp/flaky-retries.txt"
    up = next(s for s in job["steps"] if s.get("id") == "db_flaky_retries_upload")
    assert up["with"]["name"] == "flaky-retries-${{ github.run_attempt }}"
    assert "shared-tail" in up["if"] and up["with"]["if-no-files-found"] == "ignore"
    assert fs.RETRY_ARTIFACT.format(attempt="${{ github.run_attempt }}") == up["with"]["name"]


def test_the_sentinel_runs_daily_and_may_write_issues():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "flake-sentinel.yml").read_text())
    on = wf.get("on", wf.get(True))
    assert on["schedule"] == [{"cron": "40 15 * * *"}]
    assert wf["permissions"] == {"actions": "read", "contents": "read", "issues": "write"}
    assert "scripts/flake_sentinel.py" in wf["jobs"]["sentinel"]["steps"][-1]["run"]
