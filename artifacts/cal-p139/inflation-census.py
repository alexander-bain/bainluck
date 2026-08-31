"""CAL-P139 — the duplication factor of every published cell, cheaply.

``outcome-grain-fold.py`` answers the same question exactly and also gives the
deduplicated ECE, but it emits ONE ROW PER OUTCOME and db-query's 1,000-row cap
then splits every dense chunk many times over. Measured: ``polymarket/baseball``
(25k distinct outcomes) took 11 minutes; ``kalshi/baseball`` (~100k) was still
inside its ninth chunk after ten and was abandoned.

This instrument asks the same population for **two scalars per chunk** instead —
``COUNT(*)`` and ``COUNT(DISTINCT outcome_id)`` — so the row cap can never bind
and a whole cell costs about as much as one chunk of the fold. It cannot give
the deduplicated ECE; it gives the INFLATION, which is the number that says
whether the ECE fold is worth 11 minutes.

Summing across chunks is sound because the chunk key is ``fm.id`` and an outcome
belongs to exactly one market: no outcome can be counted in two chunks, so the
per-chunk distinct counts add.

⚠️ Same floor as the fold: restricting ``market_info`` to an id range can drop a
group below the ``>= 3`` threshold and collapse its ``vm_id`` to the per-market
``m:`` arm, which has one identity and therefore no duplication. Chunking loses
duplicates; it cannot invent them.

Usage::

    source ~/.claude/.env && python3 artifacts/cal-p139/inflation-census.py \\
        kalshi/baseball polymarket/soccer kalshi/economics
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "scripts"))

import calibration_cell_exact as cce  # noqa: E402
from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
)

WIDTH = 1_000_000


def chunk_sql(source, category, lo, hi):
    pop = _calibration_population_ctes(
        market_info_extra=(
            f"AND fm.source = '{source}' "
            f"AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{category}' "
            f"AND fm.id >= {lo} AND fm.id < {hi}"
        )
    )
    return cce._strip_sql_comments(
        "WITH " + pop + """
SELECT COUNT(*) AS rows_published,
       COUNT(DISTINCT d.outcome_id) AS distinct_outcomes,
       COUNT(DISTINCT d.market_id) AS distinct_markets
FROM deduped d"""
    )


def cell(source, category, depth_limit=18):
    rng = cce.db_query(
        f"SELECT MIN(id) AS lo, MAX(id) AS hi FROM futures_markets "
        f"WHERE source = '{source}'", limit=5)
    lo, hi = int(rng["rows"][0][0]), int(rng["rows"][0][1]) + 1
    rows = dist = mkts = 0
    t0 = time.time()
    edges = list(range(lo, hi, WIDTH)) + [hi]

    def run(a, b, depth=0):
        nonlocal rows, dist, mkts
        sql = chunk_sql(source, category, a, b)
        if len(sql) > cce.MAX_SQL_CHARS:
            raise RuntimeError("static SQL over the cap — impossible here")
        try:
            r = cce.db_query(sql, limit=10)
        except cce.QueryTimeout:
            if depth > depth_limit or b - a <= 1:
                raise
            mid = a + (b - a) // 2
            run(a, mid, depth + 1)
            run(mid, b, depth + 1)
            return
        v = [int(x or 0) for x in r["rows"][0]]
        rows += v[0]
        dist += v[1]
        mkts += v[2]

    for i in range(len(edges) - 1):
        run(edges[i], edges[i + 1])
        print(f"    [{i + 1}/{len(edges) - 1}] rows={rows} distinct={dist} "
              f"({time.time() - t0:.0f}s)", flush=True)
    return {"cell": f"{source}/{category}", "rows_published": rows,
            "distinct_outcomes": dist, "distinct_markets": mkts,
            "inflation": round(rows / dist, 4) if dist else None,
            "seconds": round(time.time() - t0, 1)}


def main(argv):
    out = {}
    path = os.path.join(HERE, "inflation-census.json")
    if os.path.exists(path):
        out = json.load(open(path))
    for spec in argv:
        source, _, category = spec.rpartition("/")
        print(f"\n=== {spec}", flush=True)
        d = cell(source or "polymarket", category)
        pn, pece, pgap, meta = cce.payload_cell(source, category)
        d["payload_n"] = pn
        d["payload_ece"] = pece
        d["replica_vs_payload_pct"] = (
            round((d["rows_published"] - pn) / pn * 100, 3) if pn else None)
        out[spec] = d
        print(f"  rows={d['rows_published']}  distinct={d['distinct_outcomes']}"
              f"  INFLATION {d['inflation']}x   payload n={pn} "
              f"({d['replica_vs_payload_pct']:+}% replica vs payload)")
        with open(path, "w") as fh:
            json.dump(out, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
