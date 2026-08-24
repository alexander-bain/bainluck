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

FOUR THINGS THIS REFUSES TO DO, each because the program has been burned by it

1. **PASS over no samples.** A window that collected nothing reports
   NO_SAMPLES, never PASS. An empty result is a response shape, not a fact
   (gotcha #53) — the trade backfill recorded ten weeks of SUCCESS on exactly
   this confusion.
2. **Span a restart silently.** A restart clears every process-global, so it
   also clears the state the watch is watching. A window in which a worker's
   `uptime_seconds` RESETS — or in which a worker is born mid-window — is
   recorded with `restarted: true` and does NOT count toward the seven. The
   worker-horizon half of this program has been defeated five times by exactly
   this, always discovered afterwards in a number that would not add up.
   **Corrected 2026-08-24 (LAT-P085):** this test used to be `len(processes) >
   1`, i.e. "two ids answered" — but production runs one web dyno with
   `WEB_CONCURRENCY=2`, so two stable ids answer always (ruling 129: the two
   leaders were WEB_CONCURRENCY, not the dyno count). The predicate was
   unconditionally true and the falsifier could never bank a day. See
   `_detect_restart`.
3. **Infer coverage.** Which processes answered is RECORDED, not assumed.
   As of 2026-08-24 that is ONE web dyno x `WEB_CONCURRENCY=2` = two workers
   (`worker_count`), so the cert window's "both dynos" is not satisfiable today
   and the watch says so rather than quietly reporting it as met. If web scales,
   the coverage line starts showing more ids and the assertion becomes real
   without an edit here.
4. **Grade a window that straddles a release** (ruling 130, banked on this
   branch). A window containing a deploy measures two different systems and
   reports one number: it cannot FAIL (the errors may belong to the retired
   slug) and it cannot PASS (part of its duration certifies a slug that no
   longer runs). It is INCONCLUSIVE, a third verdict, logged and excluded from
   the seven — never silently dropped, because a run that discards windows and
   a run with nothing to report look identical (gotcha #53). Both arms are
   bound, and each arm's own interval decides it: arm B by the `commit` set
   observed **inside the window**, arm A by whether a release landed inside its
   **24 h lookback** (`--last-release-at`, or the recorded commit history — see
   `arm_a_release_window`). Arm A's straddle therefore does not suppress arm
   B's 5xx, which are still attributable to a single slug.

USAGE

    # one day's window (run it once per day, or from a scheduler)
    python3 scripts/watch_2107_feed_500s.py --minutes 60

    # a short confidence read that is explicitly NOT a day
    python3 scripts/watch_2107_feed_500s.py --minutes 5 --label smoke

    # a day whose arm-A lookback you can vouch for (ruling 130) — take the
    # timestamp from `heroku releases -a bainluck`, not from memory
    python3 scripts/watch_2107_feed_500s.py --minutes 60 \
        --counts-as-day --last-release-at 2026-08-22T18:04:00+00:00

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
# Arm A reads a rolling 24 h count, so its straddle question is about 24 h —
# not about the probe window's length. Keep the two intervals separate.
RELEASE_LOOKBACK_HOURS = 24
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
    started_monotonic = time.monotonic()
    deadline = started_monotonic + minutes * 60
    statuses: Counter = Counter()
    processes: Counter = Counter()
    commits: Counter = Counter()
    failures: list[dict] = []
    # pid -> {"first_uptime", "last_uptime", "born_at_elapsed"}. Seeing N process
    # ids is NOT a restart (see `_detect_restart`); an uptime that resets is.
    uptimes: dict[str, dict] = {}
    samples = 0

    def _note_uptime(ident: dict) -> None:
        pid, up = ident.get("process_id"), ident.get("uptime_seconds")
        if not pid or up is None:
            return
        elapsed = time.monotonic() - started_monotonic
        rec = uptimes.get(pid)
        if rec is None:
            uptimes[pid] = {"first_uptime": up, "last_uptime": up,
                            "born_at_elapsed": round(elapsed - up, 1)}
        else:
            if up < rec["last_uptime"]:
                rec["went_backwards"] = True
            rec["last_uptime"] = up

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
            _note_uptime(ident)
        elif samples % 5 == 1:
            # Coverage sampling: every fifth probe, cheap enough to run all day.
            ident = _identify_process(api)
            if ident.get("process_id"):
                processes[ident["process_id"]] += 1
            if ident.get("commit"):
                commits[ident["commit"]] += 1
            _note_uptime(ident)

        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, interval))

    server_errors = sum(n for s, n in statuses.items() if s != "None" and int(s) >= 500)
    transport = statuses.get("None", 0)
    restarted, restart_reasons = _detect_restart(uptimes)
    straddled, straddle_reasons = _detect_release(commits)
    return {
        "samples": samples,
        "statuses": dict(statuses),
        "server_errors": server_errors,
        "transport_errors": transport,
        "failures": failures[:50],
        "process_ids": dict(processes),
        "commits": dict(commits),
        # Ruling 129: a dyno runs WEB_CONCURRENCY workers, so the worker count is
        # dynos x WEB_CONCURRENCY. Recorded, not inferred (docstring point 3).
        "worker_count": len(processes),
        "uptimes": uptimes,
        "restarted": restarted,
        "restart_reasons": restart_reasons,
        "release_straddle": straddled,
        "release_reasons": straddle_reasons,
    }


