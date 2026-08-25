# LAT-P086 — the three `teams` FTS indexes: an ATTENDED psql runbook for Alex

**Status:** SPEC. Written by the latency lane; **not run by it.**
**Addressee:** Alex, at an attended `psql` prompt, handed over by Fable with the next attended batch.
**Authority:** Fable directive 2026-08-24 item 0b, banked as
`docs/rulings/131-index-ddl-with-no-code-half-runs-attended-outside-alembic.md`.
**Explicitly NOT:** an Alembic migration (gotcha #31), and not a `heroku run:detached` one-off —
`CONCURRENTLY`'s wait phases need an operator who can see them (ruling 131 §"What attended means").
**Migration slot:** `none`, declared.
**Code half:** there is none. That is the property that qualifies this for ruling 131 — the route
already emits these predicates unmodified, so rollback is one `DROP INDEX CONCURRENTLY` with
nothing to redeploy.
**Why Alex and not an agent:** TCP 5432 egress is blocked from the agent sandbox, so no session
here can hold a `psql` connection at all. Run it with a leading `!` in a Claude Code prompt if you
want the output captured in-session.

**Measured:** production, 2026-08-24, PostgreSQL 17.10 (Heroku, Standard 0). Every number below is
a read.

---

## 🔴 0. The LAT-P085 proposal's THIRD index was wrong and would never have been used

`docs/audits/latency/lat-p085-search-decomposition.md` proposed:

```sql
-- DO NOT RUN — this is the WRONG form, kept here as the record
CREATE INDEX CONCURRENTLY ix_teams_fts_altnames ON teams
  USING gin (to_tsvector('english', coalesce(alternate_names::text, '')));
```

`_build_team_search_filter` (`app/routes/events.py:1566-1578`) builds its third arm with
`cast(Team.alternate_names, String)`, which SQLAlchemy renders `CAST(... AS VARCHAR)`, not `::text`.
Postgres canonicalises the two differently, and an expression index is matched **structurally**, so
the proposed index is not a candidate for the query it was written for.

Deparsed by the planner on production this window (`EXPLAIN`, plan only, `Filter` line):

| | canonical expression |
|---|---|
| what the route emits | `to_tsvector('english'::regconfig, (COALESCE((alternate_names)::character varying, ''::character varying))::text)` |
| what LAT-P085 proposed | `to_tsvector('english'::regconfig, COALESCE((alternate_names)::text, ''::text))` |

Different parse trees. The index would have built cleanly, reported `indisvalid = true`, cost disk
and a write tax on every `teams` write, and returned nothing — the LAT-P058 shape exactly (a
verification step that cannot pass), except that here it is the *lever* that cannot fire. §2's form
below was re-deparsed and is **byte-identical** to the route's arm.

The first two arms are unaffected: `coalesce(name, '')` and `coalesce(abbreviation, '')` already
canonicalise to `(COALESCE(name, ''::character varying))::text`, because `name` and `abbreviation`
are `character varying` and the two-argument `to_tsvector(regconfig, text)` supplies the same outer
coercion in an index definition as it does in a `WHERE`. Verified by deparsing both forms and
diffing the `Filter` strings.

**Still three indexes, not one `setweight` vector.** LAT-P085's reason stands: a combined vector
would let `'red' & 'sox'` match across columns and widen recall, which changes results rather than
speed.

---

## 1. Preconditions — read 2026-08-24, re-read at the prompt

| # | precondition | measured now | abort if |
|---|---|---|---|
| P1 | disk headroom | database **53 GB**; the three GINs are ~3–6 MB | free space under 2 GB |
| P2 | no existing / INVALID index of these names | **none present** — `teams` carries exactly `ix_teams_alt_names` (264 kB), `ix_teams_espn_id` (432 kB), `ix_teams_name_trgm` (2312 kB), `ix_teams_slug` (680 kB), `ix_teams_statpal_team_id` (360 kB), `teams_pkey` (656 kB), `uq_teams_slug` (656 kB), all `indisvalid=true` | any `ix_teams_fts_*` row comes back — drop it first, `CREATE INDEX CONCURRENTLY` fails on a duplicate name |
| P3 | no long-running transaction | checked at the prompt (§2 step 0) | any transaction older than 60 s — `CONCURRENTLY` waits for **every** transaction that can see the table, twice |
| P4 | table size | **9,240 rows**, 9,248 kB heap, 15 MB total | — (this is small; expect seconds, not minutes) |

**Timing.** `teams` is not on a hot write path, so the 6-hourly `backfill_winners` window that
constrains `futures_markets` DDL does not bind here. Still avoid `hour % 6 == 0`, minutes 10–50, so
P3 is likely to be satisfiable on the first read.

**`lock_timeout = '60s'`, not `'5s'`.** LAT-P058's execution record: `5s` left all three indexes
INVALID after *completed* builds died in `CONCURRENTLY`'s second wait phase, and an INVALID index is
never read but IS maintained on every write.

---

## 2. THE COMMAND BLOCK — copy-paste, in order

```sql
-- ── session GUCs ────────────────────────────────────────────────────────────
SET statement_timeout   = 0;        -- CONCURRENTLY must not be cut off mid-build
SET lock_timeout        = '60s';    -- '5s' FAILS in this database (LAT-P058)
SET maintenance_work_mem = '128MB';

-- ── step 0: precondition P3 — abort if this returns a row ───────────────────
SELECT pid, now() - xact_start AS age, state, left(query, 80) AS q
  FROM pg_stat_activity
 WHERE xact_start IS NOT NULL
   AND now() - xact_start > interval '60 seconds'
   AND pid <> pg_backend_pid()
 ORDER BY age DESC;

-- ── step 0b: precondition P2 — abort if this returns a row ──────────────────
SELECT c.relname, i.indisvalid, i.indisready
  FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE i.indrelid = 'teams'::regclass AND c.relname LIKE 'ix_teams_fts%';

-- ── step 1 of 3 ─────────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY ix_teams_fts_name ON teams
  USING gin (to_tsvector('english', (COALESCE(name, ''::character varying))::text));

-- ── step 2 of 3 ─────────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY ix_teams_fts_abbrev ON teams
  USING gin (to_tsvector('english', (COALESCE(abbreviation, ''::character varying))::text));

-- ── step 3 of 3 — NOTE the ::character varying, see §0 ──────────────────────
CREATE INDEX CONCURRENTLY ix_teams_fts_altnames ON teams
  USING gin (to_tsvector('english', (COALESCE((alternate_names)::character varying, ''::character varying))::text));
```

Run the three `CREATE`s **one at a time**, reading §3 between each. If one errors or is
interrupted, `DROP INDEX CONCURRENTLY <name>;` before retrying it — a half-built index holds its
name.

---

## 3. POST-CREATE VERIFICATION — both halves are required

Ruling 131: the verification query is not "did it error". A valid index the planner declines is the
same non-event as no index.

### 3a. The catalog says VALID

```sql
SELECT c.relname,
       i.indisvalid,
       i.indisready,
       pg_size_pretty(pg_relation_size(c.oid)) AS size,
       pg_get_expr(i.indexprs, i.indrelid)     AS indexed_expression
  FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid
 WHERE i.indrelid = 'teams'::regclass AND c.relname LIKE 'ix_teams_fts%'
 ORDER BY c.relname;
```

Expected: **three rows**, `indisvalid = t`, `indisready = t`, roughly 1–3 MB each.
Read it as — `indisready=false` → phase 1 unfinished (and such an index is inert, not maintained);
`indisready=true, indisvalid=false` → built and in a wait phase, **or dead**; `indisvalid=true` →
done. Anything other than three valid rows: stop and report, do not proceed to 3b.

`indexed_expression` is printed because §0 is a live hazard — it is the deparsed form, and each row
must match the corresponding arm of 3b's `Filter` string character for character.

### 3b. The planner USES it — the half that ruling 131 says is not optional

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT teams.id FROM teams
 WHERE to_tsvector('english', (COALESCE(name, ''::character varying))::text)
         @@ websearch_to_tsquery('english', 'red sox')
    OR to_tsvector('english', (COALESCE(abbreviation, ''::character varying))::text)
         @@ websearch_to_tsquery('english', 'red sox')
    OR to_tsvector('english', (COALESCE((alternate_names)::character varying, ''::character varying))::text)
         @@ websearch_to_tsquery('english', 'red sox');
```

**PASS = plan SHAPE, never a cost number** (LAT-P058 CORRECTION 2: a cost bar inverted silently
once already, when one indexed branch of two dragged the total under it while the expensive branch
still Seq Scanned). The required shape is a `BitmapOr` over **three** `Bitmap Index Scan` nodes,
one per `ix_teams_fts_*`. Two out of three is a FAIL and points straight back at §0.

Baseline to beat, measured this window on the identical predicate: a single `Seq Scan on teams`,
total cost **2592.82**, no index involvement.

If the shape is still a Seq Scan, re-run once with `SET enable_seqscan = off;` before the `EXPLAIN`
(and `RESET enable_seqscan;` after). That distinguishes the two causes, which print the same
otherwise: *the index cannot serve this predicate* (§0 again — expression mismatch, the shape stays
a Seq Scan even with seqscan off, or uses a different index) versus *the index can serve it but the
planner prefers a 1,156-page scan* (shape flips to `BitmapOr`, which is a pass on usability and a
note about table size, not a defect).

### 3c. An hour later — is it being chosen by real traffic

```sql
SELECT indexrelname, idx_scan, idx_tup_read
  FROM pg_stat_all_indexes
 WHERE relname = 'teams' AND indexrelname LIKE 'ix_teams_fts%';
```

**`indexrelname`, not `relname`** — in these views `relname` is the TABLE name, and the natural
mistake returns zero rows forever (LAT-P058 CORRECTION 1). Zero rows is not `idx_scan = 0`
(gotcha #53).

---

## 4. Rollback

```sql
DROP INDEX CONCURRENTLY IF EXISTS ix_teams_fts_name;
DROP INDEX CONCURRENTLY IF EXISTS ix_teams_fts_abbrev;
DROP INDEX CONCURRENTLY IF EXISTS ix_teams_fts_altnames;
```

Instant, at any hour, no deploy, no code revert. That is the whole reason ruling 131 lets this out
of the migration chain.

---

## 5. What this is predicted to buy, and what it is NOT

From `lat-p085-search-decomposition.md`, restated so nobody grades it against the wrong bar:

| | before (measured) | predicted after |
|---|---|---|
| teams arm | p50 **159 ms** | single-digit ms |
| server total | p50 **464 ms** | ~305 ms |
| wall (client) | p50 **821.7 ms** | ~660 ms |

**This does not clear the 500 ms search bar and was never going to.** The transport floor alone is
**292.8 ms**. The teams arm is 40.4% of server time, so removing essentially all of it leaves the
other 59.6% and the network. The pre-registered red for LAT-P085 stays red and stays
pre-registered until this DDL has run and 3b passes — writing the command is not running it
(ruling 131, "What it binds", clause 4).

---

## 6. Scope note — this serves `/api/events/search`, not `/typeahead`

`_build_team_search_filter` is the FTS gate on the dedicated Teams surface. The typeahead path
(`events.py:4188-4210`) matches teams with `_build_expanded_ilike`, an OR of substring `ILIKE`s,
which these GINs cannot serve. Typeahead's own p50 (232.0 ms, 6.2% cold — LAT-P084 ruling 127) is a
separate lever and must not be graded against this one.

---

## 🔴 7. LAT-P087 CORRECTION — the pre-registered BUDGET criterion passed on a no-op

`backend/scripts/gate_teams_fts_index.py` is now the executable form of §3b, and it exists because
the criterion this runbook was about to be graded against **was already satisfied before the DDL
ran**.

LAT-P085 pre-registered three criteria. The second was *"Budget — exec_ms < 50 on all four"*,
banked against a measured red of **386-485 ms**. Re-measured 2026-08-24 with **no `ix_teams_fts_*`
present anywhere in production** (verified against `pg_indexes`):

```
yankees 46.6ms   celtics 54.3ms   red sox ~50ms   world cup ~47ms
```

Three hand-run `CREATE INDEX CONCURRENTLY` statements were forty minutes from being declared a
success by a threshold that a **completely unindexed database also clears**. That is the worst
thing a gate can do: not report a wrong number, but report a correct number about the wrong thing.

It is not a code change (`git diff b5c2a750..ea07f81e` on `events.py` touches only typeahead
`_record_trending`, #2117) and not a data change. It is **load**. The predicate is a sequential scan
whose cost is per-row `to_tsvector` CPU, and host CPU contention moves it ~6x inside one minute:

```
fts_ms:  61.7  60.4  57.9  63.3  340.9  323.6        (5.9x spread, ~90 seconds)
```

71 days of `pg_stat_statements` agrees with neither reading: two route variants at 3,161 calls /
mean 106.2 ms (sd 84.6) and 838 calls / mean 230.5 ms (sd 166.6). **Both of LAT-P085's numbers were
honest readings of a quantity that does not hold still**, and the same is true of the 159 ms teams
arm in §5's table — read that row as a sample, not a constant.

### The replacement: a CPU-matched control ratio

The gate measures a control **in the same interleaved batch, seconds apart, on the same table**:

```sql
to_tsvector('english', coalesce(slug, '')) @@ websearch_to_tsquery('english', <term>)
```

`slug` is deliberately **not** one of the three indexed columns, so this DDL cannot serve it, while
it is the same shape of work — one tsvector per row over all ~9,240 rows — so it absorbs the same
contention. Across the 5.9x excursion above the ratio held **0.87 - 1.31**; the full red run below,
which happened to catch a second excursion, held **1.05 - 1.57** while absolute times swung
160 → 423 ms.

A cheap control does **not** work and was tried and rejected: `count(*) FROM teams WHERE id > 0`
stays flat at ~5.5 ms straight through the excursion, because fixed overhead dominates it. *A
control only cancels the noise it shares.*

Threshold **0.25** — a 4x+ collapse from today's ~1.1, against a post-index expectation near 0.05.

### Criterion 1 is unchanged and is still the one that matters

A ratio is a budget; only the plan proves the planner *uses* the index. `BitmapOr` over **three**
`Bitmap Index Scan` nodes, two of three is a FAIL — §3b, unchanged. The gate's SQL is **compiled
from the live ORM** via `_build_team_search_filter`, never hand-copied, so if the route's cast ever
changes the gate's SQL changes with it and the shape check fails honestly. A pasted predicate would
keep passing against an index the route no longer matches — which is precisely §0's defect.

### Recorded red, 2026-08-24 22:18 UTC

`docs/audits/latency/lat-p087-teams-fts-gate-before.json`, `EXIT CODE: 1`:

```
  yankees          fts=  389.4ms ctrl=  285.0ms ratio= 1.37  shape=MISSING all three  sem=ok  FAIL
  celtics          fts=  423.0ms ctrl=  296.9ms ratio= 1.42  shape=MISSING all three  sem=ok  FAIL
  red sox          fts=  389.4ms ctrl=  293.9ms ratio= 1.32  shape=MISSING all three  sem=ok  FAIL
  world cup        fts=  194.5ms ctrl=  123.6ms ratio= 1.57  shape=MISSING all three  sem=ok  FAIL
  stanley cup      fts=  196.2ms ctrl=  187.4ms ratio= 1.05  shape=MISSING all three  sem=ok  FAIL
  nba champion     fts=  161.2ms ctrl=  143.4ms ratio= 1.12  shape=MISSING all three  sem=ok  FAIL
  masters winner   fts=  160.7ms ctrl=  137.4ms ratio= 1.17  shape=MISSING all three  sem=ok  FAIL
  world series     fts=  163.3ms ctrl=  124.1ms ratio= 1.32  shape=MISSING all three  sem=ok  FAIL

  criterion 1 SHAPE      : FAIL on all 8
  criterion 2 BUDGET     : FAIL on all 8
  criterion 3 SEMANTICS  : PASS
VERDICT: RED
```

Semantics PASS means `lat-p085-teams-red.json` is still a valid before — the id sets have not
drifted, so a post-DDL change in them is the index changing behaviour, not the corpus moving.

### After the attended batch

```bash
source ~/.claude/.env
python3 backend/scripts/gate_teams_fts_index.py --label after \
  --out docs/audits/latency/lat-p087-teams-fts-gate-after.json
echo "EXIT CODE: $?"
```

Same command, unedited. `0` = GREEN. `1` = RED, a real verdict. **Anything else is the harness
failing to run and is not a verdict at all** (gotcha #54's amendment) — `2` is what it exits when
`ADMIN_TOKEN` is unset or `analyze` did not return an `Execution Time`.

`backend/tests/test_gate_teams_fts_index.py` (14 tests) pins the corrected criterion: it fails if an
absolute-millisecond budget is reintroduced, if the threshold rises above a third of the observed
unindexed floor, if the control moves onto an indexed column, or if the altnames cast drifts off
`CAST(... AS VARCHAR)`.
