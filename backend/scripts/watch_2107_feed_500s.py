#!/usr/bin/env python3
"""#2107 post-deploy watch — the falsifier the fix has to survive for SEVEN DAYS.

WHY THIS EXISTS AT ALL, AND WHY 24h IS NOT ENOUGH

`/api/feed` 500'd on every request on 2026-08-22 because a process-global
cache held ORM rows that one rollback could expire (see `routes/events.py`,
`TeamSnapshot`). The cert window that confirmed the diagnosis independently
also defined what would REFUTE the fix, and the number in it is the point:
**BAINLUCK-ZK fired on 4 of 5 days**. A clean 24 h therefore has roughly a 1-in-5
chance of being clean by luck alone. Merging is not closure; a week of silence
is closure.

    closure = 7 CONSECUTIVE UTC dates, post-deploy, with BOTH arms clean:
      arm A — Sentry BAINLUCK-ZK events, blast-window-excluded, are ZERO
      arm B — a 1 req/min GET /api/feed probe records ZERO attributable 5xx

Both arms, because either alone is refutable. Sentry alone trusts that a
handled 500 still reports. The probe alone trusts that one requester's traffic
reaches every process — and only arm A sees the 500s that real user traffic
provokes while the probe is asleep between samples.

THE CRITERION, PRE-REGISTERED (ruling 136, frozen 2026-08-26 before grading resumed)

A window is **CLEAN** when all of these hold:

  1. the probe served >= MIN_SERVED_REQUESTS requests outside any blast window;
  2. it observed ZERO `/api/feed` 5xx outside any blast window;
  3. arm A's Sentry count, blast-window-excluded, is ZERO;
  4. every commit `/api/health` reported contains the #2107 fix;
  5. no web worker restarted mid-window.

**Releases inside the window are tolerated.** What is NOT tolerated is an error
inside DEPLOY_BLAST_WINDOW_MINUTES of a deploy boundary: it cannot make the
window CLEAN (an error was observed) and it cannot make it FAILED (it may be the
cutover rather than the code), so it is INCONCLUSIVE, logged with the boundary it
was measured against.

WHY RELEASES ARE TOLERATED — ruling 136, and it is an attribution correction

Ruling 130 disqualified any window containing a deploy, on the grounds that it
"measures two different systems". That is true of a SLUG and false of the thing
this file tests. #2107's fix is a code change — `b2e3e1a9` plus `42f2356b` — and
EVERY slug deployed since it merged contains it. A boundary between two slugs
that both carry the fix is not a change of the system under test.

That reasoning is only sound if the slugs really do carry it, so clause 4 above
checks it rather than assuming it: `--fix-commit` is verified against every
observed commit with `git merge-base --is-ancestor`. Tolerating releases without
that check would let a ROLLBACK to a pre-fix slug bank a clean day for a fix that
was not running — the hole the tolerance would otherwise open.

FIVE THINGS THIS REFUSES TO DO, each because the program has been burned by it

1. **PASS over no samples.** A window that collected nothing reports
   NO_SAMPLES, never PASS. An empty result is a response shape, not a fact
   (gotcha #53) — the trade backfill recorded ten weeks of SUCCESS on exactly
   this confusion.
2. **Span a restart silently.** A restart clears every process-global, so it
   also clears the state the watch is watching, and unlike a release that IS a
   change of the system under test. A window in which a worker's
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
4. **Credit a deploy boundary it does not know about.** Blast windows are built
   from boundaries this run can NAME: `--release-at` / `--releases-from-heroku`
   for exact release times, plus every commit transition the probe itself saw.
   An error in a stretch whose boundaries are unknown COUNTS — fail-closed
   toward FAILED, which is the recoverable error, because a false FAILED costs a
   re-run while a false CLEAN closes a P0. `boundary_source` records which.
5. **Grade arm A against an org it cannot reach.** `SENTRY_ORG` defaulted to
   `bain-luck` until 2026-08-26; the org is `alexander-bain`, so every run that
   did not inherit the env var got a 404, which arm A reports as UNKNOWN, which
   graded the day INCONCLUSIVE. Arm A was one unset variable from being
   permanently unreadable, and nobody saw it because ruling 130's straddle check
   disqualified every window before arm A was ever reached.

WHAT WAS RETIRED, AND WHY IT IS NAMED HERE RATHER THAN DELETED

`MIN_POST_RELEASE_EXPOSURE_HOURS` (ruling 135, 6.0 h) is **retired**. Measured
2026-08-27 over the 100 most recent releases (295.8 h, 0.34 releases/hour,
median gap 0.63 h): a day banked only if no release landed in the probe hour
(78 %) AND >= 6 h had passed since the last release (52 %) — jointly ~41 %, and
in practice worse, because without `--last-release-at` the 6 h bound came from
`_narrow_since` walking recorded windows back until the SHA changed, and at one
window per day consecutive windows essentially never share a SHA. Seven
CONSECUTIVE banked days at p = 0.41 is an expected wait of about two years.
The floor is now stated in REQUESTS (`MIN_SERVED_REQUESTS`), which is what the
instrument can actually vouch for: a floor in hours measures the deploy cadence,
a floor in requests measures the exposure.

USAGE

    # one day's window (run it once per day, or from a scheduler)
    python3 scripts/watch_2107_feed_500s.py --releases-from-heroku

    # a short confidence read that is explicitly NOT a day
    python3 scripts/watch_2107_feed_500s.py --minutes 5 --label smoke

    # boundaries supplied by hand instead of by the Heroku CLI
    python3 scripts/watch_2107_feed_500s.py --minutes 60 \\
        --release-at 2026-08-27T00:45:58+00:00 --release-at 2026-08-27T00:14:27+00:00

    # where the seven days stand
    python3 scripts/watch_2107_feed_500s.py --summarize

Environment: `BAINLUCK_API` (required), `SENTRY_AUTH_TOKEN` (arm A; without it
arm A reports UNKNOWN and the day cannot count clean), `SENTRY_ORG` (defaults to
the correct org). Both live in the untracked `~/.claude/.env` — never in a
tracked file.

Exit codes follow the gate convention (gotcha #54): `0` clean, `1` a REAL
failure of the thing being watched, `3` could-not-measure. `1` is a result;
anything else non-zero is a story about the harness.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The org is `alexander-bain`. It was `bain-luck` here until 2026-08-26, which
# 404s — see docstring point 5. A wrong org does not error loudly; it becomes
# arm A UNKNOWN, which becomes INCONCLUSIVE, which reads as "not yet proven".
SENTRY_ORG = os.getenv("SENTRY_ORG", "alexander-bain")
SENTRY_ISSUE_SHORT_ID = "BAINLUCK-ZK"
REQUIRED_CLEAN_DAYS = 7
# Arm A reads a rolling 24 h count, so its interval is 24 h — not the probe
# window's length. Keep the two intervals separate.
ARM_A_LOOKBACK_HOURS = 24

# ---- ruling 136: the blast window, DERIVED from BAINLUCK-ZK's own event times
#
# Every one of the issue's 35 lifetime events was timestamped and measured
# against the preceding release, across the 100 releases spanning
# 2026-08-14T16:59:38Z -> 2026-08-27T00:45:58Z (295.8 h):
#
#     B      wall-clock covered   ZK events inside   enrichment   detection lost
#     2 min        1.1 %            0/35  ( 0.0 %)      0.00x          0.0 %
#     5 min        2.7 %            3/35  ( 8.6 %)      3.12x          8.6 %
#    10 min        5.4 %            4/35  (11.4 %)      2.12x         11.4 %   <-
#    15 min        7.9 %            5/35  (14.3 %)      1.80x         14.3 %
#    20 min       10.3 %            5/35  (14.3 %)      1.38x         14.3 %
#    30 min       14.4 %            8/35  (22.9 %)      1.59x         22.9 %
#    60 min       22.3 %           11/35  (31.4 %)      1.41x         31.4 %
#
# Enrichment peaks at 5 min and is back to background by 20 min — the signature
# of a cutover transient that dies out within minutes. The four near-deploy
# events sit at 3.1, 3.3, 4.7 and 7.1 minutes, so 10 minutes covers all of them
# while the last point is still enriched 2.12x, and it costs the falsifier
# 11.4 % of its historical detection power. The bug is overwhelmingly NOT a
# deploy artifact: its median event fires 517 minutes after the last release.
#
# SHORTER IS FAIL-CLOSED and that is why this is an upper bound rather than a
# margin. A short B grades a transient error FAILED, which costs a re-run; a
# long B grades a real regression INCONCLUSIVE, which costs the falsifier. 30
# and 60 are rejected on that ground despite being more tolerant.
DEPLOY_BLAST_WINDOW_MINUTES = 10

# The window must have SERVED enough real requests OUTSIDE the blast bands.
# Six deploy-free hours during which nobody asked for the feed is six hours of
# nothing observed; a bug that never had a chance to fire did not fail to fire.
# A 60-minute probe at `--interval 60` makes 60 requests, so 50 tolerates a few
# transport blips while refusing a window that was gutted.
#
# Counted from the probe's OWN samples, deliberately, because that is the only
# request count this instrument can vouch for. Production exposes no readable
# per-interval counter of real user feed requests: `user_seen_markets` is EMPTY
# (0 rows, ever — measured 2026-08-24, so it is not a traffic signal at all),
# `pg_stat_statements` holds only ingestion writes for `futures_markets`, and
# `pg_stat_user_indexes.idx_scan` on the feed's partial indexes conflates the
# hourly warmer rail with real users. Rather than infer a number from a counter
# that measures something else, the floor is stated over what was observed.
MIN_SERVED_REQUESTS = 50

# The default window is 90 minutes, and that number is DERIVED from the floor
# above rather than picked for roundness. A blast band costs the window ~10 of
# its samples, so at one sample per minute the floor and the window length are
# coupled. Simulated over the same 100 releases, stepping a candidate window
# start every 5 minutes across the whole 295.8 h span and counting how many
# start times still clear 50 served requests outside every band:
#
#      60 min   3184/3538 = 90.0 %      -> 7 consecutive days = 47.8 %
#      75 min   3429/3535 = 97.0 %
#      90 min   3524/3532 = 99.8 %      -> 7 consecutive days = 98.6 %   <-
#     120 min   3526/3526 = 100.0 %
#
# 60 minutes leaves a single mid-window deploy sitting right on the floor (60
# samples minus ~11 blasted = 49), which is the ruling-135 mistake in miniature:
# a criterion that happens to be clearable is not a criterion that is runnable.
# 90 absorbs four deploys and still clears. Expected wait to seven consecutive
# clean days: ~7.1 days at 90 min, against ~868 days under the retired rule.
DEFAULT_WINDOW_MINUTES = 90

# The two commits that together are the #2107 fix. Defaults so that a bare run
# still checks clause 4 rather than skipping it — the check is the thing that
# makes tolerating releases safe, so it must not be opt-in.
DEFAULT_FIX_COMMITS = (
    "b2e3e1a9",  # the team cache holds detached snapshots
    "42f2356b",  # season_stats was handed out by reference
)

HEROKU_APP = os.getenv("HEROKU_APP", "bainluck")

DEFAULT_STATE = Path(__file__).resolve().parents[2] / "docs/audits/latency/2107-watch.jsonl"
REPO_ROOT = Path(__file__).resolve().parents[2]

RC_CLEAN = 0
RC_FAILED = 1
RC_CANNOT_MEASURE = 3


def _parse_stamp(value) -> datetime | None:
    """ISO8601 -> aware UTC datetime, or None. Naive input is read as UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ------------------------------------------------------- deploy blast windows


