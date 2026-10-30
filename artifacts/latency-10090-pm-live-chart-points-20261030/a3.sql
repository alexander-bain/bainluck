SELECT source, count(*) AS rows, min(id) AS min_id, min(reading->>'observed_at') AS oldest_obs, now() AS at
FROM owed_chart_points WHERE source IN ('polymarket','kalshi') GROUP BY 1
