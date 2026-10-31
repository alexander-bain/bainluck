SELECT calls, round(mean_exec_time::numeric,2) AS mean_ms, round(min_exec_time::numeric,2) AS min_ms,
 round(shared_blks_hit::numeric/calls,1) AS hit_per_call, round(shared_blks_read::numeric/calls,2) AS read_per_call,
 round((shared_blk_read_time/calls)::numeric,2) AS read_ms_per_call, current_setting('track_io_timing') AS tio,
 (SELECT stats_reset FROM pg_stat_statements_info) AS since,
 left(regexp_replace(query,'\s+',' ','g'), 60) || ' ... ' || right(regexp_replace(query,'\s+',' ','g'), 140) AS q
FROM pg_stat_statements
WHERE query ILIKE 'SELECT win_prob_snapshots.id%' AND calls > 1000000
ORDER BY total_exec_time DESC LIMIT 4
