#!/usr/bin/env python3
"""CAL-P112 — fold ONE published cell by the STRUCTURAL SHAPE of its markets.

The scorecard says which cells are wrong. It cannot say why, because the served
payload carries no market identity — only ``(source, category, price_moved,
bucket_idx)`` counts. This script closes that one gap and nothing else: for a
single ``(source, category)`` cell it re-derives the cell's candidate rows from
production and folds them by the market's captured SHAPE, so a cell's error can
be attributed to a class of market rather than to a category name.

The shape classes, keyed on ``(n_outcomes, win_count)`` over ALL of a market's
outcomes — the same basis ``market_result_shape`` uses in
``precompute_calibration.py``:

===================  =========================================================
``void_0win``        graded nobody. Already excluded when n>=2
                     (``no_winner_markets``); the n=1 tail is not.
``bundle_multiwin``  >=3 outcomes, >=2 winners — a non-partition bundle
                     (cumulative ladders, independent binaries in one market).
                     Excluded TODAY only when category='esports'.
``field_1win``       >=3 outcomes, exactly 1 winner. A genuine partition looks
                     like this — and so does the 1-winner REALIZATION of a
                     bundle. The published price sum separates them: a
                     partition sums to ~1, a bundle to N x p.
``binary_1win``      2 outcomes, 1 winner. The scoreable core.
``binary_other``     2 outcomes, 0 or 2 winners. Excluded by
                     ``malformed_binaries`` ONLY when ``mutually_exclusive``
                     is true, and that column is not evidence (Queue 299).
``single``           1 captured outcome. A standalone Yes/No claim is a real
                     forecast; a market whose only captured leg is the winner
                     is a capture artifact. The class needs its win rate read
                     before it can be told which it is.
===================  =========================================================

THIS IS A CENSUS, NOT THE CURVE — AND IT SAYS SO EVERY RUN
------------------------------------------------------------
It applies the population predicate down to ``ranked_outcomes`` and stops:
there is no ``is_liquid`` gate, no per-outcome exclusion, no field
normalization and **no dedup**, because none of those can be computed from one
grouped scan inside a 10 s budget. Its row counts therefore run HIGH, and by a
lot on cells where dedup does the work. Measured 2026-08-28:

    polymarket/esports  census 14,121 / 6.81 / +5.57   payload 13,156 / 8.08 / +6.50
    polymarket/tech     census  2,080 / 8.04 / +5.10   payload  2,657 / 5.40 / -1.78
    kalshi/tech         census  1,756 / 7.91 / -6.43   payload  1,193 / 11.10 / -9.49

The first tracks the payload closely enough to attribute the cell's error to a
class. The third does not — dedup removes 540 of its rows — which is what
``calibration_cell_replica.py`` exists for: the same cell, full predicate,
1,218 / 10.75 / -8.97. The second reproduces neither n NOR the gap's SIGN, and
is reported in the CAL-P112 designs as **UNMEASURED, not estimated**.

So: use this file to find WHICH SHAPE carries a cell's error; use the replica to
say what a rule does to the cell. **Every report built on either must print its
number beside the payload's for the same cell** — a rail that is not shown to
reproduce is the CAL-P108 finding wearing an instrument's coat.

WHY IT PAGES THE WAY IT DOES
------------------------------
``POST /api/admin/db-query`` runs the row path under a hard-coded 10 s
``statement_timeout`` (``timeout_ms`` is refused outside ``explain``) and
truncates silently at 1,000 rows. A whole-cell scan of a large category exceeds
both. So the fold is chunked on ``futures_markets.id`` and every chunk that
returns exactly the cap is reported as TRUNCATED and re-split, because a
silently short answer here reads as "the class is small" — the failure mode
gotcha #53 exists for.

Usage::

    python3 backend/scripts/calibration_cell_shape_fold.py \\
        --source polymarket --category esports --out artifacts/x.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.resolution_authority import (  # noqa: E402
    CALIBRATION_TRUTH_ELIGIBLE_SOURCES,
)

ELIGIBLE_SQL = "(" + ",".join(f"'{s}'" for s in sorted(CALIBRATION_TRUTH_ELIGIBLE_SOURCES)) + ")"

#: The db-query row path's silent truncation point. A chunk that returns
#: exactly this many rows has not been measured, it has been cut off.
ROW_CAP = 1000

SHAPE_CASE = """
    CASE WHEN mw = 0 THEN 'void_0win'
         WHEN mn >= 3 AND mw >= 2 THEN 'bundle_multiwin'
         WHEN mn >= 3 AND mw = 1 THEN 'field_1win'
         WHEN mn = 2 AND mw = 1 THEN 'binary_1win'
         WHEN mn = 2 THEN 'binary_other'
         ELSE 'single' END
