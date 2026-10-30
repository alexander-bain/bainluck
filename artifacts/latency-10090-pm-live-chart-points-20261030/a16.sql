SELECT now() AS at, queryid, calls, total_exec_time, shared_blk_read_time, shared_blks_read, shared_blks_hit, right(regexp_replace(query,'\s+',' ','g'), 90) AS q
FROM pg_stat_statements
WHERE (query ILIKE 'SELECT win_prob_snapshots.id%' AND calls > 1000000)
 OR query ~* '^D.LETE FROM owed_chart_points WHERE owed_chart_points.id'
 OR query ~* '^I.SERT INTO win_prob_snapshots \(event_id, source, captured_at'
ORDER BY queryid
