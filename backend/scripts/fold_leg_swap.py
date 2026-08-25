#!/usr/bin/env python3
"""Are the two legs of a COHERENT Over/Under pair priced on the right sides?

Item 2's target is the mass that item 1's pair defect does NOT explain:
``baseball/quantity``'s structurally-healthy ``ok`` class — n=4,880, 72% of the
cell, **13.51 pp ECE at gap −6.23**. Coherent openings, both legs present, pair
sum inside tolerance, and still badly calibrated in a single direction.

``gap`` here is ``(sum_p − winners)/n``, so −6.23 means the class **under-prices
its winners by 6.23 pp**. That sign is the whole reason for this fold, because it
kills the obvious suspect and points at a specific alternative:

* **Hindsight contamination is REFUTED by the sign.** ``calibration_probability``
  is live on 6,770 of 6,778 eligible legs in this cell and legs were touched
  minutes ago, so a post-settlement rewrite is mechanically available. But a
  price dragged toward a known outcome makes winners look *more* likely, i.e.
  gap POSITIVE. This class is negative. Whatever is moving these prices is not
  moving them toward the answer.
* **A LEG SWAP predicts exactly this sign, and it is invisible to item 1's
  gate.** If the Over leg is written with the Under price and vice versa, the
  pair still sums to 1.0000 — perfectly "coherent" — while every leg carries its
  own complement. Winners skew toward the higher-priced side, so recording each
  leg at ``1 − p`` records winners LOW: a systematic negative gap on coherent
  pairs. A sum-based coherence check cannot see this, by construction. That is
  not a criticism of the gate; it is the gate's blind spot, and it means "the
  pair is coherent" was never evidence that the legs are on the right sides.

The discriminating measurement is the one item 1 already established: the named
leg's win rate AS A FUNCTION OF its own recorded ``p``.

    Over win rate RISES with p   -> legs are on the right sides. Swap refuted;
                                    the residual is elsewhere (real miscalibration,
                                    or threshold semantics).
    Over win rate FALLS with p    -> swap. The slope's sign IS the finding.
    flat near 0.5                 -> p carries no information for either leg.

``p`` is ``COALESCE(calibration_probability, opening_probability)`` — the
PUBLISHED number, not the opening — because 15.86 is computed on the published
number and a mechanism for a published defect has to be measured on the column
the reader sees. (Item 1's direction fold deliberately used ``opening_probability``
instead; it was diagnosing a WRITER defect at capture time. Same shape of test,
different column, different question.)

Usage:
    python3 backend/scripts/fold_leg_swap.py --league baseball \\
        --market-type quantity --out artifacts/cal-p094 --label leg_swap_bbq
"""

from __future__ import annotations

import argparse
import json
import math
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


COLUMNS = {
    "published": "COALESCE(fo.calibration_probability, fo.opening_probability)",
    "opening": "fo.opening_probability",
    "calibration": "fo.calibration_probability",
}


def swap_sql(league: str, market_type: str, column: str) -> str:
    return f"""
WITH legs AS (
  SELECT fo.market_id,
         lower(fo.name) AS leg,
         fo.is_winner,
         {COLUMNS[column]} AS p,
         fo.resolution_source AS rsrc,
         COUNT(*) OVER w AS n_legs,
         COUNT(*) FILTER (WHERE lower(fo.name) = 'over') OVER w AS n_over,
         COUNT(*) FILTER (WHERE lower(fo.name) = 'under') OVER w AS n_under,
         COUNT(fo.opening_probability) OVER w AS n_open,
         MIN(fo.opening_probability) OVER w AS min_open,
         MAX(fo.opening_probability) OVER w AS max_open,
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
       LEAST(FLOOR(p * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(p) AS sum_p,
       SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS wins
FROM legs
WHERE n_legs = 2 AND n_over = 1 AND n_under = 1
  AND n_open = 2
  AND ABS(sum_open - 1) <= {TOL}
  AND n_win = 1
  AND rsrc IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
  AND p > 0 AND p < 1
  AND is_winner IS NOT NULL
GROUP BY 1, 2
""".strip()


