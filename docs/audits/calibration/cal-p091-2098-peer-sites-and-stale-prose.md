# CAL-P091 — #2098 sites two and three, and the prose that still described the defect

*Calibration lane, window `pid:33826-cal-p091`, 2026-08-24, on the Fable directive of the same
day (pasted and reviewed by Alex). Branch `program/calibration-89`, stacked on
`program/calibration-88`.*

This is the follow-on `cal-p090-2098-source-scope-fix.md` §4 recommended: *"a follow-on queue
item covering both, carrying ruling 125 as its authority and needing no new judgment."* No new
judgment was needed and none was taken.

---

## 1. What shipped

**Ruling 125** — *a join that can DELETE a row must carry every dimension that identifies the
row.* CAL-P090 applied it to the producer. The same three-line pair was copied twice more:

| # | file | what it is |
|---|---|---|
| 2 | `backend/app/routes/admin_data_quality.py` | `GET /api/admin/calibration-data` — the endpoint whose job is to **audit** the published population |
| 3 | `backend/scripts/audit_golf_hockey_calibration.py` | the golf/hockey attribution audit, whose docstring claims to replicate "the EXACT inclusion logic" of the public curve |

Both now read:

```sql
mode_prices AS (
    SELECT vm_id, source, adj_opening_probability AS mode_price   -- + source
    FROM ranked_outcomes
    WHERE is_multi AND eligible >= 3
    GROUP BY vm_id, source, adj_opening_probability, eligible     -- + source
    HAVING COUNT(*) > GREATEST(eligible * 0.5, 2)
)
...
LEFT JOIN mode_prices mp
  ON mp.vm_id = ro.vm_id
  AND mp.source = ro.source                                       -- the join conjunct
  AND mp.mode_price = ro.adj_opening_probability
```

**Three lines, not two.** `mode_prices` must also PROJECT `source`, or the new conjunct has
nothing to join on. Nothing else in either statement moved.

### The disagreement this closes, stated as the directive requires

**Until this branch lands, `GET /api/admin/calibration-data` disagrees with the producer by
roughly 23–35 rows on `e:14887630`, and that is EXPECTED, not a new defect.** CAL-P090 fixed the
producer alone, so from `f252d12a` until `-89` merges, the auditor keeps reporting the defect as
live because the auditor still has it. The specimen: 4 Polymarket legs deleting 23 Kalshi legs on
that event; 35 rows across 2 `vm_id`s whole-domain. An instrument silently measuring a different
population than the thing it audits is worse than no instrument — its agreement reads as
corroboration.

### One structural change to make the guard honest

`admin_data_quality.py`'s `/calibration-data` SQL was an inline string inside the route function.
It is now the module constant `_CALIBRATION_AUDIT_POPULATION_SQL`, placed immediately before the
route, **body byte-identical**; the function does `sql = text(_CALIBRATION_AUDIT_POPULATION_SQL)`.

This is not tidying. A guard that re-types the SQL it guards cannot see the original regress —
which is precisely how this chain drifted out of step with the producer in the first place.
`audit_golf_hockey_calibration.py` already carried its statement as a module constant
(`BUILD_TEMP_SQL`) for the same reason; this one now matches, and the new gate imports both and
executes them.

---

## 2. The guard — `tests/integration/test_calibration_mode_price_source_scope_peers_pg.py`

Real Postgres, gated on `SEARCH_TEST_DATABASE_URL` (CI's `search-recall` service container) with
`CALIBRATION_TEST_DATABASE_URL` accepted as an override. Five tests:

| test | arm |
|---|---|
| `test_admin_calibration_data_does_not_cross_suppress_sources` | site 2, fix + falsifier + premise probe |
| `test_red_first_admin_reverted_join_reproduces_the_suppression` | site 2, **red-first** |
| `test_golf_hockey_audit_does_not_cross_suppress_sources` | site 3, fix + falsifier |
| `test_red_first_golf_reverted_join_reproduces_the_suppression` | site 3, **red-first** |
| `test_single_source_behaviour_is_unchanged_at_both_peer_sites` | the control, both chains |

**The fixture.** One `event_id` reachable from two sources. Kalshi carries five legs, two of them
at Polymarket's modal price — five legs means `eligible = 5`, so Kalshi's own mode would need
`count > GREATEST(2.5, 2) = 2.5` and 2 is not, so **Kalshi forms no mode of its own and anything
that deletes its legs came from the other source.** Polymarket carries four legs, all at 0.5:
`eligible = 4`, threshold `GREATEST(2, 2) = 2`, count 4 — those four SHOULD be deleted, by their
own mode, among themselves.

* post-fix, admin chain: `{(bucket 1, kalshi): 1, (2, kalshi): 1, (5, kalshi): 2, (6, kalshi): 1}`
* pre-fix: bucket 5 vanishes entirely — Polymarket's mode takes Kalshi's pair with it

**RED-FIRST, in the same run.** Each site has an arm that applies textual reverts to the
production string and **executes** it, asserting the suppression returns. Every substitution
asserts it matched **exactly once**: a revert that silently failed to revert would run the FIXED
SQL, observe no suppression, and report that red-first was proved — gotcha #53's shape wearing a
test's clothes. There is no local Postgres in the agent sandbox (`initdb` dies on `shmget`), so
red-first cannot be demonstrated by hand and has to be built into the run.

**THE FALSIFIER, attacked rather than assumed.** The fix must SCOPE dedup, never disable it. The
control seeds one source with a genuine within-source mode (4 legs, 3 at 0.5, count 3 > 2) on
both chains and asserts those three are still deleted. Adding `source` to a GROUP BY and a join
can only change behaviour where more than one source is present; where exactly one is, the fix
must be a no-op, and that is now measured rather than argued.

**THE PREMISE, asserted rather than assumed.** The admin arm executes a truncated prefix of the
production constant and asserts that the two sources really do share one `vm_id` and really do
carry their own source-scoped `eligible`. If a later change makes `vm_id` source-carrying, the
gate's whole subject disappears; it now says `PREMISE GONE` out loud instead of passing vacuously.

**CI.** Wired as a new `search-recall` step, *Calibration mode-price source scope, peer sites
(real Postgres)*, with the job's standard skip-detection (`set -o pipefail`, `tee`,
`grep -qiE "[0-9]+ skipped"` → `::error::` + `exit 1`). `search-recall` is in `deploy`'s `needs:`,
so a red gate there blocks deploy. YAML re-parsed after the edit; step order confirmed.

