SELECT pg_size_pretty(pg_database_size(current_database())) AS db, version() AS v,
 (SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND xact_start < now()-interval '2 minutes') AS long_xacts
