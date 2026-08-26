# CAL-P098 — point-by-point answer to `C-FOLD-REWRITE-1`'s BLOCK

subject: the fold narrowing rewrite of `_calibration_population_ctes`
verdict under review: **BLOCK**, `CODEX-REPORT-2.md:782`, 2026-08-25
frozen acceptance: `CODEX-QUEUE.md:395` (G0–G5 + kill criteria), unamended
this rework: `program/calibration-94`, one commit, parent = `origin/master` `a5688c0b`

> **The acceptance did not soften and nothing here asks it to.** Every finding
> below is accepted as correct. Three of the four are the same defect wearing
> different hats — *the frozen gate could not be executed, because no instrument
> existed that could execute it* — and that is what this queue built.

---

## Finding 1 [P1] — "neither one snapshot nor the required exact comparator"

**Accepted in full, including the part that is embarrassing:** the artifact said
"same session" and it was two HTTP POSTs.

| what G1 froze | what CAL-P096 did | what CAL-P098 does |
|---|---|---|
| one `REPEATABLE READ, READ ONLY` transaction spanning OLD and NEW | two `POST /api/admin/db-query` calls, one `get_db` session each, no transaction across the pair | one `asyncpg` transaction opened `isolation="repeatable_read", readonly=True`, spanning **every** residue and **every** `EXPLAIN` of the run. `now()` is recorded at the start and again at the end and compared: `one_snapshot` is on the artifact as a boolean, not as prose |
| bilateral `EXCEPT ALL` | one ordered MD5 + a count | `old_rows EXCEPT ALL new_rows` **and** `new_rows EXCEPT ALL old_rows`, both counted, in one statement |
| duplicate cardinality by `outcome_id` | absent | `dup_old`/`dup_new` grouped by `outcome_id`, compared bilaterally, plus `max_dup_*` so "no duplicates existed" is distinguishable from "duplicates matched" |
| every semantically consumed value, at database scale | a digest over `d.*::text` | `SELECT *` through `EXCEPT ALL` — strictly stronger than the frozen column list, and the list is separately asserted PRESENT so a projection change cannot quietly shrink the oracle (`G1_REQUIRED_COLUMNS`, 34 columns) |
| buckets as a **secondary** check | conflated with the primary | `buckets_old`/`buckets_new` on `(source, category, price_moved, width_bucket, n, winners, sum_prob)`, reported after the row oracle and never instead of it |
| ≥8 non-adjacent residues spanning MOD 64 and MOD 257, incl. 0 and both edges | MOD 997 ×2, MOD 9973 ×9 | `RESIDUE_PLAN` = `(64,0) (64,31) (64,63) (257,0) (257,61) (257,127) (257,191) (257,256)`. Non-adjacency is machine-checked, and the checker is itself tested against an adjacent pair so it can say no |

Why the two chains fit in one statement at all: each is nested inside its own
`FROM ( WITH … SELECT * FROM deduped )` sub-select, so the two identical CTE name
sets are scoped apart. That is the whole reason CAL-P096 reached for two requests,
and it was avoidable.

The rail is gone from the file — asserted, not just removed
(`TestTheRunnerUsesTheFrozenPlan::test_it_does_not_go_through_the_admin_rail`).

**The superseded artifact is marked, not deleted.**
`artifacts/cal-p096/row-identity-mod-sampled.txt` now opens with a withdrawal
banner naming all three defects; its 11 measurements stand, the claim does not.

---

## Finding 2 [P1] — "the named-node performance gate is entirely unmeasured"

**Accepted.** `EXPLAIN` without `ANALYZE` cannot produce an actual, and the rail
cannot compose `ANALYZE` at this scale, so the gate was unmeasurable rather than
unmeasured-by-choice. `--gate g3` now issues
`EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT JSON)` on the **same** G1 samples,
inside the same snapshot, with an explicit per-statement timeout in G3's frozen
60–300 s band, and **alternating run order** per residue so a warm buffer pool
cannot manufacture the win.

The named node is located **by name** — `Subplan Name == "CTE ranked_outcomes"`
(OLD) / `"CTE ranked_outcomes_core"` (NEW) — and then the WindowAgg whose direct
child is a `Sort`. This population sorts in more than one place, and "the deepest
Sort" would have been a number about an unrelated node. The two windows share an
ORDER BY prefix, so PostgreSQL stacks two WindowAggs over one Sort; the inner one
is the measured pair and the outer one's `Total Cost` is reported separately as
the subtree cost.

Recorded per side, per residue: `Actual Rows`, `Actual Loops`, derived
`sort_input_rows`, `Plan Width`, `Sort Method`, `Sort Space Used`,
`Sort Space Type`, `Temp Read/Written Blocks`, Sort and WindowAgg actual time,
WindowAgg subtree `Total Cost`, and the final `deduped` row count.

