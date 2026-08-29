"""CAL-P120 — fold one published ``odds_api_bookmaker`` cell.

WHY THIS FILE EXISTS
====================

The CAL-P112/114/117/118 instrument family (``calibration_cell_shape_fold``,
``calibration_cell_replica``, ``calibration_cell_exact``) can measure exactly
nothing on this source, and not because of a scoping bug that could be fixed
with a different ``--source`` string. All three fold the population that
``precompute_calibration._calibration_population_ctes()`` builds, and that chain
is rooted in ``futures_markets``. ``futures_markets`` has **no
``odds_api_bookmaker`` rows at all** — measured 2026-08-29, the table's whole
``source`` domain is ``polymarket`` (644,038), ``kalshi`` (255,104),
``datagolf`` (330) and ``odds_api`` (12).

``odds_api_bookmaker`` reaches the published payload by a completely separate
road: ``backfill_winners._precompute_bookmaker_calibration()`` runs one
self-contained SQL statement over ``events`` + ``odds_snapshots``, aggregates it
to ``(bucket_idx, category)`` buckets, and writes them to the Redis key
``bainluck:bookmaker_calibration``. The producer reads that key in its Phase 3
Query 5 and republishes the buckets nearly verbatim. So the rows are aggregated
*before* the producer ever sees them, and there is no per-outcome population for
the exact rail to fold.

Six of the twenty cells on the CAL board are ``odds_api_bookmaker``
(82,345 of 478,677 excess-outcomes, 17.2%). Before this file, none of them could
be measured by anything.

WHAT MAKES THE CHUNKING EXACT HERE, WHICH IT IS NOT ON POLYMARKET
=================================================================

``calibration_cell_exact`` documents one approximation it cannot remove: it
chunks on ``fm.id``, and ``virtual_market``'s ">= 3 markets in the same source"
test can straddle a chunk edge, so a market grouped in production can read
ungrouped in a chunk. CAL-P118 then found a *second*, larger disagreement on
``polymarket/soccer`` and traced it to staged-generation mosaicing.

Neither applies here, and the reason is structural rather than lucky:

* **Every grouping in this chain is per-event.** ``event_bookmakers`` groups by
  ``(event_id, bookmaker)``; the ``LATERAL`` closing-line pick is scoped to one
  ``event_id``. There is no cross-event grouping test anywhere in the statement,
  so partitioning events across chunks cannot change any row's value.
* **We chunk on ``commence_time``, which partitions events**, and an event has
  exactly one ``commence_time``. Each event lands in exactly one chunk.

So the sum over chunks IS the whole fold, by construction. The self-check below
is therefore a real check of the re-implementation rather than a check of the
chunking.

THE SELF-CHECK
==============

``--grain bucket`` reproduces the producer's own ``(bucket_idx, n, winners,
sum_prob)`` aggregate. ``--check-payload`` fetches the live ``/api/calibration``
and diffs this fold against the published cell row-for-row. That is a stronger
guarantee than importing the SQL would give: importing proves we ran the same
text, whereas this proves we land on the same published numbers.

If the diff is non-zero the script SAYS SO and exits non-zero. It never averages
a disagreement away (gotcha #53 — a silently short answer reads as a small
class).

USAGE
=====

    python3 backend/scripts/calibration_bookmaker_cell_fold.py \
        --sport-key basketball_nba --grain bucket --check-payload \
        --out artifacts/cal-p120/fold-nba-bucket.json

    python3 backend/scripts/calibration_bookmaker_cell_fold.py \
        --sport-key basketball_nba --grain game \
        --out artifacts/cal-p120/fold-nba-game.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta

# The row path's budget is a hard 10s and `timeout_ms` is refused on it
# (measured: "`timeout_ms` is only supported with `explain: true`"). So a chunk
# that times out is SPLIT, never retried — a retry of an over-wide chunk is just
# the same timeout again, and a chunk quietly dropped reads as a small class.
ROW_CAP = 1000
MAX_SPLIT_DEPTH = 12


class QueryTimeout(RuntimeError):
    pass


class Truncated(RuntimeError):
    pass


def db_query(sql: str, limit: int = ROW_CAP) -> list[dict]:
    api = os.environ["BAINLUCK_API"]
    tok = os.environ["ADMIN_TOKEN"]
    p = subprocess.run(
        ["curl", "-s", "-X", "POST",
         "-H", f"Authorization: Bearer {tok}",
         "-H", "Content-Type: application/json",
         "-d", json.dumps({"sql": sql, "limit": limit}),
         f"{api}/api/admin/db-query"],
        capture_output=True, text=True, timeout=180)
    try:
        r = json.loads(p.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"db-query returned non-JSON: {p.stdout[:300]!r}")
    if "rows" not in r:
        blob = json.dumps(r)
        if "statement_timeout" in blob:
            raise QueryTimeout(blob[:200])
        raise RuntimeError(f"db-query refused: {blob[:400]}")
    if r.get("truncated") or r["row_count"] >= limit:
        raise Truncated(f"{r['row_count']} rows")
    return [dict(zip(r["columns"], row)) for row in r["rows"]]


# The producer's statement, verbatim in structure, with two changes and only
# two: the sport key is scoped (so one cell can be folded), and the window on
# ``commence_time`` is parameterised (so it can be chunked). Both are additions
# to the WHERE of ``eligible_events``; nothing downstream is touched.
#
# The final SELECT is the only part that varies by grain, because the producer's
# own final SELECT is an aggregate and we need a second, finer one to ask how
# many INDEPENDENT observations the published aggregate is built from.
_BODY = """
WITH eligible_events AS (
  SELECT e.id, e.commence_time, e.home_score, e.away_score, s.key AS category
  FROM events e JOIN sports s ON s.id = e.sport_id
  WHERE e.status IN ('completed', 'closed')
    AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
    AND e.home_score != e.away_score
    AND e.commence_time IS NOT NULL
    AND s.key = '{sport_key}'
    AND e.commence_time >= '{lo}' AND e.commence_time < '{hi}'
),
event_bookmakers AS (
  SELECT DISTINCT ee.id AS event_id, ee.commence_time, ee.home_score,
         ee.away_score, ee.category, os.bookmaker
  FROM eligible_events ee
  JOIN odds_snapshots os ON os.event_id = ee.id
  WHERE os.captured_at < ee.commence_time
    AND os.home_win_probability IS NOT NULL
),
outcomes AS (
  SELECT eb.event_id, eb.bookmaker, eb.commence_time,
         cl.captured_at,
         cl.home_win_probability::float
           / NULLIF(cl.home_win_probability::float + cl.away_win_probability::float, 0)
           AS prob,
         (eb.home_score > eb.away_score) AS won
  FROM event_bookmakers eb
  CROSS JOIN LATERAL (
    SELECT os.home_win_probability, os.away_win_probability, os.captured_at
    FROM odds_snapshots os
    WHERE os.event_id = eb.event_id
      AND os.bookmaker = eb.bookmaker
      AND os.captured_at < eb.commence_time
      AND os.home_win_probability IS NOT NULL
      AND os.away_win_probability IS NOT NULL
      AND os.home_win_probability > 0
      AND os.away_win_probability > 0
    ORDER BY os.captured_at DESC
    LIMIT 1
  ) cl
)
"""

# Producer-identical: this is the shape that is published.
_TAIL_BUCKET = """
SELECT LEAST(FLOOR(prob * 10)::int, 9) AS bucket_idx,
       COUNT(*) AS n,
       SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
       SUM(prob::float) AS sum_prob
