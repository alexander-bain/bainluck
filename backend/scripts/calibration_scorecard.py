#!/usr/bin/env python3
"""CAL-P108 — the PUBLISHED calibration curve, scored against the finish line.

Alex, 2026-08-27: *"We haven't made any tangible progress on calibration in
months, if anything it's regressed... I'd strongly prefer to get to a point
where calibration is just FIXED."*

This script is the one measurement that sentence gets. It scores **the numbers
users actually see** — nothing else.

WHY IT READS THE SERVED PAYLOAD AND NOT THE DATABASE
-----------------------------------------------------
Every previous calibration instrument in this repo measures a *parallel rail*:

* ``fold_cohort_cell_eligible.py`` (the 21-cell board in
  ``artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md``) folds
  ``source='polymarket'`` only, over ``market_type IN (quantity,
  container_member)``, applying exactly ONE of the curve's thirteen live
  exclusion filters (truth-eligibility). It is a real measurement of a real
  population — but not of the published one.
* ``calibration_published_twin.py`` DOES fold the published predicate, and is
  the right idea. Its last production run (2026-08-25) died on a statement
  timeout after 241 s against a 240 s budget, and it has never returned a
  measured verdict since.

Both are DB-direct, and a DB-direct rail can drift from the served payload
without anyone noticing. This script cannot: it reads the payload the site
serves and folds *that*. The population predicate is not re-derived, not
re-implemented, and not trusted — it is simply not needed, because the rows
have already been through it.

THE INSTRUMENT PROVES ITSELF BEFORE IT REPORTS
------------------------------------------------
``/api/calibration`` ships a ``buckets`` array AND its own pre-aggregated
``by_category`` / ``by_source`` cells. :func:`self_check` re-derives the second
from the first and refuses to report anything if they disagree.

That check is the whole warrant for this file. It is not decoration:

* It pins the fold. The published fold pools ``(source, category,
  price_moved, bucket_idx)`` rows into **10 bins per cell** before taking the
  error. Folding at bucket-row granularity instead — the obvious first
  implementation — inflates every cell, because errors that cancel inside a bin
  no longer can. Measured 2026-08-27 on the live payload: 34 of 34 cells wrong,
  every one high (soccer 2.80 -> 3.91, hockey 0.95 -> 2.32). A silent +40%
  scorecard is worse than no scorecard.
* It makes a schema change LOUD. If the payload's shape moves, this reds
  instead of quietly scoring a different quantity under the same name.

A cut this script reports that the payload does not pre-aggregate — the
``(source, category)`` cell — is therefore computed by a fold that has been
proved against two cuts the payload DOES pre-aggregate, on the same rows, in
the same run.

WHAT "DONE" MEANS — thresholds are declared here, in code, once
-----------------------------------------------------------------
See :data:`BAR_PP`, :data:`MIN_CELL_N`, :data:`SIGMA_GATE`. Each carries its
derivation. They are proposals for Alex to ratify; changing one is a one-line
change here and the scorecard re-renders.

Usage::

    python3 backend/scripts/calibration_scorecard.py --live
    python3 backend/scripts/calibration_scorecard.py --payload artifacts/x.json
    python3 backend/scripts/calibration_scorecard.py --live --markdown

``--record`` appends the run to ``artifacts/calibration-scorecard/history.jsonl``,
keyed on the payload's own ``generated_at``. Re-running against a STALE payload
(the producer has been stalling — see ``producer.stalled``) therefore cannot
mint a second datapoint for the same curve, which would otherwise draw a
flat trend line out of one measurement repeated.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------
# THE FINISH LINE. Three numbers, each derived rather than chosen.
# --------------------------------------------------------------------------

#: Per-cell published ECE bar, in percentage points.
#:
#: 3.0 pp is the bar the calibration program has already been ranking against
#: for four weeks (``SUBCOHORT_DIAGNOSIS.md`` ranks on ``n x (ece - 3)``), so
#: adopting it keeps every banked mechanism comparable to its own history
#: instead of restating the queue in a new unit on the day we start scoring it.
#:
#: It is also defensible on its own: a 3 pp error means a market we publish at
#: 60% comes in between 57% and 63%, which is inside the width a reader can
#: reasonably act on. Below that the number is not what is wrong with the page.
BAR_PP = 3.0

#: Cells smaller than this are MATERIAL-EXEMPT: measured, listed, never queued.
#:
#: 1,000 is the payload's OWN disclosure floor — ``min_category_outcomes: 1000``
#: is what ``/api/calibration`` already uses to decide a category is big enough
#: to publish as a cell. Reusing it means the scorecard's scope and the page's
#: scope are the same set, so no cell can be "fixed" on the scorecard while
#: still visibly wrong on the page, or vice versa.
#:
#: Measured cost of the floor (2026-08-27): 49 of 287 cells clear it, and they
#: carry 854,947 of 894,511 published outcomes — **95.6% coverage from 17% of
#: the cells.** The 238 excluded cells average 166 outcomes each.
MIN_CELL_N = 1000

#: A cell is only QUEUED if its excess over the bar is established at this many
#: standard errors.
#:
#: This exists because the program's own board found the defect it prevents:
#: *"15 of the 21 are under 3 sigma, and three are under 1 sigma"* — a 21-item
#: queue that was really a 6-item one. Chasing a point estimate that the sample
#: cannot distinguish from the bar burns a cycle per cell and moves nothing.
#:
#: 2.0 sigma is the conventional two-sided 95% threshold, and on this payload it
#: cuts the material over-bar list from 30 cells to 19 — so it is doing real
#: work, not decorating the table.
SIGMA_GATE = 2.0

#: Standard error of a cell's ECE in pp, as a function of n.
#:
#: ``50/sqrt(n)`` is the convention ``SUBCOHORT_DIAGNOSIS.md`` uses throughout,
#: kept so sigmas on this scorecard and sigmas on the board mean the same thing.
#: It is the maximum-variance (p=0.5) binomial SE expressed in pp, which makes
#: it CONSERVATIVE — a real cell's bins are rarely all at 0.5, so a cell this
#: gate clears is clear by at least the margin shown.
def cell_se_pp(n: int) -> float:
    return 50.0 / math.sqrt(n) if n > 0 else float("inf")


#: Overall published headline target, in pp, on ``mce_closing_line``.
#:
#: 2.0 pp is deliberately set where the curve ALREADY sits (1.90 pp on
#: 2026-08-27, CI [0.87, 1.97]) — because the honest finding is that the
#: headline is not the problem and never was. The pooled number is an average
#: over 287 cells whose errors point in opposite directions and cancel:
#: ``kalshi/football`` is -5.16 gap while ``polymarket/esports`` is +6.50, and
#: the pooled figure reads 1.90 as though both were fine.
#:
#: So this target is a REGRESSION GUARD, not a goal. "Fixed" is the per-cell
#: table below it. Publishing a single headline as the definition of done is
#: the exact move that let this program report progress for months without a
#: user-visible cell moving.
HEADLINE_TARGET_PP = 2.0

DEFAULT_HISTORY = Path("artifacts/calibration-scorecard/history.jsonl")

# --------------------------------------------------------------------------
# Fold
# --------------------------------------------------------------------------

#: The published cell key. ``price_moved`` is a REPORTING stratum, not a cell:
#: the payload splits buckets by it but publishes ``by_category`` / ``by_source``
#: pooled across it, so pooling here is what reproduces the published number.
CELL_KEYS = ("source", "category")


def _pool(buckets: Iterable[dict], keys: tuple[str, ...]) -> dict[tuple, dict[int, dict]]:
    """``key -> {bucket_idx: {n, winners, sum_prob}}``, pooled to 10 bins.

    Pooling to ``bucket_idx`` is the load-bearing line of this file; see the
    module docstring for the measurement of what happens without it.
    """
    out: dict[tuple, dict[int, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"n": 0, "winners": 0, "sum_prob": 0.0})
    )
    for row in buckets:
        key = tuple(row.get(k) for k in keys)
        b = out[key][int(row["bucket_idx"])]
        b["n"] += int(row.get("n") or 0)
        b["winners"] += int(row.get("winners") or 0)
        b["sum_prob"] += float(row.get("sum_prob") or 0.0)
    return out


def _stats(bins: dict[int, dict]) -> dict:
    """n-weighted 10-bin ECE and signed gap, in pp.

    Signed gap is carried beside ECE because ECE is an absolute value and
    therefore cannot say WHICH WAY a cell is wrong. Two cells at 5 pp — one
    over-predicting, one under — are different defects with different
    mechanisms, and a table that only prints ECE hides that they are not the
    same problem.
    """
    n = sum(b["n"] for b in bins.values())
    if not n:
        return {"ece": None, "n": 0, "gap": None}
    err = sum(
        abs(b["winners"] / b["n"] - b["sum_prob"] / b["n"]) * b["n"]
        for b in bins.values()
        if b["n"]
    )
    gap = sum(b["sum_prob"] - b["winners"] for b in bins.values())
    return {"ece": round(err / n * 100, 2), "n": n, "gap": round(gap / n * 100, 2)}


def fold(payload: dict, keys: tuple[str, ...] = CELL_KEYS) -> list[dict]:
    cells = []
    for key, bins in _pool(payload.get("buckets") or [], keys).items():
        row = dict(zip(keys, key))
        row.update(_stats(bins))
        cells.append(row)
    return cells


# --------------------------------------------------------------------------
# Self-check — the instrument's warrant
# --------------------------------------------------------------------------


def self_check(payload: dict) -> dict:
    """Re-derive the payload's own pre-aggregated cells from its buckets.

    Returns a report; ``ok`` false means this scorecard MUST NOT be published.
    ``n`` is compared as well as ``ece``: an ECE that matches on a different
    row count is a coincidence, not agreement.
    """
    checks = []
    for dim, field in (("category", "by_category"), ("source", "by_source")):
        published = payload.get(field) or []
        derived = {c[dim]: c for c in fold(payload, (dim,))}
        mismatches = []
        for pub in published:
            got = derived.get(pub[dim])
            if got is None:
                mismatches.append({"cell": pub[dim], "reason": "absent_from_buckets"})
                continue
            # `is None`, never a falsy test: a cell whose ECE is exactly 0.00 is
            # a PERFECTLY calibrated cell, and `got["ece"] or -1` would score it
            # as a mismatch — the self-check reddest on the one result it should
            # be happiest about. Found by `test_agrees_with_a_consistent_payload`.
            if got["ece"] is None:
                mismatches.append({"cell": pub[dim], "reason": "unfoldable"})
                continue
            # 0.015 absorbs the payload's own 2-dp rounding and nothing else.
            if abs(got["ece"] - pub["ece"]) > 0.015 or got["n"] != pub["n"]:
                mismatches.append(
                    {
                        "cell": pub[dim],
                        "published": {"ece": pub["ece"], "n": pub["n"]},
                        "derived": {"ece": got["ece"], "n": got["n"]},
                    }
                )
        checks.append(
            {
                "dimension": field,
                "cells": len(published),
                "matched": len(published) - len(mismatches),
                "mismatches": mismatches,
            }
        )
    # A run that compared ZERO cells has not agreed with anything — it has
    # declined to check. Reporting that as `ok` is gotcha #53 inside the very
    # guard written to prevent it, and it is exactly what an empty or
    # shape-changed payload would produce.
    compared = sum(c["cells"] for c in checks)
    return {
        "ok": bool(checks) and compared > 0 and all(not c["mismatches"] for c in checks),
        "cells_compared": compared,
        "checks": checks,
    }


# --------------------------------------------------------------------------
# Score
# --------------------------------------------------------------------------

#: Cell verdicts. Four states, and the two "not queued" ones are DISTINCT on
#: purpose: a cell can fail the bar because it is genuinely bad but too small to
#: matter (``EXEMPT_SMALL``), or because the sample cannot tell it from the bar
#: (``UNDER_SIGMA``). Collapsing those into one "not now" bucket is how a real
#: small-cell defect and a noise reading end up in the same pile.
VERDICT_PASS = "PASS"
VERDICT_QUEUED = "OVER_BAR_ESTABLISHED"
VERDICT_UNDER_SIGMA = "OVER_BAR_UNESTABLISHED"
VERDICT_EXEMPT = "EXEMPT_BELOW_MIN_N"


def score(payload: dict) -> dict:
    cells = []
    for c in fold(payload):
        n, ece = c["n"], c["ece"]
        if ece is None:
            continue
        excess = round(ece - BAR_PP, 2)
        se = cell_se_pp(n)
        sigma = round(excess / se, 2) if se else None
        if n < MIN_CELL_N:
            verdict = VERDICT_EXEMPT
        elif excess <= 0:
            verdict = VERDICT_PASS
        elif sigma is not None and sigma >= SIGMA_GATE:
            verdict = VERDICT_QUEUED
        else:
            verdict = VERDICT_UNDER_SIGMA
        cells.append(
            {
                "cell": f"{c['source']}/{c['category']}",
                "source": c["source"],
                "category": c["category"],
                "ece": ece,
                "n": n,
                "gap": c["gap"],
                "excess_pp": excess,
                "sigma": sigma,
                # Excess-outcomes: how much wrongness this cell puts in front of
                # readers. Ranks the queue, because a 22 pp cell over 118 rows
                # and a 0.5 pp cell over 100,000 are not the same repair job.
                "excess_outcomes": round(max(0.0, excess) * n),
                "verdict": verdict,
            }
        )
    cells.sort(key=lambda c: (-c["excess_outcomes"], -c["n"]))

    material = [c for c in cells if c["verdict"] != VERDICT_EXEMPT]
    queued = [c for c in cells if c["verdict"] == VERDICT_QUEUED]
    unestablished = [c for c in cells if c["verdict"] == VERDICT_UNDER_SIGMA]
    headline = payload.get("mce_closing_line")

    return {
        "generated_at": payload.get("generated_at"),
        "population_version": payload.get("population_version"),
        "total_outcomes": payload.get("total_outcomes"),
        "headline_mce_closing_line": headline,
        "headline_ci": [payload.get("mce_ci_lower"), payload.get("mce_ci_upper")],
        "headline_target_pp": HEADLINE_TARGET_PP,
        "headline_pass": (headline is not None and headline <= HEADLINE_TARGET_PP),
        # Producer state travels WITH the number. A scorecard that reports a
        # figure without saying the producer that made it has missed five beats
        # is reporting a stale reading as a current one (gotcha #53).
        "availability": payload.get("availability"),
        "producer_stalled": (payload.get("producer") or {}).get("stalled"),
        "producer_beats_missed": (payload.get("producer") or {}).get("beats_missed"),
        "thresholds": {
            "bar_pp": BAR_PP,
            "min_cell_n": MIN_CELL_N,
            "sigma_gate": SIGMA_GATE,
            "headline_target_pp": HEADLINE_TARGET_PP,
        },
        "counts": {
            "cells_total": len(cells),
            "cells_material": len(material),
            "cells_material_outcomes": sum(c["n"] for c in material),
            "cells_pass": sum(1 for c in material if c["verdict"] == VERDICT_PASS),
            "cells_queued": len(queued),
            "cells_unestablished": len(unestablished),
            "cells_exempt": len(cells) - len(material),
            "queued_excess_outcomes": sum(c["excess_outcomes"] for c in queued),
        },
        "done": len(queued) == 0
        and headline is not None
        and headline <= HEADLINE_TARGET_PP,
        "cells": cells,
    }


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


def record(result: dict, path: Path) -> str:
    """Append one datapoint, keyed on the payload's own ``generated_at``.

    Dedup is on the CURVE's identity, not the run's clock, because the producer
    stalls: on 2026-08-20 fourteen hourly samples all carried the same
    ``generated_at`` (17:17:43Z). Keying on wall-clock would have drawn a
    fourteen-point flat line out of one measurement — a trend chart that
    invents stability from a frozen producer.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    key = result.get("generated_at")
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and json.loads(line).get("generated_at") == key:
                return "duplicate_curve_generated_at"
    point = {
        k: result[k]
        for k in (
            "generated_at",
            "population_version",
            "total_outcomes",
            "headline_mce_closing_line",
            "availability",
            "producer_stalled",
            "counts",
            "done",
        )
    }
    # Per-cell ECE for material cells only — enough to trend every cell that
    # can ever be queued, without banking 287 rows of noise per beat.
    point["material_cells"] = {
        c["cell"]: {"ece": c["ece"], "n": c["n"], "verdict": c["verdict"]}
        for c in result["cells"]
        if c["verdict"] != VERDICT_EXEMPT
    }
    with path.open("a") as fh:
        fh.write(json.dumps(point, sort_keys=True) + "\n")
    return "recorded"


