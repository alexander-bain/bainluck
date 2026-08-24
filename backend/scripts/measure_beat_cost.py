#!/usr/bin/env python3
"""Measure a beat's COST from production task-metrics, so `beat_cost:` is a
measurement rather than a hand-written field.

Ruling 127 item 3 (the PROGRAM CHARTER AMENDMENT) requires a `beat_cost:`
declaration on the `migration_slot` / `beat_schedule_change` pattern. lane1's
doctrine clause 20 — *a hand-written field is unvalidated input, not a
measurement* — is why this script exists rather than a note asking lanes to
estimate: a field a human types is a claim, and the Integrator cannot tell a
careful claim from a careless one. This prints the exact block to paste, from
numbers nobody chose.

## The named failure it prices

CAL-P078's rolling re-stage (v3874, 2026-08-20 10:45:57 PDT) took
`precompute_calibration_main` from a p50 of 163 s to 1,263 s — **7.74x**, on the
one beat a user-facing page waits on — with no declaration anywhere. The cost of
that silence was three latency cycles spent establishing the step was not caused
by ruling 110's routing change, plus a falsifier baseline that read ~6x against
a perfectly healthy beat until ruling 123 re-pinned it.

**The flag does not forbid the change.** That re-stage was correct and would have
been approved. It makes a regime change arrive ANNOUNCED.

## What "cost" means here — three numbers, because one hides two

* **p50_s** — the median run. What a regime step moves, and what ruling 110's
  falsifier grades on.
* **slot_seconds_per_day** = `p50_s * runs_24h`. A beat that doubles its p50 but
  halves its frequency costs the same worker capacity; a p50 alone cannot say
  that. This is the number a QUEUE feels.
* **pct_of_soft_limit** = `p95_s / soft_time_limit_s`. Headroom. A beat at 93 %
  of its limit is one bad day from `SoftTimeLimitExceeded`, and that is invisible
  in both numbers above.

## Exit codes (gotcha #54 — read the VALUE, not just non-zero)

    0  measured
    3  task-metrics unreadable — a story about the harness, never a result
    4  usage error

Usage:
    source ~/.claude/.env
    python3 backend/scripts/measure_beat_cost.py --task precompute_calibration_main
    python3 backend/scripts/measure_beat_cost.py --all-watched --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

EXIT_OK = 0
EXIT_UNREADABLE = 3
EXIT_USAGE = 4

#: A change that moves a beat by LESS than both of these does not need a
#: declaration. Deliberately the SAME two-gate shape as ruling 126's degradation
#: predicate, and for the same reason: a pure ratio is sharpest where a beat
#: matters least, so +4s on a 17s beat would demand a declaration while +297s on
#: the beat a page waits on would not. Both gates, always AND.
DECLARE_RATIO = 1.25
DECLARE_ABSOLUTE_S = 60.0

#: ...and either of these ALONE forces a declaration whatever the p50 did,
#: because both are failure modes a median cannot see.
DECLARE_PCT_OF_SOFT_LIMIT = 0.80
DECLARE_SLOT_SECONDS_PER_DAY = 3600.0  # one worker-slot-hour per day


def _get(base: str, path: str, token: str, timeout: float = 30.0):
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.getcode() != 200:
            raise RuntimeError(f"{path} returned {resp.getcode()}")
        return json.loads(resp.read())


def _p50(durations_ms):
    vals = sorted(float(d) for d in (durations_ms or []) if d is not None)
    if not vals:
        return None
    return round(vals[len(vals) // 2] / 1000.0, 3)


def _pct(durations_ms, q):
    vals = sorted(float(d) for d in (durations_ms or []) if d is not None)
    if not vals:
        return None
    idx = max(0, min(len(vals) - 1, int(q * len(vals)) - 1))
    return round(vals[idx] / 1000.0, 3)


def measure(base: str, token: str, metrics_name: str, soft_limit_s: float | None) -> dict:
    m = _get(base, f"/api/admin/celery/task-metrics/{urllib.parse.quote(metrics_name)}", token)
    if not m or not isinstance(m, dict):
        raise RuntimeError(f"no metrics under {metrics_name!r}")

    durations = m.get("recent_durations_ms") or []
    p50 = _p50(durations)
    p95 = _pct(durations, 0.95)
    successes = m.get("successes_24h")
    failures = m.get("failures_24h")
    runs = None
    runs_note = None
    if successes is not None or failures is not None:
        runs = int(successes or 0) + int(failures or 0)

    # 🔴 ZERO COUNTERS OVER A LIVE RING MEAN THE COUNTERS EXPIRED, NOT THAT THE
    # BEAT IS IDLE. This is #2110 defect (b) one level out, and the first run of
    # this script committed it: `precompute_calibration_main` reported
    # `runs_24h 0` and therefore `slot_seconds_per_day 0` — a beat that runs
    # hourly and costs ~1,300 s a run, rendered as costing NOTHING, in the very
    # field the Integrator would read to decide whether a declaration is needed.
    #
    # The counters expire; the ring does not. A ring with samples in it is
    # positive evidence the beat has run, so a zero counter beside it is a fact
    # about the counter. `runs_24h` is set to None and every field derived from
    # it goes with it — an unknown cost must never render as a zero cost.
    if runs == 0 and durations:
        runs_note = (
            "counters read 0 over a NON-EMPTY duration ring — the 24h counters "
            "have expired, they have not observed an idle beat. Cost per day is "
            "UNKNOWN here, not zero; re-read after the counters refill or "
            "supply runs/24h from the beat schedule."
        )
        runs = None

    out = {
        "metrics_name": metrics_name,
        "samples": len(durations),
        "p50_s": p50,
        "p95_s": p95,
        "runs_24h": runs,
        "soft_time_limit_s": soft_limit_s,
        # 🔴 An ABSENT read and a ZERO read must never render the same
        # (gotcha #53). Every derived field below is `None` when its inputs are
        # missing, never 0 — a beat we could not read must not report as a beat
        # that costs nothing.
        "slot_seconds_per_day": (
            round(p50 * runs, 1) if (p50 is not None and runs is not None) else None
        ),
        "pct_of_soft_limit": (
            round(p95 / soft_limit_s, 3)
            if (p95 is not None and soft_limit_s)
            else None
        ),
    }
    out["runs_24h_note"] = runs_note
    out["declaration_forced_by"] = _forced_by(out)
    return out


def _forced_by(row: dict) -> list[str]:
    """Which standing thresholds this beat ALREADY sits past, ratio aside.

    The ratio/absolute pair needs a BEFORE, which only the changing lane has.
    These two do not — they are properties of the current reading, so the script
    can answer them and a lane cannot forget them.
    """
    hits = []
    pct = row.get("pct_of_soft_limit")
    if pct is not None and pct >= DECLARE_PCT_OF_SOFT_LIMIT:
        hits.append(
            f"pct_of_soft_limit {pct:.0%} >= {DECLARE_PCT_OF_SOFT_LIMIT:.0%}"
        )
    ssd = row.get("slot_seconds_per_day")
    if ssd is not None and ssd >= DECLARE_SLOT_SECONDS_PER_DAY:
        hits.append(
            f"slot_seconds_per_day {ssd:.0f} >= {DECLARE_SLOT_SECONDS_PER_DAY:.0f}"
        )
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BAINLUCK_API", "https://api.bainluck.com"))
    ap.add_argument("--task", action="append", default=[], help="metrics name; repeatable")
    ap.add_argument("--all-watched", action="store_true", help="every ruling-110 watched beat")
    ap.add_argument("--soft-limit", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        print("ADMIN_TOKEN unset — `source ~/.claude/.env`", file=sys.stderr)
        return EXIT_USAGE

    targets: list[tuple[str, float | None]] = [(t, args.soft_limit) for t in args.task]
    if args.all_watched:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from app.utils.heavy_routing_falsifier import PRE_MOVE_BASELINE

        targets += [
            (b.metrics_name, float(b.soft_time_limit_s)) for b in PRE_MOVE_BASELINE
        ]
    if not targets:
        print("nothing to measure: pass --task or --all-watched", file=sys.stderr)
        return EXIT_USAGE

    rows = []
    for name, soft in targets:
        try:
            rows.append(measure(args.base, token, name, soft))
        except Exception as exc:  # noqa: BLE001
            print(f"UNREADABLE {name}: {exc}", file=sys.stderr)
            return EXIT_UNREADABLE

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return EXIT_OK

    print(
        f"{'beat':36s} {'p50_s':>8s} {'p95_s':>8s} {'runs/24h':>9s} "
        f"{'slot_s/day':>11s} {'%soft':>7s}"
    )
    for r in rows:
        def _f(v, spec, width):
            # An unreadable field prints as "—" and is padded to the SAME width
            # as a number, so a row with a gap in it still lines up under its
            # headers. A misaligned row is read as a different row.
            return f"{'—':>{width}}" if v is None else format(v, spec)

        pct = r["pct_of_soft_limit"]
        print(
            f"{r['metrics_name']:36s} {_f(r['p50_s'], '8.1f', 8)} "
            f"{_f(r['p95_s'], '8.1f', 8)} {_f(r['runs_24h'], '9d', 9)} "
            f"{_f(r['slot_seconds_per_day'], '11.0f', 11)} "
            f"{(('%.0f%%' % (100 * pct)) if pct is not None else '—'):>7s}"
        )
        for why in r["declaration_forced_by"]:
            print(f"    🔴 beat_cost DECLARATION FORCED: {why}")
        if r.get("runs_24h_note"):
            print(f"    ⚠️  {r['runs_24h_note']}")

    print(
        f"\nRatio/absolute gates need a BEFORE, which only the changing lane has: "
        f"declare when p50 rises >= {DECLARE_RATIO}x AND >= {DECLARE_ABSOLUTE_S:.0f}s. "
        f"Spec: docs/doctrine.md, 'MECHANICAL SPEC — beat_cost'."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