def heroku_release_times(app: str = HEROKU_APP, count: int = 200) -> tuple[list[datetime], str]:
    """(release timestamps, source) from the Heroku CLI, or ([], reason) on failure.

    Shelling out is a dependency and dependencies fail, so this NEVER raises and
    never blocks a run. It returns a source string that is recorded on the row,
    because "no boundaries were known" and "boundaries were known and there were
    none" are different facts that a bare empty list collapses (gotcha #53).

    Failing soft is also fail-CLOSED here, which is why it is safe: with fewer
    known boundaries, more errors fall outside every blast band and count as
    FAILED. A false FAILED costs a re-run. A false CLEAN closes a P0.
    """
    try:
        out = subprocess.run(
            ["heroku", "releases", "-a", app, "-n", str(count), "--json"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        return [], f"heroku-unavailable ({type(exc).__name__})"
    if out.returncode != 0:
        return [], f"heroku-exit-{out.returncode}"
    try:
        rows = json.loads(out.stdout)
    except Exception:
        return [], "heroku-unparseable"
    stamps = [t for t in (_parse_stamp(r.get("created_at")) for r in rows) if t]
    if not stamps:
        return [], "heroku-empty"
    return sorted(stamps), f"heroku ({len(stamps)} releases)"


def deploy_boundaries(
    timeline: list[dict],
    explicit: list[datetime] | None = None,
) -> list[dict]:
    """Every deploy boundary this run can NAME, as {at, source, uncertain_from}.

    Two sources, and they are kept apart on the row rather than merged into one
    number, because they carry different precision:

    * **explicit** — `--release-at` or the Heroku CLI. Exact to the second.
    * **observed** — a commit transition in the probe's own identity timeline.
      The deploy happened somewhere between the last sample on the old SHA and
      the first on the new one, so the boundary is recorded with
      `uncertain_from` at the earlier of the two and the blast band is measured
      from THERE. At `--interval 60` that widens the band by at most a sample.

    The observed source exists because a release can land inside the window with
    no `--release-at` covering it, and a boundary the run cannot see is a
    boundary whose transient errors get attributed to the code (docstring point
    4). Recording both is cheaper than choosing.
    """
    out: list[dict] = []
    for at in sorted(explicit or []):
        out.append({"at": at.isoformat(), "source": "explicit",
                    "uncertain_from": at.isoformat()})

    prev_sha, prev_at = None, None
    for point in timeline:
        sha = point.get("commit")
        at = _parse_stamp(point.get("at"))
        if not sha or at is None:
            continue
        if prev_sha is not None and sha != prev_sha:
            out.append({
                "at": at.isoformat(),
                "source": "observed",
                "uncertain_from": (prev_at or at).isoformat(),
                "from_commit": prev_sha[:12],
                "to_commit": sha[:12],
            })
        prev_sha, prev_at = sha, at
    return out


def blast_bands(
    boundaries: list[dict],
    minutes: float = DEPLOY_BLAST_WINDOW_MINUTES,
) -> list[tuple[datetime, datetime]]:
    """Boundaries -> [start, end] intervals inside which an error is unattributable."""
    bands = []
    for b in boundaries:
        start = _parse_stamp(b.get("uncertain_from")) or _parse_stamp(b.get("at"))
        anchor = _parse_stamp(b.get("at")) or start
        if start is None or anchor is None:
            continue
        bands.append((start, anchor + timedelta(minutes=minutes)))
    return bands


def in_blast(when: datetime | None, bands: list[tuple[datetime, datetime]]) -> bool:
    if when is None:
        return False
    return any(start <= when <= end for start, end in bands)


def attribute_errors(failures: list[dict], bands: list[tuple[datetime, datetime]]) -> dict:
    """Split observed failures into attributable and blast-window ones.

    Ruling 136's whole mechanism sits in this split. An error OUTSIDE every band
    is the live code's and refutes the fix. An error INSIDE a band may be the
    cutover, so it can neither pass nor fail the window — but it is carried out
    of here with the band it matched, because an excluded error that is not
    printed is an error nobody ever reads (ruling 130's logged-not-dropped
    clause, which survives this amendment unchanged).
    """
    attributable, blasted = [], []
    for f in failures:
        when = _parse_stamp(f.get("at"))
        (blasted if in_blast(when, bands) else attributable).append(f)
    return {
        "attributable": attributable,
        "blast_window": blasted,
        "attributable_count": len(attributable),
        "blast_window_count": len(blasted),
    }


# ---------------------------------------------------------- clause 4: ancestry


def check_fix_ancestry(commits: dict, fix_commits: list[str]) -> dict:
    """Does every observed slug contain the fix? This is what makes clause 1 safe.

    Tolerating releases rests entirely on "every deployed slug carries the fix",
    and that sentence is checkable rather than assumable: `/api/health` reports
    the commit, and `git merge-base --is-ancestor` answers it exactly.

    Three outcomes, and the middle one is the reason the function exists:

    * **CONTAINS** — every observed SHA has every fix commit as an ancestor.
    * **MISSING** — some slug did NOT carry the fix. A rollback. The window
      measured a system without the fix in it and must not bank; grading it
      CLEAN is precisely the hole that tolerating releases would open.
    * **UNRESOLVED** — a SHA is not in this clone (unfetched, or a short SHA
      that no longer resolves). Not knowing is not the same as knowing it is
      fine, so this grades INCONCLUSIVE and says which SHA to fetch.
    """
    seen = sorted(sha for sha in (commits or {}) if sha)
    if not fix_commits:
        return {"verdict": "UNCHECKED", "reason": "no --fix-commit supplied",
                "commits": seen, "missing": [], "unresolved": []}
    if not seen:
        return {"verdict": "UNRESOLVED", "reason": "no commit was observed at all",
                "commits": [], "missing": [], "unresolved": []}

    missing, unresolved = [], []
    for sha in seen:
        if not _git_ok(["cat-file", "-e", f"{sha}^{{commit}}"]):
            unresolved.append(sha)
            continue
        for fix in fix_commits:
            if not _git_ok(["merge-base", "--is-ancestor", fix, sha]):
                missing.append(f"{sha[:12]} lacks {fix[:12]}")

    if unresolved:
        return {"verdict": "UNRESOLVED", "commits": seen, "missing": missing,
                "unresolved": unresolved,
                "reason": "not in this clone: " + ", ".join(s[:12] for s in unresolved)
                          + " — fetch it, or the slug's contents are unknown"}
    if missing:
        return {"verdict": "MISSING", "commits": seen, "missing": missing,
                "unresolved": [], "reason": "; ".join(missing)}
    return {"verdict": "CONTAINS", "commits": seen, "missing": [], "unresolved": [],
            "reason": f"all {len(seen)} observed slug(s) contain "
                      f"{', '.join(f[:12] for f in fix_commits)}"}


def _git_ok(args: list[str]) -> bool:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True, timeout=30,
        ).returncode == 0
    except Exception:
        return False


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
    """1 req/min against `/api/feed`, recording every status, process and commit.

    The identity read now runs on EVERY sample rather than every fifth. Ruling
    136 measures a 10-minute blast band from a commit transition, so a boundary
    located to within five samples is a boundary located to within a band's
    length — the sampling rate stopped being a cost question and became a
    precision one. It is one extra `/api/health` per minute.
    """
    started_monotonic = time.monotonic()
    deadline = started_monotonic + minutes * 60
    statuses: Counter = Counter()
    processes: Counter = Counter()
    commits: Counter = Counter()
    failures: list[dict] = []
    timeline: list[dict] = []
    # pid -> {"first_uptime", "last_uptime", "born_at_elapsed"}. Seeing N process
    # ids is NOT a restart (see `_detect_restart`); an uptime that resets is.
    uptimes: dict[str, dict] = {}
    samples = 0
    sample_times: list[str] = []

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
        sample_times.append(stamp)

        ident = _identify_process(api)
        if ident.get("process_id"):
            processes[ident["process_id"]] += 1
        if ident.get("commit"):
            commits[ident["commit"]] += 1
            timeline.append({"at": stamp, "commit": ident["commit"]})
        _note_uptime(ident)

        if status is None or status >= 500:
            failures.append({"at": stamp, "status": status, **ident})

        if time.monotonic() >= deadline:
            break
        time.sleep(max(0.0, interval))

    server_errors = sum(n for s, n in statuses.items() if s != "None" and int(s) >= 500)
    transport = statuses.get("None", 0)
    restarted, restart_reasons = _detect_restart(uptimes)
    released, release_reasons = _detect_release(commits)
    return {
        "samples": samples,
        "sample_times": sample_times,
        "statuses": dict(statuses),
        "server_errors": server_errors,
        "transport_errors": transport,
        "failures": failures[:50],
        "process_ids": dict(processes),
        "commits": dict(commits),
        "commit_timeline_len": len(timeline),
        "timeline": timeline,
        # Ruling 129: a dyno runs WEB_CONCURRENCY workers, so the worker count is
        # dynos x WEB_CONCURRENCY. Recorded, not inferred (docstring point 3).
        "worker_count": len(processes),
        "uptimes": uptimes,
        "restarted": restarted,
        "restart_reasons": restart_reasons,
        # Ruling 136: a release inside the window is RECORDED and no longer
        # disqualifying. The field keeps its name so old rows stay readable.
        "release_straddle": released,
        "release_reasons": release_reasons,
    }


def _detect_restart(uptimes: dict[str, dict]) -> tuple[bool, list[str]]:
    """A restart is an uptime that RESETS — not a second process id.

    `restarted` was `len(processes) > 1`, which reads "more than one worker
    answered" as "the web process restarted mid-window". Ruling 129 is exactly
    that correction in the other direction: the two leaders were
    WEB_CONCURRENCY, not the dyno count. Production runs ONE web dyno with
    `WEB_CONCURRENCY=2`, so two stable process ids answer every hour of every
    day — measured 2026-08-24, both reporting uptime 6,701 s and climbing
    together. The old predicate was therefore not merely imprecise, it was
    **unconditionally true**, and every window it would ever grade was
    INCONCLUSIVE. A seven-day falsifier that cannot bank day one is not a strict
    falsifier; it is a broken one, and it fails in the direction where nobody
    goes looking, because "not yet closed" is the expected reading.

    This one survives ruling 136 unamended, and the contrast is the point: a
    RELEASE between two fix-carrying slugs is not a change of the system under
    test, but a RESTART clears the process-globals this issue is about, so it is.

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
    """Did the deployed commit CHANGE inside the window? RECORDED, not disqualifying.

    Under ruling 130 this returned the verdict. Under ruling 136 it returns a
    fact: the window saw a release, which is now expected — 22 % of random
    60-minute windows contain one at the measured cadence of 0.34 releases/hour.
    What the release buys is a BOUNDARY (see `deploy_boundaries`), and what the
    boundary buys is a blast band. The window itself is still gradeable.

    Absent commits are ignored rather than counted as a change: `/api/health`
    predating the field reports `None`, and "the instrument cannot see it" is
    not "the value differed" (gotcha #53).
    """
    seen = sorted(sha for sha in commits if sha)
    if len(seen) < 2:
        return False, []
    shown = ", ".join(sha[:12] for sha in seen)
    return True, [
        f"{len(seen)} distinct commits answered inside the window ({shown}) — "
        "a release landed mid-window; ruling 136 tolerates it and measures a "
        f"{DEPLOY_BLAST_WINDOW_MINUTES}-minute blast band from the transition"
    ]


# --------------------------------------------------------------- arm A: sentry


def sum_buckets_since(buckets: list, since: datetime | None) -> tuple[int, int, bool]:
    """(total_24h, total_since, narrowed) over Sentry's hourly `stats.24h` points.

    Retained as arm A's FALLBACK path. Hourly buckets cannot express a 10-minute
    blast band — excluding a band would drop a whole hour with it — which is why
    ruling 136 moved arm A's primary read onto per-event timestamps
    (`sentry_events_since`). This is what answers when the event list may be
    truncated and a count is still owed.

    A bucket is kept when any part of it lies at or after `since`, i.e. when
    `bucket_start + width > since`. Rounding a partial bucket INTO the count can
    only turn a would-be CLEAN into a FIRED — never the reverse — and a false
    FAILED gets investigated while a false CLEAN closes the issue. Width is read
    off consecutive timestamps rather than assumed, falling back to one hour, so
    a granularity change upstream does not silently shift the boundary.
    """
    points = [p for p in buckets if len(p) > 1]
    total = sum(int(p[1]) for p in points)
    if since is None or not points:
        return total, total, False

    width = 3600.0
    if len(points) > 1:
        deltas = [float(points[i + 1][0]) - float(points[i][0]) for i in range(len(points) - 1)]
        positive = [d for d in deltas if d > 0]
        if positive:
            width = min(positive)

    cutoff = since.timestamp()
    kept = [p for p in points if float(p[0]) + width > cutoff]
    return total, sum(int(p[1]) for p in kept), len(kept) != len(points)


def _sentry_get(url: str, token: str):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read())


def sentry_events_since(
    token: str | None,
    bands: list[tuple[datetime, datetime]],
    now: datetime,
    lookback_hours: int = ARM_A_LOOKBACK_HOURS,
) -> dict:
    """Arm A: BAINLUCK-ZK events in the lookback, blast-window-excluded.

    Reads per-event timestamps, not the issue's `count` — that field is LIFETIME
    (gotcha #49), and a dormant bug shows thousands there while firing zero
    today. Reading it would make this watch permanently, confidently red.

    Ruling 136 needs SECOND precision, because a 10-minute band is a sixth of a
    Sentry stats bucket. The events endpoint gives exactly that. The 24 h bucket
    total is still read alongside it and is used two ways: as the continuity
    number (`count_24h`, comparable with rows recorded before this) and as a
    TRUNCATION DETECTOR.

    Truncation is the one way this read can lie in the dangerous direction. The
    events endpoint pages at 100, so a flood could return the newest 100 and
    hide the rest. If the page is full AND the bucket total exceeds what came
    back, the event list is not trustworthy and the verdict falls back to the
    unexcluded bucket total — which can only produce FIRED, never a false CLEAN.
    """
    if not token:
        return {"verdict": "UNKNOWN", "reason": "SENTRY_AUTH_TOKEN not set",
                "count_24h": None, "count_scored": None, "source": None,
                "excluded_by_blast": 0}

    floor = now - timedelta(hours=lookback_hours)
    query = urllib.parse.urlencode(
        {"query": f"issue:{SENTRY_ISSUE_SHORT_ID}", "statsPeriod": "24h"})
    url = f"https://sentry.io/api/0/organizations/{SENTRY_ORG}/issues/?{query}"
    try:
        issues = _sentry_get(url, token)
    except Exception as exc:
        return {"verdict": "UNKNOWN", "reason": f"{type(exc).__name__} on {SENTRY_ORG}",
                "count_24h": None, "count_scored": None, "source": None,
                "excluded_by_blast": 0}
    if isinstance(issues, dict):  # an error body, not a list of issues
        return {"verdict": "UNKNOWN",
                "reason": f"sentry returned an error object: {str(issues)[:120]}",
                "count_24h": None, "count_scored": None, "source": None,
                "excluded_by_blast": 0}

    if not issues:
        # The issue not being returned for a 24h window is the CLEAN reading —
        # but say which reading it is, so nobody later mistakes it for "the
        # issue does not exist" (gotcha #53 again).
        return {"verdict": "CLEAN", "reason": "no 24h events for this issue",
                "count_24h": 0, "count_scored": 0, "source": "issues-endpoint",
                "excluded_by_blast": 0}

    issue = issues[0]
    total = sum(int(p[1]) for p in ((issue.get("stats") or {}).get("24h") or []) if len(p) > 1)

    events, truncated = [], False
    try:
        raw = _sentry_get(
            f"https://sentry.io/api/0/issues/{issue.get('id')}/events/?statsPeriod=24h", token)
        if isinstance(raw, list):
            events = [t for t in (_parse_stamp(e.get("dateCreated")) for e in raw) if t]
            truncated = len(raw) >= 100
        else:
            truncated = True
    except Exception:
        truncated = True

    in_lookback = [t for t in events if t >= floor]
    if truncated and total > len(in_lookback):
        return {
            "verdict": "FIRED" if total else "CLEAN",
            "count_24h": total, "count_scored": total,
            "source": "buckets-fallback", "excluded_by_blast": 0,
            "issue_id": issue.get("id"),
            "reason": f"{total} events in 24h; the per-event list was truncated "
                      f"({len(in_lookback)} returned) so no blast-window exclusion "
                      "was applied — graded on the unexcluded total",
        }

    kept = [t for t in in_lookback if not in_blast(t, bands)]
    excluded = len(in_lookback) - len(kept)
    if kept:
        reason = (f"{len(kept)} event(s) outside every blast window, newest "
                  f"{max(kept).isoformat()}"
                  + (f"; {excluded} excluded as within "
                     f"{DEPLOY_BLAST_WINDOW_MINUTES}m of a deploy" if excluded else ""))
    elif excluded:
        reason = (f"0 attributable events; all {excluded} in the lookback landed within "
                  f"{DEPLOY_BLAST_WINDOW_MINUTES}m of a deploy boundary (ruling 136)")
    else:
        reason = f"0 events in the {lookback_hours}h lookback"
    return {
        "verdict": "CLEAN" if not kept else "FIRED",
        "count_24h": total,
        "count_scored": len(kept),
        "excluded_by_blast": excluded,
        "source": "events-endpoint",
        "issue_id": issue.get("id"),
        "last_seen": issue.get("lastSeen"),
        "reason": reason,
    }


# ------------------------------------------------------------------- verdicts


def grade_window(
    probe: dict,
    sentry: dict,
    counts_as_day: bool,
    errors: dict,
    ancestry: dict,
    boundaries: list[dict],
    boundary_source: str,
) -> dict:
    """The pre-registered cascade (ruling 136). Order is the specification.

    Every branch below was frozen before grading resumed, and the ORDER is as
    load-bearing as the branches — a floor placed ahead of the failure check
    would let a gutted window suppress a real refutation, and a failure check
    placed ahead of the ancestry check would attribute a pre-fix slug's 500s to
    the fix.

      1. NO_SAMPLES        — nothing was collected. Never a pass (gotcha #53).
      2. FAILED            — a 5xx OUTSIDE every blast band. The refutation, and
                             it comes first so nothing downstream can swallow it.
      3. INCONCLUSIVE      — the observed slugs do not (or may not) carry the fix.
      4. INCONCLUSIVE      — a 5xx INSIDE a blast band: cannot pass, cannot fail.
      5. INCONCLUSIVE      — the served-request floor was not cleared.
      6. FAILED            — arm A fired outside every blast band.
      7. INCONCLUSIVE      — arm A unreadable. One arm is not the falsifier.
      8. INCONCLUSIVE      — a worker restarted; the state under watch was cleared.
      9. INCONCLUSIVE      — transport errors, or no process_id ever came back.
     10. CLEAN.

    Note what is NOT in this list: "a release landed". Ruling 136 retired it.
    """
    reasons = []
    blasted = errors["blast_window_count"]
    attributable = errors["attributable_count"]
    served_total = probe["samples"] - probe.get("transport_errors", 0)
    bands = blast_bands(boundaries)
    served_clean = sum(
        1 for t in probe.get("sample_times", [])
        if not in_blast(_parse_stamp(t), bands)
    ) - probe.get("transport_errors", 0)
    served_clean = max(0, min(served_clean, served_total))

    if probe["samples"] == 0:
        verdict = "NO_SAMPLES"
        reasons.append("probe collected zero samples — this is not a pass")
    elif attributable > 0:
        verdict = "FAILED"
        reasons.append(
            f"{attributable} 5xx on /api/feed outside every "
            f"{DEPLOY_BLAST_WINDOW_MINUTES}-minute deploy blast window — "
            "attributable to the running code (ruling 136)"
        )
    elif ancestry["verdict"] in ("MISSING", "UNRESOLVED", "UNCHECKED"):
        verdict = "INCONCLUSIVE"
        reasons.append(
            f"ruling 136 clause 4: fix ancestry is {ancestry['verdict']} — "
            f"{ancestry['reason']}. Tolerating releases is only sound while every "
            "observed slug carries the fix."
        )
    elif blasted > 0:
        verdict = "INCONCLUSIVE"
        reasons.append(
            f"{blasted} 5xx landed within {DEPLOY_BLAST_WINDOW_MINUTES}m of a deploy "
            f"boundary ({boundary_source}) — unattributable, so the window can neither "
            "bank nor refute (ruling 136)"
        )
    elif served_clean < MIN_SERVED_REQUESTS:
        verdict = "INCONCLUSIVE"
        reasons.append(
            f"exposure floor: only {served_clean} of {probe['samples']} requests were "
            f"served outside a blast window (floor {MIN_SERVED_REQUESTS}) — the window "
            "did not exercise /api/feed enough for silence to be evidence"
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
        # be scored as a coverage arm that passed.
        verdict = "INCONCLUSIVE"
        reasons.append(
            "no process_id observed — /api/health predates this fix, so coverage is unmeasured"
        )
    else:
        verdict = "CLEAN"

    return {
        "verdict": verdict,
        "reasons": reasons,
        "criterion": "ruling-136",
        "served_requests": served_total,
        "served_outside_blast": served_clean,
        "served_floor": MIN_SERVED_REQUESTS,
        "blast_window_minutes": DEPLOY_BLAST_WINDOW_MINUTES,
        "deploy_boundaries": len(boundaries),
        "boundary_source": boundary_source,
        "errors_attributable": attributable,
        "errors_in_blast_window": blasted,
        "fix_ancestry": ancestry["verdict"],
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


def streak_from_rows(rows: list[dict]) -> dict:
    """Consecutive clean UTC dates, plus WHY the streak ends where it does.

    A streak of ROWS is not a streak of DAYS. The original counter walked rows
    backwards and incremented per row with no reference to the calendar, so
    seven windows run back-to-back in one afternoon satisfied a falsifier that
    says "seven consecutive days". The falsifier's unit is a DAY; count days.

    One clean window per UTC date is what a date contributes. Two clean windows
    on the same date are still one day; a non-clean window anywhere on a date
    disqualifies that date, because the day was not clean.

    Ruling 136 adds the second half: say WHY it ended. A streak stopped by a
    FAILED day and a streak stopped by a day nobody could grade print the same
    number, and only one of them is about the fix. `stopped_by` distinguishes
    them, because three days were lost to exactly that ambiguity.
    """
    days = [r for r in rows if r.get("is_day")]
    by_date: dict[str, dict] = {}
    for row in days:
        date = (row.get("started_at") or "")[:10]
        if not date:
            continue
        verdict = (row.get("grade") or {}).get("verdict")
        clean = bool(row.get("counts_toward_seven"))
        rec = by_date.setdefault(date, {"clean": clean, "verdicts": []})
        rec["clean"] = rec["clean"] and clean
        rec["verdicts"].append(verdict)

    streak, cursor, stopped_by = 0, None, "no recorded day-window"
    for date in sorted(by_date, reverse=True):
        rec = by_date[date]
        if not rec["clean"]:
            worst = "FAILED" if "FAILED" in rec["verdicts"] else (
                rec["verdicts"][0] if rec["verdicts"] else "UNKNOWN")
            stopped_by = f"{date} graded {worst}"
            break
        day = datetime.strptime(date, "%Y-%m-%d").date()
        if cursor is not None and (cursor - day).days != 1:
            stopped_by = f"calendar gap before {cursor.isoformat()} (no window on the day prior)"
            break
        cursor = day
        streak += 1
    else:
        if streak:
            stopped_by = "start of recorded history"

    clean_dates = sorted(d for d, r in by_date.items() if r["clean"])
    earliest_close = None
    if clean_dates and streak:
        newest = datetime.strptime(clean_dates[-1], "%Y-%m-%d").date()
        earliest_close = (newest + timedelta(days=REQUIRED_CLEAN_DAYS - streak)).isoformat()
    return {
        "streak": streak,
        "required": REQUIRED_CLEAN_DAYS,
        "stopped_by": stopped_by,
        "by_date": by_date,
        "clean_dates": clean_dates,
        "day_windows": len(days),
        "earliest_closure_date": earliest_close,
    }


def summarize(state_path: Path) -> int:
    if not state_path.exists():
        print(f"#2107 watch: NO STATE at {state_path} — nothing has been recorded yet.")
        print("  Closure requires 7 consecutive clean days. Recorded so far: 0.")
        return RC_CANNOT_MEASURE

    rows = _read_rows(state_path)
    s = streak_from_rows(rows)

    print(f"#2107 watch — {state_path}")
    print(f"  criterion: ruling 136 (frozen 2026-08-26) — releases tolerated, "
          f"{DEPLOY_BLAST_WINDOW_MINUTES}m blast window, "
          f"{MIN_SERVED_REQUESTS}-request exposure floor")
    print(f"  windows recorded: {len(rows)}   day-windows: {s['day_windows']}"
          f"   distinct UTC dates: {len(s['by_date'])}")
    days = [r for r in rows if r.get("is_day")]
    for row in days[-10:]:
        grade = row.get("grade") or {}
        print(
            f"   {row.get('started_at', '?')[:19]}  {grade.get('verdict', '?'):<13}"
            f" samples={row['probe']['samples']:<5}"
            f" 5xx={grade.get('errors_attributable', row['probe'].get('server_errors'))}"
            f"(+{grade.get('errors_in_blast_window', 0)} blast)"
            f" sentry={row['sentry'].get('count_scored', row['sentry'].get('count_24h'))}"
            f" fix={grade.get('fix_ancestry', '?')}"
            f" processes={len(row['probe'].get('process_ids') or {})}"
        )
    non_day = len(rows) - len(days)
    if non_day:
        print(f"  NOTE: {non_day} window(s) recorded with is_day=false — these can NEVER "
              f"bank, whatever their verdict. Check the --label/--counts-as-day used.")

    # Ruling 130's logged-not-dropped clause survives ruling 136 unchanged: an
    # INCONCLUSIVE window is reported, never silently discarded.
    inconclusive = [r for r in days if (r.get("grade") or {}).get("verdict") == "INCONCLUSIVE"]
    if inconclusive:
        dates = sorted({(r.get("started_at") or "")[:10] for r in inconclusive})
        print(f"  INCONCLUSIVE: {len(inconclusive)} day-window(s) on {', '.join(dates)} "
              f"— neither banked nor counted against. Re-run them.")

    print(f"  clean UTC dates: {s['clean_dates']}")
    print(f"  consecutive clean days: {s['streak']}/{REQUIRED_CLEAN_DAYS}"
          f"   (streak ends at: {s['stopped_by']})")
    if s["streak"] >= REQUIRED_CLEAN_DAYS:
        print("  VERDICT: CLOSABLE — the 7-day falsifier was not refuted.")
        return RC_CLEAN
    if s["earliest_closure_date"]:
        print(f"  EARLIEST CLOSURE DATE: {s['earliest_closure_date']} "
              f"(UTC), and only if every day between banks.")
    print(f"  VERDICT: OPEN — {REQUIRED_CLEAN_DAYS - s['streak']} more clean day(s) required.")
    print("  Merge is not closure. Do not close #2107 on this.")
    return RC_FAILED


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=int, default=DEFAULT_WINDOW_MINUTES,
                    help=f"probe window length (default {DEFAULT_WINDOW_MINUTES}; see "
                         "DEFAULT_WINDOW_MINUTES for why 60 is not enough)")
    ap.add_argument("--interval", type=float, default=60.0, help="seconds between probes")
    ap.add_argument("--limit", type=int, default=20, help="/api/feed?limit=")
    ap.add_argument("--label", default="day",
                    help="free-text annotation for the window (see --counts-as-day)")
    ap.add_argument("--counts-as-day", dest="counts_as_day",
                    action=argparse.BooleanOptionalAction, default=None,
                    help="whether this window banks toward the seven. Defaults to "
                         "(--label == 'day') for backward compatibility.")
    ap.add_argument("--release-at", dest="release_at", action="append", default=[],
                    help="ISO8601 UTC timestamp of a production release inside the "
                         "lookback (ruling 136). Repeatable. Each one anchors a "
                         f"{DEPLOY_BLAST_WINDOW_MINUTES}-minute blast window.")
    ap.add_argument("--last-release-at", dest="last_release_at", default=None,
                    help="deprecated alias for a single --release-at, kept so existing "
                         "schedulers keep working")
    ap.add_argument("--releases-from-heroku", action="store_true",
                    help=f"read release times from `heroku releases -a {HEROKU_APP} --json`. "
                         "Fails soft and records boundary_source; failing soft is "
                         "fail-CLOSED, since fewer known boundaries means more errors "
                         "count as FAILED.")
    ap.add_argument("--fix-commit", dest="fix_commits", action="append", default=None,
                    help="commit that must be an ancestor of every observed slug "
                         f"(ruling 136 clause 4). Repeatable. Defaults to "
                         f"{', '.join(DEFAULT_FIX_COMMITS)}. Pass --fix-commit '' to skip, "
                         "which grades INCONCLUSIVE rather than CLEAN.")
    ap.add_argument("--state", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()

    if args.summarize:
        return summarize(args.state)

    api = os.getenv("BAINLUCK_API")
    if not api:
        print("#2107 watch: CANNOT MEASURE — BAINLUCK_API is not set (source ~/.claude/.env)")
        return RC_CANNOT_MEASURE

    fix_commits = (list(DEFAULT_FIX_COMMITS) if args.fix_commits is None
                   else [c for c in args.fix_commits if c])

    explicit: list[datetime] = []
    boundary_bits: list[str] = []
    for raw in list(args.release_at) + ([args.last_release_at] if args.last_release_at else []):
        parsed = _parse_stamp(raw)
        if parsed is None:
            print(f"#2107 watch: CANNOT MEASURE — --release-at {raw!r} is not ISO8601")
            return RC_CANNOT_MEASURE
        explicit.append(parsed)
    if explicit:
        boundary_bits.append(f"operator ({len(explicit)} release times)")
    if args.releases_from_heroku:
        stamps, source = heroku_release_times()
        explicit.extend(stamps)
        boundary_bits.append(source)
    boundary_source = " + ".join(boundary_bits) or "probe-observed transitions only"

    started = datetime.now(timezone.utc)
    # Resolve the banking decision BEFORE the hour of probing, and say it out loud.
    # `--label` used to double as the switch: any descriptive label silently set
    # `counts_toward_seven=false`, and the window burned an hour before anyone
    # could see it had never been eligible.
    counts_as_day = args.counts_as_day
    if counts_as_day is None:
        counts_as_day = args.label == "day"
    print(f"#2107 watch — probing {api}/api/feed every {args.interval:.0f}s for {args.minutes}m")
    print(f"   criterion: ruling 136 · blast window {DEPLOY_BLAST_WINDOW_MINUTES}m · "
          f"exposure floor {MIN_SERVED_REQUESTS} requests")
    print(f"   deploy boundaries: {boundary_source}")
    print(f"   fix commits checked: {', '.join(fix_commits) if fix_commits else 'NONE (will grade INCONCLUSIVE)'}")
    print(f"   label={args.label!r}  BANKS TOWARD THE SEVEN: {counts_as_day}"
          f"{'' if counts_as_day else '  <-- this window can never bank; pass --counts-as-day to change that'}")

    probe = run_probe(api, args.minutes, args.interval, args.limit)

    boundaries = deploy_boundaries(probe.get("timeline") or [], explicit)
    bands = blast_bands(boundaries)
    errors = attribute_errors(probe.get("failures") or [], bands)
    ancestry = check_fix_ancestry(probe.get("commits") or {}, fix_commits)
    sentry = sentry_events_since(
        os.getenv("SENTRY_AUTH_TOKEN"), bands, datetime.now(timezone.utc))
    grade = grade_window(
        probe, sentry, counts_as_day=counts_as_day, errors=errors,
        ancestry=ancestry, boundaries=boundaries, boundary_source=boundary_source)

    # The full timeline is a per-sample record and would dominate the state file;
    # the boundaries derived FROM it are what any later reader needs.
    probe_row = {k: v for k, v in probe.items() if k not in ("timeline", "sample_times")}
    row = {
        "issue": 2107,
        "label": args.label,
        "is_day": counts_as_day,
        "criterion": "ruling-136",
        "started_at": started.isoformat(),
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "probe": probe_row,
        "boundaries": boundaries,
        "boundary_source": boundary_source,
        "errors": {k: v for k, v in errors.items() if k.endswith("count")}
        | {"blast_window_events": errors["blast_window"]},
        "ancestry": ancestry,
        "sentry": sentry,
        "grade": grade,
        "counts_toward_seven": grade["counts_toward_seven"],
    }

    args.state.parent.mkdir(parents=True, exist_ok=True)
    with args.state.open("a") as fh:
        fh.write(json.dumps(row) + "\n")

    print(json.dumps(
        {k: row[k] for k in ("label", "boundary_source", "ancestry", "sentry", "grade")},
        indent=2))
    print(f"   recorded -> {args.state}")

    if grade["verdict"] == "CLEAN":
        return RC_CLEAN
    if grade["verdict"] == "FAILED":
        return RC_FAILED
    return RC_CANNOT_MEASURE


if __name__ == "__main__":
    sys.exit(main())
