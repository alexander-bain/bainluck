WITH pop AS (
  SELECT o.market_id, o.current_probability AS p,
         o.current_yes_bid AS b, o.current_yes_ask AS a
  FROM futures_outcomes o
  JOIN futures_markets m ON m.id = o.market_id
  WHERE m.status = 'open' AND NOT m.mutually_exclusive
    AND o.last_updated > NOW() - INTERVAL '2 days'
    AND o.current_probability IS NOT NULL
), best AS (
  SELECT market_id,
         MAX(p) FILTER (WHERE b > 0.05) AS best_bid_p,
         SUM(p) AS psum,
         COUNT(*) AS legs
  FROM pop GROUP BY market_id
), flagged AS (
  SELECT pop.market_id, pop.p,
         (COALESCE(pop.b, 0) <= 0.05
          AND pop.p > best.best_bid_p
          AND (COALESCE(pop.a, 1) - COALESCE(pop.b, 0)) >= 0.2
          AND (pop.b IS NOT NULL OR pop.a IS NOT NULL)) AS would_hide
  FROM pop JOIN best ON best.market_id = pop.market_id
  WHERE best.psum > 1.25 AND best.best_bid_p IS NOT NULL
)
SELECT f.market_id,
       b.legs,
       ROUND(b.psum, 3) AS psum,
       COUNT(*) FILTER (WHERE f.would_hide) AS hidden,
       ROUND(SUM(f.p) FILTER (WHERE NOT f.would_hide), 3) AS remainder
FROM flagged f JOIN best b ON b.market_id = f.market_id
GROUP BY f.market_id, b.legs, b.psum
HAVING COUNT(*) FILTER (WHERE f.would_hide) > 0
   AND SUM(f.p) FILTER (WHERE NOT f.would_hide) BETWEEN 0.75 AND 1.25
ORDER BY f.market_id
