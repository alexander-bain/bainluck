# CAL-P125 — `polymarket/basketball` (rank 11): MEASURED at last, candidate rule found, NOT BANKED

**Verdict: the cell is measurable, it admits a one-arm rule at 2.60 pp — and that rule is benched on
a population that 16-CAL says counts 43.44% of its rows twice. It is a CANDIDATE, not a banked
design, and the thing standing between the two is one re-bench, not a new idea.**

CAL-P124 refused this cell because the id-range rail reached only 64% of it. That is fixed
(`RAIL-whole-vm-fold.md`): the whole-vm rail reproduces the published cell to **−0.14%**.

| | n | ECE | gap |
|---|--:|--:|--:|
| published payload (`q268`) | 13,135 | 4.24 | +2.96 |
| whole-vm replica | 13,116 | 4.25 | +2.96 |
| delta | −19 (−0.14%) | +0.01 | +0.00 |

Bar 3.0 (class B/C). Excess **1.25 pp** on 13,116 rows.

---

## 1. What the cell is

| | |
|---|--:|
| markets | 26,007 |
| distinct virtual questions | 5,384 |
| markets in a GROUPED question | 21,401 (**82.3%**) |
| largest single virtual question | **120 markets** |
| questions over 100 markets | 5 |

That 82.3% is why the id-range rail failed here and passed on cricket (largest question: 9 markets),
and it is the fact every reading below turns on.

## 2. The dimensions that named nothing, recorded so nobody re-runs them

* **`--by family`** — 100% `z_no_dash_suffix`. Polymarket puts the family after the last `` - `` of
  the market name and basketball market names do not carry one. The dimension that cracked cricket
  is dead here (CAL-P123 lesson 5, again).
* **`--by age`** — 100% `z_no_snapshot` (CAL-P124 measured this).
* **`--by outcomenames`** — three classes, and the **exhaustive search over all 6 subsets returns
  ZERO under the bar** (best 4.08). Not a dead dimension — a real refusal, on this partition.

## 3. The partition that named something

`--by sumband` (shape x published price-sum band):

| class | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| `bundle\|e_sum_gt_15` | 7,186 | 54.8% | 4.96 | +1.13 |
| `binary\|b_sum_1.15_2` | 1,994 | 15.2% | 10.6 | −0.14 |
| `bundle\|d_sum_5_15` | 1,178 | 9.0% | 7.1 | +6.43 |
| **`binary\|a_sum_le_1.15`** | **1,096** | **8.4%** | **24.56** | **+21.06** |
| `field1\|a_sum_le_1.15` | 1,005 | 7.7% | **1.31** | −0.1 |
| `bundle\|c_sum_2_5` | 311 | 2.4% | 6.6 | −0.42 |
| `binary\|c_sum_2_5` | 92 | 0.7% | 22.47 | +4.29 |
| `single\|a_sum_le_1.15` | 79 | 0.6% | 42.65 | −42.65 |
| `field1\|c_sum_2_5` | 60 | 0.5% | 16.68 | +16.68 |
| `field1\|d_sum_5_15` | 46 | 0.4% | 46.72 | +38.11 |
| (4 more) | 69 | 0.5% | | |

**The clean control is the headline.** `field1|a_sum_le_1.15` — a genuine partition that realized
exactly one winner, published at prices summing to ~1 — is **1.31 pp on 1,005 rows**. That is the
number cricket could not produce: cricket's clean remainder was **5.75**, which is why cricket was
ruled unrepairable. Basketball's clean core is well under the bar, so removing its dirty rows is a
repair rather than a deletion.

## 4. The candidate

Exhaustive search over all 8,070 subsets retaining >= 300 rows
(`calibration_rule_search.py`, `search-basketball-sumband.json`): **808 pass the 3.0 bar.** Most are
useless — the global optimum keeps 1,052 rows and deletes 92% of the cell. Constrained to rules that
keep the cell:

| rule (stated as a DROP) | n kept | dropped | ECE | gap |
|---|--:|--:|--:|--:|
| **drop `binary\|a_sum_le_1.15`** | **12,020** | **1,096 (8.4%)** | **2.60** | +1.31 |
| drop it + `field1\|d_sum_5_15` | 11,974 | 1,142 (8.7%) | 2.52 | +1.17 |
| drop it + `bundle\|c_sum_2_5` + `field1\|d_sum_5_15` | 11,663 | 1,453 (11.1%) | 2.46 | +1.21 |
| drop `single\|a_sum_le_1.15` alone | 13,037 | 79 (0.6%) | 4.41 | +3.24 |

