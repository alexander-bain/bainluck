# #2316 / P144-1: season-market discovery indexes. An attended runbook, for review

**PILLARS:** DISCOVER / FORMATTING.
**SHIP:** the first reader of a game's Bigger Picture gets the whole season context in about a
second, instead of waiting ~16 s while one cold scan reads the whole `futures_markets` table.

**Status: PROPOSAL FOR REVIEW. Not approved, not applied.** Independent review, Root's routing and
Alex's attended run are all still required. #10769's approval does not extend to this one.
Owner: latency (#2316). No app code changes. The packet is this runbook, the generator
`backend/scripts/season_discovery_admission_sql.py` and the guard
`backend/tests/test_season_discovery_index_packet_2316.py`.

---

## 0. Reconciling P144-1 as it was filed. It cannot shorten the scan on its own

P144-1 (2026-08-30, the addendum in `.claude/handoff/MIGRATION-SLOT-REQUEST-LATENCY-2026-08-29.md`)
named one index, "a prefix-searchable index on `futures_markets.external_id`". That index alone
leaves the finished-shape statement on a full scan. The planner can replace a scan with an
index only when **every** arm of the sport OR is index-served. The route's OR
(`routes/events.py`, `_build_related_futures`, "3. Find sport-matching open markets") has four kinds
of arm:

| arm | example (americanfootball_ncaaf) | served today? |
|---|---|---|
| `external_id LIKE '<sport key>%'` | `'americanfootball_ncaaf%'` | no. en_US collation defeats a btree prefix (measured 2026-08-30) |
| `external_id ILIKE '<Kalshi root>%'` | `'KXNFL%'`, `'KXNCAAF%'` | no. A `text_pattern_ops` btree cannot serve ILIKE at all |
| `llm_sport_category = '<category>'` | `'football'` | **open rows only.** `ix_fm_open_category` is partial on `status = 'open'` (P146 addendum), and the finished shape also reads resolved/closed/NULL |
| `sport_id IN (...)` | the sport's ids | yes, `ix_futures_markets_sport_id`. But the bitmap would carry every tier-5 prop of the sport |

So the filed index can't serve the ILIKE arms, and nothing serves the category arm for the
finished shape. In the disposable fixture (§5), P144-1 alone gives baseball a plain Seq Scan.
For college football it gives a GIN full-index sweep of the whole tier-1–4 subset (14,791 heap
blocks of 22,038). That's still a near-full read.

The other levers were already measured and ruled out (REPORT-LAT-P144 §3, P144 audit §3), and
this packet keeps both rulings:
* **A lexical range rewrite** (`>= 'KXMLB' AND < 'KXMLB~'`) is 470× cheaper and returns
  **0 rows where LIKE returns 34,463**. Rejected.
* **Dropping the "rare" arms** removes real markets: KX arm 17 americanfootball and 1 basketball,
  `sport_id` arm 46 tennis. Rejected.

This packet changes no query text. An index can't change what a query returns, so the four-arm
predicate, the 12-sport correctness and the empty-answer accounting (`season_market_discovery`
caches `[]` for 60 s) all stay exactly as they are.

## 1. The defect, from evidence already on file (no new production reads were taken for this packet)

* 2026-10-17 20:40Z, main v5768, a normal first read of a finished college game (Maryland v
  Rutgers 15328226): **16,073 ms wall, one statement 13,022 ms**, and that statement is this
  discovery query (#2316 comment, 2026-10-17 17:31Z). Since PR #11197, readers who arrive at the
  same time wait for that one scan (13.4–13.9 s app time each) instead of running copies of it.
* `pg_stat_statements` (same comment): the two finished-shape fingerprints average **19.2 s and 23.7 s,
  max 61.4 s, 83k–115k disk blocks per call**.
* 2026-08-30 EXPLAIN, baseball finished: **Parallel Seq Scan, 126,177 blocks, 1,664 MB**, for
  400 rows out.

## 2. The proposal: three partial indexes, one per arm kind, on the tier-1–4 subset only

```sql
CREATE INDEX CONCURRENTLY ix_fm_t14_external_id_trgm
    ON futures_markets USING gin (external_id gin_trgm_ops)
    WHERE market_tier IN (1, 2, 3, 4);
CREATE INDEX CONCURRENTLY ix_fm_t14_llm_sport_category
    ON futures_markets (llm_sport_category)
    WHERE market_tier IN (1, 2, 3, 4);
CREATE INDEX CONCURRENTLY ix_fm_t14_sport_id
    ON futures_markets (sport_id)
    WHERE market_tier IN (1, 2, 3, 4);
```

* **Why trigram, not `text_pattern_ops`:** one `gin_trgm_ops` index serves both LIKE and ILIKE
  prefixes without changing the route. Trigram matches are always rechecked against the heap,
  so the en_US collation can't change a result. `pg_trgm` is already installed in production
  (`ix_futures_name_trgm`).
* **Why partial on `market_tier IN (1, 2, 3, 4)`:** the statement ANDs exactly that clause, so the
  planner can prove each index covers it. Each bitmap then holds only season markets, not the
  sport's tier-5 game props. That keeps the indexes small and the write cost limited to tier-1–4
  rows. The guard test fails if the route's tier list or arm kinds stop matching these
  definitions.
* **Plan cache premise:** the app sends binds through asyncpg prepared statements. A generic plan
  can't prove a partial predicate, so it would seq-scan. `plan_cache_mode = auto` keeps the
  custom plan whenever it costs less than the generic one, which it does here: in the fixture,
  seven executions later the custom plan was still in use. The same premise already holds in
  production for the four `status = 'open'` partials (hundreds of thousands of planner-chosen
  scans, lat-p088 spec §2a). §3's check confirms it again.
* **Never in Alembic.** Gotcha #31 and ruling 131 apply. This is a hand-run psql step, like
  #10769.

## 3. The attended block (Alex, `heroku pg:psql -a bainluck`; agent sessions have no 5432 egress)

**A0. Generate the exact statement on the day.** Run this from a checkout of the deployed commit:
`cd backend && python3 scripts/season_discovery_admission_sql.py --sport-key americanfootball_ncaaf --finished > /tmp/2316-gate.sql`.
It drives the real route and prints the route's own sports lookup (`\gset`) plus the discovery
statement. Never hand-edit it.

**A1. Preconditions. Each check below is a catalog read, not a table scan. ABORT on any row or failed bound.**

```sql
SET statement_timeout    = 0;        -- CONCURRENTLY must not be cut off mid-build
SET lock_timeout         = '60s';    -- '5s' fails in this database (LAT-P058)
SET maintenance_work_mem = '256MB';
-- P1: nothing older than 60 s; CONCURRENTLY waits out every older transaction (twice).
SELECT pid, now() - xact_start AS age, state, left(query, 80)
  FROM pg_stat_activity
 WHERE xact_start IS NOT NULL AND now() - xact_start > interval '60 seconds'
   AND pid <> pg_backend_pid();
-- P2: no leftover (possibly INVALID) index holding one of the three names.
SELECT c.relname, i.indisvalid, i.indisready FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname IN ('ix_fm_t14_external_id_trgm','ix_fm_t14_llm_sport_category','ix_fm_t14_sport_id');
-- P3: size estimate. ABORT if est_t14_rows * 220 bytes > 400 MB.
SELECT c.reltuples::bigint AS rows,
       (SELECT sum(f) FROM pg_stats s, unnest(s.most_common_vals::text::int[], s.most_common_freqs) AS u(v, f)
         WHERE s.tablename = 'futures_markets' AND s.attname = 'market_tier' AND u.v BETWEEN 1 AND 4) AS t14_frac
  FROM pg_class c WHERE c.oid = 'futures_markets'::regclass;
-- P4: the trigram opclass exists.
SELECT extversion FROM pg_extension WHERE extname = 'pg_trgm';
```

The 220 bytes per row is a ceiling. In the fixture the trigram index took 70 B per tier-1–4 row
and each btree under 8 B, with shorter ids than production's. One run at a time, never during
another attended apply or fold. The 60-second transaction check is what makes the build safe to
start while a heavy job is running.

**A2. Build, one at a time. Read the catalog after each one.**

```sql
CREATE INDEX CONCURRENTLY ix_fm_t14_llm_sport_category ON futures_markets (llm_sport_category) WHERE market_tier IN (1, 2, 3, 4);
CREATE INDEX CONCURRENTLY ix_fm_t14_sport_id ON futures_markets (sport_id) WHERE market_tier IN (1, 2, 3, 4);
CREATE INDEX CONCURRENTLY ix_fm_t14_external_id_trgm ON futures_markets USING gin (external_id gin_trgm_ops) WHERE market_tier IN (1, 2, 3, 4);
SELECT c.relname, i.indisvalid, i.indisready, pg_size_pretty(pg_relation_size(c.oid))
  FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid WHERE c.relname LIKE 'ix_fm_t14_%';
```

`IF NOT EXISTS` is left out deliberately. It would silently skip an INVALID leftover, which is
exactly the case that needs a person to look.
**If any CREATE errors, times out or is interrupted**, the index stays INVALID: the planner won't
use it, but writes still maintain it. Run `DROP INDEX CONCURRENTLY <that name>;`, re-run P1, and
retry once. If the second try fails, run the full §4 rollback and stop.
Locks: CONCURRENTLY takes SHARE UPDATE EXCLUSIVE, so reads and writes continue. It conflicts only
with VACUUM, ANALYZE and other DDL on this table. Each build reads the table twice.

**A3. The gate. `ANALYZE futures_markets;` then `\i /tmp/2316-gate.sql` once. KEEP only if all three hold:**
1. All three indexes read `indisvalid = t`.
2. The plan has **no `Seq Scan on futures_markets`**, and a `BitmapOr` lists all three
   `ix_fm_t14_*` indexes.
3. That first run's `Execution Time` ≤ **2,000 ms**. The baseline is 13,022 ms served and
   19.2–23.7 s mean in pg_stat_statements. Time is the judge here, not blocks: block counts
   aren't comparable across node types (gotcha #123, #1731's negative result).

If any of them fails, run §4. A failed gate is an answer to keep, not something to retry.

## 4. Rollback. Three statements, no code and no deploy

```sql
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_external_id_trgm;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_llm_sport_category;
DROP INDEX CONCURRENTLY IF EXISTS ix_fm_t14_sport_id;
```

No query text changes in either direction, so results are identical with any subset of the
three present. Only speed depends on having all three.

## 5. Disposable fixture evidence: mechanics only, not production cost

Local PostgreSQL 14.23, en_US.UTF-8 / UTF8. Synthetic 600,000-row `futures_markets`, 172 MB:
12 sports, mixed-case Kalshi tickers, 4% tiers 1–4, the existing indexes plus a stand-in
`ix_fm_open_category`. Statements were built from the route's own predicate code and run as SQL
prepared statements with binds, seven executions each.

| shape | before | after (three indexes) | ids |
|---|---|---|---|
| americanfootball_ncaaf finished | Seq Scan, 22,038 blocks | BitmapOr ×3 indexes, 3,793 | identical (400) |
| americanfootball_nfl finished | Seq Scan, 22,038 | 3,786 | identical (400) |
| baseball_mlb finished | Seq Scan, 22,038 | 2,062 | identical (400) |
| tennis_atp finished | Seq Scan, 22,038 | 3,758 | identical (400) |
| golf_pga finished | Seq Scan, 22,038 | 1,910 | identical (400) |
| the same five, live shape | status bitmap, 22,154 each | 206–1,250 | identical |

Negative control, P144-1 as filed (external_id indexes only): baseball still Seq Scan, college
football a 14,791-block sweep of the tier subset. The generator's psql block also ran against the
fixture with `ON_ERROR_STOP` (exit 0), and it planned the BitmapOr over all three indexes.
The interrupted-build trap was also reproduced. A CONCURRENTLY build cancelled by
statement_timeout left the index `indisvalid = f`. Re-running it with `IF NOT EXISTS` printed
`CREATE INDEX` and left it invalid, and only `DROP INDEX CONCURRENTLY` cleared it.

**These blocks are fixture blocks.** Production's cost depends on how many heap pages hold tier-1–4
rows of one sport across all history, and nothing on file measures that. §3 A3 is where
production answers it, inside the attended step, as its own gate.

## 6. What this buys, and what it doesn't

If A3 passes, a cold finished-shape discovery drops from a full scan to a read of one sport's
season markets. That covers the first reader of each sport every 300 s, and every reader while
Redis is down. The live shape should improve too, but that isn't claimed here.
Not covered: P144-3 (the series pass matches team names), P146-1 (tennis concept), #10769 (search)
and every other parked index. Each keeps its own state and approvals.
**Reader acceptance is latency's, after the build:** one served uncached finished-shape read
(`/api/events/{id}/related-futures?debug=1` runs the build uncached) with `x-timing-split` maxq
compared against 13,022 ms. #2316 stays open until then.
