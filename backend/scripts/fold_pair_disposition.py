#!/usr/bin/env python3
"""Bind every corrupted pair market to EXACTLY ONE disposition, and price each one.

CERT-403A's second P1, quoted because this script is written to its shape:

    "The advertised 1,829-market repair population does not reconcile with the
     named-leg predicate or its direction evidence ... only 823 are ou_pair=true;
     1,006 are outside the repair predicate. The same spec nevertheless prices the
     attended run as '~1,829 eligible markets'."
    fix-sketch: "split the disposition table into repairable_named_ou=823,
     nonrepairable_identical=1006, and other_noncomp=619; bind each ID to exactly
     one disposition and publish per-disposition expected cell deltas."

WHY THE OLD CENSUS COULD NOT SEE THIS
-------------------------------------
``fold_ou_pair_census.py`` cross-tabs ``ou_pair`` × ``open_class`` — both facts
are in the artifact, and both are correct. What it never produces is a single
column a market has exactly ONE value of. So the staged spec could quote the
``identical_noncomp`` row (1,829 truth-eligible) as the repair population while
its direction evidence covered only the ``ou_pair = true`` slice of that row
(823), and nothing in the artifact's own shape contradicted it. A cross-tab
invites you to read one margin and cite the other.

Here ``disposition`` is a single ``CASE``. The arms are ordered and exhaustive,
so a market lands in exactly one and the counts add to the population by
construction — you cannot quote two of these numbers about the same rows.

THE THIRD MEASUREMENT THIS FOLD ADDS, WHICH NEITHER SIDE HAS TAKEN
------------------------------------------------------------------
The repair writes ``opening_probability`` on the Under leg. The published curve
reads ``COALESCE(calibration_probability, opening_probability)`` — a coalesce,
not an exclusion (gotcha #144 / ruling 103 exist because that fallback was
invisible once already). So on any Under leg that HAS a
``calibration_probability``, the repair changes a stored column and moves the
published number **not at all**.

The staged spec's headline "repaired ECE 5.62 vs as-is 18.92" is computed over
the opening, so it silently assumes the opening IS the curve price for these
rows. That assumption is measurable and has never been measured. This fold
reports ``under_legs_with_cp`` per disposition, which is the count that decides
whether the apply is worth running at all — and it reports the repaired ECE
through the real ``COALESCE``, not through the opening alone.

TWO PASSES
----------
* ``binding`` — every market bound to one disposition, per cell, with leg counts
  and the ``calibration_probability`` coverage above. This is the reconciliation
  CERT-403A asked for.
* ``deltas``  — per-disposition expected cell deltas: ECE bins per cell per
  disposition under two treatments (``as_is`` and ``repaired``), restricted to
  the named cells so the row count stays under the ``db-query`` 1,000-row cap.
  A silently truncated shard is recorded as irreducible, never folded.

Usage:
    python3 backend/scripts/fold_pair_disposition.py --out artifacts/cal-p097
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
    ece_from_bins,
    gap_from_bins,
)

#: Imported, never restated — the writer gate, the read-side exclusion and this
#: measurement must all classify with one constant or the guard disagrees with
#: the census that justified it.
TOL = PAIR_SUM_TOLERANCE

#: The cells the staged spec's §0 table prices. ``deltas`` is restricted to
#: these so the shard row count stays well under the 1,000-row cap; ``binding``
#: is unrestricted, because the whole point of that pass is that the population
#: adds up.
NAMED_CELLS = (
    ("soccer", "container_member"),
    ("baseball", "quantity"),
    ("soccer", "quantity"),
    ("tennis", "quantity"),
    ("esports", "container_member"),
    ("basketball", "quantity"),
)

#: The disposition ladder. ORDERED and exhaustive: the first matching arm wins,
#: so every market has exactly one value and the arms cannot double-count.
#:
#: ``repairable_named_ou`` is the staged repair predicate, ALL of it, with no
#: loosening — exactly two legs, exactly one named ``over`` and one named
#: ``under``, both openings present, ``min = max`` (the identical-copy
#: signature), the pair sum outside tolerance, and exactly one winner. A market
#: that is identical-but-not-named-O/U falls to the next arm and is
#: EXCLUDE-only, because the direction evidence that licenses ``1 - p`` was
#: measured on named legs and does not transfer.
DISPOSITION_SQL = f"""
      CASE
        WHEN n_legs <> 2                      THEN 'not_two_leg'
        WHEN n_open < 2                       THEN 'partial_open'
        WHEN ABS(sum_open - 1) <= {TOL}       THEN 'complementary'
        WHEN min_open = max_open
             AND n_over = 1 AND n_under = 1
             AND n_win = 1                    THEN 'repairable_named_ou'
        WHEN min_open = max_open              THEN 'nonrepairable_identical'
        ELSE                                       'other_noncomp'
      END
