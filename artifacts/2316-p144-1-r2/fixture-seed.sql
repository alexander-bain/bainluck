DROP TABLE IF EXISTS futures_markets;
CREATE TABLE futures_markets (
  id serial PRIMARY KEY,
  source varchar(50) NOT NULL,
  external_id varchar(200) NOT NULL,
  sport_id int,
  name varchar(300) NOT NULL,
  llm_sport_category varchar(50),
  market_tier int,
  status varchar(20),
  updated_at timestamptz NOT NULL,
  pad text
);
-- 12 sports, Kalshi roots in mixed case, Odds API keys, polymarket numeric ids.
WITH sp(i, prefix, cat, kx) AS (VALUES
 (0,'americanfootball_nfl','americanfootball','KXNFL'),
 (1,'americanfootball_ncaaf','americanfootball','KXNCAAF'),
 (2,'baseball_mlb','baseball','KXMLB'),
 (3,'basketball_nba','basketball','KXNBA'),
 (4,'basketball_wnba','basketball','KXWNBA'),
 (5,'icehockey_nhl','icehockey','KXNHL'),
 (6,'soccer_epl','soccer','KXSOCCER'),
 (7,'tennis_atp','tennis','KXATP'),
 (8,'mma_ufc','mma','KXUFC'),
 (9,'boxing_boxing','boxing','KXBOXING'),
 (10,'golf_pga','golf','KXPGA'),
 (11,'table_tennis_x','table_tennis','KXTT'))
INSERT INTO futures_markets (source, external_id, sport_id, name, llm_sport_category, market_tier, status, updated_at, pad)
SELECT
  src,
  CASE src WHEN 'kalshi' THEN (CASE WHEN g % 7 = 0 THEN lower(sp.kx) ELSE sp.kx END) || '-' || g
           WHEN 'odds_api' THEN sp.prefix || '_m' || g
           ELSE 'pm' || g END,
  CASE WHEN g % 3 = 0 THEN NULL ELSE sp.i + 1 END,
  'Market ' || g || CASE WHEN g % 11 = 0 THEN ' women' ELSE '' END,
  CASE WHEN g % 13 = 0 THEN 'other' WHEN g % 17 = 0 THEN NULL ELSE sp.cat END,
  CASE WHEN g % 25 = 0 THEN 1 + (g / 25) % 4 ELSE 5 END,
  (ARRAY['resolved','resolved','closed','open','resolved','closed',NULL,'settled'])[1 + (g % 8)],
  now() - ((g % 200) || ' days')::interval,
  repeat('x', 180)
FROM generate_series(1, 600000) g
CROSS JOIN LATERAL (SELECT (ARRAY['kalshi','kalshi','kalshi','odds_api','polymarket'])[1 + (g / 3) % 5] AS src) s
JOIN sp ON sp.i = ((g::bigint * 7919) % 12)::int
ORDER BY random();
CREATE UNIQUE INDEX uq_futures_source_external ON futures_markets (source, external_id);
CREATE INDEX ix_futures_markets_sport_id ON futures_markets (sport_id);
CREATE INDEX ix_futures_markets_status ON futures_markets (status);
-- production's psql-only partial category index (named in the 2026-08-30 P146 addendum)
CREATE INDEX ix_fm_open_category ON futures_markets (llm_sport_category) WHERE status = 'open';
VACUUM ANALYZE futures_markets;
