# LAT-P275 step 1 — the attended `events` FTS index (#4140)

**Status:** ✅ **DONE.** Alex ran both statements ~10:50am PT 2026-09-09; both indexes are live and
`indisvalid`. The after-gate is **GREEN on all three criteria** —
`docs/audits/latency/lat-p275-events-gate-after.json`. **Step 2 was then measured and REFUSED** —
see "Step 2" at the bottom, which is now the important section on this page.
**Ship:** the search dropdown stops stalling mid-word. **Pillar:** DISCOVER (Instant Answers).
**Run by:** Alex, attended, outside Alembic (ruling 131 + gotcha #31 — `CREATE INDEX CONCURRENTLY`
must never go in a migration; the Heroku release phase times out at ~5 min and took the site down
on May 22 doing exactly this).

---

## The block to paste

Both statements, in order. `CONCURRENTLY` means they do **not** lock writes, so the site keeps
serving while they build. Neither can run inside a transaction — paste them one at a time, not
wrapped in `BEGIN`.

```sql
-- ~2-6 min each on a ~234k-row, ~437%-bloated table. Site stays up.
CREATE INDEX CONCURRENTLY ix_events_fts_home
    ON events USING GIN (to_tsvector('english', coalesce(home_team_name, '')));

CREATE INDEX CONCURRENTLY ix_events_fts_away
    ON events USING GIN (to_tsvector('english', coalesce(away_team_name, '')));
```

### The undo line (D51 — a repair ships with its restore)

```sql
DROP INDEX CONCURRENTLY IF EXISTS ix_events_fts_home;
DROP INDEX CONCURRENTLY IF EXISTS ix_events_fts_away;
```

Dropping returns the database to exactly today's state: these indexes are **purely additive**, no
code reads them by name, and nothing behaves differently if they are absent. Verified on production
2026-09-08 — `events` carries 21 indexes and **not one contains `to_tsvector`**, so neither name
can collide and neither statement can replace something in use.

### If a build fails halfway

`CREATE INDEX CONCURRENTLY` can leave an `INVALID` index behind if it is interrupted. It is inert
(the planner ignores it) but it should be cleaned up:

```sql
SELECT c.relname FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE c.relname IN ('ix_events_fts_home','ix_events_fts_away') AND NOT i.indisvalid;
-- then, for anything it returns:
DROP INDEX CONCURRENTLY IF EXISTS <name>;
```

---

## 🔴 The expression must match EXACTLY, `coalesce` included

The two-arg `to_tsvector('english', coalesce(col, ''))` above is not a stylistic choice and must not
be "tidied":

* **`to_tsvector(x)` and `to_tsvector('english', x)` are DIFFERENT FUNCTIONS.** Only the two-arg
  form can use a two-arg expression index. LAT-P274 burned a whole cycle and handed another lane a
  **270x-wrong** number because a hand-written probe dropped the config argument and therefore read
  as "the index does nothing".
* **The `coalesce` is part of the indexed expression.** The route wraps every column in
  `coalesce(column, '')` (`_fts_filter`, `backend/app/routes/events.py:1517-1521`), and its config
  comes from `_SEARCH_TS_CONFIG_SQL` (`:1288`), which is `'english'`. An index on the bare column
  **builds successfully and is then silently never used** — the failure mode LAT-P086 caught in
  LAT-P085's proposed altnames DDL.

The gate below is what makes that undetectable-by-eye mistake detectable: it compiles its SQL from
the live ORM, so it cannot drift from what the route actually asks for.

---

## What this buys, and what it does not

`typeahead_search` builds its event predicate as `or_(fts_event_f, ilike_event_filter)`
(`routes/events.py:6057-6063`). The ILIKE half is servable by the existing trigram GINs; the FTS
half is servable by nothing, so **the planner abandons the GINs for the whole OR** and sequentially
scans `events` on every keystroke. #4140 measured `yank` at **127-263 ms with 234,575 rows removed
by the filter**, against an arm that could answer in ~2 ms.

**It does not change what the reader finds.** Measured on production 2026-09-08:

| term | rows the FTS half returns today |
|---|---|
| `yank`, `celt`, `dodg` (mid-word) | **0** — the half is pure cost, contributing nothing |
| `yankees` / `celtics` / `red sox` (whole word) | **301 / 185 / 326** — real recall, by stemming |

On a mid-word prefix `websearch_to_tsquery('english','yank')` simply does not match the lexeme
`yanke`. So today we seq-scan 234k rows to find nothing; afterwards we index-scan to find nothing.
Same answer, ~100x less work. The gate's criterion 3 pins that the id sets do not move.

The second row is the reason **the FTS half must not be deleted** as a cheaper "fix": on whole words
it reaches 301/185/326 rows that substring matching does not, because stemming matches "Yankee …"
for `yankees`. Both halves are load-bearing (LAT-P096 measured the same for the futures twin). Any
proposal to drop it needs a production recall census first.

---

## Verifying it worked

```bash
source ~/.claude/.env
python3 backend/scripts/gate_events_fts_index.py --label after \
    --out docs/audits/latency/lat-p275-events-gate-after.json
```