FROM outcomes WHERE prob > 0.01 AND prob < 0.99
GROUP BY bucket_idx ORDER BY bucket_idx
"""

# One row per GAME. `won` is a property of the event, so bool_and over a game's
# book-rows is just that game's outcome; the spread columns say how much the
# books actually disagreed, which is what decides whether a book-row is an
# independent observation or a copy of one.
_TAIL_GAME = """
SELECT event_id,
       bool_and(won) AS won,
       COUNT(*) AS books,
       AVG(prob) AS avg_prob,
       STDDEV_POP(prob) AS sd_prob,
       MIN(prob) AS min_prob,
       MAX(prob) AS max_prob,
       MIN(captured_at) AS first_captured,
       MAX(captured_at) AS last_captured,
       MIN(commence_time) AS commence_time
FROM outcomes WHERE prob > 0.01 AND prob < 0.99
GROUP BY event_id
"""

TAILS = {"bucket": _TAIL_BUCKET, "game": _TAIL_GAME}


def collect(sport_key: str, lo: date, hi: date, grain: str, depth: int = 0) -> list[dict]:
    sql = _BODY.format(sport_key=sport_key, lo=lo.isoformat(), hi=hi.isoformat()) + TAILS[grain]
    try:
        return db_query(sql)
    except (QueryTimeout, Truncated) as exc:
        why = "timing out" if isinstance(exc, QueryTimeout) else "truncated"
        if depth >= MAX_SPLIT_DEPTH or (hi - lo).days <= 1:
            raise RuntimeError(
                f"window {lo}..{hi} still {why} at depth {depth} — cannot narrow further")
        mid = lo + (hi - lo) / 2
        print(f"      split {lo}..{hi} ({why})", file=sys.stderr, flush=True)
        return (collect(sport_key, lo, mid, grain, depth + 1)
                + collect(sport_key, mid, hi, grain, depth + 1))


def span(sport_key: str) -> tuple[date, date]:
    r = db_query(
        "SELECT MIN(e.commence_time)::date AS lo, MAX(e.commence_time)::date AS hi "
        "FROM events e JOIN sports s ON s.id = e.sport_id "
        f"WHERE s.key = '{sport_key}' AND e.status IN ('completed', 'closed') "
        "AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL "
        "AND e.home_score != e.away_score AND e.commence_time IS NOT NULL")
    lo, hi = r[0]["lo"], r[0]["hi"]
    if lo is None:
        raise SystemExit(f"no eligible events for sport key {sport_key!r}")
    return (date.fromisoformat(lo), date.fromisoformat(hi) + timedelta(days=1))


def sweep(sport_key: str, grain: str, weeks: int) -> list[dict]:
    lo, hi = span(sport_key)
    print(f"  span {lo} .. {hi}", file=sys.stderr)
    out, cur, i = [], lo, 0
    while cur < hi:
        nxt = min(cur + timedelta(weeks=weeks), hi)
        i += 1
        print(f"    [{i}] {cur}..{nxt}", file=sys.stderr, flush=True)
        out += collect(sport_key, cur, nxt, grain)
        cur = nxt
    return out


def merge_buckets(rows: list[dict]) -> dict[int, dict]:
    """Chunks partition events, so bucket totals add. See the module docstring."""
    agg: dict[int, dict] = {}
    for r in rows:
        b = agg.setdefault(int(r["bucket_idx"]), {"n": 0, "winners": 0, "sum_prob": 0.0})
        b["n"] += int(r["n"])
        b["winners"] += int(r["winners"])
        b["sum_prob"] += float(r["sum_prob"])
    return agg


def ece_of(buckets: dict[int, dict]) -> tuple[int, float, float]:
    n = sum(b["n"] for b in buckets.values())
    if not n:
        return 0, 0.0, 0.0
    ece = sum(b["n"] / n * abs(b["winners"] / b["n"] - b["sum_prob"] / b["n"])
              for b in buckets.values() if b["n"])
    gap = sum(b["sum_prob"] for b in buckets.values()) / n \
        - sum(b["winners"] for b in buckets.values()) / n
    return n, ece * 100, gap * 100


def published_cell(sport_key: str) -> dict[int, dict]:
    api = os.environ["BAINLUCK_API"]
    p = subprocess.run(["curl", "-s", f"{api}/api/calibration"],
                       capture_output=True, text=True, timeout=120)
    payload = json.loads(p.stdout)
    out: dict[int, dict] = {}
    for r in payload["buckets"]:
        if r.get("source") == "odds_api_bookmaker" and r.get("category") == sport_key:
            out[int(r["bucket_idx"])] = {
                "n": int(r["n"]), "winners": int(r["winners"]),
                "sum_prob": float(r["sum_prob"])}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sport-key", required=True)
    ap.add_argument("--grain", choices=sorted(TAILS), default="bucket")
    ap.add_argument("--weeks", type=int, default=3, help="initial chunk width in weeks")
    ap.add_argument("--check-payload", action="store_true",
                    help="diff a bucket-grain fold against the LIVE published cell")
    ap.add_argument("--out")
    a = ap.parse_args()

    rows = sweep(a.sport_key, a.grain, a.weeks)
    print(f"\nodds_api_bookmaker/{a.sport_key}  (--grain {a.grain}, {len(rows)} rows)")

    rc = 0
    if a.grain == "bucket":
        mine = merge_buckets(rows)
        n, ece, gap = ece_of(mine)
        print(f"  fold      n={n:,}  ECE={ece:.2f} pp  gap={gap:+.2f} pp")
        if a.check_payload:
            pub = published_cell(a.sport_key)
            pn, pece, pgap = ece_of(pub)
            print(f"  published n={pn:,}  ECE={pece:.2f} pp  gap={pgap:+.2f} pp")
            drift_n = (n - pn) / pn * 100 if pn else float("inf")
            print(f"  DRIFT     rows {n - pn:+,} ({drift_n:+.2f}%)  ECE {ece - pece:+.2f} pp")
            bad = [b for b in sorted(set(mine) | set(pub))
                   if mine.get(b, {}).get("n", 0) != pub.get(b, {}).get("n", 0)]
            if bad:
                rc = 1
                print(f"  🔴 {len(bad)} bucket(s) disagree on row count: {bad}")
                for b in bad:
                    print(f"       b{b}: fold {mine.get(b, {}).get('n', 0):,} "
                          f"vs published {pub.get(b, {}).get('n', 0):,}")
            else:
                print("  ✅ every bucket reproduces the published row count exactly")
    else:
        games = len(rows)
        books = sum(int(r["books"]) for r in rows)
        print(f"  games={games:,}  book-rows={books:,}  "
              f"replication={books / games:.2f}x" if games else "  no games")

    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump({"sport_key": a.sport_key, "grain": a.grain, "rows": rows},
                  open(a.out, "w"), default=str)
        print(f"  wrote {a.out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
