#!/usr/bin/env python3
"""Derive the immutable, content-addressed pair-opening repair plan.

CERT-403A P1#1's fix-sketch, which this script is written to satisfy literally:

    "derive an immutable plan containing every outcome ID, market ID, old/new
     opening probability, old/new-or-null American odds, and provenance
     representation; hash the complete semantic content; consume only plan rows
     with per-row CAS and named refusals; persist before-images and after-read
     the receipt."

This is the DERIVE half. It reads production, freezes the reviewed row set, and
writes one artifact whose address is the promise that what the reviewer read is
what an apply may write. The CONSUME half is
``app.utils.repair_apply_plan.pair_opening_repair_gate`` plus a plan-bound
repair; neither can act on a row this artifact does not name.

THE SCOPE PREDICATE IS THE STAGED SPEC'S, ALL OF IT, WITH NO LOOSENING
-----------------------------------------------------------------------
    source='polymarket' AND status='resolved'
    AND market_type IN ('quantity','container_member')
    AND exactly 2 legs
    AND exactly one named 'over' and one named 'under'
    AND both opening_probability present
    AND min = max                       (the identical-copy signature)
    AND ABS(sum - 1) > PAIR_SUM_TOLERANCE
    AND exactly one winner in the pair

``PAIR_SUM_TOLERANCE`` is imported from ``app.utils.pair_opening_coherence``,
never restated — the writer gate, the read-side exclusion and this deriver must
classify with one constant or the plan disagrees with the census that justified
it. The disposition arm this predicate selects is ``repairable_named_ou`` in
``fold_pair_disposition.py``, which measured **823** truth-eligible markets:
exactly the population CERT-403A said the direction evidence covers, and 1,006
fewer than the "~1,829 eligible markets" the staged spec priced the run at.

⚠️ READ BEFORE APPROVING ANYTHING THIS SCRIPT EMITS
----------------------------------------------------
CAL-P097 measured what the repair is worth through the price the curve actually
reads, and it is not what the staged spec claims:

* **815 of 823 (99.0%)** eligible Under legs already carry a
  ``calibration_probability``.
* The published curve reads
  ``COALESCE(calibration_probability, opening_probability)``.
* This apply writes ``opening_probability``.

So on 99% of its own population the repair changes a stored column that the
curve does not read. Measured per cell through the real coalesce
(``artifacts/cal-p097/pair_disposition.json``): ``baseball/quantity`` 25.59 ->
25.09, ``soccer/quantity`` 21.39 -> 21.19, ``basketball/quantity`` and
``tennis/quantity`` **unchanged**. The staged spec's headline 18.92 -> 5.62 is
computed on the opening column alone and does not survive the coalesce.

The repair is still CORRECT — a stored opening that is a copy of the other leg's
price is wrong whether or not anything reads it, and repairing it is what lets
the row stop being excluded later. It is simply worth far less, right now, than
the number on record. Whether it runs at all is Alex's call. This script does
not run it; ``--emit-plan`` only writes an artifact.

Usage:
    python3 backend/scripts/derive_pair_opening_repair_plan.py \\
        --out artifacts/cal-p097 --eligible-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.odds_math import probability_to_american  # noqa: E402
from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE  # noqa: E402
from app.utils.repair_apply_plan import (  # noqa: E402
    PAIR_OPENING_REPAIR_SOURCE,
    PlannedPairOpeningRepair,
    build_pair_opening_repair_plan,
    decode_pair_opening_repair_plan,
)
from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL,
)

from dbq_probe import run as dbq_run  # noqa: E402
from fold_cohort_cell_eligible import BISECT_FLOOR_IDS  # noqa: E402

TOL = PAIR_SUM_TOLERANCE


def rows_sql(eligible_only: bool) -> str:
    """One row per repairable Under leg, carrying its own before-image.

    The Over leg's id and opening travel with it because ``after_opening`` is
    defined as ``1 - over_opening``: the plan has to carry the value its own
    arithmetic depends on, or an artifact edited between review and apply would
    keep its approved address while meaning something else.
    """
    elig = (
        f"AND u.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}"
        if eligible_only
        else ""
    )
    return f"""
WITH shape AS (
  SELECT fo.market_id,
         COUNT(*) AS n_legs,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'over')  AS n_over,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'under') AS n_under,
         COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL) AS n_open,
         COUNT(*) FILTER (WHERE fo.is_winner) AS n_win,
         MIN(fo.opening_probability) AS min_open,
         MAX(fo.opening_probability) AS max_open,
         SUM(fo.opening_probability) AS sum_open
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
    AND fm.source = 'polymarket'
    AND fm.status = 'resolved'
    AND fm.market_type IN ('quantity', 'container_member')
  GROUP BY 1
), repairable AS (
  SELECT market_id FROM shape
  WHERE n_legs = 2 AND n_over = 1 AND n_under = 1 AND n_open = 2
    AND n_win = 1
    AND min_open = max_open
    AND ABS(sum_open - 1) > {TOL}
)
SELECT u.id            AS under_outcome_id,
       r.market_id     AS market_id,
       u.opening_probability   AS before_opening,
       u.opening_american_odds AS before_american,
       u.opening_source        AS before_source,
       o.id            AS over_outcome_id,
       o.opening_probability   AS over_opening,
       fm.name         AS market_name
FROM repairable r
JOIN futures_markets fm ON fm.id = r.market_id
JOIN futures_outcomes u ON u.market_id = r.market_id
     AND lower(btrim(u.name)) = 'under'
