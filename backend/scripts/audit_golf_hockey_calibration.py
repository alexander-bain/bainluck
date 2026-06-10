#!/usr/bin/env python3
"""Attribute golf/hockey calibration error to specific mechanisms.

Replicates the EXACT inclusion logic of the public GET /api/calibration
curve query (routes/calibration.py::public_calibration), restricted to
llm_sport_category IN ('golf', 'hockey'), then decomposes the error by
suspect cohort so the fix targets the dominant mechanism instead of
guessing.

Mechanisms tested (each with a counterfactual MCE = "what the curve looks
like with that cohort's rows removed"). IMPORTANT: removal here is
DIAGNOSTIC ATTRIBUTION ONLY — the production fix is to correct is_winner /
calibration prices, not to filter the chart. The one principled exception
is M1: outcomes with NO ground truth (never resolved) are not "losers" and
must not be counted as such.

  M1  unresolved-as-loser: is_winner=false + resolution_source IS NULL on a
      market where NO outcome has is_winner=true. The curve query's
      clean_vms gate (has_winner >= 1) operates at the VIRTUAL-market level
      (group_id / event_id), so a hockey game's unresolved player props or
      a golf tournament's unresolved make_cut siblings pass the gate and
      count as losers. is_winner defaults to false — there is no NULL
      state — so missing resolution is indistinguishable from a loss.
  M2  golf truncated leaderboards: markets whose stored
      market_metadata.leaderboard has < 100 entries (pre-137344d5 polls
      truncated to 50). Players who made the cut but sat outside the
      truncation were marked losers.
  M3  is_winner vs Kalshi result mismatch: binary Yes/No markets where
      market_metadata.result disagrees with the stored is_winner.
  M4  in-play price leakage (sampled): calibration snapshot captured after
      tournament/game start — commence_time guessed wrong (golf heuristic
      close_time - 4.5d, hockey ticker-derived) so the "closing line" is a
      mid-event price.
  M5  stale-opening cohort: calibration_probability = opening_probability
      (price never moved / no pre-start snapshot found). Honest but old
      prices; flattens the curve when openings are placeholder-priced.

Usage:
    heroku run -a bainluck python3 scripts/audit_golf_hockey_calibration.py
    heroku run -a bainluck python3 scripts/audit_golf_hockey_calibration.py --category golf
    heroku run -a bainluck python3 scripts/audit_golf_hockey_calibration.py --samples 25
"""
import argparse
import os
import re
from collections import defaultdict

import psycopg2
import psycopg2.extras

