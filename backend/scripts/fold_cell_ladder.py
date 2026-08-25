#!/usr/bin/env python3
"""Walk one cohort cell's truth-eligible ECE down a named-mechanism ladder.

A cell ECE is a single number with many possible causes, and the diagnosis file's
standing method is to keep splitting it until one split names a mechanism rather
than a correlate. This runs the splits the file's check ladder calls for, over one
cell, in id-range shards under the 10 s row budget:

  check 1  fallback     ``calibration_probability`` present vs the
                        ``opening_probability`` fallback standing in for it
  check 2  arity        legs per market — a two-sided pair prices to ~1 by
                        construction, an n-leg field does not
  check 3  shape        the pair-opening class (see ``fold_ou_pair_census.py``)
  check 4  capture age  opening stamped BEFORE or AFTER the event began; an
                        "opening" captured post-start is a live price wearing an
                        opening's name, and it carries hindsight into the curve
  check 5  truth        which eligible ``resolution_source`` graded the leg
  check 6  noise floor  per-bin n, so a bin carried by 31 rows is not read as a
                        finding (``MIN_CELL_N`` guards the cell, not the bin)

Each dimension is folded and reported separately rather than crossed, because the
crossed table exceeds the endpoint's silent 1,000-row cap and a truncated tail bin
would cost exactly the mass an ECE is most sensitive to.

Usage:
    python3 backend/scripts/fold_cell_ladder.py --league baseball \\
        --market-type quantity --out artifacts/cal-p094 --label ladder_baseball
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
)

from dbq_probe import run as dbq_run  # noqa: E402
from fold_cohort_cell_eligible import (  # noqa: E402
    BISECT_FLOOR_IDS,
    POPULATION_SOURCE,
    POPULATION_STATUS,
    ece_from_bins,
    gap_from_bins,
)
from fold_pairclass_ece import TOL  # noqa: E402

#: One SQL expression per ladder rung. Each must yield a short text label; the
#: fold groups by it and by bin, so every rung costs ``labels x 10`` rows.
DIMENSIONS = {
    "fallback": """CASE WHEN fo.calibration_probability IS NOT NULL
                        THEN 'calib' ELSE 'opening_fallback' END""",
    "arity": """CASE WHEN n_legs = 1 THEN '1_leg'
                     WHEN n_legs = 2 THEN '2_legs'
                     WHEN n_legs <= 5 THEN '3_5_legs'
                     ELSE '6plus_legs' END""",
    "shape": f"""CASE
                   WHEN n_legs <> 2 THEN 'not_pair'
                   WHEN n_open < 2 THEN 'partial_open'
                   WHEN ABS(sum_open - 1) <= {TOL} THEN 'complementary'
                   WHEN min_open = max_open THEN 'identical_noncomp'
                   ELSE 'other_noncomp' END""",
    "capture_age": """CASE
                        WHEN fo.opening_captured_at IS NULL THEN 'no_capture_ts'
                        WHEN ref_time IS NULL THEN 'no_event_ref'
                        WHEN fo.opening_captured_at < ref_time - INTERVAL '1 hour'
                             THEN 'pre_event'
                        WHEN fo.opening_captured_at < ref_time THEN 'final_hour'
                        ELSE 'post_start_hindsight' END""",
    "truth": "fo.resolution_source",
}


def bin_sql(league: str, market_type: str, dimension: str) -> str:
    return f"""
