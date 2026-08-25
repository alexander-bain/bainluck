# CAL-P092 — the WHICHPRICE evidence round, and the publisher after-read guard

**Date:** 2026-08-24 (PT) · **Branch:** `program/calibration-90` · **Base:** `e03076ae` (CAL-P091)
**Directive:** FABLE DIRECTIVE 2026-08-24 — CAL-P092, items 1 and 2.
**Consumes:** `C-APPLY-PRE-WHICHPRICE-R3` (BLOCK, attacks 1/3/7) and `C-APPLY-PRE-1912-R3-R3` (BLOCK, attack 5).

> "Do not modify the fold; this is an evidence round, not a fix round."

`backend/app/utils/calibration_price_provenance.py` is **byte-identical to its state at `e03076ae`**
and a test asserts it (`test_the_fold_module_is_unchanged_by_this_round`). Every change in this
queue is in the reader, in a new independent verifier, or in tests.

---

## 0. What the two BLOCKs actually said, and what is owed

| Cert | Attack | The words | Owed |
|---|---|---|---|
| WHICHPRICE-R3 | 1 | "the artifact contains zero `rows`, `bins`, `sum_prob`, or `winners` fields … for policy C, the committed pooled value is `1.7422 pp`, while the only available aggregation of cell ECEs is `4.2831 pp`; bin-level cancellation is unknowable from the artifact" | commit the grouped inputs **and** a recomputation receipt that proves the displayed table from them |
| WHICHPRICE-R3 | 3 | "Repeating a prior full-population count after the certified population moved is not a current measurement" | re-run `LEG_SPLIT_SQL` on the **same 49-cell snapshot** as the whole-market fold, commit per-cell totals/fingerprints |
| WHICHPRICE-R3 | 7 | "There is no successful `k=1` table and no `k=16` read anywhere in the artifact. The committed test only proves the SQL *text* partitions on `fm.id`; it does not compare two database results" | execute both and compare the tables |
| 1912-R3-R3 | 5 | "adding only `# after-read proved` made the same test **PASS `5 == 5`** … the guard counts prose, not a publisher-to-reader relationship" | AST/callgraph rule + retain the injected-fifth-site mutation as a red test |

All four are live-executed below. Three of the four discharge cleanly; attack 7 discharges on its
primary demand and is reported **partially** on the cert's *named* cell, with the reason measured
rather than argued (§3.3).

---

## 1. The artifacts

| File | What it is | Bytes |
|---|---|---|
| `artifacts/cal-p092/price-provenance-whole-market-r4.json` | The successor sweep: 49 row folds + 49 whole-market folds + **committed grouped inputs** + per-cell leg split + three partition-invariance specimens. `elapsed_s 940.62` | 1,046,465 |
| `artifacts/cal-p092/recomputation-receipt-r4.json` | The independent re-derivation of every table in the above, from its own committed inputs | — |
| `artifacts/cal-p092/partition-invariance-supplement.json` | Second invariance pass at feasible `k` after the first pass measured the rail's headroom had shrunk | — |
| `artifacts/cal-p092/partition-invariance-esports.json` | Third pass on the cert's *named* cell at `k=16,32`. Records **two timeouts and no comparison** — kept because a failed measurement that is deleted reads as a measurement that was never owed | — |

**Anchor of the predecessor:** `artifacts/cal-p085/price-provenance-whole-market.json`,
SHA-256 `e8b1d7d45df341138675cf28c4ab43799f45c14a6b6d6c03f8e6fe4a0482ec0d` — verified byte-for-byte
against the R3 cert's anchor line before this round began, so the successor is provably an
extension of the certified subject and not a different measurement wearing its name.

### 1.1 The headline moved, because the population moved

| | R3 (2026-08-21) | R4 (2026-08-24) | Δ |
|---|---|---|---|
| pooled whole-market `A_today` ECE | 3.7226 pp | **3.6838 pp** | −0.0388 |
| pooled whole-market `C_exclude_hindsight` ECE | 1.7422 pp | **1.7153 pp** | −0.0269 |
| Δ ECE (the thing ruling 103 authorises) | −1.9804 | **−1.9685** | +0.0119 |
| `A_today` n | 372,293 | **376,699** | +4,406 |
| `C` kept n | 337,927 | **341,940** | +4,013 |
| row-fold reconciliation | exact | **exact** (`n_delta 0`, `delta_pp 0.0`) | — |

Full R4 whole-market pooled table (all-legs):

