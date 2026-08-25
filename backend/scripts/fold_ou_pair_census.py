#!/usr/bin/env python3
"""Census the Polymarket Over/Under opening-price pair shape, in id-range shards.

THE DEFECT THIS COUNTS. ``artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md`` check 3
found two-leg Over/Under markets whose two legs carry an IDENTICAL
``opening_probability`` instead of complementary ones — the Over price written
onto the Under leg (specimen: ``Purdue/UCLA O/U 143.5``, Over 0.040 / Under
0.040, Under wins). ``calibration_probability`` falls back to
``opening_probability`` when no snapshot exists, so an ~82%-winrate Under leg
prices at ~1% and the cell's ECE inherits the whole error.

WHAT THE SPLIT IS FOR. A count of corrupted rows answers nothing on its own: a
writer defect and a historical scar produce the SAME total. The
``post_writer_fix`` flag is the second signal that tells them apart (gotcha #53).
``231e39c3`` (2026-07-08, "#137 calibration regrade pack: poly Under sign-flip")
changed ``poll_polymarket_markets`` to open the Under leg at ``under_prob``
instead of the Over's ``sub_opening``. If non-complementary identical pairs keep
appearing with openings captured AFTER that date, a writer is still producing
them and the fix is at ingestion. If they stop dead at the boundary, the writer
is already fixed and what remains is a scar plus the absence of a guard.

CLASSES (mutually exclusive, one per market):
  ``complementary``       both legs open, |sum - 1| <= TOL — healthy
  ``identical_noncomp``   both legs open, equal, and |2p - 1| > TOL — THE DEFECT
  ``other_noncomp``       both legs open, unequal, |sum - 1| > TOL — a different
                          defect and deliberately NOT merged with the one above
  ``partial_open``        fewer than two legs carry an opening at all
An equal pair at p = 0.5 is complementary and correct; it is NOT the defect, and
folding it in by matching on "both legs equal" alone would inflate the census
with the one case the writer gets right by coincidence.

Usage:
    python3 backend/scripts/fold_ou_pair_census.py --out artifacts/cal-p094 \\
        --label ou_pair_census [--league baseball --market-type quantity]
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

from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE  # noqa: E402

from dbq_probe import run as dbq_run  # noqa: E402

#: Imported, never restated. The writer's gate
#: (``app/utils/pair_opening_coherence.py``) and this census must classify the
#: same population, or the guard disagrees with the measurement that justified it.
TOL = PAIR_SUM_TOLERANCE

#: The commit that fixed the Under-side opening in ``tasks/polymarket.py``.
#: Openings captured before this are scar; after it, a live writer.
WRITER_FIX_DATE = "2026-07-08"

BISECT_FLOOR_IDS = 25


def census_sql(league: str | None, market_type: str | None) -> str:
    extra = ""
    if league:
        extra += f"\n  AND fm.llm_sport_category = '{league}'"
    if market_type:
        extra += f"\n  AND fm.market_type = '{market_type}'"
    return f"""
