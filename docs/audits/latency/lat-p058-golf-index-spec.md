# LAT-P058 — the golf identity index: a runbook addressed to the INTEGRATOR

**Status:** ⚠️ **EXECUTED 2026-08-15 by INT-072's predecessor cycle (INT-071). 2 of 3 built. This document has been CORRECTED from that run — see the execution record immediately below before running anything here.**

> ## 🔴 READ BEFORE ANY OTHER LINE OF THIS DOCUMENT — the flip half is DEAD (#1917, ruling 076)
>
> This runbook has two halves: **a DDL half and a flag half.** The DDL half **succeeded and is the
> whole win** — planner cost 128,191.5 → 12,243.92, per-call physical reads 516.7 → 2.395 MB (~216×,
> 427.6 → 3.2 GB/day), warm runtime ~2,900 ms → ≈18 ms, all of it with the flag off.
>
> **The flag half is withdrawn permanently.** The `UNION` rewrite was measured **4.79× SLOWER** than
> the `OR` it was meant to replace (≈88.2 ms vs ≈18.4 ms warm median, **2.45× shared buffers**) while
> the planner ranked it 2.81× *cheaper* — an inversion of 13.5×. `GOLF_IDENTITY_SPLIT_SCAN`, the
> `split=` parameter, the `UNION` branch and its tests are **deleted from the codebase**;
> `golf_identity_select()` takes no arguments.
>
> **§5.3 (the gate) and §6 (the flip) are struck.** §5.3 *passed* on the regression and would
> re-authorise it; it is replaced in place by §5.3′, ruling 076's four-step form, which is the
> procedure for any future rewrite gate. §7's "plan only" rollback row and §5.4's `UNION`-queryid
> note are struck for the same reason. Everything about the **indexes** below stands and is live.
>
> Sections marked "CORRECTION" in §0/§0b are **dated historical record** of how this was found, not
> instructions. Do not action them.

---

## 0. EXECUTION RECORD — 2026-08-15, INT-071 (read this first)

### 🔴 `SET lock_timeout = '5s'` was WRONG and it fails silently-expensively

The first run of §3 exactly as written left **all three indexes INVALID** (`indisvalid=false, indisready=true`) and the dyno exited. The *sizes* are the diagnosis, and they are the reason this is not ambiguous:

| index | size after the failed run | expected final size |
|---|---|---|
| `ix_fm_golf_identity_category` | **1088 kB** | ~1 MB ✔ full |
| `ix_fm_source_created_at` | **6072 kB** | its true full size (see below) ✔ full |

Both had reached their **full final size**. The builds *completed* and then died in `CONCURRENTLY`'s **second wait phase** — the one this document's own §4 warns "waits — twice — for every transaction that can see the table". Re-run byte-identically but with `lock_timeout = '60s'`, the same statement reached `indisvalid=true` in under a minute.

`futures_markets` is swept by the prediction-market matcher every 15 minutes with 13–21 s scans. **5 s is not a plausible wait budget on this table**, and the failure mode is the worst-shaped one: an INVALID index is never *read* but IS *maintained on every write*, so a "failed" run leaves a permanent write tax behind and reports nothing.

**Both invocations in §3 have been changed to `60s`.**

### The size estimate for (3) was ~5× high

Spec predicted ~25–35 MB for `ix_fm_source_created_at`. **Actual: 6,088 kB.** Anyone using the old figure to judge "is it still building?" will conclude a finished index is 20% done — which is exactly the wrong inference INT-071 drew for several minutes.

### §3's invocation prints to stdout, which is UNREACHABLE from an agent session

Gotcha #125(a): `heroku logs` dies on an EPERM rendezvous from the sandbox, so a `run:detached` one-off's stdout cannot be read at all. As written, **a failure here is invisible** — which is precisely how the first run's three INVALID indexes went unnoticed until the catalog was polled by hand.

**Use the catalog as the progress channel.** This worked well and should be the documented method:

```sql
SELECT c.relname, i.indisvalid, i.indisready, pg_size_pretty(pg_relation_size(c.oid))
  FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname LIKE 'ix_fm_golf%' OR c.relname = 'ix_fm_source_created_at';
```

Read it as: `indisready=false` → phase 1 has not finished (**and note such an index is NOT maintained on writes, so it is inert**); `indisready=true, indisvalid=false` → built, in a wait phase, *or dead*; `indisvalid=true` → done. Distinguish "in a wait" from "dead" by whether a one-off dyno is still alive (`heroku ps`), never by the catalog alone — they are identical there.

### Result of the corrected run

