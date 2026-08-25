#!/usr/bin/env python3
"""Is bin 5 a market price, or a 0.50 default wearing one?

``fold_leg_swap.py --column opening`` found that **47.2%** of
``baseball/quantity``'s structurally-healthy coherent class — 2,303 of 4,876
truth-eligible legs — sits in bin 5 at ``mean_p`` 0.5044 (Over) and 0.5072
(Under), while the realised outcome in that same bin is **3.84% Over / 93.92%
Under**. A coin-flip price against a 94/6 outcome.

A mean of 0.504 is not the same claim as a constant of 0.500, and the difference
decides the fix:

* If the mass is a **spike at one value**, this is a DEFAULT — a placeholder
  written when no real price was available. It is a data-provenance defect: the
  row asserts a forecast that was never quoted. The repair is exclusion (or
  refusal at write time), and it is invisible to every coherence check ever
  written, because ``0.50 + 0.50 = 1.0000`` is the most perfectly complementary
  pair possible. Item 1's gate would pass all 2,303 of these.
* If the mass is **spread across many nearby values**, these are real quotes on
  genuinely near-even markets, and the finding is ordinary miscalibration —
  interesting, but not a writer defect and not excludable.

A mean cannot tell those apart; only the value distribution can. So this fold
groups by the exact stored value (``Numeric(7,6)``, rounded to 4 dp to keep the
row count under the 1,000-row cap) and reports the top spikes with their
realised win rates attached, because a spike with an extreme win rate is the
signature and a spike alone is not.

The ``is_winner`` column travels with every row for one reason: a placeholder
price is only *harmful* if the outcome it stands in for was knowable. A 0.50
spike whose legs win 50/50 costs the curve nothing.

Usage:
    python3 backend/scripts/fold_coinflip_default.py --league baseball \\
        --market-type quantity --out artifacts/cal-p094 --label coinflip_bbq
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
    POPULATION_SOURCE,
    POPULATION_STATUS,
)

TOL = PAIR_SUM_TOLERANCE


def spike_sql(league: str, market_type: str) -> str:
    return f"""
WITH legs AS (
  SELECT lower(fo.name) AS leg,
         fo.is_winner,
         fo.opening_probability AS op,
         fo.calibration_probability AS cp,
         fo.resolution_source AS rsrc,
         COUNT(*) OVER w AS n_legs,
         COUNT(*) FILTER (WHERE lower(fo.name) = 'over') OVER w AS n_over,
         COUNT(*) FILTER (WHERE lower(fo.name) = 'under') OVER w AS n_under,
         COUNT(fo.opening_probability) OVER w AS n_open,
         SUM(fo.opening_probability) OVER w AS sum_open,
         COUNT(*) FILTER (WHERE fo.is_winner) OVER w AS n_win
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
    AND fm.source = '{POPULATION_SOURCE}'
    AND fm.status = '{POPULATION_STATUS}'
    AND fm.market_type = '{market_type}'
    AND fm.llm_sport_category = '{league}'
  WINDOW w AS (PARTITION BY fo.market_id)
)
SELECT leg,
       ROUND(op, 4)::text AS open_value,
       COUNT(*) AS n,
       SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS wins,
       COUNT(cp) AS n_cal,
       SUM(CASE WHEN cp IS NOT NULL AND ROUND(cp, 4) = ROUND(op, 4)
                THEN 1 ELSE 0 END) AS n_cal_equals_open
FROM legs
WHERE n_legs = 2 AND n_over = 1 AND n_under = 1
  AND n_open = 2
  AND ABS(sum_open - 1) <= {TOL}
  AND n_win = 1
  AND rsrc IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
  AND op > 0 AND op < 1
  AND is_winner IS NOT NULL
GROUP BY 1, 2
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", required=True)
    parser.add_argument("--market-type", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="coinflip_default")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    template = spike_sql(args.league, args.market_type)
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
        result = dbq_run(template.format(lo=lo, hi=hi), timeout_ms=args.timeout_ms)
        if result.get("status") == "ok":
            if result.get("truncated"):
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded", flush=True)
                continue
            for leg, val, n, wins, n_cal, n_eq in result.get("rows") or []:
                slot = acc.setdefault(
                    (leg, str(val)),
                    {"n": 0, "wins": 0, "n_cal": 0, "n_cal_equals_open": 0})
                slot["n"] += int(n)
                slot["wins"] += int(wins or 0)
                slot["n_cal"] += int(n_cal or 0)
                slot["n_cal_equals_open"] += int(n_eq or 0)
            shards.append({"lo": lo, "hi": hi, "duration_ms": result.get("duration_ms"),
                           "sql_fingerprint": result.get("sql_fingerprint")})
            print(f"  [{lo}..{hi}) ok {result.get('duration_ms')}ms", flush=True)
            continue
        width = hi - lo
        if width <= BISECT_FLOOR_IDS:
            irreducible.append({"lo": lo, "hi": hi, "reason": result.get("reason")})
            print(f"  [{lo}..{hi}) IRREDUCIBLE — {result.get('reason')}", flush=True)
            continue
        mid = lo + width // 2
        stack.append((mid, hi))
        stack.append((lo, mid))
        print(f"  [{lo}..{hi}) {result.get('status')} — bisecting", flush=True)

    total = sum(v["n"] for v in acc.values())
    rows = [{"leg": leg, "open_value": val, **v} for (leg, val), v in acc.items()]
    rows.sort(key=lambda r: -r["n"])

    complete = not irreducible
    out = {
        "label": args.label, "league": args.league, "market_type": args.market_type,
        "complete": complete, "measured": complete, "tolerance": TOL,
        "population": f"{POPULATION_SOURCE}/{POPULATION_STATUS}, "
                      f"{args.league}/{args.market_type}, 2-leg over+under, pair sum "
                      "INSIDE tolerance, one winner, truth-eligible legs only",
        "distinct_values": len(acc), "total_legs": total,
        "shard_count": len(shards), "shards": shards, "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "rows": rows,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.label}.json").write_text(json.dumps(out, indent=2))

    print(f"\nirreducible={len(irreducible)} complete={complete} "
          f"elapsed={out['elapsed_s']}s")
    print(f"distinct opening values: {len(acc)}   total legs: {total}")
    print(f"\n{'leg':<6} {'value':>8} {'n':>6} {'share':>7} {'win_rate':>9} "
          f"{'cal=open':>9}")
    for r in rows[:args.top]:
        share = r["n"] / total if total else 0
        wr = r["wins"] / r["n"] if r["n"] else 0
        eq = r["n_cal_equals_open"] / r["n_cal"] if r["n_cal"] else None
        print(f"{r['leg']:<6} {r['open_value']:>8} {r['n']:>6} {share:>7.3f} "
              f"{wr:>9.4f} {('n/a' if eq is None else f'{eq:.3f}'):>9}")
    if not complete:
        print("\nINCOMPLETE — a partial distribution cannot rule a spike in or out.")
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
