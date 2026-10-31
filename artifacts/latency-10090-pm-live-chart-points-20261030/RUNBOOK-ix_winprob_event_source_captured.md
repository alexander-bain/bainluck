# Attended index runbook: `win_prob_snapshots (event_id, source, captured_at)` (#10090)

**State: PREPARED, NOT RUN.** Prepared by latency on Fri 10/30 at 2:10 PM PT (21:10Z). Speed asks Alex to approve this exact operation. Nobody runs it before he does.

**Why.** Each live chart point does a "previous row" lookup in `_create_ordered_win_prob_snapshot` (`app/tasks/snapshots.py`): `… WHERE event_id = $1 AND source = $2 AND captured_at <= $3 ORDER BY captured_at DESC LIMIT 1 FOR UPDATE`.
- The only index that leads with the event is `ix_winprob_event_source (event_id, source)`, so every lookup reads the event's whole series from the heap and sorts it.
- Production 2026-10-30 21:03:56–21:04:18Z (`pg_stat_statements` delta): 94 calls, **237 ms each, 226 ms of it disk reads** (167 blocks per call). Every other statement in the point's transaction took under 1 ms.
- The Polymarket chart writer pays about 3.2 points a second, which is about what the stamps owe. So `owed_chart_points` holds about 17,100 Polymarket rows, and live points land on the chart about 95 minutes after their stamps.
- With this index the lookup reads one index entry: `Index Scan Backward using ix_winprob_event_source_captured`, 1 row. The same index also serves the 2-minute poll's newest-row read (14.3M calls, 13.9 ms mean since 8/31).

## 0. Who and where
- **Who:** Alex, in his normal Terminal. The sandbox blocks TCP 5432, so `pg:psql` cannot run from a lane.
- **Command:** `heroku pg:psql -a bainluck`. This is the main app's database, which both apps share.
- **When:**
  - not while a both-app exclusion/hold is active (DNPL notices), and not during an attended fold/apply;
  - preferably not between :15 and :40 UTC, while the accuracy rebuild runs (it holds long transactions that the build would wait behind);
  - not 09:00–10:15 UTC (2:00–3:15 AM PT), while the nightly backup runs (20–65 minutes each night this week, one transaction throughout).
  - Live games are fine: the build's lock does not block INSERT, UPDATE or DELETE. It does read the 4 GB table twice, so prefer a quieter hour when there is a choice.
- **How:** paste one section at a time and read its output before pasting the next. `ON_ERROR_STOP` does not stop lines that were already pasted.

## 1. Pre-checks (same psql session)
```sql
\set ON_ERROR_STOP on
\timing on
-- (a) every index on the table. Expect exactly win_prob_snapshots_pkey,
--     ix_winprob_captured and ix_winprob_event_source, all indisvalid = t.
--     STOP if any row shows indisvalid = f, or if ix_winprob_event_source_captured
--     already appears.
SELECT c.relname, i.indisvalid, i.indisready,
       pg_size_pretty(pg_relation_size(c.oid)) AS size, pg_get_indexdef(c.oid) AS def
  FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
 WHERE i.indrelid = 'public.win_prob_snapshots'::regclass
 ORDER BY 1;
-- (b) long transactions the build would wait behind. Expect 0 rows (autovacuum
--     workers are fine and are not listed). If there are rows, do not kill
--     anything: rerun (b) once a minute and go to section 2 within a minute of
--     it showing 0 rows. Still rows after 15 minutes: stop and pick another window.
SELECT pid, application_name, now() - xact_start AS xact_age, state, left(query, 80) AS query
  FROM pg_stat_activity
 WHERE datname = current_database() AND xact_start < now() - interval '2 minutes'
   AND backend_type = 'client backend'
 ORDER BY xact_start;
-- (c) nothing else building an index right now. Expect 0 rows.
SELECT pid, relid::regclass, phase, blocks_done, blocks_total FROM pg_stat_progress_create_index;
```
If (a) shows an INVALID leftover named `ix_winprob_event_source_captured`, run the rollback in section 4 first, then start again from (a).

## 2. The operation
```sql
SET lock_timeout = '10min';
SET statement_timeout = '30min';
CREATE INDEX CONCURRENTLY ix_winprob_event_source_captured ON public.win_prob_snapshots USING btree (event_id, source, captured_at);
```
- **No `IF NOT EXISTS`, on purpose.** After an interrupted build, an `IF NOT EXISTS` re-run prints `CREATE INDEX` and leaves the INVALID index in place. Pre-check (a) is the existence test.
- **Run it outside a transaction block.** psql autocommits by default. Do not start psql with `-1`/`--single-transaction`, and do not type `BEGIN`.
- **Why these timeouts.**
  - The build takes SHARE UPDATE EXCLUSIVE. That lock does not conflict with the chart INSERTs/UPDATEs or the `FOR UPDATE` lookups, so neither a wait nor the build holds up a stamp or a chart point. (An ordinary autovacuum on this table is cancelled in its favour; an anti-wraparound one is not, and pre-check (c) does not see it — the build then waits up to the lock timeout and stops cleanly.)
  - `lock_timeout = 10min` bounds each individual wait. CONCURRENTLY waits behind older transactions one holder at a time, with a fresh clock for each. Its last wait is for every transaction in the whole database that began before its second pass, not only users of this table. Reads of 44–496 seconds are routine here (`a11.out.json`; 20:10Z), so a short timeout would throw away a finished build. Waiting is harmless: in a local PG17 rehearsal an INSERT took 2.6 ms and the `FOR UPDATE` lookup 8 ms while the build sat in `waiting for old snapshots`.
  - `statement_timeout = 30min` is the absolute cap: up to ~10 minutes of waiting plus the build.
  - Any stop after the build has begun, a timed-out wait included, leaves an INVALID index with this name. Rehearsed locally: a stop in the first wait leaves an empty one; a stop in the last wait leaves a full one (~500 MB here) that every chart INSERT keeps updating until it is dropped. Only a stop while taking the table lock at the very start leaves nothing. Post-check 1 catches it; run section 4 in the same sitting.