""".strip()

LEGS_CTE = f"""
  SELECT fm.id AS market_id,
         COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
         fm.market_type,
         COUNT(*) AS n_legs,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'over')  AS n_over,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'under') AS n_under,
         COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL) AS n_open,
         COUNT(*) FILTER (WHERE fo.is_winner) AS n_win,
         COUNT(*) FILTER (WHERE fo.resolution_source
                          IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}) AS n_elig,
         MIN(fo.opening_probability) AS min_open,
         MAX(fo.opening_probability) AS max_open,
         SUM(fo.opening_probability) AS sum_open,
         MAX(fo.opening_probability)
           FILTER (WHERE lower(btrim(fo.name)) = 'over') AS over_open,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'under'
                          AND fo.calibration_probability IS NOT NULL)
           AS under_legs_with_cp,
         COUNT(*) FILTER (WHERE lower(btrim(fo.name)) = 'under') AS under_legs
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
    AND fm.source = 'polymarket'
    AND fm.status = 'resolved'
    AND fm.market_type IN ('quantity', 'container_member')
  GROUP BY 1, 2, 3
""".rstrip()


def binding_sql() -> str:
    """Pass 1 — every market bound to exactly one disposition."""
    return f"""
WITH legs AS ({LEGS_CTE}
), disp AS (
  SELECT category, market_type, market_id, (n_elig > 0) AS has_eligible,
         under_legs_with_cp, under_legs,
         {DISPOSITION_SQL} AS disposition
  FROM legs
)
SELECT category, market_type, disposition, has_eligible,
       COUNT(*) AS markets,
       SUM(under_legs) AS under_legs,
       SUM(under_legs_with_cp) AS under_legs_with_cp
FROM disp
GROUP BY 1, 2, 3, 4
""".strip()


def deltas_sql() -> str:
    """Pass 2 — per-disposition expected cell deltas, through the real COALESCE.

    ``repaired`` rewrites ONLY the Under leg of a ``repairable_named_ou`` market
    and ONLY its ``opening_probability``, exactly as the staged apply would, and
    then reads the curve price back through
    ``COALESCE(calibration_probability, <repaired opening>)``. That last step is
    the one the staged spec's 5.62 skipped: a leg carrying a
    ``calibration_probability`` keeps it, so the repair cannot move that leg's
    published bucket no matter what it writes underneath.
    """
    cells = ", ".join(f"('{c}','{m}')" for c, m in NAMED_CELLS)
    return f"""
