"""Cache one row per Polymarket market with ALL THREE price legs, not just YES.

CAL-P135 measured the NAME site's blindness on four Polymarket sports cells and
named two remaining blockers (its README §4). This is the row pull both of them
need, and it is separated from the analysis on purpose: the pull is ~25 minutes
of production load and the analysis was iterated a dozen times against it.

The one difference from ``artifacts/cal-p135/polymarket-name-ladder-census.py``'s
``ROWS_SQL`` is the two extra columns. ``MONO_ROWS_SQL`` in
``calibration_cell_exact.py`` reads a leg literally named ``yes``; Polymarket's
two-sided totals book prices ``Over``/``Under`` instead, so the rail computes a
NULL price and drops the row before any grammar runs. Pulling ``over`` and
``under`` side by side with ``yes`` is what lets the analysis measure, rather
than assume, which leg a market actually carries — and carrying ``under`` as
well as ``over`` is not redundancy: ``over + under`` is an arithmetic check on
whether the pair is a real two-sided price at all, which is the only handle
anyone has on CAL-P135-2's unexplained flat rate.

Usage:  python3 artifacts/cal-p136/pull_rows.py [category ...]
"""
import gzip
import json
import os
import subprocess
import sys

API = os.environ["BAINLUCK_API"]
TOK = os.environ["ADMIN_TOKEN"]
CAP = 1000
HERE = os.path.dirname(os.path.abspath(__file__))

#: Ids are pulled in windows of this width and each window halves on the row
#: cap. Matches the width CAL-P135 measured as reaching the whole source
#: without an irreducible chunk.
WIDTH = 1_000_000


def q(sql, limit=CAP):
    r = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{API}/api/admin/db-query",
         "-H", f"Authorization: Bearer {TOK}", "-H", "Content-Type: application/json",
         "-d", json.dumps({"sql": sql, "limit": limit})],
        capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        raise RuntimeError(r.stdout[:400])


ROWS_SQL = """
SELECT fm.id AS market_id,
       MAX(fm.name) AS name,
       MAX(fm.group_id) AS group_id,
       MAX(fm.event_id) AS event_id,
       MAX(CASE WHEN lower(btrim(fo.name)) = 'yes'
                THEN COALESCE(fo.calibration_probability, fo.opening_probability)
           END) AS yes_price,
       MAX(CASE WHEN lower(btrim(fo.name)) = 'over'
                THEN COALESCE(fo.calibration_probability, fo.opening_probability)
           END) AS over_price,
       MAX(CASE WHEN lower(btrim(fo.name)) = 'under'
                THEN COALESCE(fo.calibration_probability, fo.opening_probability)
           END) AS under_price
FROM futures_markets fm
JOIN futures_outcomes fo ON fo.market_id = fm.id
WHERE fm.source = 'polymarket'
  AND COALESCE(fm.llm_sport_category, 'uncategorized') = '{cat}'
  AND fm.id >= {lo} AND fm.id < {hi}
GROUP BY fm.id
"""


def pull(cat, lo, hi, depth=0):
    """Rows in an id range, halving on the 1000-row cap (never trust exactly CAP)."""
    d = q(ROWS_SQL.format(cat=cat, lo=lo, hi=hi))
    if "rows" in d and d.get("row_count", CAP) < CAP:
        return d["rows"]
    if hi - lo <= 1 or depth > 30:
        raise RuntimeError(f"irreducible {lo}-{hi}")
    mid = lo + (hi - lo) // 2
    return pull(cat, lo, mid, depth + 1) + pull(cat, mid, hi, depth + 1)


def path_for(cat):
    return os.path.join(HERE, f"legs-polymarket-{cat}.json.gz")


def load_rows(cat):
    """Cached row pull. Re-analysis after the first pull is free."""
    path = path_for(cat)
    if os.path.exists(path):
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    rng = q("SELECT MIN(id), MAX(id) FROM futures_markets WHERE source='polymarket'",
            limit=5)
    lo, hi = rng["rows"][0]
    rows, e, n = [], lo, 0
    while e <= hi:
        nxt = min(e + WIDTH, hi + 1)
        n += 1
        print(f"    pull [{n}] ids {e}-{nxt}", file=sys.stderr, flush=True)
        rows.extend(pull(cat, e, nxt))
        e = nxt
    with gzip.open(path, "wt") as fh:
        json.dump(rows, fh)
    return rows


COLUMNS = ("market_id", "name", "group_id", "event_id",
           "yes_price", "over_price", "under_price")


def as_dicts(cat):
    """The cached rows as dicts. db-query rows are ARRAYS, positional to COLUMNS."""
    return [dict(zip(COLUMNS, r)) for r in load_rows(cat)]


if __name__ == "__main__":
    for cat in sys.argv[1:] or ["baseball", "esports", "soccer", "basketball"]:
        print(f"=== polymarket/{cat}", file=sys.stderr, flush=True)
        rows = load_rows(cat)
        print(f"{cat}: {len(rows)} rows -> {path_for(cat)}", flush=True)
    print("PULL COMPLETE", flush=True)
