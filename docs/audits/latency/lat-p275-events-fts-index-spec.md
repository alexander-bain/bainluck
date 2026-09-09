# LAT-P275 step 1 — the attended `events` FTS index (#4140)

**Status:** awaiting an attended window. Gate is written and RED.
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

---

## Free-riding on the same attended window — a SEPARATE decision, needs its own yes

`events` carries **~143 MB of exactly duplicated trigram GIN**, confirmed present in the same
`pg_indexes` read:

| keep | drop (duplicate) |
|---|---|
| `ix_events_home_team_name_trgm` | `ix_events_home_trgm` |
| `ix_events_away_team_name_trgm` | `ix_events_away_trgm` |

Dropping the pair halves GIN write amplification on a continuously-written, ~437%-bloated table.

**This is deliberately NOT bundled with the index above.** It is a drop rather than an add, so it is
one-way enough to be Alex's own call, and it should be confirmed with a fresh scan-count read
immediately before running it rather than on the counts quoted in LAT-P275. Do not run it in the
same breath as the `CREATE`s.

---

## Step 2 is NOT in this branch, and not yet

The LAT-P140-style UNION split of `event_team_filter` does not ship in the same branch as this
index and **does not ship at all until the index is live and this gate is green** —
split-before-index makes the arm *worse* (the FTS half alone is 1.25-3.46 s).
