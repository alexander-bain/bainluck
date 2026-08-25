# LAT-P088 — `ix_futures_name_trgm_open`: an ATTENDED psql runbook for Alex

**Status:** spec only. **No DDL was run by this session** (LAT-P088 directive item 2, explicit).
**Ruling 131 / gotcha #31:** index DDL with no code half runs as attended psql, never inside an
Alembic migration — `CONCURRENTLY` inside the Heroku release phase hangs the release and takes the
site down (the May 22 `odds_snapshots` outage).

**Gate:** `backend/scripts/gate_futures_open_trgm_index.py`. Recorded RED at **exit 1** before this
spec was written — `docs/audits/latency/lat-p088-futures-open-trgm-red.json`.

---

## 🔴 0. THE DIRECTIVE'S NAMED LEVER IS THE WRONG INSTRUMENT — read this before §2

LAT-P088 asked for a **futures FTS** index, on the strength of LAT-P087's own decomposition:
`futures` is 44.8% of the feed's server total and 59.3% of `/api/events/search`. **Both
percentages are correct. The instrument is wrong twice, and both refutations are measurements,
not opinions.**

### 0a. The feed's 44.8% contains no text predicate at all

The feed's `futures` cost is two stages, `market_load` and `scoring_loop`
(`backend/app/routes/feed.py:6520`, `:7429`):

| stage | what it actually is |
|---|---|
| `market_load` | `SELECT FuturesMarket … WHERE id IN (<ids>)` with eager loads — an **integer primary-key lookup** |
| `scoring_loop` | a pure-Python per-market loop that **issues no SQL whatsoever** |

There is no `ILIKE`, no `tsquery`, no `to_tsvector` in either. **44.8% of the feed is real and is
44.8% of something no index on text can reach.** The two costs named as one lever share a word,
not a mechanism. This index does not claim the feed half, and neither would an FTS index.

### 0b. The search half already HAS the FTS predicate, and it is already free

