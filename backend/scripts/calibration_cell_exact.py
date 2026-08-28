#!/usr/bin/env python3
"""CAL-P114 — fold ONE published cell through the PRODUCER'S OWN CTE chain.

This is the third and last instrument in the CAL-P112 family, and it exists
because the first two could not measure the cell this queue was pointed at.

===========================  ==========================================  =========
instrument                   how it derives the population               reproduces
===========================  ==========================================  =========
``calibration_cell_shape_fold``   re-implements the predicate down to    NO on
                                  ``ranked_outcomes``; no dedup, no      several
                                  per-outcome exclusions. Scales.        cells
``calibration_cell_replica``      re-implements the chain through        yes, to
                                  ``deduped`` in Python. Caps at         ~2% on n
                                  ~6,000 candidate rows.
**this file**                     ``_calibration_population_ctes()``     BY
                                  IMPORTED FROM THE PRODUCER, verbatim.  CONSTRUCTION
===========================  ==========================================  =========

The first two are re-implementations, so every published-curve rule they bench
inherits an unmeasured drift between the bench and the curve. On
``kalshi/economics`` that drift is not small and not subtle: the shape census
reads **69,653 / 4.65 / +4.27** (55,425 / 3.41 / +2.19 with the truth-eligibility
gate) against the payload's **28,581 / 5.29 / −0.47** — 1.9x the rows and the
WRONG SIGN on the gap. A rule designed on that rail is designed on a different
population, and CAL-P112 said exactly this about ``polymarket/tech`` before
declaring it UNMEASURED.

WHY THIS ONE CANNOT DRIFT
---------------------------
It does not re-implement anything. It calls
``precompute_calibration._calibration_population_ctes()`` — the same function
the producer calls to build the curve — and appends only a ``GROUP BY`` over
``deduped``, which is the final published population. Its self-check is
therefore not "do two implementations agree" but "does the producer's own
predicate, run now, reproduce the payload it produced".

**It does not import the frozen file to CHANGE it.** Ruling 009 freezes commits
to ``precompute_calibration.py``; reading it is what every test in
``backend/tests`` already does. ``git diff origin/master`` for that path is
empty on this branch.

THE THREE THINGS THAT MADE IT WORK, ALL OF THEM NON-OBVIOUS
-------------------------------------------------------------
1. ``market_info_extra`` is a documented parameter of the chain (the horizon
   surface at ``precompute_calibration.py:5583`` uses it the same way). It
   injects into ``market_info``'s WHERE, and every downstream CTE joins
   ``market_info`` — so scoping it to one cell scopes the whole chain.
2. **``POST /api/admin/db-query`` refuses the chain verbatim** with
   ``"Multi-statement queries not allowed"``. The producer's SQL is full of
   prose comments and some contain a semicolon; the guard counts those. The
   comments are stripped quote-safely before sending (``_strip_sql_comments``).
3. The whole-cell chain exceeds the row path's hard 10 s budget, so it is
   chunked on ``fm.id`` through the SAME ``market_info_extra`` hook, and a
   chunk that still times out is SPLIT rather than retried (gotcha #53 — a
   silently short answer reads as "the class is small").

THE ONE APPROXIMATION, MEASURED RATHER THAN ASSERTED
------------------------------------------------------
Chunking on ``fm.id`` can split a ``group_id`` / ``event_id`` cluster across a
chunk boundary, and ``virtual_market``'s ">= 3 markets in the same source"
grouping test is then evaluated on a partial cluster — so a market that is
grouped in production can read ungrouped in a chunk and take the ``rn = 1``
branch instead of the multi branch. This is the same class of approximation
``calibration_cell_replica`` documents, and here it is CHECKED rather than
described: ``--edge-check`` re-runs the whole sweep at a different chunk width
and prints both totals. If the two disagree, the chunking is doing something
and the run says so instead of averaging it away.

Usage::

    python3 backend/scripts/calibration_cell_exact.py \\
        --source kalshi --category economics --by age --edge-check \\
        --out artifacts/cal-p114/exact-kalshi-economics.json
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

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
)

#: The db-query row path's silent truncation point.
ROW_CAP = 1000

#: Default id width per chunk. 1M ids measured ~1.7 s against production.
DEFAULT_WIDTH = 1_000_000


class QueryTimeout(RuntimeError):
    """The server cancelled the statement — the one failure this script can
    FIX, by scanning a narrower id range, and the one that must never be
    retried forever at the same size."""


def _strip_sql_comments(sql: str) -> str:
    """Drop ``--`` line comments, respecting single-quoted literals.

    The db-query guard rejects the producer's SQL outright because some of its
    prose comments contain a semicolon and the guard reads that as a second
    statement. Stripping comments is semantics-preserving; stripping them with
    a naive ``split('--')`` is not, because outcome names and regexes in this
    chain legitimately contain ``--`` inside quotes.
    """
    out = []
    for line in sql.split("\n"):
        i, in_quote, cut = 0, False, None
        while i < len(line):
            ch = line[i]
            if ch == "'":
                in_quote = not in_quote
            elif not in_quote and ch == "-" and line[i + 1:i + 2] == "-":
                cut = i
                break
            i += 1
        out.append(line if cut is None else line[:cut].rstrip())
    return "\n".join(ln for ln in out if ln.strip())


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
            last = e.read().decode()[:400]
            if "statement_timeout" in last:
                raise QueryTimeout(last) from e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"db-query failed after {retries} attempts: {last}")


# ---------------------------------------------------------------------------
# Attribution dimensions. Each is a SQL expression over ``deduped d`` plus the
# joins it needs. ``none`` is the plain cell fold and is what the self-check
# compares against the payload.
# ---------------------------------------------------------------------------
#: How stale the last snapshot before the market's own close is. Part A2 of
#: ``backfill_winners`` sets ``calibration_probability`` to exactly this
#: snapshot for every non-event market with a ``commence_time``, which is 100%
#: of ``kalshi/economics``, so this dimension asks: how old is the price the
#: curve calls a closing line?
AGE_JOIN = """
LEFT JOIN futures_markets fm2 ON fm2.id = d.market_id
LEFT JOIN LATERAL (
    SELECT fos.captured_at
    FROM futures_odds_snapshots fos
    WHERE fos.outcome_id = d.outcome_id
      AND fos.captured_at < fm2.commence_time
      AND fos.probability > 0 AND fos.probability < 1
    ORDER BY fos.captured_at DESC LIMIT 1
) ls ON true
"""
AGE_EXPR = """
CASE WHEN fm2.commence_time IS NULL THEN 'z_no_commence'
     WHEN ls.captured_at IS NULL THEN 'z_no_snapshot'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '15 minutes' THEN 'a_lt15m'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '1 hour'     THEN 'b_15m_1h'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '4 hours'    THEN 'c_1h_4h'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '1 day'      THEN 'd_4h_1d'
     WHEN fm2.commence_time - ls.captured_at < INTERVAL '7 days'     THEN 'e_1d_7d'
     ELSE 'f_gt7d' END