JOIN futures_outcomes o ON o.market_id = r.market_id
     AND lower(btrim(o.name)) = 'over'
WHERE TRUE {elig}
ORDER BY u.id
""".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="pair_opening_repair_plan")
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=1_000_000)
    parser.add_argument(
        "--eligible-only",
        action="store_true",
        help="restrict to truth-eligible Under legs (the 823 the direction "
             "evidence covers). Without it the plan spans the whole 7,155-market "
             "class, which NO measurement licenses.",
    )
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    template = rows_sql(args.eligible_only)

    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.chunk, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()

    started = time.monotonic()
    raw_rows: list[tuple] = []
    shards: list[dict] = []
    irreducible: list[dict] = []

    while stack:
        lo, hi = stack.pop()
        result = dbq_run(template.format(lo=lo, hi=hi), timeout_ms=args.timeout_ms)
        if result.get("status") == "ok":
            if result.get("truncated"):
                # A silently truncated shard is a plan that quietly omits rows
                # the reviewer would have approved. Never folded.
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded", flush=True)
                continue
            got = result.get("rows") or []
            raw_rows.extend(got)
            shards.append({"lo": lo, "hi": hi, "rows": len(got),
                           "duration_ms": result.get("duration_ms"),
                           "sql_fingerprint": result.get("sql_fingerprint")})
            if got:
                print(f"  [{lo}..{hi}) ok {result.get('duration_ms')}ms "
                      f"+{len(got)}", flush=True)
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

    elapsed = round(time.monotonic() - started, 1)

    planned: list[PlannedPairOpeningRepair] = []
    skipped: list[dict] = []
    for (under_id, market_id, before_open, before_am, before_src,
         over_id, over_open, market_name) in raw_rows:
        over_open = float(over_open)
        # ROUNDED TO THE COLUMN'S OWN SCALE, and this is not cosmetic.
        # ``opening_probability`` is ``Numeric(7, 6)``. Plain ``1.0 - 0.32`` is
        # 0.6799999999999999 in binary float, which the column would store as
        # 0.680000 anyway — but ``probability_to_american`` sees the unrounded
        # value first and returns -212 where the true complement gives -213.
        # Caught on the first derivation: 11 of 823 rows disagreed with the
        # American odds ALREADY STORED on the row, every one of them by exactly
        # one, and the stored value was right. A plan is a promise about exact
        # values, so the arithmetic has to land on the grid the column uses.
        after_open = round(1.0 - over_open, 6)
        if not (0.0 < after_open < 1.0) or abs(after_open - float(before_open)) < 1e-9:
            # The 0.5000 pair, or a degenerate leg. Not repairable by complement
            # — its complement is itself — and the plan refuses such rows at
            # decode anyway. Recorded rather than dropped silently.
            skipped.append({
                "outcome_id": int(under_id),
                "reason": "complement_is_a_no_op_or_out_of_range",
                "before_opening": float(before_open),
                "over_opening": over_open,
            })
            continue
        planned.append(
            PlannedPairOpeningRepair(
                outcome_id=int(under_id),
                market_id=int(market_id),
                expected_before_opening=float(before_open),
                expected_before_american=(
                    None if before_am is None else int(before_am)
                ),
                expected_before_source=before_src,
                after_opening=after_open,
                # DECISION: the odds move with the probability. Recomputed by
                # the same function every other row's odds came from, so the
                # repaired row is self-consistent rather than uniquely odd.
                after_american=probability_to_american(after_open),
                over_outcome_id=int(over_id),
                over_opening=over_open,
                market_name=market_name,
            )
        )

    plan = build_pair_opening_repair_plan(
        planned,
        context={
            "derived_by": "CAL-P097 derive_pair_opening_repair_plan.py",
            "eligible_only": args.eligible_only,
            "pair_sum_tolerance": TOL,
            "provenance_stamp": PAIR_OPENING_REPAIR_SOURCE,
            "american_odds_treatment": "recomputed from the repaired probability",
            "complete": not irreducible,
            "worth_warning": (
                "815/823 eligible Under legs already carry a "
                "calibration_probability, and the curve reads COALESCE(cp, "
                "opening). Measured per cell this apply moves baseball/quantity "
                "25.59 -> 25.09 and leaves basketball and tennis unchanged. It "
                "is NOT the 18.92 -> 5.62 on record."
            ),
        },
    )

    payload = plan.as_payload()
    # Re-decode our own artifact before writing it. A plan that cannot survive
    # its own loader is not a plan, and finding that out at the attended apply
    # is finding out at the worst possible moment.
    decoded, reason = decode_pair_opening_repair_plan(payload)
    payload["self_decode"] = {"ok": decoded is not None, "reason": reason}
    payload["derivation"] = {
        "elapsed_s": elapsed,
        "shards": shards,
        "irreducible": irreducible,
        "rows_read": len(raw_rows),
        "rows_skipped": skipped,
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.label}.json"
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"\n=== {args.label} — {elapsed}s, {len(shards)} shards, "
          f"{len(irreducible)} irreducible ===")
    print(f"rows read      : {len(raw_rows)}")
    print(f"rows planned   : {payload['row_count']}  over {payload['market_count']} markets")
    print(f"rows skipped   : {len(skipped)}")
    print(f"plan_hash      : {payload['plan_hash']}")
    print(f"self-decode    : {payload['self_decode']}")
    print(f"wrote {out_path}")
    return 0 if (not irreducible and decoded is not None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
