#!/usr/bin/env python3
"""CAL-P991 — for ONE cell, why each captured leg did or did not reach the curve.

WHY THIS EXISTS. ``calibration_cell_exact.py --by ouside`` measured that in
``polymarket/basketball/quantity`` the published Over legs win **7.2%**
(partnered) and **9.8%** (alone) at every price band, while a raw sample of the
same markets has Over winning ~45%. A cell whose win rate is flat in price is
not mispriced — something is CHOOSING which legs publish, and choosing the
losing side. This fold names the chooser.

It walks ``ranked_outcomes`` — the last CTE before every exclusion is applied —
and assigns each leg the FIRST filter that would drop it, in ``deduped``'s own
precedence order, then groups by (leg side, verdict, won/lost). Precedence
matters: a leg routinely trips several filters and a count that lets it appear
under each one cannot be summed (the ``deduped`` block says the same thing about
its own rungs). ``kept`` is the arm that publishes.

READ IT AS A CONTINGENCY TABLE, NOT A RANKING. The question is never "which
verdict is biggest" — it is "which verdict's Over/Under split differs from the
population's". A filter that drops 60% of the legs evenly is not a calibration
defect; a filter that drops 200 legs and every one of them is a winning Over is.

Usage::

    python3 backend/scripts/fold_dedup_verdict_cell.py \\
        --source polymarket --category basketball --market-type quantity \\
        --out artifacts/cal-p991/verdict-basketball-quantity.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
)

from calibration_cell_exact import (  # noqa: E402
    _strip_sql_comments,
    db_query,
)

#: ``deduped``'s WHERE, as an ordered CASE. The order is the file's order, and
#: the last three arms are the CASE at the bottom of ``deduped`` unrolled: a
#: complete normalized field always publishes, a multi row must clear the
#: extreme-tail band AND not be the virtual market's modal price, and everything
#: else publishes only its ``rn = 1`` representative.
VERDICT_CASE = """
CASE
  WHEN NOT ro.is_liquid                     THEN 'x01_illiquid'
  WHEN ro.is_poly_placeholder               THEN 'x02_poly_placeholder'
  WHEN ro.is_malformed_binary               THEN 'x03_malformed_binary'
  WHEN ro.is_esports_bundle                 THEN 'x04_esports_bundle'
  WHEN ro.is_player_props_placeholder       THEN 'x05_player_props_placeholder'
  WHEN ro.is_golf_placeholder               THEN 'x06_golf_placeholder'
  WHEN ro.is_kalshi_prop_threshold          THEN 'x07_kalshi_prop_threshold'
  WHEN ro.is_weather_wide_spread            THEN 'x08_weather_wide_spread'
  WHEN ro.is_no_winner_market               THEN 'x09_no_winner_market'
  WHEN ro.is_draw_authority_missing         THEN 'x10_draw_authority_missing'
  WHEN ro.is_orphan_partition               THEN 'x11_orphan_partition'
  WHEN ro.is_field_incomplete               THEN 'x12_field_incomplete'
  WHEN ro.is_mex_normalized                 THEN 'kept_complete_field'
  WHEN ro.is_multi AND NOT (ro.adj_opening_probability > 0.005
                        AND ro.adj_opening_probability < 0.98)
                                            THEN 'x13_multi_extreme_tail'
  WHEN ro.is_multi AND mp.vm_id IS NOT NULL THEN 'x14_multi_modal_price'
  WHEN ro.is_multi                          THEN 'kept_multi'
  WHEN ro.rn = 1                            THEN 'kept_rn1'
  ELSE 'x15_not_the_rn1_representative'
END
"""


def cell_sql(source: str, category: str, market_type: str, lo: int, hi: int) -> str:
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}' "
            f"AND fm.id >= {lo} AND fm.id < {hi}"
        )
    )
    return _strip_sql_comments(
        "WITH " + pop + f"""
SELECT {VERDICT_CASE} AS verdict,
       CASE WHEN lower(btrim(ro.outcome_name)) = 'over' THEN 'over'
            WHEN lower(btrim(ro.outcome_name)) = 'under' THEN 'under'
            ELSE 'zz_other' END AS side,
       CASE WHEN ro.is_winner THEN 'won' ELSE 'lost' END AS graded,
       COUNT(*) AS n
FROM normalized ro
LEFT JOIN mode_prices mp
  ON mp.vm_id = ro.vm_id AND mp.source = ro.source
  AND mp.mode_price = ro.adj_opening_probability
WHERE COALESCE(ro.market_type, 'null') = '{market_type}'
GROUP BY 1, 2, 3
""".strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--market-type", required=True)
    ap.add_argument("--width", type=int, default=1_000_000)
    ap.add_argument("--min-id", type=int, default=1)
    ap.add_argument("--max-id", type=int, default=60_097_325)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.width, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()

    started = time.monotonic()
    acc: dict[tuple[str, str, str], int] = defaultdict(int)
    chunks = 0
    while stack:
        lo, hi = stack.pop()
        try:
            res = db_query(cell_sql(args.source, args.category,
                                    args.market_type, lo, hi))
        except Exception as exc:  # QueryTimeout and friends -> split
            if (hi - lo) <= 25:
                print(f"  [{lo}..{hi}) IRREDUCIBLE {exc}", flush=True)
                continue
            mid = lo + (hi - lo) // 2
            stack.append((mid, hi))
            stack.append((lo, mid))
            continue
        for verdict, side, graded, n in res.get("rows") or []:
            acc[(verdict, side, graded)] += int(n)
        chunks += 1
        if chunks % 10 == 0:
            print(f"  {chunks} chunks, id<{hi}, "
                  f"{time.monotonic() - started:.0f}s", flush=True)

    rows = []
    for (verdict, side, graded), n in acc.items():
        rows.append({"verdict": verdict, "side": side, "graded": graded, "n": n})
    out = {
        "cell": f"{args.source}/{args.category}/{args.market_type}",
        "elapsed_s": round(time.monotonic() - started, 1),
        "rows": rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")

    # verdict -> side -> {won, lost}
    table: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"won": 0, "lost": 0}))
    for r in rows:
        table[r["verdict"]][r["side"]][r["graded"]] += r["n"]
    print(f"\n{out['cell']}  {out['elapsed_s']}s")
    print(f"{'verdict':>32} {'side':>9} {'n':>6} {'won':>6} {'win%':>7}")
    for verdict in sorted(table):
        for side in sorted(table[verdict]):
            v = table[verdict][side]
            n = v["won"] + v["lost"]
            print(f"{verdict:>32} {side:>9} {n:>6} {v['won']:>6} "
                  f"{100.0 * v['won'] / n:>6.1f}%")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
