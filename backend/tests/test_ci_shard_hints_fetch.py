"""`scripts/ci_shard_hints_fetch.py`: the shard timings come from green master
runs' artifacts, every shard of one run applies the same one, and a failure after
the choice is loud (a shard that fell back alone would split the suite apart from
its siblings). No network: a fake opener answers by URL."""

import io
import json
import sys
import urllib.error
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ci_shard_hints_fetch as f  # noqa: E402

RUN = "2026-11-16T12:00:00Z"
GOOD = {"_comment": "x", "files": {"tests/test_a.py": 1.5, "tests/test_b.py": 0.0}}


def _zip(payload, member=f.MEMBER):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, payload if isinstance(payload, str) else json.dumps(payload))
    return buf.getvalue()


def _art(aid, created, branch="master", expired=False):
    return {"id": aid, "name": f.ARTIFACT, "created_at": created, "expired": expired,
            "archive_download_url": f"https://dl/{aid}", "workflow_run": {"id": 900 + aid, "head_branch": branch}}


class Fake:
    def __init__(self, artifacts, blobs, fail=None):
        self.artifacts, self.blobs, self.fail, self.calls = artifacts, blobs, fail or {}, []

    def __call__(self, req):
        url = req.full_url
        self.calls.append(url)
        if url in self.fail:
            exc = self.fail[url].pop(0) if isinstance(self.fail[url], list) else self.fail[url]
            if exc is not None:
                raise exc
        if "/actions/runs/" in url and "/jobs" not in url:
            return json.dumps({"created_at": RUN}).encode()
        if "/actions/artifacts" in url:
            return json.dumps({"artifacts": self.artifacts}).encode()
        return self.blobs[url]


def _apply(fake, tmp_path):
    target = tmp_path / "d.json"
    target.write_text('{"files": {"tests/committed.py": 1}}')
    rc = f.apply("o/r", "77", "tok", opener=fake, target=target, sleep=lambda s: None)
    return rc, json.loads(target.read_text())


def test_the_newest_master_artifact_made_before_this_run_is_applied(tmp_path):
    arts = [_art(1, "2026-11-16T09:00:00Z"), _art(2, "2026-11-16T11:00:00Z"),
            _art(3, "2026-11-16T13:00:00Z"),  # after this run started: a sibling shard might not see it
            _art(4, "2026-11-16T11:30:00Z", branch="feature"), _art(5, "2026-11-16T11:45:00Z", expired=True)]
    fake = Fake(arts, {"https://dl/2": _zip(GOOD)})
    rc, written = _apply(fake, tmp_path)
    assert rc == 0 and written["files"] == GOOD["files"]
    assert "https://dl/2" in fake.calls and "https://dl/3" not in fake.calls


def test_every_shard_of_one_run_chooses_the_same_artifact():
    arts = [_art(i, f"2026-11-16T0{i}:00:00Z") for i in range(1, 9)]
    assert len({f.choose(arts, RUN)["id"] for _ in range(8)}) == 1


def test_no_artifact_keeps_the_committed_file(tmp_path):
    rc, written = _apply(Fake([], {}), tmp_path)
    assert rc == 0 and written == {"files": {"tests/committed.py": 1}}


@pytest.mark.parametrize("blob", [
    _zip({"files": {}}), _zip({"files": {"tests/a.py": -1}}), _zip({"files": {"app/x.py": 1}}),
    _zip("not json"), _zip(GOOD, member="other.json"), b"not a zip",
])
def test_a_chosen_artifact_that_cannot_be_used_fails_loudly(tmp_path, blob):
    rc, written = _apply(Fake([_art(1, "2026-11-16T09:00:00Z")], {"https://dl/1": blob}), tmp_path)
    assert rc == 1 and written == {"files": {"tests/committed.py": 1}}


