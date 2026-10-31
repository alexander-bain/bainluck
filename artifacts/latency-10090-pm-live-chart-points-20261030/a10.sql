SELECT calls, round(mean_exec_time::numeric,2) AS mean_ms, round(stddev_exec_time::numeric,1) AS sd, rows, regexp_replace(query, '\s+', ' ', 'g') AS q
FROM pg_stat_statements
WHERE query ILIKE 'SELECT win_prob_snapshots.id%' AND calls > 1000000
ORDER BY total_exec_time DESC LIMIT 6
