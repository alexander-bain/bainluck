SELECT e.status, count(*) AS owed_rows, count(DISTINCT o.event_id) AS events,
 min(o.reading->>'observed_at') AS oldest_obs, percentile_disc(0.5) WITHIN GROUP (ORDER BY o.reading->>'observed_at') AS median_obs
FROM owed_chart_points o LEFT JOIN events e ON e.id=o.event_id
WHERE o.source='polymarket' GROUP BY 1 ORDER BY 2 DESC