WITH legs AS (
  SELECT fo.market_id,
         COUNT(*) AS n_legs,
         COUNT(*) FILTER (WHERE lower(fo.name) = 'over')  AS n_over,
         COUNT(*) FILTER (WHERE lower(fo.name) = 'under') AS n_under,
         COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL) AS n_open,
         COUNT(*) FILTER (WHERE fo.calibration_probability IS NOT NULL) AS n_calib,
         COUNT(*) FILTER (WHERE fo.is_winner) AS n_win,
         COUNT(*) FILTER (WHERE fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}) AS n_elig,
         MIN(fo.opening_probability) AS min_open,
         MAX(fo.opening_probability) AS max_open,
         SUM(fo.opening_probability) AS sum_open,
         MAX(fo.opening_captured_at) AS last_open_at
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
    AND fm.source = 'polymarket'
    AND fm.status = 'resolved'
    AND fm.market_type IN ('quantity', 'container_member'){extra}
  GROUP BY 1
), classed AS (
  SELECT (n_legs = 2 AND n_over = 1 AND n_under = 1) AS ou_pair,
         CASE
           WHEN n_open < 2 THEN 'partial_open'
           WHEN ABS(sum_open - 1) <= {TOL} THEN 'complementary'
           WHEN min_open = max_open THEN 'identical_noncomp'
           ELSE 'other_noncomp'
         END AS open_class,
         n_calib,
         (n_elig > 0) AS has_eligible,
         (last_open_at >= TIMESTAMPTZ '{WRITER_FIX_DATE}') AS post_writer_fix,
         n_win,
         sum_open
  FROM legs
  WHERE n_legs = 2
)
SELECT ou_pair, open_class, n_calib, has_eligible, post_writer_fix,
       COUNT(*) AS markets,
       SUM(n_win) AS winning_legs,
       ROUND(AVG(sum_open)::numeric, 4) AS avg_sum_open
FROM classed
GROUP BY 1, 2, 3, 4, 5
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="ou_pair_census")
    parser.add_argument("--league")
    parser.add_argument("--market-type")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=2_000_000)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    template = census_sql(args.league, args.market_type)
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
            rows = result.get("rows") or []
            if result.get("truncated"):
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded")
                continue
            for ou, cls, n_calib, has_elig, post_fix, markets, wins, avg_sum in rows:
                key = (bool(ou), cls, int(n_calib), bool(has_elig), bool(post_fix))
                slot = acc.setdefault(key, {"markets": 0, "winning_legs": 0, "sum_open_acc": 0.0})
                slot["markets"] += int(markets)
                slot["winning_legs"] += int(wins or 0)
                slot["sum_open_acc"] += float(avg_sum or 0) * int(markets)
            shards.append({"lo": lo, "hi": hi, "rows": len(rows),
                           "duration_ms": result.get("duration_ms"),
                           "sql_fingerprint": result.get("sql_fingerprint")})
            print(f"  [{lo}..{hi}) ok rows={len(rows)} {result.get('duration_ms')}ms "
                  f"fp={result.get('sql_fingerprint')}")
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

    rows_out = []
    for (ou, cls, n_calib, has_elig, post_fix), v in sorted(
        acc.items(), key=lambda kv: -kv[1]["markets"]
    ):
        rows_out.append({
            "ou_pair": ou, "open_class": cls, "n_calib": n_calib,
            "has_eligible": has_elig, "post_writer_fix": post_fix,
            "markets": v["markets"], "winning_legs": v["winning_legs"],
            "avg_sum_open": round(v["sum_open_acc"] / v["markets"], 4) if v["markets"] else None,
        })

    complete = not irreducible
    out = {
        "label": args.label,
        "complete": complete,
        "measured": complete,
        "scope": {"league": args.league, "market_type": args.market_type,
                  "source": "polymarket", "status": "resolved",
                  "market_type_in": ["quantity", "container_member"],
                  "two_leg_markets_only": True},
        "tolerance": TOL,
        "writer_fix_date": WRITER_FIX_DATE,
        "writer_fix_commit": "231e39c3",
        "shard_count": len(shards),
        "shards": shards,
        "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "rows": rows_out,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.label}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {path} shards={len(shards)} irreducible={len(irreducible)} "
          f"complete={complete} elapsed={out['elapsed_s']}s")
    print(f"{'ou':>5} {'class':>18} {'ncal':>4} {'elig':>5} {'post':>5} "
          f"{'markets':>8} {'winlegs':>8} {'avgsum':>7}")
    for r in rows_out:
        print(f"{str(r['ou_pair']):>5} {r['open_class']:>18} {r['n_calib']:>4} "
              f"{str(r['has_eligible']):>5} {str(r['post_writer_fix']):>5} "
              f"{r['markets']:>8} {r['winning_legs']:>8} {str(r['avg_sum_open']):>7}")
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