def weighted_corr(points: list[tuple[float, float, int]]) -> float | None:
    """n-weighted correlation between recorded p and realised win rate.

    Returns ``None`` rather than 0.0 when it is undefined (a single populated
    bin has zero variance), because 0.0 reads as "measured, no relationship" and
    that is a different claim from "not measurable".
    """
    total = sum(n for _, _, n in points)
    if total <= 0 or len(points) < 3:
        return None
    mx = sum(x * n for x, _, n in points) / total
    my = sum(y * n for _, y, n in points) / total
    sx = math.sqrt(sum(n * (x - mx) ** 2 for x, _, n in points) / total)
    sy = math.sqrt(sum(n * (y - my) ** 2 for _, y, n in points) / total)
    if sx == 0 or sy == 0:
        return None
    cov = sum(n * (x - mx) * (y - my) for x, y, n in points) / total
    return round(cov / (sx * sy), 4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", required=True)
    parser.add_argument("--market-type", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="leg_swap")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    parser.add_argument("--column", choices=sorted(COLUMNS), default="published",
                        help="which probability column the slope is measured on")
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    template = swap_sql(args.league, args.market_type, args.column)
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
            for leg, b, n, sum_p, wins in result.get("rows") or []:
                slot = acc.setdefault((leg, int(b)), {"n": 0, "sum_p": 0.0, "wins": 0})
                slot["n"] += int(n)
                slot["sum_p"] += float(sum_p or 0)
                slot["wins"] += int(wins or 0)
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

    by_leg: dict[str, list] = {}
    for (leg, b), v in sorted(acc.items()):
        by_leg.setdefault(leg, []).append({"bin": b, **v})

    summary = {}
    for leg, bins in by_leg.items():
        n = sum(b["n"] for b in bins)
        wins = sum(b["wins"] for b in bins)
        sum_p = sum(b["sum_p"] for b in bins)
        pts = [(b["sum_p"] / b["n"], b["wins"] / b["n"], b["n"]) for b in bins if b["n"]]
        summary[leg] = {
            "n": n, "wins": wins,
            "mean_p": round(sum_p / n, 4) if n else None,
            "win_rate": round(wins / n, 4) if n else None,
            "gap_pp": round((sum_p - wins) / n * 100, 2) if n else None,
            "weighted_corr_p_vs_winrate": weighted_corr(pts),
            "bins": bins,
        }

    complete = not irreducible
    out = {
        "label": args.label, "league": args.league, "market_type": args.market_type,
        "complete": complete, "measured": complete, "tolerance": TOL,
        "probability_column": COLUMNS[args.column].replace("fo.", ""),
        "population": f"{POPULATION_SOURCE}/{POPULATION_STATUS}, "
                      f"{args.league}/{args.market_type}, 2-leg over+under, both "
                      "openings present, pair sum INSIDE tolerance (the coherent "
                      "'ok' class), exactly one winner, truth-eligible legs only",
        "shard_count": len(shards), "shards": shards, "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "summary": summary,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.label}.json").write_text(json.dumps(out, indent=2))

    print(f"\nirreducible={len(irreducible)} complete={complete} "
          f"elapsed={out['elapsed_s']}s")
    for leg, s in summary.items():
        print(f"\n{leg}: n={s['n']} mean_p={s['mean_p']} win_rate={s['win_rate']} "
              f"gap={s['gap_pp']}pp corr={s['weighted_corr_p_vs_winrate']}")
        print(f"   {'bin':>4} {'n':>6} {'mean_p':>8} {'win_rate':>9} {'err_pp':>8}")
        for b in s["bins"]:
            mp = b["sum_p"] / b["n"]
            wr = b["wins"] / b["n"]
            print(f"   {b['bin']:>4} {b['n']:>6} {mp:>8.4f} {wr:>9.4f} "
                  f"{(mp - wr) * 100:>8.2f}")
    if not complete:
        print("\nINCOMPLETE — a partial slope is not a verdict about a population.")
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
