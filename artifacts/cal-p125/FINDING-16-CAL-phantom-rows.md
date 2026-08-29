# 16-CAL — the published calibration curve counts some outcomes more than once

**This is a population defect in the frozen file, it is in the served payload today, and no
self-check on either rail can see it.**

`polymarket/basketball` publishes **13,116 rows standing on 7,419 distinct outcomes**. 5,697 rows —
**43.44% of the cell** — are the same outcome counted again. It is not confined to the cell that
found it: `polymarket/cricket`, the cell that reproduces the payload *exactly* on the new rail
(+0.00%), is **12.85% phantom**.

| cell | published rows | distinct outcomes | phantom | share | markets affected |
|---|--:|--:|--:|--:|--:|
| `polymarket/basketball` | 13,116 | 7,419 | **5,697** | **43.44%** | 968 of 1,522 |
| `polymarket/cricket` | 3,252 | 2,834 | **418** | **12.85%** | 193 of 1,089 |

Both measured over **every unit** of the cell, on curve `q268` / `2026-08-29T00:36:47Z`, with
`calibration_whole_vm_fold.py --phantom`.

---

## 1. Why this is arithmetic, not a judgement call

`deduped` — the CTE the producer's own docstring calls *"the final published population"* — is

```sql
deduped AS ( SELECT ro.* FROM normalized ro LEFT JOIN mode_prices mp ... )
```

one row per outcome. So `COUNT(*) > COUNT(DISTINCT outcome_id)` over `deduped` cannot be a
threshold anyone can argue about. There is no reading of the schema on which it is intended.

**And the payload agrees with the duplicated count, not the distinct one.** The served cell reports
`n = 13,135` against the rail's 13,116; `compute_calibration_payload` aggregates the same `deduped`
into buckets. So the SELF-CHECK — the strongest instrument this lane has, the one that just proved
the new rail correct to −0.14% — is blind to it **by construction**: both sides of the comparison
contain the same phantoms.

## 2. The cause, isolated by differential rather than by reading

Duplication first appears at `ranked_outcomes`. Traced through one basketball unit:

| CTE | rows | distinct key | |
|---|--:|--:|---|
| `market_info` | 310 | 310 (market_id) | clean |
| `virtual_market` | 310 | 310 (market_id) | clean |
| `ranked_outcomes` | 119 | 69 (outcome_id) | **duplicated** |
| `normalized` | 119 | 69 | inherited |
| `deduped` | 52 | 33 | inherited |

`ranked_outcomes` joins

```sql
JOIN clean_vms cv ON cv.vm_id = vm.vm_id AND cv.source = vm.source
```

and `clean_vms` is `SELECT * FROM vm_stats WHERE eligible >= 1 AND has_winner >= 1`, where

```sql
vm_stats AS ( ... GROUP BY vm.vm_id, vm.source, vm.category, vm.is_grouped,
                            vm.mutually_exclusive )
```

**Five grouping columns; the join matches on two.** Every extra `clean_vms` row for a
`(vm_id, source)` emits the whole virtual question's outcomes again.

Which column fans out, measured on the same unit:

```
clean_vms rows                 491
distinct (vm_id, source)       387     <-- what ranked_outcomes joins on
distinct + category            387
distinct + is_grouped          387
distinct + mutually_exclusive  491     <-- accounts for all of it
```

It is `mutually_exclusive`, and only `mutually_exclusive`. That column is per-MARKET and, in
`market_info`'s own words, *"defaults to True and is set for Yes/No claims and duels alike"* — so a
Polymarket game group holding a moneyline and a player prop carries both values, and every outcome
in it is published twice.

**The differential closes it.** Replacing `clean_vms` with `SELECT DISTINCT ON (vm_id, source) *`
and changing nothing else, over 16 basketball units:

```
as shipped                             rows=3221  distinct_outcomes=1859  phantom=1362
clean_vms DISTINCT ON (vm_id,source)   rows=1865  distinct_outcomes=1865  phantom=   0
```

