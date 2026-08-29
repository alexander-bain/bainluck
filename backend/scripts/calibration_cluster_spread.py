#!/usr/bin/env python3
"""CAL-P124 — measure how far a cell's virtual-question clusters are SCATTERED in market id.

Ruling 134 note: read-only instrument. It writes nothing, it re-implements no
part of the published population, and ``git diff origin/master -- backend/app``
is empty on the branch that carries it. Ruling 009 freezes commits to
``precompute_calibration.py``; this file does not even import it.

WHY THIS FILE EXISTS
--------------------
``calibration_cell_exact.py`` folds a cell by chunking on ``fm.id`` in fixed
id-width ranges, and it re-derives ``virtual_market`` inside every chunk. The
producer's own docstring says exactly what that costs
(``precompute_calibration.py``, ``_virtual_market_ctes``):

    ... a chunk holding fewer than 3 would see the event collapse below the
    gate entirely, silently re-assigning every one of its markets to ``m:`` —
    a different question identity, a different representative, a different
    bucket.

A market re-assigned to ``m:`` is its own virtual question, takes the
non-multi ``rn = 1`` branch, and publishes ONE row where the grouped market
published many. So a shattered cluster does not corrupt rows — it DELETES
them, and it deletes them roughly uniformly with respect to price, which is
why the loss is invisible in a bucket-shape check.

That is a hypothesis about a cell's DATA LAYOUT, and this file measures it
directly instead of inferring it from a fold that already cost four minutes.

WHAT ``--edge-check`` CANNOT SEE, AND WHY THIS IS NOT REDUNDANT WITH IT
-----------------------------------------------------------------------
``calibration_cell_exact.py --edge-check`` re-runs the fold at HALF the chunk
width and flags a disagreement. It is a MARGINAL test, and on a cell whose
clusters are scattered over tens of millions of ids it is close to useless:
halving 1,000,000 to 500,000 does not un-shatter a cluster whose members span
31,000,000. Measured on ``polymarket/basketball`` (CAL-P124):

    exact replica    n = 8,426     (chunk width 1,000,000)
    edge check       n = 8,421     (chunk width   500,000)   -> "5 rows"
    published cell   n = 13,135                              -> -35.85%

The edge check reported a 5-row sensitivity on a cell the rail was missing by
4,709 rows. It was not wrong; it answered the question it asks, which is
"does the ANSWER move when the width moves", not "is the width small enough".
This file answers the second question, and it answers it in about eight
seconds without folding anything.

THE FOUR MEASURED POINTS (CAL-P124)
-----------------------------------
Reproduction shortfall is the fold's own SELF-CHECK line, exact replica
against the served payload, all four on curve ``q268``:

    cell                     markets in wide clusters   reproduction shortfall
    polymarket/cricket                    7.0%                    -0.18%
    polymarket/soccer                    14.2%                    -5.06%
    polymarket/baseball                  32.2%                    -5.70%
    polymarket/basketball                93.1%                   -35.85%

**Monotone on four of four.** This retires the standing "Polymarket is 5-6%
short" budget as a source-level constant: it is not a property of the venue,
it is a property of how id-scattered a particular cell's groups are, and the
two cells that motivated the 5-6% figure sit at 14.2% and 32.2% on this axis
rather than at cricket's 7.0%.

**n = 4 is a correlation, not a calibration.** :func:`risk_band` therefore
returns a QUALITATIVE band with the evidence attached, and deliberately does
not interpolate a predicted percentage. A queue that wants a number runs the
fold; what this file buys is knowing whether the fold's number can be trusted
BEFORE spending four minutes on it.

USAGE
-----
::

    source ~/.claude/.env
    python3 backend/scripts/calibration_cluster_spread.py \\
        --source polymarket --category basketball
    python3 backend/scripts/calibration_cluster_spread.py \\
        --source polymarket --category basketball --width 500000 --json out.json

``--width`` must match the chunk width the fold will actually use, because
"wide" means "wider than one chunk" and nothing else. The default matches
``calibration_cell_exact.DEFAULT_WIDTH``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#: Mirrors ``calibration_cell_exact.DEFAULT_WIDTH``. Imported rather than
#: re-declared where possible; the literal is the fallback for the standalone
#: unit tests, which must not need the sibling module on the path.
DEFAULT_WIDTH = 1_000_000

#: The two cluster keys ``virtual_market`` can assign a market to before it
#: falls back to ``m:<market_id>``. Order matters: ``g:`` wins over ``e:``.
CLUSTER_KEYS = ("group_id", "event_id")

#: The ">= 3 eligible markets in the same source" gate, verbatim from
#: ``_virtual_market_ctes``. A cluster below it is never a cluster at all, so
#: it cannot be shattered and must not be counted in the denominator.
GROUPING_GATE = 3


class QueryFailed(RuntimeError):
    """A db-query call that did not return rows. Never swallowed (gotcha #53)."""


def cluster_spread_sql(source: str, category: str, key: str) -> str:
    """One aggregate row: how scattered are this cell's ``key`` clusters.

    Aggregated SERVER-SIDE on purpose. The per-cluster row list for
    ``polymarket/basketball`` is 717 rows and for ``polymarket/soccer`` 7,325 —
    both over the db-query 1,000-row cap, which truncates SILENTLY and would
    read as "this cell has few clusters" rather than as a failure.
    """
    if key not in CLUSTER_KEYS:
        raise ValueError(f"key must be one of {CLUSTER_KEYS}, got {key!r}")
    # Literal interpolation is confined to an allowlisted column name and two
    # caller-supplied identifiers that are quote-escaped below.
    src = source.replace("'", "''")
    cat = category.replace("'", "''")
    return f"""
SELECT COUNT(*) AS clusters,
       COALESCE(SUM(c), 0) AS markets,
       COALESCE(SUM(CASE WHEN spread >= {{width}} THEN c ELSE 0 END), 0) AS markets_in_wide,
       COALESCE(SUM(CASE WHEN spread >= {{width}} THEN 1 ELSE 0 END), 0) AS wide_clusters,
       COALESCE(MAX(spread), 0) AS max_spread,
       COALESCE(MAX(c), 0) AS max_size
FROM (
    SELECT {key}, MAX(id) - MIN(id) AS spread, COUNT(*) AS c
    FROM futures_markets
    WHERE source = '{src}'
      AND COALESCE(llm_sport_category, 'uncategorized') = '{cat}'
      AND {key} IS NOT NULL
    GROUP BY {key}
    HAVING COUNT(*) >= {GROUPING_GATE}
) t
""".strip()


def pct_in_wide(markets: int, markets_in_wide: int) -> float | None:
    """Share of clustered markets living in a cluster wider than one chunk.

    ``None`` when there are no clustered markets at all — that is "this cell
    has no clusters to shatter", which is a DIFFERENT statement from "0% of
    them are shattered", and rendering it as 0.0 would read as a clean bill of
    health for a cell nobody measured.
    """
    if markets < 0 or markets_in_wide < 0:
        raise ValueError("counts must be non-negative")
    if markets_in_wide > markets:
        raise ValueError("markets_in_wide cannot exceed markets")
    if markets == 0:
        return None
    return round(100.0 * markets_in_wide / markets, 1)


def risk_band(pct: float | None) -> str:
    """Qualitative reproduction risk for a fold chunked at this width.

    Deliberately coarse. The four measured points (see the module docstring)
    are monotone but they are four points, and a queue that reads an
    interpolated "predicted -18.4%" off an n=4 curve will believe it.
    """
    if pct is None:
        return "NO_CLUSTERS"
    if pct < 0:
        raise ValueError("pct must be non-negative")
    if pct < 10.0:
        return "LOW"
    if pct < 35.0:
        return "MODERATE"
    if pct < 60.0:
        return "HIGH"
    return "SEVERE"


#: What each band means for a fold, in the terms the board actually uses.
BAND_GUIDANCE = {
    "NO_CLUSTERS": "no >=3 clusters in this cell; id-range chunking cannot shatter anything",
    "LOW": "id-range chunking is close to harmless here (cricket, 7.0% -> -0.18%)",
    "MODERATE": "expect a single-digit shortfall (soccer 14.2% -> -5.06%, baseball 32.2% -> -5.70%)",
    "HIGH": "extrapolating past the measured points; fold the cell only with the shortfall stated",
    "SEVERE": "the fold does not reach this cell (basketball 93.1% -> -35.85%); treat it as UNMEASURED",
}


def db_query(sql: str, limit: int = 50, retries: int = 3) -> dict:
    """POST /api/admin/db-query, or raise. Never returns a partial answer quietly."""
    base = os.environ.get("BAINLUCK_API")
    token = os.environ.get("ADMIN_TOKEN")
    if not base or not token:
        raise QueryFailed(
            "BAINLUCK_API / ADMIN_TOKEN are unset — run with "
            "`source ~/.claude/.env && ...` in the SAME command (gotcha #124)"
        )
    body = json.dumps({"sql": sql, "limit": limit}).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/api/admin/db-query",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    last = ""
    for _ in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as fh:
                d = json.loads(fh.read().decode())
            if "rows" not in d:
                last = json.dumps(d)[:400]
                continue
            return d
        except urllib.error.HTTPError as e:  # noqa: PERF203 — retries are the point
            last = f"HTTP {e.code}: {e.read()[:300]!r}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {str(e)[:300]}"
    raise QueryFailed(f"db-query failed after {retries} attempts: {last}")


def measure(source: str, category: str, width: int) -> dict:
    """Both cluster keys for one cell."""
    out: dict = {"source": source, "category": category, "width": width, "by_key": {}}
    for key in CLUSTER_KEYS:
        sql = cluster_spread_sql(source, category, key).format(width=width)
        r = db_query(sql)
        if not r["rows"]:
            raise QueryFailed(f"{key}: db-query returned no aggregate row")
        rec = dict(zip(r["columns"], r["rows"][0]))
        # db-query serialises bigints as strings (memory: rows are ARRAYS, and
        # SUM() of a bigint comes back quoted).
        rec = {k: int(v) if isinstance(v, str) and v.lstrip("-").isdigit() else v
               for k, v in rec.items()}
        rec["pct_in_wide"] = pct_in_wide(rec["markets"], rec["markets_in_wide"])
        rec["risk"] = risk_band(rec["pct_in_wide"])
        out["by_key"][key] = rec
    worst = max(
        (v for v in out["by_key"].values() if v["pct_in_wide"] is not None),
        key=lambda v: v["pct_in_wide"],
        default=None,
    )
    out["worst_key"] = None if worst is None else worst
    out["risk"] = "NO_CLUSTERS" if worst is None else worst["risk"]
    return out


def render(out: dict) -> str:
    lines = [
        f"{out['source']}/{out['category']}   cluster spread at chunk width {out['width']:,}",
        "",
        f"  {'key':<10} {'clusters':>9} {'markets':>9} {'in wide':>9} "
        f"{'% wide':>7} {'max spread':>12} {'max size':>9}  risk",
    ]
    for key, r in out["by_key"].items():
        pct = "—" if r["pct_in_wide"] is None else f"{r['pct_in_wide']:.1f}%"
        lines.append(
            f"  {key:<10} {r['clusters']:>9,} {r['markets']:>9,} {r['markets_in_wide']:>9,} "
            f"{pct:>7} {r['max_spread']:>12,} {r['max_size']:>9,}  {r['risk']}"
        )
    lines += ["", f"  VERDICT  {out['risk']} — {BAND_GUIDANCE[out['risk']]}"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH,
                    help="the chunk width the FOLD will use; 'wide' means wider than this")
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()
    if args.width < 1:
        ap.error("--width must be >= 1")
    out = measure(args.source, args.category, args.width)
    print(render(out))
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump(out, fh, indent=1)
        print(f"\n  wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
