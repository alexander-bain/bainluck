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

    # CAL-P998 — the measured SE, in the sigma ledger's own input shape
    python3 backend/scripts/calibration_bookmaker_cell_fold.py \
        --sport-key basketball_nba --sigma \
        --out artifacts/cal-p998/sigma-bookmaker-basketball_nba.json

THE SIGMA MODE, AND WHY IT IS HERE AND NOT IN ``calibration_cluster_sigma.py``
==============================================================================

CAL-P128's ledger banks a measured cluster-bootstrap SE per cell so the board
stops feeding a row-grain estimate into a standard-error gate. It is fed by
``calibration_cluster_sigma.py``, which drives ``calibration_cell_exact`` --
and therefore cannot see this source at all, for the reason at the top of this
file. So the six ``odds_api_bookmaker`` cells were the only cells on the board
that could not be banked even in principle: **6 of the 14 queued cells on the
2026-09-03 board, 82,345 excess-outcomes.** CAL-P120 derived their game-grain
SE by hand and wrote it in a report; the board has carried them at the row
basis ever since, which is precisely the hand-derivation the ledger exists to
end.

``--sigma`` closes that loop. It adds the one thing that is genuinely this
source's own -- the cluster, which is the GAME -- and imports everything that
decides: ``bootstrap_ece`` and the fold it resamples through, the bars, the
gate, and the entry shape ``calibration_sigma_ledger.entry_from_sigma_json``
already consumes. Nothing about the board's arithmetic is re-implemented for
one source.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

# So `--sigma` can import the board's own bootstrap and bars whether this file
# is run from the repo root, from `backend/`, or loaded by importlib from a
# test. Inserted at import rather than inside the function: a path fixed up
# lazily is a path that is right in the shell and wrong under pytest, which is
# CAL-P129's bug wearing a different hat.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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

# One row per (GAME, decile) — the grain a cluster bootstrap needs, added by
# CAL-P998. `--grain game` collapses a game to one average price, and ~30% of
# games straddle two deciles (403 of NBA's 573 sit entirely inside one), so
# resampling from it would resample a cell this rail does not publish. Keyed by
# the pair, the resample is EXACT: every book-row keeps the bin it was folded
# into, and the games are the units.
_TAIL_GAME_BUCKET = """
SELECT event_id,
       bucket_idx,
       COUNT(*) AS n,
       SUM(CASE WHEN won THEN 1 ELSE 0 END) AS winners,
       SUM(prob::float) AS sum_prob
FROM outcomes WHERE prob > 0.01 AND prob < 0.99
GROUP BY event_id, bucket_idx
"""

TAILS = {"bucket": _TAIL_BUCKET, "game": _TAIL_GAME, "game_bucket": _TAIL_GAME_BUCKET}


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
    return published_cell_with_meta(sport_key)[0]


def published_cell_with_meta(sport_key: str) -> tuple[dict[int, dict], dict]:
    """The published cell AND the curve it came off.

    The meta half is not decoration: a ledger entry that does not carry the
    ``population_version`` and ``generated_at`` it was measured against cannot
    be aged, and ``calibration_sigma_ledger.lookup`` has nothing to decide
    FRESH / CARRIED / STALE from. CAL-P998.
    """
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
    meta = {
        "generated_at": payload.get("generated_at"),
        "population_version": payload.get("population_version"),
    }
    return out, meta


# --------------------------------------------------------------------------
# CAL-P998 — the sigma this source could never have
#
# `calibration_cluster_sigma.py` (CAL-P121) is the board's measured-SE
# instrument and it CANNOT run here: it drives `calibration_cell_exact`, which
# folds the `futures_markets`-rooted producer chain, and this source has zero
# rows in that table (the reason this file exists at all). So the six
# `odds_api_bookmaker` cells — 6 of the 14 queued cells on the 2026-09-03
# board, 82,345 excess-outcomes — were the only cells on the board that could
# not be banked in the sigma ledger even in principle. CAL-P120 derived their
# game-grain SE by hand, wrote it in a report, and the board has carried them
# at the row basis ever since; that hand-derivation is exactly what CAL-P128's
# ledger exists to end.
#
# This closes the loop WITHOUT a second implementation of anything that
# decides: the bootstrap, the fold it resamples through, the bars, the gate and
# the ledger's entry shape are all imported. What is added here is the one
# thing that is genuinely this source's own — its cluster, which is the GAME.
# --------------------------------------------------------------------------