def load_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    pts = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return sorted(pts, key=lambda p: p.get("generated_at") or "")


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------


def render_markdown(result: dict, history: list[dict]) -> str:
    L: list[str] = []
    hl = result["headline_mce_closing_line"]
    arrow, trend = "—", "no prior datapoint"
    if len(history) >= 2:
        prev = history[-2]["headline_mce_closing_line"]
        if prev is not None and hl is not None:
            delta = round(hl - prev, 2)
            arrow = "🔴 ↑" if delta > 0.05 else ("🟢 ↓" if delta < -0.05 else "🟡 →")
            trend = (
                f"{prev} -> {hl} pp ({delta:+.2f}) since "
                f"{(history[-2].get('generated_at') or '?')[:10]}"
            )
    L.append(f"**Published curve: {hl} pp** (`mce_closing_line`)  {arrow}  {trend}")
    L.append("")
    L.append(
        f"- population `{result['population_version']}`, "
        f"{result['total_outcomes']:,} published outcomes, "
        f"curve generated `{result['generated_at']}`"
    )
    L.append(
        f"- availability **{result['availability']}**, producer stalled "
        f"**{result['producer_stalled']}** (beats missed "
        f"{result['producer_beats_missed']})"
    )
    c = result["counts"]
    L.append(
        f"- **{c['cells_queued']} cells over bar and established** "
        f"({c['queued_excess_outcomes']:,} excess-outcomes) | "
        f"{c['cells_pass']} pass | {c['cells_unestablished']} over-bar-unestablished | "
        f"{c['cells_exempt']} exempt (n < {MIN_CELL_N})"
    )
    L.append(f"- **DONE: {'YES' if result['done'] else 'NO'}**")
    L.append("")
    L.append("| # | cell | ECE pp | n | gap pp | excess pp | sigma | excess-outcomes |")
    L.append("|--:|---|--:|--:|--:|--:|--:|--:|")
    for i, cell in enumerate(
        [x for x in result["cells"] if x["verdict"] == VERDICT_QUEUED], 1
    ):
        L.append(
            f"| {i} | `{cell['cell']}` | {cell['ece']:.2f} | {cell['n']:,} | "
            f"{cell['gap']:+.2f} | {cell['excess_pp']:+.2f} | {cell['sigma']:.1f} | "
            f"{cell['excess_outcomes']:,} |"
        )
    return "\n".join(L)


