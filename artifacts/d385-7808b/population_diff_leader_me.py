import json, os, subprocess
SQL = """
WITH base AS (
  SELECT o.market_id, o.name, o.current_probability AS p,
         o.current_yes_bid AS b, o.current_yes_ask AS a, m.group_type, m.mutually_exclusive AS me
  FROM futures_outcomes o JOIN futures_markets m ON m.id=o.market_id
  WHERE m.status='open' AND o.last_updated > NOW() - INTERVAL '2 days'
        AND o.current_probability IS NOT NULL
), mx AS (
  SELECT market_id, MAX(p) AS top_p FROM base GROUP BY market_id
), o AS (
  SELECT base.*, mx.top_p,
         ((base.b IS NOT NULL OR base.a IS NOT NULL)
          AND (COALESCE(base.a,1.0) - COALESCE(base.b,0.0)) >= 0.2) AS wide
  FROM base JOIN mx ON mx.market_id = base.market_id
), t AS (
  SELECT *,
    (wide AND (b IS NULL OR b <= 0.05)
       AND ABS(p - (COALESCE(b,0.0)+COALESCE(a,1.0))/2) < 0.0005) AS ph_old,
    ((wide AND (b IS NULL OR b <= 0.05)
       AND ABS(p - (COALESCE(b,0.0)+COALESCE(a,1.0))/2) < 0.0005)
     OR (me AND wide AND (b IS NULL OR b <= 0.05) AND p > 0.05 AND p = top_p)) AS ph_new,
    (b IS NOT NULL OR a IS NOT NULL) AS has_book
  FROM o
), agg AS (
  SELECT market_id,
         bool_or(group_type='negrisk') AS is_excl,
         COUNT(*) FILTER (WHERE ph_old) AS ph_old_n,
         COUNT(*) FILTER (WHERE ph_new) AS ph_new_n,
         COUNT(*) FILTER (WHERE has_book) AS book_n,
         COUNT(*) FILTER (WHERE has_book AND NOT ph_old) AS real_old,
         COUNT(*) FILTER (WHERE has_book AND NOT ph_new) AS real_new,
         COALESCE(SUM(p) FILTER (WHERE NOT ph_old),0) AS sum_old,
         COALESCE(SUM(p) FILTER (WHERE NOT ph_new),0) AS sum_new,
         (ARRAY_AGG(name ORDER BY (CASE WHEN ph_old THEN 1 ELSE 0 END), p DESC NULLS LAST))[1] AS leader_old,
         (ARRAY_AGG(name ORDER BY (CASE WHEN ph_new THEN 1 ELSE 0 END), p DESC NULLS LAST))[1] AS leader_new
  FROM t GROUP BY market_id
), d AS (
  SELECT *,
    CASE WHEN ph_old_n=0 THEN false
         WHEN real_old=0 THEN true
         WHEN book_n>=3 AND real_old<2 THEN true
         WHEN is_excl THEN NOT (sum_old BETWEEN 0.75 AND 1.25)
         ELSE false END AS drop_old,
    CASE WHEN ph_new_n=0 THEN false
         WHEN real_new=0 THEN true
         WHEN book_n>=3 AND real_new<2 THEN true
         WHEN is_excl THEN NOT (sum_new BETWEEN 0.75 AND 1.25)
         ELSE false END AS drop_new
  FROM agg
)
SELECT COUNT(*) AS markets,
       COUNT(*) FILTER (WHERE ph_old_n>0) AS markets_touched_old,
       COUNT(*) FILTER (WHERE ph_new_n>0) AS markets_touched_new,
       SUM(ph_old_n) AS outcomes_hidden_old,
       SUM(ph_new_n) AS outcomes_hidden_new,
       COUNT(*) FILTER (WHERE leader_old IS DISTINCT FROM leader_new) AS leader_changes,
       COUNT(*) FILTER (WHERE drop_old AND NOT drop_new) AS cards_newly_kept,
       COUNT(*) FILTER (WHERE drop_new AND NOT drop_old) AS cards_newly_dropped
FROM d
"""
body = json.dumps({"sql": " ".join(SQL.split()), "limit": 10})
out = subprocess.run(["curl","-s","-X","POST","-H",f"Authorization: Bearer {os.environ['ADMIN_TOKEN']}","-H","Content-Type: application/json","-d",body,f"{os.environ['BAINLUCK_API']}/api/admin/db-query"],capture_output=True,text=True).stdout
d=json.loads(out)
if "rows" in d:
    print(json.dumps(dict(zip(d["columns"], d["rows"][0])), indent=1), "duration_ms", d.get("duration_ms"))
else:
    print(out[:800])