All five clauses are graded in code, with unit tests that make each one fail:

* **G3.1** identical actual WindowAgg input rows — `test_g3_fails_on_a_changed_window_population`
* **G3.2** width ≤ 25% — `test_g3_fails_a_wide_row_even_when_it_is_faster` (a 100× speedup on a wide row is still a FAIL)
* **G3.3** median node time ≤ 70%, no sample worse than +10%
* **G3.4** spill must not increase — `test_g3_fails_a_new_spill`; an unchanged spill is *reported*, never called a win
* **G3.5** final rows identical

`node_time_ms` takes the WindowAgg's **inclusive** time rather than adding Sort +
WindowAgg, because `Actual Total Time` already includes children and the sum
would be a number that does not exist. Pinned by
`test_node_time_does_not_double_count_the_sort`.

Width is additionally graded in CI on the seeded Postgres
(`test_new_sort_is_narrower_than_the_old_sort`), because width is a property of
the projection and not of the data — so it is the one part of G3 a seed can grade
honestly.

---

## Finding 3 [P1] — "four required mutation controls and part of the adversarial suite do not exist"

**Accepted.** A comparator nobody has fooled on purpose is a comparator nobody
has tested.

### G4 — all five controls, each producing a recorded exit code

Driven by `FOLD_GATE_MUTANT`; CI runs the loop and reads the exit code **by
value** (gotcha #54: `1` is a result, anything else is a story about the harness),
with no pipe anywhere near it.

| # | mutant | what it breaks | what must go red |
|---|---|---|---|
| 1 | `wide_shape` | NEW := the pre-split chain | G1 stays green (identical rows) and the **width** clause fails at ratio 1.0 |
| 2 | `global_rn1` | §3's own rejected shortcut: `WHERE core.rn = 1` on the joined CTE, before the flags exist | legitimate multi/field members disappear |
| 3 | `row_swap` | one published row replaced by one carrying every value but a displaced `outcome_id` | **buckets green, rows red** |
| 4 | `flag_flip` | `is_nonexclusive_bundle` inverted | **buckets green, values red** |
| 5 | `narrow_population` | `AND MOD(fo.id, 2) = 0` inside the core | the published population shrinks |

`flag_flip` targets `is_nonexclusive_bundle` deliberately: it is the one flag
`deduped`'s `WHERE` does not read, so inverting it changes no membership, no
probability and no bucket. That is the precise failure an aggregate oracle cannot
see, and the test asserts the flag is census-only rather than assuming it.

Every mutation is validated to have **changed the text** before it is used
(`mutate_in_cte` / `append_to_cte` raise on a missing anchor). A mutation that
silently no-ops is worse than no mutation: the control runs, the gate stays green,
and the green is filed as evidence of teeth it was never shown to have.

### The collision control, retained permanently

`test_aggregate_green_while_row_identity_red_collision_control` runs
unconditionally — including under every mutant, because it tests the ruler rather
than the thing measured. It asserts, in one statement, that the aggregate
comparator reports **0** differing buckets while the row comparator reports
**exactly one** old-only and **exactly one** new-only row. Queue 299 / #259's
precedent, executed rather than cited; without it the frozen text says G1 is
vacuous.

### G2 — the adversarial populations

| G2 requirement | before | now |
|---|---|---|
| exact-distance tie decided by `fo.id` | ✅ `_m(70)` | unchanged |
| non-partition multi where >1 outcome survives | ✅ | now **named** in the oracle: `_m(70)` publishes both legs |
| complete normalized field summing to 1 | partial | `_m(10)`, with each member's normalized probability asserted **and** the partition's sum asserted to close at 1.0 |
| **incomplete field where one excluded member drops the whole field** | ❌ absent | ✅ `_m(140)`: four Kalshi weather members, proved shape, one winner, divisor 1.60; member `wx-d` carries a 0.10/0.90 book with bid evidence and no trade, so it stays **liquid and in the roster** and is excluded per-outcome. `survivor_n` 3 ≠ `eligible_n` 4 → `is_field_incomplete` → **all four drop**. This is the specimen that makes §3's rejected shortcut visible: with the flags joined after `rn = 1`, `field_completeness` would aggregate over one row instead of four, `wx-d`'s exclusion would be invisible, and this field would publish four wrong rows with the right count |
| one specimen per moved LEFT-JOIN flag | ✅ all nine | unchanged, and the coverage assertion now also requires a `liquid` specimen |
| Kalshi liquid/illiquid pair | one-sided | ✅ `_m(120)`/`_m(160)`: same source, same 0.30 price, differing **only** in one snapshot carrying a bid and no trade (the Queue #267 / C44 #1 keep) |
| Polymarket placeholder/non-placeholder pair | one-sided | ✅ `_m(110)`/`_m(150)`: same source, same 0.50 price, same band, differing **only** in trade evidence |
| identity fixed, one flag mutated | ❌ | ✅ the `flag_flip` control |
| **per-fixture exact expected sets and values** | ❌ global OLD==NEW only | ✅ `EXPECTED`: every seeded market's exact published `outcome_id` set, the reason in one sentence, the flags that must hold, and the normalized probabilities. Graded against **OLD and NEW independently**, so "they agree" is no longer the only thing on record |

The seed and the oracle are prevented from drifting by a **DB-free** test
(`TestTheSeedAndTheOracleCannotDrift`) that runs in the ordinary suite: every
seeded market has an expectation, every expected outcome exists in the seed, the
incomplete-field specimen is still incomplete, and both evidence pairs still
differ in exactly one dimension.

---

## Finding 4 [P1] — "the mandatory full canonical durable twin has not run"

**Accepted, and it is still correctly withheld.** The frozen ordering fires G5
only after G0–G4 pass, so a G5 run today would be out of order regardless of who
ran it.

What CAL-P098 owed here is that the run must not be *unreachable* when its turn
comes, and it is not. The instrument exists, it is the shipping path, and the
invocation is one line:

```bash
heroku run:detached -a bainluck \
  "python3 scripts/measure_published_twin.py --bank --timeout-ms 5400000"
# then, ~90 min later — never the dyno's stdout (gotcha #48):
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BAINLUCK_API/api/admin/calibration-twin/last" | python3 -m json.tool
```

⚠️ **One trap, named so nobody loses a run to it.** `MAX_TIMEOUT_MS` is
**1,350,000 ms**, and it is not the fold's ceiling — it describes the CELERY
task's `soft_time_limit=1800`. `POST /api/admin/calibration-twin/run?timeout_ms=5400000`
therefore **clamps to 1,350 s** and will report a timeout at 22½ minutes that
means nothing about the fold. The 5,400 s ceiling is `ONE_OFF_MAX_TIMEOUT_MS`
and is reachable **only** through `scripts/measure_published_twin.py --bank`
on a one-off dyno, which has no `soft_time_limit` over it. Use the script.

---

## Who runs the gates, and why this queue did not

Ruling 134 (banked 2026-08-25, and restated at the head of `CLAUDE.md`) is
explicit: *build lanes BUILD — their only permitted measurement is their own
gates… every cert belongs to the measurement lane.* G1/G3/G5 are cert executions
against a frozen acceptance, they are heavy production reads, and the frozen text
addresses them to the cert window by name. So this queue **built the instruments
and did not fire them**, and says so rather than shipping a thin production
sample that would have to be graded a second time.

What it did instead, which is the strongest thing available to a build lane: it
made the harness **executable and self-proving**. The comparator statement is not
described, it is *run* — on CI's real Postgres, over a seed that exercises every
moved join, through the identical code path the one-off dyno uses. If the harness
cannot execute, that is discovered in CI on a seeded database rather than on a
dyno at MOD 64.

Two facts the cert window should have before it starts:

1. **There is no local Postgres in either sandbox.** `initdb` dies at
   `shmget: Operation not permitted` — re-confirmed 2026-08-25 in this window,
   matching the BLOCK's own note. G2/G4 are therefore CI-only, and CI runs them
   only on a pushed branch. That is a real constraint on this cert, not an
   omission by either side.
2. **`heroku logs` is EPERM-blocked from the agent sandbox** and its failure
   looks like a clean grep. Every G1/G3 run must be read back from the durable
   row at `GET /api/admin/fold-narrowing-gate/last`, never from dyno stdout.

## The one-line invocations

```bash
# G1 + G3, frozen residue plan, one snapshot, durable bank
heroku run:detached -a bainluck \
  "python3 scripts/verify_fold_narrowing_row_identity.py --gate both --bank"

curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BAINLUCK_API/api/admin/fold-narrowing-gate/last" | python3 -m json.tool

# exit codes: 0 PASS · 1 a gate FAILED · 3 could not measure · 4 config
```

## What is NOT claimed

* No production row-identity or named-node measurement was taken this queue.
  G1 and G3 are **unrun**, not passed, and the artifact schema reports an unrun
  gate as `NOT_MEASURED` with exit 3 rather than as agreement.
* G5 is unrun.
* The G2/G4 Postgres gates have **never executed anywhere** — no local Postgres,
  and the branch is unpushed so no CI run exists. They are proved to *collect*
  (6 tests, 6 skips, exit 0) and their DB-free premises are proved by 83 passing
  tests (74 structural + 9 reader), plus the full backend suite at 20,012 passed /
  0 failed / EXIT 0. That is the honest state.
* The population SQL is **byte-identical to `6fe52759`**. This queue changed the
  ruler, not the rewrite.
