#!/usr/bin/env python3
"""Run Option C analysis queries and save to a file for review.

Usage: heroku run --app bainluck python3 scripts/option_c_analysis.py
"""
import os
import json
import psycopg2

url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
conn = psycopg2.connect(url)
cur = conn.cursor()

results = {}

cur.execute("""
    SELECT COUNT(*) FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fo.resolution_source = 'clean_resolution'
      AND fo.is_winner = true
      AND fm.source = 'kalshi' AND fm.status = 'resolved'
""")
results["1_kalshi_clean_resolution_winners"] = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(DISTINCT fm.id) FROM futures_markets fm
    JOIN futures_outcomes fo ON fo.market_id = fm.id
    WHERE fm.source = 'kalshi' AND fm.status = 'resolved'
      AND fo.resolution_source = 'clean_resolution' AND fo.is_winner = true
      AND EXISTS (
          SELECT 1 FROM futures_outcomes fo2
          WHERE fo2.market_id = fm.id AND fo2.resolution_source = 'pass2_guess'
      )
""")
results["2_markets_with_clean_winner_AND_pass2guess_sibling"] = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(fo.id) FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    JOIN events e ON fm.event_id = e.id
    WHERE fo.resolution_source = 'clean_resolution'
      AND fo.is_winner = true AND fm.source = 'kalshi'
      AND e.home_score IS NOT NULL AND e.status IN ('completed', 'closed')
""")
results["3_clean_winners_with_game_scores"] = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(fo.id) FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    JOIN events e ON fm.event_id = e.id
    WHERE fo.resolution_source = 'pass2_guess'
      AND fm.source = 'kalshi' AND fm.status = 'resolved'
      AND e.home_score IS NOT NULL AND e.status IN ('completed', 'closed')
      AND EXISTS (
          SELECT 1 FROM futures_outcomes fo2
          WHERE fo2.market_id = fm.id
            AND fo2.resolution_source = 'clean_resolution'
            AND fo2.is_winner = true
      )
""")
results["4_pass2_guess_BLOCKED_by_clean_winner_sibling"] = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(fo.id) FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    JOIN events e ON fm.event_id = e.id
    WHERE fo.resolution_source = 'clean_resolution'
      AND fo.is_winner = true AND fm.source = 'kalshi'
      AND e.home_score IS NOT NULL AND e.status IN ('completed', 'closed')
      AND EXISTS (
          SELECT 1 FROM futures_outcomes fo2
          WHERE fo2.market_id = fm.id
            AND fo2.resolution_source IN ('pass2_guess', 'pass2_loser',
                'binary_higher_wins', 'multi_max_prob')
      )
""")
results["5_option_c_re_null_count"] = cur.fetchone()[0]

cur.execute("""
    SELECT regexp_replace(fm.external_id, '-.*', ''), COUNT(fo.id)
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    JOIN events e ON fm.event_id = e.id
    WHERE fo.resolution_source = 'clean_resolution'
      AND fo.is_winner = true AND fm.source = 'kalshi'
      AND e.home_score IS NOT NULL
    GROUP BY 1 ORDER BY 2 DESC LIMIT 15
""")
results["6_by_ticker_prefix"] = {r[0]: r[1] for r in cur.fetchall()}

cur.execute("""
    SELECT
        CASE
            WHEN fo.current_probability >= 0.95 THEN 'prob>=0.95'
            WHEN fo.current_probability >= 0.50 THEN 'prob 0.50-0.95'
            WHEN fo.current_probability IS NULL THEN 'prob NULL'
            ELSE 'prob<0.50 (LIKELY WRONG)'
        END, COUNT(*)
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fo.resolution_source = 'clean_resolution'
      AND fo.is_winner = true AND fm.source = 'kalshi'
    GROUP BY 1 ORDER BY 2 DESC
""")
results["7_winner_probability_distribution"] = {r[0]: r[1] for r in cur.fetchall()}

cur.execute("""
    SELECT fm.source, fo.is_winner, COUNT(*)
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fo.resolution_source = 'clean_resolution'
    GROUP BY 1, 2 ORDER BY 3 DESC
""")
results["8_all_clean_resolution_by_source"] = [
    {"source": r[0], "is_winner": r[1], "count": r[2]} for r in cur.fetchall()
]

conn.close()

# Save to Redis with 24h TTL
import redis
import ssl
ru = os.environ["REDIS_URL"]
rc = redis.from_url(ru, ssl_cert_reqs=None) if ru.startswith("rediss") else redis.from_url(ru)
rc.setex("bainluck:option_c_analysis", 86400, json.dumps(results))

# Also print
for k, v in results.items():
    print(f"{k}: {json.dumps(v) if isinstance(v, (dict, list)) else v}")
