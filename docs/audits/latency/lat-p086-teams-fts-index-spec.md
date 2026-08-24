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