The name arm does carry `to_tsvector('english', coalesce(name,'')) @@ websearch_to_tsquery(…)`,
ANDed with the trigram ILIKE (`events.py:3049`; the comment there records FTS being *removed* from
recall in #993 and later re-added as a precision filter). Production `EXPLAIN ANALYZE`,
2026-08-25, on the arm compiled from the live ORM:

```
Bitmap Heap Scan on futures_markets     131.3 ms   rows=16
  Filter: (… to_tsvector(…) @@ 'world' AND to_tsvector(…) @@ 'seri')
  Rows Removed by Filter: 0            ← ZERO
```

The FTS predicate runs on **16 rows** and removes **none**. An index serving it would save two
`to_tsvector` calls on sixteen rows. (The `numnode(…)=0 OR …` wrapper folds at plan time, so
indexability was never the obstacle — the predicate has nothing left to do by the time it runs.)
**A futures FTS index is NOT INDICATED. Do not create one.**

---

## 1. What the measurement actually found — the defect this DDL attacks

One node above that filter:

```
BitmapAnd                                          130.4 ms
  Bitmap Index Scan ix_futures_name_trgm            25.7 ms  rows=315
  Bitmap Index Scan ix_futures_markets_status      104.5 ms  rows=71,368
```

A 71,368-row btree bitmap on `status='open'`, built so it can be ANDed against a trigram bitmap
that already returned 315 rows. It cannot remove a row the trigram scan did not already have.

That node was 80% of *that* term's arm. **It is not the general case, and it was checked rather
than generalised**: across 14 probed terms the planner adds the status bitmap for only 4, and on
`champion` it is 22.2 ms of 400 ms. The defect the two shapes share sits one level down:

| quantity | measured 2026-08-25 |
|---|---|
| `futures_markets` | **858,938 rows / 985 MB** |
| of which `status='open'` | **71,368 (8.3%)** |
| `%winner%` matches | **42,336 rows** |
| …of those, open | **3,483 (8.2%)** |
| `champion` BitmapOr → heap emit | **70,711 → 3,794** |

**Every futures search trigram bitmap is built over the whole corpus while only ~8% of what it
returns can ever appear in a result.** That ~12× of discarded work is paid three times — in the
bitmap scan, in the `BitmapAnd`, and in the heap recheck — and a fourth time, for the subject
terms, in the 71,368-row btree bitmap that exists only to perform the discard.

Probe-independent corroboration, `pg_stat_user_indexes`:

```
ix_futures_markets_status   774,846 scans   50,492,855,560 tuples read
```

50.5 **billion** tuples — the highest tuple-read of any index on either futures table, at
**65,152 rows per scan**, which reproduces the 71,368 above from counters no query of mine wrote.

---

## 2. THE COMMAND BLOCK — copy-paste, in order

```sql
-- ── session GUCs ────────────────────────────────────────────────────────────
SET statement_timeout    = 0;        -- CONCURRENTLY must not be cut off mid-build
SET lock_timeout         = '60s';    -- '5s' FAILS in this database (LAT-P058)
SET maintenance_work_mem = '256MB';  -- a GIN build over 71,368 rows of text

-- ── step 0: precondition P3 — ABORT if this returns a row ───────────────────
--     CONCURRENTLY waits out every transaction older than itself.
SELECT pid, now() - xact_start AS age, state, left(query, 80) AS q
  FROM pg_stat_activity
 WHERE xact_start IS NOT NULL
   AND now() - xact_start > interval '60 seconds'
   AND pid <> pg_backend_pid()
 ORDER BY age DESC;

-- ── step 0b: precondition P2 — ABORT if this returns a row ──────────────────
--     A half-built index holds its name; drop it before retrying.
SELECT c.relname, i.indisvalid, i.indisready
  FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE i.indrelid = 'futures_markets'::regclass
   AND c.relname = 'ix_futures_name_trgm_open';

-- ── the one index ───────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY ix_futures_name_trgm_open
    ON futures_markets USING gin (name gin_trgm_ops)
    WHERE status = 'open';
```

One `CREATE`, then §3. If it errors or is interrupted:
`DROP INDEX CONCURRENTLY ix_futures_name_trgm_open;` before retrying.

### 2a. Why the predicate is written `status = 'open'` and not `(status)::text = 'open'::text`

LAT-P086 §0 killed a proposed index because its expression (`::text`) did not match the form the
route compiles (`CAST(… AS VARCHAR)`) — it would have been created, been valid, and never been
used. So the same check was run here rather than assumed.

`status` is `VARCHAR`, so Postgres normalises **both** the route's predicate and this DDL's to
`(status)::text = 'open'::text`; the four partials already in this schema are stored in exactly
that form. The route's compiled arm emits `futures_markets.status = 'open'`
(`scripts/explain_search_arm.py "world series" --arm name`).

**And implication is PROVEN in this database, not argued from the manual** —
`pg_stat_user_indexes`, same read:

```
ix_fm_feed_open_sports     745,024 scans      (WHERE (status)::text = 'open'::text AND event_id IS NULL)
ix_fm_feed_open_timely     150,739 scans
ix_fm_feed_open_volume      11,943 scans
ix_fm_feed_open_enriched     6,126 scans
```

All four `status='open'` partials are planner-chosen in production, hundreds of thousands of times.
The planner in *this* database already satisfies an ORM-emitted `status = 'open'` from a partial
index written that way. That is what §3b then confirms for this specific index.

### 2b. Sizing and write tax, from `pg_class` rather than from hope

`ix_futures_name_trgm` (the full trigram GIN) is **182 MB** over 858,938 rows. The partial covers
71,368 rows (8.3%), so **~15–20 MB** is the expectation. Text length is not uniform across
open/closed rows, so treat that as an estimate and read the real number in §3a — a wildly larger
result is itself a finding.

The write tax is paid only on rows entering, leaving, or changing `name` while at
`status='open'`. Kalshi/Polymarket polling writes `futures_markets` heavily, but the great
majority of that volume is snapshot/price churn on `futures_outcomes` and status transitions
*out* of open, which remove a row from this index rather than maintaining it.

---

## 3. POST-CREATE VERIFICATION — both halves are required

Ruling 131: "created" is not "used". An index that is `VALID` and never chosen is a write tax with
a name.

### 3a. The catalog says VALID, and the size is sane

```sql
SELECT c.relname,
       i.indisvalid,
       i.indisready,
       pg_size_pretty(pg_relation_size(c.oid)) AS size
  FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE i.indrelid = 'futures_markets'::regclass
   AND c.relname = 'ix_futures_name_trgm_open';
```

Required: `indisvalid = t`, `indisready = t`. Expect `size` ≈ 15–20 MB (see §2b).

### 3b. The planner USES it — and the status bitmap is GONE

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT futures_markets.id FROM futures_markets
 WHERE futures_markets.name ILIKE '%champion%'
   AND futures_markets.status = 'open'
   AND (futures_markets.resolution_date IS NULL
        OR futures_markets.resolution_date >= now());
```

Two things must both be true:

1. a `Bitmap Index Scan on ix_futures_name_trgm_open` appears; **and**
2. there is **no** `Bitmap Index Scan on ix_futures_markets_status` in the same plan.

(2) is the half that matters and the half a casual check skips. If the planner picks the new index
*and still* builds the 71,368-row status bitmap, it is not satisfying `status='open'` from the
index predicate, and the main mechanism has not engaged even though the index is in the plan.
The gate encodes exactly this as its SHAPE criterion (`FORBIDDEN_INDEX`).

### 3c. The gate, with the exit code read as a VALUE

```bash
source ~/.claude/.env
python3 backend/scripts/gate_futures_open_trgm_index.py --label after \
  --out docs/audits/latency/lat-p088-futures-open-trgm-gate-after.json
echo "EXIT CODE: $?"
```

The budget criterion is **`median over terms of (ratio_after / ratio_before) ≤ 0.5`**, where each
ratio is `median(name arm) / median(outcome arm)` from the same interleaved batch. Relative to the
recorded before, so **a no-op scores 1.0 on every term and fails arithmetically**.

#### The criterion was validated against this database, not just reasoned about

"A no-op scores 1.0" is true of the arithmetic. Whether ambient variance can reach 0.5 on its own
was a separate question — and leaving it unanswered is exactly how LAT-P085's `exec_ms < 50` got
banked. So a **second `before` run** was taken with no DDL in between and scored against the
baseline exactly as an `after` run would be. Two runs of the same unindexed database:

| | median collapse | per-term range | verdict at ceiling 0.5 |
|---|---|---|---|
| no-op, 1 round | **1.005** | 0.197 – 1.836 | FAILS — gate holds |
| no-op, 5 rounds | **1.295** | 0.529 – 1.774 | FAILS — gate holds |

2.6× of headroom. Individual terms are genuinely noisy and several single terms *do* cross 0.5 on
noise alone — which is precisely why the verdict is a **median over eight terms** rather than a
per-term AND. Artifact: `lat-p088-futures-open-trgm-noop-selftest.json`, and
`tests/test_gate_futures_open_trgm_index.py` asserts the headroom so that if production drift ever
erodes it, the ceiling gets re-derived instead of quietly passing.

Per gotcha #54 as amended — **`1` is a result; every other non-zero is a story about the harness**:

| exit | meaning | action |
|---|---|---|
| **0** | GREEN — shape, budget, non-regression and semantics all hold | keep the index |
| **1** | RED — a criterion genuinely failed | §4 rollback; the mechanism did not pay |
| **2** | the harness could not answer (no baseline, `ADMIN_TOKEN` unset, db-query refused) | **neither verdict applies** — fix the harness and re-run |

Do not pipe that command. `cmd \| tail` reports *tail's* exit code, and this lane has two recorded
gate runs that logged a clean `0` over runs that never happened.

### 3d. An hour later — is real traffic choosing it

```sql
SELECT indexrelname, idx_scan, idx_tup_read
  FROM pg_stat_user_indexes
 WHERE relname = 'futures_markets'
   AND indexrelname IN ('ix_futures_name_trgm_open',
                        'ix_futures_name_trgm',
                        'ix_futures_markets_status');
```

`ix_futures_name_trgm_open.idx_scan` must be climbing. The interesting number is
`ix_futures_markets_status.idx_tup_read` — its **rate** should fall sharply from 65,152 rows per
scan. Note the counters are cumulative since the last stats reset, so read the delta between two
reads, never the absolute.

---

## 4. Rollback

```sql
DROP INDEX CONCURRENTLY ix_futures_name_trgm_open;
```

No application code changes, so there is nothing to revert on the code side and no deploy is
involved in either direction. `ix_futures_name_trgm` is untouched and continues to serve every
query this index would have served. **Rollback is one statement with no coordination.**

---

## 5. What this is predicted to buy — and what it is NOT

**Claimed.** The `futures` name arm of `/api/events/search`, on trigram-broad terms. The measured
mechanism is a ~12× reduction in bitmap and heap-recheck volume, plus removal of the 71,368-row
btree bitmap on the terms that build one. The four subject terms are the **slowest** in the probed
set (`champion` 1,054 ms, `winner` 616 ms, `election` 330 ms in the recorded before) and are
plausible real queries.

**NOT claimed, explicitly:**

- **The feed's 44.8%.** §0a. No text predicate exists there. Nothing in this spec moves it.
- **An FTS win.** §0b. `Rows Removed by Filter = 0`.
- **A fixed millisecond figure.** The gate's budget is a *ratio against a CPU-matched control*
  precisely because absolute numbers are unusable here — LAT-P087 found the teams gate's
  `exec_ms < 50` passing on a completely unindexed database under a 5.9× ambient load swing.
- **The full-arm timeout.** `champion` and `winner` currently exceed the endpoint's 10 s row-path
  timeout on the *full* production UNION; the route sheds the futures stage there
  (`events.py:2920`). This index shrinks one arm of that UNION. Whether it brings the full arm back
  under the timeout is a **question for the after-run**, recorded in the gate's semantics field as
  `UNREAD:statement_timeout`, not a claim being made here.

---

## 6. Scope note — one index, one arm

This serves the **name** arm of the futures search. The **outcome** arm (trigram work on
`futures_outcomes.name`) is deliberately untouched: it is the gate's CPU-matched control, and it is
only a valid control because this DDL cannot serve it. `futures_outcomes` carries its own ~69–71%
share of some queries' blocks (`events.py:2963`) and is a separate lever for a separate cycle —
with its own before/after, not folded into this one.
