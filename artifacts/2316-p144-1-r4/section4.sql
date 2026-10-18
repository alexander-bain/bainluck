\set ON_ERROR_STOP off
SET statement_timeout = 0;
SET lock_timeout      = '60s';   -- bounds each lock wait of each DROP attempt
-- First: P1c. A build can outlive the session that started it. Any row means HOLD: drop nothing.
\unset no_build_in_flight
SELECT count(*) = 0 AS no_build_in_flight FROM pg_stat_progress_create_index
 WHERE relid = 'futures_markets'::regclass \gset
\if :no_build_in_flight
-- Attempt 1 of 2.
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_external_id_trgm;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_llm_sport_category;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sport_id;
-- Between attempts, for the receipt. IF EXISTS makes attempt 2 a no-op for any name already gone.
SELECT c.relname, i.indisvalid, i.indisready FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');
-- Attempt 2 of 2, the last.
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_external_id_trgm;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_llm_sport_category;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sport_id;
\else
\echo HOLD: an index build is in flight on futures_markets. Nothing was dropped.
SELECT pid, phase, index_relid::regclass FROM pg_stat_progress_create_index
 WHERE relid = 'futures_markets'::regclass;
\endif
-- Final read. 0 rows: ROLLED BACK. Any row: ROLLBACK INCOMPLETE. Nothing runs after it.
SELECT c.relname, i.indisvalid, i.indisready FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');