"""

#: The Kalshi SERIES ticker — everything before the first '-' of the event
#: ticker. This is the market FAMILY (KXWTIH, KXNASDAQ100U, KXFED...), which is
#: the unit a rule can actually name.
SERIES_JOIN = "LEFT JOIN futures_markets fm2 ON fm2.id = d.market_id"
SERIES_EXPR = "SPLIT_PART(fm2.external_id, '-', 1)"

#: Terminal market shape, on the same basis ``market_result_shape`` uses.
#:
#: The ``market_id IN (SELECT market_id FROM market_info)`` conjunct is NOT
#: redundant with the ``ON`` clause and must not be "tidied" away. Without it
#: the planner has no predicate on ``futures_outcomes`` and prices a full
#: 3.3M-row seq scan + aggregate BEFORE the join — measured here as a chunk
#: that never returns and recursively splits to the depth limit. It is the same
#: defect CAL-P039 found in ``vm_stats`` (19.1x on the query), arriving through
#: a different door: a planner hint spelled as a predicate. ``market_info`` is
#: already scoped to this chunk's cell, so the conjunct is implied by the join
#: and changes no row.
SHAPE_JOIN = """
LEFT JOIN (
    SELECT fo3.market_id,
           COUNT(*) AS mn,
           COUNT(*) FILTER (WHERE fo3.is_winner) AS mw
    FROM futures_outcomes fo3
    WHERE fo3.market_id IN (SELECT market_id FROM market_info)
    GROUP BY fo3.market_id
) sh ON sh.market_id = d.market_id
"""
SHAPE_EXPR = """
CASE WHEN sh.mw = 0 THEN 'void_0win'
     WHEN sh.mn >= 3 AND sh.mw >= 2 THEN 'bundle_multiwin'
     WHEN sh.mn >= 3 AND sh.mw = 1 THEN 'field_1win'
     WHEN sh.mn = 2 AND sh.mw = 1 THEN 'binary_1win'
     WHEN sh.mn = 2 THEN 'binary_other'
     ELSE 'single' END
