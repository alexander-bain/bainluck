SELECT pg_size_pretty(pg_relation_size('win_prob_snapshots')) AS heap, pg_size_pretty(pg_indexes_size('win_prob_snapshots')) AS idx,
 pg_size_pretty(pg_relation_size('ix_winprob_event_source')) AS ix_es, pg_size_pretty(pg_relation_size('ix_winprob_captured')) AS ix_cap,
 (SELECT reltuples::bigint FROM pg_class WHERE relname='win_prob_snapshots') AS est_rows
