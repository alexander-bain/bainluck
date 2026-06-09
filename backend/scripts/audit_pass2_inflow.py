#!/usr/bin/env python3
"""Audit: are new pass2_guess outcomes still being created?

Usage: heroku run -a bainluck python3 scripts/audit_pass2_inflow.py
"""
import os
import json
import psycopg2
import redis

url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
conn = psycopg2.connect(url)
cur = conn.cursor()
results = {}

# 1. pass2_guess on recently-resolved markets (proxy for new inflow)
cur.execute("""
    SELECT DATE(fm.resolution_date), COUNT(fo.id)
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fo.resolution_source = 'pass2_guess'
      AND fm.resolution_date > NOW() - INTERVAL '14 days'
    GROUP BY 1
    ORDER BY 1
""")
results["pass2_guess_on_recent_markets"] = {str(r[0]): r[1] for r in cur.fetchall()}

# 2. All code paths that write 'pass2_guess' - check if retrotag2 is still active
cur.execute("""
    SELECT COUNT(*) FROM futures_outcomes
    WHERE resolution_source IS NULL
      AND is_winner = true
      AND current_probability IS NOT NULL
      AND current_probability > 0.05
      AND current_probability < 0.95
      AND market_id IN (SELECT id FROM futures_markets WHERE status = 'resolved')
""")
results["retrotag2_candidates"] = cur.fetchone()[0]

# 3. NULL resolution_source outcomes (the retrotag pool)
cur.execute("""
    SELECT COUNT(*) FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fm.status = 'resolved' AND fo.resolution_source IS NULL
""")
results["total_null_source"] = cur.fetchone()[0]

# 4. Current totals
cur.execute("""
    SELECT fm.source, COUNT(*)
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fo.resolution_source = 'pass2_guess'
    GROUP BY fm.source ORDER BY 2 DESC
""")
results["current_totals"] = {r[0]: r[1] for r in cur.fetchall()}

conn.close()

# Save to Redis
ru = os.environ["REDIS_URL"]
rc = redis.from_url(ru, ssl_cert_reqs=None) if ru.startswith("rediss") else redis.from_url(ru)
rc.setex("bainluck:option_c_analysis", 86400, json.dumps(results))

for k, v in results.items():
    if isinstance(v, dict):
        print(f"{k}:")
        for dk, dv in v.items():
            print(f"  {dk}: {dv}")
    else:
        print(f"{k}: {v}")