"""

#: SHAPE x PUBLISHED-PRICE-SUM, the cross CAL-P112's RULE E turns on.
#:
#: RULE E replaces the bundle test's realized ``win_count >= 2`` with a
#: STRUCTURAL one — a market whose published prices sum to more than 1.15 is
#: not a partition, whatever it happened to realize. The two tests disagree on
#: exactly the rows that decide whether a cell is a calibration failure or a
#: population defect: a ladder that realized ONE winner passes the realization
#: test and fails the structural one. Folding the cross is the only way to see
#: whether a cell's ``field_1win`` remainder is a clean control (sums to ~1) or
#: the same ladders on a quiet day (sums to N x p).
#:
#: The sum is over ``deduped`` — the PUBLISHED rows — because that is the sum a
#: reader of the curve is implicitly told is a probability distribution.
SUMBAND_PRE = """,
msums AS (
    SELECT market_id, SUM(adj_opening_probability) AS msum
    FROM deduped GROUP BY market_id
)"""
SUMBAND_JOIN = SHAPE_JOIN + "\nLEFT JOIN msums ms ON ms.market_id = d.market_id"
SUMBAND_EXPR = """
CASE WHEN sh.mw = 0 THEN 'void'
     WHEN sh.mn >= 3 AND sh.mw >= 2 THEN 'bundle'
     WHEN sh.mn >= 3 AND sh.mw = 1 THEN 'field1'
     WHEN sh.mn = 2 THEN 'binary'
     ELSE 'single' END
|| '|' ||
CASE WHEN ms.msum IS NULL THEN 'na'
     WHEN ms.msum <= 1.15 THEN 'a_sum_le_1.15'
     WHEN ms.msum <= 2    THEN 'b_sum_1.15_2'
     WHEN ms.msum <= 5    THEN 'c_sum_2_5'
     WHEN ms.msum <= 15   THEN 'd_sum_5_15'
     ELSE 'e_sum_gt_15' END
"""

#: name -> (key expression, extra JOINs, extra CTEs appended to the chain)
DIMENSIONS = {
    "none": ("'all'", "", ""),
    "age": (AGE_EXPR, AGE_JOIN, ""),
    "series": (SERIES_EXPR, SERIES_JOIN, ""),
    "shape": (SHAPE_EXPR, SHAPE_JOIN, ""),
    "sumband": (SUMBAND_EXPR, SUMBAND_JOIN, SUMBAND_PRE),
    "price_moved": ("CASE WHEN d.price_moved THEN 'moved' ELSE 'unmoved' END", "", ""),
    "market_type": ("COALESCE(d.market_type, 'null')", "", ""),
}


def cell_sql(source: str, category: str, lo: int, hi: int, dim: str) -> str:
    expr, join, pre = DIMENSIONS[dim]
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}' "
            f"AND fm.id >= {lo} AND fm.id < {hi}"
        )
    )
    return _strip_sql_comments(
        "WITH " + pop + pre + f"""
SELECT {expr} AS k,
       LEAST(FLOOR(d.adj_opening_probability * 10)::int, 9) AS b,
       COUNT(*) AS n,
       SUM(CASE WHEN d.is_winner THEN 1 ELSE 0 END) AS w,
       ROUND(SUM(d.adj_opening_probability)::numeric, 6) AS sp