# ---------------------------------------------------------------------------
# Inclusion query: verbatim CTE chain from public_calibration, restricted to
# golf/hockey, with extra diagnostic columns carried through.
# ---------------------------------------------------------------------------
BUILD_TEMP_SQL = """
CREATE TEMP TABLE audit_rows AS
WITH market_info AS (
    SELECT fm.id AS market_id, fm.source, fm.event_id, fm.group_id,
        fm.commence_time,
        COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
        fm.mutually_exclusive
    FROM futures_markets fm
    WHERE fm.status = 'resolved'
      AND COALESCE(fm.llm_sport_category, 'uncategorized') IN ('golf', 'hockey')
),
group_sizes AS (
    SELECT group_id, source, COUNT(*) AS group_size
    FROM market_info
    WHERE group_id IS NOT NULL
    GROUP BY group_id, source
),
event_sizes AS (
    SELECT event_id, source, COUNT(*) AS event_size
    FROM market_info
    WHERE event_id IS NOT NULL
    GROUP BY event_id, source
),
virtual_market AS (
    SELECT
        mi.market_id, mi.source, mi.category, mi.event_id,
        CASE WHEN gs.group_size >= 3
             THEN 'g:' || mi.group_id
             WHEN es.event_size >= 3
             THEN 'e:' || mi.event_id::text
             ELSE 'm:' || mi.market_id::text
        END AS vm_id,
        COALESCE(gs.group_size >= 3, false)
          OR COALESCE(es.event_size >= 3, false) AS is_grouped,
        mi.mutually_exclusive
    FROM market_info mi
    LEFT JOIN group_sizes gs
      ON gs.group_id = mi.group_id AND gs.source = mi.source
    LEFT JOIN event_sizes es
      ON es.event_id = mi.event_id AND es.source = mi.source
),
vm_stats AS (
    SELECT
        vm.vm_id, vm.source, vm.category, vm.is_grouped,
        vm.mutually_exclusive,
        COUNT(DISTINCT vm.market_id) AS market_count,
        COUNT(*) AS total_outcomes,
        COUNT(*) FILTER (WHERE fo.is_winner = true) AS has_winner,
        COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL
                          AND fo.opening_probability > 0
                          AND fo.opening_probability < 1) AS eligible
    FROM virtual_market vm
    JOIN futures_outcomes fo ON fo.market_id = vm.market_id
    GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped,
             vm.mutually_exclusive
),
clean_vms AS (
    SELECT * FROM vm_stats
    WHERE eligible >= 1
      AND has_winner >= 1
),
-- Diagnostic: does the MARKET (not the virtual market) have a winner?
market_winner AS (
    SELECT fo.market_id, BOOL_OR(fo.is_winner) AS market_has_winner
    FROM futures_outcomes fo
    JOIN market_info mi ON mi.market_id = fo.market_id
    GROUP BY fo.market_id
),
ranked_outcomes AS (
    SELECT
        COALESCE(fo.calibration_probability, fo.opening_probability) AS adj_opening_probability,
        fo.is_winner AS is_winner,
        (fo.calibration_probability IS NOT NULL
         AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability) AS price_moved,
        cv.vm_id, cv.source, cv.category,
        cv.eligible, cv.is_grouped,
        (cv.is_grouped OR cv.eligible >= 3) AS is_multi,
        ROW_NUMBER() OVER (
            PARTITION BY cv.vm_id
            ORDER BY ABS(fo.opening_probability - 0.5)
        ) AS rn,
        -- diagnostic columns --
        fo.id AS outcome_id,
        fo.name AS outcome_name,
        fo.market_id,
        fo.resolution_source,
        fo.opening_captured_at,
        fo.volume AS outcome_volume,
        mw.market_has_winner,
        fm.name AS market_name,
        fm.external_id,
        split_part(fm.external_id, '-', 1) AS ticker_prefix,
        (fm.event_id IS NOT NULL) AS linked,
        fm.commence_time,
        fm.resolution_date,
        CASE WHEN jsonb_typeof(fm.market_metadata->'leaderboard') = 'array'
             THEN jsonb_array_length(fm.market_metadata->'leaderboard')
             ELSE NULL END AS lb_size,
        LOWER(fm.market_metadata->>'result') AS kalshi_result
    FROM futures_outcomes fo
    JOIN virtual_market vm ON vm.market_id = fo.market_id
    JOIN clean_vms cv ON cv.vm_id = vm.vm_id AND cv.source = vm.source
    JOIN market_winner mw ON mw.market_id = fo.market_id
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fo.opening_probability IS NOT NULL
      AND fo.opening_probability > 0 AND fo.opening_probability < 1
      AND (fo.resolution_source IS NULL
           OR fo.resolution_source NOT IN ('pass2_guess', 'pass3_threshold',
                                            'did_not_play', 'withdrew',
                                            'no_pregame_trading'))
      AND COALESCE(fo.volume, -1) != 0
),
mode_prices AS (
    SELECT vm_id, adj_opening_probability AS mode_price
    FROM ranked_outcomes
    WHERE is_multi AND eligible >= 3
    GROUP BY vm_id, adj_opening_probability, eligible
    HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
)
SELECT ro.*,
    LEAST(FLOOR(ro.adj_opening_probability * 10)::int, 9) AS bucket_idx
FROM ranked_outcomes ro
LEFT JOIN mode_prices mp
  ON mp.vm_id = ro.vm_id AND mp.mode_price = ro.adj_opening_probability
WHERE
    CASE
        WHEN ro.is_multi
            THEN ro.adj_opening_probability > 0.005
             AND ro.adj_opening_probability < 0.98
             AND mp.vm_id IS NULL
        ELSE ro.rn = 1
    END
"""

SNAPSHOT_TIMING_SQL = """
SELECT ar.outcome_id, ar.category, ar.bucket_idx, ar.is_winner,
       ar.commence_time, ar.resolution_date,
       cal_snap.captured_at AS cal_snap_at,
       post.n_post_commence
FROM audit_rows ar
LEFT JOIN LATERAL (
    SELECT fos.captured_at
    FROM futures_odds_snapshots fos
    WHERE fos.outcome_id = ar.outcome_id
      AND fos.captured_at < ar.commence_time
      AND fos.probability > 0 AND fos.probability < 1
    ORDER BY fos.captured_at DESC
    LIMIT 1
) cal_snap ON true
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS n_post_commence
    FROM futures_odds_snapshots fos
    WHERE fos.outcome_id = ar.outcome_id
      AND fos.captured_at >= ar.commence_time
) post ON true
WHERE ar.adj_opening_probability >= 0.65
  AND ar.commence_time IS NOT NULL
ORDER BY RANDOM()
LIMIT %(sample_n)s
"""


