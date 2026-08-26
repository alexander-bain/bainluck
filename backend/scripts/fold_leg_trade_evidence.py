#!/usr/bin/env python3
"""Can a Polymarket Under/No leg ever look TRADED to the curve's own exclusions?

The twin of ``fold_leg_book_coverage.py``, and the one with teeth, because this
one is read by the published curve rather than by a forensic.

``app/tasks/precompute_calibration.py`` gates the Polymarket half of
``/api/calibration`` on snapshot evidence:

    POLY_PLACEHOLDER_EXCLUDE = vm.source = 'polymarket'
        AND COALESCE(cp, op) BETWEEN 0.45 AND 0.55
        AND NOT EXISTS (SELECT 1 FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = fo.id
                          AND (fos.yes_bid > 0 OR fos.last_price > 0))

    POLY_NEVER_TRADED = the same NOT EXISTS, unbanded, feeding the
        Queue #220/221 exclusion-symmetry census.

Both ask one question — *did this leg ever show a bid or a trade?* — of
``futures_odds_snapshots.yes_bid`` / ``last_price``. In
``app/tasks/polymarket.py`` the decomposed-pair path writes those two columns on
the **Over/Yes** snapshot and omits them from the **Under/No** snapshot, which
carries only ``probability``, ``american_odds`` and ``captured_at``.

If that omission is total, then ``NOT EXISTS`` is **unconditionally true for
every Under/No leg** and the two predicates above are not measuring liquidity on
that half of the population at all — they are re-reading a column the writer
never fills. A traded Under leg and a Gamma placeholder Under leg produce the
identical answer, which is gotcha #53 in the read direction: the emptier reading
of one response shape being taken for a fact about the world.

Two consequences, opposite in sign, and both follow from the same NEVER:

* ``POLY_PLACEHOLDER_EXCLUDE`` drops **every** Under/No leg priced in
  [0.45, 0.55] out of the published curve, including the ones whose market
  genuinely traded. A silent population loss, not a filter.
* ``is_poly_never_traded`` reports 100% never-traded for Under/No legs, so any
  exclusion-symmetry number computed from it is describing the writer.

``n_with_trade_evidence`` is the EXISTS the predicates run, counted rather than
negated, because a count of zero over the whole population is the only form of
this claim that cannot be a sampling accident.

Usage:
    python3 backend/scripts/fold_leg_trade_evidence.py --out artifacts/cal-p095 \\
        --label leg_trade_evidence
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

LEG_NAMES = ("over", "under", "yes", "no")

# Mirrors POLY_PLACEHOLDER_EXCLUDE's band verbatim. Restating it rather than
# importing keeps this script runnable without the app package's task imports,
# and the band is asserted against the constant in the test suite instead.
BAND_LO, BAND_HI = 0.45, 0.55


def evidence_sql() -> str:
    names = ", ".join(f"'{n}'" for n in LEG_NAMES)
    return f"""
SELECT lower(fo.name) AS leg,
       COUNT(*) AS n_legs,
       COUNT(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM futures_odds_snapshots fos
           WHERE fos.outcome_id = fo.id
             AND (fos.yes_bid > 0 OR fos.last_price > 0)
       )) AS n_trade_evidence,
       COUNT(*) FILTER (WHERE COALESCE(fo.calibration_probability,
                                       fo.opening_probability)
                              BETWEEN {BAND_LO} AND {BAND_HI}) AS n_band,
       COUNT(*) FILTER (WHERE COALESCE(fo.calibration_probability,
                                       fo.opening_probability)
                              BETWEEN {BAND_LO} AND {BAND_HI}
                          AND NOT EXISTS (
           SELECT 1 FROM futures_odds_snapshots fos
           WHERE fos.outcome_id = fo.id
             AND (fos.yes_bid > 0 OR fos.last_price > 0)
       )) AS n_placeholder_excluded
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
  AND fm.source = '{POPULATION_SOURCE}'
  AND lower(fo.name) IN ({names})
GROUP BY 1
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="leg_trade_evidence")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=2_000_000)
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    args = parser.parse_args()

    template = evidence_sql()
    acc: dict[str, dict] = {}
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
            for leg, n, n_ev, n_band, n_excl in result.get("rows") or []:
                slot = acc.setdefault(str(leg), {"n_legs": 0, "n_trade_evidence": 0,
                                                 "n_band": 0,
                                                 "n_placeholder_excluded": 0})
                slot["n_legs"] += int(n)
                slot["n_trade_evidence"] += int(n_ev or 0)
                slot["n_band"] += int(n_band or 0)
                slot["n_placeholder_excluded"] += int(n_excl or 0)
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

    complete = not irreducible
    out = {
        "label": args.label,
        "complete": complete,
        "measured": complete,
        "population": f"{POPULATION_SOURCE}, all statuses, outcome name in {LEG_NAMES}",
        "predicate": "EXISTS(futures_odds_snapshots WHERE yes_bid > 0 OR last_price > 0)"
                     f" — the exact test POLY_PLACEHOLDER_EXCLUDE negates, band "
                     f"[{BAND_LO}, {BAND_HI}]",
        "shard_count": len(shards),
        "shards": shards,
        "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "by_leg": acc,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.label}.json").write_text(json.dumps(out, indent=2))

    print(f"\nirreducible={len(irreducible)} complete={complete} "
          f"elapsed={out['elapsed_s']}s")
    print(f"\n{'leg':<6} {'n_legs':>9} {'traded':>9} {'traded%':>8} "
          f"{'in_band':>9} {'excluded':>9}")
    for leg in LEG_NAMES:
        v = acc.get(leg)
        if not v:
            continue
        n = v["n_legs"] or 1
        print(f"{leg:<6} {v['n_legs']:>9} {v['n_trade_evidence']:>9} "
              f"{v['n_trade_evidence']/n:>8.4f} {v['n_band']:>9} "
              f"{v['n_placeholder_excluded']:>9}")
    if not complete:
        print("\nINCOMPLETE — a partial count cannot prove a NEVER.")
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