WITH allrows AS (
  SELECT fo.is_winner AS is_winner,
         fo.resolution_source AS rsrc,
         fo.opening_probability AS op,
         fo.opening_captured_at AS opening_captured_at,
         fo.calibration_probability AS calibration_probability,
         COALESCE(fo.calibration_probability, fo.opening_probability) AS p,
         COALESCE(fm.commence_time, fm.resolution_date) AS ref_time,
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
    AND fm.market_type = '{market_type}'
    AND fm.llm_sport_category = '{league}'
  WINDOW w AS (PARTITION BY fo.market_id)
)
SELECT ({DIMENSIONS[dimension]})::text AS label,
       LEAST(FLOOR(p * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(p) AS sum_prob,
       SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners
FROM allrows
WHERE rsrc IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
  AND p > 0 AND p < 1
  AND op IS NOT NULL
  AND is_winner IS NOT NULL
GROUP BY 1, 2
""".strip()


def fold(template: str, min_id: int, max_id: int, chunk: int) -> tuple[dict, list, list]:
    acc: dict[tuple, dict] = {}
    shards: list[dict] = []
    irreducible: list[dict] = []
    stack: list[tuple[int, int]] = []
    lo = min_id
    while lo < max_id:
        hi = min(lo + chunk, max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()
    while stack:
        lo, hi = stack.pop()
        result = dbq_run(template.format(lo=lo, hi=hi), timeout_ms=10_000)
        if result.get("status") == "ok":
            if result.get("truncated"):
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                continue
            for label, b, n, sum_prob, winners in (result.get("rows") or []):
                slot = acc.setdefault((label, int(b)), {"n": 0, "sum_prob": 0.0, "winners": 0})
                slot["n"] += int(n)
                slot["sum_prob"] += float(sum_prob or 0)
                slot["winners"] += int(winners or 0)
            shards.append({"lo": lo, "hi": hi, "duration_ms": result.get("duration_ms"),
                           "sql_fingerprint": result.get("sql_fingerprint")})
            continue
        width = hi - lo
        if width <= BISECT_FLOOR_IDS:
            irreducible.append({"lo": lo, "hi": hi, "reason": result.get("reason")})
            continue
        mid = lo + width // 2
        stack.append((mid, hi))
        stack.append((lo, mid))
    return acc, shards, irreducible


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", required=True)
    parser.add_argument("--market-type", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    started = time.monotonic()
    report: dict = {
        "label": args.label,
        "cell": f"{args.league}/{args.market_type}",
        "dimensions": {},
        "bin_profile": [],
    }
    all_complete = True

    for dim in DIMENSIONS:
        acc, shards, irreducible = fold(
            bin_sql(args.league, args.market_type, dim),
            args.min_id, args.max_id, args.chunk,
        )
        complete = not irreducible
        all_complete &= complete
        by_label: dict[str, list] = {}
        for (label, b), v in acc.items():
            by_label.setdefault(label, []).append({"bin": b, **v})
        groups = []
        for label, bins in by_label.items():
            e, n = ece_from_bins(bins)
            groups.append({"label": label, "ece": e, "n": n, "gap": gap_from_bins(bins),
                           "winners": sum(x["winners"] for x in bins)})
        groups.sort(key=lambda g: -g["n"])
        report["dimensions"][dim] = {
            "complete": complete, "measured": complete,
            "shard_count": len(shards), "irreducible": irreducible, "groups": groups,
        }
        print(f"\n--- check: {dim}  (shards={len(shards)} irreducible={len(irreducible)})")
        print(f"{'label':<26} {'n':>7} {'ece':>7} {'gap':>8} {'winrate':>8}")
        for g in groups:
            wr = f"{g['winners']/g['n']:.3f}" if g["n"] else "-"
            print(f"{g['label']:<26} {g['n']:>7} {str(g['ece']):>7} {str(g['gap']):>8} {wr:>8}")
        # The bin profile only needs one dimension's fold; take it from the first.
        if not report["bin_profile"]:
            merged: dict[int, dict] = {}
            for (_, b), v in acc.items():
                slot = merged.setdefault(b, {"n": 0, "sum_prob": 0.0, "winners": 0})
                slot["n"] += v["n"]
                slot["sum_prob"] += v["sum_prob"]
                slot["winners"] += v["winners"]
            for b in sorted(merged):
                v = merged[b]
                report["bin_profile"].append({
                    "bin": b, "n": v["n"],
                    "avg_p": round(v["sum_prob"] / v["n"], 4),
                    "actual": round(v["winners"] / v["n"], 4),
                    "err_pp": round(abs(v["winners"] / v["n"] - v["sum_prob"] / v["n"]) * 100, 2),
                })

    report["complete"] = all_complete
    report["measured"] = all_complete
    report["elapsed_s"] = round(time.monotonic() - started, 1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.label}.json"
    path.write_text(json.dumps(report, indent=2))

    print(f"\n--- check 6: bin profile / noise floor")
    print(f"{'bin':>4} {'n':>7} {'avg_p':>7} {'actual':>7} {'err_pp':>7} {'contrib_pp':>10}")
    total_n = sum(b["n"] for b in report["bin_profile"])
    for b in report["bin_profile"]:
        print(f"{b['bin']:>4} {b['n']:>7} {b['avg_p']:>7} {b['actual']:>7} "
              f"{b['err_pp']:>7} {b['err_pp']*b['n']/total_n:>10.2f}")
    print(f"\nwrote {path} complete={all_complete} elapsed={report['elapsed_s']}s")
    return 0 if all_complete else 1


if __name__ == "__main__":
    sys.exit(main())
