# CAL-P102 — the G3.2 advisory's code obligation, built

**Advisory:** `CODEX-REPORT-2.md`, CODEX run 2026-08-26 21:44Z — *"C-FOLD-REWRITE-1 G3.2
advisory"*. Verdict **(a) CODE — the frozen G3.2 bar stands at <=25%**.
**Subject before this queue:** `program/calibration-94 @ b660336f` (PR #2223).
**Cert:** `C-FOLD-REWRITE-1`, re-pin to this branch's head. Acceptance UNCHANGED.

---

## What the advisory ruled, and what it did not

It ruled the rewrite genuinely violates the bar on the evidence available, and it ruled the
21:30Z production probes **cannot** support a re-freeze — they EXPLAIN two unrelated queries
over `futures_markets` (`Plan Width 13`, aggregate width 8), locate no
`CTE ranked_outcomes[_core]`, and misdescribe the CI ratio as "1114 B row / 1186 B aggregate"
when the gate compares the NEW Sort tuple with the OLD Sort tuple.

So the two options the directive named resolve one way only: **build the named fix.** No bar is
re-proposed here, no threshold is touched, and `G3_MAX_WIDTH_RATIO = 0.25` is exactly where it
was. This lane measured nothing to reach that conclusion — the advisory is the measurement, and
ruling 134 leaves the re-measure to the gate itself, in CI, on the frozen criterion.

## The defect in one line

**Column count is not byte count.** CAL-P096 deferred nine per-market LEFT JOINs out from under
the window; the Sort's projection fell from 27 columns to 17; the width fell from **1186 B to
1114 B — 93.9%**, against a 25% bar (CI run `33016072464`, job `98334497656`). The ten columns
that left were the cheap ones. CAL-P101's projection diagnostic is what makes that legible, and
it is the reason this round could be diagnosed at all rather than argued about.

## The fix

The advisory named a valid shape and this is it: *"a key-only window CTE carrying the stable
outcome ID plus only the partition/order/window inputs, followed by a join-back on that immutable
outcome ID before the downstream completeness, normalization, and multi-row publication logic."*

| CTE | before | after |
|---|---|---|
| `ranked_outcomes_base` | — | the scan, its WHERE, the 17-column payload, `{rn_order} AS rn_order_val`, and a `ROW_NUMBER() OVER ()` surrogate. **No window sort.** |
| `ranked_outcomes_core` | the scan **and** the two windows over the 17-column row | **key-only**: `row_key`, `rn`, `rn_distance_rank`, reading `ranked_outcomes_base` whole |
| `ranked_outcomes` | `FROM ranked_outcomes_core core` + nine LEFT JOINs | `FROM ranked_outcomes_base base` + `JOIN ranked_outcomes_core core ON core.row_key = base.row_key` + the same nine |

`ranked_outcomes`' emitted relation is **unchanged**: same 31 columns, same names, same order,
asserted against the frozen pre-split fixture. Everything outside `ranked_outcomes` is still
byte-identical to that fixture, which is what keeps it an oracle.

### The Sort's input is now four values

`row_key` (bigint) · `vm_id` (the partition key) · `rn_order_val` (float8) · `outcome_id`
(bigint). Nothing else can be in it, and that is asserted as a **column-set equality**, not a
prohibition list — `test_no_payload_column_survives_under_the_sort`. Adding "just one more"
column to save a join is the exact move that produced 93.9%.

### Why the name did not move

The obvious spelling was a new CTE for the window with the payload keeping the name
`ranked_outcomes_core`. That would have left `NEW_WINDOW_CTE` pointing at a CTE with no
WindowAgg, so `named_node_metrics` would return `measured: False` and G3 would go NOT_MEASURED —
**an instrument change, mid-flight, on the criterion the rewrite is being graded against.** The
windows keep the name so the frozen bar keeps measuring the same node role it was frozen on.
`OLD_WINDOW_CTE` / `NEW_WINDOW_CTE` / `G3_MAX_WIDTH_RATIO` / `G3_MAX_MEDIAN_TIME_RATIO` /
`G3_MAX_SAMPLE_REGRESSION` are all untouched.

### Why the join back is a surrogate and not `outcome_id`

Ruling 125 — *"a join that can DELETE a row must carry every dimension that identifies the
row"* — read in the duplicate direction. **`outcome_id` is not a key of this relation.**
`clean_vms` inherits `vm_stats`' `GROUP BY (vm_id, source, category, is_grouped,
mutually_exclusive)` while the base scan joins `cv` on `(vm_id, source)` alone, so a grouped
`vm_id` whose member markets disagree about category or exclusivity carries **two** `cv` rows and
therefore two copies of every outcome. Keying the join on `outcome_id` would pair each copy with
each rank and square them.

This is a pre-existing property of the chain. The rewrite must reproduce it, not quietly
de-duplicate it. It is pinned by
`test_outcome_id_is_provably_not_a_key_of_the_base_relation`, which reads the grouping out of the
SQL — so if `vm_stats` ever narrows to `(vm_id, source)`, that goes red and the surrogate gets
reconsidered on purpose instead of by accident.

The full natural key would also work and is the wrong choice: it puts `source` and `category` —
two more TEXT columns — into the very Sort this exists to narrow, and `Plan Width` prices an
unanalyzed `varchar(255)` at 141 B whatever it holds (CAL-P101's own note). One bigint carries
the same identity in 8.

`ROW_NUMBER() OVER ()` has no ORDER BY, so it adds a WindowAgg and **no Sort** — pinned, because
giving it one would put a sort of the WIDE row back one CTE earlier, where no gate is looking.

### Why this is the same `rn`

Four claims, each checkable without a database:

1. **Same population.** The window CTE reads `ranked_outcomes_base` whole, with no predicate of
   its own — asserted (`WHERE` must not appear in it). The horizon path's INNER `horizon_price`
   join is a FILTER and stays in the base, so "before the window" still holds.
2. **Same ordering.** `rn_order_val` IS `{rn_order}`, projected one CTE earlier and asserted to
   be projected rather than restated. Sorting by a column and sorting by the expression that
   produced it order identically, NULLs included.
3. **Same tie authority.** `b.outcome_id` IS `fo.id`. Alex's 2026-08-03 ruling survives intact,
   and `rn_distance_rank` still ranks on distance ALONE — both pinned in
   `test_calibration_staged_futures_sql_300d.py`, now asserting BOTH halves (what the base
   projects AND what the window orders by) rather than one `ORDER BY` line.
4. **1:1 join back**, on a surrogate unique by construction.

Row identity itself is not a string claim and is not asserted as one. CI's real-Postgres gate
runs the frozen pre-split SQL and the current SQL side by side on one seed and diffs
`ranked_outcomes`, `deduped` and `field_completeness` row for row, column for column.

### The G4.5 control had to move with the population

`mutant_narrow_population` appended `AND MOD(fo.id, 2) = 0` to `NEW_WINDOW_CTE`. That CTE now has
no `WHERE` and no `fo` alias, so the control would have raised a **syntax error instead of
narrowing a population** — a control that cannot execute is a control that stopped controlling.
It targets the new `NEW_POPULATION_CTE = "ranked_outcomes_base"`, and the pin asserts both
directions (it lands on the population, it does NOT land on the window).

G4.2 (`WHERE core.rn = 1`) is untouched, and that is why the payload took the new alias while the
ranks kept `core`: renaming the other way would have broken that control the same way.

## Gates

| gate | result |
|---|---|
| `test_calibration_fold_narrowing_p096.py` | **89 passed** exit 0 (was 77 — 12 added) |
| `+ test_fold_narrowing_gate_reader_p098.py` | **101 passed** exit 0 |
| `test_calibration_staged_futures_sql_300d.py` | **30 passed** exit 0 |
| fingerprint coverage + derived map | **20 passed** exit 0 |
| `uncovered_sql_shaping` | **still 21** — unchanged; only `source_sha256` moved in the fixture |
| SQL parses (`sqlglot`, postgres dialect) | headline / frozen_roster / horizon — all three, CTE order `clean_vms → base → core → ranked_outcomes` |
| alias resolution across the split | 0 unresolved on all three call paths, and now a permanent test |
| ruff | exit 0 on all four changed Python files |
| `ci.yml` | YAML parses; comment-only edit |

## What this lane could NOT close

1. **The width itself is unmeasured here, and deliberately.** `Plan Width` is a fact about an
   executed plan on a real database. This queue changes the projection and pins the column set;
   the number is CI's, against the unchanged bar. If the ratio is still over 25% after this, the
   diagnosis was wrong and it should BLOCK again — the shape above is falsifiable in one CI run.
2. **The heterogeneous-group fan-out is proved STRUCTURALLY, not executed.** The PG seed has no
   grouped `vm_id` whose members disagree about category, so the surrogate's necessity is argued
   from the SQL rather than demonstrated on rows. Writing that seed means writing its `EXPECTED`
   oracle with no local Postgres to check it (`initdb` dies on `shmget`), and a wrong expectation
   turns a DEPLOY gate red for a reason unrelated to the rewrite — the failure mode
   `test_pg_gate_seed_completeness.py` exists because of. **Owed, specified, not shipped
   blind:** three markets sharing `group_id` + `source` (so `group_size >= 3` and the vm takes
   the `g:` arm) with one carrying a different `llm_sport_category`, plus its `EXPECTED` entry.
3. **The second base scan is not free and is not measured.** `ranked_outcomes` reads
   `ranked_outcomes_base` rather than re-scanning `futures_outcomes` — asserted — so the six
   EXISTS-shaped flags are still computed exactly once. What is added is one orderless WindowAgg
   pass for `row_key` and one hash join. Both should be dwarfed by not spilling a 1,114 B × ~1.5M
   sort, and neither is on the Sort + WindowAgg clock G3 times. That is a prediction, and G3's
   own time bars (`0.70` median, `1.10` per-sample) are what test it.
4. **Nothing about the apply moved.** No production read, no fold run, no `EXPLAIN`, no write.
