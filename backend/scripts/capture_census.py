#!/usr/bin/env python3
"""Cross-sport capture-truth census (program: calibration, 2026-08-03).

Thin CLI over the shared library `app/utils/capture_census.py` — the SAME code
the calibration sentinel runs every sweep (2026-08-03 addendum), so the one-off
report and the permanent sentinel axis can never drift.

Runs on a Heroku one-off dyno (connects directly to DATABASE_URL). READ-ONLY:
every statement is a server-side aggregate.

    heroku run -a bainluck python scripts/capture_census.py            # all
    heroku run -a bainluck python scripts/capture_census.py --phase a
    heroku run -a bainluck python scripts/capture_census.py --window 180

Note (gotcha: one-off dyno PROJECT_PATH=backend): the app root on the dyno is
backend/, so the path is scripts/capture_census.py and `from app...` resolves.
"""

import argparse
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.utils import capture_census as cc  # noqa: E402


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL not set — run this on a Heroku one-off dyno.")
    return psycopg2.connect(url, sslmode="require")


def phase_a(cur, window):
    games = dict(_run(cur, cc.games_sql(window)))
    market_rows = _run(cur, cc.market_rows_sql(window))
    source_rows = _run(cur, cc.source_split_sql(window))
    by_sc, other_names = cc.tally_market_rows(market_rows)
    by_src = cc.tally_source_split(source_rows)

    print("\n" + "=" * 80)
    print("PHASE A.1 — Resolved games per sport (denominator)")
    print("=" * 80)
    for sport in sorted(games, key=lambda s: -games[s]):
        print(f"  {sport:28s} {games[sport]:>8,}")

    print("\n" + "=" * 80)
    print("PHASE A.2 — Market class x sport (via SHARED classifier)")
    print("=" * 80)
    print(f"{'sport':20s} {'class':11s} {'mkts':>6s} {'mkt/g':>6s} "
          f"{'outc':>7s} {'wt':>7s} {'wt/g':>6s} {'volpos':>7s} {'artf':>6s}")
    for sport in sorted(by_sc, key=lambda s: -games.get(s, 0)):
        g = max(games.get(sport, 0), 1)
        for cls in cc.CLASSES:
            mc = by_sc[sport].get(cls)
            if not mc:
                continue
            print(f"{sport:20s} {cls:11s} {mc.markets:>6,} {mc.markets/g:>6.2f} "
                  f"{mc.outcomes:>7,} {mc.well_traded:>7,} {mc.well_traded/g:>6.2f} "
                  f"{mc.vol_pos:>7,} {mc.artifact:>6,}")

    print("\n" + "=" * 80)
    print("PHASE A.3 — AUTO-FLAGGED findings (starved class / classifier leak / "
          "pass-rate outlier)")
    print("=" * 80)
    findings = cc.capture_findings(games, by_sc, by_src)
    if not findings:
        print("  (none — every sport lands sane)")
    for f in findings:
        print(f"  [{f.severity:5s}] {f.kind:16s} {f.cohort}")
        print(f"          {f.detail}")

    print("\n" + "=" * 80)
    print("PHASE A.4 — Top 'other'-bucket names (classifier fix inputs)")
    print("=" * 80)
    flat = sorted(
        ((n, s, name) for s, names in other_names.items() for name, n in names.items()),
        reverse=True,
    )
    for n, sport, name in flat[:30]:
        print(f"  {n:>5,}  {sport:18s}  {name}")


def phase_c(cur, window):
    print("\n" + "=" * 80)
    print("PHASE C — Well-traded bar by source x sport: snapshot vs volume")
    print("  fail% = fails snapshot bar; artifact = fails snapshot BUT volume>0")
    print("=" * 80)
    print(f"{'sport':18s} {'source':12s} {'outc':>8s} {'wt':>8s} {'fail%':>6s} "
          f"{'volpos':>8s} {'volnull':>8s} {'artifact':>8s} {'art%':>6s}")
    for sport, source, outc, well, volp, voln, art in _run(cur, cc.source_split_sql(window)):
        outc = outc or 0
        fail = (outc - (well or 0)) / outc * 100 if outc else 0
        artpct = (art or 0) / outc * 100 if outc else 0
        print(f"{sport:18s} {source or '?':12s} {outc:>8,} {well or 0:>8,} "
              f"{fail:>5.1f}% {volp or 0:>8,} {voln or 0:>8,} "
              f"{art or 0:>8,} {artpct:>5.1f}%")


def phase_q4(cur, window):
    # Sportsbook odds_snapshots per-game coverage — a wide table with fixed
    # columns for exactly moneyline/spread/total (kept here, not in the shared
    # library, because it is a sportsbook-coverage extra, not a sentinel cohort).
    print("\n" + "=" * 80)
    print("PHASE Q4 — Sportsbook (odds_snapshots) per-game coverage by sport")
    print("=" * 80)
    sql = (cc._GAME_CTE % {"window": window}) + """
        SELECT g.sport_key,
               COUNT(DISTINCT os.event_id), COUNT(DISTINCT os.bookmaker), COUNT(*),
               COUNT(*) FILTER (WHERE os.home_moneyline IS NOT NULL),
               COUNT(*) FILTER (WHERE os.home_spread IS NOT NULL),
               COUNT(*) FILTER (WHERE os.over_under IS NOT NULL)
        FROM odds_snapshots os JOIN g ON g.id = os.event_id
        GROUP BY g.sport_key ORDER BY 4 DESC;
    """
    print(f"{'sport':18s} {'games':>7s} {'books':>6s} {'rows':>9s} "
          f"{'ml':>8s} {'spread':>8s} {'total':>8s}")
    for sport, games, books, rows, ml, spread, total in _run(cur, sql):
        print(f"{sport:18s} {games:>7,} {books:>6,} {rows:>9,} "
              f"{ml:>8,} {spread:>8,} {total:>8,}")


def phase_q5(cur):
    print("\n" + "=" * 80)
    print("PHASE Q5 — Published calibration population: snapshot bar vs volume bar")
    print("  (resolved, opening in (0,1) — the calibration eligibility gate)")
    print("=" * 80)
    print(f"{'source':14s} {'eligible':>10s} {'wt_snap':>10s} {'snap%':>6s} "
          f"{'wt_vol':>10s} {'vol%':>6s} {'volnull':>10s} {'artifact':>10s}")
    for source, elig, snap, vol, voln, art in _run(cur, cc.published_population_sql()):
        elig = elig or 0
        snappct = (snap or 0) / elig * 100 if elig else 0
        volpct = (vol or 0) / elig * 100 if elig else 0
        print(f"{source or '?':14s} {elig:>10,} {snap or 0:>10,} {snappct:>5.1f}% "
              f"{vol or 0:>10,} {volpct:>5.1f}% {voln or 0:>10,} {art or 0:>10,}")


def _run(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=30, help="lookback days (30)")
    ap.add_argument("--phase", choices=["a", "c", "q4", "q5", "all"], default="all")
    args = ap.parse_args()

    conn = connect()
    cur = conn.cursor()
    print(f"# Cross-sport capture census — window={args.window}d "
          f"(shared lib: app/utils/capture_census.py)")
    if args.phase in ("a", "all"):
        phase_a(cur, args.window)
    if args.phase in ("c", "all"):
        phase_c(cur, args.window)
    if args.phase in ("q4", "all"):
        phase_q4(cur, args.window)
    if args.phase in ("q5", "all"):
        phase_q5(cur)
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
