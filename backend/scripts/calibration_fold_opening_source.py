#!/usr/bin/env python3
"""#5401 — fold ONE cell by ``opening_source`` through the PRODUCER'S OWN chain.

WHY THIS EXISTS. #5401 measured that ``futures_outcomes.opening_source`` splits
high-confidence Kalshi legs into a well-calibrated cohort (``bid_ask_midpoint``,
90-99% at a mean price of ~0.96) and two fallback cohorts that are not
(``first_snapshot`` and no recorded basis at all, 0.1-61%). Every number in that
issue is measured on the RAW resolved-legs population.

The published calibration population is a PIPELINE, not a ``WHERE`` clause —
``kalshi/golf`` runs 73,970 -> 38,252 -> 34,774 -> 31,296 -> 22,074 — and
several of the legs #5401 names are already removed by ``is_golf_placeholder``,
the liquidity gate, or the representative rules before they can reach a reader.
So the raw deficit CANNOT be quoted at a cell, and the repair's expected
population move CANNOT be declared, until the same split is taken INSIDE the
serving window. That is this file's whole job.

It is the CAL-P114 instrument pointed at a different question: it calls
``_calibration_population_ctes()`` from the producer, appends the ``deduped``
precedence ladder as a CASE (borrowed verbatim from
``fold_dedup_verdict_cell.py``), and groups the result by opening basis rather
than by leg side. ``kept_*`` verdicts are the arm a reader sees.

Read the ``kept`` rows and nothing else when sizing the repair: an excluded leg
is already not in the curve, and counting it would over-state the ship.

Usage::

    python3 backend/scripts/calibration_fold_opening_source.py \\
        --source kalshi --category golf \\
        --out artifacts/cal-p1118/opening-source-kalshi-golf.json
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
from fold_dedup_verdict_cell import VERDICT_CASE  # noqa: E402

#: The band #5401 is about. A fallback-priced leg below this is not the defect —
#: the claim is specifically that near-certainty is being published off no book.
HIGH_BAND = 0.80


def cell_sql(source: str, category: str, lo: int, hi: int) -> str:
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}' "
            f"AND fm.id >= {lo} AND fm.id < {hi}"
        )
    )
    return _strip_sql_comments(
        "WITH " + pop + f"""
SELECT COALESCE(fo2.opening_source, '(none)') AS opening_source,
       {VERDICT_CASE} AS verdict,
       CASE WHEN ro.adj_opening_probability >= {HIGH_BAND}
            THEN 'hi' ELSE 'lo' END AS band,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE ro.is_winner) AS won,
       ROUND(SUM(ro.adj_opening_probability)::numeric, 3) AS implied
FROM normalized ro
LEFT JOIN mode_prices mp
  ON mp.vm_id = ro.vm_id AND mp.source = ro.source
  AND mp.mode_price = ro.adj_opening_probability
JOIN futures_outcomes fo2 ON fo2.id = ro.outcome_id
GROUP BY 1, 2, 3
""".strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
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
    # (opening_source, verdict, band) -> [n, won, implied]
    acc: dict[tuple[str, str, str], list[float]] = defaultdict(
        lambda: [0, 0, 0.0])
    chunks = 0
    irreducible = 0
    while stack:
        lo, hi = stack.pop()
        try:
            res = db_query(cell_sql(args.source, args.category, lo, hi))
        except Exception as exc:  # QueryTimeout and friends -> split
            if (hi - lo) <= 25:
                print(f"  [{lo}..{hi}) IRREDUCIBLE {exc}", flush=True)
                irreducible += 1
                continue
            mid = lo + (hi - lo) // 2
            stack.append((mid, hi))
            stack.append((lo, mid))
            continue
        rows = res.get("rows") or []
        # gotcha: the row cap is 1,000 and a capped answer is silently short.
        if len(rows) >= 1000:
            raise RuntimeError(f"[{lo}..{hi}) hit the 1,000-row cap")
        for opening_source, verdict, band, n, won, implied in rows:
            cell = acc[(opening_source, verdict, band)]
            cell[0] += int(n)
            cell[1] += int(won)
            cell[2] += float(implied or 0.0)
        chunks += 1
        if chunks % 10 == 0:
            print(f"  {chunks} chunks, id<{hi}, "
                  f"{time.monotonic() - started:.0f}s", flush=True)

    out_rows = [
        {"opening_source": k[0], "verdict": k[1], "band": k[2],
         "n": int(v[0]), "won": int(v[1]), "implied": round(v[2], 2)}
        for k, v in sorted(acc.items())
    ]
    out = {
        "cell": f"{args.source}/{args.category}",
        "high_band": HIGH_BAND,
        "elapsed_s": round(time.monotonic() - started, 1),
        "irreducible_chunks": irreducible,
        "rows": out_rows,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")

    print(f"\n{out['cell']}  {out['elapsed_s']}s  "
          f"irreducible={irreducible}")
    print(f"{'basis':>18} {'band':>5} {'n':>7} {'won':>6} {'implied':>9} "
          f"{'win%':>7} {'impl%':>7}")
    for scope in ("kept", "excluded"):
        print(f"-- {scope.upper()} (verdicts {'kept_*' if scope == 'kept' else 'x*'})")
        agg: dict[tuple[str, str], list[float]] = defaultdict(
            lambda: [0, 0, 0.0])
        for r in out_rows:
            is_kept = r["verdict"].startswith("kept")
            if is_kept != (scope == "kept"):
                continue
            cell = agg[(r["opening_source"], r["band"])]
            cell[0] += r["n"]
            cell[1] += r["won"]
            cell[2] += r["implied"]
        for (basis, band), (n, won, implied) in sorted(agg.items()):
            if not n:
                continue
            print(f"{basis:>18} {band:>5} {int(n):>7} {int(won):>6} "
                  f"{implied:>9.1f} {100.0 * won / n:>6.1f}% "
                  f"{100.0 * implied / n:>6.1f}%")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
