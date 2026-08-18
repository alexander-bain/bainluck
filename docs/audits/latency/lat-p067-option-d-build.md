# LAT-P067 — Option D: what was built, what was deliberately NOT built, and the D3 correction

**Written:** 2026-08-18 PDT, latency lane cycle 39, `pid:64040`, branch `program/latency-60`
stacked on `program/latency-59` @ `0eabea46`.
**Slot authority:** `.claude/handoff/MIGRATION-SLOT-OPTION-D.md` — integrator-owned, durable,
`status: ASSIGNED`, `assigned_by: INT-084`.

---

## §1 — The precondition finally held, and that is the whole reason this window built it

Three consecutive windows (LAT-P063, P065, P066) refused to build Option D, each recording the same
reason: **PROGRAM-LANES invariant 5 is unconditional — no slot, no migration** — and the slot
existed only as prose inside `PROGRAM-LATENCY-NEXT.md`, which is *latency-owned and rotates*.
LAT-P065 counted **14 handoff files mentioning "Option D", every one a latency-lane file, zero
Integrator-owned.**

INT-084 wrote the artifact and said plainly that the fault was the Integrator's, not the lane's:
*"An assignment that lives only in the requester's own rotating file has not been made; it has been
mentioned."* That is the correct reading, and the refusals were correct. **The artifact IS the
assignment**, and it now exists, so this window built against it.

---

## §2 — The four slot conditions, each honoured AND each guarded by a test

The slot file's own warning is that the failure mode is *"a later window that only reads the summary
line"* helpfully folding the GIN back into the migration. A docstring does not survive that. A test
does.

| # | condition | how it is honoured | the guard |
|---|---|---|---|
| **1** | Table-only migration | `CREATE TABLE typeahead_index` + 2 small btrees, nothing else | `test_the_migration_moves_no_data` |
| **2** | ~90 MB trigram GIN built OUT OF BAND | not in the migration; DDL handed to Alex (§5) | `test_the_migration_creates_no_gin_index` |
| **3** | ~380 k backfill is a TASK | `rebuild_typeahead_index`, bounded + resumable | the task exists; the migration guard above forbids the alternative |
| **4** | revision id ≤ 32 chars | `add_typeahead_index` = 20 chars | `test_the_migration_revision_id_is_within_alembic_s_limit` |

Condition 2's guard needed three drafts, and the failures are worth recording because both are
guard-design traps rather than typos:

1. **Substring matching** — `"gin" not in text` fired on `sa.BigInteger()`. A guard that fails on a
   perfectly correct migration gets deleted by the next person, which would leave condition 2
   unguarded. That is a worse outcome than not writing it.
2. **Matching the whole file** — a word-boundary regex over the raw text then hit the code comment
   that *explains why the GIN is not here*. The prose is deliberate and useful.

The guard now reads **tokenised source with comments and string literals stripped**, so it can tell
"this migration builds a GIN" from "this migration explains why it does not".

**Mutation-proved, exit code 1 both times:** folding a `postgresql_using="gin"` index into
`upgrade()` fails the guard; removing the builder from `HEAVY_TASKS` fails the routing guard.

---

## §3 — D3: the sizing model is CORRECTED against my own registered sketch, before it is graded

`lat-p063-option-d-mechanism-and-prediction.md` sized the table at **~120 B/row ⇒ ~46 MB heap**.
That was a sketch of a schema that did not exist yet. The schema now exists and it is wider:

| | sketch | actual |
|---|---|---|
| bytes/row | ~120 B | **~177 B** |
| heap @ ~380 k rows | ~46 MB | **~67 MB** |
| + PK btree | — | ~10 MB |
| + unique btree | — | ~20 MB |
| + out-of-band GIN | ~90 MB | ~90 MB |
| **total** | ~140 MB | **~187 MB** |

**D3's registered bar is < 200 MB, HALT above 350 MB. It still passes — with ~13 MB of margin
instead of ~60.** That is stated here, in advance, so the D3 grading *carries* the correction rather
than discovering it and having to decide in the moment whether ~187 MB is a pass. It is a pass. The
halt threshold is untouched at 350 MB.

Two width decisions already bought most of the overrun back, and both are pinned in the model
docstring so a later "cleanup" cannot quietly undo them:

- **`content_hash` is a `BIGINT`, not a 64-char sha256 hex.** The hex would have cost 64 B/row =
  **24 MB** — more than a third of the heap of a table whose entire justification is heap width.
- **`rank_hint` is `REAL` (4 B), not double.** It is a ranking nudge, never an arithmetic result.

The signedness is not a detail: PostgreSQL `BIGINT` is signed, so an unsigned 64-bit digest
overflows on insert for **half of all inputs**. Frequent enough to look like corruption, rare enough
to survive a three-row fixture — so the test asserts over 500 spread inputs, not one.

---

## §4 — What was deliberately NOT built: the read path

**Nothing reads `typeahead_index`. That is a registered gate, not an unfinished job.**

D3's own halt language is explicit: *"> 350 MB ⇒ the sizing model is wrong … **re-derive before
building the read path** — do not proceed on 'it is still smaller than 688'."* D3 cannot be measured
until the table exists and is populated in production. Building the read path this window would have
been building **through a halt gate this lane registered itself** — and the slot artifact says the
same thing from the other side: *"This does not pre-approve the read-path cutover. The slot covers
the table; D1/D2/D3/D4 govern whether anything reads from it."*

The sequencing that follows from the registrations, rather than from convenience:

1. **This window** — table + builder + sentinel ship.
2. **Deploy + one-off dyno backfill** (§5) → **D3 measurable** via `pg_relation_size`.
3. **D3 passes** → build the read path behind a flag, with ruling 076's dated deletion attached.
4. **D1 + D2** → the 8-query never-warmed arm and the 46 armed gold probes.

