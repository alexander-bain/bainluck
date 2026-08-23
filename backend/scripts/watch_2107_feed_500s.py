#!/usr/bin/env python3
"""#2107 post-deploy watch — the falsifier the fix has to survive for SEVEN DAYS.

WHY THIS EXISTS AT ALL, AND WHY 24h IS NOT ENOUGH

`/api/feed` 500'd on every request on 2026-08-22 because a process-global
cache held ORM rows that one rollback could expire (see `routes/events.py`,
`TeamSnapshot`). The cert window that confirmed the diagnosis independently
also defined what would REFUTE the fix, and the number in it is the point:
**BAILUCK-ZK fired on 4 of 5 days**. A clean 24 h therefore has roughly a 1-in-5
chance of being clean by luck alone. Merging is not closure; a week of silence
is closure.

    closure = 7 CONSECUTIVE days, post-deploy, with BOTH arms clean:
      arm A — Sentry BAINLUCK-ZK 24 h event count is ZERO
      arm B — a 1 req/min GET /api/feed probe records ZERO 5xx

Both arms, because either alone is refutable. Sentry alone trusts that a
handled 500 still reports. The probe alone trusts that one requester's traffic
reaches every process.

THREE THINGS THIS REFUSES TO DO, each because the program has been burned by it

1. **PASS over no samples.** A window that collected nothing reports
   NO_SAMPLES, never PASS. An empty result is a response shape, not a fact
   (gotcha #53) — the trade backfill recorded ten weeks of SUCCESS on exactly
   this confusion.
2. **Span a restart silently.** A restart clears every process-global, so it
   also clears the state the watch is watching. `process_id` (added to
   `/api/health` by this same fix) changes on restart even when `dyno` does
   not; a day whose samples straddle two process ids is recorded with
   `restarted: true` and does NOT count toward the seven. The worker-horizon
   half of this program has been defeated five times by exactly this, always
   discovered afterwards in a number that would not add up.
3. **Infer coverage.** Which processes answered is RECORDED, not assumed.
   There is one web dyno as of 2026-08-23 (`heroku ps`: `web (Standard-2X) …
   web.1`), so the cert window's "both dynos" is not satisfiable today and the
   watch says so rather than quietly reporting it as met. If web scales, the
   coverage line starts showing more ids and the assertion becomes real
   without an edit here.

USAGE

    # one day's window (run it once per day, or from a scheduler)
    python3 scripts/watch_2107_feed_500s.py --minutes 60

    # a short confidence read that is explicitly NOT a day
    python3 scripts/watch_2107_feed_500s.py --minutes 5 --label smoke

    # where the seven days stand
    python3 scripts/watch_2107_feed_500s.py --summarize

Environment: `BAINLUCK_API` (required), `SENTRY_AUTH_TOKEN` (arm A; without it
arm A reports UNKNOWN and the day cannot count clean). Both live in the
untracked `~/.claude/.env` — never in a tracked file.

Exit codes follow the gate convention (gotcha #54): `0` clean, `1` a REAL
failure of the thing being watched, `3` could-not-measure. `1` is a result;
anything else non-zero is a story about the harness.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SENTRY_ORG = os.getenv("SENTRY_ORG", "bain-luck")
SENTRY_ISSUE_SHORT_ID = "BAINLUCK-ZK"
REQUIRED_CLEAN_DAYS = 7
DEFAULT_STATE = Path(__file__).resolve().parents[2] / "docs/audits/latency/2107-watch.jsonl"

RC_CLEAN = 0
RC_FAILED = 1
RC_CANNOT_MEASURE = 3


# ---------------------------------------------------------------- arm B: probe


def _get(url: str, timeout: float = 20.0):
    """Return (status, body_bytes). A transport error is status None.

    Deliberately NOT collapsed into a bare `except: return None`: a refused
    connection and a 500 are different facts and the whole point of this file
    is not to confuse two things that print the same (gotcha #36).
    """
    req = urllib.request.Request(url, headers={"User-Agent": "bainluck-2107-watch"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # a real status, just not 2xx
        return exc.code, exc.read()
    except Exception:
        return None, b""


def _identify_process(api: str) -> dict:
    """Ask which process answered. Absent fields are reported, not invented."""
    status, body = _get(f"{api}/api/health")
    if status != 200:
        return {"process_id": None, "dyno": None, "commit": None}
    try:
        payload = json.loads(body)
    except Exception:
        return {"process_id": None, "dyno": None, "commit": None}
    return {
        "process_id": payload.get("process_id"),
        "dyno": payload.get("dyno"),
        "commit": payload.get("commit"),
        "uptime_seconds": payload.get("uptime_seconds"),
    }


def run_probe(api: str, minutes: int, interval: float, limit: int) -> dict:
    """1 req/min against `/api/feed`, recording every status and every process."""
    deadline = time.monotonic() + minutes * 60
    statuses: Counter = Counter()
    processes: Counter = Counter()
    commits: Counter = Counter()
    failures: list[dict] = []
    samples = 0

    while True:
        stamp = datetime.now(timezone.utc).isoformat()
        status, _ = _get(f"{api}/api/feed?limit={limit}")
        samples += 1
        statuses[str(status)] += 1

        if status is None or status >= 500:
            # Only pay for the identity read when it is worth attributing.
            ident = _identify_process(api)
            failures.append({"at": stamp, "status": status, **ident})
            if ident.get("process_id"):
                processes[ident["process_id"]] += 1
            if ident.get("commit"):
                commits[ident["commit"]] += 1
        elif samples % 5 == 1:
            # Coverage sampling: every fifth probe, cheap enough to run all day.
            ident = _identify_process(api)
            if ident.get("process_id"):
                processes[ident["process_id"]] += 1
            if ident.get("commit"):
                commits[ident["commit"]] += 1

        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, interval))

    server_errors = sum(n for s, n in statuses.items() if s != "None" and int(s) >= 500)
    transport = statuses.get("None", 0)
    return {
        "samples": samples,
        "statuses": dict(statuses),
        "server_errors": server_errors,
        "transport_errors": transport,
        "failures": failures[:50],
        "process_ids": dict(processes),
        "commits": dict(commits),
        "restarted": len(processes) > 1,
    }


# --------------------------------------------------------------- arm A: sentry


def sentry_24h_count(token: str | None) -> dict:
    """BAINLUCK-ZK's events in the last 24 h.

    Reads the 24 h STATS buckets, never the issue's `count` — that field is
    LIFETIME (gotcha #49), and a dormant bug shows thousands there while firing
    zero today. Reading it would make this watch permanently, confidently red.
    """
    if not token:
        return {"verdict": "UNKNOWN", "reason": "SENTRY_AUTH_TOKEN not set", "count_24h": None}

    query = urllib.parse.urlencode({"query": f"issue:{SENTRY_ISSUE_SHORT_ID}", "statsPeriod": "24h"})
    url = f"https://sentry.io/api/0/organizations/{SENTRY_ORG}/issues/?{query}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            issues = json.loads(resp.read())
    except Exception as exc:
        return {"verdict": "UNKNOWN", "reason": f"{type(exc).__name__}", "count_24h": None}

    if not issues:
        # The issue not being returned for a 24h window is the CLEAN reading —
        # but say which reading it is, so nobody later mistakes it for "the
        # issue does not exist" (gotcha #53 again).
        return {"verdict": "CLEAN", "reason": "no 24h events for this issue", "count_24h": 0}

    buckets = (issues[0].get("stats") or {}).get("24h") or []
    total = sum(int(point[1]) for point in buckets if len(point) > 1)
    return {
        "verdict": "CLEAN" if total == 0 else "FIRED",
        "count_24h": total,
        "issue_id": issues[0].get("id"),
        "reason": None if total == 0 else f"{total} events in 24h",
    }


# ------------------------------------------------------------------- verdicts


def grade_window(probe: dict, sentry: dict, counts_as_day: bool) -> dict:
    reasons = []
    if probe["samples"] == 0:
        verdict = "NO_SAMPLES"
        reasons.append("probe collected zero samples — this is not a pass")
    elif probe["server_errors"] > 0:
        verdict = "FAILED"
        reasons.append(f"{probe['server_errors']} 5xx on /api/feed")
    elif sentry["verdict"] == "FIRED":
        verdict = "FAILED"
        reasons.append(f"BAINLUCK-ZK {sentry['reason']}")
    elif sentry["verdict"] == "UNKNOWN":
        verdict = "INCONCLUSIVE"
        reasons.append(f"arm A unreadable ({sentry['reason']}) — one arm is not the falsifier")
    elif probe["restarted"]:
        verdict = "INCONCLUSIVE"
        reasons.append(
            "the web process restarted mid-window, which clears the very state under watch"
        )
    elif probe["transport_errors"] > 0:
        verdict = "INCONCLUSIVE"
        reasons.append(f"{probe['transport_errors']} transport errors — cannot attribute")
    elif not probe["process_ids"]:
        # No `process_id` came back at any point, so the window cannot say WHICH
        # process it cleared — and a coverage arm that measured nothing must not
        # be scored as a coverage arm that passed. Expected before this fix
        # deploys, since `process_id` ships with it.
        verdict = "INCONCLUSIVE"
        reasons.append(
            "no process_id observed — /api/health predates this fix, so coverage is unmeasured"
        )
    else:
        verdict = "CLEAN"

    return {
        "verdict": verdict,
        "reasons": reasons,
        "counts_toward_seven": bool(counts_as_day and verdict == "CLEAN"),
    }


def summarize(state_path: Path) -> int:
    if not state_path.exists():
        print(f"#2107 watch: NO STATE at {state_path} — nothing has been recorded yet.")
        print("  Closure requires 7 consecutive clean days. Recorded so far: 0.")
        return RC_CANNOT_MEASURE

    rows = [json.loads(line) for line in state_path.read_text().splitlines() if line.strip()]
    days = [r for r in rows if r.get("counts_toward_seven") is not None and r.get("is_day")]
    streak = 0
    for row in reversed(days):
        if row.get("counts_toward_seven"):
            streak += 1
        else:
            break

    print(f"#2107 watch — {state_path}")
    print(f"  windows recorded: {len(rows)}   day-windows: {len(days)}")
    for row in days[-10:]:
        print(
            f"   {row.get('started_at', '?')[:19]}  {row['grade']['verdict']:<13}"
            f" samples={row['probe']['samples']:<5} 5xx={row['probe']['server_errors']}"
            f" sentry24h={row['sentry'].get('count_24h')}"
            f" processes={len(row['probe'].get('process_ids') or {})}"
        )
    print(f"  consecutive clean days: {streak}/{REQUIRED_CLEAN_DAYS}")
    if streak >= REQUIRED_CLEAN_DAYS:
        print("  VERDICT: CLOSABLE — the 7-day falsifier was not refuted.")
        return RC_CLEAN
    print(f"  VERDICT: OPEN — {REQUIRED_CLEAN_DAYS - streak} more clean day(s) required.")
    print("  Merge is not closure. Do not close #2107 on this.")
    return RC_FAILED


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=int, default=60, help="probe window length")
    ap.add_argument("--interval", type=float, default=60.0, help="seconds between probes")
    ap.add_argument("--limit", type=int, default=20, help="/api/feed?limit=")
    ap.add_argument("--label", default="day", help="'day' counts toward the seven; anything else does not")
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()

    if args.summarize:
        return summarize(args.state)

    api = os.getenv("BAINLUCK_API")
    if not api:
        print("#2107 watch: CANNOT MEASURE — BAINLUCK_API is not set (source ~/.claude/.env)")
        return RC_CANNOT_MEASURE

    started = datetime.now(timezone.utc)
    print(f"#2107 watch — probing {api}/api/feed every {args.interval:.0f}s for {args.minutes}m")

    probe = run_probe(api, args.minutes, args.interval, args.limit)
    sentry = sentry_24h_count(os.getenv("SENTRY_AUTH_TOKEN"))
    grade = grade_window(probe, sentry, counts_as_day=(args.label == "day"))

    row = {
        "issue": 2107,
        "label": args.label,
        "is_day": args.label == "day",
        "started_at": started.isoformat(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "probe": probe,
        "sentry": sentry,
        "grade": grade,
        "counts_toward_seven": grade["counts_toward_seven"],
    }

    args.state.parent.mkdir(parents=True, exist_ok=True)
    with args.state.open("a") as fh:
        fh.write(json.dumps(row) + "\n")

    print(json.dumps({k: row[k] for k in ("label", "probe", "sentry", "grade")}, indent=2))
    print(f"   recorded -> {args.state}")

    if grade["verdict"] == "CLEAN":
        return RC_CLEAN
    if grade["verdict"] == "FAILED":
        return RC_FAILED
    return RC_CANNOT_MEASURE


if __name__ == "__main__":
    sys.exit(main())