def test_a_listing_failure_fails_rather_than_falling_back(tmp_path):
    url = f"{f.API}/repos/o/r/actions/artifacts?name={f.ARTIFACT}&per_page=100"
    fake = Fake([], {}, fail={url: urllib.error.HTTPError(url, 403, "no", {}, None)})
    rc, _ = _apply(fake, tmp_path)
    assert rc == 1


def test_a_transient_error_is_retried(tmp_path):
    err = urllib.error.HTTPError("https://dl/1", 502, "bad gateway", {}, None)
    fake = Fake([_art(1, "2026-11-16T09:00:00Z")], {"https://dl/1": _zip(GOOD)}, fail={"https://dl/1": [err, None]})
    rc, written = _apply(fake, tmp_path)
    assert rc == 0 and written["files"] == GOOD["files"] and fake.calls.count("https://dl/1") == 2


def _jobs(steps_ran=True, n=8, conclusion="success"):
    return {"jobs": [
        {"id": 100 + i, "name": f"backend-tests ({i})", "conclusion": conclusion,
         "steps": [{"name": f"Run tests (shard {i}/8)", "conclusion": "success" if steps_ran else "skipped"}]}
        for i in range(1, n + 1)
    ] + [{"id": 1, "name": "frontend-build", "conclusion": "success", "steps": []}]}


class JobsFake:
    def __init__(self, jobs):
        self.jobs, self.calls = jobs, []

    def __call__(self, req):
        self.calls.append(req.full_url)
        if req.full_url.endswith("/jobs?filter=latest&per_page=100"):
            return json.dumps(self.jobs).encode()
        return f"2026-11-16T10:00:00.1Z 0.50s call     tests/test_{req.full_url.split('/')[-2]}.py::t\n".encode()


def test_job_logs_reads_each_shard_of_the_latest_attempt(tmp_path):
    out = tmp_path / "all.log"
    fake = JobsFake(_jobs())
    assert f.job_logs("o/r", "55", "tok", out, opener=fake, sleep=lambda s: None) == 0
    assert out.read_text().count("s call") == 8
    assert "/actions/runs/55/jobs?filter=latest" in fake.calls[0]  # per job: survives a re-run
    assert not any(c.endswith("/runs/55/logs") for c in fake.calls)  # never the run archive


def test_a_run_whose_shards_ran_no_tests_holds(tmp_path):
    assert f.job_logs("o/r", "55", "tok", tmp_path / "x", opener=JobsFake(_jobs(steps_ran=False)), sleep=lambda s: None) == f.HOLD


@pytest.mark.parametrize("jobs", [_jobs(n=7), _jobs(conclusion="failure")])
def test_a_partial_or_failed_set_of_shards_refuses(tmp_path, jobs):
    assert f.job_logs("o/r", "55", "tok", tmp_path / "x", opener=JobsFake(jobs), sleep=lambda s: None) == 1


# ── DECIDE: once per run, in change-scope (Fable, 9:35 PM Nov 17, #12797) ─────

COMMITTED = '{"files": {"tests/committed.py": 1}}'


def _decide(fake, tmp_path, rate=None, out=None):
    committed = tmp_path / "committed.json"
    committed.write_text(COMMITTED)
    out = out or (tmp_path / "run" / "ci_shard_durations.json")
    rc = f.decide("o/r", "77", "tok", out, opener=fake, committed=committed,
                  sleep=lambda s: None, rate=rate if rate is not None else {})
    return rc, (json.loads(out.read_text()) if out.exists() else None)


def test_decide_writes_the_newest_master_artifact_for_the_whole_run(tmp_path, capsys):
    arts = [_art(1, "2026-11-16T09:00:00Z"), _art(2, "2026-11-16T11:00:00Z"), _art(3, "2026-11-16T13:00:00Z")]
    fake = Fake(arts, {"https://dl/2": _zip(GOOD)})
    rc, written = _decide(fake, tmp_path)
    assert rc == 0 and written["files"] == GOOD["files"]
    assert len(fake.calls) == 3  # the run, the list, the download: three calls per run, not 27
    assert "artifact 2" in capsys.readouterr().out


