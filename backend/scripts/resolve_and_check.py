#!/usr/bin/env python3
"""Trigger resolve_winners, wait, and report results.

Usage: heroku run -a bainluck python3 scripts/resolve_and_check.py
"""
import os
import json
import time
import psycopg2
import redis

ru = os.environ["REDIS_URL"]
rc = redis.from_url(ru, ssl_cert_reqs=None) if ru.startswith("rediss") else redis.from_url(ru)

# Trigger resolve_winners via Celery
from app.tasks import celery_app
task = celery_app.send_task(
    "app.tasks.resolve_winners",
    kwargs={"limit": 2000},
    queue="background",
)
print(f"Triggered resolve_winners: {task.id}")

# Wait for it to complete (poll task metrics)
print("Waiting for completion...")
for i in range(60):
    time.sleep(10)
    data = rc.hgetall("bainluck:task_metrics:resolve_winners")
    if data:
        ts = data.get(b"last_success_at", b"").decode()
        if ts and ts > time.strftime("%Y-%m-%dT%H:%M", time.gmtime(time.time() - 30)):
            duration = data.get(b"last_duration_ms", b"?").decode()
            summary = data.get(b"last_result_summary", b"{}").decode()
            print(f"\nCompleted in {duration}ms")
            try:
                s = json.loads(summary)
                print(f"score: {s.get('score')}")
                print(f"clean: winners={s.get('clean_resolution',{}).get('winners',0)} losers={s.get('clean_resolution',{}).get('losers',0)}")
                print(f"kalshi_markets: {s.get('kalshi_markets')}")
            except:
                print(summary[:300])
            break
    if i % 6 == 5:
        print(f"  ...still waiting ({(i+1)*10}s)")
else:
    print("Timed out waiting for task")

# Now check the audit count
print("\n=== AUDIT ===")
url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
conn = psycopg2.connect(url)
cur = conn.cursor()

cur.execute("""
    SELECT fm.source, COUNT(fo.id)
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fo.resolution_source = 'pass2_guess'
    GROUP BY fm.source ORDER BY 2 DESC
""")
total = 0
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]:,}")
    total += row[1]
print(f"  TOTAL: {total:,}")

cur.execute("""
    SELECT regexp_replace(fm.external_id, '-.*', ''), COUNT(fo.id)
    FROM futures_outcomes fo
    JOIN futures_markets fm ON fo.market_id = fm.id
    WHERE fo.resolution_source = 'pass2_guess' AND fm.source = 'kalshi'
    GROUP BY 1 ORDER BY 2 DESC LIMIT 5
""")
print("\nTop 5 Kalshi:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]:,}")

conn.close()
