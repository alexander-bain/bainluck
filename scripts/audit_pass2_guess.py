#!/usr/bin/env python3
"""Deep audit of remaining pass2_guess outcomes.

Usage:
    heroku run --app bainluck python3 scripts/audit_pass2_guess.py
"""
import os
import psycopg2

def main():
    url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    # 1. Total by source
    cur.execute("""
        SELECT fo.source, COUNT(*)
        FROM futures_outcomes fo
        WHERE fo.resolution_source = 'pass2_guess'
        GROUP BY fo.source ORDER BY 2 DESC
    """)
    print("=== pass2_guess by source ===")
    total = 0
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")
        total += row[1]
    print(f"  TOTAL: {total:,}")

    # 2. Kalshi by ticker prefix
    cur.execute("""
        SELECT
            regexp_replace(fm.ticker_id, '-[0-9]{2}[A-Z]{3}[0-9]{2,4}.*$', '') as prefix,
            fm.status,
            COUNT(*) as cnt
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fo.source = 'kalshi'
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 30
    """)
    print("\n=== Kalshi top 30 ticker prefixes ===")
    for row in cur.fetchall():
        print(f"  {row[0]} [{row[1]}]: {row[2]:,}")

    # 3. Polymarket by category
    cur.execute("""
        SELECT COALESCE(fm.llm_sport_category, 'null'), fm.status, COUNT(*) as cnt
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fo.source = 'polymarket'
        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20
    """)
    print("\n=== Polymarket top 20 categories ===")
    for row in cur.fetchall():
        print(f"  {row[0]} [{row[1]}]: {row[2]:,}")

    # 4. Kalshi: how many are on resolved vs open markets?
    cur.execute("""
        SELECT fm.status, COUNT(DISTINCT fm.id) as markets, COUNT(*) as outcomes
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fo.source = 'kalshi'
        GROUP BY fm.status ORDER BY 3 DESC
    """)
    print("\n=== Kalshi pass2_guess: market status breakdown ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} markets, {row[2]:,} outcomes")

    # 5. Polymarket: how many are on resolved vs open markets?
    cur.execute("""
        SELECT fm.status, COUNT(DISTINCT fm.id) as markets, COUNT(*) as outcomes
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fo.source = 'polymarket'
        GROUP BY fm.status ORDER BY 3 DESC
    """)
    print("\n=== Polymarket pass2_guess: market status breakdown ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} markets, {row[2]:,} outcomes")

    # 6. Kalshi resolved markets with pass2_guess: do they have result data
    #    from the settled events API (resolution_date set)?
    cur.execute("""
        SELECT
            CASE WHEN fm.resolution_date IS NOT NULL THEN 'has_resolution_date'
                 ELSE 'no_resolution_date' END as has_date,
            COUNT(DISTINCT fm.id) as markets,
            COUNT(*) as outcomes
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess'
          AND fo.source = 'kalshi'
          AND fm.status = 'resolved'
        GROUP BY 1
    """)
    print("\n=== Kalshi resolved + pass2_guess: resolution_date presence ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} markets, {row[2]:,} outcomes")

    # 7. Spot-check: Kalshi resolved markets with pass2_guess where
    #    other outcomes on the same market HAVE api_settlement
    cur.execute("""
        SELECT COUNT(DISTINCT fm.id)
        FROM futures_markets fm
        WHERE fm.status = 'resolved'
          AND fm.source = 'kalshi'
          AND EXISTS (
              SELECT 1 FROM futures_outcomes fo
              WHERE fo.market_id = fm.id AND fo.resolution_source = 'pass2_guess'
          )
          AND EXISTS (
              SELECT 1 FROM futures_outcomes fo2
              WHERE fo2.market_id = fm.id AND fo2.resolution_source = 'api_settlement'
          )
    """)
    mixed = cur.fetchone()[0]
    print(f"\n=== Markets with MIXED resolution (some api_settlement, some pass2_guess) ===")
    print(f"  Kalshi: {mixed:,} markets")

    # 8. Are linked events (event_id) helping? Check if game markets
    #    have event scores that could resolve them
    cur.execute("""
        SELECT
            CASE WHEN fm.event_id IS NOT NULL THEN 'linked_to_event'
                 ELSE 'no_event' END as linkage,
            COUNT(DISTINCT fm.id) as markets,
            COUNT(*) as outcomes
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess'
          AND fo.source = 'kalshi'
        GROUP BY 1
    """)
    print("\n=== Kalshi pass2_guess: event linkage ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} markets, {row[2]:,} outcomes")

    # 9. Kalshi game markets with event_id: do those events have scores?
    cur.execute("""
        SELECT
            CASE WHEN e.home_score IS NOT NULL THEN 'has_scores'
                 ELSE 'no_scores' END as score_status,
            COUNT(DISTINCT fm.id) as markets,
            COUNT(*) as outcomes
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        JOIN events e ON fm.event_id = e.id
        WHERE fo.resolution_source = 'pass2_guess'
          AND fo.source = 'kalshi'
        GROUP BY 1
    """)
    print("\n=== Kalshi linked game markets: event score availability ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} markets, {row[2]:,} outcomes")

    # 10. How many Kalshi pass2_guess outcomes have is_winner=true vs false?
    cur.execute("""
        SELECT fo.is_winner, COUNT(*)
        FROM futures_outcomes fo
        WHERE fo.resolution_source = 'pass2_guess' AND fo.source = 'kalshi'
        GROUP BY fo.is_winner ORDER BY 1
    """)
    print("\n=== Kalshi pass2_guess: is_winner distribution ===")
    for row in cur.fetchall():
        print(f"  is_winner={row[0]}: {row[1]:,}")

    # 11. Same for Polymarket
    cur.execute("""
        SELECT fo.is_winner, COUNT(*)
        FROM futures_outcomes fo
        WHERE fo.resolution_source = 'pass2_guess' AND fo.source = 'polymarket'
        GROUP BY fo.is_winner ORDER BY 1
    """)
    print("\n=== Polymarket pass2_guess: is_winner distribution ===")
    for row in cur.fetchall():
        print(f"  is_winner={row[0]}: {row[1]:,}")

    # 12. Kalshi: age distribution of pass2_guess outcomes
    cur.execute("""
        SELECT
            CASE
                WHEN fm.commence_time > NOW() - INTERVAL '30 days' THEN '0-30d'
                WHEN fm.commence_time > NOW() - INTERVAL '90 days' THEN '30-90d'
                WHEN fm.commence_time > NOW() - INTERVAL '180 days' THEN '90-180d'
                WHEN fm.commence_time > NOW() - INTERVAL '365 days' THEN '180-365d'
                ELSE '365d+'
            END as age_bucket,
            COUNT(*) as cnt
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fo.source = 'kalshi'
        GROUP BY 1
        ORDER BY MIN(fm.commence_time)
    """)
    print("\n=== Kalshi pass2_guess: age distribution ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    # 13. Polymarket: age distribution
    cur.execute("""
        SELECT
            CASE
                WHEN fm.commence_time > NOW() - INTERVAL '30 days' THEN '0-30d'
                WHEN fm.commence_time > NOW() - INTERVAL '90 days' THEN '30-90d'
                WHEN fm.commence_time > NOW() - INTERVAL '180 days' THEN '90-180d'
                WHEN fm.commence_time > NOW() - INTERVAL '365 days' THEN '180-365d'
                ELSE '365d+'
            END as age_bucket,
            COUNT(*) as cnt
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.resolution_source = 'pass2_guess' AND fo.source = 'polymarket'
        GROUP BY 1
        ORDER BY MIN(fm.commence_time)
    """)
    print("\n=== Polymarket pass2_guess: age distribution ===")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    # 14. Verify pass2_guess accuracy on Kalshi: spot-check resolved markets
    #     where the guess says is_winner=True — is calibration_probability >= 0.5?
    cur.execute("""
        SELECT
            CASE
                WHEN fo.calibration_probability >= 0.90 THEN 'cal>=0.90'
                WHEN fo.calibration_probability >= 0.50 THEN 'cal>=0.50'
                WHEN fo.calibration_probability IS NULL THEN 'cal_null'
                ELSE 'cal<0.50'
            END as bucket,
            COUNT(*)
        FROM futures_outcomes fo
        WHERE fo.resolution_source = 'pass2_guess'
          AND fo.source = 'kalshi'
          AND fo.is_winner = true
        GROUP BY 1 ORDER BY 2 DESC
    """)
    print("\n=== Kalshi pass2_guess winners: calibration_probability distribution ===")
    print("  (Winners should have high cal_prob — low values mean guess was wrong)")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    # 15. Same check for losers
    cur.execute("""
        SELECT
            CASE
                WHEN fo.calibration_probability <= 0.10 THEN 'cal<=0.10'
                WHEN fo.calibration_probability <= 0.50 THEN 'cal<=0.50'
                WHEN fo.calibration_probability IS NULL THEN 'cal_null'
                ELSE 'cal>0.50'
            END as bucket,
            COUNT(*)
        FROM futures_outcomes fo
        WHERE fo.resolution_source = 'pass2_guess'
          AND fo.source = 'kalshi'
          AND fo.is_winner = false
        GROUP BY 1 ORDER BY 2 DESC
    """)
    print("\n=== Kalshi pass2_guess losers: calibration_probability distribution ===")
    print("  (Losers should have low cal_prob — high values mean guess was wrong)")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