A hypothesis that was tested and **disproved** first, recorded so nobody re-runs it: `mode_prices`
also groups by a column it does not select (`eligible`), and `deduped` LEFT JOINs it on the three
it does. That would duplicate too — but `SELECT DISTINCT` on `mode_prices` changes the phantom count
by **zero**. It is not the cause.

## 3. What it does to the number

**Unknown, and that is the honest answer — but the sign is not random.** The duplication is not a
uniform inflation that cancels in an average. It multiplies outcomes *only* inside grouped virtual
questions that mix `mutually_exclusive` values, so it re-weights the curve toward exactly the
Polymarket game-bundle population, and it does so by a factor that varies per virtual question.

Three consequences worth stating plainly:

* **Every bucket weight in the published curve is wrong** by the per-bucket duplication rate.
  `mce_closing_line = 1.89` is a weighted average over those weights.
* **Every excess-outcomes figure on the board is computed on inflated `n`.** The board ranks cells
  by `n x excess`; `polymarket/basketball`'s 16,287 is built on 13,116 rows of which 5,697 are
  duplicates.
* **Every rule this lane has benched was benched on this population** — including the five banked
  designs. A rule's ECE is not obviously invariant to de-duplication, because de-duplication is not
  uniform across the classes a rule names.

**Nothing here says any of those numbers is wrong by a lot.** It says nobody has measured them on a
de-duplicated population, and that is now a cheap thing to do.

## 4. Why it needs Alex

`precompute_calibration.py` is frozen under ruling 009. This is a change to the published
population's row identity — the most load-bearing line in the file — so it is not a build-lane fix
under ruling 134, and it is not something to slip in beside a cell rule.

**The options, and the recommendation.**

* **(a) MEASURE FIRST, then rule — recommended.** De-duplicate `clean_vms` in a read-side replica
  only, re-fold the board's cells, and publish the delta on the headline before touching the
  producer. This lane can do that now with `--phantom` and the whole-vm rail; it needs no freeze
  exception because nothing is written. The cost is one session.
* **(b) Fix it now under a ruling-009 exception.** Fastest to a correct curve, but it lands a
  population change during a freeze whose whole purpose is to hold the population still, and the
  falsifier window would have to restart.
* **(c) Disclose and defer.** Cheapest, and wrong here: this is not a known-bad *cell* like
  `polymarket/cricket` (14-CAL). It is a defect in how every cell is counted.

**Recommendation: (a).** The freeze is already not liftable in the current window (12 < 22, the ring
is rolling), so there is time to measure, and a fix shipped without the delta measured is a fix
nobody can cert.

## 5. What this does NOT change

* The whole-vm rail's repair stands. It reproduces the payload to −0.14% on `basketball` and
  +0.00% on `cricket` **because** it replays the producer's own chain, phantoms included. Fixing
  the phantoms is a separate change to a different CTE, and the rail is what makes it measurable.
* The five banked designs are not withdrawn. They are re-benchable, and 16-CAL is now the reason
  to re-bench them rather than a reason to distrust them.

## 6. Reproduce

```bash
source ~/.claude/.env
python3 backend/scripts/calibration_whole_vm_fold.py \
    --source polymarket --category basketball --roster-buckets 64 --buckets 64 \
    --phantom --roster-cache artifacts/cal-p125/roster-basketball.json
python3 backend/scripts/calibration_whole_vm_fold.py \
    --source polymarket --category cricket --roster-buckets 16 --buckets 16 \
    --phantom --roster-cache artifacts/cal-p125/roster-cricket.json
```

Artifacts: `artifacts/cal-p125/phantom-{basketball,cricket}.json`.

Guard: `test_the_fan_out_join_is_still_on_two_of_five_columns` in
`backend/tests/test_calibration_whole_vm_fold_p125.py` pins the defect **deliberately**, so that
acting on 16-CAL makes a test fail by name and carries the instruction to re-measure. A finding
that can be fixed silently is a finding that gets re-discovered.
