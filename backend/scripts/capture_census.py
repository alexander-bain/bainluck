#!/usr/bin/env python3
"""Cross-sport capture-truth census (program: calibration, 2026-08-03).

Answers, for EVERY sport (not just MLB): per resolved game, how many markets /
outcomes / *well-traded* outcomes do we capture, split by market class and by
source — and where do those numbers become impossible (a classifier failure)
rather than a real capture gap.

Runs on a Heroku one-off dyno (connects directly to DATABASE_URL). READ-ONLY:
every statement is a server-side aggregate, never a row dump.

    heroku run -a bainluck python scripts/capture_census.py            # all
    heroku run -a bainluck python scripts/capture_census.py --phase a
    heroku run -a bainluck python scripts/capture_census.py --window 180

Note (gotcha: one-off dyno PROJECT_PATH=backend): the app root on the dyno is
backend/, so the path is scripts/capture_census.py, NOT backend/scripts/..., and
`from app.utils...` imports resolve.

Market class is computed with the SHARED production classifier
(app.utils.game_market_class.classify_game_market_class) so the census measures
exactly what production recognizes. If classification is wrong, the census flags
it — that is the point (Mission 3a). No inline SQL regex, no drift.
"""

import argparse
import os
import sys
from collections import defaultdict

import psycopg2

# Import the SHARED classifier (the one Mission 3b fixes ONCE).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils.game_market_class import classify_game_market_class  # noqa: E402

# --- auto-flag thresholds (Mission 3a) -------------------------------------
MONEYLINE_PER_GAME_FLOOR = 1.0   # < 1 game-winner market/game is impossible
OTHER_SHARE_CEILING = 0.10       # > 10% "other" = classifier failing, not exotic

CLASSES = ["moneyline", "spread", "total", "player_prop", "team_prop", "other"]


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set — run this on a Heroku one-off dyno.")
    return psycopg2.connect(url, sslmode="require")


GAME_CTE = """
WITH g AS (
  SELECT e.id, s.key AS sport_key
  FROM events e
  JOIN sports s ON s.id = e.sport_id
  WHERE e.status IN ('completed', 'closed')
    AND e.commence_time >= NOW() - INTERVAL '%(window)s days'
)
"""

# CURRENT production well-traded bar (precompute_calibration.py:2012-2013): a
# pure snapshot-delta. Measures "did polling capture two distinct prices," NOT
# "did it trade."
WELL_TRADED = """
COUNT(*) FILTER (
  WHERE fo.calibration_probability IS DISTINCT FROM fo.opening_probability
    AND fo.opening_probability IS NOT NULL
)
"""
# PROPOSED bar: source-reported trade activity (FuturesOutcome.volume;
# NULL=unknown, 0=confirmed-zero, >0=traded).
VOLUME_POSITIVE = "COUNT(*) FILTER (WHERE fo.volume > 0)"
VOLUME_NULL = "COUNT(*) FILTER (WHERE fo.volume IS NULL)"
# ARTIFACT: FAILS the snapshot bar but DID trade (volume>0) — flunked only
# because our snapshots missed the move.
ARTIFACT = """
COUNT(*) FILTER (
  WHERE fo.volume > 0
    AND NOT (fo.calibration_probability IS DISTINCT FROM fo.opening_probability
             AND fo.opening_probability IS NOT NULL)
)
"""


def q_denominators(cur, window):
    print("\n" + "=" * 80)
    print("PHASE A.1 — Resolved games per sport (the denominator)")
    print("=" * 80)
    cur.execute(GAME_CTE % {"window": window}
                + "SELECT sport_key, COUNT(*) FROM g GROUP BY sport_key "
                  "ORDER BY 2 DESC;")
    rows = cur.fetchall()
    print(f"{'sport':28s} {'games':>8s}")
    for sport, games in rows:
        print(f"{sport:28s} {games:>8,}")
    return {r[0]: r[1] for r in rows}


def _fetch_market_rows(cur, window):
    """One row per game-linked market, with per-market outcome aggregates."""
    cur.execute(
        GAME_CTE % {"window": window}
        + f"""
        SELECT g.sport_key, fm.name, fm.external_id,
               COUNT(fo.id)          AS outcomes,
               {WELL_TRADED}         AS well_traded,
               {VOLUME_POSITIVE}     AS vol_pos,
               {VOLUME_NULL}         AS vol_null,
               {ARTIFACT}            AS artifact
        FROM futures_markets fm
        JOIN g ON g.id = fm.event_id
        LEFT JOIN futures_outcomes fo ON fo.market_id = fm.id
        GROUP BY g.sport_key, fm.id, fm.name, fm.external_id;
        """
    )
    return cur.fetchall()


