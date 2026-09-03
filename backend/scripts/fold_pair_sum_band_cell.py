#!/usr/bin/env python3
"""CAL-P991 — band ONE board cell's two-leg markets by their PUBLISHED price sum.

WHY. ``polymarket/baseball/quantity`` (board rank 1) is not tilted, it is FLAT:
in its game-total family the win rate runs 0.368 -> 0.382 -> 0.380 -> 0.393 as
the published price runs 0.041 -> 0.344, and tops out at 0.722 where the price
says 0.930. A price that barely moves the outcome is not a mispriced forecast;
it is a number that is not a forecast. Reading the rows shows what it is:

    Cincinnati Reds vs. New York Yankees: O/U 7.5   Over 0.0010  Under 0.0010
    Milwaukee Brewers vs. Atlanta Braves: O/U 6.5   Over 0.0100  Under 0.0005

Two mutually exclusive legs of one question, published at a sum of 0.002 and
0.0105. Exactly one of them wins, always, so the pair's honest sum is 1.0.

WHAT THE PRODUCER ALREADY CHECKS, AND THE HOLE IT LEAVES. ``mex_normalization``
divides a partition by its own sum — but only for markets with **>= 3**
outcomes, and only when the sum is **above** 1.15. ``malformed_binary_filter``
does cover 2-outcome markets — but it tests the WINNER count, never the price.
``nonexclusive_bundle_filter`` covers ``polymarket/baseball`` — but only for
markets of **>= 3** outcomes, and a Polymarket run-total ladder is not one
market with many rungs, it is many two-leg markets one per line, so every
>= 3-outcome rule is structurally blind to it. The result is that **no rule in
the chain reads a binary's price sum, and no rule in the chain looks
downward at all.**

WHAT THIS FOLD DOES. It bands every two-leg Over/Under market of the cell by the
sum of its two PUBLISHED prices (``COALESCE(calibration_probability,
opening_probability)`` — the coalesce the curve grades, gotcha #144), and bins
each band's legs separately so a band's SIZE is never read as its ERROR.

THE BANDS WERE FIXED BEFORE THE FOLD RAN AND THEY ARE SYMMETRIC IN LOG SPACE
around 1.0, at the producer's own incoherence threshold and its reciprocal:
1/4, 1/1.15, 1.15, 4. Lesson 13 — a correction expected to run one way runs both
ways, so the banding has to be able to SEE both ways. Here it is expected to
find the low side, and the high side is the arm that says whether that
expectation was the instrument or the cell.

``z_not_two_leg`` is the untouched control. A row-dropping rule keyed on this
dimension must move it by zero rows, and doctrine 18 grades it there.

POPULATION. The raw cell, matching ``fold_shape_class_cell.py`` and
``fold_prop_family_cell.py`` so the three tables read against each other. The
published-population counterpart is ``calibration_cell_exact.py --by pairsum``,
which is what a before/after must be quoted on.

Usage::

    python3 backend/scripts/fold_pair_sum_band_cell.py \\
        --league baseball --market-type quantity \\
        --out artifacts/cal-p991/pairsum-baseball-quantity.json
"""

from __future__ import annotations

import argparse
import json
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
from sharded_sweep import sweep  # noqa: E402

#: The producer's own incoherence threshold and its reciprocal, and the same
#: pair one octave out. Named constants because two dimensions that band the
#: same quantity must band it identically or their tables cannot be read
#: against each other (the ``sumband`` / ``pairsum`` rule in
#: ``calibration_cell_exact.py``).
SUM_HI = 1.15
SUM_LO = round(1 / 1.15, 4)   # 0.8696
SUM_HI_FAR = 4.0
SUM_LO_FAR = 0.25


