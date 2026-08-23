#!/usr/bin/env python3
"""Grade ruling 110's surviving predictions from the falsifier payload.

## Why this exists

The ≥6 h horizon read has been defeated five consecutive times, and the sixth
attempt runs under a bought deploy freeze. A protected window is the worst place
to be composing queries, deciding thresholds, or discovering that a field is
named something else. **Everything that can be decided before the horizon is
decided here**; the morning window only READS.

So this script takes no measurement of its own. It consumes one payload —
`GET /api/admin/heavy-move/falsifier` — and renders the verdict that ruling 110
obliges, against thresholds imported from the falsifier module rather than
re-typed (a second copy of `DEGRADE_P50_RATIO` is a second thing to drift).

## What is graded, and what is NOT

Ruling 110 registered four predictions and then retired two BY NAME.

* **P1** (period p95 < 200 s) and **P2** (loss < 20 %) are **RETIRED** and are
  not graded here. LAT-P078 measured 90.6 s and 19 % with the routing *not
  deployed*, so both were already satisfied by the null and would have been
  credited to the intervention. They are not rescuable by a new threshold
  either: period p95 has measured 176.5 / 292.7 / 90.6 / ~106–117 s, a
  between-window spread of **3.2×**, against a predicted effect of ~2×. A
  statistic whose between-window spread exceeds the effect cannot discriminate
  it at one window per arm. **If a future reader wants them back, they need a
  different statistic, not a different cutoff.**
* **P3** — the control: no PROTECTED beat degrades. Fails if any protected beat
  grades `degraded`.
* **P4** — promoted to primary: the two moved tasks' 24 h run counts RISE toward
  schedule, because they were starved rather than idle (31→72, 45→96). Computed
  in the payload; this reads it.
* **P5** — at a horizon where the falsifier is no longer `pre_horizon`, its
  verdict is `HOLD`. Failable as `REVERT` and, since the LAT-P079 amendment, as
  `INCONCLUSIVE`.

## 🔴 The REVERT obligation

Ruling 110 was granted on the deal that a `REVERT` reverts the routing **in the
same window that reads it**. This script exits **2** on REVERT so it cannot be
scrolled past. See the exit-code table below.

## Exit codes — read the VALUE, not just non-zero (gotcha #54)

    0  graded, and nothing failed (may include honestly pre-horizon predictions)
    1  a prediction FAILED, but no REVERT — report it, no routing change owed
    2  🔴 REVERT — ruling 110's routing reverts in THIS window
    3  the payload could not be read or parsed — a story about the harness,
       never a result about the move

## Usage

    # the morning window, live:
    source ~/.claude/.env
    python3 backend/scripts/grade_ruling_110.py --live --out docs/audits/latency/....json

    # offline, against a payload already captured (no production read):
    python3 backend/scripts/grade_ruling_110.py --from-file /tmp/falsifier.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

# Thresholds come FROM the instrument. Never re-typed here.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.utils.heavy_routing_falsifier import (  # noqa: E402
    DEGRADE_P50_RATIO,
    HEAVY_MOVE_EXCEPTION,
    MIN_POST_MOVE_SAMPLES,
    MOVER_PRE_MOVE,
)

EXIT_OK = 0
EXIT_PREDICTION_FAILED = 1
EXIT_REVERT = 2
EXIT_UNREADABLE = 3

#: Ruling 110's retired predictions, kept BY NAME so a future reader sees they
#: were retired rather than forgotten (the retirement is the finding).
RETIRED = {
    "P1": "period p95 < 200 s — pre-satisfied by the null (90.6 s, routing not deployed)",
    "P2": "loss < 20 % — pre-satisfied by the null (19 %, routing not deployed)",
}


def _fetch_live() -> dict[str, Any]:
    base = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not base or not token:
        raise RuntimeError(
            "BAINLUCK_API and ADMIN_TOKEN must be set — `source ~/.claude/.env`"
        )
    req = urllib.request.Request(
        f"{base}/api/admin/heavy-move/falsifier",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def grade_p3(payload: dict[str, Any]) -> dict[str, Any]:
    """The control: no PROTECTED beat degrades."""
    beats = payload.get("beats") or []
    degraded = [b for b in beats if b.get("verdict") == "degraded"]
    pre_horizon = [b for b in beats if b.get("verdict") == "pre_horizon"]
    censored = [b for b in beats if b.get("verdict") == "censored"]
    gradeable = [b for b in beats if b.get("verdict") not in ("pre_horizon", "censored")]

    if degraded:
        verdict = "FAILED"
    elif not gradeable:
        verdict = "PRE_HORIZON"
    else:
        verdict = "PASSED"

    # 🔴 A BARE "PASSED" OVERSTATES A PARTIAL READ. P3 passing on 3 of 7 beats is
    # a different claim from P3 passing on 7 of 7, and the rendered table is what
    # the window actually reads. Coverage is therefore part of the verdict line,
    # not buried in the JSON — the same reason `observed` exists on the movers.
    coverage = f"{len(gradeable)}/{len(beats)} beats gradeable"

    return {
        "prediction": "P3",
        "claim": f"no protected beat degrades (p50 ratio <= {DEGRADE_P50_RATIO}x)",
        "verdict": verdict,
        "beats_total": len(beats),
        "beats_gradeable": len(gradeable),
        "beats_pre_horizon": len(pre_horizon),
        "beats_censored": len(censored),
        "degraded": [
            {"task": b.get("task"), "ratio": b.get("ratio"), "reason": b.get("reason")}
            for b in degraded
        ],
        "coverage": coverage,
        # A censored beat is not a pass. Gotcha #146: a percentile at a ceiling
        # is a fact about the clip rate, never about the distribution under it.
        "note": ", ".join(
            part
            for part in (
                coverage,
                f"{len(pre_horizon)} pre-horizon" if pre_horizon else "",
                f"{len(censored)} CENSORED (unobservable, not passing)" if censored else "",
            )
            if part
        ),
    }


def grade_p4(payload: dict[str, Any]) -> dict[str, Any]:
    """The movers' 24 h run counts rise toward schedule."""
    movers = payload.get("movers") or {}
    rows = []
    for task in sorted(HEAVY_MOVE_EXCEPTION):
        m = movers.get(task) or {}
        pre = MOVER_PRE_MOVE[task]
        rows.append(
            {
                "task": task,
                "observed": m.get("observed"),
                "runs_24h": m.get("runs_24h"),
                "pre_move_runs_24h": pre.runs_24h,
                "scheduled_fires_24h": pre.scheduled_fires_24h,
                "p4": m.get("p4"),
            }
        )

    states = {r["p4"] for r in rows}
    if any(r.get("observed") is not True for r in rows) or "unreadable" in states:
        verdict = "UNREADABLE"
    elif "flat_or_fell" in states:
        verdict = "FAILED"
    elif states == {"rose"}:
        verdict = "PASSED"
    else:
        verdict = "PRE_HORIZON"

    return {
        "prediction": "P4",
        "claim": "both moved tasks' 24h run counts RISE (31->72, 45->96) — starved, not idle",
        "verdict": verdict,
        "movers": rows,
        "note": (
            "🔴 observed=False or null counters is the disjoint-READ_SET defect "
            "(#2071), not a measurement — do NOT read it as zero"
            if verdict == "UNREADABLE"
            else ""
        ),
    }