FROM deduped d
{join}
GROUP BY 1, 2"""
    )


def collect(source: str, category: str, lo: int, hi: int, dim: str,
            depth: int = 0) -> list:
    """Fold one id range, splitting on BOTH failure modes of the row path.

    Truncation and statement-timeout are the same bug wearing two faces: the
    range is too big. Only one of them is loud.
    """
    try:
        r = db_query(cell_sql(source, category, lo, hi, dim), limit=ROW_CAP)
    except QueryTimeout:
        return _split(source, category, lo, hi, dim, depth, "timing out")
    if r["row_count"] >= ROW_CAP:
        return _split(source, category, lo, hi, dim, depth, "truncated")
    return r["rows"]


def _split(source: str, category: str, lo: int, hi: int, dim: str,
           depth: int, why: str) -> list:
    if depth > 18 or hi - lo <= 1:
        raise RuntimeError(f"chunk {lo}-{hi} still {why} at depth {depth}")
    mid = lo + (hi - lo) // 2
    return (collect(source, category, lo, mid, dim, depth + 1)
            + collect(source, category, mid, hi, dim, depth + 1))


def sweep(source: str, category: str, dim: str, width: int,
          holdout_at: int | None = None) -> tuple[dict, dict]:
    rng = db_query(
        f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM futures_markets "
        f"WHERE source = '{source}'", limit=5)
    lo, hi = rng["rows"][0]

    edges, e = [], lo
    while e <= hi:
        edges.append(e)
        e = min(e + width, hi + 1)
    edges.append(hi + 1)
    if holdout_at and lo < holdout_at <= hi:
        edges = sorted(set(edges) | {holdout_at})

    def _new():
        return defaultdict(lambda: defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0}))

    by_key = _new()
    halves = {"OLD": _new(), "NEW": _new()}
    t_sweep = time.time()
    for i in range(len(edges) - 1):
        rlo, rhi = edges[i], edges[i + 1]
        half = None if not holdout_at else ("OLD" if rlo < holdout_at else "NEW")
        # Progress on stderr, not stdout: a sweep with no output for ten
        # minutes is indistinguishable from a hung one, and the whole point of
        # the split-on-timeout recursion is that SOME chunks cost far more than
        # the median. Say which one.
        print(f"    [{i + 1}/{len(edges) - 1}] ids {rlo}-{rhi} "
              f"({time.time() - t_sweep:.0f}s elapsed)", file=sys.stderr, flush=True)
        for k, b, n, w, sp in collect(source, category, rlo, rhi, dim):
            targets = [by_key] + ([halves[half]] if half else [])
            for t in targets:
                v = t[k][b]
                v["n"] += n
                v["w"] += w
                v["sp"] += float(sp)
    return by_key, halves


def fold(bins: dict) -> tuple[int, float | None, float | None]:
    n = sum(v["n"] for v in bins.values())
    if not n:
        return 0, None, None
    ece = sum(abs(v["w"] / v["n"] - v["sp"] / v["n"]) * v["n"]
              for v in bins.values()) / n * 100
    gap = sum(v["sp"] - v["w"] for v in bins.values()) / n * 100
    return n, round(ece, 2), round(gap, 2)


def pool(by_key: dict) -> dict:
    out: dict[int, dict] = defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0})
    for bb in by_key.values():
        for b, v in bb.items():
            out[b]["n"] += v["n"]
            out[b]["w"] += v["w"]
            out[b]["sp"] += v["sp"]
    return out


def payload_cell(source: str, category: str) -> tuple[int, float | None, float | None, dict]:
    """The published cell, folded from the served payload's own buckets.

    This is the number every line this script prints must be read against —
    a rail that is not shown to reproduce is a parallel rail wearing the
    published curve's name.
    """
    base = os.environ["BAINLUCK_API"].rstrip("/")
    with urllib.request.urlopen(f"{base}/api/calibration", timeout=120) as fh:
        d = json.loads(fh.read().decode())
    bins: dict[int, dict] = defaultdict(lambda: {"n": 0, "w": 0, "sp": 0.0})
    for r in d["buckets"]:
        if r["source"] == source and r["category"] == category:
            v = bins[r["bucket_idx"]]
            v["n"] += r["n"]
            v["w"] += r["winners"]
            v["sp"] += r["sum_prob"]
    n, ece, gap = fold(bins)
    return n, ece, gap, {"generated_at": d.get("generated_at"),
                         "population_version": d.get("population_version")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--by", default="none", choices=sorted(DIMENSIONS))
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH,
                    help="id width per chunk (a chunk that times out is split)")
    ap.add_argument("--edge-check", action="store_true",
                    help="re-run the plain fold at half the chunk width and "
                         "print both totals, so chunk-boundary effects on "
                         "virtual_market grouping are measured, not assumed")
    ap.add_argument("--holdout-at", type=int, default=None,
                    help="a market_id; fold OLD (< id) and NEW (>= id) "
                         "separately. market_id is monotone with creation, so "
                         "NEW is genuinely later data. The id becomes a chunk "
                         "EDGE, so neither half is contaminated.")
    ap.add_argument("--out")
    args = ap.parse_args()

    t0 = time.time()
    by_key, halves = sweep(args.source, args.category, args.by,
                           args.width, args.holdout_at)
    took = time.time() - t0

    pooled = pool(by_key)
    n, ece, gap = fold(pooled)
    pn, pece, pgap, meta = payload_cell(args.source, args.category)

    print(f"{args.source}/{args.category}   (--by {args.by}, "
          f"width {args.width}, {took:.0f}s)")
    print(f"  curve generated {meta['generated_at']}  "
          f"population {meta['population_version']}")
    print()
    print("  SELF-CHECK — the producer's own chain against the payload it produced")
    print(f"    {'exact replica':<16} n={n:>7}  ECE={ece:>6}  gap={gap:>+7}")
    print(f"    {'payload':<16} n={pn:>7}  ECE={pece:>6}  gap={pgap:>+7}")
    if pn:
        dn = (n - pn) / pn * 100
        print(f"    {'delta':<16} n={n - pn:>+7} ({dn:+.2f}%)  "
              f"ECE={ece - pece:+.2f}  gap={gap - pgap:+.2f}")
    print()

    if args.by != "none":
        print(f"  {'class':<18} {'n':>7} {'share':>7} {'ECE':>7} {'gap':>8}")
        for k in sorted(by_key, key=lambda k: -sum(v["n"] for v in by_key[k].values())):
            kn, kece, kgap = fold(by_key[k])
            print(f"  {str(k):<18} {kn:>7} {kn / n * 100:>6.1f}% "
                  f"{kece:>7} {kgap:>+8}")
        print()

    if args.holdout_at:
        print(f"  HOLDOUT on market_id {args.holdout_at}")
        for half in ("OLD", "NEW"):
            print(f"    {half}")
            for k in sorted(halves[half],
                            key=lambda k: -sum(v["n"] for v in halves[half][k].values())):
                kn, kece, kgap = fold(halves[half][k])
                print(f"      {str(k):<18} {kn:>7} {kece:>7} {kgap:>+8}")
        print()

    edge = None
    if args.edge_check:
        w2 = max(1, args.width // 2)
        bk2, _ = sweep(args.source, args.category, "none", w2)
        n2, ece2, gap2 = fold(pool(bk2))
        edge = {"width": w2, "n": n2, "ece": ece2, "gap": gap2}
        print(f"  EDGE CHECK — same fold at chunk width {w2}")
        print(f"    n={n2} ECE={ece2} gap={gap2:+}   "
              f"(vs n={n} ECE={ece} gap={gap:+} at width {args.width})")
        if (n2, ece2, gap2) == (n, ece, gap):
            print("    IDENTICAL — chunk boundaries do not move this cell.")
        else:
            print("    ⚠️  DIFFERENT — chunking is affecting virtual_market "
                  "grouping; treat every class number as approximate.")
        print()

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump({
                "source": args.source, "category": args.category,
                "by": args.by, "width": args.width, "seconds": round(took, 1),
                "payload": {"n": pn, "ece": pece, "gap": pgap, **meta},
                "exact": {"n": n, "ece": ece, "gap": gap},
                "edge_check": edge,
                "by_key": {str(k): {str(b): v for b, v in bb.items()}
                           for k, bb in by_key.items()},
                "halves": {h: {str(k): {str(b): v for b, v in bb.items()}
                               for k, bb in hv.items()}
                           for h, hv in halves.items()} if args.holdout_at else None,
            }, fh)
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
