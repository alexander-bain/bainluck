#!/usr/bin/env python3
"""Is the exact-0.5000 spike the KNOWN #1578 phantom, or a new defect?

``fold_coinflip_default.py`` found the spike and proved it is a spike:
``baseball/quantity``'s coherent truth-eligible class carries **1,826 legs at
exactly 0.5000** (37.45% of the class, a 17x cliff over the next distinct value
at n=52), and those legs win **97.62% Under / 2.44% Over**. A price quoted at one
single value against a 97/3 outcome is not a market price.

But "not a market price" does not yet say WHICH defect, and the answer decides
who owns the fix:

* If the spike satisfies :func:`is_fabricated_midpoint` — a book at least
  ``FEED_PHANTOM_MIN_SPREAD`` (0.20) wide whose midpoint IS the stored price —
  then this is the already-named **#1578 / #151 fabricated-midpoint class**. Its
  forward writer guard SHIPPED (``_resolve_market_probability_with_source``
  declines it, and the docstring records the census: 179,888 outcomes, the 1,580
  graded ones winning 0.13% while asserting 50%). Nothing new needs building.
  What is owed is the **historical exclusion that was deferred** — the same
  shape as the Kalshi wide-spread capture, where the forward guard shipped and
  the historical rows were left on the curve.
* If it does NOT satisfy the predicate, this is a NEW writer path producing 0.50
  placeholders that the shipped guard does not catch, and it needs its own fix.

Reporting it as "a 0.50 placeholder class" without settling that is the expensive
mistake, because it reads as new work and would get a second guard built beside a
working one.

Two honest limits, stated because they bound the claim rather than decorate it:

1. ``current_yes_bid`` / ``current_yes_ask`` are CURRENT columns on a market that
   has since resolved. They are the book as the poller last saw it, not the book
   at capture time. So a match is evidence the row belongs to the phantom class;
   a non-match is NOT proof it does not, because the book may have been
   overwritten after capture. The asymmetry runs one way and is not symmetric
   evidence.
2. Both sides NULL returns False from the predicate by design (no order book at
   all = a model price, not a phantom). Those legs are counted separately as
   ``no_book`` rather than folded into either verdict, because "the predicate
   says no" and "the predicate does not apply" are different answers and
   collapsing them would manufacture a clean negative.

Usage:
    python3 backend/scripts/fold_spike_provenance.py --league baseball \\
        --market-type quantity --out artifacts/cal-p094 --label spike_prov_bbq
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.feed_market_quality import FEED_PHANTOM_MIN_SPREAD  # noqa: E402
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
#: Mirrors ``_PHANTOM_MIDPOINT_TOLERANCE``, which is module-private. Asserted
#: equal at import so a change there fails here loudly instead of silently
#: measuring a different predicate than production applies.
MIDPOINT_TOL = 0.0005


def _assert_tolerance_matches() -> None:
    from app.utils import feed_market_quality as fmq

    live = getattr(fmq, "_PHANTOM_MIDPOINT_TOLERANCE", None)
    if live is not None and abs(float(live) - MIDPOINT_TOL) > 1e-12:
        raise SystemExit(
            f"_PHANTOM_MIDPOINT_TOLERANCE is {live}, this fold hard-codes "
            f"{MIDPOINT_TOL}. Update the constant — a fold that measures a "
            f"different predicate than production applies proves nothing."
        )


def provenance_sql(league: str, market_type: str) -> str:
    return f"""
WITH legs AS (
  SELECT lower(fo.name) AS leg,
         fo.is_winner,
         fo.opening_probability AS op,
         fo.current_yes_bid AS bid,
         fo.current_yes_ask AS ask,
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
       CASE
         WHEN bid IS NULL AND ask IS NULL THEN 'no_book'
         WHEN (COALESCE(ask, 1.0) - COALESCE(bid, 0.0)) < {FEED_PHANTOM_MIN_SPREAD}
              THEN 'tight_book'
         WHEN ABS(op - (COALESCE(bid, 0.0) + COALESCE(ask, 1.0)) / 2)
              < {MIDPOINT_TOL} THEN 'fabricated_midpoint'
         ELSE 'wide_book_not_midpoint'
       END AS verdict,
       COUNT(*) AS n,
       SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS wins,
       COUNT(bid) AS n_bid,
       COUNT(ask) AS n_ask
FROM legs
WHERE n_legs = 2 AND n_over = 1 AND n_under = 1
  AND n_open = 2
  AND ABS(sum_open - 1) <= {TOL}
  AND n_win = 1
  AND rsrc IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
  AND ROUND(op, 4) = 0.5000
  AND is_winner IS NOT NULL
GROUP BY 1, 2
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", required=True)
    parser.add_argument("--market-type", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="spike_provenance")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    _assert_tolerance_matches()

    template = provenance_sql(args.league, args.market_type)
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
            for leg, verdict, n, wins, n_bid, n_ask in result.get("rows") or []:
                slot = acc.setdefault((leg, verdict),
                                      {"n": 0, "wins": 0, "n_bid": 0, "n_ask": 0})
                slot["n"] += int(n)
                slot["wins"] += int(wins or 0)
                slot["n_bid"] += int(n_bid or 0)
                slot["n_ask"] += int(n_ask or 0)
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
    by_verdict: dict[str, dict] = {}
    for (leg, verdict), v in acc.items():
        slot = by_verdict.setdefault(verdict, {"n": 0, "wins": 0, "legs": {}})
        slot["n"] += v["n"]
        slot["wins"] += v["wins"]
        slot["legs"][leg] = v

    complete = not irreducible
    out = {
        "label": args.label, "league": args.league, "market_type": args.market_type,
        "complete": complete, "measured": complete,
        "predicate": {"min_spread": FEED_PHANTOM_MIN_SPREAD,
                      "midpoint_tolerance": MIDPOINT_TOL,
                      "book_columns": "current_yes_bid / current_yes_ask "
                                      "(CURRENT, not as-of-capture — see docstring)"},
        "population": f"{POPULATION_SOURCE}/{POPULATION_STATUS}, "
                      f"{args.league}/{args.market_type}, coherent 2-leg over+under, "
                      "one winner, truth-eligible, opening_probability = 0.5000 exactly",
        "total_spike_legs": total, "by_verdict": by_verdict,
        "shard_count": len(shards), "shards": shards, "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.label}.json").write_text(json.dumps(out, indent=2))

    print(f"\nirreducible={len(irreducible)} complete={complete} "
          f"elapsed={out['elapsed_s']}s")
    print(f"exact-0.5000 spike legs folded: {total}")
    print(f"\n{'verdict':<24} {'n':>6} {'share':>7} {'win_rate':>9}")
    for verdict, v in sorted(by_verdict.items(), key=lambda kv: -kv[1]["n"]):
        share = v["n"] / total if total else 0
        wr = v["wins"] / v["n"] if v["n"] else 0
        print(f"{verdict:<24} {v['n']:>6} {share:>7.3f} {wr:>9.4f}")
        for leg, lv in sorted(v["legs"].items()):
            lwr = lv["wins"] / lv["n"] if lv["n"] else 0
            print(f"   {leg:<21} {lv['n']:>6} {'':>7} {lwr:>9.4f}"
                  f"   bid_present={lv['n_bid']} ask_present={lv['n_ask']}")
    if not complete:
        print("\nINCOMPLETE — a partial attribution is not an attribution.")
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