**One arm, 8.4% of the cell, 4.25 -> 2.60, margin 0.40 pp against the bar.** That is a wider margin
than rank 1's banked K' (2.71, margin 0.29). The last row is the control that matters: dropping the
lone-claim class *alone* makes the cell **worse** (4.41), so the rule is not the 12-CAL filter in
disguise.

## 5. Why it is NOT banked, and it is not a small reservation

`binary|a_sum_le_1.15` is "a two-outcome market whose PUBLISHED prices sum to <= 1.15". To state that
as a rule a reader can accept, you have to know whether it means *both legs published and coherent*
or *one leg published*. `sumband` bands a SUM and cannot tell those apart, so this rail added
`--by publegs`, which COUNTS the published legs:

| class | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| `bundle\|pub4plus/4plus` | 8,669 | 66.1% | 4.4 | +1.93 |
| **`binary\|pub4plus/2`** | **2,108** | **16.1%** | 10.06 | −0.37 |
| `field1\|pub4plus/4plus` | 1,041 | 7.9% | 3.32 | +1.86 |
| `binary\|pub2/2` | 882 | 6.7% | 19.0 | +16.34 |
| `binary\|pub1/2` | 192 | 1.5% | 49.87 | +49.87 |
| `single\|pub1/1` | 79 | 0.6% | 42.65 | −42.65 |

**`binary|pub4plus/2` is arithmetically impossible** — four or more published rows from a market
with two outcomes — and it is 16.1% of the cell. Chasing it is what found 16-CAL:
`deduped` publishes **13,116 rows standing on 7,419 distinct outcomes**, so **43.44% of this cell's
published rows are the same outcome counted again** (`FINDING-16-CAL-phantom-rows.md`).

So every class in section 3 is a mixture of real rows and duplicates, in a ratio that is **not
uniform across classes** — the duplication fires on grouped virtual questions whose markets disagree
on `mutually_exclusive`, which is a property the sumband classes correlate with. The 2.60 is a real
number about the published population. It is not yet a number about the *outcomes*.

`binary|pub1/2` — 192 rows, ECE 49.87, gap +49.87, a perfectly one-sided error — is the 12-CAL
lone-claim cohort on this cell, counted, and it is **1.5%**, not the 8.4% the sumband class
suggested.

## 6. What would bank it

One re-bench, and the instruments for it now exist:

1. Re-fold `--by sumband` and `--by publegs` on a de-duplicated replica (`clean_vms DISTINCT ON
   (vm_id, source)` — the differential in 16-CAL §2, read-side only, no freeze exception needed).
2. Re-run `calibration_rule_search.py` on the result.
3. Add the holdout. **This design has no holdout split yet** — CAL-P123's lesson 2 says believe the
   split over the pooled number, and an exhaustive search over 8,070 subsets is an exhaustive search
   for an overfit. `calibration_cluster_sigma.py --out artifacts/cal-p125/sigma-basketball.json`
   has run; take the row-balanced split point from its `cluster_rows`, and use the whole-vm rail's
   `--holdout-at`, which puts the halves in the GROUP BY rather than relying on a chunk edge.
4. Name the mechanism. "Two published legs summing to <= 1.15" is a threshold; a rule needs a
   sentence about what those markets ARE.

Until then this cell's board status is **MEASURED, candidate rule at 2.60 pp, not banked** — which
is two steps up from CAL-P124's UNMEASURED and one step short of the five banked designs.

## 7. Reproduce

```bash
source ~/.claude/.env
python3 backend/scripts/calibration_whole_vm_fold.py --source polymarket --category basketball \
    --roster-buckets 64 --buckets 64 --by sumband \
    --roster-cache artifacts/cal-p125/roster-basketball.json \
    --out artifacts/cal-p125/whole-vm-basketball-sumband.json
python3 backend/scripts/calibration_rule_search.py \
    --in artifacts/cal-p125/whole-vm-basketball-sumband.json --bar 3.0 --min-share 0.7
```

First fold ~500 s cold, ~100 s with the cached roster. The search is instant.
