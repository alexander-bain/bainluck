#!/usr/bin/env python3
"""CAL-P991 — split ONE board cell's legs by the SHAPE of the market they sit on.

WHY. The board's rank-1 mechanism (``polymarket/baseball/quantity``) was named as
R1 — a two-leg Over/Under market whose BOTH legs open at exactly ``0.5000``,
which is the arithmetic signature of the writer taking 0.5 from an untraded
market and writing the partner as ``1 - 0.5``. That exclusion shipped
CELL-SCOPED to ``("polymarket", "baseball")`` (``PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS``),
and the staged design said in its own §6 that the writer path is not
baseball-specific so the spike is *likely* wider — "but likely is not measured".

This measures it, per cell, one cell per invocation. It reports each shape class
SEPARATELY with its own bins, so the reader sees not just how big a class is but
whether it is the class carrying the error. A class that is 40% of the rows and
calibrated is not a mechanism; a class that is 15% of the rows and reads 45 pp is.

POPULATION. Deliberately the same raw one ``fold_cohort_cell_eligible.py`` folds
(source/status/market_type/league, priced strictly inside (0,1), graded), NOT the
published one. Two reasons: it is the population the 2026-08-24 board ranking was
taken on, so the numbers are comparable to it; and it shows the class BEFORE any
producer exclusion removes it, which is the only way to see a class that a
cell-scoped exclusion is currently not removing.

The published-population counterpart is ``calibration_cell_exact.py``, which
folds the producer's own CTE chain and is what a before/after must be quoted on.

SHARDING is ``fm.id`` ranges for ``fold_cohort_cell_eligible.py``'s reason: the
population predicate has no index, so ``MOD`` divides the aggregate and multiplies
the scan. A shard that still times out is SPLIT, never dropped, and a range that
stays red at the floor is recorded as IRREDUCIBLE and taints the run (gotcha #53).

Usage::

    python3 backend/scripts/fold_shape_class_cell.py \\
        --league basketball --market-type quantity \\
        --out artifacts/cal-p991/shape-basketball-quantity.json
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

#: R1's exact value, imported rather than restated so this fold cannot measure a
#: different predicate than the one production applies.
from app.tasks.precompute_calibration import (  # noqa: E402
    PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE,
)


def shard_sql(league: str, market_type: str) -> str:
    """Per-shard: shape every market, then bin its legs under that shape's class.

    The shape CTE aggregates over ALL outcomes of the market — the same basis
    ``market_result_shape`` uses in the producer — so the class reflects the
    market as CAPTURED. The leg SELECT then re-applies the price/grade filters,
    which means a market can be classed ``ou_half2`` on two captured legs while
    contributing fewer than two legs to the bins. That is intended: the class is
    a statement about the market, the bins are a statement about what publishes.
    """
    half = PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE
    cell = (
        f"fm.source = '{POPULATION_SOURCE}'\n"
        f"  AND fm.status = '{POPULATION_STATUS}'\n"
        f"  AND fm.market_type = '{market_type}'\n"
        f"  AND fm.llm_sport_category = '{league}'"
    )
    return f"""
WITH shape AS (
  SELECT fo.market_id,
         COUNT(*) AS n_out,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'over') AS n_over,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'under') AS n_under,
         COUNT(*) FILTER (WHERE ROUND(fo.opening_probability, 4) = {half}) AS n_half
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
    AND {cell}
  GROUP BY 1
)
SELECT CASE
         WHEN s.n_out = 2 AND s.n_over = 1 AND s.n_under = 1 AND s.n_half = 2
           THEN 'ou_half2'
         WHEN s.n_out = 2 AND s.n_over = 1 AND s.n_under = 1 AND s.n_half = 1
           THEN 'ou_half1'
         WHEN s.n_out = 2 AND s.n_over = 1 AND s.n_under = 1
           THEN 'ou_priced'
         WHEN s.n_out >= 3 THEN 'multi'
         WHEN s.n_out = 1 THEN 'single'
         ELSE 'pair_unnamed'
       END AS cls,
       CASE WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
            THEN 'eligible' ELSE 'ineligible' END AS truth,
       LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