`/api/events/typeahead` is a ~700-line route inside a 10,660-line file. Cutting it over is its own
queue, and a half-cutover behind a flag nobody may flip is precisely the shape ruling 076 was banked
against this month.

---

## §5 — THE ALEX ACTION, verbatim. The feature sits dark without it.

`psql` / TCP 5432 egress is blocked from every agent session, so **no lane can run
`CREATE INDEX CONCURRENTLY` itself.** The slot file flags this as the fifth thing, and as the one
that sinks the feature if missed: the migration lands, the table is created empty-and-unindexed, the
backfill fills it, and the read path is then **slower than the trigram surface it replaces** — which
is #1866's whole history (gotcha #53: an instrument reporting success while doing nothing).

**Run AFTER the deploy and AFTER the backfill in §6.** Both statements are idempotent.

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_typeahead_index_search_trgm
  ON typeahead_index USING gin (search_text gin_trgm_ops);
```

Then the D3 read, which is the measurement the whole sequence gates on:

```sql
SELECT pg_size_pretty(pg_relation_size('typeahead_index'))                AS heap,
       pg_size_pretty(pg_indexes_size('typeahead_index'))                 AS indexes,
       pg_size_pretty(pg_total_relation_size('typeahead_index'))          AS total,
       (SELECT count(*) FROM typeahead_index)                             AS rows;
```

- Run via the `!` prefix in an Alex session, or `heroku pg:psql -a bainluck`.
- **Never in the release phase / never in a migration** — gotcha #31, the May 22 outage verbatim.
- **Blocks** the D1 read-path cutover. Do not flip anything before this returns.

---

## §6 — The initial fill (one-off dyno, condition 3)

```
heroku run:detached --size=standard-2x -a bainluck -- \
  python3 -c "from app.tasks import rebuild_typeahead_index as t; \
              print(t.apply(kwargs={'budget_seconds': 1500}).get())"
```

`run:detached` is not optional: a non-detached `heroku run` **silently fails to execute** in this
sandbox (gotcha #48). Verify by census, never by stdout:

```sql
SELECT entity_type, count(*), max(refreshed_at) FROM typeahead_index GROUP BY 1 ORDER BY 1;
```

The task is resumable, so repeat until `terminal == "complete"`. A `partial` is not a failure — it
is the budget doing its job — and it is recorded as NOT-GREEN precisely so "the sweep is behind"
cannot be mistaken for "the sweep is done".

---

## §7 — D4 ships in the same commit, and the reason is not process hygiene

`typeahead_index` is a **second copy of truth**. #1866 has already produced three instruments that
reported success while doing nothing:

- a trade backfill recording SUCCESS every 6 h for ten weeks while recovering nothing (gotcha #53),
- a warmer whose `fresh` skip branch could never fire,
- two tests that stayed green while asserting a model production had already refuted.

A denormalised index that silently goes stale is **worse than the slow query it replaces**, because
the slow query was at least correct. So:

- `typeahead_index_sentinel` re-projects sampled live sources and compares `content_hash`.
- Both tasks are enrolled in `ENFORCED_TASKS` **with real terminals** — enrolment without a
  `terminal` is a no-op that still reads GREEN.
- Drift above **2 %** ⇒ `terminal: failed`, loudly not-GREEN.
- An **empty** index ⇒ `no_work`, not 100 % drift. An alarm that screams through the entire initial
  build is an alarm nobody reads — the retired grid health score, verbatim.
- The threshold is **not zero** and is inclusive, both deliberately, and both pinned by a boundary
  test so a later reader does not "fix" them in either direction.

The detector is **pure** (`compare_projections`) so D4's "detects an injected drift" requirement is
provable without a database — which matters concretely here, because there is no local Postgres in
this sandbox, so a DB-only proof would be a proof that never runs.

**Registered for the sentinel's first production reads:** the first sentinel run after the table
exists but before the backfill completes should report `no_work` / `index_empty`. Its first run
after a completed backfill should report `drift_rate == 0.0`. **A nonzero steady-state drift on a
settled pool HALTS the read path** (D4's own language) — it would mean the projections and the
sources disagree, which is a recall bug, not a tuning parameter.

---

## §8 — Queue placement, with the arithmetic rather than the habit

Both tasks go on `heavy`, not `background`.

`background` is the queue #1609 proved has **~one effective slot**, and whose depth read **3,014** at
this window's Phase 0 — against **418** at LAT-P065's baseline and **1,030** at LAT-P066's. A new
latency-tolerant multi-minute resident belongs there least of all; putting it there would re-create
the exact starvation `-59` cures, on the very queue the cure is about.

The added load on `heavy` is bounded, small, and stated so it can be checked rather than trusted:

| task | cadence | cap | share of ONE of heavy's two slots |
|---|---|---|---|
| `rebuild_typeahead_index` | :23 / :53 | 90 s budget (150 s soft / 180 s hard) | **~2.5 %** |
| `typeahead_index_sentinel` | daily 07:50 UTC | ~5 s detect-only | negligible |

:23/:53 is chosen, not default: it is clear of `prediction_market_match` (:05/:20/:35/:50) and of
`precompute_calibration_main` (:15) — between them the two things that can hold both heavy slots.
07:50 is **after** the 07:45 settled sentinel, so nothing lands inside #233's protected 07:10–07:45
window. Both are pinned by tests, because a cadence chosen for a reason and then edited without it
is just a number.

Every limit sits under the **300 s global hard `task_time_limit`**, which is a SIGKILL recorded as
`no_data` rather than as a failure. The **inner** op is bounded separately at 25 s/page — bounding
only the loop boundary is the `project_budget_guard_inner_op` mistake, and a task can honour a 90 s
budget at every check and still be killed inside one page.