def shard_sql(league: str, market_type: str) -> str:
    cell = (
        f"fm.source = '{POPULATION_SOURCE}'\n"
        f"  AND fm.status = '{POPULATION_STATUS}'\n"
        f"  AND fm.market_type = '{market_type}'\n"
        f"  AND fm.llm_sport_category = '{league}'"
    )
    # The pair sum is taken over EVERY captured leg of the market, not over the
    # legs that survive the price filter: a market whose partner leg was dropped
    # for a NULL price still had two legs, and summing only the survivor would
    # manufacture a low sum out of the filter rather than out of the writer.
    # ``y_one_leg_priced`` holds those out as their own class instead of banding
    # them, because a pair with one price has no pair sum to judge.
    #
    # 🔴 NO APOSTROPHES IN THE EMITTED SQL, INCLUDING IN ``--`` COMMENTS. The
    # db-query read guard scans for quotes to find statement boundaries, so one
    # possessive inside a comment makes it read the rest as a string literal and
    # answer "Only SELECT queries are allowed" at every width (measured
    # 2026-09-03; ``sharded_sweep.is_sql_refusal`` is what stops that from
    # becoming a bisect storm).
    return f"""
WITH pairshape AS (
  SELECT fo.market_id,
         COUNT(*) AS n_out,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'over')  AS n_over,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'under') AS n_under,
         COUNT(*) FILTER (
           WHERE COALESCE(fo.calibration_probability, fo.opening_probability)
                 IS NOT NULL) AS n_priced,
         SUM(COALESCE(fo.calibration_probability, fo.opening_probability))
           AS psum
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
    AND {cell}
  GROUP BY 1
)
SELECT CASE
         WHEN NOT (s.n_out = 2 AND s.n_over = 1 AND s.n_under = 1)
           THEN 'z_not_two_leg'
         WHEN s.n_priced < 2              THEN 'y_one_leg_priced'
         WHEN s.psum IS NULL              THEN 'y_sum_null'
         WHEN s.psum <  {SUM_LO_FAR}      THEN 'a_sum_lt_0.25'
         WHEN s.psum <  {SUM_LO}          THEN 'b_sum_0.25_0.87'
         WHEN s.psum <= {SUM_HI}          THEN 'c_sum_coherent'
         WHEN s.psum <= {SUM_HI_FAR}      THEN 'd_sum_1.15_4'
         ELSE 'e_sum_gt_4' END AS band,
       CASE WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
            THEN 'eligible' ELSE 'ineligible' END AS truth,
       LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
JOIN pairshape s ON s.market_id = fm.id
WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
  AND {cell}
  AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
  AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
  AND fo.is_winner IS NOT NULL
GROUP BY 1, 2, 3
""".strip()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True)
    p.add_argument("--league", required=True)
    p.add_argument("--market-type", required=True)
    p.add_argument("--min-id", type=int, default=1)
    p.add_argument("--max-id", type=int, default=62_000_000)
    p.add_argument("--chunk", type=int, default=4_000_000)
    p.add_argument("--timeout-ms", type=int, default=10_000)
    args = p.parse_args()

    raw: list = []
    irreducible: list = []
    t0 = time.time()
    sweep(shard_sql(args.league, args.market_type), args.min_id, args.max_id,
          args.chunk, args.timeout_ms, raw, irreducible,
          runner=dbq_run, floor=BISECT_FLOOR_IDS)
    secs = round(time.time() - t0, 1)

    agg: dict = {}
    for band, truth, b, n, sp, w in raw:
        bins = agg.setdefault(str(band), {}).setdefault(str(truth), {})
        slot = bins.setdefault(int(b), {"n": 0, "sum_prob": 0.0, "winners": 0})
        slot["n"] += int(n or 0)
        slot["sum_prob"] += float(sp or 0)
        slot["winners"] += int(w or 0)

    print(f"\n{args.league}/{args.market_type}  complete={not irreducible}  "
          f"{secs}s", flush=True)
    print(f"{'band':<20}{'truth':<12}{'n':>7}{'ece':>8}{'gap':>9}"
          f"{'lo win%':>9}{'hi win%':>9}")
    table = []
    for band, by_truth in sorted(agg.items()):
        for truth, bins in sorted(by_truth.items()):
            ece, n = ece_from_bins(list(bins.values()))
            gap = gap_from_bins(list(bins.values()))
            lo_n = sum(v["n"] for k, v in bins.items() if k <= 1)
            lo_w = sum(v["winners"] for k, v in bins.items() if k <= 1)
            hi_n = sum(v["n"] for k, v in bins.items() if k >= 8)
            hi_w = sum(v["winners"] for k, v in bins.items() if k >= 8)
            lo = round(100 * lo_w / lo_n, 1) if lo_n else None
            hi = round(100 * hi_w / hi_n, 1) if hi_n else None
            print(f"{band:<20}{truth:<12}{n:>7}{str(ece):>8}{str(gap):>9}"
                  f"{str(lo):>9}{str(hi):>9}")
            table.append({"band": band, "truth": truth, "n": n, "ece": ece,
                          "gap": gap, "lo_n": lo_n, "lo_win": lo,
                          "hi_n": hi_n, "hi_win": hi,
                          "bins": {str(k): v for k, v in sorted(bins.items())}})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "league": args.league, "market_type": args.market_type,
        "population": {"source": POPULATION_SOURCE, "status": POPULATION_STATUS},
        "bands": {"lo_far": SUM_LO_FAR, "lo": SUM_LO,
                  "hi": SUM_HI, "hi_far": SUM_HI_FAR},
        "seconds": secs, "complete": not irreducible,
        "irreducible": irreducible, "table": table,
    }, indent=1))
    print(f"\nwrote {out}")
    return 1 if irreducible else 0


if __name__ == "__main__":
    raise SystemExit(main())