- **Optional progress view** from a second psql window: `SELECT phase, blocks_done, blocks_total FROM pg_stat_progress_create_index;`

## 3. Expected cost, and post-checks
- **Expected build time: about 1–5 minutes.** This is an estimate from a local rig, not a production build.
  - Local PG14 (laptop SSD): a 508 MB heap of 1.3M rows in the production column shape built in 2.27 s.
  - Production: 3,968 MB heap, about 12.9M rows (PG17), read twice under live load.
  - Wall time can also stretch by the length of any transaction open at its start or at its last wait, up to the 10-minute lock timeout each; pre-check (b) keeps the first one short.
- **Expected disk: about 500 MB** (the rig measured 50 MB for 1.3M rows), plus about as much sort scratch while it runs. The plan is Standard 3: 108 GB of 512 GB used, so even ten times the estimate fits.
- **Post-check 1, in the same psql session:** rerun pre-check (a). It must show `ix_winprob_event_source_captured | t | t | ~500 MB | CREATE INDEX ix_winprob_event_source_captured ON public.win_prob_snapshots USING btree (event_id, source, captured_at)`. Anything other than `indisvalid = t` and `indisready = t` means go to section 4 now.
- **Post-check 2, a lane does this via db-query plan-only `explain`:** the plain-SELECT mirror of the lookup (`SELECT id FROM win_prob_snapshots WHERE event_id = <a live event> AND source = 'polymarket' AND captured_at <= now() ORDER BY captured_at DESC LIMIT 1`) must show `Index Scan Backward using ix_winprob_event_source_captured`. Today it shows `Sort` over `Index Scan using ix_winprob_event_source` (`ex1.out.json` in this folder).
- **Post-check 3, the effect, owned by speed (light reads, about 30 minutes after post-check 1):**
  - the Polymarket `owed_chart_points` count falls from about 17,100 toward Kalshi's tens (`a3.sql`);
  - the previous-row lookup's per-call time falls from about 237 ms (`a16.sql`, two reads about 20 s apart);
  - live Polymarket `ws_fast_lane` rows appear in a last-30-minutes read (`q12.sql` in `artifacts/discover-10090-item5-poll-vs-socket-20261030/`), where today there are 0.
  - No `ANALYZE` is needed: the index is on plain columns.

## 4. Rollback (also how an INVALID leftover is cleared)
```sql
SET lock_timeout = '10min';
SET statement_timeout = '30min';
DROP INDEX CONCURRENTLY IF EXISTS public.ix_winprob_event_source_captured;
-- then rerun pre-check (a): the name must be ABSENT.
```
- If the DROP prints `canceling statement due to lock timeout`, nothing is harmed: run the same three lines again. It waits for every transaction that has this table open, and writes are not blocked while it waits. Rehearsed locally: a rerun after the reader ended completed.
- After a rollback, behaviour is exactly today's: the chart writer stays behind.
- The rollback writes no data.

## 5. Recording it so `alembic --autogenerate` never proposes dropping it
- **Older drift, unchanged by this:** autogenerate already proposes four index changes on this table, because the model's `index=True` columns do not match the migration's `ix_winprob_event_source` / `ix_winprob_captured`. Any autogenerated revision must still have those lines removed by hand. Checked locally: master proposes those four plus dropping the new index; with the declaration, only those four.
- **The declaration** is in `WinProbSnapshot.__table_args__` on the draft PR (latency branch `latency/10090-winprob-chart-lookup-index`). It must merge **after** post-check 1 passes, not before. Declared before the build, an autogenerated revision could emit a non-concurrent `CREATE INDEX` into a release, which is gotcha #31.
- **No Alembic migration.** On a database without the index it would build non-concurrently inside the release phase, holding a lock against every chart INSERT for the whole build. On production it would no-op over an INVALID leftover and report success.
- **The guard** is `backend/tests/test_winprob_chart_lookup_index_registration_10090.py`. It pins the declared definition, the compiled DDL (this section 2 minus CONCURRENTLY), and that no migration executes the name.
- **Not migration-class** (notice 47(c)). No DDL runs on merge or release; this attended psql step is the only build. If the index is ever rolled back, the declaration comes out in the same session.

## Not claimed
- The production build time and size. Both come from the local rig and the heap ratio.
- That the backlog clears at a particular rate. The lookup is ~226 of the ~310 ms each Polymarket point costs today. The rest (session slot, round trips through a busy event loop) is inferred from the total and is not measured per stage. If the writer still trails after the build, the next lever is several points per transaction in `_drain_history`.
- Anything about `ix_winprob_event_source`, which becomes a prefix of the new index. Dropping it is a separate decision, and nothing here depends on it.
