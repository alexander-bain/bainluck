# CAL-P122 — rank 8, `kalshi/entertainment`: the losers are not missing, they are filtered

**Pillar: TRUTH. Ship: the calibration page stops reporting a class of forecasts as
never having been wrong, when the exchange said they were wrong and we have the row.**

Status: **diagnosed on the producer's own chain, holdout-split, NO RULE BANKED, and one
banked-and-ruled rule elsewhere is CONTRADICTED.** Nothing in this document changes a
published row; `git diff origin/master...HEAD -- backend/app frontend` is empty on this
branch.

| | |
|---|---|
| board rank | 8 of 14 (corrected board, CAL-P120 §6g) |
| published cell | `kalshi/entertainment` — ECE **5.21** pp, n **8,355**, gap **+1.07** |
| class / bar | C_exchange_standalone / **3.0** pp |
| excess | **+2.21** pp = **18,465** excess-outcomes |
| curve | `2026-08-29T00:36:47Z`, population `q268` |
| **the cell's honest number** | **6.30 pp on n 8,850** — see §3 |

---

## 0. The three cheap checks first, because three queues have now paid for them

**Can the rail reach the cell?** Yes, and this is its best reproduction on a Kalshi cell
after rank 6.

| cell | exact rail | payload | Δn |
|---|---|---|--:|
| `kalshi/crypto` (CAL-P121) | 4,566 / 7.61 / +1.83 | 4,565 / 7.60 / +1.84 | +0.02% |
| **`kalshi/entertainment`** | **8,418 / 5.21 / +1.04** | 8,355 / 5.21 / +1.07 | **+0.75%** |
| `kalshi/economics` (CAL-P114) | 28,738 / 5.29 / −0.47 | 28,613 / 5.29 / −0.47 | +0.55% |

ECE reproduces to the second decimal. Every number below is on that rail.

**Is the cell's name evidence of what is in it?** CAL-P121's lesson 5 says run `--by series`
in the first five minutes. Run: **the label is TRUE here.** 155 series, and the mass is music
charts and streaming — `KXARTISTSTREAMS` 12.4%, `KXBBCHARTPOSITIONSONG` 5.6%,
`KXBBCHARTPOSITIONALBUM` 4.8%, `KXALBUMSALES` 4.5%, `KXRT` (Rotten Tomatoes) 4.4% — plus
Netflix rankings, Emmy/Cannes/ESPY nominations and reality-TV eliminations. Nothing here is
mis-shelved. **The lesson still paid**: the answer arrived in ninety seconds and the
alternative was assuming it.

**Is the cell's σ a claim about independent observations?** Measured, not assumed —
`calibration_cluster_sigma`, 2,000 resamples, seeded:

```
kalshi/entertainment — 8,418 published rows / 1,550 distinct markets / 5.43 rows per market

  basis                                 SE pp    sigma
  row grain (the board today)           0.545     4.06
  market grain (perfect-corr bound)     1.270     1.74
  cluster bootstrap (MEASURED)          0.474     4.66

  bootstrap ECE 95% interval  [4.43, 6.27] pp      design effect  0.76
```

**ESTABLISHED at 4.66σ**, and the bootstrap's own 95% lower bound (4.43 pp) clears the 3.0 bar
without reference to any standard-error convention.

### 🔴 This is the first cell where CAL-P114 §3a's shortcut would have changed a verdict

The market-grain bound reads **1.74σ — under `SIGMA_GATE = 2.0`**. Substituting the market
count for `n`, which §3a proposed and CAL-P120 effectively applied, would have taken this cell
**off the board**. Measured, it belongs on it at 4.66σ. Two cells (economics, crypto) were
already known to be mis-corrected in opposite directions by that shortcut; this is the third,
and the first where the error is decisive rather than academic. **The recommendation put to
Alex — report `effective_n` and `design_effect` as a pair, do not redefine the denominator —
now has a case behind it, not just a caveat.**

---

## 1. The cell in one table

`--by sumband` (shape × published price sum), the producer's own chain:

