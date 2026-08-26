#!/usr/bin/env python3
"""Does the Under/No leg of a Polymarket pair have a book, or does nobody write one?

CAL-P094 attributed ``baseball/quantity``'s exact-0.5000 spike with
``fold_spike_provenance.py`` and recorded its largest verdict as a fact about the
market:

    ``no_book`` 924 (all Under, zero bid, zero ask) ... **every one of the 924
    no_book legs is an UNDER leg with no book at all, and that is not a
    stale-book artifact: a leg that never had a book never had one.**

CAL-P095 reproduced the same shape in ``soccer/quantity`` (992 legs, again all
Under, again zero bid and zero ask) and then read the writer. In
``app/tasks/polymarket.py`` the decomposed-pair path writes
``current_yes_bid`` / ``current_yes_ask`` on the **Over** upsert and on nothing
else: neither the Under ``pg_insert`` values nor its ``on_conflict_do_update``
set clause mentions either column. The Under leg's book is NULL because **no
code path has ever written it**, for any market, at any price.

So ``no_book`` is a fact about the WRITER, not about the market, and the
inference it carried does not survive: an absent column read as an absent book
is gotcha #53 exactly — the emptier reading of one response shape treated as a
finding. This fold is the disambiguating second signal that gotcha asks for.

**The predicate is the point, not the count.** If Under legs carry a book
sometimes, the CAL-P094 reading stands and the 924 really were untraded. If they
carry one *never*, then every book-based phantom predicate is structurally blind
on 100% of Polymarket Under legs — which is the measured reason
``is_fabricated_midpoint`` claims only 6.6% (baseball) / 7.8% (soccer) of a spike
whose Under half is exactly half the mass.

Counts are ``COUNT(<col>)``, which counts non-NULLs, against ``COUNT(*)``. A leg
class whose ``n_bid`` and ``n_ask`` are both 0 over the whole population is not a
sampling accident.

Usage:
    python3 backend/scripts/fold_leg_book_coverage.py --out artifacts/cal-p095 \\
        --label leg_book_coverage
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dbq_probe import run as dbq_run  # noqa: E402
from fold_cohort_cell_eligible import (  # noqa: E402
    BISECT_FLOOR_IDS,
    POPULATION_SOURCE,
)

# The two leg names the decomposed-pair writer emits, and their partners. The
# writer picks "Over"/"Under" for o/u sub-markets and "Yes"/"No" otherwise, from
# the SAME code path — so both pairs must show the same asymmetry, or the finding
# is about one naming branch rather than about the writer.
LEG_NAMES = ("over", "under", "yes", "no")


def coverage_sql() -> str:
    names = ", ".join(f"'{n}'" for n in LEG_NAMES)
    return f"""
SELECT lower(fo.name) AS leg,
       fm.status AS status,
       COUNT(*) AS n,
       COUNT(fo.current_yes_bid) AS n_bid,
       COUNT(fo.current_yes_ask) AS n_ask,
       COUNT(fo.opening_probability) AS n_open
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
  AND fm.source = '{POPULATION_SOURCE}'
  AND lower(fo.name) IN ({names})
GROUP BY 1, 2
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="leg_book_coverage")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    args = parser.parse_args()

    template = coverage_sql()
    acc: dict[tuple[str, str], dict] = {}
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
            for leg, status, n, n_bid, n_ask, n_open in result.get("rows") or []:
                slot = acc.setdefault(
                    (str(leg), str(status)),
                    {"n": 0, "n_bid": 0, "n_ask": 0, "n_open": 0},
                )
                slot["n"] += int(n)
                slot["n_bid"] += int(n_bid or 0)
                slot["n_ask"] += int(n_ask or 0)
                slot["n_open"] += int(n_open or 0)
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

    by_leg: dict[str, dict] = {}
    for (leg, status), v in acc.items():
        slot = by_leg.setdefault(leg, {"n": 0, "n_bid": 0, "n_ask": 0, "n_open": 0,
                                       "by_status": {}})
        for k in ("n", "n_bid", "n_ask", "n_open"):
            slot[k] += v[k]
        slot["by_status"][status] = dict(v)

    complete = not irreducible
    out = {
        "label": args.label,
        "complete": complete,
        "measured": complete,
        "population": f"{POPULATION_SOURCE}, all statuses, outcome name in {LEG_NAMES}",
        "book_columns": "futures_outcomes.current_yes_bid / current_yes_ask",
        "shard_count": len(shards),
        "shards": shards,
        "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "by_leg": by_leg,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.label}.json").write_text(json.dumps(out, indent=2))

    print(f"\nirreducible={len(irreducible)} complete={complete} "
          f"elapsed={out['elapsed_s']}s")
    print(f"\n{'leg':<6} {'n':>9} {'n_bid':>9} {'bid%':>7} {'n_ask':>9} {'ask%':>7} "
          f"{'n_open':>9}")
    for leg in LEG_NAMES:
        v = by_leg.get(leg)
        if not v:
            continue
        n = v["n"] or 1
        print(f"{leg:<6} {v['n']:>9} {v['n_bid']:>9} {v['n_bid']/n:>7.4f} "
              f"{v['n_ask']:>9} {v['n_ask']/n:>7.4f} {v['n_open']:>9}")
    if not complete:
        print("\nINCOMPLETE — a partial coverage count cannot prove a NEVER.")
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
