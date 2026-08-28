#!/usr/bin/env python3
"""CAL-P112 — the per-cohort finish-line threshold table, scored on the served payload.

``calibration_scorecard.py`` (CAL-P108) declares ONE bar for every published
cell: ``BAR_PP = 3.0``. This script is the ratification instrument for the
question that bar leaves open — *should the bar be the same number in every
cohort?* — and it deliberately does NOT change the scorecard's live thresholds.
Until Alex ratifies, the scorecard keeps rendering the flat bar and this script
renders the proposal beside it, on the same payload, in the same run.

WHY A SEPARATE FILE AND NOT A FLAG ON THE SCORECARD
----------------------------------------------------
A finish line that moves when a lane edits a constant is not a finish line. The
scorecard's ``BAR_PP`` is the ratified number; a proposal that overwrites it
before ratification would make the published page report a bar nobody approved,
and the next reader could not tell which one they were looking at. So the
proposal lives here, is labelled PRE-RATIFICATION in its own output, and the
day it is ratified the change to ``calibration_scorecard.py`` is three lines.

THE DERIVATION RULE, AND THE ONE IT REJECTS
---------------------------------------------
The obvious way to set a per-cohort bar is from the cohort's own current
distribution — "the bar is the class's 25th percentile". That is circular: the
bar then moves every time a cell improves, so the program can never arrive. A
finish line has to be derived from something OUTSIDE today's measurement.

Two external quantities are available, and they justify exactly one departure
from the flat bar:

1. **Reader actionability.** 3.0 pp means a market published at 60% lands
   between 57% and 63%. That is a property of what a person does with the
   number, not of the venue that produced it, so it does not vary by cohort.
   It is the bar for every class.
2. **Estimator averaging.** ``odds_api*`` cells are a DEVIGGED CONSENSUS OF
   MANY BOOKMAKERS — the price is an average of independent estimates, so its
   idiosyncratic quoting error is smaller by construction than a single thin
   order book's. This is a structural property of how the price is formed, is
   fixed in advance, and does not move as cells improve. It is the only
   defensible reason to hold one class tighter, and it is why class A gets
   2.5 pp.

The measurement that KILLS the opposite move — a looser bar for thin,
long-horizon exchange markets — is in the output: every class already contains
a published cell far under 3.0 pp (``polymarket/weather`` 1.63 pp and
``kalshi/politics`` 2.08 pp are both class C). A class that has already proved
3.0 pp reachable has not earned a bar above it.

THE PRECONDITION THAT IS NOT A THRESHOLD
------------------------------------------
CAL-P112's cell diagnoses found that the two worst cells on the board are not
miscalibrated — they are MIS-POPULATED. ``kalshi/tech`` is 79% cumulative-
threshold ladder rows by n (a 40-rung "price of NVIDIA H200 compute" market
where every rung resolves YES); ``polymarket/esports`` is 29% one-winner
realizations of the same non-partition shape. Those rows are not forecasts of
one question and no bar, tight or loose, is the right response to them. So the
table carries a PRECONDITION rather than a fourth threshold: a cell whose
published population is dominated by non-partition bundle rows is queued for a
POPULATION fix, not scored as a calibration failure. See
``artifacts/cal-p112/RULE-DESIGN-*.md``.

Usage::

    python3 backend/scripts/calibration_threshold_table.py --live
    python3 backend/scripts/calibration_threshold_table.py --payload x.json --markdown
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from calibration_scorecard import (  # noqa: E402
    BAR_PP,
    HEADLINE_TARGET_PP,
    MIN_CELL_N,
    SIGMA_GATE,
    VERDICT_EXEMPT,
    cell_se_pp,
    score,
    self_check,
)

# --------------------------------------------------------------------------
# The cohort classes. Assignment is STRUCTURAL — how the price is formed — and
# is decided by (source, category) alone, so a cell can never drift between
# classes as its numbers move.
# --------------------------------------------------------------------------

#: Categories that are a scheduled contest with a fixed, near-term settlement.
#: Used only to split exchange cells into B and C; ``odds_api*`` is class A
#: whatever its category, because the class is about the PRICE, not the sport.
GAME_CATEGORIES: frozenset[str] = frozenset({
    "baseball", "basketball", "soccer", "hockey", "football", "tennis", "golf",
    "cricket", "esports", "mma", "motorsports", "table_tennis", "boxing",
    "cycling", "horse_racing", "lacrosse", "rugby", "chess",
})

CLASS_A = "A_multibook_consensus"
CLASS_B = "B_exchange_contest"
CLASS_C = "C_exchange_standalone"

#: PROPOSED per-cohort bars, pp. Pre-ratification — see the module docstring
#: for the derivation of each, and why only class A departs from 3.0.
PROPOSED_BARS: dict[str, float] = {
    CLASS_A: 2.5,
    CLASS_B: 3.0,
    CLASS_C: 3.0,
}

#: The incumbent, for the side-by-side. ``calibration_scorecard.BAR_PP``.
INCUMBENT_BARS: dict[str, float] = {k: BAR_PP for k in PROPOSED_BARS}

CLASS_RATIONALE: dict[str, str] = {
    CLASS_A: (
        "Devigged consensus of many bookmakers. The published price is an "
        "average of independent estimates, so its idiosyncratic quoting error "
        "is structurally smaller than a single order book's — the one external "
        "reason to hold a class tighter than reader-actionability requires. "
        "These cells also carry the game cards, the most-read surface."
    ),
    CLASS_B: (
        "Single-venue exchange price on a scheduled contest. Real order book, "
        "near-term settlement, no averaging across venues. Reader "
        "actionability sets the bar and nothing about the class earns a "
        "departure from it."
    ),
    CLASS_C: (
        "Single-venue exchange price on a standalone or long-horizon question. "
        "Thin books and distant settlement raise the VARIANCE of a cell's "
        "estimate, which the sigma gate already prices; they do not license a "
        "larger BIAS. The class's own cells prove 3.0 pp reachable — "
        "polymarket/weather 1.63 pp, kalshi/politics 2.08 pp."
    ),
}


def classify(source: str, category: str) -> str:
    if (source or "").startswith("odds_api"):
        return CLASS_A
    return CLASS_B if category in GAME_CATEGORIES else CLASS_C


def evaluate(result: dict, bars: dict[str, float], sigma_gate: float = SIGMA_GATE) -> dict:
    """Score every MATERIAL cell against its class's bar.

    ``at_bar`` counts the cells that are NOT queued, which is the scorecard's
    own DONE test (``done`` iff zero queued) applied per class. A cell over the
    bar on the point estimate but under the sigma gate is at bar here for the
    same reason it is not queued there: the sample cannot tell it from the bar,
    so working it burns a cycle and moves nothing.
    """
    material = [c for c in result["cells"] if c["verdict"] != VERDICT_EXEMPT]
    rows, queued = [], []
    for c in material:
        klass = classify(c["source"], c["category"])
        bar = bars[klass]
        excess = round(c["ece"] - bar, 2)
        sigma = round(excess / cell_se_pp(c["n"]), 2)
        is_queued = excess > 0 and sigma >= sigma_gate
        row = {
            "cell": c["cell"], "class": klass, "ece": c["ece"], "n": c["n"],
            "gap": c["gap"], "bar_pp": bar, "excess_pp": excess, "sigma": sigma,
            "excess_outcomes": round(max(0.0, excess) * c["n"]) if is_queued else 0,
            "queued": is_queued,
        }
        rows.append(row)
        if is_queued:
            queued.append(row)
    rows.sort(key=lambda r: (-r["excess_outcomes"], -r["n"]))
    per_class = {}
    for klass in bars:
        sub = [r for r in rows if r["class"] == klass]
        per_class[klass] = {
            "bar_pp": bars[klass],
            "cells": len(sub),
            "at_bar": sum(1 for r in sub if not r["queued"]),
            "queued": sum(1 for r in sub if r["queued"]),
            "outcomes": sum(r["n"] for r in sub),
        }
    return {
        "bars": dict(bars),
        "cells_material": len(rows),
        "cells_at_bar": len(rows) - len(queued),
        "cells_queued": len(queued),
        "queued_excess_outcomes": sum(r["excess_outcomes"] for r in queued),
        "per_class": per_class,
        "rows": rows,
    }


def needle(evaluation: dict, generated_at: str) -> str:
    """The lane's ONE number, per ``.claude/handoff/NEEDLE-SPEC.md``."""
    return (
        f"NEEDLE: calibration {evaluation['cells_at_bar']}/"
        f"{evaluation['cells_material']} cells-at-bar @ {generated_at}"
    )


