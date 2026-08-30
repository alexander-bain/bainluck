# LAT-P148 — the index that could not be used by the query that asked for it

**Pillar:** DISCOVER experience. **Ship:** the FIRST open of a big championship market —
NFL Super Bowl Winner, MLB World Series Winner — stops taking four to seven seconds before
anything renders. LAT-P127 fixed the *repeat* open with a cache; this fixes the open that no
cache can help: the one a brand-new visitor pays, and the one every visitor pays again after
each 300 s expiry, deploy, or Redis eviction.

**Issue:** [#2333](https://github.com/alexander-bain/bainluck/issues/2333).
Branch `program/latency-148`, cut from `origin/master` @ `944c466e`. `migration_slot: none`,
`beat_schedule_change: FALSE`, `ddl: NONE`.

**Directive:** `runner-inbox/latency/041-market-page-cold-read.md`, staged by Fable
2026-08-30 ~8:00am PT — Alex's own hand-measured page.

---

## 1. The report, and reproducing it

Alex measured `/api/futures/86832` at **6.7 / 0.47 / 0.45 s** on the morning of 2026-08-30
with his three-curl loop, and asked the obvious question: `latency-113` is merged
(`26c219aa`), `ix_futures_odds_snapshots_outcome_bookmaker_captured` exists — so why is the
cold read still six seconds, and why is warm 0.45 s when P127 promised ~20 ms?

Reproduced from this worktree the same morning, same loop:

```
read1: total=4.042656s http=200
read2: total=0.452893s http=200
read3: total=0.418197s http=200
```

**They are two different findings, and only one of them is a bug.**

## 2. The warm number is not server time

`x-timing-split` on a genuinely warm read, three in a row:

```
wall=93.5;db=61.9;app=31.6;q=3;maxq=32.0;router=2.1
wall=60.1;db=32.5;app=27.6;q=3;maxq=15.9;router=2.2
wall=26.9;db= 4.4;app=22.5;q=3;maxq= 2.5;router=2.5
```

**27–94 ms.** The 0.45 s in the curl loop is the client's connection setup:

```
dns=0.000015  conn=0.000208  tls=0.166971  ttfb=0.302460  total=0.380329
dns=0.000016  conn=0.000186  tls=0.167689  ttfb=0.320354  total=0.398744
```

167 ms of TLS handshake plus ~135 ms of round trip before a byte arrives, and each `curl`
invocation opens a fresh connection so each one pays it again. A browser pays this once and
then reuses the connection.

**P127's warm bar was met.** Recorded here so the warm number is not re-litigated a third
time: `total=` from a cold-start curl is not a server measurement, and the three-curl loop
cannot see the difference. `x-timing-split` can.

## 3. The cold number is a real bug, and it is one query

`x-timing-split` on a cold read (the cache had just expired):

```
wall=3625.5; db=3595.4; app=30.1; q=4; maxq=3547.9; router=1.4
```

Four statements; **one of them is 3,548 ms of the 3,625 ms wall**. It is the provenance
query in `_get_source_breakdown`. `EXPLAIN (ANALYZE, BUFFERS)` against production:

```
Subquery Scan                                      actual 9,163 ms   rows out    256
  WindowAgg
    Sort   Sort Method: external merge   7,640 kB DISK    rows in 190,656
      Nested Loop                                          rows in 190,656
        Index Scan  ix_futures_outcomes_market_id                 32 rows
        Index Scan  ix_futures_odds_snapshots_outcome_id   5,958 rows x 32 loops
Shared I/O Read Time 7,973 ms      Temp Written 956 blocks
```

**190,656 rows read and sorted to disk to return 256.** A ratio of 745:1.

### 3.1 Why the index Alex built is not in that plan

This is the part worth keeping. The index is
`(outcome_id, bookmaker, captured_at DESC)`. The query is

```sql
row_number() OVER (PARTITION BY outcome_id, bookmaker ORDER BY captured_at DESC)
```

with a predicate on `outcome_id` **and nothing on `bookmaker`**. PostgreSQL has no index
skip scan, so a lookup that constrains only the leading column cannot descend into the
second one — it must read every entry under each `outcome_id` regardless. The planner
compared a wide index it could only scan against a narrow one it could only scan, and
correctly chose the narrow one.

**So P127-3 could not have worked as specified.** The DDL was necessary and not sufficient;
the shape had to change with it. This is the finding, not the stale statistics below.

### 3.2 The stale statistics are real and are not the cause

`pg_stat_user_tables` on `futures_odds_snapshots`:

| n_live_tup | last_analyze | last_autoanalyze | last_autovacuum |
|---|---|---|---|
| 196,407,475 | `NULL` | 2026-08-22 | 2026-08-15 |

The planner estimated **1,661** rows where 190,656 came back — a 115× miss, consistent with
eight-day-old statistics on a 196 M-row table. Worth fixing on its own account, and it is
**parked, not dropped** — but it is not this bug. Every plan available for that query shape
reads every row; a better estimate would have chosen the same plan.

## 4. What replaces it

The skip PostgreSQL will not do for us, written out by hand. Walk the `(outcome_id,
bookmaker)` pairs one `LIMIT 1` at a time — each an index-only probe on
`ix_fos_outcome_bookmaker` — then take the newest row for each pair through a LATERAL, which
is a single-row backward read on the P127 index.

```
Nested Loop                                                    rows 256
  Recursive Union                                              rows 288
    Index Scan       ix_futures_outcomes_market_id             rows 32
      Index Only Scan ix_fos_outcome_bookmaker         1 row  x 32 loops
    WorkTable Scan
      Index Only Scan ix_fos_outcome_bookmaker         1 row  x 256 loops
  Index Scan  ix_futures_odds_snapshots_outcome_bookmaker_captured
                                                       1 row  x 256 loops
```

The last line is the index P127 bought, in the plan for the first time.

| | before | after |
|---|---|---|
| executed row query (market 86832) | 3,533 ms | **344 ms cold, 51–73 ms warm** |
| rows examined | 190,656 | **576 index seeks + 256 heap rows** |
| disk sort | 7,640 kB external merge | **none** |
| result rows | 256 | 256 |

### 4.1 Equivalence

There is no PostgreSQL in this sandbox and the recursive CTE / LATERAL / `unnest` this
statement is built from are not SQLite-expressible, so no local test can execute it.
Equivalence was therefore proved where the data is: old statement and new, run back to back
against production, results sorted and compared row for row.

```
mid=     86832 old= 256r 3532.6ms  new= 256r 343.9ms  IDENTICAL=True
mid=         1 old= 150r 1806.2ms  new= 150r 211.2ms  IDENTICAL=True
mid=  59835854 old=  27r   35.0ms  new=  27r  52.6ms  IDENTICAL=True
mid=  59835763 old=  10r   27.6ms  new=  10r  33.9ms  IDENTICAL=True
mid=  59835766 old=   9r   12.8ms  new=   9r  13.7ms  IDENTICAL=True
mid=  59835812 old=   8r   26.4ms  new=   8r  36.0ms  IDENTICAL=True
mid=  59835802 old=   4r   23.6ms  new=   4r  23.4ms  IDENTICAL=True
mid=  59837295 old=   3r   17.3ms  new=   3r  14.8ms  IDENTICAL=True
mid=  59836474 old=   2r   14.5ms  new=   2r  14.6ms  IDENTICAL=True
mid=  59838085 old=   2r   17.1ms  new=   2r  28.8ms  IDENTICAL=True
ALL IDENTICAL
```

**Small markets get marginally slower** — 35 ms → 53 ms at 27 outcomes, a few ms elsewhere —
and that is the honest shape of the trade. The recursion has a fixed cost the window
function does not, and it is repaid the moment a market has more snapshots than pairs. Those
markets were already inside the noise floor of a 300 ms round trip; the ones that were not
are the ones that move.

### 4.2 Not a time bound, and why

The obvious cheap fix is `captured_at >= now() - SOURCE_STALENESS_DAYS`, which would prune
most of the 190,656 rows. It is wrong. Sources older than seven days are **kept and flagged
`stale: true`** so the frontend can mute them and drop them from spread math — bounding the
scan would delete them from the page instead. `TestTheContractTheCallerDependsOn::
test_a_stale_source_is_flagged_not_omitted` is the guard that holds that line.

## 5. The three edits that would each undo this

All three read as improvements, which is why they are pinned by tests and by mutants rather
than left to review.

**`captured_at IS NOT NULL` — and this one has a citation in this repo, one commit away.**
`app.utils.latest_observation`, shipped by LAT-P147 yesterday, adds exactly this predicate
and documents it as load-bearing. It is right there and wrong here, and the inversion is
worth stating precisely:

- P147 replaces a `max()`. `max()` **skips** nulls; `ORDER BY captured_at DESC` is **NULLS
  FIRST**. Without the predicate the two forms disagree, so P147 must add it.
- This replaces a **window function**, which is NULLS FIRST too. A null-`captured_at` row
  wins its partition under the old statement, so it must win its pair under this one. Adding
  the predicate here *is* the behaviour change.

`captured_at` is genuinely nullable on production (`information_schema`, checked
2026-08-30) even though the model declares it non-optional, so this is reachable rather than
theoretical. Same clause, opposite correctness, two adjacent branches.

**`NULLS LAST`** — reads as defensive; P147 measured it at **19× slower**, because it stops
matching the index's own ordering and turns each one-row backward read into a Sort over the
whole pair.

**An `id` tiebreak** — reads as determinism, same mechanism, and buys nothing: production
carries **zero** `(outcome_id, bookmaker, captured_at)` groups with more than one row on this
market, and the window function it replaces broke ties arbitrarily anyway.

## 6. Gates

| gate | result |
|---|---|
| `tests/test_futures_source_breakdown_loose_scan_lat_p148.py` | 16 passed, exit 0 |
| `tests/integration/test_futures_detail_sources_cache_lat_p127.py` | 22 passed, exit 0 |
| `scripts/evals/futures_source_breakdown_loose_scan_mutations.py` | **16/16 killed**, exit 0 |
| `scripts/evals/scan_mutation_residue.py` | CLEAN, exit 0 |
| full backend suite | see `.claude/handoff/REPORT-LAT-P148.md` |

### 6.1 Two mutants survived the first battery run

Recorded because both were worth more than the fourteen that died.

**M-NOTERM** drops the recursive terminator, whose failure mode is a hung web dyno rather
than a wrong number. The test written to catch it split the SQL on `UNION ALL` and searched
everything after it — which also contains the **final select's** identical
`WHERE p.bookmaker IS NOT NULL`. Removing the terminator left that copy behind and the
assertion passed against the wrong half of the query. The slice now cuts at the LATERAL.

**M-WINDOWBACK** was not a hole in the suite: it was a mutant that did not mutate. Its first
form prepended a `-- restored --` comment to the CTE and called that "the window function is
back". Nothing about the statement changed, so nothing could kill it — that is not an
equivalent mutant, it is a broken one. Rewritten to genuinely resolve the pair with a window
function (answer-identical, scan-shaped) and killed.

### 6.2 A shared-`/tmp` hazard the harness works around

`_mutation_guard.MANIFEST_DIR` still defaults to `/tmp/bainluck_mutation_guard`, which every
checkout of this repo on this machine shares (#2330, unfixed on master). A battery that
crashes there can be "recovered" by the next lane's run and restore *its* live files from
*this* tree's backups. This harness repoints both the manifest dir and the backup dir to
paths derived from the worktree, before the guard is used.

## 7. What is parked, not done

- **`ANALYZE futures_odds_snapshots`** — `last_analyze` is NULL, `last_autoanalyze` is
  eight days old on a 196 M-row table, and the planner's estimate for the old query was 115×
  low. Not this bug's cause, and it needs an attended run against production. Appended to
  `PARKED-MEASUREMENTS.md`.
- **Route-order shadowing in `futures.py`** — `@router.get("/{market_id}")` is registered at
  line 2277, but `/cross-source-timeline` (2939) and `/groups` (3860) are registered after
  it. The path template has no `:int` convertor, so Starlette matches the single segment
  first and FastAPI then 422s on int coercion. Found while mapping the route; out of scope
  here, filed separately rather than fixed under a latency branch.
- **The route-level after-measurement** is post-deploy by definition. Section 4's numbers are
  the *query* measured on production; the served-wait number belongs to the Integrator's
  verification, and a read taken within five minutes of a release is not evidence.