"""


class QueryTimeout(RuntimeError):
    """The server cancelled the statement. Distinct from any other failure
    because it is the one this script can FIX — by scanning a smaller id
    range — and the one that must never be retried forever at the same size."""


def db_query(sql: str, limit: int = ROW_CAP, retries: int = 3) -> dict:
    base = os.environ["BAINLUCK_API"].rstrip("/")
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            f"{base}/api/admin/db-query", data=body,
            headers={"Authorization": "Bearer " + os.environ["ADMIN_TOKEN"],
                     "Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
        except urllib.error.HTTPError as e:
            last = e.read().decode()[:300]
            time.sleep(2 * (attempt + 1))
    if last and "statement_timeout" in last:
        raise QueryTimeout(last)
    raise RuntimeError(f"db-query failed after {retries} attempts: {last}")


def chunk_sql(source: str, category: str, lo: int, hi: int) -> str:
    return f"""
SELECT cls, b, COUNT(*) AS n, SUM(win) AS w, ROUND(SUM(cp)::numeric, 4) AS sp
FROM (
  SELECT LEAST(9, FLOOR(cp * 10)::int) AS b, win, cp, {SHAPE_CASE} AS cls
  FROM (
    SELECT COALESCE(fo.calibration_probability, fo.opening_probability) AS cp,
           CASE WHEN fo.is_winner THEN 1 ELSE 0 END AS win,
           COUNT(*) OVER (PARTITION BY fo.market_id) AS mn,
           SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) OVER (PARTITION BY fo.market_id) AS mw
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.id >= {lo} AND fm.id < {hi}
      AND fm.source = '{source}' AND fm.llm_sport_category = '{category}'
      AND fm.status = 'resolved'
      AND fo.opening_probability IS NOT NULL
      AND fo.opening_probability > 0 AND fo.opening_probability < 1
      AND fo.resolution_source IN {ELIGIBLE_SQL}
  ) t
) u GROUP BY 1, 2
"""


def _split(source: str, category: str, lo: int, hi: int, depth: int, why: str) -> list:
    if depth > 14 or hi - lo <= 1:
        raise RuntimeError(f"chunk {lo}-{hi} still {why} at depth {depth}")
    mid = lo + (hi - lo) // 2
    return collect(source, category, lo, mid, depth + 1) + \
        collect(source, category, mid, hi, depth + 1)


def collect(source: str, category: str, lo: int, hi: int, depth: int = 0) -> list:
    """Fold one id range, splitting on BOTH failure modes of the row path.

    Truncation and statement-timeout are the same bug wearing two faces: the
    range is too big. Only one of them is loud. A silently short chunk reads as
    "this class is small" and a timeout that is merely retried reads as "the
    endpoint is flaky" — both end with a rule designed on a population that was
    never measured, so both split instead.
    """
    try:
        r = db_query(chunk_sql(source, category, lo, hi), limit=ROW_CAP)
    except QueryTimeout:
        return _split(source, category, lo, hi, depth, "timing out")
    if r["row_count"] >= ROW_CAP:
        return _split(source, category, lo, hi, depth, "truncated")
    return r["rows"]


def fold(bins: dict) -> tuple[int, float | None, float | None]:
    n = sum(v["n"] for v in bins.values())
    if not n:
        return 0, None, None
    ece = sum(abs(v["w"] / v["n"] - v["sp"] / v["n"]) * v["n"] for v in bins.values()) / n * 100
    gap = sum(v["sp"] - v["w"] for v in bins.values()) / n * 100
    return n, round(ece, 2), round(gap, 2)


def pool(by_class: dict, classes) -> dict:
    out: dict[int, dict] = defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0})
    for c in classes:
        for b, v in by_class.get(c, {}).items():
            out[b]["n"] += v["n"]
            out[b]["w"] += v["w"]
            out[b]["sp"] += v["sp"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--chunks", type=int, default=24)
    ap.add_argument("--holdout-at", type=int, default=None,
                    help="a market_id; fold OLD (< id) and NEW (>= id) separately. "
                         "market_id is monotone with creation, so NEW is later data. "
                         "The id becomes a chunk EDGE, so neither half is contaminated.")
    ap.add_argument("--out")
    args = ap.parse_args()

    rng = db_query(
        f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM futures_markets "
        f"WHERE source = '{args.source}'", limit=5)
    lo, hi = rng["rows"][0]
    step = max(1, (hi + 1 - lo) // args.chunks)

    edges = []
    edge = lo
    while edge <= hi:
        edges.append(edge)
        edge = min(edge + step, hi + 1)
    edges.append(hi + 1)
    if args.holdout_at and lo < args.holdout_at <= hi:
        edges = sorted(set(edges) | {args.holdout_at})

    def _new_map():
        return defaultdict(lambda: defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0}))

    by_class = _new_map()
    halves = {"OLD": _new_map(), "NEW": _new_map()}
    for i in range(len(edges) - 1):
        rlo, rhi = edges[i], edges[i + 1]
        half = None if not args.holdout_at else ("OLD" if rlo < args.holdout_at else "NEW")
        for cls, b, n, w, sp in collect(args.source, args.category, rlo, rhi):
            for target in (by_class,) + ((halves[half],) if half else ()):
                v = target[cls][b]
                v["n"] += n
                v["w"] += w
                v["sp"] += float(sp)

    print(f"{args.source}/{args.category}")
    print(f"  {'class':18s} {'n':>7} {'ECE':>7} {'gap':>8}")
    for cls in sorted(by_class, key=lambda k: -sum(v["n"] for v in by_class[k].values())):
        n, e, g = fold(by_class[cls])
        print(f"  {cls:18s} {n:7d} {e:7.2f} {g:+8.2f}")

    # Today's published shape: every class the curve does not already exclude.
    # ``bundle_multiwin`` is excluded only in esports, so it stays in elsewhere.
    excluded_today = ["void_0win"] + (
        ["bundle_multiwin"] if args.category == "esports" else [])
    today = [c for c in by_class if c not in excluded_today]
    print(f"\n  CENSUS of today's published shape: {fold(pool(by_class, today))}"
          "   <- PRE-DEDUP, runs high. Compare with the payload's own n/ECE/gap"
          " before quoting it, and use calibration_cell_replica.py to score a rule.")

    out = {"source": args.source, "category": args.category,
           "by_class": {c: {str(b): v for b, v in bins.items()}
                        for c, bins in by_class.items()},
           "census_today": fold(pool(by_class, today))}

    if args.holdout_at:
        print(f"\n  HOLDOUT at market_id {args.holdout_at}"
              " — the rule is never re-fitted on either half")
        out["holdout_at"] = args.holdout_at
        for half in ("OLD", "NEW"):
            m = halves[half]
            print(f"    {half}")
            for cls in sorted(m, key=lambda k: -sum(v["n"] for v in m[k].values())):
                n, e, g = fold(m[cls])
                print(f"      {cls:18s} n={n:6d} ECE={e:6.2f} gap={g:+7.2f}")
            hteam = [c for c in m if c not in excluded_today]
            print(f"      {'-- census --':18s} {fold(pool(m, hteam))}")
            out[half] = {"by_class": {c: dict(zip(("n", "ece", "gap"), fold(m[c])))
                                      for c in m},
                         "census_today": fold(pool(m, hteam))}

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
