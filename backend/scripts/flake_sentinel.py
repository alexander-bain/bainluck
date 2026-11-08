#!/usr/bin/env python3
"""#12252 item 2 — the flake sentinel: a test that fails and then passes on the SAME commit
twice within 7 days gets one issue and leaves the required jobs until that issue closes.

Nov 6: four of seven shared-tail attempts failed on near-identical code and each one cost a
deploy and ~25 min of somebody re-running it. Decide 55-A's retry-once (#12250) is the
stopgap; this is the ledger that names the rigs and takes them off the merge path.

EVIDENCE (both read from GitHub, nothing from a person):
  * a JOB that concluded ``failure`` and later ``success`` on the same head commit — a
    re-run attempt, or a new run on that commit. The tests named ``FAILED``/``ERROR`` in
    the failed job's log are the flaked tests. A job that failed with no test named
    (a setup step, a cascade) is reported as job-level and never filed.
  * a 55-A retry INSIDE a job: the shared tail's conftest hook writes each re-run nodeid
    to ``$FLAKY_RETRIES_FILE`` and CI uploads it as ``flaky-retries-<attempt>`` (the
    annotation text stays as well). Listing those artifacts is one call per page, where
    reading annotations would be one call per job — GITHUB_TOKEN gets 1,000 calls an hour.

FILING goes through ``reconcile_issue`` (the one sentinel rail): title ``Flaky: <test id>``,
one issue per test (fingerprint = sha256 of the id), label ``flaky-quarantine``. A test
whose issue was CLOSED and that flakes twice again after the close gets the same issue
REOPENED, never a duplicate. An open issue gets a comment only when there is new evidence
since the last daily run. The sentinel never closes an issue: a person closes it when the
rig is fixed, and the test is back in the required jobs on the next run.

QUARANTINE is read by CI, not written here: ``ci.yml``'s change-scope lists the open
``flaky-quarantine`` issues, the required jobs stop failing on those tests (conftest), and
the non-required ``flaky-canary`` job runs them for real.

  python3 scripts/flake_sentinel.py --dry-run   # report only (no issue writes)
  python3 scripts/flake_sentinel.py             # report + file/reopen/comment
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.agent_origin import tagged  # noqa: E402

REPO = "alexander-bain/bainluck"
API = "https://api.github.com"
WORKFLOW = "ci.yml"
WINDOW_DAYS = 7
THRESHOLD = 2
MARKER_KEY = "flaky-test-fingerprint"
QUARANTINE_LABEL = "flaky-quarantine"
TITLE_PREFIX = "Flaky: "
RETRY_ARTIFACT = "flaky-retries-{attempt}"
RETRY_ATTEMPTS = (1, 2, 3)
# Stop reading (and say so) before the token's hourly budget is spent.
RATE_FLOOR = 100
# Evidence newer than this is "new since the last daily run" (the cron is late by hours).
NEW_EVIDENCE_HOURS = 30

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# `-v` lines ("tests/x.py::t FAILED") and the short summary ("FAILED tests/x.py::t - ...").
_FAILED_AFTER = re.compile(r"(tests/[\w/.-]+\.py::\S+?) (?:FAILED|ERROR)\b")
_FAILED_BEFORE = re.compile(r"(?:FAILED|ERROR) (tests/[\w/.-]+\.py::\S+)")


@dataclass(frozen=True)
class Event:
    test: str
    sha: str
    run_id: int
    attempt: int
    job: str
    at: str  # ISO time of the failed attempt
    kind: str  # "rerun" (job failed, later passed) or "retry" (55-A retry inside a job)

    def link(self) -> str:
        return f"https://github.com/{REPO}/actions/runs/{self.run_id}/attempts/{self.attempt}"


class RateLimited(RuntimeError):
    pass


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Job logs and artifact zips redirect to signed storage URLs, which refuse (401) a
    request that still carries the GitHub token — and must never receive it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.remove_header("Authorization")
        return new


_OPENER = urllib.request.build_opener(_DropAuthOnRedirect)


def _where(url: str) -> str:
    """A URL safe to print: no query string (a signed storage URL's query is its key)."""
    parts = urllib.parse.urlsplit(url)
    return f"{parts.netloc}{parts.path}"


class Api:
    def __init__(self, token: str):
        self.token = token
        self.calls = 0
        self.remaining: int | None = None

    def _fetch(self, url: str, method: str = "GET", data: dict | None = None) -> bytes:
        if self.remaining is not None and self.remaining < RATE_FLOOR:
            raise RateLimited(f"{self.remaining} GitHub calls left this hour")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(url if url.startswith("http") else API + url, data=body,
                                     headers=tagged(url, headers), method=method)
        for attempt in range(3):  # GitHub answers 502/503 or cuts a big body off now and then
            self.calls += 1
            try:
                with _OPENER.open(req, timeout=60) as resp:
                    payload = resp.read()
                    left = resp.headers.get("X-RateLimit-Remaining")
                if left is not None and left.isdigit():
                    self.remaining = int(left)
                return payload
            except urllib.error.HTTPError as exc:
                if exc.code < 500 or attempt == 2:
                    raise
            except (http.client.IncompleteRead, urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
            time.sleep(2 * (attempt + 1))
        raise AssertionError("unreachable")

    def get(self, path: str):
        return json.loads(self._fetch(path) or b"null")

    def raw(self, path: str) -> bytes:
        return self._fetch(path)

    def write(self, method: str, path: str, data: dict):
        return json.loads(self._fetch(path, method, data) or b"null")


# ---------------------------------------------------------------------------
# Pure logic (unit-tested without the network)
# ---------------------------------------------------------------------------

def failed_test_ids(log: str) -> set[str]:
    text = _ANSI.sub("", log)
    return set(_FAILED_AFTER.findall(text)) | set(_FAILED_BEFORE.findall(text))


def candidate_run_ids(runs: list[dict]) -> set[int]:
    """Runs whose jobs can hold a fail-then-pass: a re-run attempt, or a commit that has
    both a failed and a successful run. Everything else is never read job by job."""
    by_sha: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        by_sha[r["head_sha"]].append(r)
    out: set[int] = set()
    for rs in by_sha.values():
        out.update(r["id"] for r in rs if (r.get("run_attempt") or 1) > 1)
        concl = {r.get("conclusion") for r in rs}
        if "failure" in concl and "success" in concl:
            out.update(r["id"] for r in rs)
    return out


def failed_then_passed(jobs: list[dict]) -> list[dict]:
    """Jobs (all attempts, all runs, ONE commit) that failed while a later job of the same
    name on that commit succeeded."""
    by_name: dict[str, list[dict]] = defaultdict(list)
    for j in jobs:
        by_name[j["name"]].append(j)
    out = []
    for js in by_name.values():
        js = sorted(js, key=lambda j: j.get("started_at") or "")
        for i, j in enumerate(js):
            if j.get("conclusion") == "failure" and any(k.get("conclusion") == "success" for k in js[i + 1:]):
                out.append(j)
    return out


def fingerprint(test: str) -> str:
    return hashlib.sha256(test.encode()).hexdigest()[:12]


def flaky(events: list[Event], since: str | None = None) -> dict[str, list[Event]]:
    """Tests with THRESHOLD or more events (after ``since`` when given)."""
    by: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        if since is None or e.at > since:
            by[e.test].append(e)
    return {t: sorted(es, key=lambda e: e.at) for t, es in by.items() if len(es) >= THRESHOLD}


def issue_body(test: str, events: list[Event]) -> str:
    rows = "\n".join(f"- {e.at[:16].replace('T', ' ')}Z `{e.sha[:10]}` {e.job} — "
                     f"{'failed, then passed on a re-run' if e.kind == 'rerun' else 'failed, passed on its 55-A retry'}"
                     f" ([run {e.run_id}, attempt {e.attempt}]({e.link()}))" for e in events)
    return (
        f"PILLAR: TRUTH. **Ship:** a lane's merge stops waiting on a test that fails and then "
        f"passes on the same commit.\n\n"
        f"`{test}` failed and then passed on the same commit {len(events)} times in the last "
        f"{WINDOW_DAYS} days (the flake sentinel's bar is {THRESHOLD}):\n\n{rows}\n\n"
        f"**While this issue is open the test is quarantined:** the required CI jobs do not fail "
        f"on it (each failure prints a `Quarantined flaky test` warning), and the non-required "
        f"`flaky-canary` job runs it for real and reports. **Close this issue when the rig is "
        f"fixed**; the next CI run puts the test back in the required jobs. If it flakes twice "
        f"again after that, the sentinel reopens this issue rather than filing a new one.\n\n"
        f"Filed by `backend/scripts/flake_sentinel.py` (#12252 item 2), daily.\n\n"
        f"<sub>`{MARKER_KEY}:{fingerprint(test)}`  (dedupe key — do not remove)</sub>"
    )


def evidence_comment(test: str, new: list[Event]) -> str:
    return (f"Flake sentinel: {len(new)} new fail-then-pass event(s) for `{test}`:\n\n"
            + "\n".join(f"- `{e.sha[:10]}` {e.job} ([run {e.run_id}, attempt {e.attempt}]({e.link()}))"
                        for e in new))


# ---------------------------------------------------------------------------
# Reading GitHub
# ---------------------------------------------------------------------------

def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def list_runs(api: Api, now: dt.datetime) -> list[dict]:
    runs = []
    for d in range(WINDOW_DAYS):  # one day per query: a search caps at 1,000 results
        hi, lo = now - dt.timedelta(days=d), now - dt.timedelta(days=d + 1)
        page = 1
        while True:
            b = api.get(f"/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?created={_iso(lo)}..{_iso(hi)}"
                        f"&per_page=100&page={page}")
            runs += b.get("workflow_runs", [])
            if len(b.get("workflow_runs", [])) < 100:
                break
            page += 1
    return runs


def rerun_events(api: Api, runs: list[dict]) -> tuple[list[Event], list[dict]]:
    sha_of = {r["id"]: r["head_sha"] for r in runs}
    jobs_by_sha: dict[str, list[dict]] = defaultdict(list)
    for rid in sorted(candidate_run_ids(runs)):
        page = 1
        while True:
            b = api.get(f"/repos/{REPO}/actions/runs/{rid}/jobs?filter=all&per_page=100&page={page}")
            jobs_by_sha[sha_of[rid]] += b.get("jobs", [])
            if len(b.get("jobs", [])) < 100:
                break
            page += 1
    events, job_level = [], []
    for sha, jobs in jobs_by_sha.items():
        for j in failed_then_passed(jobs):
            log = api.raw(f"/repos/{REPO}/actions/jobs/{j['id']}/logs").decode("utf-8", "replace")
            tests = failed_test_ids(log)
            if not tests:
                job_level.append(j)
            for t in sorted(tests):
                events.append(Event(t, sha, j["run_id"], j.get("run_attempt") or 1, j["name"],
                                    j.get("started_at") or "", "rerun"))
    return events, job_level


def retry_events(api: Api, since: str) -> list[Event]:
    events = []
    for attempt in RETRY_ATTEMPTS:
        page = 1
        while True:
            b = api.get(f"/repos/{REPO}/actions/artifacts?name={RETRY_ARTIFACT.format(attempt=attempt)}"
                        f"&per_page=100&page={page}")
            arts = b.get("artifacts", [])
            for a in arts:
                if a.get("expired") or (a.get("created_at") or "") < since:
                    continue
                run = a.get("workflow_run") or {}
                blob = api.raw(a["archive_download_url"])
                with zipfile.ZipFile(io.BytesIO(blob)) as z:
                    for name in z.namelist():
                        for line in z.read(name).decode("utf-8", "replace").splitlines():
                            if re.fullmatch(r"tests/[\w/.-]+\.py::\S+", line.strip()):
                                events.append(Event(line.strip(), run.get("head_sha") or "", run.get("id") or 0,
                                                    attempt, "database-integration (shared-tail)",
                                                    a.get("created_at") or "", "retry"))
            if len(arts) < 100:
                break
            page += 1
    return events


def flaky_issues(api: Api, state: str) -> list[dict]:
    out, page = [], 1
    while True:
        b = api.get(f"/repos/{REPO}/issues?state={state}&labels={QUARANTINE_LABEL}&per_page=100&page={page}")
        out += [i for i in b if "pull_request" not in i]
        if len(b) < 100:
            break
        page += 1
    return out


def _owner(issues: list[dict], test: str) -> dict | None:
    from app.tasks.sentinel_filing import declared_fingerprints

    fp = (MARKER_KEY, fingerprint(test))
    owned = [i for i in issues if fp in declared_fingerprints(i.get("body"))]
    return min(owned, key=lambda i: i["number"]) if owned else None


# ---------------------------------------------------------------------------
# Filing
# ---------------------------------------------------------------------------

def file_flakes(api: Api, events: list[Event], now: dt.datetime, dry: bool) -> list[str]:
    from app.tasks.sentinel_filing import reconcile_issue

    lines = []
    window = _iso(now - dt.timedelta(days=WINDOW_DAYS))
    recent = _iso(now - dt.timedelta(hours=NEW_EVIDENCE_HOURS))
    open_issues, closed_issues = flaky_issues(api, "open"), flaky_issues(api, "closed")
    for test, evs in sorted(flaky(events, since=window).items()):
        is_open, was_closed = _owner(open_issues, test), _owner(closed_issues, test)
        if is_open:
            new = [e for e in evs if e.at > recent]
            if not new:
                lines.append(f"- `{test}`: {len(evs)} events, issue #{is_open['number']} open, nothing new")
                continue
            action = "comment"
        elif was_closed:
            after = flaky([e for e in evs if e.at > (was_closed.get("closed_at") or "")])
            if test not in after:
                lines.append(f"- `{test}`: {len(evs)} events, #{was_closed['number']} closed and fewer than "
                             f"{THRESHOLD} since — not reopened")
                continue
            evs, new, action = after[test], after[test], "reopen"
        else:
            new, action = evs, "file"
        if dry:
            lines.append(f"- `{test}`: {len(evs)} events — would {action}")
            continue
        if action == "reopen":
            api.write("PATCH", f"/repos/{REPO}/issues/{was_closed['number']}", {"state": "open"})
        result = reconcile_issue(
            red=True, fingerprint=fingerprint(test), marker_key=MARKER_KEY,
            labels=["alert-intake", "needs-agent", "area:infra", "type:bug", "priority:p2", QUARANTINE_LABEL],
            title=f"{TITLE_PREFIX}{test}", body=issue_body(test, evs), title_prefix=None,
            red_comment=evidence_comment(test, new), add_to_board=False,
        )
        lines.append(f"- `{test}`: {len(evs)} events — {action}: {result.get('action')} "
                     f"#{result.get('issue') or (was_closed or {}).get('number')}")
    return lines


def report(events: list[Event], job_level: list[dict], filed: list[str], api: Api, partial: str | None) -> str:
    by: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        by[e.test].append(e)
    seen = sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out = [f"## Flake sentinel — last {WINDOW_DAYS} days ({api.calls} GitHub calls)"]
    if partial:
        out.append(f"\n**PARTIAL — {partial}. Tests below are a lower bound; nothing is reported as clean.**")
    out.append(f"\n**{THRESHOLD}+ fail-then-pass events (filed or kept):**")
    out += filed or ["- none"]
    once = [(t, es) for t, es in seen if len(es) < THRESHOLD]
    out.append("\n**Seen once this week (watch, not filed):**")
    out += [f"- `{t}` — {es[0].job}, `{es[0].sha[:10]}` ([run]({es[0].link()}))" for t, es in once] or ["- none"]
    out.append(f"\n**Jobs that failed then passed with no test named** (setup step or cascade, never filed): "
               f"{len(job_level)}")
    names = defaultdict(int)
    for j in job_level:
        names[j["name"]] += 1
    out += [f"- {n}: {c}" for n, c in sorted(names.items(), key=lambda kv: -kv[1])]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GITHUB_TOKEN unset — nothing read", file=sys.stderr)
        return 2
    api, now = Api(token), dt.datetime.now(dt.timezone.utc)
    events, job_level, partial, filed = [], [], None, []
    try:
        runs = list_runs(api, now)
        events, job_level = rerun_events(api, runs)
        events += retry_events(api, _iso(now - dt.timedelta(days=WINDOW_DAYS)))
        filed = file_flakes(api, events, now, args.dry_run)
    except RateLimited as exc:
        partial = str(exc)
    except urllib.error.HTTPError as exc:
        partial = f"GitHub returned {exc.code} on {_where(exc.url or '')}"
    text = report(events, job_level, filed, api, partial)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write(text + "\n")
    return 1 if partial else 0


if __name__ == "__main__":
    sys.exit(main())
