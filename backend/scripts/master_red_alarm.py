"""Red-master alarm (Fable, Mon Nov 16, item 3).

When a CI run on a push to master finishes red, post ONE line on the NOW-lines
issue within minutes, so no lane has to notice by hand. On Nov 16 master sat
red from 12:09 AM to 5:23 AM PT before anyone read it.

    stuck: master red, HOLD (server), <failing tests or jobs>, <run link>

The HOLD (Fable, 7:26 PM Tue Nov 17) stops server merges: only a back-out or a
fix for the named test merges while it holds. It ends at the first of (Fable,
6:06 AM Wed Nov 18): the next server "live" line; a green master run containing
the change that /api/health serves; Fable or Alex saying so.

The HOLD is written only when the run's ``deploy`` job did not succeed. A red
job outside deploy's needs (a canary, say) leaves the server deploying, so that
line reports the failure and holds nothing.

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
DEPLOY_JOB_NAMES = frozenset({"deploy", "deploy-after-full"})
NON_BLOCKING_JOB_NAMES = frozenset({"flaky-canary"})
MAX_TESTS = 5

_TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s?")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
#: pytest's short test summary: `FAILED tests/x.py::T::t[p] - msg` and
#: `ERROR tests/x.py - msg` (a collection or fixture error).
_FAILED = re.compile(r"^(?:FAILED|ERROR) (tests/\S+)")
#: `-v` output with no `-rf` summary (the real-Postgres gates run `-v -rs`):
#: `tests/x.py::t[p] FAILED [ 50%]`. The `::` keeps file progress lines out.
_VERBOSE = re.compile(r"^(tests/\S+::\S+) (?:FAILED|ERROR)\b")


def failed_tests(log_text: str) -> list[str]:
    """Distinct pytest node ids from a job log's short summary, in order."""
    seen: list[str] = []
    for raw in log_text.splitlines():
        line = _TIMESTAMP.sub("", _ANSI.sub("", raw)).strip()
        match = _FAILED.match(line) or _VERBOSE.match(line)
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
    deployed: bool = False,
    rerun: Optional[str] = None,
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
    blocking_failed = [j for j in failed_jobs if j not in NON_BLOCKING_JOB_NAMES]
    canary_only = deployed and bool(failed_jobs) and not blocking_failed
    if rerun is None:
        if deployed:
            rerun = "not_needed"
        elif attempt == 1:
            rerun = "triggered"
        else:
            rerun = "already_ran"
    if canary_only:
        hold, policy, procedure = (
            "",
            "This run's release still succeeded (only non-blocking canary failed), so the server slot is not held. ",
            "",
        )
    elif deployed:
        hold = "HOLD (no further merges until Fable posts a line), "
        release_tag = f"`{sha[:10]}`" + (f" ({ref})" if ref else "")
        policy = (
            f"Ruling 394(d): the full test run beside release {release_tag} went red "
            "(run concluded red after release succeeded). "
            "**No further merge happens until Fable posts a line.**"
        )
        procedure = ""
    else:
        hold = "HOLD (server), "
        policy = (
            "This run's `deploy` job did not succeed, so nothing from it reaches the server. "
            "Until the HOLD ends, only a back-out or a fix for the named test merges on the server; "
            "website and apps keep moving. "
            "The HOLD ends at the first of: the re-run passing; the next server \"live\" line; "
            "a green master run containing this change that `/api/health` serves; Fable or Alex saying so."
        )
        if rerun == "triggered":
            line1 = (
                "Ruling 241: A — This alarm re-ran the failed jobs once automatically "
                "(nobody needs to press re-run); when the re-run passes, the HOLD ends immediately "
                "and nobody waits for a repair PR."
            )
        elif rerun == "would_trigger":
            line1 = (
                "Ruling 241: A — On a live run this alarm re-runs the failed jobs once automatically "
                "(dry-run: not triggered); when the re-run passes, the HOLD ends immediately "
                "and nobody waits for a repair PR."
            )
        elif rerun.startswith("failed:"):
            detail = rerun[len("failed:"):].strip()
            line1 = (
                f"Ruling 241: A — Automatic re-run failed ({detail}); re-run the failed jobs once "
                "manually — when the re-run passes, the HOLD ends immediately and nobody waits for a repair PR."
            )
        else:
            line1 = (
                f"Ruling 241: A — The automatic re-run already ran and attempt {attempt} failed too "
                "(no further auto-rerun); back out last-in or land a fix for the named test."
            )
        line2 = (
            "If a timing test failed on master, passed on that re-run, and no change in the batch "
            "touched it, Builder E moves it within the hour to `flaky-canary` (non-blocking) via a "
            "tests-only PR (`backend/tests/timing_quarantine.json`) with an issue and 7 days to repair or delete it."
        )
        procedure = f"\n\n{line1}\n{line2}"
    release_label = f" beside release `{sha[:10]}`{f' ({ref})' if ref else ''}" if (deployed and not canary_only) else ""
    return (
        f"stuck: master red{release_label}, {hold}{shown}, [run {run_id}]({run_url})"
        + (f" (attempt {attempt})" if attempt > 1 else "")
        + f"\n\nMaster `{sha[:10]}` — {what}{headline}. "
        "Posted automatically by `master-red-alarm.yml`. "
        + policy
        + procedure
        + "\n\n"
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

    deployed = any(
        j.get("name") in DEPLOY_JOB_NAMES and j.get("conclusion") == "success" for j in jobs
    )

    if not args.dry_run and already_posted(_recent_comment_bodies(repo, issue), run_id, attempt):
        print(f"already posted for run {run_id} attempt {attempt}")
        return 0

    if deployed:
        rerun_state = "not_needed"
    elif attempt > 1:
        rerun_state = "already_ran"
    elif args.dry_run:
        rerun_state = "would_trigger"
    else:
        try:
            _gh(f"repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs", "--method", "POST")
            rerun_state = "triggered"
            print(f"triggered rerun-failed-jobs for run {run_id}")
        except (RuntimeError, subprocess.TimeoutExpired) as err:
            rerun_state = f"failed:{str(err).splitlines()[0][:140]}"
            print(f"rerun-failed-jobs failed for run {run_id}: {err}")

    line = compose(
        run_id=run_id,
        attempt=attempt,
        run_url=run.get("html_url") or f"https://github.com/{repo}/actions/runs/{run_id}",
        sha=run.get("head_sha") or "",
        title=(run.get("head_commit") or {}).get("message") or run.get("display_title") or "",
        conclusion=conclusion,
        tests=tests,
        failed_jobs=[j.get("name", "?") for j in failed],
        deployed=deployed,
        rerun=rerun_state,
    )
    print(line)
    if args.dry_run:
        return 0
    _gh(f"repos/{repo}/issues/{issue}/comments", "--method", "POST", body={"body": line})
    print(f"posted on #{issue}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
