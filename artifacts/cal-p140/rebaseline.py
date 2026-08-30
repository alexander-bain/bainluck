#!/usr/bin/env python3
"""CAL-P140 — the re-baseline monitor: score the post-repair window AND say what
each beat in it actually was.

WHY THIS EXISTS AND WHY IT IS NOT `calibration_freeze_score.py`
---------------------------------------------------------------
`calibration_freeze_score.py` answers ruling 009's question and only that one:
how many of the last 24 beats published. That is the right instrument for the
freeze and the wrong one for the two questions this window raises.

1. **A miss is not a miss.** CAL-P118-2 established four failure classes and they
   have completely different meanings for the freeze:

       A  GATE_REFUSAL   the publish gate refused (`gate == "refuse"`)
       B  DIAGNOSTICS    a statement in the diagnostics phase timed out
       C  DEPLOY_KILL    the beat was cancelled by a release mid-flight
       D  FIX_REGRESSION the sports `read:events` cancel that v3921/3200b840 repaired

   Only D indicts the fix. C is exogenous. A during 2026-08-29T01:38Z-20:21Z was
   a measurement of a missing Redis key (CAL-P139 §2), not of the producer. B is
   a standing, unrepaired defect that spends freeze budget every time it fires.
   A score that adds these together is a number with four meanings.

2. **A clean beat is not a datapoint.** §6e: a clean beat usually RE-SERVES the
   census it served last hour. It is a real observation of the PRODUCER — ruling
   009 counts it, correctly — and it is not an observation of the CALIBRATION.
   Twenty consecutive re-publishes of 1.88 pp are one reading, not twenty.

   So every clean beat is labelled `MEASUREMENT` or `REPUBLISH`, and the two are
   never summed.

   **The discriminator is `disclosure.staged_at`, and it is NOT
   `frozen_over_drift`.** That was this instrument's first draft and it was
   wrong, in the direction that would have labelled every beat from here to the
   end of time a re-publish. Read the source: under a rolling re-stage
   (`calibration_staged_disclosure.py:267`) the serving branch computes
   `frozen_over_drift = not drift_known_zero` — it is a statement about whether
   the served census has DRIFTED since it was taken, which it always has by the
   second beat. It says nothing about whether the bank advanced.

   What actually advances the population is `promote_if_complete`
   (`calibration_staged_futures.py:1736`): the moment the rebuild covers all 128
   planned units it is promoted into the serving slot, `staged_at` is re-stamped
   to that instant, and a fresh rebuild starts at zero. So a NEW `staged_at` is a
   new census and everything else is the same census re-served.

   The trap that makes this worth spelling out: in the ring, the rebuild is never
   observed AT 128. It is observed at 122, 119, 121, 94, 122, 123, 124, 127 and
   then at 0, because the promotion happens inside the beat that completes it.
   Read as a gauge that resets, that is eight rebuilds dying just short. Read
   against `staged_at`, which advances every single time, it is eight successful
   promotions. **A counter returning to zero does not say which of the two it
   was; the timestamp beside it does.**

   `input_fingerprint` is NOT a population marker either — per
   `REASON_INPUT_FINGERPRINT` it hashes the build's SQL functions, so it moves on
   a deploy and not on a census.

THE HONESTY CONSTRAINT THAT SHAPES THE CODE
--------------------------------------------
**B and D are indistinguishable in the ring.** Both land as
`terminal="failed", gate="not_evaluated"`; the ring observation carries
`gauges` and `disclosure` but no stage timings and no error. The only place the
error lives is `task-metrics.last_error`, which holds exactly ONE failure — the
most recent — and is overwritten by the next one.

Therefore: this script attributes a `failed/not_evaluated` beat ONLY when
`task-metrics.last_failure_at` matches that beat's stamp. Otherwise it emits
`B_OR_D_UNATTRIBUTED` and says so. It does not infer the class from `elapsed_ms`
sitting in the band where B usually lands, because that is shape-matching, and
gotcha #53's lesson generalises: a plausible reading of an absent signal is
still an absent signal.

The operational consequence is the whole reason the runner directive says
"classify as they happen, not after": **a miss unclassified within one beat is
unclassifiable forever.**

WHY `--watch` IS NOT A CONVENIENCE
-----------------------------------
The window is 24 hours long and no session is. `--watch` polls the ring, and the
first time it sees a beat it classifies it — reading `last_error` while that
error is still the producer's most recent — and appends the verdict to a JSONL
that later runs never rewrite. The log is the durable half of the instrument:
once a beat is in it, its attribution survives every subsequent failure.

A beat already in the log is never re-read, so a late reader cannot downgrade an
attribution it can no longer make.

USAGE
-----
    source ~/.claude/.env
    python3 artifacts/cal-p140/rebaseline.py --baseline-at 2026-08-29T23:35:53Z
    python3 artifacts/cal-p140/rebaseline.py --baseline-at ... --json > rebaseline.json
    python3 artifacts/cal-p140/rebaseline.py --baseline-at ... \
        --watch --log artifacts/cal-p140/window-log.jsonl --interval 420

Read-only against production. Needs BAINLUCK_API and ADMIN_TOKEN.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

WINDOW = 24
CLEAN_REQUIRED = 22
HISTORY_IDENTITY = "calibration:beat_gauge_history"
PRODUCER_TASK = "precompute_calibration_main"

#: How close `last_failure_at` must sit to a beat's `generated_at` for the error
#: to be that beat's. The producer stamps the ring observation and the failure
#: counter within the same terminal handler; the observed gap is ~0.1 s. Two
#: minutes is loose enough to survive a slow handler and far tighter than the
#: ~1 h beat cadence, so it can never claim a neighbour's error.
ATTRIBUTION_TOLERANCE_S = 120

#: Substrings that identify a class from the producer's own exception text.
#: Ordered; first hit wins. Every one of these is a phrase the producer emits,
#: not a phrase this script invents.
ERROR_SIGNATURES = [
    ("B_DIAGNOSTICS_TRUTH_CENSUS", r"resolution_source"),
    ("D_FIX_REGRESSION_READ_EVENTS", r"read:events|FROM\s+events\b"),
    ("B_DIAGNOSTICS_OTHER", r"statement timeout|QueryCanceledError"),
]

SQL_RING = (
    "SELECT o->>'generation' AS generation, o::text AS observation "
    "FROM durable_state_snapshots d, "
    "jsonb_array_elements(d.payload->'observations') o "
    f"WHERE d.identity = '{HISTORY_IDENTITY}' "
    "ORDER BY 1"
)


class MonitorError(RuntimeError):
    """Could not measure. Distinct from measuring something bad."""


def _get(url: str, token: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise MonitorError(f"HTTP {exc.code}: {exc.read().decode()[:300]}") from None
    except urllib.error.URLError as exc:
        raise MonitorError(f"unreachable: {exc.reason}") from None


def _post(api: str, token: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/admin/db-query",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise MonitorError(f"HTTP {exc.code}: {exc.read().decode()[:300]}") from None
    except urllib.error.URLError as exc:
        raise MonitorError(f"unreachable: {exc.reason}") from None


def parse_stamp(text):
    if not text:
        return None
    try:
        stamp = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=datetime.timezone.utc)
    return stamp.astimezone(datetime.timezone.utc)


def classify_error(error_text: str) -> str:
    for label, pattern in ERROR_SIGNATURES:
        if re.search(pattern, error_text or "", re.IGNORECASE):
            return label
    return "B_OR_D_UNRECOGNISED_ERROR"


def classify(obs: dict, *, live_error=None, previous_staged_at=None) -> dict:
    """One beat -> one class. Pure, so every branch is reachable from a test.

    ``live_error`` is ``(failure_at, error_text)`` from task-metrics, or None. It
    is consulted ONLY for the ambiguous class and ONLY when its stamp matches.

    ``previous_staged_at`` is the served census of the last PUBLISHED beat, and
    it is what makes the §6e call. ``None`` means there is no previous published
    beat to compare against — the first beat of a window — and that is reported
    as ``MEASUREMENT_UNKNOWN`` rather than guessed either way.
    """
    outcome = obs.get("outcome") or {}
    disclosure = obs.get("disclosure") or {}
    terminal = obs.get("terminal")
    gate = outcome.get("gate")
    published = outcome.get("published") is True
    stamp = parse_stamp(obs.get("generated_at"))

    clean = published and terminal == "complete" and gate == "pass"

    if clean:
        # §6e. See the module docstring: a NEW staged_at is a new census; the
        # same staged_at is the same census re-served, however fresh the
        # payload's own generated_at looks.
        staged_at = disclosure.get("staged_at")
        if staged_at is None:
            kind, why = "MEASUREMENT_UNKNOWN", "published — the beat disclosed no staged_at"
        elif previous_staged_at is None:
            kind, why = (
                "MEASUREMENT_UNKNOWN",
                f"published — served the census promoted at {staged_at}; no prior "
                "published beat in this window to compare it against",
            )
        elif staged_at != previous_staged_at:
            kind, why = (
                "MEASUREMENT",
                f"published — a NEW census was promoted at {staged_at} "
                f"(previous {previous_staged_at}); the population moved",
            )
        else:
            kind, why = (
                "REPUBLISH",
                f"published — re-served the census promoted at {staged_at}; "
                f"the rebuild stands at {disclosure.get('rebuild_units_banked')}/128",
            )
        return {"class": "CLEAN", "datapoint": kind, "attribution": why,
                "staged_at": staged_at}

    if gate == "refuse":
        return {
            "class": "A_GATE_REFUSAL",
            "datapoint": "MISS",
            "attribution": "publish gate refused; the gate's codes are in the beat's own outcome",
        }

    if terminal == "cancelled":
        return {
            "class": "C_DEPLOY_KILL",
            "datapoint": "MISS",
            "attribution": (
                f"task cancelled mid-flight after {obs.get('elapsed_ms')} ms — "
                "a release, not the producer"
            ),
        }

    if terminal == "failed" and gate == "not_evaluated":
        if live_error is not None:
            failure_at, error_text = live_error
            if (
                failure_at is not None
                and stamp is not None
                and abs((failure_at - stamp).total_seconds()) <= ATTRIBUTION_TOLERANCE_S
            ):
                return {
                    "class": classify_error(error_text),
                    "datapoint": "MISS",
                    "attribution": (error_text or "").strip().split("\n")[0][:240],
                    "attributed_from": "task-metrics.last_error",
                    "attribution_gap_s": round((failure_at - stamp).total_seconds(), 3),
                }
        return {
            "class": "B_OR_D_UNATTRIBUTED",
            "datapoint": "MISS",
            "attribution": (
                "failed before the gate was evaluated. B (diagnostics timeout) and D "
                "(the read:events regression) are indistinguishable in the ring; the "
                "error lived in task-metrics.last_error and has been overwritten."
            ),
        }

    return {
        "class": "UNCLASSIFIED",
        "datapoint": "MISS",
        "attribution": f"terminal={terminal!r} gate={gate!r} published={published!r} — a shape the taxonomy does not name",
    }


#: A ring observation and the producer run that made it are stamped by the same
#: terminal handler, but the sampler writes the ring on its own schedule. 90 s is
#: far wider than the observed gap and far narrower than the beat cadence.
COVERAGE_TOLERANCE_S = 90


def sampler_coverage(ring_generations_ms, producer_run_ends_s) -> dict:
    """Is the ring a complete record of the runs the producer admits to?

    This is load-bearing and asymmetric, which is why it is checked at all: the
    freeze score is a count of clean beats among the observations that EXIST. A
    beat the sampler drops is invisible, and an invisible MISS raises the score.
    So a gap in the ring cannot make the freeze look worse than it is — only
    better. That is the direction that must never go unmeasured.

    The newest run is expected to be missing whenever the sampler has not yet
    run since it, so it is reported separately from a real drop.
    """
    ring = sorted(float(g) / 1000.0 for g in ring_generations_ms)
    ends = sorted(float(e) for e in producer_run_ends_s)
    if not ends:
        return {"checked": False, "reason": "producer reported no run ends"}

    def seen(end):
        return any(abs(g - end) <= COVERAGE_TOLERANCE_S for g in ring)

    missing = [e for e in ends if not seen(e)]
    newest = ends[-1]
    pending = [e for e in missing if e == newest]
    dropped = [e for e in missing if e != newest]

    fmt = lambda e: datetime.datetime.fromtimestamp(  # noqa: E731
        e, datetime.timezone.utc
    ).isoformat().replace("+00:00", "Z")
    return {
        "checked": True,
        "producer_runs_examined": len(ends),
        "dropped_by_sampler": len(dropped),
        "dropped_at": [fmt(e) for e in dropped],
        "awaiting_sampler": [fmt(e) for e in pending],
        "complete": not dropped,
        "note": (
            "a dropped observation can only RAISE the freeze score, never lower it"
        ),
    }


def build(observations, *, baseline, live_error=None, window=WINDOW,
          required=CLEAN_REQUIRED, coverage=None):
    ordered = sorted(observations, key=lambda o: int(o["generation"]))

    eligible, excluded = [], 0
    for obs in ordered:
        stamp = parse_stamp(obs.get("generated_at"))
        if baseline is not None and (stamp is None or stamp < baseline):
            excluded += 1
        else:
            eligible.append(obs)

    considered = eligible[-window:]

    beats, counts, datapoints = [], {}, {}
    # Carried across the loop because §6e is a question about a beat's relation
    # to the last one that PUBLISHED — a miss serves nothing and cannot reset it.
    previous_staged_at = None
    for i, obs in enumerate(considered, start=1):
        verdict = classify(obs, live_error=live_error,
                           previous_staged_at=previous_staged_at)
        disclosure = obs.get("disclosure") or {}
        if verdict["class"] == "CLEAN" and disclosure.get("staged_at"):
            previous_staged_at = disclosure["staged_at"]
        beats.append(
            {
                "n": i,
                "generated_at": obs.get("generated_at"),
                "terminal": obs.get("terminal"),
                "gate": (obs.get("outcome") or {}).get("gate"),
                "elapsed_ms": obs.get("elapsed_ms"),
                "staged_at": disclosure.get("staged_at"),
                "frozen_over_drift": disclosure.get("frozen_over_drift"),
                "rebuild_units_banked": disclosure.get("rebuild_units_banked"),
                "units_banked": disclosure.get("units_banked"),
                "beats_to_publish": (obs.get("gauges") or {}).get("staged:beats_to_publish"),
                "input_fingerprint": obs.get("input_fingerprint"),
                **verdict,
            }
        )
        counts[verdict["class"]] = counts.get(verdict["class"], 0) + 1
        datapoints[verdict["datapoint"]] = datapoints.get(verdict["datapoint"], 0) + 1

    clean = counts.get("CLEAN", 0)
    misses = len(considered) - clean
    if len(considered) < window:
        verdict = "WINDOW_NOT_FULL"
    elif clean >= required:
        verdict = "CONDITION_MET"
    else:
        verdict = "NOT_MET"

    # Distinct served censuses in the window. Each additional one is a
    # `promote_if_complete` that landed inside it.
    censuses = sorted({b["staged_at"] for b in beats if b.get("staged_at")})
    fingerprints = sorted({b["input_fingerprint"] for b in beats if b["input_fingerprint"]})

    return {
        "instrument": "CAL-P140 rebaseline monitor",
        "taxonomy": "CAL-P118-2 (A gate-refusal / B diagnostics / C deploy-kill / D fix-regression)",
        "condition": f"{required} of the last {window}",
        "baseline_at": baseline.isoformat() if baseline else None,
        "verdict": verdict,
        "clean": clean,
        "misses": misses,
        "misses_allowed": window - required,
        "misses_remaining": (window - required) - misses,
        "beats_in_window": len(considered),
        "window": window,
        "excluded_pre_baseline": excluded,
        "ring_observations": len(ordered),
        "class_counts": counts,
        "datapoint_counts": datapoints,
        # §6e. Kept separate from `clean` on purpose: summing them is the error
        # the discipline exists to prevent.
        "measurement_events": datapoints.get("MEASUREMENT", 0),
        "republishes": datapoints.get("REPUBLISH", 0),
        "measurement_unknown": datapoints.get("MEASUREMENT_UNKNOWN", 0),
        "censuses_served_in_window": censuses,
        "promotions_in_window": max(0, len(censuses) - 1),
        # Kept, but demoted to what it is: a marker of DEPLOYS, not of censuses.
        "input_fingerprints_in_window": fingerprints,
        "sampler_coverage": coverage,
        "beats": beats,
    }


def render(result: dict) -> str:
    glyph = {
        "CLEAN": "#",
        "A_GATE_REFUSAL": "A",
        "B_DIAGNOSTICS_TRUTH_CENSUS": "B",
        "B_DIAGNOSTICS_OTHER": "B",
        "D_FIX_REGRESSION_READ_EVENTS": "D",
        "C_DEPLOY_KILL": "C",
        "B_OR_D_UNATTRIBUTED": "?",
        "B_OR_D_UNRECOGNISED_ERROR": "?",
        "UNCLASSIFIED": "!",
    }
    strip = "".join(glyph.get(b["class"], "!") for b in result["beats"])
    full = result["beats_in_window"] == result["window"]
    head = (
        f"  {result['clean']}/{result['window']} clean"
        if full
        else f"  {result['clean']}/{result['beats_in_window']} clean so far (window {result['window']})"
    )
    lines = [
        "CAL-P140 RE-BASELINE MONITOR — " + result["condition"],
        head + f"   ({result['misses']} misses; {result['misses_remaining']} of "
        f"{result['misses_allowed']} budget left)",
        f"  {strip}   <- oldest ... newest   (# clean, A/B/C/D miss class, ? unattributed)",
        f"  baseline {result['baseline_at']}",
        f"  ring     {result['ring_observations']} observations, "
        f"{result['excluded_pre_baseline']} excluded as pre-baseline",
        f"  VERDICT  {result['verdict']}",
        "",
        "  §6e — what the clean beats are (discriminator: disclosure.staged_at):",
        f"    MEASUREMENT  a new census was promoted, the number could move: {result['measurement_events']}",
        f"    REPUBLISH    the same census re-served, one reading:           {result['republishes']}",
        f"    UNKNOWN      no prior published beat to compare against:       {result['measurement_unknown']}",
        f"    censuses served in window: {len(result['censuses_served_in_window'])}"
        f"  -> promotions inside it: {result['promotions_in_window']}",
        "",
        "  misses by class:",
    ]
    misses = [b for b in result["beats"] if b["class"] != "CLEAN"]
    if not misses:
        lines.append("    (none)")
    for b in misses:
        lines.append(f"    #{b['n']:>2} {b['generated_at']}  {b['class']}")
        lines.append(f"        {b['attribution'][:150]}")
    if any(b["class"].startswith("B_OR_D") for b in misses):
        lines += [
            "",
            "  ⚠️  At least one miss is UNATTRIBUTED. B and D are indistinguishable in the",
            "      ring; the error lives in task-metrics.last_error and is overwritten by",
            "      the next failure. A miss not classified within one beat is unclassifiable.",
        ]
    cov = result.get("sampler_coverage") or {}
    if cov.get("checked"):
        lines += [
            "",
            f"  sampler coverage: {cov['producer_runs_examined']} producer runs examined, "
            f"{cov['dropped_by_sampler']} dropped"
            + (f", {len(cov['awaiting_sampler'])} awaiting the sampler" if cov["awaiting_sampler"] else ""),
        ]
        if not cov["complete"]:
            lines.append(
                "  ⚠️  THE RING IS INCOMPLETE. Dropped beats are invisible to the score and a "
                "dropped MISS inflates it: " + ", ".join(cov["dropped_at"][:6])
            )
    return "\n".join(lines)


def read_ring(api: str, token: str) -> list[dict]:
    payload = _post(api, token, {"sql": SQL_RING, "limit": 400})
    columns = payload.get("columns") or []
    rows = [dict(zip(columns, r)) for r in (payload.get("rows") or [])]
    if not rows:
        # gotcha #53 — an empty 200 is a shape, not an absence. An empty ring is
        # the sampler failing and must never render as a score of zero.
        raise MonitorError(
            f"{HISTORY_IDENTITY} returned NO observations — that is the sampler down, "
            "not a clean count of zero"
        )
    observations = []
    for row in rows:
        obs = json.loads(row["observation"])
        obs["generation"] = row["generation"]
        observations.append(obs)
    return observations


def read_producer(api: str, token: str):
    """Returns ``(live_error, run_ends_s)``; either half may be None/empty."""
    metrics = _get(f"{api.rstrip('/')}/api/admin/task-metrics?task={PRODUCER_TASK}", token)
    live_error = (parse_stamp(metrics.get("last_failure_at")), metrics.get("last_error") or "")
    return live_error, metrics.get("recent_durations_at") or []


def snapshot(api: str, token: str, baseline):
    observations = read_ring(api, token)
    live_error, run_ends = None, []
    try:
        live_error, run_ends = read_producer(api, token)
    except MonitorError as exc:
        print(f"WARNING: task-metrics unreadable ({exc}); misses stay unattributed",
              file=sys.stderr)
    coverage = sampler_coverage([o["generation"] for o in observations], run_ends)
    result = build(observations, baseline=baseline, live_error=live_error,
                   coverage=coverage)
    if live_error:
        result["live_error_stamp"] = live_error[0].isoformat() if live_error[0] else None
    return result


def watch(api, token, baseline, log_path, interval, deadline_beats=WINDOW) -> int:
    """Classify each beat the first time it is seen, and never again.

    The log is append-only and keyed on ``generated_at``. A beat already logged
    is skipped whole — not re-classified — because the attribution captured at
    first sight is strictly better evidence than anything a later pass can
    reconstruct.
    """
    seen = set()
    if os.path.exists(log_path):
        with open(log_path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    seen.add(json.loads(line).get("generated_at"))
        print(f"resuming: {len(seen)} beats already classified in {log_path}")

    while True:
        try:
            result = snapshot(api, token, baseline)
        except MonitorError as exc:
            # A read failure is a failure to MEASURE, never a miss. Recording it
            # as a beat would be inventing a datapoint out of our own outage.
            print(f"[{_now()}] read failed, not a beat: {exc}", file=sys.stderr)
            time.sleep(interval)
            continue

        fresh = [b for b in result["beats"] if b["generated_at"] not in seen]
        with open(log_path, "a") as fh:
            for beat in fresh:
                beat["classified_at"] = _now()
                fh.write(json.dumps(beat) + "\n")
                seen.add(beat["generated_at"])
                print(f"[{_now()}] beat #{beat['n']} {beat['generated_at']} -> "
                      f"{beat['class']} / {beat['datapoint']}")
        if not fresh:
            print(f"[{_now()}] no new beat; {result['clean']}/{result['beats_in_window']} clean, "
                  f"{result['misses_remaining']} budget left")

        if result["beats_in_window"] >= deadline_beats:
            print(f"[{_now()}] window full — {result['verdict']}")
            print(render(result))
            return 0
        time.sleep(interval)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--baseline-at", required=True,
                    help="ISO-8601 instant of the re-baseline. Beats before it are excluded.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--watch", action="store_true",
                    help="poll until the window is full, classifying each beat on first sight")
    ap.add_argument("--log", default="artifacts/cal-p140/window-log.jsonl",
                    help="append-only JSONL of first-sight classifications (--watch)")
    ap.add_argument("--interval", type=int, default=420,
                    help="seconds between polls (--watch); must be well under the beat cadence")
    args = ap.parse_args(argv)

    api = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not api or not token:
        print("BAINLUCK_API and ADMIN_TOKEN required (source ~/.claude/.env)", file=sys.stderr)
        return 2

    baseline = parse_stamp(args.baseline_at)
    if baseline is None:
        print(f"unparseable --baseline-at: {args.baseline_at}", file=sys.stderr)
        return 2

    if args.watch:
        return watch(api, token, baseline, args.log, args.interval)

    try:
        result = snapshot(api, token, baseline)
    except MonitorError as exc:
        print(f"could not measure: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
