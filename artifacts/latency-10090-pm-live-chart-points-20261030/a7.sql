SELECT source, COALESCE(game_state->>'poll_type','(none)') AS pt, count(*) AS rows, min(captured_at) AS min_cap, max(captured_at) AS max_cap, now() AS at,
 (SELECT count(*) FROM owed_chart_points WHERE source='polymarket') AS pm_owed
FROM win_prob_snapshots WHERE id > 25421769 GROUP BY 1,2 ORDER BY 3 DESC
