#!/usr/bin/env python3
"""Attribute each cohort cell's TRUTH-ELIGIBLE ECE to the pair-shape class of its market.

``fold_ou_pair_census.py`` counts corrupted markets. A count is not an impact:
18,875 identical-opening pairs could carry the whole of a cell's error or none of
it, and the disposition the CAL-P094 directive asks for — read-side exclusion vs a
``1 - p`` repair — turns entirely on which. This fold measures the ECE the class
actually contributes, per cell, so the proposal arrives with its census attached
rather than with a row count standing in for one.

The classification is computed with WINDOW functions over the FULL market before
the eligibility and validity filters are applied. Doing it the other way round —
filter first, classify the survivors — silently reclassifies every pair whose
partner leg was filtered out as a one-leg market, which is the exact shape of the
defect being counted, so the defect would erase its own evidence.

Bins, the ECE definition, the population predicate and ``MIN_CELL_N`` are taken
from :mod:`app.utils.cohort_cell_census` via ``fold_cohort_cell_eligible`` so the
numbers here are comparable to the file's, not merely similar to them.

Usage:
    python3 backend/scripts/fold_pairclass_ece.py --out artifacts/cal-p094 \\
        --label pairclass_ece
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE  # noqa: E402
from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
)

from dbq_probe import run as dbq_run  # noqa: E402
from fold_cohort_cell_eligible import (  # noqa: E402
    BISECT_FLOOR_IDS,
    POPULATION_MARKET_TYPES,
    POPULATION_SOURCE,
    POPULATION_STATUS,
    SCOPE_LEAGUES,
    ece_from_bins,
    gap_from_bins,
)

#: The writer's own gate constant, imported. The two artifacts are read side by
#: side, and a tolerance that drifted between them would make the market count and
#: the ECE attribution describe different populations.
TOL = PAIR_SUM_TOLERANCE

#: Four classes, not five. ``11 leagues x 2 types x 5 classes x 10 bins`` is 1,100
#: rows, over the endpoint's silent 1,000-row cap; folding ``not_pair`` in with
#: the healthy pairs as ``ok`` keeps the worst case at 880. Truncated shards are
#: recorded and never folded, so the cap cannot quietly eat the tail bins.
CLASSES = ("identical_noncomp", "other_noncomp", "partial_open", "ok")


def bin_sql() -> str:
    types = ", ".join(f"'{t}'" for t in POPULATION_MARKET_TYPES)
    leagues = ", ".join(f"'{lg}'" for lg in SCOPE_LEAGUES)
    return f"""