def _detect_golf_market_type(name: str):
    """Mirror of backfill_winners._detect_golf_market_type."""
    lower = (name or "").lower()
    if re.search(r"winner|champion(?!ship)", lower):
        return "win"
    if "top 5" in lower or "top five" in lower:
        return "top_5"
    if "top 10" in lower or "top ten" in lower:
        return "top_10"
    if "top 20" in lower or "top twenty" in lower:
        return "top_20"
    if re.search(r"make.*cut|to make the cut", lower):
        return "make_cut"
    if re.search(r"head.to.head|h2h|matchup.*vs|vs\.", lower):
        return "h2h"
    return None


def mce(rows):
    """Same definition as routes/calibration.py::_cohort_mce:
    unweighted mean over populated deciles of |actual - avg_pred| * 100."""
    buckets = defaultdict(lambda: {"n": 0, "w": 0, "p": 0.0})
    for r in rows:
        b = buckets[r["bucket_idx"]]
        b["n"] += 1
        b["w"] += 1 if r["is_winner"] else 0
        b["p"] += float(r["adj_opening_probability"])
    if not buckets:
        return None
    err = sum(abs(b["w"] / b["n"] - b["p"] / b["n"]) for b in buckets.values())
    return round(err / len(buckets) * 100, 2)


def curve_table(rows):
    buckets = defaultdict(lambda: {"n": 0, "w": 0, "p": 0.0})
    for r in rows:
        b = buckets[r["bucket_idx"]]
        b["n"] += 1
        b["w"] += 1 if r["is_winner"] else 0
        b["p"] += float(r["adj_opening_probability"])
    lines = ["  bucket   n        avg_pred   actual    gap"]
    for idx in sorted(buckets):
        b = buckets[idx]
        ap, ac = b["p"] / b["n"], b["w"] / b["n"]
        lines.append(
            f"  {idx*10:>2}-{idx*10+10:<3}  {b['n']:<8,} {ap:>7.1%}   {ac:>7.1%}  {ac-ap:>+7.1%}"
        )
    return "\n".join(lines)


