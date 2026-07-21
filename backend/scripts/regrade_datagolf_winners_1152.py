#!/usr/bin/env python3
"""#1152 re-grade: DataGolf Winner/Top-N/Make-Cut markets that resolved with the
CHAMPION graded as a loser (0 winners) for ~4 tournaments since 2026-07-05.

The authoritative fix lives in app/tasks/backfill_winners.py (leaderboard
resolution now runs before the all_losers heuristic, and all_losers excludes
DataGolf). This script re-grades the ALREADY-corrupted historical markets.

Re-grading is done by the authoritative leaderboard resolver
(_backfill_datagolf_winners), which reads each market's STORED final leaderboard
(dg_id -> finishing position) — a confirmed re-resolve source, so this does NOT
violate gotcha #21 (never bulk-reset is_winner without a confirmed re-resolve
source).

DRY-RUN BY DEFAULT. Nothing is written unless you pass --apply.

Usage (Heroku one-off dyno; PROJECT_PATH=backend puts scripts at /app, so do
NOT prefix with `cd backend` — see the "Heroku one-off dyno: no cd backend"
gotcha):

    # Dry-run report (read-only): what WOULD change, per tournament
    heroku run -a bainluck python3 scripts/regrade_datagolf_winners_1152.py

    # Apply the authoritative leaderboard re-grade
    heroku run -a bainluck python3 scripts/regrade_datagolf_winners_1152.py --apply

Options:
    --since YYYY-MM-DD   Only report markets with resolution_date >= this
                         (default 2026-07-01; the regression window).
    --apply              Actually run the authoritative resolver (writes).
"""

import argparse
import os
import sys

import psycopg2
import psycopg2.extras


def _placement_won(pos_raw, market_type):
    """Mirror of _datagolf_check_placement for the read-only dry-run report."""
    if pos_raw is None:
        return None
    pos_str = str(pos_raw).strip()
    cut_statuses = {"CUT", "MC", "MDF", "WD", "DQ", "DNS", "W/D"}
    if pos_str.upper() in cut_statuses:
        return False  # cut/WD/DQ never place (win/top_N) or make the cut
    numeric_str = pos_str.upper().lstrip("T")
    try:
        pos = int(numeric_str)
    except ValueError:
        return None
    thresholds = {"win": 1, "top_5": 5, "top_10": 10, "top_20": 20}
    if market_type in thresholds:
        return pos <= thresholds[market_type]
    if market_type == "make_cut":
        return True
    return None


def dry_run(since):
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT fm.id, fm.external_id, fm.resolution_date::date AS d,
               fm.market_metadata->'leaderboard' AS leaderboard,
               COUNT(fo.id) AS n_out,
               SUM(CASE WHEN fo.is_winner THEN 1 ELSE 0 END) AS cur_winners
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'datagolf'
          AND fm.status = 'resolved'
          AND fm.resolution_date >= %s
          AND (fm.external_id LIKE %s OR fm.external_id LIKE %s
               OR fm.external_id LIKE %s OR fm.external_id LIKE %s
               OR fm.external_id LIKE %s)
        GROUP BY fm.id, fm.external_id, fm.resolution_date, fm.market_metadata
        ORDER BY fm.resolution_date, fm.external_id
        """,
        (since, "%:win", "%:top_5", "%:top_10", "%:top_20", "%:make_cut"),
    )
    rows = cur.fetchall()

    total_flips = 0
    affected_markets = 0
    print(f"DRY-RUN — DataGolf winner/top-N/make_cut markets since {since}\n")
    print(f"{'market':<34} {'date':<12} {'cur_win':>7} {'lb_win':>7} {'flip?':>6}")
    print("-" * 72)
    for r in rows:
        mtype = r["external_id"].rsplit(":", 1)[-1]
        lb = r["leaderboard"] or []
        pos_by_dg = {
            str(e.get("dg_id")): e.get("position")
            for e in lb
            if e.get("dg_id") is not None
        }
        # expected winners from the stored leaderboard
        lb_win = 0
        for dg_id, pos in pos_by_dg.items():
            if _placement_won(pos, mtype):
                lb_win += 1
        cur_win = int(r["cur_winners"] or 0)
        flip = lb_win != cur_win
        if flip:
            affected_markets += 1
            total_flips += abs(lb_win - cur_win)
        print(
            f"{r['external_id']:<34} {str(r['d']):<12} "
            f"{cur_win:>7} {lb_win:>7} {'YES' if flip else '':>6}"
        )
    print("-" * 72)
    print(
        f"\n{affected_markets} markets would change; "
        f"~{total_flips} winner-flip(s). Re-run with --apply to write.\n"
        "Note: markets showing lb_win=0 have no stored leaderboard (nothing to "
        "recover here) or a genuinely empty field."
    )
    conn.close()


def apply_regrade():
    import asyncio

    from app.tasks.backfill_winners import _backfill_datagolf_winners

    print("APPLY — running authoritative _backfill_datagolf_winners() ...")
    stats = asyncio.run(_backfill_datagolf_winners())
    print(
        "Done: %d markets processed, %d winners set, %d losers set, "
        "%d no_leaderboard, %d errors"
        % (
            stats["markets_processed"],
            stats["winners_set"],
            stats["losers_set"],
            stats["no_leaderboard"],
            len(stats["errors"]),
        )
    )
    if stats["errors"]:
        print("ERRORS:", stats["errors"][:5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-07-01")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.apply:
        apply_regrade()
    else:
        dry_run(args.since)


if __name__ == "__main__":
    sys.exit(main())