# --------------------------------------------------------------------------


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=90) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="fetch $BAINLUCK_API/api/calibration")
    src.add_argument("--payload", help="score a saved payload JSON instead")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--history", default=str(DEFAULT_HISTORY))
    ap.add_argument("--out", help="write the full JSON result here")
    args = ap.parse_args()

    if args.live:
        base = os.environ.get("BAINLUCK_API", "https://api.bainluck.com").rstrip("/")
        payload = fetch(f"{base}/api/calibration")
    else:
        payload = json.loads(Path(args.payload).read_text())

    check = self_check(payload)
    if not check["ok"]:
        print("SELF-CHECK FAILED — scorecard NOT valid, nothing reported.", file=sys.stderr)
        print(json.dumps(check, indent=2)[:4000], file=sys.stderr)
        return 1

    result = score(payload)
    result["self_check"] = {
        "ok": True,
        "detail": [
            f"{c['dimension']}: {c['matched']}/{c['cells']} cells reproduced exactly"
            for c in check["checks"]
        ],
    }

    hist_path = Path(args.history)
    if args.record:
        result["record_status"] = record(result, hist_path)
    history = load_history(hist_path)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True))

    if args.markdown:
        print(render_markdown(result, history))
    else:
        print(json.dumps({k: v for k, v in result.items() if k != "cells"}, indent=2))
        print(f"\nself-check: {result['self_check']['detail']}")
        print(f"\nQUEUED CELLS ({result['counts']['cells_queued']}):")
        for i, cell in enumerate(
            [c for c in result["cells"] if c["verdict"] == VERDICT_QUEUED], 1
        ):
            print(
                f"{i:3d}. {cell['cell']:42s} ece={cell['ece']:6.2f} n={cell['n']:>8,} "
                f"gap={cell['gap']:+7.2f} sigma={cell['sigma']:6.1f} "
                f"excess-outcomes={cell['excess_outcomes']:>8,}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
