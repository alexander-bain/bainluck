SELECT source, count(*) AS rows, count(DISTINCT event_id) AS events, min(id) AS min_id, max(id) AS max_id,
 min(reading->>'observed_at') AS oldest_obs, max(reading->>'observed_at') AS newest_obs
FROM owed_chart_points GROUP BY 1 ORDER BY 2 DESC