def _detect_restart(uptimes: dict[str, dict]) -> tuple[bool, list[str]]:
    """A restart is an uptime that RESETS — not a second process id.

    `restarted` was `len(processes) > 1`, which reads "more than one worker
    answered" as "the web process restarted mid-window". Ruling 129 (banked on
    this branch at 79f1313b) is exactly that correction in the other direction:
    the two leaders were WEB_CONCURRENCY, not the dyno count. Production runs
    ONE web dyno with `WEB_CONCURRENCY=2`, so two stable process ids answer
    every hour of every day — measured 2026-08-24, both reporting uptime 6,701 s
    and climbing together. The old predicate was therefore not merely
    imprecise, it was **unconditionally true**, and every window it would ever
    grade was INCONCLUSIVE. A seven-day falsifier that cannot bank day one is
    not a strict falsifier; it is a broken one, and it fails in the direction
    where nobody goes looking, because "not yet closed" is the expected reading.

    Two direct signals, both from `uptime_seconds`, which was already collected:

    * an id whose uptime went BACKWARDS between samples — it restarted;
    * an id BORN during the window (`elapsed - uptime` meaningfully positive) —
      it did not exist when the window opened, so something started it.

    A 60 s tolerance absorbs boot and clock jitter. Neither signal fires for N
    stable long-lived workers, which is the healthy shape this must not flag.
    """
    reasons: list[str] = []
    for pid, rec in uptimes.items():
        if rec.get("went_backwards"):
            reasons.append(f"{pid[:12]} uptime reset mid-window")
        elif rec.get("born_at_elapsed", 0.0) > 60.0:
            reasons.append(
                f"{pid[:12]} was born {rec['born_at_elapsed']:.0f}s into the window"
            )
    return bool(reasons), reasons


def _detect_release(commits: dict) -> tuple[bool, list[str]]:
    """Arm B's straddle test: did the deployed commit CHANGE inside the window?

    Ruling 130. `/api/health` already reports `commit`, and `run_probe` already
    counts them — the signal was being collected and thrown away. Two or more
    distinct SHAs answering inside one window is a release landing inside it,
    full stop; there is no heuristic here about whether the release "could have"
    touched `/api/feed`, because the ruling decides on the boundary, not on a
    guess about relevance.

    Deliberately NOT the same test as `_detect_restart`. A restart with no new
    slug (a dyno cycle, a memory-quota kill) resets process-globals and is
    graded by the restart arm; a release with no restart is impossible on Heroku
    but the two signals still answer different questions and a window can trip
    exactly one of them. Collapsing them would print one reason for two causes,
    which is the failure this whole file is written against.

    Absent commits are ignored rather than counted as a change: `/api/health`
    predating the field reports `None`, and "the instrument cannot see it" is
    not "the value differed" (gotcha #53). That case is already caught by the
    `process_ids` arm.
    """
    seen = sorted(sha for sha in commits if sha)
    if len(seen) < 2:
        return False, []
    shown = ", ".join(sha[:12] for sha in seen)
    return True, [
        f"{len(seen)} distinct commits answered inside the window ({shown}) — "
        "a release landed mid-window"
    ]


