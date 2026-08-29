#!/usr/bin/env python3
"""CAL-P129 — name the Kalshi series behind the shape-incoherent one-winner fields.

The RAIL (``calibration_cell_exact.py --by sumband``) is what measures the
defect: on ``kalshi/entertainment`` the ``field1`` arms are monotone in their
own price sum, 1.67 -> 9.21 -> 25.21 -> 47.87 pp, one-directional, on BOTH
holdout halves. That is the authoritative measurement and this script does not
reproduce it.

This script answers the different, cheaper question the writer lane needs:
*which Kalshi series are these?* It is a COMPOSITION census, not a bench.

🔴 ITS POPULATION IS BROADER THAN THE PUBLISHED CELL. It applies no liquidity
filter, no no-winner filter, none of the producer's exclusions -- only
``calibration_probability IS NOT NULL AND is_winner IS NOT NULL``. So its
outcome counts are an upper envelope and must never be quoted as the cell's.
The published figure is the rail's: 1,228 of 8,480 rows (14.5%).

Chunked on ``fm.id`` because the ungrouped join exceeds the row path's hard 10 s
budget. A chunk that times out is SPLIT, never dropped and never retried
(gotcha #53) -- the first run's ``fm.id < 20000000`` timed out and is split into
three here; a silently missing chunk would read as "that id range is clean".
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

#: Split so that every chunk returned inside the 10 s budget on 2026-08-29.
#: The first three are one chunk that timed out, split rather than retried.
CHUNKS = [
    "fm.id < 2000000",
    "fm.id >= 2000000 AND fm.id < 5000000",
    "fm.id >= 5000000 AND fm.id < 7000000",
    "fm.id >= 7000000 AND fm.id < 9000000",
    "fm.id >= 9000000 AND fm.id < 10500000",
    "fm.id >= 10500000 AND fm.id < 12000000",
    "fm.id >= 12000000 AND fm.id < 20000000",
    "fm.id >= 20000000 AND fm.id < 26000000",
    "fm.id >= 26000000 AND fm.id < 33000000",
    "fm.id >= 33000000 AND fm.id < 40000000",
    "fm.id >= 40000000 AND fm.id < 50000000",
    "fm.id >= 50000000 AND fm.id < 55000000",
    "fm.id >= 55000000",
]

#: ``nwin = 1`` is the "exactly one outcome won" shape -- the rail's ``field1``.
#: ``psum > 2`` is the incoherence: a one-winner field whose prices sum to more
#: than 2 is claiming more than two certainties where reality supplies one.
SQL = """
SELECT split_part(fm.external_id, '-', 1) AS series,
       COUNT(*) AS markets,
       SUM(s.k) AS outcomes,
       ROUND(AVG(s.psum)::numeric, 2) AS avg_price_sum,
       ROUND(AVG(s.k)::numeric, 1) AS avg_outcomes_per_market
FROM futures_markets fm
JOIN (SELECT fo.market_id,
             SUM(fo.calibration_probability) AS psum,
             COUNT(*) AS k,
             COUNT(*) FILTER (WHERE fo.is_winner) AS nwin
      FROM futures_outcomes fo
      WHERE fo.calibration_probability IS NOT NULL
        AND fo.is_winner IS NOT NULL
      GROUP BY fo.market_id) s ON s.market_id = fm.id
WHERE fm.source = 'kalshi'
  AND fm.llm_sport_category = 'entertainment'
  AND {chunk}
  AND s.nwin = 1
  AND s.psum > 2
GROUP BY 1
ORDER BY outcomes DESC
"""


def query(sql: str) -> dict:
    base = os.environ.get("BAINLUCK_API", "https://api.bainluck.com").rstrip("/")
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise SystemExit("ADMIN_TOKEN unset — `source ~/.claude/.env` in the SAME command")
    req = urllib.request.Request(
        f"{base}/api/admin/db-query",
        data=json.dumps({"sql": " ".join(sql.split()), "limit": 60}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read() or b"{}")}


#: Per-chunk results, cached across runs. Chunk timeouts on this query are
#: LOAD-dependent, not size-dependent -- three successive runs on 2026-08-29
#: failed on different chunks, including tiny ones that had just succeeded. So
#: re-running the whole sweep to chase one chunk both wastes production budget
#: and never converges. A chunk that has returned once is banked; a run only
#: asks for the ones still missing. This is NOT a retry of a failed query in the
#: same breath -- it is resumption, and the census is still refused as
#: INCOMPLETE until every chunk is present.
CACHE = pathlib.Path(__file__).with_name("incoherent-field-census-chunks.json")


def main() -> int:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for chunk in CHUNKS:
        if chunk in cache:
            continue
        res = query(SQL.format(chunk=chunk))
        if "rows" not in res:
            # LOUD. A dropped chunk reads as a clean id range.
            print(f"CHUNK FAILED (re-run to resume): {chunk}", file=sys.stderr)
            continue
        cache[chunk] = res["rows"]
        CACHE.write_text(json.dumps(cache, indent=2) + "\n")

    per_series: dict[str, dict] = {}
    failures = [{"chunk": c} for c in CHUNKS if c not in cache]
    for chunk in CHUNKS:
        for series, markets, outcomes, avg_sum, avg_k in cache.get(chunk, []):
            # db-query serializes SUM()/numeric as a STRING; COUNT() comes back
            # an int. Coerce both rather than trusting either (memory: rows are
            # ARRAYS and their types are the driver's, not the schema's).
            markets, outcomes = int(markets), int(outcomes)
            e = per_series.setdefault(
                series, {"markets": 0, "outcomes": 0, "weighted_sum": 0.0}
            )
            e["markets"] += markets
            e["outcomes"] += outcomes
            e["weighted_sum"] += float(avg_sum) * markets

    for e in per_series.values():
        e["avg_price_sum"] = round(e.pop("weighted_sum") / e["markets"], 2)

    out = {
        "note": (
            "COMPOSITION census, broader population than the published cell — "
            "no producer exclusions applied. The published figure is the rail's "
            "1,228 of 8,480 rows (14.5%). Never quote these counts as the cell's."
        ),
        "chunks_run": len(CHUNKS),
        "chunks_failed": failures,
        "totals": {
            "series": len(per_series),
            "markets": sum(e["markets"] for e in per_series.values()),
            "outcomes": sum(e["outcomes"] for e in per_series.values()),
        },
        "series": dict(
            sorted(per_series.items(), key=lambda kv: -kv[1]["outcomes"])
        ),
    }
    dest = pathlib.Path(__file__).with_name("incoherent-field-census.json")
    dest.write_text(json.dumps(out, indent=2) + "\n")

    print(f"{'series':<30} {'mkts':>5} {'outcomes':>9} {'avg price sum':>14}")
    for k, e in out["series"].items():
        print(f"{k:<30} {e['markets']:>5} {e['outcomes']:>9} {e['avg_price_sum']:>14.2f}")
    print(f"\ntotals: {out['totals']}")
    if failures:
        print(f"🔴 {len(failures)} CHUNK(S) FAILED — census INCOMPLETE", file=sys.stderr)
        return 1
    print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