def render_markdown(result: dict, incumbent: dict, proposed: dict) -> str:
    L: list[str] = []
    L.append("### Cells at bar — incumbent vs proposed (PRE-RATIFICATION)")
    L.append("")
    L.append(f"payload `{result['generated_at']}`, population "
             f"`{result['population_version']}`, headline "
             f"{result['headline_mce_closing_line']} pp")
    L.append("")
    L.append("| table | bar A / B / C | cells at bar | queued | queued excess-outcomes |")
    L.append("|---|---|--:|--:|--:|")
    for name, ev in (("incumbent (flat)", incumbent), ("**proposed**", proposed)):
        b = ev["bars"]
        L.append(
            f"| {name} | {b[CLASS_A]} / {b[CLASS_B]} / {b[CLASS_C]} | "
            f"**{ev['cells_at_bar']}/{ev['cells_material']}** | {ev['cells_queued']} | "
            f"{ev['queued_excess_outcomes']:,} |"
        )
    L.append("")
    L.append("| class | bar pp | cells | at bar | queued | outcomes | rationale |")
    L.append("|---|--:|--:|--:|--:|--:|---|")
    for klass in (CLASS_A, CLASS_B, CLASS_C):
        p = proposed["per_class"][klass]
        L.append(
            f"| `{klass}` | **{p['bar_pp']}** | {p['cells']} | {p['at_bar']} | "
            f"{p['queued']} | {p['outcomes']:,} | {CLASS_RATIONALE[klass]} |"
        )
    L.append("")
    L.append("| # | cell | class | ECE | n | gap | bar | excess | sigma | excess-outcomes |")
    L.append("|--:|---|---|--:|--:|--:|--:|--:|--:|--:|")
    for i, r in enumerate([x for x in proposed["rows"] if x["queued"]], 1):
        L.append(
            f"| {i} | `{r['cell']}` | {r['class'][0]} | {r['ece']:.2f} | {r['n']:,} | "
            f"{r['gap']:+.2f} | {r['bar_pp']} | {r['excess_pp']:+.2f} | "
            f"{r['sigma']:.1f} | {r['excess_outcomes']:,} |"
        )
    return "\n".join(L)


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=90) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true")
    src.add_argument("--payload")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.live:
        base = os.environ.get("BAINLUCK_API", "https://api.bainluck.com").rstrip("/")
        payload = fetch(f"{base}/api/calibration")
    else:
        payload = json.loads(Path(args.payload).read_text())

    # Same warrant as the scorecard: an instrument that cannot reproduce the
    # payload's own pre-aggregated cells does not get to report a finish line.
    check = self_check(payload)
    if not check["ok"]:
        print("SELF-CHECK FAILED — threshold table NOT valid.", file=sys.stderr)
        return 1

    result = score(payload)
    incumbent = evaluate(result, INCUMBENT_BARS)
    proposed = evaluate(result, PROPOSED_BARS)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {"generated_at": result["generated_at"],
             "population_version": result["population_version"],
             "headline_mce_closing_line": result["headline_mce_closing_line"],
             "min_cell_n": MIN_CELL_N, "sigma_gate": SIGMA_GATE,
             "headline_target_pp": HEADLINE_TARGET_PP,
             "incumbent": incumbent, "proposed": proposed,
             "status": "PRE-RATIFICATION"},
            indent=2, sort_keys=True))

    if args.markdown:
        print(render_markdown(result, incumbent, proposed))
    else:
        print(f"payload {result['generated_at']}  population {result['population_version']}")
        for name, ev in (("incumbent flat 3.0", incumbent), ("PROPOSED  2.5/3.0/3.0", proposed)):
            print(f"  {name:22s} cells at bar {ev['cells_at_bar']}/{ev['cells_material']}"
                  f"  queued {ev['cells_queued']}"
                  f"  excess-outcomes {ev['queued_excess_outcomes']:,}")
    print()
    print("PRE-RATIFICATION — Alex ratifies by MC; until then the scorecard's flat "
          f"{BAR_PP} pp bar is the live one.")
    print(needle(proposed, result["generated_at"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