| class | n | share | ECE | gap | mean price | actual |
|---|--:|--:|--:|--:|--:|--:|
| `bundle` ǀ 5–15 | 2,442 | 29.0% | 5.46 | +0.19 | 51.62 | 51.43 |
| `field1` ǀ **≤ 1.15** | 2,416 | 28.7% | **1.66** | **+0.25** | 15.23 | 14.98 |
| `bundle` ǀ 2–5 | 1,373 | 16.3% | 8.61 | −0.26 | 37.11 | 37.36 |
| `field1` ǀ 1.15–2 | 574 | 6.8% | 9.21 | **+8.63** | 22.22 | 13.59 |
| `field1` ǀ 2–5 | 499 | 5.9% | 25.21 | **+25.21** | 34.83 | 9.62 |
| **`single` ǀ ≤ 1.15** | **395** | **4.7%** | **32.48** | **−32.48** | 67.52 | **100.00** |
| `bundle` ǀ 1.15–2 | 290 | 3.4% | 4.96 | −3.29 | 22.57 | 25.86 |
| `bundle` ǀ ≤ 1.15 | 181 | 2.2% | 19.83 | −15.34 | 24.99 | 40.33 |
| `field1` ǀ 5–15 | 155 | 1.8% | 47.87 | **+47.87** | 56.26 | 8.39 |
| `binary` ǀ ≤ 1.15 | 93 | 1.1% | 12.63 | −3.48 | 59.96 | 63.44 |

Two things jump out and they are different kinds of thing.

**The `field1` ladder is the familiar one.** Sorted by published price sum it runs
**+0.25 → +8.63 → +25.21 → +47.87**, monotone, one-directional, and present at the same sign
in both holdout halves. This is precisely the shape CAL-P114 measured on `kalshi/economics`
and precisely what RULE E's structural test (a market whose published prices sum above 1.15 is
not a partition, whatever it realized) exists to catch. Nothing new is needed to name it.

**The `single` class is a 100% win rate.** 395 rows, every one a winner, at an average
published price of 0.675. That is not a calibration reading. **A population that cannot
contain a loss has no error to report**, and the −32.48 pp the board is charging this cell for
it is arithmetic on a number that was never a forecast outcome.

`--by market_type` gives the class a column-level name with no residue: the 395 rows are
exactly the cell's `unshaped` markets, and `unshaped` is exactly 395 rows.

**The `bundle` half is not a directional defect and must not be treated as one.** Every bundle
band's *gap* is within 3.3 pp of zero and the two largest are within 0.3. Its ECE is
bucket-level, two-sided error — the honest kind. §4's grid shows what happens to a rule that
forgets this.

---

## 2. 🔴 The `single` class is OUR defect, it has a line number, and it is not the one anybody has been citing

CAL-P112 met this class first, on `polymarket/esports`, and named it **the winner-only single
capture**:

