# #2316 / P144-1: season-market discovery indexes. An attended runbook, for review

**PILLARS:** DISCOVER / FORMATTING.
**SHIP:** the first reader of a game's Bigger Picture gets the whole season context in about a
second, instead of waiting ~16 s while one cold scan reads the whole `futures_markets` table.

**Status: PROPOSAL FOR REVIEW. Not approved, not applied.** Independent review, Root's routing and
Alex's attended run are all still required. #10769's approval does not extend to this one.
Owner: latency (#2316). No app code changes. The packet is this runbook, the generator
`backend/scripts/season_discovery_admission_sql.py` and the guard
`backend/tests/test_season_discovery_index_packet_2316.py`.

**Index state: PROPOSED**

(The guard reads that line. `PROPOSED` and `ROLLED BACK` require that `models.py` does NOT declare
the three indexes; `KEPT` requires that it does. See §6, "After a final KEEP".)

Revision 2 (2026-10-17 18:40 PDT) answers lane1b's review of `5d5854e5c1` (R1–R10 + three nits).
The index set and the no-query-change design are unchanged. What changed: the gate (a size and plan
gate across four sports, under its own timeout, through a prepared statement), the safety argument
for CONCURRENTLY, the rollback's verification, the size ceiling, the write cost and the GIN
pending-list choice, and the final KEEP (now a cold-path acceptance after the build).

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
  max 61.4 s, 83k–115k disk blocks per call**. That is ≈0.21 ms per block read on the full-scan
  path, the figure the cold budget in §3 starts from.
* 2026-08-30 EXPLAIN, baseball finished: **Parallel Seq Scan, 126,177 blocks, 1,664 MB**, for
  400 rows out.

## 2. The proposal: three partial indexes, one per arm kind, on the tier-1–4 subset only

```sql
CREATE INDEX CONCURRENTLY ix_fm_t14_external_id_trgm
    ON futures_markets USING gin (external_id gin_trgm_ops)
    WITH (fastupdate = on, gin_pending_list_limit = 4096)
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
* **Why `fastupdate = on` with the pending list pinned at 4 MB (R10).** Every update to a tier-1–4
  row is already non-HOT: `updated_at` (`ix_fm_feed_open_enriched`) and `volume_24h`
  (`ix_fm_feed_open_volume`) are both indexed, so each such update also inserts into all three new
  indexes. Production Polymarket ids are 66-character hex condition ids (some with `_yes`/`_no`,
  `tasks/polymarket.py`), about 69 trigrams per row. On those ids the fixture measured (§5):
  `fastupdate = off` costs **1.0–2.3 ms per update** and rising (24,000 updates: 23 s, 39 s, 56 s);
  the default pending list costs **65–130 µs**, flush included; smaller lists cost more, not less
  (256 kB: 12–19 s per 24,000; 1 MB: 2–8 s). So the pending list stays on. Its read cost is
  bounded instead: every GIN search scans the whole pending list, at most 4 MB = 512 pages, and
  the cold budget in §3 reserves those 512 pages. The limit is set on the index, so it does not
  depend on the server's `gin_pending_list_limit`.
* **Plan cache premise (R4, corrected).** The app sends binds through asyncpg prepared statements.
  A generic plan can't prove a partial predicate, so it would seq-scan. `plan_cache_mode = auto`
  builds a custom plan for the first five executions and from the sixth keeps it only while it is
  cheaper than the generic one. Revision 1 said §3's check "confirms it again"; it could not,
  because a literal statement over psql's simple protocol is always custom-planned. The gate file
  now PREPAREs the statement with the same `$n` binds the asyncpg dialect sends (the sport ids
  inlined), plans it five times without running it, runs the sixth under EXPLAIN ANALYZE and
  prints `pg_prepared_statements.generic_plans`, which must read 0. That is production's plan
  cache logic on production's statement text, in Alex's session rather than the app's. The app's
  own sessions are checked by the cold-path acceptance in §6: a generic plan there would show as a
  full-scan mean.
* **Never in Alembic.** Gotcha #31 and ruling 131 apply. This is a hand-run psql step, like
  #10769.

## 3. The attended block (Alex, `heroku pg:psql -a bainluck`; agent sessions have no 5432 egress)

**A0. Generate the gate file on the day.** Run this from a checkout of the deployed commit:
`cd backend && python3 scripts/season_discovery_admission_sql.py --gate-set > /tmp/2316-gate.sql`.
It drives the real route four times (finished shape: americanfootball_ncaaf, baseball_mlb,
soccer_epl, basketball_other) and prints, per sport, the route's own sports lookup (`\gset`) and
the prepared discovery statement. Never hand-edit it. If a sports lookup comes back empty the
block prints `ABORT <sport>` and skips that sport instead of running a broken statement.

**A1. Preconditions. Each check below is a catalog read, not a table scan. ABORT on any row, or
on `abort = t`.**

```sql
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
```

* **P3's ceilings come from production-shaped ids (R9).** Revision 1's 220 B per row came from
  fixture ids averaging 15 characters. On 66-character hex ids the fixture's trigram index built
  at **216–238 B per tier-1–4 row**, and under churn it grew to **640–810 B per row** with a
  vacuum between every full rewrite, still rising about 19 B per row per rewrite (§5). Each btree
  took 21 B. P3 therefore estimates at the steady-state ceiling (1,000 + 2 × 40 B), assuming every
  tier-1–4 row has a hex id; the build-time sizes are checked again after A2.
* **P5's bound.** The fixture's worst case is ≈150 µs of index work per tier-1–4 write (hex ids,
  pending list on, btrees included). 300 writes/s × 150 µs ≈ 45 ms of CPU per second, under 5%
  of one core. If the statistics epoch predates the last restart, the average comes out high,
  which fails closed. Bursts (a poller rewriting thousands of rows at once) land in the pending
  list; the poller that overflows it pays the flush.
* One run at a time, never during another attended apply or fold.

**Why this is safe to start while a heavy job is running (R5).** P1 is a snapshot, not a guarantee.
CONCURRENTLY later waits, twice, for every transaction in the database that holds a snapshot.
Those waits are lock waits, so `lock_timeout = '60s'` applies to them: measured in the fixture,
a build waiting `virtualxid` on a 90-second reader was cancelled at 60.2 s with
`canceling statement due to lock timeout`, leaving the index `indisvalid = f, indisready = t`
(writes maintain it, the planner ignores it). So a transaction over 60 s that is open during a
build does not hang the build or block anyone: the build **fails closed**, and the expected
failure is an INVALID index, then a drop, then one retry. The discovery query itself runs up to
61.4 s today, so this failure is likely and is not a reason to stop. Locks: CONCURRENTLY takes
SHARE UPDATE EXCLUSIVE, so reads and writes continue. It conflicts only with VACUUM, ANALYZE and
other DDL on this table. Each build reads the table twice.

**A2. Build, one at a time. Read the catalog after each one.**

```sql
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
```

`IF NOT EXISTS` is left out deliberately. It would silently skip an INVALID leftover, which is
exactly the case that needs a person to look.

**If any CREATE errors, times out or is interrupted** (including the laptop session dropping):
1. Re-read P1c until it returns **no row**. A build can outlive the session that started it;
   never drop an index while its build is still running.
2. `DROP INDEX CONCURRENTLY <that name>;`
3. Re-read P2: that name must be gone. If it is still there, repeat step 2.
4. Re-run P1 and P1b, then retry that one CREATE **once**. If the retry fails, run the full §4
   rollback and stop. A second failure is an answer to keep, not something to retry.

**A3. The gate.** Still under the build session's settings, `ANALYZE futures_markets;`, then
`\i /tmp/2316-gate.sql` once. The file sets its own `statement_timeout = '30s'` before each
statement, so nothing in it inherits the build's 0. A timeout, an error or an `ABORT <sport>` line
is a FAIL.

The gate is a **plan and size gate with a cache-independent bound (R1)**. It runs straight after
three builds that each read the whole heap twice, and an ANALYZE, so its times are warm times:
they can rule a KEEP out but never in. The heap-block ceiling is the bound that does not depend
on the cache. Cold budget 2,000 ms = 3,000 heap blocks × 0.5 ms per random heap read (1,500 ms;
the full-scan path on file reads ≈0.21 ms per block, and a bitmap heap read is sparse, so ×2.5)
\+ a full pending list, 512 pages × 0.5 ms (256 ms) + index pages. That compares a count with a
budget inside one node type, so gotcha #123 (block counts across node types) does not apply.

**Provisional KEEP only if every line below holds, for each of the four statements.** The
generator prints the same table at the top of every block, and the guard test holds the two equal.

```text gate-criteria
statement_timeout = 30s
every_index_valid = yes
seq_scan_on_futures_markets = none
bitmapor_lists_all_three_indexes = yes
lossy_heap_blocks = 0
max_exact_heap_blocks = 3000
max_execution_ms = 2000
generic_plans_after_sixth = 0
max_trgm_bytes_per_t14_row_at_build = 330
max_btree_bytes_per_t14_row_at_build = 40
```

Where to read each one: `every_index_valid` and both size lines are A2's read (`indisvalid = t`,
`within = t` on all three rows). `seq_scan_on_futures_markets`: no `Seq Scan on futures_markets`
in any plan. `bitmapor_lists_all_three_indexes`: the `BitmapOr` names all three `ix_fm_t14_*`
indexes. `lossy_heap_blocks` and `max_exact_heap_blocks`: the Bitmap Heap Scan's
`Heap Blocks: exact=N` line (PostgreSQL prints `lossy=` only when it is non-zero, so any `lossy=`
fails). `max_execution_ms`: `Execution Time`. `generic_plans_after_sixth`: the
`pg_prepared_statements` row after each plan (`generic_plans = 0`, `custom_plans = 6`). Also copy
into the receipt, without judging them: `Buffers: shared hit/read` and, if the file's
`SHOW track_io_timing` printed `on`, the `I/O Timings` line.

If any line fails, run §4. A failed gate is an answer to keep, not something to retry. A pass is a
**provisional** KEEP. The final KEEP is the cold-path acceptance in §6.

## 4. Rollback. Drop, then prove the drop. No code and no deploy

```sql
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
```

`IF EXISTS` keeps a partial rollback (only one index ever built) from erroring, but it also
succeeds silently on a misspelt name. That is why the rollback ends with the catalog read, and why
the guard test holds the DROP set, every catalog-read name list and the CREATE set equal (R6).
DROP INDEX CONCURRENTLY waits for snapshots just as CREATE does, so `lock_timeout` can cancel it
too. **Unlike a build retry, a rollback retry is required:** re-run the DROP for every name the
final read still returns, and read again, until it returns 0 rows.

No query text changes in either direction, so results are identical with any subset of the
three present. Only speed depends on having all three.

## 5. Disposable fixture evidence: mechanics only, not production cost

Local PostgreSQL 14.23, en_US.UTF-8 / UTF8. Synthetic 600,000-row `futures_markets`, 172 MB:
12 sports, mixed-case Kalshi tickers, 4% tiers 1–4, the existing indexes plus a stand-in
`ix_fm_open_category`. Statements were built from the route's own predicate code and run as SQL
prepared statements with binds.

| shape | before | after (three indexes) | ids |
|---|---|---|---|
| americanfootball_ncaaf finished | Seq Scan, 22,038 blocks | BitmapOr ×3 indexes, 3,793 | identical (400) |
| americanfootball_nfl finished | Seq Scan, 22,038 | 3,786 | identical (400) |
| baseball_mlb finished | Seq Scan, 22,038 | 2,062 | identical (400) |
| tennis_atp finished | Seq Scan, 22,038 | 3,758 | identical (400) |
| golf_pga finished | Seq Scan, 22,038 | 1,910 | identical (400) |
| the same five, live shape | status bitmap, 22,154 each | 206–1,250 | identical |

Negative control, P144-1 as filed (external_id indexes only): baseball still Seq Scan, college
football a 14,791-block sweep of the tier subset. The interrupted-build trap was also reproduced:
a CONCURRENTLY build cancelled by statement_timeout left the index `indisvalid = f`; re-running it
with `IF NOT EXISTS` printed `CREATE INDEX` and left it invalid; only `DROP INDEX CONCURRENTLY`
cleared it.

Revision 2 adds (receipts: `artifacts/2316-p144-1-r2/` in the latency worktree):

* **The revision-2 runbook itself, run end to end** with `ON_ERROR_STOP`: §4 to clear, A1, A2,
  the generated four-sport gate file, §4 again, final read 0 rows (`flow.txt`). Results are in the
  fixture row of the table below.
* **Plan cache (R4).** Before any index existed, each of the four gate blocks printed
  `generic_plans = 0, custom_plans = 6`: the five plan-only `EXPLAIN EXECUTE`s count toward the
  plan cache's switch decision, so the sixth run is the one that could switch.
* **lock_timeout during a build (R5).** A REPEATABLE READ reader held its snapshot for 90 s. The
  build reached `waiting for old snapshots`, waited on `virtualxid`, and was cancelled at
  **60,233 ms** with `canceling statement due to lock timeout`, leaving `indisvalid = f, indisready
  = t`. Afterwards `pg_stat_progress_create_index` was empty (`r5-lock-timeout.txt`).
* **Size on production-shaped ids (R9).** 24,000 rows with `0x` + 64 hex (+ `_yes`/`_no` on two
  thirds), 68.9 trigrams per id against the fixture's 15.8: trigram index **216 B per row** at bulk
  build (fixture ids: 39 B), 175 B when filled one insert at a time. Under churn, vacuumed between
  rewrites: 5.7 MB → 15.3 MB after the first full rewrite, then +0.45 MB per rewrite, 19.4 MB after
  ten (640–810 B per row). Btrees: 21 B per row (`r9-size.txt`, `r9-plateau.txt`).
* **Write cost (R10).** 24,000 non-HOT updates of hex-id rows, three rounds each:
  no trigram index 0.26–0.38 s; `fastupdate = on`, 4 MB list 1.6 / 2.2 / 3.1 s; 1 MB 2.3 / 8.2 /
  7.6 s; 256 kB 12.3 / 18.6 / 18.7 s; `fastupdate = off` 23.2 / 38.9 / 55.9 s (`r10-*.txt`).

**These blocks are fixture blocks.** Production's cost depends on how many heap pages hold tier-1–4
rows of one sport across all history, and nothing on file measures that. §3 A3 answers it inside
the attended step as a provisional gate, and §6 answers it for real readers.

| still unpaid in production | answered by |
|---|---|
| tier-1–4 row count and size | P3 (estimate), A2's size read (actual) |
| heap spread of one sport's tier-1–4 rows | A3 `Heap Blocks: exact` |
| the plan, and custom plans on psql's prepared path | A3 |
| custom plans on the asyncpg path, and cold time | §6 acceptance |
| write rate | P5 (premise), §6 steady-state size |
| CONCURRENTLY under heavy-app transactions | fails closed (§3, measured), A2 retry |
| the rollback succeeding | §4's final read |

## 6. What this buys, the final KEEP, and what follows it

If A3 passes, a cold finished-shape discovery drops from a full scan to a read of one sport's
season markets. That covers the first reader of each sport every 300 s, and every reader while
Redis is down. The live shape should improve too, but that isn't claimed here.
Not covered: P144-3 (the series pass matches team names), P146-1 (tennis concept), #10769 (search)
and every other parked index. Each keeps its own state and approvals.

**The final KEEP is a cold-path acceptance, defined now, before any build (R1).** It is latency's
post-build measurement, not part of the attended block, and nothing in it writes. It reads only
existing statistics through `/api/admin/db-query`:

```text acceptance-criteria
window_starts_hours_after_build = 6
window_hours = 24
window_may_extend_to_hours = 72
min_finished_shape_calls = 10
max_mean_exec_ms = 2000
max_trgm_bytes_per_t14_row_steady = 1000
on_failure = section 4 rollback
```

* **Mean.** Read `calls` and `total_exec_time` from `pg_stat_statements` for every finished-shape
  discovery fingerprint (query text starting `SELECT futures_markets.id, futures_markets.market_tier`
  and containing `updated_at >=`) at the window's start and end. The mean over the window is
  Δ`total_exec_time` / Δ`calls`, summed over those fingerprints, against the 19.2–23.7 s means on
  file. It mixes cold and warm calls exactly as readers get them. A generic plan on the app's
  connections would show here as a full-scan mean.
* **Too few calls**, or a fingerprint evicted between the two reads (`pg_stat_statements` sits
  near its cap): extend the window, up to 72 h. Still short: the result is UNMEASURED and the
  indexes stay on a provisional KEEP, reported as exactly that, never as a KEEP.
* **Steady-state size:** at the window's end, `pg_relation_size('ix_fm_t14_external_id_trgm')`
  ≤ 1,000 B × the P3 estimate of tier-1–4 rows.
* **On failure** (mean or size over its bound): latency asks Root to put the §4 rollback on
  YOUR-TURN with its exact steps. Alex runs it. #2316 records the failed acceptance as the result.
* **The reader check** stays latency's as well: one served uncached finished-shape read
  (`/api/events/{id}/related-futures?debug=1` runs the build uncached), its `x-timing-split` maxq
  compared against 13,022 ms. #2316 stays open until both are in.

**After a final KEEP (R8). Owner: latency, under #2316, before #2316 closes.** Declare the three
indexes in `FuturesMarket.__table_args__` in `backend/app/models/models.py`, as
`ix_fm_kalshi_resdate_id` already is: `postgresql_using="gin"` and
`postgresql_ops={"external_id": "gin_trgm_ops"}` with `postgresql_with={"fastupdate": "on",
"gin_pending_list_limit": 4096}` for the trigram one, and `postgresql_where` plus a matching
`sqlite_where` on all three. Then flip **Index state** at the top of this file to `KEPT`.
`alembic/env.py` has no `include_object` filter, so without the declaration the next
`--autogenerate` revision drops all three in a release, non-concurrently, and the speedup
silently reverts. Declaring them **before** the KEEP is just as wrong: autogenerate would emit a
non-concurrent CREATE in a release (gotcha #31). The guard test enforces both directions from
the Index state line. After a rollback the line reads `ROLLED BACK`.
