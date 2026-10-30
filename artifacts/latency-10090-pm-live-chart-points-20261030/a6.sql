SELECT (SELECT count(*) FROM owed_chart_points WHERE source='polymarket') AS pm_owed,
 (SELECT max(id) FROM win_prob_snapshots) AS max_snap_id, now() AS at