def game_clusters(rows: list[dict]) -> list[dict[int, dict]]:
    """``--grain game_bucket`` rows -> one ``{decile: {n, w, sp}}`` per game.

    A shape change, not an aggregation: chunks partition events, so no game
    appears twice and no two games are ever combined. The key names are
    ``calibration_cell_exact.fold``'s, because that is the fold the bootstrap
    runs through and restating it here would be a second fold.
    """
    out: dict[str, dict[int, dict]] = {}
    for r in rows:
        g = out.setdefault(str(r["event_id"]), {})
        b = g.setdefault(int(r["bucket_idx"]), {"n": 0, "w": 0, "sp": 0.0})
        b["n"] += int(r["n"])
        b["w"] += int(r["winners"])
        b["sp"] += float(r["sum_prob"])
    return list(out.values())


def sigma_object(sport_key: str, clusters: list[dict[int, dict]],
                 published: dict[int, dict], meta: dict,
                 boot: int, seed: int) -> dict:
    """The ledger's own input shape, so no new schema enters the board.

    Emitted key-for-key as ``calibration_cluster_sigma.py`` emits it, which is
    what lets ``calibration_sigma_ledger.entry_from_sigma_json`` fold it with
    no change and ``validate`` re-check it. A parallel entry shape for one
    source would be a second ledger wearing the first one's filename.
    """
    import calibration_cluster_sigma as ccs  # local: only the sigma path needs it

    pooled: dict[int, dict] = {}
    for g in clusters:
        for b, v in g.items():
            p = pooled.setdefault(b, {"n": 0, "w": 0, "sp": 0.0})
            p["n"] += v["n"]
            p["w"] += v["w"]
            p["sp"] += v["sp"]
    n, ece, gap = ccs.cce.fold(pooled)
    pn, pece, pgap = ece_of(published)

    klass = ccs.cs.classify("odds_api_bookmaker", sport_key)
    bar = ccs.cs.CLASS_BARS_PP[klass]
    excess = (ece or 0.0) - bar
    k = len(clusters)

    se_row = ccs.cs.cell_se_pp(n)
    # The GAME-grain SE, which on this source is not merely a bound: `won` is a
    # function of `event_id` alone, so every book-row of a game carries a
    # byte-identical outcome and the within-cluster correlation of the response
    # is exactly 1 BY CONSTRUCTION. The bootstrap should therefore land on this
    # number rather than between it and the row basis, and a large gap between
    # the two is a finding about the fold, not about the sample.
    se_market = ccs.cs.cell_se_pp(k)
    samples, se_boot = ccs.bootstrap_ece(clusters, boot, seed)

    def _sig(se):
        # `se != se` was the NaN test here. It is correct and it is also
        # indistinguishable from a typo — CodeQL reads it as a comparison of
        # identical values, which is exactly how a real one would look. Same
        # three rejections (None, 0, NaN), said out loud.
        if not se or math.isnan(se):
            return None
        return excess / se

    return {
        "source": "odds_api_bookmaker",
        "category": sport_key,
        "boot": boot,
        "seed": seed,
        "clusters": k,
        "rows_per_cluster": round(n / k, 3) if k else None,
        "bar": bar,
        "excess": round(excess, 2),
        "klass": klass,
        "sigma_gate": ccs.cs.SIGMA_GATE,
        "established": bool(_sig(se_boot) is not None and _sig(se_boot) >= ccs.cs.SIGMA_GATE),
        "bootstrap_ci": [
            round(ccs.percentile(samples, 0.025), 2),
            round(ccs.percentile(samples, 0.975), 2),
        ],
        "payload": {
            "n": pn,
            "ece": round(pece, 2),
            "gap": round(pgap, 2),
            "generated_at": meta.get("generated_at"),
            "population_version": meta.get("population_version"),
        },
        # This rail reproduces the published cell EXACTLY (CAL-P120: every
        # bucket row count exact, drift +0.00%), so `exact_coverage` lands on
        # 1.0 rather than near it. That is a property of the chunking being on
        # `commence_time`, and it is asserted rather than hoped for: a coverage
        # outside COVERAGE_BAND turns the entry into POPULATION_DIVERGENCE and
        # the board will say so.
        "exact": {"n": n, "ece": ece, "gap": gap},
        "se": {"row": se_row, "market": se_market, "bootstrap": se_boot},
        "sigma": {
            "row": _sig(se_row),
            "market": _sig(se_market),
            "bootstrap": _sig(se_boot),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sport-key", required=True)
    ap.add_argument("--grain", choices=sorted(TAILS), default="bucket")
    ap.add_argument("--weeks", type=int, default=3, help="initial chunk width in weeks")
    ap.add_argument("--check-payload", action="store_true",
                    help="diff a bucket-grain fold against the LIVE published cell")
    ap.add_argument("--sigma", action="store_true",
                    help="cluster-bootstrap the cell's SE over GAMES and emit a "
                         "sigma-ledger entry (implies --grain game_bucket)")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260903)
    ap.add_argument("--out")
    a = ap.parse_args()

    if a.sigma:
        # Forced rather than validated: `--sigma --grain game` is a request for
        # a bootstrap over a grain that cannot answer it, and silently
        # producing a number from the wrong units is the failure mode this
        # whole file is about.
        a.grain = "game_bucket"

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
    elif a.grain == "game":
        games = len(rows)
        books = sum(int(r["books"]) for r in rows)
        print(f"  games={games:,}  book-rows={books:,}  "
              f"replication={books / games:.2f}x" if games else "  no games")

    if a.sigma:
        clusters = game_clusters(rows)
        if not clusters:
            print("  🔴 no games in span — refusing to emit a ledger entry for an "
                  "empty cell (an SE over nothing is not a small SE)")
            return 1
        published, meta = published_cell_with_meta(a.sport_key)
        obj = sigma_object(a.sport_key, clusters, published, meta, a.boot, a.seed)
        se, sig = obj["se"], obj["sigma"]
        print(f"  population {meta['population_version']}  "
              f"curve {meta['generated_at']}")
        print(f"  games={obj['clusters']:,}  book-rows={obj['exact']['n']:,}  "
              f"replication={obj['rows_per_cluster']}x")
        print(f"  ECE {obj['exact']['ece']} pp (published {obj['payload']['ece']}) "
              f"vs bar {obj['bar']} — excess {obj['excess']:+.2f} pp")
        print(f"    {'basis':<34} {'SE pp':>8} {'sigma':>8}")
        for label, key in (("row grain (the board today)", "row"),
                           ("game grain (rho = 1 exactly)", "market"),
                           ("cluster bootstrap (MEASURED)", "bootstrap")):
            print(f"    {label:<34} {se[key]:>8.3f} {sig[key]:>8.2f}")
        print(f"  VERDICT  {'ESTABLISHED' if obj['established'] else 'NOT ESTABLISHED'}"
              f" at SIGMA_GATE {obj['sigma_gate']}")
        if a.out:
            os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
            # `with`, not a bare `open()` inside the call: the artifact this
            # writes is folded into the sigma ledger by a second command, and an
            # unclosed handle can leave it truncated on the interpreter's whim.
            with open(a.out, "w") as fh:
                json.dump(obj, fh, default=str)
            print(f"  wrote {a.out} — fold into the ledger with "
                  f"`calibration_sigma_ledger.py --build`")
        return rc

    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump({"sport_key": a.sport_key, "grain": a.grain, "rows": rows},
                  open(a.out, "w"), default=str)
        print(f"  wrote {a.out}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
