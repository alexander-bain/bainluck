import json, os, subprocess
CORE = """
WITH base AS (
  SELECT o.market_id, o.name, o.current_probability AS p,
         o.current_yes_bid AS b, o.current_yes_ask AS a,
         m.name AS mname, m.source, m.mutually_exclusive AS me
  FROM futures_outcomes o JOIN futures_markets m ON m.id=o.market_id
  WHERE m.status='open' AND o.last_updated > NOW() - INTERVAL '2 days'
        AND o.current_probability IS NOT NULL
), f AS (
  SELECT *,
    ((b IS NOT NULL OR a IS NOT NULL) AND (COALESCE(a,1.0)-COALESCE(b,0.0)) >= 0.2) AS wide,
    (b IS NOT NULL AND b > 0.05) AS buyer
  FROM base WHERE me
), agg0 AS (
  SELECT market_id, MAX(p) FILTER (WHERE buyer) AS best_bid_p, SUM(p) AS psum, COUNT(*) AS legs,
         MAX(mname) AS mname, MAX(source) AS source
  FROM f GROUP BY market_id
), marked AS (
  SELECT f.*, agg0.best_bid_p, agg0.psum, agg0.legs, agg0.mname AS mkt, agg0.source AS src,
    (agg0.psum > 1.25 AND agg0.best_bid_p IS NOT NULL AND f.wide
     AND (f.b IS NULL OR f.b <= 0.05) AND f.p > 0.05 AND f.p > agg0.best_bid_p) AS hide
  FROM f JOIN agg0 ON agg0.market_id=f.market_id
), agg1 AS (
  SELECT market_id, MAX(mkt) AS mkt, MAX(src) AS src, MAX(psum) AS psum, MAX(legs) AS legs,
         COUNT(*) FILTER (WHERE hide) AS hidden,
         COALESCE(SUM(p) FILTER (WHERE NOT hide),0) AS survivor_sum,
         COUNT(*) FILTER (WHERE NOT hide) AS survivors,
         (ARRAY_AGG(name ORDER BY p DESC NULLS LAST))[1] AS old_leader,
         (ARRAY_AGG(name ORDER BY (CASE WHEN hide THEN 1 ELSE 0 END), p DESC NULLS LAST))[1] AS new_leader
  FROM marked GROUP BY market_id
), rep AS (
  SELECT *, (hidden > 0 AND survivor_sum BETWEEN 0.75 AND 1.25 AND survivors >= 2) AS repairable
  FROM agg1
)
"""
Q1 = CORE + "SELECT COUNT(*) FILTER (WHERE hidden>0) AS fields_with_an_inversion, COUNT(*) FILTER (WHERE repairable) AS fields_repaired, SUM(hidden) FILTER (WHERE repairable) AS legs_hidden, COUNT(*) FILTER (WHERE repairable AND old_leader IS DISTINCT FROM new_leader) AS leader_changes FROM rep"
Q2 = CORE + "SELECT market_id, src, mkt, legs, psum, hidden, survivor_sum, old_leader, new_leader FROM rep WHERE repairable ORDER BY psum DESC LIMIT 60"
def run(sql, limit):
    body = json.dumps({"sql": " ".join(sql.split()), "limit": limit})
    out = subprocess.run(["curl","-s","-X","POST","-H",f"Authorization: Bearer {os.environ['ADMIN_TOKEN']}","-H","Content-Type: application/json","-d",body,f"{os.environ['BAINLUCK_API']}/api/admin/db-query"],capture_output=True,text=True).stdout
    return json.loads(out)
d=run(Q1,5); print(json.dumps(dict(zip(d["columns"], d["rows"][0])) if "rows" in d else d, indent=1))
d2=run(Q2,60)
if "rows" in d2:
    for r in d2["rows"]:
        m=dict(zip(d2["columns"],r))
        print(f"{m['market_id']:>9} {m['src'][:10]:11}{str(m['mkt'])[:40]:42} legs={m['legs']:>3} sum={float(m['psum']):.2f}->{float(m['survivor_sum']):.2f} hid={m['hidden']:>2}  {str(m['old_leader'])[:22]:23}-> {str(m['new_leader'])[:22]}")
else: print(d2)