JOIN shape s ON s.market_id = fm.id
WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
  AND {cell}
  AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
  AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
  AND fo.opening_probability IS NOT NULL
  AND fo.is_winner IS NOT NULL
GROUP BY 1, 2, 3
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--league", required=True)
    parser.add_argument("--market-type", required=True)
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    template = shard_sql(args.league, args.market_type)

    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.chunk, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()

    started = time.monotonic()
    # cls -> truth -> bin -> {n, sum_prob, winners}
    acc: dict[str, dict[str, dict[int, dict]]] = {}
    shards: list[dict] = []
    irreducible: list[dict] = []

    while stack:
        lo, hi = stack.pop()
        result = dbq_run(template.format(lo=lo, hi=hi), timeout_ms=args.timeout_ms)
        status = result.get("status")
        if status == "ok":
            if result.get("truncated"):
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded", flush=True)
                continue
            for cls, truth, b, n, sum_prob, winners in result.get("rows") or []:
                slot = (
                    acc.setdefault(cls, {})
                    .setdefault(truth, {})
                    .setdefault(int(b), {"n": 0, "sum_prob": 0.0, "winners": 0})
                )
                slot["n"] += int(n)
                slot["sum_prob"] += float(sum_prob or 0)
                slot["winners"] += int(winners or 0)
            shards.append({
                "lo": lo, "hi": hi,
                "rows": result.get("row_count"),
                "duration_ms": result.get("duration_ms"),
                "sql_fingerprint": result.get("sql_fingerprint"),
            })
            print(f"  [{lo}..{hi}) ok rows={result.get('row_count')} "
                  f"{result.get('duration_ms')}ms", flush=True)
            continue

        # Not ok. A timeout is the only failure a SPLIT can answer.
        reason = str(result.get("reason") or "")
        if "timeout" not in reason.lower() or (hi - lo) <= BISECT_FLOOR_IDS:
            irreducible.append({"lo": lo, "hi": hi, "reason": reason[:200],
                                "status": status})
            print(f"  [{lo}..{hi}) IRREDUCIBLE {status}: {reason[:120]}", flush=True)
            continue
        mid = lo + (hi - lo) // 2
        stack.append((mid, hi))
        stack.append((lo, mid))
        print(f"  [{lo}..{hi}) timeout — split at {mid}", flush=True)

    out = {
        "label": "shape_class_cell",
        "cell": f"{args.league}/{args.market_type}",
        "population": {
            "source": POPULATION_SOURCE,
            "status": POPULATION_STATUS,
            "market_type": args.market_type,
            "league": args.league,
            "note": "raw cell population (the 2026-08-24 board's basis), "
                    "NOT the published population",
        },
        "half_spike_value": PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE,
        "irreducible": irreducible,
        "complete": not irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "shard_count": len(shards),
        "classes": {},
    }

    for cls, by_truth in sorted(acc.items()):
        entry = {}
        for truth, bins in by_truth.items():
            ece, n = ece_from_bins(list(bins.values()))
            entry[truth] = {
                "n": n,
                "ece": ece,
                "gap": gap_from_bins(list(bins.values())),
                "bins": {str(k): v for k, v in sorted(bins.items())},
            }
        out["classes"][cls] = entry

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")

    print(f"\n{out['cell']}  complete={out['complete']}  {out['elapsed_s']}s")
    # `gap` is the fold's own convention, price MINUS outcome: positive means
    # the class was published too high. `None` is MIN_CELL_N (<30), which is
    # absent rather than 0.0 — the distinction the folds exist to keep.
    print(f"{'class':>14} {'truth':>11} {'n':>7} {'ece':>7} {'gap':>8}")
    for cls, by_truth in out["classes"].items():
        for truth, v in sorted(by_truth.items()):
            print(f"{cls:>14} {truth:>11} {v['n']:>7} "
                  f"{str(v['ece']):>7} {str(v['gap']):>8}")
    print(f"\nwrote {args.out}")
    return 0 if out["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
