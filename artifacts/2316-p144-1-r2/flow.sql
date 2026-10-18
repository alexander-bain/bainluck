\set ON_ERROR_STOP on
\echo === section 4 (clear)
SET statement_timeout = 0;
SET lock_timeout      = '60s';
-- First: P1c must return no row (a build can outlive the session that started it).
SELECT pid, phase, index_relid::regclass FROM pg_stat_progress_create_index
 WHERE relid = 'futures_markets'::regclass;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_external_id_trgm;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_llm_sport_category;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sport_id;
-- Last: this read MUST return 0 rows. The rollback is not done until it does.
SELECT c.relname, i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');

\echo === A1
SET statement_timeout    = 0;        -- CONCURRENTLY must not be cut off mid-build
SET lock_timeout         = '60s';    -- '5s' fails in this database (LAT-P058)
SET maintenance_work_mem = '256MB';
-- P0: record the live index list for the run receipt (the 2026-08-24 snapshot predates ix_fm_open_category).
SELECT indexrelid::regclass AS index, pg_get_indexdef(indexrelid) AS def
  FROM pg_index WHERE indrelid = 'futures_markets'::regclass ORDER BY 1;
-- P1: nothing older than 60 s. A point-in-time check only: see "Why this is safe" below.
SELECT pid, now() - xact_start AS age, state, left(query, 80)
  FROM pg_stat_activity
 WHERE xact_start IS NOT NULL AND now() - xact_start > interval '60 seconds'
   AND pid <> pg_backend_pid();
-- P1b: no prepared transaction (it holds a snapshot no session shows).
SELECT gid, prepared, owner FROM pg_prepared_xacts;
-- P1c: no index build already in flight on this table.
SELECT pid, phase, index_relid::regclass FROM pg_stat_progress_create_index
 WHERE relid = 'futures_markets'::regclass;
-- P2: no leftover (possibly INVALID) index holding one of the three names.
SELECT c.relname, i.indisvalid, i.indisready FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');
-- P3: size. Steady-state ceiling 1,000 B (trigram) + 2 x 40 B (btrees) per tier-1-4 row;
-- abort when the estimate passes 400 MB or the statistics are missing.
WITH t AS (
  SELECT c.reltuples AS rows,
         (SELECT sum(u.f)
            FROM pg_stats s, unnest(s.most_common_vals::text::int[], s.most_common_freqs) AS u(v, f)
           WHERE s.schemaname = 'public' AND s.tablename = 'futures_markets'
             AND s.attname = 'market_tier' AND u.v BETWEEN 1 AND 4) AS t14_frac
    FROM pg_class c WHERE c.oid = 'futures_markets'::regclass)
SELECT rows::bigint, t14_frac, (rows * t14_frac)::bigint AS est_t14_rows,
       (rows * t14_frac * (1000 + 2 * 40))::bigint AS est_steady_bytes,
       coalesce(rows <= 0 OR rows * t14_frac * (1000 + 2 * 40) > 400 * 1024 * 1024, true) AS abort
  FROM t;
-- P4: the trigram opclass exists.
SELECT extversion FROM pg_extension WHERE extname = 'pg_trgm';
-- P5: write premise. Index-maintaining writes per second, averaged since the statistics epoch,
-- scaled to the tier-1-4 share. Abort above 300/s, or on less than an hour of statistics.
WITH w AS (
  SELECT t.n_tup_ins + t.n_tup_upd - t.n_tup_hot_upd AS nonhot_writes,
         extract(epoch FROM now() - coalesce(d.stats_reset, pg_postmaster_start_time())) AS secs
    FROM pg_stat_user_tables t, pg_stat_database d
   WHERE t.relid = 'futures_markets'::regclass AND d.datname = current_database()),
     f AS (
  SELECT sum(u.f) AS t14_frac
    FROM pg_stats s, unnest(s.most_common_vals::text::int[], s.most_common_freqs) AS u(v, f)
   WHERE s.schemaname = 'public' AND s.tablename = 'futures_markets'
     AND s.attname = 'market_tier' AND u.v BETWEEN 1 AND 4)
SELECT nonhot_writes, secs::bigint, round((nonhot_writes / secs)::numeric, 1) AS writes_per_s,
       round((nonhot_writes / secs * t14_frac)::numeric, 1) AS est_t14_writes_per_s,
       coalesce(secs < 3600 OR nonhot_writes / secs * t14_frac > 300, true) AS abort
  FROM w, f;

\echo === A2
CREATE INDEX CONCURRENTLY ix_fm_t14_llm_sport_category ON futures_markets (llm_sport_category) WHERE market_tier IN (1, 2, 3, 4);
CREATE INDEX CONCURRENTLY ix_fm_t14_sport_id ON futures_markets (sport_id) WHERE market_tier IN (1, 2, 3, 4);
CREATE INDEX CONCURRENTLY ix_fm_t14_external_id_trgm ON futures_markets USING gin (external_id gin_trgm_ops) WITH (fastupdate = on, gin_pending_list_limit = 4096) WHERE market_tier IN (1, 2, 3, 4);
-- The build-time size check: within = t for every row (330 B trigram, 40 B btree, per estimated tier-1-4 row).
WITH t AS (
  SELECT c.reltuples AS rows,
         (SELECT sum(u.f)
            FROM pg_stats s, unnest(s.most_common_vals::text::int[], s.most_common_freqs) AS u(v, f)
           WHERE s.schemaname = 'public' AND s.tablename = 'futures_markets'
             AND s.attname = 'market_tier' AND u.v BETWEEN 1 AND 4) AS t14_frac
    FROM pg_class c WHERE c.oid = 'futures_markets'::regclass)
SELECT c.relname, i.indisvalid, i.indisready, pg_relation_size(c.oid) AS bytes,
       (CASE WHEN c.relname = 'ix_fm_t14_external_id_trgm' THEN 330 ELSE 40 END * t.rows * t.t14_frac)::bigint AS bound,
       coalesce(pg_relation_size(c.oid) <= CASE WHEN c.relname = 'ix_fm_t14_external_id_trgm' THEN 330 ELSE 40 END * t.rows * t.t14_frac, false) AS within
  FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid, t
 WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');

\echo === A3
ANALYZE futures_markets;
\i /tmp/lat2316-fixture/r2/gate.sql
\echo === section 4
SET statement_timeout = 0;
SET lock_timeout      = '60s';
-- First: P1c must return no row (a build can outlive the session that started it).
SELECT pid, phase, index_relid::regclass FROM pg_stat_progress_create_index
 WHERE relid = 'futures_markets'::regclass;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_external_id_trgm;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_llm_sport_category;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sport_id;
-- Last: this read MUST return 0 rows. The rollback is not done until it does.
SELECT c.relname, i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname IN ('ix_fm_t14_llm_sport_category', 'ix_fm_t14_sport_id', 'ix_fm_t14_external_id_trgm');