| policy | ECE (pp) | Δ vs A | n |
|---|---|---|---|
| `A_today` | 3.6838 | 0.0 | 376,699 |
| `B_exclude_cp_absent` | 2.8265 | −0.8573 | 305,100 |
| **`C_exclude_hindsight`** | **1.7153** | **−1.9685** | **341,940** |
| `D_moved_price_only` | 7.2600 | +3.5762 | 40,472 |
| `E_pregame_or_unknown_ts` | 2.9207 | −0.7631 | 38,067 |

Which-legs sensitivity reproduces at the new population: population-legs `C` is `1.7149 pp / 341,976`,
a **−0.0004 pp / +36 row** difference against all-legs. Same sign, same order of magnitude as R3's
`−0.0005 / +36`. The row-to-whole correction is `1.7169 → 1.7153`, **−0.0016 pp**.

**Nothing in this table changes the decision.** It is the same exclusion, worth the same ~2 pp, on
a population three days larger. What changed is that it is now *checkable*.

---

## 2. Attack 1 — the committed inputs and the recomputation receipt

### 2.1 What was added to the reader

`backend/scripts/measure_price_provenance.py` gains `--raw-rows`. Under it, every cell's grouped
rows are persisted **verbatim, stringified, sorted** (`canonical_raw`), for both folds, together
with `raw_rows_schema` — the column order written down, so an independent re-deriver does not have
to infer it (inferring it would be re-deriving the producer's assumptions).

`sum_prob` is committed as the **numeric string the rail returned**. Parsing it to a double and
re-serialising would make any receipt agree with the producer because it inherited the producer's
rounding.

### 2.2 The receipt

`backend/scripts/verify_price_provenance_artifact.py` reads **only the artifact**. It does not
import `app.utils.calibration_price_provenance` — a test asserts that by AST, over the module's
import statements, and also that it imports nothing from `app.` at all. It re-states the five row
policies, the five whole-market lifts, the population-legs sensitivity, the `MIN_CELL_N` floor and
the bin-pooled ECE from ruling 103's prose and the artifact's own schema.

Every figure is re-derived **twice**: once with `Fraction` (exact, no float error) and once with
IEEE doubles in the producer's order. The float pass must match the committed value **exactly**;
the exact pass must sit within `1e-4 pp`. A receipt with only the float pass would be re-deriving
the producer's rounding; one with only the exact pass would report last-digit rounding as a defect.

**Result, live:**

```
$ python3 backend/scripts/verify_price_provenance_artifact.py \
      artifacts/cal-p092/price-provenance-whole-market-r4.json \
      --out artifacts/cal-p092/recomputation-receipt-r4.json
EXIT CODE: 0
RECEIPT verdict=True checked={'cells_row_fold': 49, 'cells_whole_market': 49, 'pooled': 2}
        problems=0 cell_average_C=6.9891
```

49 of 49 row folds, 49 of 49 whole-market folds, and **both pooled tables** (row-level and
whole-market, including the population-legs sensitivity) reproduced from committed inputs by a
second implementation. Zero differences.

### 2.3 The counter-example, recomputed rather than asserted

The receipt also prints the arithmetic the cert could only offer: the **unweighted average of the
49 per-cell whole-market policy-C ECEs is 6.9891 pp**, against the pooled **1.7153 pp**. (R3's pair
was `4.2831` vs `1.7422`; the average moved much further than the pool because it weights a 2-row
cell like a 79,076-row one.) This is not an error being reported — it is what a pooled ECE and a
cell average *are*, and it is the entire reason an artifact of answers cannot be checked.

### 2.4 The limit of this receipt, stated

The receipt is independent of the **Python fold**, not of the **SQL**. Both sides read the same
grouped rows the database returned, so a misclassification inside `PROVENANCE_FOLD_SQL` would be
reproduced faithfully by both. Attack 1 is about the arithmetic above the rows; the SQL is attacks
2/4/6's ground, and those passed. Saying so here rather than letting a green receipt imply more
than it proves.

---

## 3. Attack 3 — the leg split, measured on THIS population

`--leg-split` was run for **all 49 cells of the same sweep** as the whole-market fold, and pooled by
summation (every column is a market count, and no market spans two cells because the cell
predicates are all on `fm`):

```json
"pooled_leg_split": {
  "totals": {"markets": 480638, "all_after": 24816, "none_after": 455715, "mixed": 107},
  "cells_measured": 49, "cells_unmeasured": [], "complete": true
}
```

**107 mixed markets in 480,638 — 0.0223%.** Against R3's carried-forward `101 / 464,777`.

The cert was right that the repetition was not a measurement: on the current population the count
is **107, not 101**, and the denominator is **480,638, not 464,777**. The conclusion the number was
load-bearing for is unchanged — mixed markets remain ~2 parts in 10,000, so the whole-market lift
drops essentially the same rows its row-level twin does — but it is now a measurement of the fold
under cert rather than a memory of an older one.

The pool carries `complete: true` and names any cell it could not measure. A partial sum presented
as a population count is the same defect at smaller scale; `test_an_unmeasured_cell_makes_the_pool_incomplete_by_name`
holds that line, and a side-probe timeout still cannot kill the fold (CAL-P077 ruling (a)).

---

## 4. Attack 7 — two database results, compared

`--invariance CELL:K,K` runs one cell's **whole-market** fold at each `k` as genuinely separate
sets of statements and compares:

1. the **policy table** — the object the apply is authorised against — byte-canonically; and
2. the **grouped inputs**, re-aggregated per key first.

On (2): a `k`-way partition legitimately emits the same `(grade, bin, level…)` key once per
partition, so comparing verbatim rows would report "the partitions disagree" for every cell ever
partitioned. `aggregate_raw` sums the last three columns per key as `Decimal` from the returned
numeric strings, so the re-aggregation is **exact** and a mismatch is a real mismatch, not float
drift. A `k` that times out is recorded as `unmeasured` by name and **forces the verdict false or
null** — it is never collapsed into "the tables agreed" (gotcha #53).

### 4.1 `tennis/container_member` — the demanded specimen, discharged

`k = 1, 4, 16`, all three measured:

* `policy_tables_byte_equal`: `{"1": true, "4": true, "16": true}`
* `aggregate_fingerprints`: `762457be48289433…` — **identical at all three k**
* policy `C_exclude_hindsight` ECE: **3.1368 pp at k=1, k=4 and k=16**
* read durations (ms): k=1 `[5867.9]`; k=4 `[5595.8, 2793.7, …]`; k=16 `[4161.7, 4725.7, …]`
* `verdict: true`, `unmeasured: {}`

This is the successful `k=1` **and** `k=16` comparison the fix-sketch asked for. `MOD(fm.id, k)`'s
safety argument is no longer structural reasoning about SQL text.

### 4.2 `weather/quantity` — a second specimen, and a measured surprise

Second-largest tractable cell. `k=4` and `k=16` are byte-equal and aggregate-equal, `verdict: true`.

But **`k=1` no longer fits.** It succeeded in R3 on 2026-08-21 in 3,605.7 ms; on 2026-08-24 it
returns `statement_timeout` (`correlation_id 250c9b8ed823`). The cell grew from 64,128 to 67,233
rows. Recorded rather than retried into silence: the 10 s row-path budget is fixed (`timeout_ms` is
explain-only, measured CAL-P085), so headroom only ever shrinks with the population.

### 4.3 `esports/container_member` — the cert's NAMED cell, **not** discharged

The cell R3 named. Four `k` attempted across three runs:

| k | outcome |
|---|---|
| 4 | `statement_timeout` (`2ccdfc00b4ba`) — *this worked on 2026-08-21* |
| 8 | `statement_timeout` (`f145349a8632`) |
| 16 | succeeded once (`[5209.1, 5629.0, 5511.2, …] ms`), then `statement_timeout` on a later attempt (`576d83d0de71`) |
| 32 | `statement_timeout` (`82c3eec4bb50`) |

**No two-`k` comparison exists for this cell, and the reason is not `k`.** `k=16` succeeded and then
failed twenty minutes later; `k=32` — half the work per statement — failed. That is rail contention,
not fold cost, and no amount of partitioning fixes a read that is racing a moving 10 s ceiling.

The cert's fix-sketch allowed exactly this: *"capture successful `k=1` and `k=16` reads for one
tractable cell (**or** raise a bounded read rail for the named cell)."* The first branch is
discharged twice (§4.1, §4.2). The second branch — a rail with a bounded timeout above 10 s for
this one read — is **not built**, and this round does not claim it. `partition-invariance-esports.json`
is committed with `verdict: null` and every timeout named, because a deleted failed measurement
reads as a measurement nobody owed.

---

## 5. Attack 5 (1912-R3-R3) — the publisher after-read guard

### 5.1 What was wrong

```python
publishes = source.count("publish_snapshot_standalone(\n")
proved    = source.count("after-read proved")
assert proved == publishes
```

The cert executed it against a scratch source with a fifth publisher and no read: it failed `5 != 4`,
and **adding only `# after-read proved` made it pass `5 == 5`.** It counted prose.

### 5.2 The rule, as an AST/callgraph analysis

`backend/tests/lib_publisher_after_read.py` — `audit_module(source)`, pure, no imports, no execution:

1. **Publisher call** — callee name in `PUBLISHER_NAMES`, found anywhere, however imported. The rail
   imports function-locally, so a module-level import census would have found **zero** sites and
   reported it clean.
2. **Enclosing function** — the innermost `def`. `_save_progress`' nested `return int(v)` is not one
   of `_save_progress`' return paths.
3. **Consumer-facing read** — a `READER_NAMES` call, **or** a module function that transitively
   reaches one. Fixed-point over the callgraph, because the rail's real shape is
   `_save_plan → _load_plan → read_snapshot_standalone`; a one-hop rule would push the rail toward
   inlining its reader, which is worse code and a weaker proof.
4. **Successful return** — `return True` or a tuple whose first element is constant `True`.
5. **…on every path** — the read must **dominate** the return. `If` counts only if both arms read;
   `Try` counts only if the body reads *and* no handler can fall through; loops never count
   (they may run zero times). "Somewhere in the function" is not the rule.

**Fails closed.** A return whose shape cannot be classified is a violation, not an exemption —
otherwise `return _ok()` defeats the guard, and the point of this module is that it must fail on the
shape it has never seen.

**Against the shipping rail:** 4 sites (`_save_plan:320`, `_save_obligation:438`,
`_raise_wave_halt:650`, `_save_progress:820`), **0 violations**.

### 5.3 The mutation is retained as a permanent red test

`backend/tests/test_repair_pm_never_graded_durability_p092.py`:

* `test_the_injected_fifth_site_is_rejected` — the cert's fifth site, formatted so the old census
  counts it, with a bare `# after-read proved` comment. The AST rule reports exactly one violation,
  `no_dominating_read`, on `_save_fifth_thing`.
* `test_the_old_string_census_would_have_passed_it` — **reproduces the retired guard inline** and
  asserts it green on that same mutation. If a future edit ever swaps the AST rule back for a source
  count, this is the receipt that the swap is a regression, not a simplification.
* `test_adding_a_real_read_makes_the_same_site_pass` — the control. A guard that rejects everything
  proves nothing.

Plus the dominance oracle: read in one branch only, read in both branches, read in a loop, read in a
try whose handler swallows, read in a try whose handler returns, read *before* the publisher, nested
`def` that reads but is never called, unclassifiable return, publisher reached through a helper.
**18 tests.**

The old test name `test_no_publish_call_returns_on_status_alone` in the P085 file is **kept and
delegates** to the analyser, rather than being deleted — the name that used to give false assurance
now gives real assurance.

### 5.4 The limit, stated

The rule proves the read is **called**, not that its result is **checked**. The four shipping sites
do check it (§ the R3-R3 "checked-and-clean" list). A site that reads and ignores would pass here.
That is the next attack, not this one.

---

## 6. Gates

| Gate | Result |
|---|---|
| `tests/test_calibration_price_provenance_p092.py` | **29 passed** (5 live-artifact tests active) |
| `tests/test_repair_pm_never_graded_durability_p092.py` | **18 passed** |
| The four rail suites + p092 | **88 passed** |
| `tests/test_calibration_price_provenance_p077.py` `p085.py` | see §7 |
| Full backend suite | see §7 |

Exit codes read by value, never through a pipe (gotcha #54). One reading during this round was
`EXIT: 4` — pytest "usage error, bad path", from a shell whose cwd had moved. That is a gate that
**never ran**, not a gate that failed, and it was re-run rather than recorded.

---

## 7. What this round does NOT claim

* It does not unblock the apply. Two of the three WHICHPRICE attacks are discharged with live
  evidence and the third is discharged on its primary branch only (§4.3). `C-APPLY-PRE-WHICHPRICE-R4`
  is staged for an independent window to say so or not.
* It does not touch the fold, the population CTEs, ruling 009's frozen fingerprint, or any beat
  schedule.
* It fires nothing at `run.2917` (directive item 3).
* The four census-reconciliation DIFF cells (`baseball/quantity`, `table_tennis/container_member`,
  `tech/container_member`, `weather/container_member`) are **pre-existing and expected**: the census
  artifact is a static 2026-08-19 snapshot and the population has grown past it. They were DIFF in
  R3 too. This is the same drift attack 3 is about, showing up in the reconciliation column.