> 453 markets, 453 outcomes, **453 winners — a win rate of 1.000 at an average published price
> of 0.59**. `orphan_partition_markets` deliberately does not catch this ("a standalone Yes/No
> claim with one outcome is a complete, scoreable prediction"), and that reasoning is right in
> general and false here: **a population that is 100% winners is not a set of Yes/No claims
> being scored, it is one-sided capture.**

That conclusion became **RULE E2**, which excludes the class, and E2 ships on the
`(source, category)` allowlist Alex ruled on 2026-08-28 — so it lands on rank 2, and rank 6's
RULE C inherits the same allowlist entry.

**"It is one-sided capture" is a claim about the CAPTURE, and it has never been measured.**
"100% winners" is equally consistent with a second explanation: the losers were captured, were
graded, and are removed by a filter. There is a filter that does exactly that, three CTEs
before anything E2 can see, and it is one line —
`precompute_calibration.py:2067-2071`:

```sql
clean_vms AS (
    SELECT * FROM vm_stats
    WHERE eligible >= 1
      AND has_winner >= 1          -- <-- this one
),
```

`has_winner` is counted over the **virtual market**. A market grouped with siblings is carried
by any winner in the group, so its losers publish normally. A **lone claim** — an ungrouped
market whose virtual market is itself, holding exactly one captured outcome — has nobody to
carry it, **so it publishes if and only if it won.**

### The producer says the opposite, twice, and both carve-outs are unreachable

Queue 299 rung 1 exempts the class on purpose:

```python
def market_has_no_winner_authority(n_outcomes, n_winners):
    """... A 1-outcome market is judged by market_is_orphan_partition instead
    (a lone Yes/No claim that legitimately resolved No is not an authority failure)."""
    return n_outcomes >= 2 and n_winners == 0
```

and `orphan_partition_markets` then declines to catch it too — it requires
`market_type = 'field'`, and these are `unshaped`. **Both carve-outs are dead letters for a
lone claim: `clean_vms` deleted the row before either predicate is evaluated.** The gate
predates Queue 299 by three months (#691, 2026-05-28); Queue 299 wrote a careful exemption for
a row that no longer reaches it.

### The instrument, and what it measures

**`backend/scripts/calibration_missing_loser_census.py`** (new file, read-only, 28 guards /
12 mutations / 12 reds). It builds on `_calibration_population_ctes` — the producer's own
function — and reads `vm_stats`, the CTE `clean_vms` filters. **Selecting from `vm_stats`
instead of `clean_vms` IS the counterfactual**: the same population, one predicate earlier. It
re-implements nothing, and a guard test asserts the gate is still in the frozen file so the
instrument goes RED rather than printing a zero if the defect is ever repaired (gotcha #53).

It splits the gate's shadow into two arms, because only one is a defect:

```
kalshi/entertainment — the gate's shadow
  arm                                      n      ECE      gap  winrate
  A_also_no_winner (rung 1 owns these)  1,622    35.00   +35.00     0.0%
  B_lone_claim (UNIQUELY dropped)         432    51.91   +51.91     0.0%
```

`A_also_no_winner` is a virtual market of ≥2 outcomes that graded nobody. Queue 299 rung 1
removes those on its own account and is right to: with `is_winner` defaulting to False, an
all-loser multi-outcome market is indistinguishable from an ungraded one. **Reported so the
total cannot be mistaken for the defect, never counted as one.** A census that printed one
number here would claim 2,054 where the defensible claim is 432.

### The 432 are graded losses, not ungraded rows — and the writer settles it

Every one satisfies the published eligibility contract: opening price in (0, 1), the Kalshi
bid/trade evidence predicate, and `resolution_source` on the **calibration-truth allowlist**.
Their source is `api_settlement`, and `backfill_winners.py:411-419` and `:5809-5815` write it:

```sql
UPDATE futures_outcomes SET is_winner = false, resolution_source = 'api_settlement', ...
```

**One statement, both columns, driven by Kalshi's own `result = 'no'`.** An `api_settlement`
row with `is_winner = false` is an affirmative NO from the exchange, not a default. (The rows
where that is *not* true are already excluded: of the raw lone-claim losers, 139 carry
`clean_resolution`, 59 carry NULL and 37 carry `all_losers` — none is on the allowlist, and
none is in the 432.)

### The one approximation, and its direction is known

The sweep is chunked on `fm.id`, and `virtual_market`'s grouping is evaluated inside a chunk,
so a market production groups with a sibling in another chunk can read ungrouped here.
**Chunking can only ever over-populate this class, never under-populate it** — the census is
an upper bound and the bound points one way. `--edge-check` re-runs the whole sweep at half
the width and prints both totals rather than describing the risk.

---

## 3. What the cell actually reads

```
  THE LONE-CLAIM CLASS, published vs whole
    population                               n      ECE      gap  winrate
    published today (winners only)         395    32.48   -32.48   100.0%
    with its losers restored               827    21.09   +11.60    47.8%

  THE CELL
    published today                      8,418     5.21    +1.04    34.1%
    with lone-claim losers restored      8,850     6.30    +3.53    32.5%
```

Three readings a reader should not skip:

1. **The sign REVERSES on the class.** Published, the cell is charged −32.48 pp for a
   population "under-priced" by a third. Restored, the same markets are **over**-priced by
   11.60. The board's number for this class is not too big; it is pointing the wrong way.
2. **The honest cell is WORSE, not better — 5.21 → 6.30.** The filter has been flattering us.
   Per CAL-P114 §2, an ECE that rises because two real errors stopped cancelling is the more
   honest number, and this lane does not get to prefer the smaller one.
3. **The counterfactual is exact, not modelled.** A restored lone-claim row's path through the
   rest of the chain is determined: `is_multi` is `is_grouped OR eligible >= 3` and both are
   false by the class's definition, so the row takes `deduped`'s `ELSE ro.rn = 1` branch;
   `rn` partitions by `vm_id` and the vm holds one row, so `rn = 1`; `is_mex_normalized` needs
   `survivor_n >= 3`, so `adj_opening_probability` is the raw curve price. It publishes, at
   that price, in that bucket, as a loss.

### The holdout says it is present in both halves and GROWING

Split at `market_id 13096338`, taken from the published population's own row-balanced median
(`cluster_rows`, 4,216 / 4,202 — lesson 2):

| half | published (winners only) | losers dropped |
|---|---|---|
| OLD | 205 rows, 100.0% winners | **60** |
| NEW | 190 rows, 100.0% winners | **372** |

**No sign reversal, and the newer half carries 6.2x the dropped rows.** This is not a back
catalogue that a forward fix leaves behind (contrast rank 1's R1/R2, where 1,258 of 1,284 rows
are in the OLD half). It is live and accelerating.

---

## 4. 🔴 THE RULE: none is banked, and the reason is the point

Eight policies, benched on the producer's own chain, on the published population **and** on
the honest one, pooled and on both holdout halves. `S` = exclude the lone-claim class,
`E` = RULE E (keep only published sum ≤ 1.15), `F` = drop `field1` above 1.15, `B` = drop
bundles, `R` = restore the 432.

| policy | POOLED | OLD | NEW | |
|---|---|---|---|---|
| **A_today** (published, control) | 8,418 / **5.21** | 4,205 / 5.30 | 4,213 / 5.70 | — |
| **A2 honest control** (restored) | 8,850 / **6.30** | 4,265 / 5.22 | 4,585 / **7.97** | the real starting line |
| S (exclude lone class only) | 8,023 / 4.85 | 4,000 / 4.80 | 4,023 / 5.61 | fails |
| B (drop bundles) | 4,132 / 6.30 | 2,205 / 5.70 | 1,927 / 8.33 | 🔴 **worse than nothing** |
| E (keep sum ≤ 1.15) | 3,085 / 5.10 | 1,679 / 4.97 | 1,406 / 7.05 | fails |
| **S + E** | **2,690 / 1.27** | 1,474 / **2.17** | 1,216 / **2.38** | **passes — and see below** |
| S + F + B | 2,509 / 1.86 | 1,405 / 2.87 | 1,104 / 2.15 | passes — same objection |
| **E, scored on the honest population** | **3,517 / 5.75** | 1,739 / 3.88 | 1,778 / **9.61** | 🔴 **fails, and fails worse** |
| R + F (restore, drop `field1` > 1.15) | 7,622 / 5.40 | 3,670 / 5.48 | 3,952 / 6.43 | fails |
| R + F + B | 3,336 / 6.15 | 1,670 / 4.22 | 1,666 / 9.81 | fails |

**Read the two bold rows together. They are the same rule.**

`S + E` lands the cell at **1.27 pp** — the best number any policy has produced on any cell on
this board. Scored against the corrected population, the identical predicate reads **5.75 pp
and fails both the bar and the NEW half at 9.61.** The entire 4.5 pp difference is the 395
rows `S` deletes, and those rows are one side of a two-sided population that our own filter
made one-sided.

> **A rule that clears the bar on the published population and fails on the true one has not
> fixed a cell. It has deleted the evidence that the cell is broken.** `S` *is* RULE E2 wearing
> this cell's name.

So: **no rule is banked for rank 8, and the conveyor does not get a fifth design out of this
cell.** What it gets instead is a named, measured, line-numbered defect that is ours, a
correction to a design that is already ruled, and an instrument that lets the measurement lane
size it everywhere else without this lane spending another cycle (ruling 134).

### What would actually clear the cell, stated so nobody re-derives it

Nothing measured here does. After the repair the residual is the `field1` ladder (1,228 rows,
monotone in the sum band) on top of a bundle half whose gap is ~0 and whose ECE is two-sided.
**R + F is 5.40 and does not pass.** The next honest question for this cell is what the
`bundle` half's two-sided bucket error is made of — `KXARTISTSTREAMS` alone is 1,048 rows at
ECE 16.4 / gap −7.89, the largest single error mass in the cell, and no queue has read it.
That is a diagnosis, not a rule, and it is **parked (CAL-P122-2)** rather than guessed at.

---

## 5. Owed to Alex

### 12-CAL — the curve publishes winners and drops losers for lone claims. Three options.

**The finding.** `clean_vms`' `has_winner >= 1` is evaluated over the virtual market. For an
ungrouped single-outcome market it means *publish if and only if it won*. On
`kalshi/entertainment` that is **432 authoritative graded losses removed and 395 winners kept**,
and the class is published as 395/395 instead of 395/827.

**Why it is yours and not this lane's.** Fixing it changes the published curve, in a source and
category the freeze covers, and it makes the headline **worse** — this cell alone goes
5.21 → 6.30. CAL-P120 set the standing rule and it binds here: *a lane must not quietly change
a headline in either direction, least of all the one that flatters it.*

| | option | what happens |
|---|---|---|
| **(a)** | **RECOMMENDED — narrow the gate to `has_winner >= 1 OR the vm is a lone claim with an authoritative resolution`, then re-measure the board.** | The rows return as forecasts, graded as the exchange graded them. Queue 299's stated intent starts being true. The published number rises. |
| (b) | Leave the gate and **exclude** the lone-claim class by rule (this is E2). | The number stays low and stays wrong; ~2.7%+ of a cell is deleted rather than scored, and the disclosed-exclusion total grows for a defect that is ours. |
| (c) | Leave both and disclose the asymmetry on the page. | Honest, but it publishes a class we know is unscoreable and asks the reader to discount it. |

Option (a) is the only one that ends in a true number. It is also the only one that makes
CAL-P112's own sentence — *"a standalone Yes/No claim with one outcome is a complete, scoreable
prediction"* — true in the product rather than only in a docstring.

### 13-CAL — 🔴 RULE E2 is ruled, unbuilt, and its premise is disproven. Hold it.

E2 rides the `(source, category)` allowlist Alex approved on 2026-08-28 for rank 2, and rank
6's RULE C inherits the same entry. Its stated justification is *"it is one-sided capture"*.
Measured on `kalshi/entertainment`, the capture is two-sided and the **filter** is one-sided.

**E2 must not land before 12-CAL is decided.** If (a) is taken, E2 has no population left to
exclude in this cell and its scope everywhere else must be re-derived from the corrected
population — not from the census that named it. If (b) or (c) is taken, E2 is still the right
mechanical answer but its *rule text* is wrong and must say what it actually does: *"we drop a
class our own population filter has made unscoreable"*, not *"the exchange only gave us
winners"*. **A published exclusion whose stated cause is false is the same defect as an
exclusion that outlives its cause (§6f clause 4).**

**Scope of the contradiction, measured where measured:** `kalshi/entertainment` 432 losers
against 395 published winners. Whether E2's origin cell (`polymarket/esports`, 453/453) and the
other ruled cells carry the same class is the first thing 12-CAL needs and it is a
measurement-lane job on the instrument this queue shipped — **parked CAL-P122-1**, one command
per cell.

---

## 6. Parked, not dropped

* **CAL-P122-1 — run the missing-loser census on every queued cell.**
  `python3 backend/scripts/calibration_missing_loser_census.py --source S --category C`.
  Priority order: `polymarket/esports` (E2's origin and the 453/453 claim),
  `kalshi/economics` and `kalshi/crypto` (the two ruled cells the allowlist reaches),
  `polymarket/economics` (CAL-P114 recorded a 506-row single class at 43.16 ECE / −43.16 gap —
  the same signature). ⚠️ The row path rate-limits at 60/min; space the runs or the sweep dies
  on a 429 mid-flight and the partial reads as a small class.
* **CAL-P122-2 — what is the `bundle` half of `kalshi/entertainment` made of?** 4,286 rows,
  50.9% of the cell, gap within 3.3 pp of zero at every price-sum band and ECE 4.96–19.83:
  two-sided bucket error, which is the honest kind and therefore the kind nobody has read.
  `KXARTISTSTREAMS` is 1,048 rows at 16.4 / −7.89 and is the largest single error mass in the
  cell. **Not a rule candidate until somebody reads it** — CAL-P114 caught this program
  inventing a mechanism out of a plausible fold once already.

## 7. The exit-exam item this closes, and the lead it refutes

Exit-exam item 3 carries `kalshi entertainment` as *"PARTLY diagnosed — the settlement-timing
rival is UNKNOWN, not refuted"*, with the strongest lead in the exam being CAL-P026's
`price_moved` split of bucket 9: **816 moved rows at −27.5 pp against 98 unmoved at −8.1 pp**,
read as consistent with settlement-collapse.

Folded on the published cell today, `--by price_moved` reads:

| cohort | n | ECE | gap |
|---|--:|--:|--:|
| `moved` | 6,117 | **4.96** | +0.16 |
| `unmoved` | 2,301 | **6.37** | +3.38 |

**The moved half is the BETTER half, cell-wide.** That does not refute the bucket-9 reading on
its own terms — it is a different population — but it removes the cell-level warrant for
treating settlement-timing as this cell's mechanism, and `--by cpdrift` says the same thing
from the other side: the coin-flip classes CAL-P117 found dominating rank 1 are **3.8% of this
cell** (`a_forced_to_half` 284 rows, `b_pulled_to_half` 36), and the 61.5% `d_normal` majority
carries a 6.04 ECE on its own.

**Item 3's entertainment half now has a named diagnosis, and it is not the one the exam
predicted.** The exam expected *"an exclusion with a count"*; the measured answer is *a
population filter of ours, and the count belongs on the other side of the ledger.*
