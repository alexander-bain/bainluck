#!/usr/bin/env python3
"""Fold the cohort-cell ECE twins over production in id-range shards.

WHY THIS EXISTS. ``artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md`` is ranked by
``ece_all`` — an ECE over rows the published curve already excludes (CAL-P093).
Re-ranking it needs ``ece_eligible`` for EVERY cell, and the obvious way to get
that — one ``GROUP BY`` over the population — cannot run: the admin read rail's
row path is fixed at a 10 s ``statement_timeout`` (``timeout_ms`` is refused
there; MEASURED 2026-08-24) and the population predicate has no index, so even a
bare ``COUNT(*)`` over ``source='polymarket' AND status='resolved'`` seq-scans
858,938 rows and dies.

WHY ID RANGES AND NOT ``MOD(fm.id, k)``. The CAL-P094 directive asked for a
``MOD`` fold, and ``MOD`` is the wrong shard key HERE for a reason worth writing
down: ``MOD(fm.id, k) = j`` is not sargable, so every one of the k shards still
performs the SAME full sequential scan of ``futures_markets``. It divides the
JOIN and aggregate work by k while MULTIPLYING the scan by k. Measured: the
roster ``GROUP BY`` alone times out at 10 s (``e87f755d36db``), and its plan is a
Seq Scan costing 130,431 (``e610b5575d602919``) — so the scan alone does not fit,
and no amount of k makes it fit. ``fm.id >= lo AND fm.id < hi`` IS sargable: it
rides ``futures_markets_pkey``, so each shard reads only its own slice.

This is the same lesson as gotcha #41 in a different coat: the ordering (or here,
the sharding) is never the whole answer — ask what work the shard actually
removes. A shard that removes rows from the aggregate but not from the scan has
not sharded the thing that was too slow.

Bisection, not a fixed shard count, for the census's own reason: a contended
range must be subdivided and reported, never dropped. A range that stays red at
:data:`BISECT_FLOOR_IDS` is IRREDUCIBLE and taints the run — it is recorded with
its bounds rather than spread across cells by a guess, because we cannot know
which cells it would have contained (gotcha #53: an absent range and an empty
range must not render the same).

Usage:
    python3 backend/scripts/fold_cohort_cell_eligible.py \\
        --out artifacts/cal-p094 --label eligible_fold
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

from dbq_probe import run as dbq_run  # noqa: E402

#: The population, verbatim from ``app.utils.cohort_cell_census``. Restated here
#: rather than imported as a string because this script must be able to prove it
#: matches the census by eye at review time; it is asserted equal in the test.
POPULATION_SOURCE = "polymarket"
POPULATION_STATUS = "resolved"
POPULATION_MARKET_TYPES = ("quantity", "container_member")

#: The leagues the diagnosis file's scope table actually contains. Restricting to
#: them is not a shortcut — it is the row cap. 27 leagues x 2 types x 2 truth
#: classes x 10 bins is 1,080 rows, over the endpoint's 1,000-row cap, and the cap
#: TRUNCATES SILENTLY (memory: db-query 1000-row cap). A fold that silently loses
#: its last bins would under-report exactly the tail bins that dominate an ECE.
SCOPE_LEAGUES = (
    "basketball", "baseball", "esports", "hockey", "soccer", "economics",
    "golf", "table_tennis", "politics", "tennis", "geopolitics",
)

#: Below this many ids a still-timing-out range is IRREDUCIBLE. CAL-P066's
#: measured floor, carried unchanged.
BISECT_FLOOR_IDS = 25

#: Rows returned per shard, worst case, well under the 1,000-row cap.
MAX_EXPECTED_ROWS = len(SCOPE_LEAGUES) * 2 * 2 * 10


def bin_sql() -> str:
    types = ", ".join(f"'{t}'" for t in POPULATION_MARKET_TYPES)
    leagues = ", ".join(f"'{l}'" for l in SCOPE_LEAGUES)
    return f"""
SELECT fm.llm_sport_category AS league,
       fm.market_type AS market_type,
       CASE WHEN fo.resolution_source IN {CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL}
            THEN 'eligible' ELSE 'ineligible' END AS truth,
       LEAST(FLOOR(COALESCE(fo.calibration_probability, fo.opening_probability) * 10), 9)::int AS bin,
       COUNT(*) AS n,
       SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
       SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS winners
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.id >= {{lo}} AND fm.id < {{hi}}
  AND fm.source = '{POPULATION_SOURCE}'
  AND fm.status = '{POPULATION_STATUS}'
  AND fm.market_type IN ({types})
  AND fm.llm_sport_category IN ({leagues})
  AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
  AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
  AND fo.opening_probability IS NOT NULL
  AND fo.is_winner IS NOT NULL
GROUP BY 1, 2, 3, 4
""".strip()


def ece_from_bins(bins: list[dict]) -> tuple[float | None, int]:
    """n-weighted 10-bin ECE in pp — ``_compute_horizon_mce``'s definition."""
    populated = [b for b in bins if b["n"]]
    total_n = sum(b["n"] for b in populated)
    if total_n < 30:  # MIN_CELL_N — absent, never 0.0
        return None, total_n
    err = 0.0
    for b in populated:
        avg_p = b["sum_prob"] / b["n"]
        actual = b["winners"] / b["n"]
        err += abs(actual - avg_p) * b["n"]
    return round(err / total_n * 100, 2), total_n


