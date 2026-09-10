#!/usr/bin/env python3
"""CAL-P1083 item 2 — fold ONLY the 70 markets CAL-P1081's plan repriced, through
the PRODUCER'S OWN CTE chain, grouped by golf arm AND by whether the leg was one
of the 2,041 the repair actually wrote.

This is the discriminator the queue asked for: intersect the plan's outcome ids
with the arm's published population via ``_calibration_population_ctes`` rather
than re-deriving either side. ``market_info_extra`` pins the chain to the plan's
own market ids, so the population is the producer's, not a re-implementation.

Usage:  source ~/.claude/.env && python3 tools/cal-1083-plan-grain.py <plan.json> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "scripts"))

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
)
from calibration_cell_exact import (  # noqa: E402
    GOLFROUND_EXPR,
    GOLFROUND_JOIN,
    QueryTimeout,
    _strip_sql_comments,
)

import os  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

#: The producer's chain over even a 70-market scope exceeds db-query's 10s row
#: budget, and `timeout_ms` does not lift it — the deployed guard answers
#: "`timeout_ms` is only supported with `explain: true`" (gotcha #149; CLAUDE.md's
#: db-query table still reads as though the row path takes it). So the only lever
#: is to SPLIT the market scope, never to retry: a short answer that reads as a
#: small class is gotcha #53, and splitting is what `calibration_cell_exact` does.


def db_query(sql: str) -> list:
    base = os.environ["BAINLUCK_API"].rstrip("/")
    body = json.dumps({"sql": sql, "limit": 1000}).encode()
    req = urllib.request.Request(
        f"{base}/api/admin/db-query", data=body,
        headers={"Authorization": "Bearer " + os.environ["ADMIN_TOKEN"],
                 "Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        if "statement_timeout" in detail:
            raise QueryTimeout(detail) from e
        raise RuntimeError(detail) from e
    if r["row_count"] >= 1000:
        raise RuntimeError("row cap hit — the group-by is wider than expected")
    return r["rows"]


def fold(market_ids: list[int], outcome_ids: list[int], depth: int = 0) -> list:
    pop = _calibration_population_ctes(
        market_info_extra="AND fm.id IN (" + ",".join(str(i) for i in market_ids) + ")"
    )
    # `deduped` is the producer's final published population. Grouping it by the
    # golf-arm expression and by plan membership answers, in one query, both
    # "which arm did these markets land in" and "how many of the repriced legs
    # actually reach the curve".
    sql = _strip_sql_comments(
        "WITH " + pop + f"""
SELECT {GOLFROUND_EXPR} AS arm,
       (d.outcome_id IN ({",".join(str(i) for i in outcome_ids)})) AS repriced,
       COUNT(*) AS n,
       SUM(CASE WHEN d.is_winner THEN 1 ELSE 0 END) AS w,
       ROUND(SUM(d.adj_opening_probability)::numeric, 6) AS sp
FROM deduped d
{GOLFROUND_JOIN}
GROUP BY 1, 2
ORDER BY 1, 2"""
    )
    print(f"   [{depth}] {len(market_ids)} markets, sql {len(sql)} chars",
          file=sys.stderr)
    try:
        return db_query(sql)
    except QueryTimeout:
        if len(market_ids) <= 1:
            raise
        mid = len(market_ids) // 2
        print(f"   [{depth}] timed out — splitting {len(market_ids)} markets",
              file=sys.stderr)
        return (fold(market_ids[:mid], outcome_ids, depth + 1)
                + fold(market_ids[mid:], outcome_ids, depth + 1))


def main() -> int:
    plan = json.load(open(sys.argv[1]))["result"]["planned"]
    market_ids = sorted({r["market_id"] for r in plan})
    outcome_ids = sorted({r["outcome_id"] for r in plan})

    rows = fold(market_ids, outcome_ids)
    # Chunks are disjoint on market_id, so the arm x repriced cells add.
    agg: dict[tuple, list] = {}
    for arm, repriced, n, w, sp in rows:
        cell = agg.setdefault((arm, bool(repriced)), [0, 0, 0.0])
        cell[0] += int(n)
        cell[1] += int(w)
        cell[2] += float(sp)
    print("arm\trepriced\tn\tw\tsum_prob\tavg_px\trate")
    for (arm, repriced), (n, w, sp) in sorted(agg.items()):
        print(f"{arm}\t{repriced}\t{n}\t{w}\t{sp:.3f}\t{sp / n:.4f}\t{w / n:.4f}")
    json.dump(
        {"market_ids": market_ids, "planned_outcomes": len(outcome_ids),
         "chunks": len(rows),
         "cells": [{"arm": a, "repriced": r, "n": n, "w": w, "sum_prob": sp}
                   for (a, r), (n, w, sp) in sorted(agg.items())]},
        open(sys.argv[2], "w"),
        indent=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