WITH allrows AS (
  SELECT fm.llm_sport_category AS league,
         fm.market_type AS mt,
         fo.is_winner AS is_winner,
         fo.resolution_source AS rsrc,
         fo.opening_probability AS op,
         COALESCE(fo.calibration_probability, fo.opening_probability) AS p,
         COUNT(*) OVER w AS n_legs,
         COUNT(fo.opening_probability) OVER w AS n_open,
         MIN(fo.opening_probability) OVER w AS min_open,
         MAX(fo.opening_probability) OVER w AS max_open,
         SUM(fo.opening_probability) OVER w AS sum_open
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
    AND fm.source = '{POPULATION_SOURCE}'
    AND fm.status = '{POPULATION_STATUS}'
    AND fm.market_type IN ({types})
    AND fm.llm_sport_category IN ({leagues})
  WINDOW w AS (PARTITION BY fo.market_id)
)
SELECT league, mt,
       CASE
         WHEN n_legs <> 2 THEN 'ok'
         WHEN n_open < 2 THEN 'partial_open'
         WHEN ABS(sum_open - 1) <= {TOL} THEN 'ok'
         WHEN min_open = max_open THEN 'identical_noncomp'
         ELSE 'other_noncomp'
       END AS open_class,
       LEAST(FLOOR(p * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(p) AS sum_prob,
       SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners
FROM allrows
WHERE rsrc IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
  AND p > 0 AND p < 1
  AND op IS NOT NULL
  AND is_winner IS NOT NULL
GROUP BY 1, 2, 3, 4
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="pairclass_ece")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=2_000_000)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    template = bin_sql()
    acc: dict[tuple, dict] = {}
    shards: list[dict] = []
    irreducible: list[dict] = []

    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.chunk, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()

    started = time.monotonic()
    while stack:
        lo, hi = stack.pop()
        result = dbq_run(template.format(lo=lo, hi=hi), timeout_ms=10_000)
        if result.get("status") == "ok":
            if result.get("truncated"):
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded")
                continue
            rows = result.get("rows") or []
            for league, mt, cls, b, n, sum_prob, winners in rows:
                key = (league, mt, cls, int(b))
                slot = acc.setdefault(key, {"n": 0, "sum_prob": 0.0, "winners": 0})
                slot["n"] += int(n)
                slot["sum_prob"] += float(sum_prob or 0)
                slot["winners"] += int(winners or 0)
            shards.append({"lo": lo, "hi": hi, "rows": len(rows),
                           "duration_ms": result.get("duration_ms"),
                           "sql_fingerprint": result.get("sql_fingerprint")})
            print(f"  [{lo}..{hi}) ok rows={len(rows)} {result.get('duration_ms')}ms")
            continue
        width = hi - lo
        if width <= BISECT_FLOOR_IDS:
            irreducible.append({"lo": lo, "hi": hi, "reason": result.get("reason")})
            print(f"  [{lo}..{hi}) IRREDUCIBLE — {result.get('reason')}")
            continue
        mid = lo + width // 2
        stack.append((mid, hi))
        stack.append((lo, mid))
        print(f"  [{lo}..{hi}) {result.get('status')} — bisecting at {mid}")

    cells: dict[tuple, dict] = {}
    for (league, mt, cls, b), v in acc.items():
        cell = cells.setdefault((league, mt), {c: [] for c in CLASSES})
        cell.setdefault(cls, []).append({"bin": b, **v})

    out_cells = []
    for (league, mt), by_class in cells.items():
        all_bins: dict[int, dict] = {}
        keep_bins: dict[int, dict] = {}
        for cls, bins in by_class.items():
            for b in bins:
                for target in (all_bins,) + ((keep_bins,) if cls != "identical_noncomp" else ()):
                    slot = target.setdefault(b["bin"], {"n": 0, "sum_prob": 0.0, "winners": 0})
                    slot["n"] += b["n"]
                    slot["sum_prob"] += b["sum_prob"]
                    slot["winners"] += b["winners"]
        ece_all, n_all = ece_from_bins(list(all_bins.values()))
        ece_keep, n_keep = ece_from_bins(list(keep_bins.values()))
        per_class = {}
        for cls in CLASSES:
            bins = by_class.get(cls) or []
            e, n = ece_from_bins(bins)
            per_class[cls] = {
                "ece": e, "n": n, "gap": gap_from_bins(bins),
                "winners": sum(x["winners"] for x in bins),
            }
        out_cells.append({
            "league": league, "market_type": mt,
            "ece_eligible": ece_all, "n_eligible": n_all,
            "ece_ex_identical": ece_keep, "n_ex_identical": n_keep,
            "delta_pp": None if (ece_all is None or ece_keep is None) else round(ece_keep - ece_all, 2),
            "n_identical": per_class["identical_noncomp"]["n"],
            "by_class": per_class,
        })
    out_cells.sort(key=lambda c: -(c["n_identical"] or 0))

    complete = not irreducible
    out = {
        "label": args.label, "complete": complete, "measured": complete,
        "tolerance": TOL, "classes": list(CLASSES),
        "scope": {"source": POPULATION_SOURCE, "status": POPULATION_STATUS,
                  "market_types": list(POPULATION_MARKET_TYPES),
                  "leagues": list(SCOPE_LEAGUES), "truth": "eligible only"},
        "shard_count": len(shards), "shards": shards, "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "cells": out_cells,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.label}.json"
    path.write_text(json.dumps(out, indent=2))

    print(f"\nwrote {path} shards={len(shards)} irreducible={len(irreducible)} "
          f"complete={complete} elapsed={out['elapsed_s']}s\n")
    print(f"{'cell':<34} {'ece_e':>7} {'n_e':>7} {'ex_id':>7} {'delta':>7} "
          f"{'n_id':>6} {'ece_id':>7} {'gap_id':>7}")
    for c in out_cells:
        idc = c["by_class"]["identical_noncomp"]
        print(f"{c['league']+'/'+c['market_type']:<34} {str(c['ece_eligible']):>7} "
              f"{c['n_eligible']:>7} {str(c['ece_ex_identical']):>7} "
              f"{str(c['delta_pp']):>7} {c['n_identical']:>6} "
              f"{str(idc['ece']):>7} {str(idc['gap']):>7}")
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