def q_class_per_sport(cur, window, games_by_sport):
    print("\n" + "=" * 80)
    print("PHASE A.2 — Market class x sport (via SHARED classifier)")
    print("=" * 80)
    rows = _fetch_market_rows(cur, window)
    # tally[sport][cls] = [markets, outcomes, well_traded, vol_pos, artifact]
    tally = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0, 0]))
    other_names = defaultdict(lambda: defaultdict(int))  # sport -> name -> n
    for sport, name, ext, outc, well, volp, voln, art in rows:
        cls = classify_game_market_class(name or "", ext, sport)
        t = tally[sport][cls]
        t[0] += 1
        t[1] += outc or 0
        t[2] += well or 0
        t[3] += volp or 0
        t[4] += art or 0
        if cls == "other":
            other_names[sport][(name or "")[:70]] += 1

    print(f"{'sport':20s} {'class':11s} {'mkts':>6s} {'mkt/g':>6s} "
          f"{'outc':>7s} {'wt':>7s} {'wt/g':>6s} {'volpos':>7s} {'artf':>6s}")
    for sport in sorted(tally, key=lambda s: -games_by_sport.get(s, 0)):
        games = max(games_by_sport.get(sport, 0), 1)
        for cls in CLASSES:
            if cls not in tally[sport]:
                continue
            m, o, w, vp, art = tally[sport][cls]
            print(f"{sport:20s} {cls:11s} {m:>6,} {m/games:>6.2f} "
                  f"{o:>7,} {w:>7,} {w/games:>6.2f} {vp:>7,} {art:>6,}")
    return tally, other_names


def flag_classifier_failures(tally, games_by_sport):
    print("\n" + "=" * 80)
    print("PHASE A.3 — AUTO-FLAGGED classifier failures (not facts)")
    print(f"  rule: moneyline < {MONEYLINE_PER_GAME_FLOOR}/game  OR  "
          f"other > {OTHER_SHARE_CEILING:.0%} of markets")
    print("=" * 80)
    any_flag = False
    for sport in sorted(tally, key=lambda s: -games_by_sport.get(s, 0)):
        games = max(games_by_sport.get(sport, 0), 1)
        total_markets = sum(v[0] for v in tally[sport].values()) or 1
        ml = tally[sport].get("moneyline", [0])[0]
        other = tally[sport].get("other", [0])[0]
        flags = []
        if ml / games < MONEYLINE_PER_GAME_FLOOR:
            flags.append(f"moneyline {ml/games:.2f}/game (<{MONEYLINE_PER_GAME_FLOOR})")
        if other / total_markets > OTHER_SHARE_CEILING:
            flags.append(f"other {other/total_markets:.0%} of {total_markets} mkts "
                         f"(>{OTHER_SHARE_CEILING:.0%})")
        if flags:
            any_flag = True
            print(f"  [FLAG] {sport}: " + "; ".join(flags))
    if not any_flag:
        print("  (none — every sport lands sane)")


def print_other_names(other_names, games_by_sport, limit=30):
    print("\n" + "=" * 80)
    print("PHASE A.4 — Top 'other'-bucket names per flagged sport (fix inputs)")
    print("=" * 80)
    flat = []
    for sport, names in other_names.items():
        for name, n in names.items():
            flat.append((n, sport, name))
    flat.sort(reverse=True)
    for n, sport, name in flat[:limit]:
        print(f"  {n:>5,}  {sport:18s}  {name}")


def q_source_split(cur, window):
    # Mission 3c: quantify the capture artifact per source x sport.
    print("\n" + "=" * 80)
    print("PHASE C — Well-traded bar by source x sport: snapshot vs volume")
    print("  fail% = fails snapshot bar; artifact = fails snapshot BUT volume>0")
    print("=" * 80)
    cur.execute(
        GAME_CTE % {"window": window}
        + f"""
        SELECT g.sport_key, fm.source,
               COUNT(fo.id) AS outc,
               {WELL_TRADED} AS well,
               {VOLUME_POSITIVE} AS volp,
               {VOLUME_NULL} AS voln,
               {ARTIFACT} AS artifact
        FROM futures_markets fm
        JOIN g ON g.id = fm.event_id
        LEFT JOIN futures_outcomes fo ON fo.market_id = fm.id
        GROUP BY g.sport_key, fm.source
        HAVING COUNT(fo.id) > 0
        ORDER BY g.sport_key, outc DESC;
        """
    )
    print(f"{'sport':18s} {'source':12s} {'outc':>8s} {'wt':>8s} {'fail%':>6s} "
          f"{'volpos':>8s} {'volnull':>8s} {'artifact':>8s} {'art%':>6s}")
    for sport, source, outc, well, volp, voln, art in cur.fetchall():
        outc = outc or 0
        fail = (outc - (well or 0)) / outc * 100 if outc else 0
        artpct = (art or 0) / outc * 100 if outc else 0
        print(f"{sport:18s} {source or '?':12s} {outc:>8,} {well or 0:>8,} "
              f"{fail:>5.1f}% {volp or 0:>8,} {voln or 0:>8,} "
              f"{art or 0:>8,} {artpct:>5.1f}%")