**Exit 0 = GREEN, exit 1 = RED. Any other exit is the harness failing, not a verdict** (gotcha #54).
Three criteria, all of which must pass:

1. **SHAPE (the one that cannot be faked by timing):** a `BitmapOr` over **both** new indexes, and
   **zero `Seq Scan` nodes**. One index of two is a FAIL — a structurally-mismatched expression
   index builds valid and is silently never used.
2. **BUDGET:** FTS median / control median ≤ **0.25**. The control is the same predicate on
   `home_team_normalized`, a column this DDL deliberately does not index, measured **interleaved in
   the same batch** so a host CPU excursion lands on both. An absolute-millisecond threshold was
   rejected: on the sibling teams gate it **already passed on a no-op**, because seq-scan cost swings
   ~6x within a single minute.
3. **SEMANTICS:** the id set for every term is unchanged from the pre-index capture.

**The RED is already banked** — `docs/audits/latency/lat-p275-events-gate-before.json`, run
2026-09-08 before any DDL:

```
yank      fts=3575.2ms ctrl=412.3ms ratio= 8.67  shape=MISSING:both  FAIL
yankees   fts=4405.0ms ctrl=371.7ms ratio=11.85  shape=MISSING:both  FAIL
celt      fts=5601.3ms ctrl=444.5ms ratio=12.60  shape=MISSING:both  FAIL
celtics   fts=2626.8ms ctrl=238.8ms ratio=11.00  shape=MISSING:both  FAIL
red sox   fts=2609.1ms ctrl=235.9ms ratio=11.06  shape=MISSING:both  FAIL
dodg      fts=2385.4ms ctrl=218.9ms ratio=10.90  shape=MISSING:both  FAIL
VERDICT: RED   (exit 1)
```

Those milliseconds are `count(*)` under `EXPLAIN ANALYZE` on a bloated table — a different quantity
from #4140's 127-263 ms, which timed the arm inside the real LIMITed query. Both are honest; it is
why the verdict rides on the ratio and the plan shape rather than on a millisecond budget.

### The GREEN, banked 2026-09-09 (`lat-p275-events-gate-after.json`)

```
yank      fts=   0.1ms ctrl=105.8ms ratio=0.00  shape=ok  sem=ok  n=  0(+0 since pin)  PASS
yankees   fts=   0.6ms ctrl=114.8ms ratio=0.01  shape=ok  sem=ok  n=301(+2 since pin)  PASS
celt      fts=   0.2ms ctrl=177.7ms ratio=0.00  shape=ok  sem=ok  n=  0(+0 since pin)  PASS
celtics   fts=   0.5ms ctrl=103.5ms ratio=0.00  shape=ok  sem=ok  n=185(+0 since pin)  PASS
red sox   fts=   0.8ms ctrl=105.9ms ratio=0.01  shape=ok  sem=ok  n=326(+2 since pin)  PASS
dodg      fts=   0.2ms ctrl=112.2ms ratio=0.00  shape=ok  sem=ok  n=  0(+0 since pin)  PASS
VERDICT: GREEN   (exit 0)
```

`yank` 3,575.2 ms → 0.1 ms. BitmapOr over both new indexes, zero Seq Scan, id sets unmoved.

#### Criterion 3 needed a population pin, and that is a lesson, not a footnote

The first after-run came back **RED on semantics** for `yankees` and `red sox` — and the index was
fine. `events` is written continuously, so the frozen id-set baseline had been overtaken by **four
MLB fixtures ingested that morning** (`created_at` 2026-09-09, `LOST=0` on both terms — every
baseline id was still there). `celtics`, out of season, did not move.

A criterion that compares a live table against a frozen capture **grades the calendar**: it goes RED
with age, stays RED, and teaches the next lane to wave its own gate through. So criterion 3 now pins
the population to the baseline's own capture instant (`_meta.pin_created_at_utc`, backfilled here to
`2026-09-09T01:02:55.806834` — the max `created_at` over all 790 baseline ids, with the first
post-baseline row landing at 06:02). That restores an **exact set equality** over the rows the
baseline actually captured, so it still catches a row the index hides *and* a row it invents, while
rows ingested since are counted and printed (`+2 since pin`) rather than graded.

Verified by mutation, not by reasoning: adding one phantom id to the `celtics` baseline makes the
gate print `sem=LOST:1,GAINED:0` and exit 1, with the five sibling terms still passing.

---

## Free-riding on the same attended window — a SEPARATE decision, needs its own yes

`events` carries **~143 MB of exactly duplicated trigram GIN**, confirmed present in the same
`pg_indexes` read:

🔴 **THIS TABLE WAS INVERTED AND IS CORRECTED HERE (2026-09-09).** As first written it said to keep
the `_team_name_trgm` pair and drop the short-name pair — which is backwards, and would have dropped
the two indexes doing essentially all the work. Fresh `pg_stat_user_indexes` read, 2026-09-09:

| keep | scans | drop (duplicate) | scans |
|---|---|---|---|
| `ix_events_home_trgm` | **3,014,900** | `ix_events_home_team_name_trgm` | 21,928 |
| `ix_events_away_trgm` | **2,986,521** | `ix_events_away_team_name_trgm` | 50,367 |