def gap_from_bins(bins: list[dict]) -> float | None:
    populated = [b for b in bins if b["n"]]
    total_n = sum(b["n"] for b in populated)
    if total_n < 30:
        return None
    sum_p = sum(b["sum_prob"] for b in populated)
    wins = sum(b["winners"] for b in populated)
    return round((sum_p - wins) / total_n * 100, 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--label", default="eligible_fold")
    parser.add_argument("--min-id", type=int, default=1)
    parser.add_argument("--max-id", type=int, default=59_600_000)
    parser.add_argument("--chunk", type=int, default=4_000_000)
    args = parser.parse_args()

    if not os.environ.get("ADMIN_TOKEN"):
        print("ERROR: ADMIN_TOKEN not set. Run: source ~/.claude/.env", file=sys.stderr)
        return 2

    template = bin_sql()
    acc: dict[tuple[str, str, str, int], dict] = {}
    shards: list[dict] = []
    irreducible: list[dict] = []

    stack: list[tuple[int, int]] = []
    lo = args.min_id
    while lo < args.max_id:
        hi = min(lo + args.chunk, args.max_id)
        stack.append((lo, hi))
        lo = hi
    stack.reverse()  # pop() ascending, so progress reads in id order

    started = time.monotonic()
    while stack:
        lo, hi = stack.pop()
        sql = template.format(lo=lo, hi=hi)
        result = dbq_run(sql, timeout_ms=10_000)
        status = result.get("status")
        if status == "ok":
            rows = result.get("rows") or []
            if result.get("truncated"):
                # The cap truncates SILENTLY. Never fold a truncated page.
                irreducible.append(
                    {"lo": lo, "hi": hi, "reason": "row_cap_truncated", "rows": len(rows)}
                )
                print(f"  [{lo}..{hi}) TRUNCATED at the row cap — NOT folded")
                continue
            for league, market_type, truth, b, n, sum_prob, winners in rows:
                key = (league, market_type, truth, int(b))
                slot = acc.setdefault(
                    key, {"n": 0, "sum_prob": 0.0, "winners": 0}
                )
                slot["n"] += int(n)
                slot["sum_prob"] += float(sum_prob)
                slot["winners"] += int(winners)
            shards.append(
                {
                    "lo": lo,
                    "hi": hi,
                    "rows": len(rows),
                    "duration_ms": result.get("duration_ms"),
                    "sql_fingerprint": result.get("sql_fingerprint"),
                }
            )
            print(
                f"  [{lo}..{hi}) ok rows={len(rows)} "
                f"{result.get('duration_ms')}ms fp={result.get('sql_fingerprint')}"
            )
            continue

        # Not ok. Subdivide if we can; otherwise record the absence with bounds.
        width = hi - lo
        if width <= BISECT_FLOOR_IDS:
            irreducible.append(
                {"lo": lo, "hi": hi, "reason": result.get("reason"), "status": status}
            )
            print(f"  [{lo}..{hi}) IRREDUCIBLE — {result.get('reason')}")
            continue
        mid = lo + width // 2
        stack.append((mid, hi))
        stack.append((lo, mid))
        print(f"  [{lo}..{hi}) {status} ({result.get('reason')}) — bisecting at {mid}")

    cells: dict[str, dict] = {}
    for (league, market_type, truth, b), v in acc.items():
        cell = f"{league}/{market_type}"
        cells.setdefault(cell, {"eligible": [], "ineligible": [], "all": []})
        row = {"bin": b, **v}
        cells[cell][truth].append(row)
        cells[cell]["all"].append(row)

    report = []
    for cell, buckets in sorted(cells.items()):
        ece_e, n_e = ece_from_bins(buckets["eligible"])
        ece_a, n_a = ece_from_bins(buckets["all"])
        report.append(
            {
                "cell": cell,
                "ece_eligible": ece_e,
                "n_eligible": n_e,
                "gap_eligible": gap_from_bins(buckets["eligible"]),
                "ece_all": ece_a,
                "n_all": n_a,
                "eligible_share": round(n_e / n_a, 4) if n_a else None,
                # The RANK KEY. n_eligible x (ece_eligible - 3), the diagnosis
                # file's impact metric on the honest denominator. None when the
                # cell is under the reporting floor or already under the bar —
                # never 0.0, which would sort as "best cell" (ece_from_bins's
                # reason, applied to the ranking too).
                "impact_eligible": (
                    round(n_e * (ece_e - 3), 1) if ece_e is not None and ece_e > 3 else None
                ),
            }
        )
    report.sort(key=lambda c: (c["impact_eligible"] is None, -(c["impact_eligible"] or 0)))

    complete = not irreducible
    out = {
        "label": args.label,
        "complete": complete,
        "measured": complete,
        "reason": None if complete else "irreducible_ranges_present",
        "population": {
            "source": POPULATION_SOURCE,
            "status": POPULATION_STATUS,
            "market_type_in": list(POPULATION_MARKET_TYPES),
            "leagues_in": list(SCOPE_LEAGUES),
            "league_scope_note": (
                "Restricted to the diagnosis file's scope leagues by the 1,000-row "
                "cap, not by judgment. Cells outside this list are NOT measured "
                "here and must not be read as absent-because-clean."
            ),
        },
        "shards": shards,
        "shard_count": len(shards),
        "irreducible": irreducible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "cells": report,
        "rank_key": "n_eligible * (ece_eligible - 3)",
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{args.label}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {path}  shards={len(shards)} irreducible={len(irreducible)} "
          f"complete={complete} elapsed={out['elapsed_s']}s")
    for c in report[:20]:
        print(
            f"  {c['cell']:34s} ece_elig={c['ece_eligible']!s:>7} "
            f"n_elig={c['n_eligible']:>7} ece_all={c['ece_all']!s:>7} "
            f"n_all={c['n_all']:>7} share={c['eligible_share']!s:>7} "
            f"impact={c['impact_eligible']}"
        )
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
