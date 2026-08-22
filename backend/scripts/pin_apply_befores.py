#!/usr/bin/env python3
"""CAL-P087 — freeze the apply's two BEFORE numbers, with timestamps.

Why
---
``QUEUE-STAGED-CAL-APPLY-HINDSIGHT-EXCLUSION.md`` §5b requires the apply's
closing report to quote BOTH population pairs — the full population where the
exclusion acts, and the rendered cohort a reader actually sees. Fable's CAL-P087
directive adds the part §5b did not pin down: *the closing report's befores must
be frozen numbers, not remembered ones.*

A remembered before is the failure mode this program keeps meeting. The apply
degrades the curve for ~17 hours; when it finishes, the rendered baseline will
have moved on its own, and a report that re-derives its own before AFTER the
change has no before at all. So both numbers are measured (or re-anchored) HERE,
stamped, and written to one artifact.

The two numbers are not the same KIND of number, and the artifact says so
--------------------------------------------------------------------------
* **Full population, 3.7226 -> ~1.7422 pp.** RE-ANCHORED, not re-measured: it
  comes from CAL-P085's whole-market fold, which took 411 s of a run that cannot
  be repeated during the freeze. This script pins its VALUES out of the banked
  artifact and stamps that artifact's own provenance, so the closing report
  quotes a file rather than a memory.
* **Rendered cohort, ~1.35 pp.** RE-MEASURED live, right now, from
  ``GET /api/calibration`` through the exact code path the page renders:
  ``aggregateBuckets(buckets, price_moved !== false)`` then ``ece``, ported
  field-for-field from ``frontend/lib/calibrationParity.ts`` +
  ``frontend/lib/calibrationMath.ts`` — including ``aggregateBuckets``'s rounding
  of ``error`` to one decimal place in pp, which is load-bearing: ECE is a
  weighted mean of those ROUNDED errors, and computing it from unrounded ones
  gives a different number than the page shows.

The port is validated by reproduction, not by inspection: the run prints
``cohortN`` alongside the ECE, and CAL-P086B's re-measure recorded
``cohortN = 525,601`` at 1.3509 pp against ``C-CALPAGE-SKEPTIC-1``'s 1.37 pp.
A cohortN in that neighbourhood with an ECE in that neighbourhood is the port
agreeing with two independent prior measurements of the same quantity.

    source ~/.claude/.env
    python3 scripts/pin_apply_befores.py --out artifacts/cal-p087/ARTIFACT-CAL-P087-APPLY-BEFORES-PINNED.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CAL_P085_ARTIFACT = os.path.join(REPO, "artifacts", "cal-p085", "price-provenance-whole-market.json")


# --------------------------------------------------------------------------
# The rendered-cohort metric, ported from the two frontend modules named above.
# --------------------------------------------------------------------------

def aggregate_buckets(buckets: list[dict], keep) -> list[dict]:
    """``frontend/lib/calibrationParity.ts:74``, field for field."""
    agg: dict[int, dict] = {}
    for b in buckets:
        if keep and not keep(b):
            continue
        idx = b.get("bucket_idx")
        if idx is None:
            continue
        idx = int(idx)
        a = agg.setdefault(idx, {"n": 0, "winners": 0, "sum_prob": 0.0, "sum_sq_err": 0.0})
        a["n"] += b.get("n") or 0
        a["winners"] += b.get("winners") or 0
        a["sum_prob"] += b.get("sum_prob") or 0.0
        a["sum_sq_err"] += b.get("sum_sq_err") or 0.0
    out = []
    for idx, a in agg.items():
        if not a["n"]:
            continue
        avg_prob = a["sum_prob"] / a["n"]
        actual = a["winners"] / a["n"]
        out.append({
            "midpoint": idx * 10 + 5,
            "n": a["n"],
            "winners": a["winners"],
            # Math.round(x*1000)/10 — JS half-up on positives; Python's round()
            # is banker's, so this is spelled out rather than delegated.
            "avgProb": _js_round1(avg_prob * 1000) / 10,
            "actual": _js_round1(actual * 1000) / 10,
            "error": _js_round1((actual - avg_prob) * 1000) / 10,
        })
    out.sort(key=lambda r: r["midpoint"])
    return out


def _js_round1(x: float) -> float:
    """``Math.round`` — half away from zero on the positive side, half UP overall."""
    import math

    return math.floor(x + 0.5)


def ece(cal: list[dict]) -> float:
    """``frontend/lib/calibrationMath.ts:19`` — n-weighted mean |error| in pp."""
    total = sum(b["n"] for b in cal)
    if not total:
        return 0.0
    return sum((b["n"] / total) * abs(b["error"]) for b in cal)


def mce(cal: list[dict]) -> float:
    """``frontend/lib/calibrationMath.ts:13`` — unweighted mean |error| in pp."""
    if not cal:
        return 0.0
    return sum(abs(b["error"]) for b in cal) / len(cal)


COHORT_FILTER = lambda b: b.get("price_moved") is not False  # noqa: E731


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    api = os.environ.get("BAINLUCK_API")
    if not api:
        raise SystemExit("ABORT: source ~/.claude/.env first (BAINLUCK_API).")

    read_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with urllib.request.urlopen(api.rstrip("/") + "/api/calibration", timeout=180) as resp:
        payload = json.loads(resp.read().decode())

    buckets = payload.get("buckets") or []
    cohort = aggregate_buckets(buckets, COHORT_FILTER)
    full = aggregate_buckets(buckets, None)
    cohort_n = sum((b.get("n") or 0) for b in buckets if COHORT_FILTER(b))
    full_n = sum((b.get("n") or 0) for b in buckets)

    with open(CAL_P085_ARTIFACT) as fh:
        p085 = json.load(fh)
    wm = p085["pooled_whole_market"]["all_legs"]

    git_ts = subprocess.run(
        ["git", "-C", REPO, "log", "-1", "--format=%cI", "--", CAL_P085_ARTIFACT],
        capture_output=True, text=True,
    ).stdout.strip()
    git_sha = subprocess.run(
        ["git", "-C", REPO, "log", "-1", "--format=%H", "--", CAL_P085_ARTIFACT],
        capture_output=True, text=True,
    ).stdout.strip()

    out = {
        "schema": "calibration-apply-befores/v1",
        "queue": "CAL-P087",
        "issue": 1145,
        "pins_for": "QUEUE-STAGED-CAL-APPLY-HINDSIGHT-EXCLUSION.md section 5b",
        "pinned_at_utc": read_at,
        "purpose": (
            "The apply's closing report must quote these two pairs as FROZEN befores. "
            "Both are true; neither on its own is an honest report of what happened."
        ),

        "full_population": {
            "kind": "re-anchored from a banked artifact, NOT re-measured",
            "before_ece_pp": wm["A_today"]["ece"],
            "after_projected_ece_pp": wm["C_exclude_hindsight"]["ece"],
            "n_rows": wm["A_today"]["n"],
            "rows_dropped": 34366,
            "rows_dropped_pct": 9.231,
            "cells_measured": p085.get("whole_market_cells_measured"),
            "cells_unmeasured": p085.get("whole_market_cells_unmeasured"),
            "policy": p085.get("proposed_policy"),
            "source_artifact": "artifacts/cal-p085/price-provenance-whole-market.json",
            "source_artifact_schema": p085.get("schema"),
            "source_artifact_elapsed_s": p085.get("elapsed_s"),
            "source_artifact_committed_at_utc": git_ts,
            "source_artifact_commit": git_sha,
            "why_not_re_measured": (
                "The whole-market fold ran 411.15 s and folds the population #2076 has "
                "never got through inside 1,350 s on the twin rail. Re-running it during "
                "the freeze is not available, so the pin is the banked artifact's value "
                "with the artifact's own provenance attached."
            ),
        },

        "rendered_cohort": {
            "kind": "RE-MEASURED live at pinned_at_utc",
            "metric": "ece over aggregateBuckets(buckets, price_moved !== false), pp",
            "before_ece_pp": round(ece(cohort), 4),
            "before_mce_pp": round(mce(cohort), 4),
            "cohort_n": cohort_n,
            "full_n": full_n,
            "bins": len(cohort),
            "after_expectation": "little movement — see why_they_differ",
            "payload_generated_at": payload.get("generated_at"),
            "payload_population_version": payload.get("population_version"),
            "payload_total_outcomes": payload.get("total_outcomes"),
            "payload_total_markets": payload.get("total_markets"),
            "payload_staged": payload.get("staged"),
            "full_population_ece_pp_same_read": round(ece(full), 4),
            "prior_measurements_of_the_same_quantity": {
                "CAL-P086B_2026-08-21": {"ece_pp": 1.3509, "cohort_n": 525601},
                "C-CALPAGE-SKEPTIC-1": {"ece_pp": 1.37, "cohort_n": 525601},
            },
            "not_this_number": {
                "mce_opening_price": payload.get("mce_opening_price"),
                "mce_closing_line": payload.get("mce_closing_line"),
                "note": (
                    "The payload's own mce_* fields are a THIRD, different metric. "
                    "Section 5b forbids substituting one for another."
                ),
            },
        },

        "why_they_differ": (
            "The page's cohort filter (price_moved !== false) already excludes most of "
            "the hindsight legs the apply removes — those legs are price_moved = true "
            "with an after_resolution capture, so the exclusion lands almost entirely "
            "outside the denominator the chart renders."
        ),
        "guardrail_cells_to_recheck_post_apply": ["hockey", "basketball"],
        "guardrail_note": (
            "C-CALPAGE-SKEPTIC-1 predicted both would breach the 5 pp guardrail on the "
            "live page and neither did (1.94 / 1.44). If they remain clean post-apply, "
            "the report must say so explicitly: it means the exclusion landed where the "
            "curve does not show it."
        ),
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
        fh.write("\n")
    print(json.dumps(out, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
