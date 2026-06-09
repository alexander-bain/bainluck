#!/usr/bin/env python3
"""Investigate why KXNCAAMBTOTAL and KXNCAABBGAME are stuck.

Usage: heroku run -a bainluck python3 scripts/investigate_plateau.py
"""
import os
import json
import psycopg2
import redis

url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
conn = psycopg2.connect(url)
cur = conn.cursor()
results = {}

# 1. KXNCAAMBTOTAL: check if game markets exist with same suffix
cur.execute("""
    SELECT fm.external_id
    FROM futures_markets fm
    WHERE fm.source = 'kalshi'
      AND fm.external_id LIKE 'KXNCAAMBTOTAL%%'
      AND fm.event_id IS NULL
      AND fm.status = 'resolved'
    LIMIT 10
""")
unlinked_totals = [r[0] for r in cur.fetchall()]
results["unlinked_total_tickers"] = unlinked_totals

# For each, check if a GAME market with the same suffix exists and HAS event_id
linkable = 0
not_linkable = 0
for ticker in unlinked_totals:
    suffix = ticker.split("-", 1)[1] if "-" in ticker else ""
    game_ticker = f"KXNCAAMBGAME-{suffix}"
    cur.execute("""
        SELECT fm.event_id FROM futures_markets fm
        WHERE fm.source = 'kalshi' AND fm.external_id = %s
    """, (game_ticker,))
    row = cur.fetchone()
    if row and row[0]:
        linkable += 1
    else:
        not_linkable += 1

results["ncaamb_total_linkable_via_game"] = linkable
results["ncaamb_total_not_linkable"] = not_linkable

# 2. Count ALL unlinked markets by prefix that could be linked via game suffix
cur.execute("""
    WITH unlinked AS (
        SELECT fm.external_id,
               regexp_replace(fm.external_id, '-.*', '') AS prefix,
               substring(fm.external_id from '-(.*)$') AS suffix
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'kalshi'
          AND fm.event_id IS NULL
          AND fm.status = 'resolved'
          AND fo.resolution_source = 'pass2_guess'
    )
    SELECT prefix, COUNT(DISTINCT suffix) AS markets
    FROM unlinked
    GROUP BY prefix
    ORDER BY 2 DESC
    LIMIT 15
""")
results["unlinked_by_prefix"] = {r[0]: r[1] for r in cur.fetchall()}

# 3. KXNCAABBGAME: why no scores? Check sport_key
cur.execute("""
    SELECT s.key, COUNT(e.id), COUNT(e.home_score)
    FROM events e
    JOIN sports s ON e.sport_id = s.id
    JOIN futures_markets fm ON fm.event_id = e.id
    WHERE fm.source = 'kalshi'
      AND fm.external_id LIKE 'KXNCAABBGAME%%'
    GROUP BY s.key
""")
results["ncaabb_game_sport_keys"] = [
    {"sport": r[0], "events": r[1], "with_scores": r[2]}
    for r in cur.fetchall()
]

# 4. Check if ESPN has NCAAB women's basketball coverage
cur.execute("""
    SELECT s.key, s.title, COUNT(e.id) AS total,
           COUNT(e.espn_id) AS has_espn,
           COUNT(e.home_score) AS has_score
    FROM events e
    JOIN sports s ON e.sport_id = s.id
    WHERE s.key LIKE '%%ncaa%%' OR s.key LIKE '%%college%%'
    GROUP BY s.key, s.title
    ORDER BY 3 DESC
""")
results["ncaa_sport_coverage"] = [
    {"key": r[0], "title": r[1], "events": r[2],
     "has_espn": r[3], "has_score": r[4]}
    for r in cur.fetchall()
]

# 5. Overall: how many pass2_guess could be linked via game ticker suffix?
cur.execute("""
    WITH unlinked_props AS (
        SELECT fm.id, fm.external_id,
               regexp_replace(fm.external_id, '^KX[A-Z]+', '') AS suffix_with_dash
        FROM futures_markets fm
        JOIN futures_outcomes fo ON fo.market_id = fm.id
        WHERE fm.source = 'kalshi'
          AND fm.event_id IS NULL
          AND fm.status = 'resolved'
          AND fo.resolution_source = 'pass2_guess'
    ),
    game_events AS (
        SELECT fm.external_id, fm.event_id
        FROM futures_markets fm
        WHERE fm.source = 'kalshi'
          AND fm.event_id IS NOT NULL
          AND (fm.external_id LIKE 'KXNBAGAME%%'
               OR fm.external_id LIKE 'KXNCAAMBGAME%%'
               OR fm.external_id LIKE 'KXNCAABBGAME%%'
               OR fm.external_id LIKE 'KXNHLGAME%%'
               OR fm.external_id LIKE 'KXMLBSTGAME%%'
               OR fm.external_id LIKE 'KXNFLGAME%%')
    )
    SELECT COUNT(DISTINCT up.id)
    FROM unlinked_props up
    JOIN game_events ge ON ge.external_id LIKE '%%' || up.suffix_with_dash
""")
results["total_linkable_via_game_suffix"] = cur.fetchone()[0]

conn.close()

# Save to Redis
ru = os.environ["REDIS_URL"]
rc = redis.from_url(ru, ssl_cert_reqs=None) if ru.startswith("rediss") else redis.from_url(ru)
rc.setex("bainluck:option_c_analysis", 86400, json.dumps(results))

# Print
for k, v in results.items():
    if isinstance(v, (dict, list)):
        print(f"{k}:")
        if isinstance(v, dict):
            for dk, dv in sorted(v.items(), key=lambda x: -(x[1] if isinstance(x[1], (int, float)) else 0)):
                print(f"  {dk}: {dv}")
        else:
            for item in v:
                print(f"  {item}")
    else:
        print(f"{k}: {v}")
