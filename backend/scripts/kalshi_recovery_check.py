#!/usr/bin/env python3
"""Kalshi recovery status check — run with: ! python3 backend/scripts/kalshi_recovery_check.py

Connects directly to the production DB using DATABASE_URL from environment.
Source .env.claude first: source .env.claude
"""

import os
import sys

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("ERROR: DATABASE_URL not set. Run: source .env.claude")
    sys.exit(1)

import psycopg2

conn = psycopg2.connect(db_url.replace("postgres://", "postgresql://"), sslmode="require")
cur = conn.cursor()

print("=" * 70)
print("KALSHI RECOVERY STATUS CHECK")
print("=" * 70)

# 1. Overall status by market status
cur.execute("""
    SELECT fm.status, COUNT(DISTINCT fm.id) AS markets,
           COUNT(fo.id) AS outcomes,
           COUNT(fo.id) FILTER (WHERE fo.is_winner IS NOT NULL) AS has_winner,
           COUNT(fo.id) FILTER (WHERE fo.calibration_probability IS NOT NULL) AS has_cal_prob,
           COUNT(fo.id) FILTER (WHERE fo.opening_probability IS NOT NULL) AS has_opening
    FROM futures_markets fm
    JOIN futures_outcomes fo ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi'
    GROUP BY fm.status ORDER BY fm.status
""")
print("\n1. OVERALL STATUS")
print(f"{'status':>10s} {'markets':>8s} {'outcomes':>9s} {'winner':>8s} {'cal_prob':>9s} {'opening':>9s}")
for r in cur.fetchall():
    print(f"{r[0]:>10s} {r[1]:>8d} {r[2]:>9d} {r[3]:>8d} {r[4]:>9d} {r[5]:>9d}")

# 2. Calibration probability gap analysis
cur.execute("""
    SELECT
        COUNT(*) AS total_missing_cal,
        COUNT(*) FILTER (WHERE fo.opening_probability IS NOT NULL) AS has_opening,
        COUNT(*) FILTER (WHERE fo.opening_probability IS NULL) AS no_opening,
        COUNT(*) FILTER (WHERE EXISTS (
            SELECT 1 FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
        )) AS has_snapshots,
        COUNT(*) FILTER (WHERE NOT EXISTS (
            SELECT 1 FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id
        )) AS no_snapshots
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
      AND fo.calibration_probability IS NULL
""")
r = cur.fetchone()
print(f"\n2. CALIBRATION PROBABILITY GAP ({r[0]} missing)")
print(f"   Has opening_probability: {r[1]}")
print(f"   No opening_probability:  {r[2]}")
print(f"   Has snapshots:           {r[3]}")
print(f"   No snapshots:            {r[4]}")

# 3. Event linkage breakdown for stuck outcomes
cur.execute("""
    SELECT
        CASE WHEN fm.event_id IS NOT NULL THEN 'event-linked' ELSE 'no-event' END AS link,
        COUNT(*)
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
      AND fo.calibration_probability IS NULL
      AND fo.opening_probability IS NOT NULL
    GROUP BY 1
""")
print(f"\n3. STUCK OUTCOMES WITH opening_probability (should get cal_prob via fallback)")
for r in cur.fetchall():
    print(f"   {r[0]}: {r[1]}")

# 4. Coverage percentages
cur.execute("""
    SELECT
        ROUND(100.0 * COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS winner_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE fo.calibration_probability IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS cal_pct,
        COUNT(*) AS total
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
""")
r = cur.fetchone()
print(f"\n4. COVERAGE SUMMARY (resolved Kalshi)")
print(f"   is_winner:              {r[0]}%")
print(f"   calibration_probability: {r[1]}%")
print(f"   total outcomes:          {r[2]}")

# 5. Polymarket comparison
cur.execute("""
    SELECT
        ROUND(100.0 * COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS winner_pct,
        ROUND(100.0 * COUNT(*) FILTER (WHERE fo.calibration_probability IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS cal_pct,
        COUNT(*) AS total
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fm.source = 'polymarket' AND fm.status = 'resolved'
""")
r = cur.fetchone()
print(f"\n5. POLYMARKET COMPARISON (resolved)")
print(f"   is_winner:              {r[0]}%")
print(f"   calibration_probability: {r[1]}%")
print(f"   total outcomes:          {r[2]}")

# 6. Celery queue check (via simple select, not API)
print(f"\n6. BACKGROUND TASKS")
print(f"   (Run 'curl -s api.bainluck.com/api/admin/celery-debug?secret=$ADMIN_TOKEN' to check queue)")

print("\n" + "=" * 70)
conn.close()
