#!/usr/bin/env python3
"""CAL-P112 — the per-cohort finish-line threshold table, scored on the served payload.

**RATIFIED by Alex, MC, 2026-08-28 ~1:15pm PT: A 2.5 pp / B 3.0 pp / C 3.0 pp,
as proposed.** CAL-P115 wired it: the classes, the bars and :func:`classify` now
live in ``calibration_scorecard.py`` and this file IMPORTS them, so the live
scorecard and this table are scoring the same cells against the same numbers by
construction and cannot be made to disagree by editing one of them.

WHAT THIS FILE IS FOR, NOW THAT THE QUESTION IS ANSWERED
----------------------------------------------------------
Two jobs, both of which outlive the ratification:

1. **The per-class breakdown and its rationale**, rendered against the live
   payload — the cohort view the scorecard's flat cell list cannot show.
2. **The incumbent side-by-side.** It keeps rendering the pre-ratification flat
   3.0 pp bar beside the ratified one, so the measured COST of the decision (one
   cell, ``odds_api_bookmaker/icehockey_nhl``) stays reproducible on today's
   curve instead of decaying into a claim about a constant nobody can run
   anymore. A ratification whose effect can no longer be measured is a prose
   threshold, which is the failure this whole program keeps paying for.

It also cross-checks itself against the scorecard on every run: scoring the
ratified bars here must return exactly what ``score()`` returned there, and the
run FAILS if it does not. See :func:`agreement`.

WHY THE FILES ARE STILL SEPARATE
----------------------------------
A finish line that moves when a lane edits a constant is not a finish line. The
bars live in the scorecard — the instrument that publishes the page — precisely
so that no side-by-side renderer can quietly become the source of truth for
them. This file may propose; it may not declare.

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
    CLASS_A,
    CLASS_B,
    CLASS_BARS_PP,
    CLASS_C,
    CLASS_RATIONALE,
    GAME_CATEGORIES,  # noqa: F401  — re-exported so the guard suite can pin it
    HEADLINE_TARGET_PP,
    MIN_CELL_N,
    SIGMA_GATE,
    VERDICT_EXEMPT,
    VERDICT_QUEUED,
    cell_se_pp,
    classify,
    needle,  # noqa: F401  — re-exported; the NEEDLE contract is pinned here
    score,
    self_check,
)

# --------------------------------------------------------------------------
# The bars are IMPORTED, never re-declared. Before CAL-P115 this module owned
# the class map and the scorecard owned a flat bar, which is how the two
# instruments spent a day disagreeing by design. Now there is one declaration
# and it lives with the instrument that publishes the page.
# --------------------------------------------------------------------------

#: The RATIFIED bars (Alex, MC, 2026-08-28). A local alias for readability —
#: the same object the scorecard scores with, so the two cannot drift.
RATIFIED_BARS: dict[str, float] = CLASS_BARS_PP

#: The pre-ratification incumbent, kept for the side-by-side: one flat
#: ``calibration_scorecard.BAR_PP`` for every class. This is history now, and it
#: is still rendered so the measured COST of the ratification — one cell — stays
#: checkable on today's curve rather than decaying into a prose claim.
INCUMBENT_BARS: dict[str, float] = {k: BAR_PP for k in CLASS_BARS_PP}


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


def agreement(result: dict, ratified: dict) -> dict:
    """Does this table, at the ratified bars, say what the scorecard said?

    It must, because the scorecard now applies the SAME bars through the SAME
    ``classify``. That makes this a tautology on a good day and a tripwire on a
    bad one: the day someone re-declares a bar in one file, or ``evaluate``'s
    queue predicate drifts from ``score``'s verdict ladder, this is the line
    that reds. It is checked on every run rather than only in the guard suite,
    because the number this file prints ends up in YOUR-TURN.
    """
    c = result["counts"]
    mismatches = [
        {"field": field, "scorecard": got, "table": want}
        for field, got, want in (
            ("cells_material", c["cells_material"], ratified["cells_material"]),
            ("cells_at_bar", c["cells_at_bar"], ratified["cells_at_bar"]),
            ("cells_queued", c["cells_queued"], ratified["cells_queued"]),
            (
                "queued_excess_outcomes",
                c["queued_excess_outcomes"],
                ratified["queued_excess_outcomes"],
            ),
        )
        if got != want
    ]
    queued_here = {r["cell"] for r in ratified["rows"] if r["queued"]}
    queued_there = {
        cell["cell"] for cell in result["cells"] if cell["verdict"] == VERDICT_QUEUED
    }
    if queued_here != queued_there:
        mismatches.append({
            "field": "queued_cells",
            "only_scorecard": sorted(queued_there - queued_here),
            "only_table": sorted(queued_here - queued_there),
        })
    return {"ok": not mismatches, "mismatches": mismatches}


def render_markdown(result: dict, incumbent: dict, ratified: dict) -> str:
    L: list[str] = []
    L.append("### Cells at bar — RATIFIED per-cohort bars, and the incumbent they replaced")
    L.append("")
    L.append(f"payload `{result['generated_at']}`, population "
             f"`{result['population_version']}`, headline "
             f"{result['headline_mce_closing_line']} pp")
    L.append("")
    L.append("| table | bar A / B / C | cells at bar | queued | queued excess-outcomes |")
    L.append("|---|---|--:|--:|--:|")
    for name, ev in (
        ("incumbent (flat, pre-2026-08-28)", incumbent),
        ("**RATIFIED — live**", ratified),
    ):
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
        p = ratified["per_class"][klass]
        L.append(
            f"| `{klass}` | **{p['bar_pp']}** | {p['cells']} | {p['at_bar']} | "
            f"{p['queued']} | {p['outcomes']:,} | {CLASS_RATIONALE[klass]} |"
        )
    L.append("")
    L.append("| # | cell | class | ECE | n | gap | bar | excess | sigma | excess-outcomes |")
    L.append("|--:|---|---|--:|--:|--:|--:|--:|--:|--:|")
    for i, r in enumerate([x for x in ratified["rows"] if x["queued"]], 1):
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
    ratified = evaluate(result, RATIFIED_BARS)

    agree = agreement(result, ratified)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {"generated_at": result["generated_at"],
             "population_version": result["population_version"],
             "headline_mce_closing_line": result["headline_mce_closing_line"],
             "min_cell_n": MIN_CELL_N, "sigma_gate": SIGMA_GATE,
             "headline_target_pp": HEADLINE_TARGET_PP,
             "incumbent": incumbent, "ratified": ratified,
             "scorecard_agreement": agree,
             "status": "RATIFIED 2026-08-28 (Alex, MC)"},
            indent=2, sort_keys=True))

    if args.markdown:
        print(render_markdown(result, incumbent, ratified))
    else:
        print(f"payload {result['generated_at']}  population {result['population_version']}")
        for name, ev in (
            ("incumbent flat 3.0", incumbent),
            ("RATIFIED  2.5/3.0/3.0", ratified),
        ):
            print(f"  {name:22s} cells at bar {ev['cells_at_bar']}/{ev['cells_material']}"
                  f"  queued {ev['cells_queued']}"
                  f"  excess-outcomes {ev['queued_excess_outcomes']:,}")
    print()
    if not agree["ok"]:
        print("SCORECARD DISAGREEMENT — the two instruments do not match at the "
              "ratified bars. NOTHING HERE IS PUBLISHABLE.", file=sys.stderr)
        print(json.dumps(agree["mismatches"], indent=2)[:4000], file=sys.stderr)
        return 1
    print(f"RATIFIED (Alex, MC, 2026-08-28): A {RATIFIED_BARS[CLASS_A]} / "
          f"B {RATIFIED_BARS[CLASS_B]} / C {RATIFIED_BARS[CLASS_C]} pp — LIVE in "
          "calibration_scorecard.py, and reproduced by this table cell-for-cell.")
    print(needle(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
