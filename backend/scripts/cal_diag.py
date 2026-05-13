import os, psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"], sslmode="require")
cur = conn.cursor()
cur.execute("""
    SELECT COALESCE(fm.llm_sport_category, 'uncategorized') AS cat,
        COUNT(*) AS total,
        COUNT(CASE WHEN fo.calibration_probability = fo.opening_probability THEN 1 END) AS cal_eq_open,
        COUNT(CASE WHEN fo.calibration_probability IS NOT NULL AND fo.calibration_probability != fo.opening_probability THEN 1 END) AS cal_diff,
        ROUND(AVG(ABS(COALESCE(fo.calibration_probability, 0) - COALESCE(fo.opening_probability, 0)))::numeric, 4) AS avg_shift
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.status = 'resolved'
      AND fo.opening_probability IS NOT NULL
      AND fo.opening_probability > 0 AND fo.opening_probability < 1
      AND COALESCE(fm.llm_sport_category, 'uncategorized') IN ('economics', 'hockey', 'golf', 'tennis', 'weather', 'politics')
    GROUP BY cat ORDER BY total DESC
""")
print("=== Calibration vs Opening by Category ===")
for r in cur.fetchall():
    cat, total, eq, diff, shift = r
    pct = eq * 100 // max(total, 1)
    print(f"  {cat:12s}: total={total:>6,}  same={eq:>6,} ({pct:>2}%)  diff={diff:>6,}  shift={shift}")

cur.execute("""
    SELECT COALESCE(fm.llm_sport_category, 'uncategorized') AS cat, fm.source,
        COUNT(*) AS n,
        COUNT(CASE WHEN ABS(COALESCE(fo.calibration_probability, fo.opening_probability) - 0.5) < 0.05 THEN 1 END) AS near_50,
        COUNT(CASE WHEN fo.calibration_probability = fo.opening_probability THEN 1 END) AS same_as_open,
        COUNT(CASE WHEN fm.commence_time IS NULL THEN 1 END) AS no_commence
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.status = 'resolved'
      AND fo.opening_probability > 0 AND fo.opening_probability < 1
      AND fo.current_probability IS NOT NULL
      AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
      AND COALESCE(fm.llm_sport_category, 'uncategorized') IN ('economics', 'hockey', 'golf')
    GROUP BY cat, fm.source ORDER BY cat, fm.source
""")
print("\n=== Problem categories: resolved outcomes in calibration ===")
for r in cur.fetchall():
    cat, src, n, near50, same, nocom = r
    print(f"  {cat:12s} {src:12s}: n={n:>5,}  near_50={near50:>5,} ({near50*100//max(n,1):>2}%)  same_as_open={same:>5,} ({same*100//max(n,1):>2}%)  no_commence={nocom:>5,}")

cur.execute("""
    SELECT COALESCE(fm.llm_sport_category, 'uncategorized') AS cat, fm.source,
        COUNT(*) AS n,
        AVG(
            (SELECT COUNT(*) FROM futures_odds_snapshots fos WHERE fos.outcome_id = fo.id)
        ) AS avg_snapshots
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fm.id = fo.market_id
    WHERE fm.status = 'resolved'
      AND fo.opening_probability > 0 AND fo.opening_probability < 1
      AND ABS(COALESCE(fo.calibration_probability, fo.opening_probability) - 0.5) < 0.05
      AND fo.current_probability IS NOT NULL
      AND (fo.current_probability >= 0.95 OR fo.current_probability <= 0.05)
      AND COALESCE(fm.llm_sport_category, 'uncategorized') IN ('economics', 'hockey', 'golf')
    GROUP BY cat, fm.source ORDER BY cat, fm.source
    LIMIT 10
""")
print("\n=== Near-50% outcomes: avg snapshots ===")
for r in cur.fetchall():
    cat, src, n, avg_snaps = r
    print(f"  {cat:12s} {src:12s}: n={n:>5,}  avg_snapshots={float(avg_snaps):.1f}")

conn.close()
