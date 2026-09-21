import json, os, subprocess
SQL = """
WITH base AS (
  SELECT o.market_id, o.name, o.current_probability AS p,
         o.current_yes_bid AS b, o.current_yes_ask AS a, m.name AS mname, m.source
  FROM futures_outcomes o JOIN futures_markets m ON m.id=o.market_id
  WHERE m.status='open' AND o.last_updated > NOW() - INTERVAL '2 days'
        AND o.current_probability IS NOT NULL
), mx AS (SELECT market_id, MAX(p) AS top_p FROM base GROUP BY market_id
), o AS (
  SELECT base.*, mx.top_p,
    ((base.b IS NOT NULL OR base.a IS NOT NULL)
      AND (COALESCE(base.a,1.0)-COALESCE(base.b,0.0)) >= 0.2) AS wide
  FROM base JOIN mx ON mx.market_id=base.market_id
), t AS (
  SELECT *,
    (wide AND (b IS NULL OR b<=0.05) AND ABS(p-(COALESCE(b,0.0)+COALESCE(a,1.0))/2)<0.0005) AS ph_old,
    (wide AND (b IS NULL OR b<=0.05) AND p>0.05 AND p=top_p) AS lead_hit
  FROM o
), agg AS (
  SELECT market_id, MAX(mname) AS mname, MAX(source) AS source,
    (ARRAY_AGG(name ORDER BY p DESC NULLS LAST))[1] AS old_leader,
    (ARRAY_AGG(p ORDER BY p DESC NULLS LAST))[1] AS old_p,
    (ARRAY_AGG(b ORDER BY p DESC NULLS LAST))[1] AS old_b,
    (ARRAY_AGG(a ORDER BY p DESC NULLS LAST))[1] AS old_a,
    (ARRAY_AGG(name ORDER BY (CASE WHEN ph_old OR lead_hit THEN 1 ELSE 0 END), p DESC NULLS LAST))[1] AS new_leader,
    (ARRAY_AGG(p ORDER BY (CASE WHEN ph_old OR lead_hit THEN 1 ELSE 0 END), p DESC NULLS LAST))[1] AS new_p,
    (ARRAY_AGG(b ORDER BY (CASE WHEN ph_old OR lead_hit THEN 1 ELSE 0 END), p DESC NULLS LAST))[1] AS new_b,
    bool_or(lead_hit) AS lead_hit
  FROM t GROUP BY market_id
)
SELECT market_id, source, mname, old_leader, old_p, old_b, old_a, new_leader, new_p, new_b
FROM agg WHERE lead_hit AND old_leader IS DISTINCT FROM new_leader
ORDER BY old_p DESC LIMIT 20
"""
body = json.dumps({"sql": " ".join(SQL.split()), "limit": 20})
out = subprocess.run(["curl","-s","-X","POST","-H",f"Authorization: Bearer {os.environ['ADMIN_TOKEN']}","-H","Content-Type: application/json","-d",body,f"{os.environ['BAINLUCK_API']}/api/admin/db-query"],capture_output=True,text=True).stdout
d=json.loads(out)
if "rows" not in d: print(out[:900]); raise SystemExit
for r in d["rows"]:
    m=dict(zip(d["columns"],r))
    print(f"{m['market_id']:>9} {m['source'][:10]:11}{str(m['mname'])[:44]:46} OLD {str(m['old_leader'])[:20]:21} p={m['old_p']} b={m['old_b']} a={m['old_a']}  ->  NEW {str(m['new_leader'])[:20]:21} p={m['new_p']} b={m['new_b']}")