@pytest.mark.parametrize("blob", [_zip({"files": {}}), _zip("not json"), b"not a zip"])
def test_decide_falls_back_to_the_committed_file_when_the_artifact_is_unusable(tmp_path, blob, capsys):
    rc, written = _decide(Fake([_art(1, "2026-11-16T09:00:00Z")], {"https://dl/1": blob}), tmp_path)
    assert rc == 0 and written == json.loads(COMMITTED)  # one decider: no sibling can disagree
    assert "the committed file" in capsys.readouterr().out


def test_decide_falls_back_when_github_refuses_the_listing(tmp_path, capsys):
    url = f"{f.API}/repos/o/r/actions/artifacts?name={f.ARTIFACT}&per_page=100"
    fake = Fake([], {}, fail={url: urllib.error.HTTPError(url, 403, "rate limited", {}, None)})
    rc, written = _decide(fake, tmp_path)
    assert rc == 0 and written == json.loads(COMMITTED)
    assert "HTTPError" in capsys.readouterr().out


def test_decide_never_retries_so_change_scope_cannot_stall(tmp_path):
    err = urllib.error.HTTPError("https://dl/1", 502, "bad gateway", {}, None)
    fake = Fake([_art(1, "2026-11-16T09:00:00Z")], {"https://dl/1": _zip(GOOD)}, fail={"https://dl/1": [err, None]})
    rc, written = _decide(fake, tmp_path)
    assert rc == 0 and written == json.loads(COMMITTED) and fake.calls.count("https://dl/1") == 1


def test_decide_with_no_artifact_writes_the_committed_file(tmp_path):
    rc, written = _decide(Fake([], {}), tmp_path)
    assert rc == 0 and written == json.loads(COMMITTED)


def test_decide_prints_the_token_budget_left(tmp_path, capsys):
    rate = {"x-ratelimit-limit": "15000", "x-ratelimit-remaining": "14321", "x-ratelimit-used": "679", "x-ratelimit-resource": "core"}
    _decide(Fake([], {}), tmp_path, rate=rate)
    assert "token budget: 14321 of 15000 left (core; 679 used this hour)" in capsys.readouterr().out


def test_decide_fails_only_when_it_cannot_write_a_decision(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")  # a file where the output's parent directory should be
    rc, _ = _decide(Fake([], {}), tmp_path, out=blocker / "ci_shard_durations.json")
    assert rc == 1


def test_decide_ends_at_its_deadline_with_the_committed_file(tmp_path, capsys):
    import time as _t

    class Slow(Fake):
        def __call__(self, req):
            _t.sleep(3)  # GitHub stalls; change-scope's step may not be waived
            return super().__call__(req)

    committed = tmp_path / "committed.json"
    committed.write_text(COMMITTED)
    out = tmp_path / "run" / "d.json"
    started = _t.monotonic()
    rc = f.decide("o/r", "77", "tok", out, opener=Slow([], {}), committed=committed,
                  sleep=lambda s: None, rate={}, deadline=1)
    assert rc == 0 and json.loads(out.read_text()) == json.loads(COMMITTED)
    assert _t.monotonic() - started < 2.5
    assert "deadline" in capsys.readouterr().out


def test_adopt_writes_only_a_valid_timings_file(tmp_path):
    src, target = tmp_path / "src.json", tmp_path / "hints.json"
    src.write_text(json.dumps(GOOD))
    target.write_text(COMMITTED)
    assert f.adopt(src, target=target) == 0
    assert json.loads(target.read_text())["files"] == GOOD["files"]


@pytest.mark.parametrize("text", [None, "not json", json.dumps({"files": {"app/x.py": 1}})])
def test_adopt_refuses_a_missing_or_malformed_file_and_keeps_the_hints(tmp_path, text):
    src, target = tmp_path / "src.json", tmp_path / "hints.json"
    if text is not None:
        src.write_text(text)
    target.write_text(COMMITTED)
    assert f.adopt(src, target=target) == 1
    assert target.read_text() == COMMITTED
