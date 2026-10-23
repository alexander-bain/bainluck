-- INERT REVIEW MATERIAL: NOT ADMITTED; no caller exists for this packet.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '2s';
SET LOCAL lock_timeout = '500ms';
EXPLAIN (FORMAT JSON)
WITH g AS (
  SELECT e.id, s.key AS sport_key, e.home_team_name, e.away_team_name,
         (e.commence_time AT TIME ZONE 'UTC')::date AS fixture_day
  FROM events e
  JOIN sports s ON s.id = e.sport_id
  WHERE e.status IN ('completed', 'closed')
    AND e.commence_time >= NOW() - INTERVAL '30 days'
)

        SELECT g.sport_key, fm.source, COUNT(fo.id), 
COUNT(*) FILTER (
  WHERE fo.calibration_probability IS DISTINCT FROM fo.opening_probability
    AND fo.opening_probability IS NOT NULL
)
,
               COUNT(*) FILTER (WHERE fo.volume > 0), COUNT(*) FILTER (WHERE fo.volume IS NULL), 
COUNT(*) FILTER (
  WHERE fo.volume > 0
    AND NOT (fo.calibration_probability IS DISTINCT FROM fo.opening_probability
             AND fo.opening_probability IS NOT NULL)
)

        FROM futures_markets fm
        JOIN g ON g.id = fm.event_id
        LEFT JOIN futures_outcomes fo ON fo.market_id = fm.id
        GROUP BY g.sport_key, fm.source
        HAVING COUNT(fo.id) > 0
        ORDER BY g.sport_key, 3 DESC;
ROLLBACK;