def print_cohorts(title, rows, key_fn, min_n=25, high_only=True):
    """Per-cohort gap table for high-confidence rows (pred >= 0.65)."""
    pool = [r for r in rows if float(r["adj_opening_probability"]) >= 0.65] if high_only else rows
    groups = defaultdict(list)
    for r in pool:
        groups[key_fn(r)].append(r)
    print(f"\n--- {title} (pred >= 0.65) ---")
    print(f"  {'cohort':<38} {'n':>7}  {'avg_pred':>8}  {'actual':>7}  {'gap':>8}")
    for k, g in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(g) < min_n:
            continue
        ap = sum(float(r["adj_opening_probability"]) for r in g) / len(g)
        ac = sum(1 for r in g if r["is_winner"]) / len(g)
        print(f"  {str(k):<38} {len(g):>7,}  {ap:>8.1%}  {ac:>7.1%}  {ac-ap:>+8.1%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", choices=["golf", "hockey"], default=None)
    ap.add_argument("--samples", type=int, default=15, help="sample rows per mechanism")
    ap.add_argument("--timing-sample", type=int, default=4000)
    args = ap.parse_args()

    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Building audit_rows (exact replica of public /api/calibration inclusion)...")
    cur.execute(BUILD_TEMP_SQL)
    cur.execute("SELECT * FROM audit_rows")
    all_rows = cur.fetchall()
    print(f"Included outcomes: {len(all_rows):,}")

    categories = [args.category] if args.category else ["golf", "hockey"]

    # Sampled snapshot-timing pass (M4) — done once, partitioned by category
    cur.execute(SNAPSHOT_TIMING_SQL, {"sample_n": args.timing_sample})
    timing_rows = cur.fetchall()

    for cat in categories:
        rows = [r for r in all_rows if r["category"] == cat]
        if not rows:
            print(f"\n=== {cat.upper()}: no rows ===")
            continue

        print("\n" + "=" * 72)
        print(f"=== {cat.upper()}: {len(rows):,} outcomes, MCE {mce(rows)}pp ===")
        print("=" * 72)
        print(curve_table(rows))

        # ------------------------------------------------------------------
        # Cohort breakdowns (where does the high-bucket error live?)
        # ------------------------------------------------------------------
        print_cohorts("by resolution_source", rows,
                      lambda r: r["resolution_source"] or "NULL(unresolved?)")
        print_cohorts("by ticker prefix", rows, lambda r: r["ticker_prefix"][:36])
        print_cohorts("by event-linked", rows, lambda r: "linked" if r["linked"] else "unlinked")
        print_cohorts("by price_moved", rows,
                      lambda r: "closing-line" if r["price_moved"] else "opening-only (M5)")
        if cat == "golf":
            print_cohorts("by golf market type", rows,
                          lambda r: _detect_golf_market_type(r["market_name"]) or "other")
            print_cohorts("by leaderboard size", rows,
                          lambda r: ("no_leaderboard" if r["lb_size"] is None
                                     else "truncated(<100)" if r["lb_size"] < 100
                                     else ">=100"))

        # ------------------------------------------------------------------
        # Mechanism attribution: counterfactual MCE with cohort removed
        # ------------------------------------------------------------------
        base = mce(rows)

        def m1(r):  # unresolved counted as loser
            return (not r["is_winner"] and r["resolution_source"] is None
                    and not r["market_has_winner"])

        def m2(r):  # golf truncated leaderboard losers
            return (cat == "golf" and not r["is_winner"]
                    and r["lb_size"] is not None and r["lb_size"] < 100)

        def m3(r):  # is_winner contradicts Kalshi settlement result
            if r["kalshi_result"] not in ("yes", "no"):
                return False
            nm = (r["outcome_name"] or "").strip().lower()
            if nm not in ("yes", "no"):
                return False
            return r["is_winner"] != (nm == r["kalshi_result"])

        def m5(r):  # opening-only price
            return not r["price_moved"]

        mechanisms = [
            ("M1 unresolved-as-loser (missing ground truth)", m1),
            ("M2 truncated-leaderboard losers (golf)", m2),
            ("M3 is_winner != Kalshi result", m3),
            ("M5 opening-only calibration price", m5),
        ]
        print(f"\n--- mechanism attribution (baseline MCE {base}pp) ---")
        print(f"  {'mechanism':<48} {'affected':>9} {'hi-bucket':>9} {'MCE w/o':>8} {'explained':>9}")
        verdict = []
        for name, fn in mechanisms:
            hit = [r for r in rows if fn(r)]
            hi = sum(1 for r in hit if float(r["adj_opening_probability"]) >= 0.65)
            rest = [r for r in rows if not fn(r)]
            m = mce(rest)
            explained = None if (m is None or base is None) else round(base - m, 2)
            verdict.append((name, len(hit), hi, m, explained))
            print(f"  {name:<48} {len(hit):>9,} {hi:>9,} "
                  f"{m if m is not None else '—':>8} {explained if explained is not None else '—':>9}")

        # Combined counterfactual: all corrections at once
        combined = mce([r for r in rows if not (m1(r) or m2(r) or m3(r))])
        print(f"  {'M1+M2+M3 combined':<48} {'':>9} {'':>9} {combined:>8} "
              f"{round(base - combined, 2) if combined is not None else '—':>9}")

        # ------------------------------------------------------------------
        # M4: snapshot timing (sampled, pred >= 0.65)
        # ------------------------------------------------------------------
        trows = [t for t in timing_rows if t["category"] == cat]
        if trows:
            n_inplay_risk = sum(
                1 for t in trows
                if t["cal_snap_at"] and t["resolution_date"]
                and (t["resolution_date"] - t["cal_snap_at"]).total_seconds() < 12 * 3600
            )
            n_no_prestart = sum(1 for t in trows if t["cal_snap_at"] is None)
            n_has_post = sum(1 for t in trows if (t["n_post_commence"] or 0) > 0)
            print(f"\n--- M4 snapshot timing (sample n={len(trows)}, pred>=0.65) ---")
            print(f"  cal snapshot within 12h of resolution_date (in-play risk): "
                  f"{n_inplay_risk} ({n_inplay_risk/len(trows):.0%})")
            print(f"  no pre-commence snapshot at all (fell back to opening):    "
                  f"{n_no_prestart} ({n_no_prestart/len(trows):.0%})")
            print(f"  has post-commence snapshots (in-play data exists):         "
                  f"{n_has_post} ({n_has_post/len(trows):.0%})")

        # ------------------------------------------------------------------
        # Samples for manual spot-check of the top mechanisms
        # ------------------------------------------------------------------
        for name, fn in mechanisms[:3]:
            hit = sorted(
                (r for r in rows if fn(r) and float(r["adj_opening_probability"]) >= 0.65),
                key=lambda r: -float(r["adj_opening_probability"]),
            )[: args.samples]
            if not hit:
                continue
            print(f"\n--- samples: {name} ---")
            for r in hit:
                print(f"  [{float(r['adj_opening_probability']):.0%} pred, "
                      f"winner={r['is_winner']}, res_src={r['resolution_source']}, "
                      f"lb={r['lb_size']}] {r['external_id'][:40]} | "
                      f"{(r['market_name'] or '')[:50]} | {(r['outcome_name'] or '')[:30]}")

    conn.close()
    print("\nDone. Reminder: counterfactuals above are attribution, not a proposed "
          "display filter. Fix order: resolve missing is_winner (M1/M3 — Kalshi "
          "settlement data ages out after ~2-3 months, so this is time-sensitive), "
          "re-fetch truncated leaderboards (M2), then fix commence_time sources (M4).")


if __name__ == "__main__":
    main()
