#!/usr/bin/env python3
"""CAL-P991 — split ONE board cell's legs by the PROP FAMILY its market names.

WHY. ``polymarket/baseball/quantity`` (board rank 1) publishes at
n 5,730 / ECE 6.74 / gap -1.88 on q269, and its per-bin shape is not a tilt —
it is a SHRINK. Bins 2-6 are calibrated to within 3 pp; bins 0-1 win far more
than they are priced (0.047 -> 0.171, 0.139 -> 0.306) and bins 7-9 win far less
(0.931 -> 0.824). A monotone mispricing cannot do that. A MIXTURE can: pool a
calibrated population with a subpopulation whose outcome is independent of its
price, and the tails collapse toward the pooled base rate while the middle,
which sits at the base rate already, does not move.

So the question this fold asks is not "which family is biggest" but "which
family's win rate is FLAT in price" — a family whose bin-0 legs and bin-9 legs
win at about the same rate is a family whose price is not about its outcome.

``family`` is read from ``fm.name``, which is written at capture and is
therefore knowable before a winner exists (the same rule ``slotratio`` states:
a dimension a shipping exclusion could not evaluate at publish time is a
diagnosis dimension only). Polymarket names these markets
``"<subject>: <family> O/U <line>"``, so the family is the text between the
colon and the ``O/U``. Anything that does not match that shape is ``(unnamed)``
and is reported, never dropped (gotcha #53) — a family bucket that silently
swallowed the rows it could not parse would read as a clean census of a
population it never saw.

POPULATION. The raw cell (source/status/market_type/league, priced strictly
inside (0,1), graded), the same one ``fold_shape_class_cell.py`` folds, so the
two tables can be read against each other. ``truth`` splits eligible from
ineligible rather than filtering, because the eligible arm is what the curve
grades and the ineligible arm is the control that says whether a family's
flatness is a property of the family or of the grading.

SHARDING is ``fm.id`` ranges, split on timeout, IRREDUCIBLE at the floor.

Usage::

    python3 backend/scripts/fold_prop_family_cell.py \\
        --league baseball --market-type quantity \\
        --out artifacts/cal-p991/family-baseball-quantity.json
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

#: The name shape Polymarket writes for a player/team quantity market. Kept as
#: one constant so the parse and the "did it parse" guard cannot drift apart.
FAMILY_REGEX = r':\s*(.*?)\s*O/U'


def shard_sql(league: str, market_type: str) -> str:
    cell = (
        f"fm.source = '{POPULATION_SOURCE}'\n"
        f"  AND fm.status = '{POPULATION_STATUS}'\n"
        f"  AND fm.market_type = '{market_type}'\n"
        f"  AND fm.llm_sport_category = '{league}'"
    )
    return f"""
SELECT COALESCE(substring(fm.name from '{FAMILY_REGEX}'), '(unnamed)') AS family,
       CASE WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
            THEN 'eligible' ELSE 'ineligible' END AS truth,
       LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
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

    sql_tmpl = shard_sql(args.league, args.market_type)
    raw: list = []
    irreducible: list = []
    t0 = time.time()
    sweep(sql_tmpl, args.min_id, args.max_id, args.chunk,
          args.timeout_ms, raw, irreducible,
          runner=dbq_run, floor=BISECT_FLOOR_IDS)
    secs = round(time.time() - t0, 1)

    # family -> truth -> bin -> {n, sum_prob, winners}
    agg: dict = {}
    for family, truth, b, n, sp, w in raw:
        cell = agg.setdefault(str(family), {}).setdefault(str(truth), {})
        slot = cell.setdefault(int(b), {"n": 0, "sum_prob": 0.0, "winners": 0})
        slot["n"] += int(n or 0)
        slot["sum_prob"] += float(sp or 0)
        slot["winners"] += int(w or 0)

    print(f"\n{args.league}/{args.market_type}  complete={not irreducible}  "
          f"{secs}s", flush=True)
    header = (f"{'family':<26}{'truth':<12}{'n':>7}{'ece':>8}{'gap':>8}"
              f"{'lo win%':>9}{'hi win%':>9}{'flat':>7}")
    print(header)
    table = []
    for family, by_truth in sorted(agg.items()):
        for truth, bins in sorted(by_truth.items()):
            ece, n = ece_from_bins(list(bins.values()))
            gap = gap_from_bins(list(bins.values()))
            lo_n = sum(v["n"] for k, v in bins.items() if k <= 1)
            lo_w = sum(v["winners"] for k, v in bins.items() if k <= 1)
            hi_n = sum(v["n"] for k, v in bins.items() if k >= 8)
            hi_w = sum(v["winners"] for k, v in bins.items() if k >= 8)
            lo = round(100 * lo_w / lo_n, 1) if lo_n else None
            hi = round(100 * hi_w / hi_n, 1) if hi_n else None
            # The mixture signature: a family whose cheapest legs and dearest
            # legs win at similar rates is not being priced, it is being
            # labelled. Reported as a number, never as a verdict.
            flat = round(hi - lo, 1) if (lo is not None and hi is not None) else None
            print(f"{family[:25]:<26}{truth:<12}{n:>7}{str(ece):>8}{str(gap):>8}"
                  f"{str(lo):>9}{str(hi):>9}{str(flat):>7}")
            table.append({"family": family, "truth": truth, "n": n,
                          "ece": ece, "gap": gap, "lo_n": lo_n, "lo_win": lo,
                          "hi_n": hi_n, "hi_win": hi, "spread": flat,
                          "bins": {str(k): v for k, v in sorted(bins.items())}})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "league": args.league, "market_type": args.market_type,
        "population": {"source": POPULATION_SOURCE, "status": POPULATION_STATUS},
        "family_regex": FAMILY_REGEX,
        "seconds": secs, "complete": not irreducible,
        "irreducible": irreducible, "table": table,
    }, indent=1))
    print(f"\nwrote {out}")
    return 1 if irreducible else 0


if __name__ == "__main__":
    raise SystemExit(main())