WITH legs AS ({LEGS_CTE}
), disp AS (
  SELECT category, market_type, market_id, over_open,
         {DISPOSITION_SQL} AS disposition
  FROM legs
), priced AS (
  SELECT d.category, d.market_type, d.disposition,
         t.treatment,
         CASE
           WHEN t.treatment = 'repaired'
                AND d.disposition = 'repairable_named_ou'
                AND lower(btrim(fo.name)) = 'under'
           THEN COALESCE(fo.calibration_probability, 1 - d.over_open)
           ELSE COALESCE(fo.calibration_probability, fo.opening_probability)
         END AS price,
         fo.is_winner
  FROM disp d
  JOIN futures_outcomes fo ON fo.market_id = d.market_id
  CROSS JOIN (VALUES ('as_is'), ('repaired')) AS t(treatment)
  WHERE (d.category, d.market_type) IN ({cells})
    AND d.disposition IN ('complementary', 'repairable_named_ou',
                          'nonrepairable_identical', 'other_noncomp')
    AND fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
    AND fo.is_winner IS NOT NULL
)
SELECT category, market_type, disposition, treatment,
       LEAST(FLOOR(price * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(price) AS sum_prob,
       SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) AS winners
FROM priced
WHERE price > 0 AND price < 1
GROUP BY 1, 2, 3, 4, 5
""".strip()


def fold(template: str, args, on_rows) -> tuple[list[dict], list[dict], float]:
    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.chunk, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()

    started = time.monotonic()
    shards: list[dict] = []
    irreducible: list[dict] = []

    while stack:
        lo, hi = stack.pop()
        result = dbq_run(template.format(lo=lo, hi=hi), timeout_ms=args.timeout_ms)
        if result.get("status") == "ok":
            if result.get("truncated"):
                irreducible.append({"lo": lo, "hi": hi, "reason": "row_cap_truncated"})
                print(f"  [{lo}..{hi}) TRUNCATED — NOT folded", flush=True)
                continue
            on_rows(result.get("rows") or [])
            shards.append(
                {
                    "lo": lo,
                    "hi": hi,
                    "duration_ms": result.get("duration_ms"),
                    "sql_fingerprint": result.get("sql_fingerprint"),
                }
            )
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

    return shards, irreducible, round(time.monotonic() - started, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="pair_disposition")
    parser.add_argument("--timeout-ms", type=int, default=10_000)
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=2_000_000)
    parser.add_argument("--skip-deltas", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    # ---- pass 1: the binding -------------------------------------------------
    binding: dict[tuple, dict] = {}

    def take_binding(rows):
        for cat, mtype, disp, elig, markets, under_legs, under_cp in rows:
            slot = binding.setdefault(
                (cat, mtype, disp, bool(elig)),
                {"markets": 0, "under_legs": 0, "under_legs_with_cp": 0},
            )
            slot["markets"] += int(markets or 0)
            slot["under_legs"] += int(under_legs or 0)
            slot["under_legs_with_cp"] += int(under_cp or 0)

    print("=== pass 1: disposition binding ===", flush=True)
    b_shards, b_irr, b_elapsed = fold(binding_sql(), args, take_binding)

    # ---- pass 2: the deltas --------------------------------------------------
    bins: dict[tuple, dict[int, dict]] = {}

    def take_deltas(rows):
        for cat, mtype, disp, treat, b, n, sum_prob, winners in rows:
            slot = bins.setdefault((cat, mtype, disp, treat), {}).setdefault(
                int(b), {"n": 0, "sum_prob": 0.0, "winners": 0}
            )
            slot["n"] += int(n)
            slot["sum_prob"] += float(sum_prob or 0)
            slot["winners"] += int(winners or 0)

    d_shards: list[dict] = []
    d_irr: list[dict] = []
    d_elapsed = 0.0
    if not args.skip_deltas:
        print("\n=== pass 2: per-disposition cell deltas ===", flush=True)
        d_shards, d_irr, d_elapsed = fold(deltas_sql(), args, take_deltas)

    # ---- reconciliation ------------------------------------------------------
    by_disposition: dict[str, dict] = {}
    for (cat, mtype, disp, elig), v in binding.items():
        agg = by_disposition.setdefault(
            disp,
            {"markets": 0, "eligible_markets": 0, "under_legs": 0,
             "under_legs_with_cp": 0, "cells": {}},
        )
        agg["markets"] += v["markets"]
        agg["under_legs"] += v["under_legs"]
        agg["under_legs_with_cp"] += v["under_legs_with_cp"]
        if elig:
            agg["eligible_markets"] += v["markets"]
            cell = agg["cells"].setdefault(
                f"{cat}/{mtype}", {"markets": 0, "under_legs_with_cp": 0}
            )
            cell["markets"] += v["markets"]
            cell["under_legs_with_cp"] += v["under_legs_with_cp"]

    deltas: dict[str, dict] = {}
    for (cat, mtype, disp, treat), b in bins.items():
        vals = list(b.values())
        ece, n = ece_from_bins(vals)
        deltas.setdefault(f"{cat}/{mtype}", {}).setdefault(disp, {})[treat] = {
            "ece": ece, "n": n, "gap": gap_from_bins(vals),
        }

    payload = {
        "label": args.label,
        "measured": not (b_irr or d_irr),
        "tolerance": TOL,
        "disposition_sql": DISPOSITION_SQL,
        "note": (
            "disposition is a single ordered CASE, so every market has exactly "
            "one value and the arms sum to the population by construction. "
            "CERT-403A P1#2 exists because a cross-tab let two different "
            "margins be quoted about the same rows."
        ),
        "binding": {
            "elapsed_s": b_elapsed,
            "shards": b_shards,
            "irreducible": b_irr,
            "by_disposition": by_disposition,
            "rows": [
                {"category": c, "market_type": m, "disposition": d,
                 "has_eligible": e, **v}
                for (c, m, d, e), v in sorted(binding.items(), key=lambda kv: str(kv[0]))
            ],
        },
        "deltas": {
            "elapsed_s": d_elapsed,
            "shards": d_shards,
            "irreducible": d_irr,
            "cells": deltas,
        },
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.label}.json"
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"\n=== {args.label} — binding {b_elapsed}s / deltas {d_elapsed}s, "
          f"irreducible {len(b_irr)}+{len(d_irr)} ===")
    print(f"{'disposition':<26} {'markets':>9} {'eligible':>9} "
          f"{'under_legs':>11} {'with_cp':>9}")
    for disp, v in sorted(by_disposition.items(), key=lambda kv: -kv[1]["markets"]):
        print(f"{disp:<26} {v['markets']:>9} {v['eligible_markets']:>9} "
              f"{v['under_legs']:>11} {v['under_legs_with_cp']:>9}")
    for cell, per in sorted(deltas.items()):
        for disp, per_t in sorted(per.items()):
            a, r = per_t.get("as_is"), per_t.get("repaired")
            if a and r and a["ece"] != r["ece"]:
                print(f"  {cell} / {disp}: as_is {a['ece']} (n {a['n']}) "
                      f"-> repaired {r['ece']} (n {r['n']})")
    print(f"wrote {out_path}")
    return 0 if not (b_irr or d_irr) else 1


if __name__ == "__main__":
    raise SystemExit(main())
