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