def _parse_stamp(value: str | None) -> datetime | None:
    """ISO8601 -> aware UTC datetime, or None. Naive input is read as UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def arm_a_release_window(
    rows: list[dict],
    now: datetime,
    window_commits: dict,
    last_release_at: datetime | None = None,
    lookback_hours: int = RELEASE_LOOKBACK_HOURS,
) -> dict:
    """Did a release land inside arm A's 24 h lookback? STRADDLED / CLEAR / UNKNOWN.

    Ruling 130 binds BOTH arms, and arm A's interval is not the probe window —
    it is the 24 h Sentry `statsPeriod`. A perfectly single-slug 60-minute probe
    can sit inside a 24 h count that spans two deploys, and that count is the
    thing being scored against zero.

    Three sources of knowledge, in descending authority:

    1. ``--last-release-at``. The operator reading Heroku's release list knows
       the answer exactly. It wins, and it is the escape hatch that keeps this
       from stalling a first run.
    2. **The commit set** — this window's, plus every recorded window inside the
       lookback, plus the most recent recorded window at or BEFORE the lookback
       start. More than one distinct SHA across that set is a release inside it.
    3. Nothing. Then the answer is UNKNOWN, not CLEAR.

    That anchor row in (2) is the part worth being careful about. Rows *inside*
    the lookback all start after `now - 24h` by construction, so agreeing with
    each other says nothing about the hours before the earliest of them; a fresh
    state file with one row in it would read as unanimous and certify 24 h it
    never observed. Requiring an observation at or before the boundary is what
    makes CLEAR mean covered. It costs one warm-up day, after which every run
    has an anchor — a bounded cost, unlike `_detect_restart`'s old predicate,
    which was unconditionally true and could never resolve at all.
    """
    if last_release_at is not None:
        age_h = (now - last_release_at).total_seconds() / 3600.0
        if age_h < lookback_hours:
            return {
                "verdict": "STRADDLED",
                "reason": f"--last-release-at is {age_h:.1f}h ago, inside the "
                          f"{lookback_hours}h arm-A lookback",
                "source": "operator",
            }
        return {
            "verdict": "CLEAR",
            "reason": f"--last-release-at is {age_h:.1f}h ago, outside the "
                      f"{lookback_hours}h arm-A lookback",
            "source": "operator",
        }

    floor = now - timedelta(hours=lookback_hours)
    inside, anchor, anchor_at = [], None, None
    for row in rows:
        started = _parse_stamp(row.get("started_at"))
        if started is None:
            continue
        commits = (row.get("probe") or {}).get("commits") or {}
        if started >= floor:
            inside.append((started, commits))
        elif anchor_at is None or started > anchor_at:
            anchor_at, anchor = started, commits

    seen = {sha for sha in (window_commits or {}) if sha}
    for _started, commits in inside:
        seen.update(sha for sha in commits if sha)
    anchor_shas = {sha for sha in (anchor or {}) if sha}
    seen.update(anchor_shas)

    if len(seen) > 1:
        shown = ", ".join(sorted(sha[:12] for sha in seen))
        return {
            "verdict": "STRADDLED",
            "reason": f"{len(seen)} distinct commits recorded within the "
                      f"{lookback_hours}h arm-A lookback ({shown})",
            "source": "history",
        }

    if not anchor_shas:
        return {
            "verdict": "UNKNOWN",
            "reason": f"no recorded window with a commit at or before the "
                      f"{lookback_hours}h lookback start ({floor.isoformat()}) — "
                      "arm A's 24h cannot be certified deploy-free. Pass "
                      "--last-release-at, or run again once a day of history exists.",
            "source": "history",
        }

    return {
        "verdict": "CLEAR",
        "reason": f"one commit ({next(iter(seen))[:12]}) across the "
                  f"{lookback_hours}h lookback, anchored at {anchor_at.isoformat()}",
        "source": "history",
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


def grade_window(probe: dict, sentry: dict, counts_as_day: bool, release: dict) -> dict:
    """Ruling 130 puts the straddle checks INSIDE the cascade, per arm, on purpose.

    A blanket "release anywhere near this window -> INCONCLUSIVE" pre-check would
    be wrong in one direction that matters: arm B's 5xx, observed inside a window
    that ran end to end on a single slug, ARE attributable to that slug, and a
    24 h lookback containing yesterday's deploy does not make them unattributable.
    Suppressing them would convert a real refutation into a shrug.

    So each straddle sits immediately ahead of the arm it disqualifies:

      arm B straddle -> ahead of the 5xx FAILED  (errors may be the retired slug's)
      arm A straddle -> ahead of the Sentry FAILED, behind the 5xx one

    `release` is a required argument with no default. A default would let a
    caller skip the check and still get a CLEAN, which is the exact shape of
    every silent-coverage bug this program has spent the month on.
    """
    reasons = []
    release = release or {"verdict": "UNKNOWN", "reason": "no release verdict supplied"}
    if probe["samples"] == 0:
        verdict = "NO_SAMPLES"
        reasons.append("probe collected zero samples — this is not a pass")
    elif probe.get("release_straddle"):
        verdict = "INCONCLUSIVE"
        reasons.append(
            "ruling 130: the window straddles a release, so its 5xx count is "
            "unattributable — " + "; ".join(probe.get("release_reasons") or ["unspecified"])
        )
    elif probe["server_errors"] > 0:
        verdict = "FAILED"
        reasons.append(f"{probe['server_errors']} 5xx on /api/feed")
    elif release["verdict"] in ("STRADDLED", "UNKNOWN"):
        verdict = "INCONCLUSIVE"
        reasons.append(
            f"ruling 130: arm A's 24h lookback is {release['verdict']} — "
            f"{release['reason']}"
        )
    elif sentry["verdict"] == "FIRED":
        verdict = "FAILED"
        reasons.append(f"BAINLUCK-ZK {sentry['reason']}")
    elif sentry["verdict"] == "UNKNOWN":
        verdict = "INCONCLUSIVE"
        reasons.append(f"arm A unreadable ({sentry['reason']}) — one arm is not the falsifier")
    elif probe["restarted"]:
        verdict = "INCONCLUSIVE"
        reasons.append(
            "a web worker restarted mid-window, which clears the very state under "
            "watch: " + "; ".join(probe.get("restart_reasons") or ["unspecified"])
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


def _read_rows(state_path: Path) -> list[dict]:
    """Every recorded window, oldest first. A malformed line is skipped, loudly."""
    if not state_path.exists():
        return []
    rows = []
    for n, line in enumerate(state_path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"   WARNING: {state_path}:{n} is not JSON — skipped, not counted")
    return rows


def summarize(state_path: Path) -> int:
    if not state_path.exists():
        print(f"#2107 watch: NO STATE at {state_path} — nothing has been recorded yet.")
        print("  Closure requires 7 consecutive clean days. Recorded so far: 0.")
        return RC_CANNOT_MEASURE

    rows = _read_rows(state_path)
    days = [r for r in rows if r.get("counts_toward_seven") is not None and r.get("is_day")]

    # A streak of ROWS is not a streak of DAYS. The original counter walked
    # `days` backwards and incremented per row, with no reference to the calendar
    # whatsoever — so seven windows run back-to-back in a single afternoon
    # satisfied a falsifier that says "seven consecutive days", and the artifact
    # it wrote would have read as closure evidence to every future reader. The
    # falsifier's unit is a DAY; count days.
    #
    # One clean window per UTC date is what a date contributes. Two clean windows
    # on the same date are still one day; a FAILED window anywhere on a date
    # disqualifies that whole date, because the day was not clean.
    by_date: dict[str, bool] = {}
    for row in days:
        date = (row.get("started_at") or "")[:10]
        if not date:
            continue
        clean = bool(row.get("counts_toward_seven"))
        by_date[date] = clean if date not in by_date else (by_date[date] and clean)

    streak = 0
    cursor = None
    for date in sorted(by_date, reverse=True):
        if not by_date[date]:
            break
        day = datetime.strptime(date, "%Y-%m-%d").date()
        if cursor is not None and (cursor - day).days != 1:
            break  # a calendar gap ends the streak; "consecutive" means consecutive
        cursor = day
        streak += 1

    print(f"#2107 watch — {state_path}")
    print(f"  windows recorded: {len(rows)}   day-windows: {len(days)}"
          f"   distinct UTC dates: {len(by_date)}")
    for row in days[-10:]:
        print(
            f"   {row.get('started_at', '?')[:19]}  {row['grade']['verdict']:<13}"
            f" samples={row['probe']['samples']:<5} 5xx={row['probe']['server_errors']}"
            f" sentry24h={row['sentry'].get('count_24h')}"
            f" processes={len(row['probe'].get('process_ids') or {})}"
        )
    non_day = len(rows) - len(days)
    if non_day:
        print(f"  NOTE: {non_day} window(s) recorded with is_day=false — these can NEVER "
              f"bank, whatever their verdict. Check the --label/--counts-as-day used.")

    # Ruling 130: an INCONCLUSIVE window is logged, not dropped. A streak stuck
    # at 3/7 because every window straddles a deploy and a streak stuck at 3/7
    # because the fix keeps regressing print the same number, and only one of
    # them is about the fix. Say which.
    straddled = [
        r for r in days
        if any("ruling 130" in reason for reason in (r.get("grade") or {}).get("reasons") or [])
    ]
    if straddled:
        dates = sorted({(r.get("started_at") or "")[:10] for r in straddled})
        print(f"  RELEASE-STRADDLED (ruling 130): {len(straddled)} day-window(s) on "
              f"{', '.join(dates)} measured across a deploy and were DISCARDED — "
              f"neither banked nor counted against. Re-run on a deploy-free date.")
    print(f"  clean UTC dates: {sorted(d for d, c in by_date.items() if c)}")
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
    ap.add_argument("--label", default="day",
                    help="free-text annotation for the window (see --counts-as-day)")
    ap.add_argument("--counts-as-day", dest="counts_as_day",
                    action=argparse.BooleanOptionalAction, default=None,
                    help="whether this window banks toward the seven. Defaults to "
                         "(--label == 'day') for backward compatibility.")
    ap.add_argument("--last-release-at", dest="last_release_at", default=None,
                    help="ISO8601 UTC timestamp of the most recent production release "
                         "(ruling 130). Highest-authority answer to 'does arm A's 24h "
                         "lookback contain a deploy'; without it the recorded commit "
                         "history is used, and a state file with under a day of history "
                         "grades UNKNOWN rather than CLEAR.")
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
    # Resolve the banking decision BEFORE the hour of probing, and say it out loud.
    # `--label` used to double as the switch: any descriptive label silently set
    # `counts_toward_seven=false`, and the window burned an hour before anyone
    # could see it had never been eligible. Worse, a false `counts_toward_seven`
    # reads to a later reader as "the fix regressed" when it means "the label was
    # wrong" — the same shape as gotcha #53, two causes collapsed into one value.
    counts_as_day = args.counts_as_day
    if counts_as_day is None:
        counts_as_day = args.label == "day"
    print(f"#2107 watch — probing {api}/api/feed every {args.interval:.0f}s for {args.minutes}m")
    print(f"   label={args.label!r}  BANKS TOWARD THE SEVEN: {counts_as_day}"
          f"{'' if counts_as_day else '  <-- this window can never bank; pass --counts-as-day to change that'}")

    last_release_at = None
    if args.last_release_at:
        last_release_at = _parse_stamp(args.last_release_at)
        if last_release_at is None:
            print(f"#2107 watch: CANNOT MEASURE — --last-release-at "
                  f"{args.last_release_at!r} is not ISO8601")
            return RC_CANNOT_MEASURE

    probe = run_probe(api, args.minutes, args.interval, args.limit)
    sentry = sentry_24h_count(os.getenv("SENTRY_AUTH_TOKEN"))
    release = arm_a_release_window(
        _read_rows(args.state),
        datetime.now(timezone.utc),
        probe.get("commits") or {},
        last_release_at=last_release_at,
    )
    grade = grade_window(probe, sentry, counts_as_day=counts_as_day, release=release)

    row = {
        "issue": 2107,
        "label": args.label,
        "is_day": counts_as_day,
        "started_at": started.isoformat(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "probe": probe,
        "sentry": sentry,
        "release": release,
        "grade": grade,
        "counts_toward_seven": grade["counts_toward_seven"],
    }

    args.state.parent.mkdir(parents=True, exist_ok=True)
    with args.state.open("a") as fh:
        fh.write(json.dumps(row) + "\n")

    print(json.dumps(
        {k: row[k] for k in ("label", "probe", "sentry", "release", "grade")}, indent=2))
    print(f"   recorded -> {args.state}")

    if grade["verdict"] == "CLEAN":
        return RC_CLEAN
    if grade["verdict"] == "FAILED":
        return RC_FAILED
    return RC_CANNOT_MEASURE


if __name__ == "__main__":
    sys.exit(main())
