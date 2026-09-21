import json, os, subprocess, sys
SQL = """
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
), agg AS (
  SELECT market_id, MAX(mname) AS mname, MAX(source) AS source,
         MAX(p) FILTER (WHERE buyer) AS best_bid_p,
         MAX(p) AS top_p,
         COUNT(*) FILTER (WHERE buyer) AS buyers
  FROM f GROUP BY market_id
), hit AS (
  SELECT f.market_id, f.name, f.p, f.b, f.a, agg.mname, agg.source, agg.best_bid_p, agg.buyers
  FROM f JOIN agg ON agg.market_id=f.market_id
  WHERE f.wide AND (f.b IS NULL OR f.b <= 0.05) AND f.p > 0.05
        AND agg.best_bid_p IS NOT NULL AND f.p > agg.best_bid_p
)
SELECT COUNT(DISTINCT market_id) AS markets_touched, COUNT(*) AS legs_hidden FROM hit
"""
SQL2 = SQL.replace("SELECT COUNT(DISTINCT market_id) AS markets_touched, COUNT(*) AS legs_hidden FROM hit",
  "SELECT market_id, source, mname, name, p, b, a, best_bid_p, buyers FROM hit ORDER BY p DESC LIMIT 25")
def run(sql, limit):
    body = json.dumps({"sql": " ".join(sql.split()), "limit": limit})
    out = subprocess.run(["curl","-s","-X","POST","-H",f"Authorization: Bearer {os.environ['ADMIN_TOKEN']}","-H","Content-Type: application/json","-d",body,f"{os.environ['BAINLUCK_API']}/api/admin/db-query"],capture_output=True,text=True).stdout
    return json.loads(out)
d=run(SQL,5)
print(json.dumps(dict(zip(d["columns"], d["rows"][0])) if "rows" in d else d, indent=1))
d2=run(SQL2,25)
if "rows" in d2:
    for r in d2["rows"]:
        m=dict(zip(d2["columns"],r))
        print(f"{m['market_id']:>9} {m['source'][:10]:11}{str(m['mname'])[:40]:42} HIDE {str(m['name'])[:22]:23} p={m['p']} b={m['b']} a={m['a']} | best bid-backed p={m['best_bid_p']} ({m['buyers']} buyers)")
else:
    print(d2)
