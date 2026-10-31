SELECT pid, application_name, state, wait_event_type, wait_event, round(extract(epoch FROM now()-xact_start)::numeric,2) AS xact_s,
 round(extract(epoch FROM now()-query_start)::numeric,2) AS q_s, pg_blocking_pids(pid) AS blockers, left(regexp_replace(query,'\s+',' ','g'),160) AS q
FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state<>'idle'
ORDER BY xact_start NULLS LAST LIMIT 40