---

## 3. 🔴 A DEFECT FOUND IN INHERITED WORK — CAL-P090's guard could never have run

**`tests/integration/test_calibration_mode_price_source_scope_pg.py` (CAL-P090's own guard) would
have died on its first real CI run**, on a job `deploy` needs, for a reason with nothing to do
with #2098. CAL-P090's report recorded the file as "COLLECTED but never EXECUTED" — which is
exactly why nobody found out.

Six NOT NULL columns were missing from its raw `INSERT`s, in two flavours:

| column | why it is required |
|---|---|
| `futures_markets.external_id` | NOT NULL, **no default at all** |
| `futures_markets.name` | NOT NULL, no default |
| `futures_outcomes.external_id` | NOT NULL, no default |
| `events.status` | NOT NULL, **Python-side `default='scheduled'` only** |
| `futures_markets.category` | NOT NULL, Python-side `default='championship'` only |
| `futures_odds_snapshots.reading_count` | NOT NULL, Python-side `default=1` only |

The second flavour is the trap: **a raw `text("INSERT ...")` never runs SQLAlchemy's Python-side
`default=`.** Only a `server_default` is filled by the database. An ORM insert would have supplied
all six and taught you nothing.

All six are repaired, in CAL-P090's file and in the new one.

### And a static guard for the class — `tests/test_pg_gate_seed_completeness.py`

Reading the seed by eye caught the three no-default columns and **missed all three Python-default
ones**. So the check is now mechanical, and it lives in the **ordinary** backend suite because
that is the arm of this failure that can be run without a database:

* it parses `INSERT INTO <table> (<cols>)` out of each listed gate and compares against
  `Base.metadata`, excusing `server_default` and autoincrementing PKs and **nothing else**;
* a discovery test fails if any real-Postgres gate grows a raw INSERT and is not listed, so
  `COVERED` cannot silently fall behind. A gate is identified by its `*TEST_DATABASE_URL` env
  gate, **not** by filename — `*_pg.py` is a convention several existing gates predate, and
  `test_create_wave_insert_bind_contract.py` and `test_kalshi_cliff_bind_contract.py` are now
  covered too (both already clean). The docstring records why the arm must NOT be widened to
  every file containing an INSERT: `test_route_admin_db_query.py` carries
  `"INSERT INTO events (id) VALUES (1)"` as a **rejection fixture** — an INSERT that is supposed
  to be invalid — and flagging it would be a false red on a test doing its job;
* it asserts it parsed at least one statement per listed file — silently checking nothing is the
  one outcome it exists to prevent.

It cannot tell you a gate passes. It tells you the gate will get far enough to fail for its own
reasons, which is the entire gap that let this through.

---

## 4. Stale prose — three regions that still described the defect as a semantic

The directive's item 3. These describe code that ruling 125 changed, so they ride the same wave.

### `app/utils/calibration_staged_futures.py` — module docstring, and `plan_units`

Both said the unit is `vm_id` without source because the population keys **two** things on bare
`vm_id`: the `mode_prices` election and the `ROW_NUMBER() PARTITION BY cv.vm_id` representative
window — so cross-source peers "vote in the same mode-price election and compete for the same
representative row."

**The mode-price half was a defect, not a semantic, and it is gone.** Both regions now say so and
name the measured specimen. But the honest position is narrower than "one reason instead of two",
and it is now written down:

* the surviving source-blind key is the representative window;
* `rn` is consulted only on the non-multi branch (`ELSE ro.rn = 1`), and any `vm_id` shared across
  sources got there through the `e:` arm, which requires `event_size >= 3` **per source** and
  therefore makes both sides `is_multi`. **So on exactly the rows where the collision occurs,
  `rn` is computed and never read.**

**The rule "a `vm_id` is never split" is RETAINED**, on the two grounds that survive: whole-`vm_id`
units are what make CAL-P016's partition content-addressed and the cursor stable, and "computed
and never read" is an argument, not the measured row-identity proof a change of chunk key would
need. Both regions now say explicitly that changing the unit is a **ruling, not a refactor** —
because the weaker justification is exactly the condition under which a future window quietly
"simplifies" it.

### `app/tasks/calibration_published_twin_worker.py` — §4 of the module notes

Said the aggregates are source-scoped and safe "but `mode_prices` groups by bare `vm_id` and
`deduped` joins on bare `vm_id`", measured 1,271 event_ids reaching `event_size >= 3` under more
than one source, and closed: *"Whether any of the 1,271 actually cross-suppresses today is **NOT
measured**."*

**It was measured, and it does** — and it was not a chunking hazard, it was a defect in the
published curve. §4 now records the measurement, records ruling 125's fix at all three sites, and
re-derives what is left: the representative window, computed-and-not-read on the colliding rows.
Its conclusion is correspondingly weakened rather than reversed — **a source-chunked fold is no
longer known to differ, and is still not PROVEN row-identical**, and promoting it needs a measured
row-diff, not an inference from that note.

---

## 5. What this change does NOT do

* **It does not touch `precompute_calibration.py`.** Ruling 009's freeze and ruling 033 both hold;
  the producer's fix is CAL-P090's commit and is untouched here.
* **It does not run cert C-2098-SOURCE-1.** That cert owns the producer and is staged with its
  own window.
* **It does not change the apply's sequencing, or open any §5c gate.** `-89` merges behind the
  same chain `-88` does.
* **It writes nothing.** Both sites are read-side SELECTs; gotcha #21 is not in play.
* **It does not re-open the chunk key.** §4 above deliberately stops at describing the weakened
  argument.

---

## 6. Gates

Recorded per gotcha #54 — exit codes read by value, never through a pipe.

| gate | result |
|---|---|
| `pytest tests/test_pg_gate_seed_completeness.py` | **3 passed** (and it FAILED red first, naming all six columns — that is how they were found) |
| `pytest` peers + `-88` gate + seed-completeness | **3 passed, 8 skipped** (the 8 are the PG gates without a database — expected locally, `::error::`-detected in CI) |
| `pytest -k "staged_futures or published_twin or calibration_population or frozen"` | **279 passed** |
| `.github/workflows/ci.yml` | PyYAML re-parse OK; new step present in `search-recall`; `deploy.needs` still includes `search-recall` |
| revert-anchor uniqueness | every `_REVERTS` substitution and the `CREATE TEMP TABLE` strip verified to match **exactly once** in the live source |
| `pytest tests/test_startup.py` | **4 passed** |
| `pytest tests/` (full backend) | **18,762 passed, 103 skipped, 61 xfailed, 0 failed** — 12m11s |
| `TZ=UTC npx jest ciJestGate ciTypecheckGate` | **31 passed** — the only two tests that parse `ci.yml`, both re-run because this window edited it |
| `git merge-tree` vs `origin/master` | **exit 0, 0 conflicts** |

**One gate had to be run twice, and the reason is worth recording.** The first full-suite attempt
reported `EXIT CODE: 0` from the background launcher while pytest had actually exited **4** on
`unrecognized arguments: --timeout` — the plugin is not installed. That is gotcha #54's amendment
exactly: the launcher reports its own exit, and `4` is a usage error, a story about the harness
rather than a result. The second attempt then ran while this file's `COVERED` list was being
widened, so pytest had already imported the pre-widening module at collection; it was re-run a
third time with nothing in flight, which is the 18,762 above (up 2 from 18,760 — the two new
parametrized cases). A suite number collected around an edit is not a number about the tree you
are committing.

---

## 7. Files changed

```
backend/app/routes/admin_data_quality.py                  fix + SQL hoisted to a module constant
backend/scripts/audit_golf_hockey_calibration.py          fix
backend/app/utils/calibration_staged_futures.py           prose (module docstring, plan_units)
backend/app/tasks/calibration_published_twin_worker.py    prose (module notes §4)
backend/tests/integration/test_calibration_mode_price_source_scope_peers_pg.py   NEW — the guard
backend/tests/test_pg_gate_seed_completeness.py           NEW — the static seed check
backend/tests/integration/test_calibration_mode_price_source_scope_pg.py         repaired (§3)
.github/workflows/ci.yml                                  new search-recall step
docs/audits/calibration/cal-p091-2098-peer-sites-and-stale-prose.md              this file
```

Also produced this window, **outside the repo by design**:
`.claude/handoff/RUNBOOK-CAL-P086-ATTENDED-APPLY.md` — the attended-apply run sheet (directive
item 2). The apply fires today and `-89` does not merge today, so a run sheet on the branch would
arrive after the run. `.claude/handoff/` is master-worktree-only and gitignored; there is
deliberately no second copy.