| index | state | size |
|---|---|---|
| `ix_fm_source_created_at` | ✅ **VALID** | 6,088 kB |
| `ix_fm_golf_identity_extid` | ✅ **VALID** | 16 kB |
| `ix_fm_golf_identity_category` | ⚠️ **not built** — `indisready=false`, 0 bytes, inert | — |

The three INVALID indexes from attempt 1 were dropped before any retry, so no write tax was left behind.

**Measured payoff of (3), which needed neither the code half nor the flag** — `EXPLAIN (ANALYZE)` on production after the index:

```
Index Only Scan using ix_fm_source_created_at
Actual Total Time  = 0.149 ms     Actual Loops = 1
Shared Read Blocks = 0            Shared Hit Blocks = 5
```

against 2,746 ms mean and 186.6 MB physically read per call before. `Actual` times with loops stated, so this is runtime, not a cost estimate.

### ⛔ The flag stays OFF, and branch B is the open question

`GOLF_IDENTITY_SPLIT_SCAN` is unset and untouched. **`ix_fm_golf_identity_category` — branch B's index — does not exist**, so flipping now would run the `UNION` with one unindexed branch, and unindexed the `UNION` costs **255,180** against the `OR`'s **128,191**. Step 5.3's preconditions are not met. **The branch-B call belongs to the latency lane**: rebuild it, or change the shape. Do not flip until it is built and `EXPLAIN` shows both branches indexed.

> ⚠️ **The 255,180 figure above is now STALE.** It was measured when NEITHER golf index existed. One
> of the two is now valid, which changes the number but NOT the verdict — see §0b CORRECTION 2. Do
> not re-derive "is it still 2×?" as the flip test; it is no longer 2×, and it is still wrong to flip.

---

## 0b. LAT-P059 RE-READ — 2026-08-17, and two of this document's own checks are now unsafe

Production Phase-0 re-read, 2026-08-17 ~09:2x PDT / 16:2x UTC, Heroku commit `3fce7867`, PG 17.10.
The catalogue confirms INT-071's end state three days on, with the two valid indexes having grown:

| index | `indisvalid` | `indisready` | size |
|---|---|---|---|
| `ix_fm_source_created_at` | ✅ true | true | **7,520 kB** (was 6,088 kB) |
| `ix_fm_golf_identity_extid` | ✅ true | true | **40 kB** (was 16 kB) |
| `ix_fm_golf_identity_category` | ⛔ **false** | **false** | **0 bytes — still not built, still inert** |