def q_odds_snapshot_coverage(cur, window):
    # Q4 generalized to all sports. odds_snapshots is a WIDE table with fixed
    # columns for exactly three classes (moneyline/spread/total).
    print("\n" + "=" * 80)
    print("PHASE Q4 — Sportsbook (odds_snapshots) per-game coverage by sport")
    print("=" * 80)
    cur.execute(
        GAME_CTE % {"window": window}
        + """
        SELECT g.sport_key,
               COUNT(DISTINCT os.event_id) AS games_with_odds,
               COUNT(DISTINCT os.bookmaker) AS bookmakers,
               COUNT(*) AS rows,
               COUNT(*) FILTER (WHERE os.home_moneyline IS NOT NULL) AS ml,
               COUNT(*) FILTER (WHERE os.home_spread IS NOT NULL) AS spread,
               COUNT(*) FILTER (WHERE os.over_under IS NOT NULL) AS total
        FROM odds_snapshots os
        JOIN g ON g.id = os.event_id
        GROUP BY g.sport_key
        ORDER BY rows DESC;
        """
    )
    print(f"{'sport':18s} {'games':>7s} {'books':>6s} {'rows':>9s} "
          f"{'ml':>8s} {'spread':>8s} {'total':>8s}")
    for sport, games, books, rows, ml, spread, total in cur.fetchall():
        print(f"{sport:18s} {games:>7,} {books:>6,} {rows:>9,} "
              f"{ml:>8,} {spread:>8,} {total:>8,}")


def q5_published_population(cur):
    # Q5 (Mission 3d input): the honest well-traded number in the ACTUAL
    # published calibration population, per source, snapshot bar vs volume bar.
    print("\n" + "=" * 80)
    print("PHASE Q5 — Published calibration population: snapshot bar vs volume bar")
    print("  (resolved, opening in (0,1) — the calibration eligibility gate)")
    print("=" * 80)
    cur.execute(
        f"""
        SELECT fm.source,
               COUNT(*) AS eligible,
               {WELL_TRADED} AS well_snapshot,
               {VOLUME_POSITIVE} AS well_volume,
               {VOLUME_NULL} AS vol_null,
               {ARTIFACT} AS artifact
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.opening_probability > 0 AND fo.opening_probability < 1
        GROUP BY fm.source
        ORDER BY eligible DESC;
        """
    )
    print(f"{'source':14s} {'eligible':>10s} {'wt_snap':>10s} {'snap%':>6s} "
          f"{'wt_vol':>10s} {'vol%':>6s} {'volnull':>10s} {'artifact':>10s}")
    for source, elig, snap, vol, voln, art in cur.fetchall():
        elig = elig or 0
        snappct = (snap or 0) / elig * 100 if elig else 0
        volpct = (vol or 0) / elig * 100 if elig else 0
        print(f"{source or '?':14s} {elig:>10,} {snap or 0:>10,} {snappct:>5.1f}% "
              f"{vol or 0:>10,} {volpct:>5.1f}% {voln or 0:>10,} {art or 0:>10,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=30, help="lookback days (30)")
    ap.add_argument("--phase", choices=["a", "c", "q4", "q5", "all"], default="all")
    args = ap.parse_args()

    conn = connect()
    cur = conn.cursor()
    print(f"# Cross-sport capture census — window={args.window}d")

    if args.phase in ("a", "all"):
        games = q_denominators(cur, args.window)
        tally, other_names = q_class_per_sport(cur, args.window, games)
        flag_classifier_failures(tally, games)
        print_other_names(other_names, games)
    if args.phase in ("c", "all"):
        q_source_split(cur, args.window)
    if args.phase in ("q4", "all"):
        q_odds_snapshot_coverage(cur, args.window)
    if args.phase in ("q5", "all"):
        q5_published_population(cur)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
