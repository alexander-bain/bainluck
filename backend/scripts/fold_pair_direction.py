#!/usr/bin/env python3
"""Which leg of an ``identical_noncomp`` pair held the REAL price?

This fold exists to decide a disposition, not to describe a population. The
CAL-P094 directive permits a ``1 - p`` repair of the corrupted openings "ONLY
where the pair relationship is structurally certain". The pair *relationship* is
certain — a two-leg Over/Under market is mutually exclusive and exhaustive, and
the healthy ``complementary`` class averages a sum of 1.0000 across 339,587
markets. What is NOT certain is the repair's DIRECTION.

``identical_noncomp`` means both legs carry the same opening ``p``. The named
mechanism says the Over leg's price is the source-resolved one and it was copied
onto the Under leg, so the repair would be ``under := 1 - p``. But if the
corruption ran the other way — or if ``p`` is not a real price for either leg —
then repairing in the named direction DOUBLES the error instead of removing it,
and it does so invisibly, because an invented opening is indistinguishable from a
quote afterwards.

The direction is testable. If ``p`` is a real Over price, the Over leg must win
at a rate near ``p`` and the Under leg near ``1 - p``. If ``p`` is real for
neither leg, both win near 0.5 regardless of ``p``. Those two worlds are
distinguishable in one query, and they recommend opposite dispositions:

    Over wins ~ p          -> repair is directionally proven; propose it
    both win ~ 0.5         -> p carries no information; exclusion only

Note what does NOT test this. "Half the legs win" is true by construction for any
one-winner two-leg market and says nothing about ``p``; the census already shows
``winning_legs`` exactly equal to markets for every eligible class. The
discriminating quantity is the win rate of the NAMED leg AS A FUNCTION OF ``p``.

Truth-eligible legs only, so the answer speaks about the published curve.

Usage:
    python3 backend/scripts/fold_pair_direction.py --out artifacts/cal-p094 \
        --label pair_direction
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
)

TOL = PAIR_SUM_TOLERANCE


def direction_sql() -> str:
    types = ", ".join(f"'{t}'" for t in POPULATION_MARKET_TYPES)
    return f"""
WITH legs AS (
  SELECT fo.market_id,
         lower(fo.name) AS leg,
         fo.is_winner,
         fo.opening_probability AS op,
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
    AND fm.market_type IN ({types})
  WINDOW w AS (PARTITION BY fo.market_id)
)
SELECT leg,
       LEAST(FLOOR(op * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(op) AS sum_op,
       SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS wins
FROM legs
WHERE n_legs = 2 AND n_over = 1 AND n_under = 1
  AND n_open = 2
  AND min_open = max_open
  AND ABS(sum_open - 1) > {TOL}
  AND n_win = 1
  AND rsrc IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
  AND op > 0 AND op < 1
  AND is_winner IS NOT NULL
GROUP BY 1, 2
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="pair_direction")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    template = direction_sql()
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
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded", flush=True)
                continue
            for leg, b, n, sum_op, wins in result.get("rows") or []:
                slot = acc.setdefault((leg, int(b)), {"n": 0, "sum_op": 0.0, "wins": 0})
                slot["n"] += int(n)
                slot["sum_op"] += float(sum_op or 0)
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
        sum_op = sum(b["sum_op"] for b in bins)
        summary[leg] = {
            "n": n, "wins": wins,
            "mean_p": round(sum_op / n, 4) if n else None,
            "win_rate": round(wins / n, 4) if n else None,
            "bins": bins,
        }

    complete = not irreducible
    out = {
        "label": args.label, "complete": complete, "measured": complete,
        "tolerance": TOL,
        "population": "polymarket/resolved, 2-leg over+under, both openings present "
                      "and IDENTICAL, pair sum outside tolerance, exactly one winner, "
                      "truth-eligible legs only",
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
        print(f"\n{leg}: n={s['n']} mean_p={s['mean_p']} win_rate={s['win_rate']}")
        print(f"   {'bin':>4} {'n':>6} {'mean_p':>8} {'win_rate':>9} {'verdict':>10}")
        for b in s["bins"]:
            mp = b["sum_op"] / b["n"]
            wr = b["wins"] / b["n"]
            print(f"   {b['bin']:>4} {b['n']:>6} {mp:>8.4f} {wr:>9.4f}"
                  f" {'~p' if abs(wr - mp) < abs(wr - 0.5) else '~0.5':>10}")
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