def grade_p5(payload: dict[str, Any]) -> dict[str, Any]:
    """Past the horizon, the falsifier's own verdict is HOLD."""
    verdict_str = payload.get("verdict")
    horizon = payload.get("horizon") or {}
    beats = payload.get("beats") or []
    still_pre = [b for b in beats if b.get("verdict") == "pre_horizon"]

    if still_pre:
        outcome = "PRE_HORIZON"
    elif verdict_str == "HOLD":
        outcome = "PASSED"
    elif verdict_str == "REVERT":
        outcome = "REVERT"
    else:
        outcome = "FAILED"

    return {
        "prediction": "P5",
        "claim": (
            "past the horizon the falsifier reads HOLD "
            "(failable as REVERT and as INCONCLUSIVE)"
        ),
        "verdict": outcome,
        "falsifier_verdict": verdict_str,
        "age_since_move_h": horizon.get("age_since_move_h"),
        "counters_clear_the_move": horizon.get("counters_clear_the_move"),
        "beats_still_pre_horizon": [b.get("task") for b in still_pre],
        "min_post_move_samples_required": MIN_POST_MOVE_SAMPLES,
    }


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    grades = [grade_p3(payload), grade_p4(payload), grade_p5(payload)]
    revert = any(g["verdict"] == "REVERT" for g in grades)
    failed = [g["prediction"] for g in grades if g["verdict"] == "FAILED"]
    return {
        "ruling": 110,
        "falsifier_verdict": payload.get("verdict"),
        "falsifier_reason": payload.get("reason"),
        "horizon": payload.get("horizon"),
        "retired_predictions": RETIRED,
        "grades": grades,
        "revert_obliged": revert,
        "failed_predictions": failed,
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "RULING 110 — GRADE",
        f"  falsifier verdict : {report['falsifier_verdict']}",
        f"  horizon           : {(report.get('horizon') or {}).get('age_since_move_h')} h",
        "",
    ]
    for g in report["grades"]:
        lines.append(f"  {g['prediction']}  {g['verdict']:<12} {g['claim']}")
        if g.get("note"):
            lines.append(f"        note: {g['note']}")
    lines.append("")
    for name, why in report["retired_predictions"].items():
        lines.append(f"  {name}  RETIRED      {why}")
    lines.append("")
    if report["revert_obliged"]:
        lines.append("  🔴 REVERT OBLIGED — ruling 110's routing reverts in THIS window.")
    elif report["failed_predictions"]:
        lines.append(f"  ⚠️  FAILED: {', '.join(report['failed_predictions'])} (no revert owed)")
    else:
        lines.append("  no failure; see per-prediction verdicts for what is still pre-horizon.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="fetch from production")
    src.add_argument("--from-file", help="grade an already-captured payload")
    ap.add_argument("--out", help="write the JSON report here")
    args = ap.parse_args(argv)

    try:
        if args.live:
            payload = _fetch_live()
        else:
            with open(args.from_file) as fh:
                payload = json.load(fh)
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
        print(f"UNREADABLE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE

    if not isinstance(payload, dict) or "verdict" not in payload:
        print(f"UNREADABLE: payload is not a falsifier response: {payload!r:.200}", file=sys.stderr)
        return EXIT_UNREADABLE

    report = build_report(payload)
    print(render(report))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
        print(f"\nwrote {args.out}")

    if report["revert_obliged"]:
        return EXIT_REVERT
    if report["failed_predictions"]:
        return EXIT_PREDICTION_FAILED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