`GOLF_IDENTITY_SPLIT_SCAN` re-read: **still unset**. So **both halves of the ruling-050 prediction
are still missing** — the DDL half is 2 of 3, and the flag half has not happened. Per the Fable
directive (*"grade the registered prediction only after BOTH halves exist … or grade nothing and
name the missing half"*), **LAT-P059 graded nothing.** The `OR` statement is unchanged and slightly
worse than baseline: `queryid 184240953744049829` now reads **516.7 MB/call** at **mean 2,913.3 ms**,
against the 492.5 MB / 2,741.3 ms banked on 2026-08-14.

### 🔴 CORRECTION 1 — §5.4's index-usage query can never return a row

The "worth reading, since it is the whole point" query filters `pg_stat_user_indexes` on **`relname`**.
In that view **`relname` is the TABLE name; the index name is `indexrelname`.** As written it returns
**zero rows, always** — measured both ways this window:

```
... FROM pg_stat_user_indexes WHERE relname     IN ('ix_fm_...')  ->  0 rows
... FROM pg_stat_all_indexes  WHERE indexrelname IN ('ix_fm_...')  ->  3 rows, real counters
```

This is the failure shape the program keeps finding: **a verification step that cannot pass.** Its
stated reading — *"`idx_scan = 0` an hour after the flip means the planner is not using them"* — is
one short step from an empty result set, and an empty result set is not `idx_scan = 0` (gotcha #53:
an empty answer is a response shape, not a fact). §5.4 is corrected in place below.

### 🔴 CORRECTION 2 — §5.3's numeric cost bar now PASSES while branch B still Seq Scans

Both shapes re-`EXPLAIN`ed this window against the **current, partially-indexed** catalogue:

| shape | plan | total cost |
|---|---|---|
| `OR` (today's default) | one Seq Scan | **128,261.89** |
| `UNION` (gated) | Index Only Scan `ix_fm_golf_identity_extid` (45.89) **+ Seq Scan branch B (127,864.28)** + Sort + Unique | **128,033.85** |

The `UNION` is now **0.998×** the `OR` — not the 1.99× regression this document was written against.
The reason is that branch A's index landed and branch A is tiny; **branch B, which carries 7,263 of
the 7,343 rows, still sequentially scans the whole 977 MB heap.**

**The verdict is unchanged — DO NOT FLIP — but the reason has changed, and the numeric criterion has
silently inverted.** §5.3 says to require "a total cost **well under 128,191.5**". Today's `UNION`
costs 128,033.85, which **is** under 128,191.5. A reader applying the numeric bar literally would
conclude the gate passes, flip the flag, and buy a Sort + Unique for a 0.2% cost change and no
reduction whatsoever in physical reads.

**So the gate is PLAN SHAPE, never a cost ratio.** The binding condition is the one sentence:
*both* branches must show an `Index Only Scan` / `Bitmap Index Scan`. A cost number cannot express
it, because one indexed branch out of two can drag the total under the bar while the expensive
branch is untouched. §5.3 is corrected in place below.

### ✅ The A2 index is in active production use — measured, not assumed

`ix_fm_source_created_at`: **`idx_scan = 3,360`**, `idx_tup_read = 278,374,078`. It is being chosen
by the planner and is doing work. This remains the one part of LAT-P058 that has actually landed,
and it needed neither the code half nor the flag.

### Retry for the one remaining index

Nothing about the DDL needs re-derivation — statement (1) in §3 is correct as written, now that
`lock_timeout` is `60s`. Preconditions re-read this window: **P1 disk 51 GB (unchanged, ~13 GB free,
well over the 2 GB floor); P3 zero transactions older than 60 s; P4 flag off.** P2 needs one
addition, because the ground has changed:

> **P2 (amended).** `ix_fm_golf_identity_category` **already exists as a not-ready stub**
> (`indisvalid=false, indisready=false`, 0 bytes). `CREATE INDEX CONCURRENTLY` will fail on the
> duplicate name. **`DROP INDEX CONCURRENTLY ix_fm_golf_identity_category;` first.** It is inert —
> a not-ready index is not maintained on writes — so this is a correctness precondition for the
> retry, **not** an active-harm cleanup, and it is not urgent on its own. INT-071's attempt to drop
> it was stopped by a session guardrail on encoded production DDL; that guardrail was respected and
> the stub was left in place deliberately.

After it goes valid, run §5.3 as **plan shape**, and only then §6.

**Status:** SPEC. The lane wrote it; the lane does not run it.
**Addressee:** the Integrator, as a `heroku run:detached` one-off dyno operation.
**Explicitly NOT:** an Alembic migration (gotcha #31), and not a task for Alex.
**Authority:** Fable directive 2026-08-14, item 1 — *"Write the index half as a spec for the
INTEGRATOR: exact DDL (CREATE INDEX CONCURRENTLY), preconditions, timing constraints vs the hourly
drains, and the pg_stat verification plan. The integrator runs it as a one-off dyno op — not Alex,
not a migration (gotcha #31)."*
**Code half:** `program/latency-53` — `golf_identity_select()` in `backend/app/routes/golf.py`,
config-gated OFF by default. This document is the other half.
**Measured:** production, 2026-08-14 ~17:3x–17:5x PDT, Heroku v3820 / `cabc791a`, PG 17.10,
Standard 0. Every number below is a read, not an estimate.

---

## 1. What this fixes, and how big it is

One statement is **the single largest consumer of physical reads in the database**:

```
queryid 184240953744049829
SELECT futures_markets.id, futures_markets.source, futures_markets.external_id, futures_markets.name
  FROM futures_markets
 WHERE futures_markets.external_id ILIKE 'golf_%'
    OR futures_markets.llm_sport_category = 'golf'
```

| | measured |
|---|---|
| calls (lifetime in the `pg_stat_statements` window) | **5,829** |
| mean | **2,741.3 ms** |
| max | **37,482.9 ms** |
| `shared_blks_read` | **367,470,460** blocks = **2,803 GB** |
| per call | **492.5 MB physically read** |
| daily | **1,110 calls · 533.7 GB/day = 19% of every physical read the database performs** |

It is on the **request path** — `_build_completed_tournament`, which serves every completed golf
tournament page, all four majors among them.

**It reads 7,169 rows out of 779,617 (0.92%) and pays a full sequential scan of a 977 MB heap to
find them.** That is the whole defect. There is no index it can use:

| candidate | why it cannot serve this query |
|---|---|
| `ix_futures_markets_source` | wrong column |
| `uq_futures_source_external (source, external_id)` | `external_id` is the SECOND column; no prefix scan on it alone, and `ILIKE` cannot use a plain btree anyway |
| `ix_fm_feed_open_sports (llm_sport_category, …)` | **PARTIAL** on `status='open' AND event_id IS NULL`; this query filters on neither, by design — completed markets are exactly what it exists to find |

> ⚠️ **Premise correction for `lat-p057-tail-attack-design.md` §2 A1.** That design said
> "`llm_sport_category` has a btree". **It does not.** The only index over that column is the
> partial one above, and it is unusable here. The full index catalogue was read this window
> (`pg_indexes`, 17 indexes on `futures_markets`) — the design's A1 sizing stands, its index premise
> does not.

---

## 2. The ordering constraint, and why it is load-bearing

The code half ships the `UNION` shape — two independently indexable branches — **gated OFF**.

`EXPLAIN` on production, both shapes, plan-only:

| shape | plan | total cost |
|---|---|---|
| `OR` (today, and the default) | one **Seq Scan** | **128,191.5** |
| `UNION` (the gated shape) | **TWO Seq Scans** + Sort + Unique | **255,180.0** |

**Until these indexes exist the `UNION` is a 1.99× REGRESSION on the largest query in the
database.** Two sequential scans of a 977 MB heap are worse than one. That is why the shape is
behind a config var rather than merged bare, and it is why the flag must not be flipped before
step 5 verifies the plan.

**Set-equality of the two shapes is proven, not assumed** — production, over the real corpus:

```
cur_n = 7169   new_n = 7169   in_cur_not_new = 0   in_new_not_cur = 0
md5(ordered id list)  OR    = 0e7625c986754f8315b451c1003dd206
md5(ordered id list)  UNION = 0e7625c986754f8315b451c1003dd206
```

Plus `backend/tests/test_golf_identity_prefilter.py` (22 cases), which proves it again over a
seeded corpus containing the adversarial rows: matches-both (where `UNION ALL` would duplicate),
matches-external-id-only, matches-category-only, matches-neither, the `_`-as-LIKE-wildcard case,
and the uppercase case that a `LIKE`-for-`ILIKE` "tidy-up" would silently drop.

---

## 3. Exact DDL

Three indexes. Two serve the golf query (one per `UNION` branch); the third is the A2 fix, which
needs **no code change at all** and can be judged independently.

```sql
-- Session setup. NOT optional. CREATE INDEX CONCURRENTLY cannot run inside a
-- transaction block, and it will be killed by any inherited statement_timeout.
SET statement_timeout = 0;
SET lock_timeout = '60s';   -- was '5s'; 5s FAILS. See the EXECUTION RECORD below.
SET maintenance_work_mem = '128MB';   -- server default is 205MB; these builds need far less

-- (1) branch B of the UNION: llm_sport_category = 'golf'
--     PARTIAL + COVERING. ~7,169 rows, ~1 MB. Serves an Index Only Scan returning
--     exactly the four columns the query selects, so the 977 MB heap is not touched.
CREATE INDEX CONCURRENTLY ix_fm_golf_identity_category
    ON futures_markets (id)
    INCLUDE (source, external_id, name)
    WHERE llm_sport_category = 'golf';

-- (2) branch A of the UNION: external_id ILIKE 'golf_%'
--     ~4 rows today. Tiny, and still required: without it branch A seq-scans and the
--     UNION is worse than the OR it replaced.
CREATE INDEX CONCURRENTLY ix_fm_golf_identity_extid
    ON futures_markets (id)
    INCLUDE (source, external_id, name)
    WHERE external_id ILIKE 'golf_%';

-- (3) A2, independent of the golf query and of the code branch:
--     SELECT max(created_at) FROM futures_markets WHERE source = $1
--     measured 186.6 MB read per call, 280.6 calls/day, 51.1 GB/day, mean 2,746 ms —
--     to return ONE value. Today's plan is a Bitmap Heap Scan over 197,776 kalshi rows
--     (verified by EXPLAIN this window). This makes it a one-tuple index-only scan.
--     ~779,617 rows × ~30 B ≈ 25-35 MB.
CREATE INDEX CONCURRENTLY ix_fm_source_created_at
    ON futures_markets (source, created_at DESC);
```

**If (2) fails with `functions in index predicate must be marked IMMUTABLE`** — `ILIKE` is `~~*`,
which should be immutable, but if this server disagrees, substitute:

```sql
CREATE INDEX CONCURRENTLY ix_fm_golf_identity_extid
    ON futures_markets (lower(external_id) text_pattern_ops)
    INCLUDE (source, external_id, name);
```

…and **stop there without flipping the flag**, because that fallback is a full-table index
(~110 MB) whose predicate does not match the query's `ILIKE` — it would need a matching code change
(`func.lower(external_id).like('golf_%')`) that this branch does not ship. Report it back; do not
improvise the code side.

**Optional, after all three succeed** — populates the visibility map so the Index Only Scans stay
index-only rather than falling back to heap fetches:

```sql
VACUUM (ANALYZE) futures_markets;   -- minutes on a 977 MB heap; safe, online, interruptible
```

---

## 4. Preconditions — check each, in order

| # | check | how | abort if |
|---|---|---|---|
| P1 | disk headroom | `SELECT pg_size_pretty(pg_database_size(current_database()))` | **51 GB / 64 GB (79.75%) measured today.** The three indexes add **~35 MB**, and a `CONCURRENTLY` build needs transient space of the same order. Abort if free space is under 2 GB. |
| P2 | no index of these names already exists, valid or invalid | `SELECT relname, indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid WHERE relname LIKE 'ix_fm_golf_identity%' OR relname='ix_fm_source_created_at'` | any row with `indisvalid=false` — **drop it first** (see §7); a failed `CONCURRENTLY` leaves an INVALID index that is never used but IS maintained on every write |
| P3 | no long-running transaction is open on `futures_markets` | `SELECT pid, state, now()-xact_start AS age, left(query,80) FROM pg_stat_activity WHERE xact_start IS NOT NULL AND now()-xact_start > interval '60 seconds' ORDER BY age DESC` | anything older than ~2 min. **`CREATE INDEX CONCURRENTLY` waits — twice — for every transaction that can see the table.** One 5.6-minute query stalls the whole build. There is a known 335,941 ms-mean `SELECT DISTINCT fos.outcome_id …` in this database; do not start while it is running. |
| P4 | ~~the flag is OFF~~ **— VOID (#1917): there is no flag.** The var is deleted from the code and unset in production; nothing reads it. If `heroku config:get GOLF_IDENTITY_SPLIT_SCAN -a bainluck` ever returns non-empty, that is someone re-adding a var against ruling 076, not a precondition failure — unset it and read §5.3. | — | — |
| P5 | the code half is deployed (or is not — either is fine) | `curl -s "$BAINLUCK_API/api/health"` | nothing. The DDL is safe with or without `program/latency-53` deployed: with the flag OFF the route still runs the `OR`, which merely *gains* a `BitmapOr` option. **The DDL may therefore run BEFORE the merge, and that is the preferred order.** |

### Timing constraints vs the drains

There is **no quiet window** — the database sustains **79.1 MB/s** of physical reads around the
clock and `crontab` coverage is dense at nearly every minute (that finding is `lat-p057`'s Option
B2, rejected on measurement). So this spec does **not** ask for a quiet window. It asks for the
three specific things that actually break a `CONCURRENTLY` build:

1. **Avoid the 6-hourly backfill band.** `backfill_winners` and the six-hourly drains cluster at
   `minute IN (10,15,20,25,30,35,40,45,50)` of `hour % 6 == 0`. `backfill_winners` runs ~35 phases
   and holds the longest transactions in the system. **Start at `minute 55–05` of an hour that is
   NOT `hour % 6 == 0`.** That leaves the `*/10` and `*/15` precompute beats, which are short.
2. **Do not start within 10 minutes of a Heroku release.** A release runs Alembic; a migration
   taking an `ACCESS EXCLUSIVE` lock while a `CONCURRENTLY` build holds `SHARE UPDATE EXCLUSIVE`
   deadlocks the release, and the release loses. Check `heroku releases -a bainluck -n 3` first.
3. **Expect minutes, not seconds, and do not interrupt.** Indexes (1) and (2) are ~1 MB and should
   build in well under a minute each; (3) scans 779,617 rows and will take single-digit minutes.
   `CONCURRENTLY` does two full passes plus two waits. **Killing it mid-build leaves an INVALID
   index** — see §7.

### The dyno invocation

Non-detached `heroku run` **silently fails in a sandbox** (gotcha #48) — it aborts on an EPERM
rendezvous and never executes, returning an empty stdout that reads exactly like success. Use
`run:detached`, and verify by side effect, never by stdout:

```bash
heroku run:detached --size=standard-1x -a bainluck -- \
  python3 -c "
import asyncio, os, asyncpg
DDL = [
  \"SET statement_timeout = 0\",
  \"SET lock_timeout = '60s'\",   # was '5s'; 5s FAILS -- see the EXECUTION RECORD
  \"CREATE INDEX CONCURRENTLY ix_fm_golf_identity_category ON futures_markets (id) INCLUDE (source, external_id, name) WHERE llm_sport_category = 'golf'\",
  \"CREATE INDEX CONCURRENTLY ix_fm_golf_identity_extid ON futures_markets (id) INCLUDE (source, external_id, name) WHERE external_id ILIKE 'golf_%'\",
  \"CREATE INDEX CONCURRENTLY ix_fm_source_created_at ON futures_markets (source, created_at DESC)\",
]
async def main():
    url = os.environ['DATABASE_URL'].replace('postgres://','postgresql://')
    conn = await asyncpg.connect(url, ssl='require')
    for s in DDL:
        print('RUN:', s[:70], flush=True)
        await conn.execute(s)     # asyncpg runs these OUTSIDE an implicit transaction
        print('OK', flush=True)
    await conn.close()
asyncio.run(main())
"
```

> **Scripts live at `/app`, not `/app/backend`** — a `cd backend &&` silently no-ops on a Heroku
> one-off dyno. The invocation above is self-contained precisely so that does not matter.
> ⚠️ asyncpg must not wrap these in a transaction. `conn.execute()` on a single statement is
> autocommit; do **not** put them inside `async with conn.transaction()`.

---

## 5. Verification plan — `pg_stat`, and the plan itself

Run all four. **Step 5.3 is the gate on flipping the flag.** Every one of these is a
`POST /api/admin/db-query` call; none of them needs psql (5432 egress is blocked from an agent
session).

**5.1 — the indexes exist and are VALID**

```sql
SELECT c.relname, i.indisvalid, i.indisready, pg_size_pretty(pg_relation_size(c.oid)) AS size
  FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname IN ('ix_fm_golf_identity_category','ix_fm_golf_identity_extid','ix_fm_source_created_at');
```
Expect **3 rows, all `indisvalid = true`**. Expected sizes: ~1 MB, ~16 kB, ~25–35 MB.
Any `indisvalid = false` ⇒ **HALT**, drop it (§7), diagnose, retry.

**5.2 — the golf query still returns the same 7,169 rows**

```sql
SELECT count(*) AS n, md5(string_agg(id::text, ',' ORDER BY id)) AS ids_md5
  FROM (SELECT id FROM futures_markets WHERE external_id ILIKE 'golf_%'
        UNION
        SELECT id FROM futures_markets WHERE llm_sport_category = 'golf') s;
```
The count will have drifted (markets are created continuously); the md5 will not match today's.
**What must hold is equality against the `OR` taken in the SAME statement** — re-run the paired
query from §2 and require `in_cur_not_new = 0` and `in_new_not_cur = 0`. ⚠️ `db-query` refuses a
**leading** `WITH`; put the CTE after a `SELECT` or use scalar subqueries.

**5.3 — ~~THE GATE: the plan uses the indexes, on both branches~~ — WITHDRAWN. There is nothing to flip.**

> ⛔ **DO NOT RUN THE STEP THAT USED TO BE HERE. IT PASSED, AND IT WAS WRONG BY 13.5×.**
>
> This step authorised flipping `GOLF_IDENTITY_SPLIT_SCAN` on two conditions: both `UNION` branches
> planning as index scans (sound), **and** the `UNION`'s total cost coming in under the `OR`'s
> 128,191.5 (**not a comparison at all**). LAT-P061 ran it. Both conditions passed, the second by a
> landslide — the `UNION` planned at **4,361.77**, a claimed 2.81× cheaper. Then the lane took a
> stopwatch to it:
>
> | | planner cost | warm median runtime | shared buffers |
> |---|---|---|---|
> | `OR` (live, post-index, `BitmapOr`) | 12,243.92 | **≈18.4 ms** | 1.00× |
> | `UNION` | 4,361.77 | **≈88.2 ms** | **2.45×** |
>
> **The gate said 2.81× cheaper; the stopwatch said 4.79× dearer** — backwards by 13.5×, and by
> 141× against the stale 128,191.5 bar the step quoted, which was the *pre-index* `OR`'s cost,
> superseded by the very DDL the flip was waiting on. 94 of the `UNION`'s 98 ms is a `HashAggregate`
> the `OR` never pays and the planner priced at nearly nothing. Following this runbook as written
> flips the flag, records a green gate, and ships a 4.8× slowdown **with the gate as the evidence.**
>
> The flip is **withdrawn permanently** (LAT-P061). The flag, the `UNION` branch and its tests are
> **deleted** (#1917, ruling 076 clause 2) — measured-worse code behind a permanently-off switch is
> a trap, not a rollback path. `golf_identity_select()` now takes no arguments and emits one
> statement. **There is no flag to set, so §6 is dead too.**
>
> Banked as **`docs/rulings/076-planner-cost-cannot-rank-two-statements.md`**. Full measurement:
> `docs/audits/latency/lat-p061-split-scan-refused.md`.

**5.3′ — what this step should have been, and the form any future rewrite gate takes**

Kept, in ruling 076's four-step form, because the *procedure* outlives this particular rewrite. Use
it for **any** flip that replaces statement A with statement B — none of the four steps is optional
and step 1 alone is what the old 5.3 mistook for a gate.

1. **Shape first, as a PRECONDITION, never as the verdict.** The right indexes, the right scan
   types, no surprise nodes. Cheap and fast to fail. For this rewrite that meant `Index Only Scan`
   (fallback `Bitmap Index Scan`) naming `ix_fm_golf_identity_extid` on one branch and
   `ix_fm_golf_identity_category` on the other. It passed — and the rewrite was still 4.8× worse.
2. **Then the STOPWATCH, ALTERNATING.** `EXPLAIN (ANALYZE, BUFFERS)`, A/B/A/B on the live database,
   **≥8 executions after warm-up**, medians reported with the spread. Alternating is not decoration:
   an all-A-then-all-B run hands the second arm a cache the first arm loaded.
3. **Report BUFFERS alongside time.** Time says what happened today; buffers say what happens when
   the pool is under pressure. The `UNION`'s 2.45× buffer draw is the durable finding — the one that
   would have bitten hardest exactly when the route matters.
4. **Re-measure the bar; never re-quote it** (ruling 069). Any threshold carried from an earlier
   window is stale by the table growth and the index builds that happened since.

**A cost number may appear as corroboration. It may never be the criterion.** `EXPLAIN`-derived
numbers gate **shape**; they do not gate **speed**.

The DDL, separately, is a **win on its own** and stays — via `BitmapOr` on the surviving `OR`:
`{"explain": true, "sql": "SELECT id, source, external_id, name FROM futures_markets WHERE external_id ILIKE 'golf_%' OR llm_sport_category = 'golf'"}`

**5.4 — `pg_stat_statements`, before and after**

The anchor is the **queryid**, which survives restarts. Baseline captured 2026-08-14 (this window):

| queryid | calls | mean_ms | max_ms | `shared_blks_read` | MB/call |
|---|---|---|---|---|---|
| `184240953744049829` | 5,829 | **2,741.3** | 37,482.9 | 367,470,460 | **492.5** |

```sql
SELECT queryid, calls, round(mean_exec_time::numeric,1) AS mean_ms,
       shared_blks_read,
       round((shared_blks_read*8192.0/GREATEST(calls,1)/1048576.0)::numeric,1) AS mb_per_call
  FROM pg_stat_statements
 WHERE queryid IN (184240953744049829);
```

⚠️ `pg_stat_statements` is **cumulative** and this view is **at its 5,000-entry cap and evicting**
(4,945 held when last read). So:
- Read the **delta over a fixed interval**, not the absolute. (The original bullet here said the
  `OR`'s counters "stop growing when the flag flips" — ~~struck, #1917~~: there is no flip, the `OR`
  is the only shape, and its counters keep growing forever. Delta-not-absolute still holds, for the
  eviction reason above.)
- ~~The `UNION` is a different statement with a different queryid; find it after the flip.~~
  **Struck (#1917).** No `UNION` statement is ever emitted. If one shows up in `pg_stat_statements`
  matching `'%UNION%' AND '%llm_sport_category%'`, that is a **regression to investigate**, not a
  queryid to record.
- **Errored statements are never recorded**, so the 37,482.9 ms max is a max over *successful* runs
  only; the true worst case is higher.

Also worth reading, since it is the whole point:

```sql
-- CORRECTED (LAT-P059). The original filtered on `relname`, which in this view is the
-- TABLE name, not the index name -- so it returned ZERO ROWS, always. See §0b CORRECTION 1.
SELECT indexrelname, idx_scan, idx_tup_read
  FROM pg_stat_all_indexes
 WHERE indexrelname IN ('ix_fm_golf_identity_category','ix_fm_golf_identity_extid','ix_fm_source_created_at');
```
Expect **one row per index that exists**. **A missing ROW means the index does not exist — which is a
different finding from `idx_scan = 0`, and the two must not be collapsed.** Measured 2026-08-17:
`ix_fm_source_created_at` `idx_scan = 3,360`; the two golf indexes `0`.

⚠️ **That reading is superseded and its explanation was wrong-shaped.** It was taken when only branch
A's index existed and the note attributed the two zeros to "the flag is off, so nothing emits the
`UNION` yet". There is no flag and no `UNION` (#1917): the indexes are consumed by the **`OR`'s
`BitmapOr`**, which is why they must be non-zero. Re-read them now that both are valid — a sustained
`idx_scan = 0` on either means the planner has stopped using it for the `OR` and the 516.7 → 2.395
MB/call win has silently reverted. That is the live check; the flip it used to gate does not exist.

---

## 6. ~~The flag~~ — DEAD. The flag does not exist.

> ⛔ **DO NOT RUN `heroku config:set GOLF_IDENTITY_SPLIT_SCAN=1`.** There is no such config var and
> no code reads one. `_GOLF_SPLIT_SCAN_ENV`, `_golf_split_scan_enabled()`, the `split=` parameter and
> the `UNION` branch were **deleted** in #1917; `golf_identity_select()` takes no arguments and emits
> exactly one statement, guarded by `test_golf_identity_prefilter.py`. Setting the var now does
> nothing at all — which is the *second*-worst outcome, the worst being that someone reintroduces the
> branch to make the runbook true again.
>
> Why, in one line: the `UNION` is **4.79× slower** than the `OR` it was meant to replace (≈88.2 ms
> vs ≈18.4 ms warm median, 2.45× shared buffers). See §5.3 above and ruling 076.
>
> **The DDL was the whole win, and it landed with the flag off the entire time** — 516.7 → 2.395 MB
> per call, ~2,900 ms → ≈18 ms, planner cost 128,191.5 → 12,243.92. Nothing about that result is
> waiting on a flip.

The deploy read (§8) still applies to the **DDL**, twice, per ruling 064.

---

## 7. Rollback

Only the DDL is rollable back now, and only the last two rows below apply.

| level | action | effect |
|---|---|---|
| ~~plan only~~ | ~~`heroku config:unset GOLF_IDENTITY_SPLIT_SCAN -a bainluck`~~ | **Struck (#1917).** There is no flag and no second plan to roll back to. The var is unset in production and unread by the code. |
| indexes | `DROP INDEX CONCURRENTLY ix_fm_golf_identity_category, ix_fm_golf_identity_extid, ix_fm_source_created_at;` (one statement per call; `CONCURRENTLY` again, `statement_timeout = 0`) | back to pre-LAT-P058 exactly — **and back to 516.7 MB physically read per call, 19% of all database reads.** This is a real rollback with a large, measured cost; do not take it as the cheap option. |
| a failed build | `DROP INDEX CONCURRENTLY <name>;` — **required**, not optional | an INVALID index is never *used* but is still *maintained on every write*, so leaving one is a permanent write tax |

**The paragraph that used to be here claimed config rollback as "the property the config gate buys,
and why the gate exists".** That property was real and it was still not worth it: what the gate
actually bought was a green certificate for a 4.79× regression (§5.3). A cheap rollback from a
change that should never ship is not a mitigation — ruling 076.

The code half needs no rollback: `golf_identity_select()` emits the same indexed `OR` it always did,
now as its only shape.

---

## 8. Pre-registered prediction (ruling 050) — grade after BOTH halves

The lane's registered prediction stands, and the directive is explicit that it is graded after both
halves. Restated here so the Integrator can grade the DDL's half without re-deriving it:

| surface | prediction | halt |
|---|---|---|
| 46 gold dispositions | **0 of 46 change. 39/44, MRR 0.8913043478260869.** Nothing here touches ranking. | **any** movement HALTS |
| golf completed-tournament route | p50 **2.74 s → < 500 ms** | no improvement ⇒ re-read the plan before iterating |
| DB physical read rate | **79.1 → ~62 MB/s**; pool turnover **12.9 → ~16.5 s** | flat ⇒ the `pg_stat_statements` attribution is wrong |
| **#1866's typeahead tail** | **0–15% improvement. Explicitly NOT predicted to be fixed.** | **> 30% ⇒ the continuous-throughput model is wrong**, the periodic-eviction model re-opens, and the next window must say WHICH model it now believes |

**Step 1 alone is not predicted to fix the tail**, and that is stated in advance on purpose: a 21%
cut in read volume moves pool turnover from ~12.9 s to ~16.5 s, nowhere near enough to hold 579 MB
of trigram index resident against arbitrary keystrokes. The tail's fix is the dedicated typeahead
index table (`lat-p057-tail-attack-design.md` Option D), which is a queue of its own with a
migration slot and a staleness sentinel in scope.

---

## 9. What this spec deliberately does not ask for

- **No Alembic migration.** Gotcha #31: a `CONCURRENTLY` build inside Heroku's ~5-minute release
  phase hangs the release into a full outage (the May 22 `odds_snapshots` incident).
- **No `psql`.** TCP 5432 egress is blocked from agent sessions; everything above runs through a
  one-off dyno or `POST /api/admin/db-query`.
- **No plan upgrade.** Storage at 79.75% is a real operational ceiling and belongs to Alex as a
  *storage* decision — `lat-p057` §2 Option C refuses to let latency be its justification.
- **No `status` or date filter on the golf query.** Completed markets are precisely what
  `_build_completed_tournament` exists to find; narrowing the row set would break the four majors
  it was written to rescue. `test_golf_completed_tournament_query_shape.py` asserts the absence of
  a `status` filter in both the caller and the prefilter.