The pair to keep is also the correctly-tuned one: three of the four carry
`WITH (gin_pending_list_limit='256')` and `ix_events_home_team_name_trgm` is the lone exception, so
the original table would have dropped a tuned index in favour of an untuned one **and** moved 3M
scans onto it. They are otherwise identical (`gin (col gin_trgm_ops)`), so either name can serve —
which is exactly why the scan counts, not the names, decide.

Dropping the pair halves GIN write amplification on a continuously-written, ~437%-bloated table.

**This is deliberately NOT bundled with the index above.** It is a drop rather than an add, so it is
one-way enough to be Alex's own call, and it should be confirmed with a fresh scan-count read
immediately before running it rather than on the counts quoted in LAT-P275. Do not run it in the
same breath as the `CREATE`s.

---

## Step 2 — built, measured, and REFUSED (2026-09-09)

The precondition was met — index live, gate GREEN — so the LAT-P140-style UNION split of
`event_team_filter` was built and measured against production before shipping. **It is a
regression, and it does not ship.** The code was written and reverted; what survives is this
section and the numbers.

### It is slower, on 7 of 9 terms

Both forms compiled from the live ORM, interleaved, 3 rounds, `EXPLAIN ANALYZE`, **with the route's
real scope conditions** (`status IN ('live','scheduled')`, the 7-day `commence_time` window,
`not_a_proven_duplicate()`):

| term | OR (ships today) | UNION split | | term | OR | UNION |
|---|---|---|---|---|---|---|
| `yank` | 16.2 ms | 18.8 ms | | `soccer` | 19.5 ms | 24.0 ms |
| `yankees` | 18.0 ms | 38.0 ms | | `nfl` | 19.1 ms | 22.6 ms |
| `red sox` | **19.4 ms** | **96.1 ms** | | `lakers` | 53.5 ms | 66.4 ms |
| `chi` | 40.8 ms | 62.6 ms | | `celtics` | 43.4 ms | 34.2 ms |
| `dodg` | 27.0 ms | 22.4 ms | | | | |

Worst case **53.5 → 96.1 ms**, median **19.5 → 34.2 ms**. Read the worst case: on the futures twin
the split was right precisely because the worst case *fell* 14x. Here it nearly doubles.

Recall is unaffected either way — set-identical on 10/10 terms by `count(*)` + server-side `md5` of
the ORDER-BY-id id set, 146 rows compared, 9 terms non-empty. The split is not wrong, just slower.

### Why — and this corrects #4140's premise

**Zero `Seq Scan` nodes in either form.** The scoped query never seq-scans `events` and drives off
`ix_events_status_commence`, not off any text index: `status IN ('live','scheduled')` AND a 7-day
`commence_time` window is already a tight candidate set, and the text predicate is a cheap recheck
over it. Splitting into arms therefore *multiplies the driving scan* — three arms each re-walk the
same scope index, then pay an `IN` semi-join to union the results. No arrangement of the UNION fixes
that, because the scope, not the text half, is what drives the plan.

**Proved by counterfactual, not inferred.** Re-running the OR with a deliberately unindexable FTS
half — one-argument `to_tsvector(x)`, which cannot use a two-argument expression index (the #4130
trap, used on purpose here) — reproduces the pre-index world:

| term | indexed FTS half | unindexable FTS half | Seq Scans | driving index |
|---|---|---|---|---|
| `yank` | 84.3 ms | 99.1 ms | 0 | `ix_events_status_commence` |
| `red sox` | 74.8 ms | 56.5 ms | 0 | `ix_events_status_commence` |
| `chi` | 50.6 ms | 47.1 ms | 0 | `ix_events_status_commence` |
| `nfl` | 38.4 ms | 55.7 ms | 0 | `ix_events_status_commence` |

Same speed, same plan, no seq scan — **with the FTS half unindexable.** So for `/typeahead` the OR
was never the problem and the index changes nothing.

#4140's headline number (`yank` 127-263 ms, 234,575 rows removed, Seq Scan) is real but it measured
the **recall arm on its own, without the route's scope conditions** — a query `/typeahead` never
runs. Live production `events_query` sampled the same day: 35-89 ms median across eight terms.

### What is actually true after all this

* The index is **live, valid, additive and GREEN**, and it does what its gate says: the *unscoped*
  events FTS arm goes 3,575 ms → 0.1 ms. Nothing about that is retracted, and it costs nothing to
  keep. Any surface that runs that arm unscoped now has it indexed.
* `/typeahead` was not the surface paying for it, so **`/typeahead` does not get measurably faster**
  from either step. The honest ship from LAT-P275/P288 is the index and the gate, not a latency win
  on the dropdown.
* **Do not re-open the UNION split for this arm** without first showing that the driving index has
  changed. The measurement to repeat is the counterfactual table above, not the bare-arm timing.
* The general lesson, which is the one worth carrying: **measure the arm inside the query that
  actually runs.** A recall predicate timed without its scope is a different query, and it can be
  three orders of magnitude off in the direction that invents work.
