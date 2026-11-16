"""Red-master alarm (Fable, Mon Nov 16, item 3).

When a CI run on a push to master finishes red, post ONE line on the NOW-lines
issue within minutes, so no lane has to notice by hand. On Nov 16 master sat
red from 12:09 AM to 5:23 AM PT before anyone read it.

    stuck: master red, <failing tests or jobs>, <run link>

Run by ``.github/workflows/master-red-alarm.yml`` on ``workflow_run`` of CI.
GitHub API only (standard library, ``GH_TOKEN``); never reads production.
Posts nothing for a green or cancelled run, and never posts twice for the same
run and attempt: each line carries a hidden marker that is checked first.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import subprocess
from typing import Iterable, Optional

#: The line is only for runs that really failed. `cancelled` is a superseded
#: run (concurrency), not a red master.
RED_CONCLUSIONS = ("failure", "timed_out")
MAX_TESTS = 5

_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s?")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
#: pytest's short test summary: `FAILED tests/x.py::T::t[p] - msg` and
#: `ERROR tests/x.py - msg` (a collection or fixture error).
_FAILED = re.compile(r"^(?:FAILED|ERROR) (tests/\S+)")


def failed_tests(log_text: str) -> list[str]:
    """Distinct pytest node ids from a job log's short summary, in order."""
    seen: list[str] = []
    for raw in log_text.splitlines():
        line = _TIMESTAMP.sub("", _ANSI.sub("", raw)).strip()
        match = _FAILED.match(line)
        if match and match.group(1) not in seen:
            seen.append(match.group(1))
    return seen


def marker(run_id: int, attempt: int) -> str:
    return f"<!-- master-red-alarm run={run_id} attempt={attempt} -->"


def already_posted(bodies: Iterable[str], run_id: int, attempt: int) -> bool:
    mark = marker(run_id, attempt)
    return any(mark in (body or "") for body in bodies)


def pr_reference(title: str) -> Optional[str]:
    """`#12345` from a squash title `... (#12345)` or `Merge pull request #12345`."""
    match = re.search(r"\(#(\d+)\)\s*$", title) or re.search(r"Merge pull request #(\d+)", title)
    return f"#{match.group(1)}" if match else None


def compose(
    *,
    run_id: int,
    attempt: int,
    run_url: str,
    sha: str,
    title: str,
    conclusion: str,
    tests: list[str],
    failed_jobs: list[str],
) -> str:
    if tests:
        shown = ", ".join(f"`{t}`" for t in tests[:MAX_TESTS])
        if len(tests) > MAX_TESTS:
            shown += f" and {len(tests) - MAX_TESTS} more"
    elif failed_jobs:
        shown = "no failing test line found; failed jobs: " + ", ".join(
            f"`{j}`" for j in failed_jobs
        )
    else:
        shown = f"run concluded `{conclusion}` with no failed job listed"
    ref = pr_reference(title)
    headline = title.splitlines()[0][:120] if title else ""
    what = f"{ref} " if ref else ""
    return (
        f"stuck: master red, {shown}, [run {run_id}]({run_url})"
        + (f" (attempt {attempt})" if attempt > 1 else "")
        + f"\n\nMaster `{sha[:10]}` — {what}{headline}. "
        "Posted automatically by `master-red-alarm.yml`; no deploy goes out until master is green. "
        "Read the failing job before any re-run.\n\n"
        + marker(run_id, attempt)
    )


# ── GitHub calls through `gh` (not exercised by the unit tests) ─────────────
# `gh api` follows the job-log redirect to blob storage without forwarding the
# token, which a hand-rolled urllib redirect would (and storage refuses).


def _gh(*args: str, body: Optional[dict] = None) -> str:
    cmd = ["gh", "api", *args]
    if body is not None:
        cmd += ["--input", "-"]
    done = subprocess.run(
        cmd,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if done.returncode != 0 and "--allow-escape-sequences" in done.stderr and body is None:
        # Newer gh refuses to print a body holding terminal escapes, and job logs
        # carry pytest's colours. Older gh has no such flag, so ask only when told.
        done = subprocess.run(
            [*cmd, "--allow-escape-sequences"], capture_output=True, text=True, timeout=120
        )
    if done.returncode != 0:
        raise RuntimeError(f"gh api {args[0]} exited {done.returncode}: {done.stderr.strip()[:300]}")
    return done.stdout


def _recent_comment_bodies(repo: str, issue: int) -> list[str]:
    """Every comment body on the NOW-lines issue (GitHub caps an issue at 2,500)."""
    out = _gh(f"repos/{repo}/issues/{issue}/comments?per_page=100", "--paginate", "--jq", ".[].body | @json")
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print the line; post nothing")
    args = ap.parse_args(argv)

    repo = os.environ["REPO"]
    issue = int(os.environ["NOW_LINES_ISSUE"])
    run_id = int(os.environ["RUN_ID"])

    run = json.loads(_gh(f"repos/{repo}/actions/runs/{run_id}"))
    attempt = int(run.get("run_attempt") or 1)
    conclusion = run.get("conclusion") or ""
    if run.get("event") != "push" or run.get("head_branch") != "master":
        print(f"run {run_id} is {run.get('event')} on {run.get('head_branch')}; not master")
        return 0
    if conclusion not in RED_CONCLUSIONS:
        print(f"run {run_id} concluded {conclusion!r}; nothing to post")
        return 0

    jobs = json.loads(
        _gh(f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100")
    ).get("jobs", [])
    failed = [j for j in jobs if j.get("conclusion") in RED_CONCLUSIONS]
    tests: list[str] = []
    for job in failed:
        try:
            log = _gh(f"repos/{repo}/actions/jobs/{job['id']}/logs")
        except (RuntimeError, subprocess.TimeoutExpired) as err:  # an expired log
            print(f"log for job {job['id']} unavailable: {err}")
            continue
        for node in failed_tests(log):
            if node not in tests:
                tests.append(node)

    line = compose(
        run_id=run_id,
        attempt=attempt,
        run_url=run.get("html_url") or f"https://github.com/{repo}/actions/runs/{run_id}",
        sha=run.get("head_sha") or "",
        title=(run.get("head_commit") or {}).get("message") or run.get("display_title") or "",
        conclusion=conclusion,
        tests=tests,
        failed_jobs=[j.get("name", "?") for j in failed],
    )
    print(line)
    if args.dry_run:
        return 0
    if already_posted(_recent_comment_bodies(repo, issue), run_id, attempt):
        print(f"already posted for run {run_id} attempt {attempt}")
        return 0
    _gh(f"repos/{repo}/issues/{issue}/comments", "--method", "POST", body={"body": line})
    print(f"posted on #{issue}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
