SELECT left(regexp_replace(query, '\s+', ' ', 'g'), 220) AS q, calls, round(mean_exec_time::numeric,2) AS mean_ms, round(max_exec_time::numeric,1) AS max_ms, round(total_exec_time::numeric/1000,1) AS total_s
FROM pg_stat_statements
WHERE query ILIKE '%win_prob_snapshots%' OR query ILIKE '%owed_chart_points%'
ORDER BY total_exec_time DESC LIMIT 25
