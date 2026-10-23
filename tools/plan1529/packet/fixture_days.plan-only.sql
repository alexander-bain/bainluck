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
SELECT sport_key, fixture_day, COUNT(*) FROM g GROUP BY 1, 2;
ROLLBACK;
