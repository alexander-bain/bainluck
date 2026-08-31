# CAL-P134 — the Kalshi ladder book was invisible to the instrument built to find it, and once it is visible the price rule refuses on two cells running

Published number **1.89 pp, FLAT** (twentieth reading, population still `q268` /
`2026-08-29T00:36:47Z` — unmoved across twenty readings and thirteen sessions;
per §6e a re-publish is not a datapoint).

Freeze gate at session start AND end: `2/24 clean, 22 misses, NOT_MET`. The
freeze HOLDS. Unchanged from CAL-P133's hand-off.

---

## 0. WHAT THIS SESSION DID, IN ONE PARAGRAPH

CAL-P133 built `--by mono`, the generalized nested-ladder price law, and parked
"run it on the rest of the board" as the obvious next move. The first cell on
that list — `kalshi/economics`, rank 2, 65,524 excess-outcomes, the cell where
threshold ladders were most certain to exist — folded to **46 families and one
condemned pair**. That reads as an all-clear and is nothing of the kind: 4,621
of the cell's 7,590 markets are cumulative ladders, and the instrument could not
see a single one. Fixing the blindness produced a rung grammar Kalshi actually
writes, a second and strictly stronger law over the same ladders, and **two
replicated refusals** that between them close the price rule at this site.

---

## 1. THE BLINDNESS, AND WHY IT REPORTED ITSELF AS A CLEAN CELL

`--by mono` has two rung sites. The NAME site (one market per rung, price = the
`yes` leg) is the one it folds. The OUTCOME site existed in the module but was
wired to exactly one grammar: a bare `2400+` leg, every leg of the market.

Kalshi writes neither. It puts the whole ladder inside one market's outcome list
in three shapes this repo had never parsed:

```
Above 410M          above $68.25          7,175 or above
```

Two consequences, and the second is the one worth remembering:

1. `parse_plus_bracket` refuses every one of them.
2. **`MONO_ROWS_SQL` cannot even see them** — it keys on a leg literally named
   `yes`, and these markets have no such leg. So the pre-pass did not report
   "4,621 markets refused by the grammar". It reported 7,590 rows scanned, 46
   families, 45 of them singletons. A reader with the census in front of them
   would have concluded the cell has no ladders in it.

That is gotcha #53 and lesson 16 in one object: **a check for a thing by one
grammar is blind to a book that uses another, and it reports that blindness as
an all-clear.** The `mono` fold output is kept at
`fold-kalshi-economics-mono.txt` so the all-clear is on the record next to what
was actually there.

## 2. THE TRUTH LAW — STRONGER THAN THE PRICE LAW, AND IT IS NOT LEAKAGE-FREE

Reading a real ladder to find out why the parser refused it turned up something
the price law cannot say. Market `29210103`, *US CPI inflation for May 30, 2026*,
every leg `api_settlement`:

```
  Above 2.04%   priced 0.010   graded WON
  Above 2.14%   priced 0.990   graded WON
  Above 2.49%   priced 0.050   graded LOST
```

The prices are a monotonicity violation. But market `6175766` (*Brent crude*)
carries something with no defence at all: `above $116` graded **LOST** while
`above $117` and `above $118` graded **WON**. If Brent cleared 117 it cleared
116. At least one of those labels is wrong, and no fact about the world makes
both correct.

Containment settles every rung at once — `is_winner(above X) == (V > X)` — so on
a descending family the graded results, read in ascending rung order, can only
be `True … True False … False`. `truth_reversals()` in
`app/utils/ladder_monotonicity.py` is that law.

🔴 **THE ONE SENTENCE THAT MUST TRAVEL WITH EVERY NUMBER BELOW.** Every other law
in that module is a function of names and prices, which is what lets a holdout
test stability rather than leakage. **This one reads `is_winner`.** A rule built
on it is a truth-ELIGIBILITY finding of the pass2_loser kind — rows removed
because their ground truth is provably self-contradictory — and it is **not** in
CAL-P133's leakage-free class. `truth_dim` and the module both say so in prose,
and a guard asserts the sentence is still there.

Two confounds are controlled rather than assumed. `is_winner` is nullable
DEFAULT false, so only a leg carrying a `resolution_source` is read as graded.
And the population is split by resolution authority, because **the split is the
finding**.

### 2a. The result: the guesser fails a pure-logic test 74× more often than the settlement feed

`kalshi/economics`, raw cell, from the shipped predicate's own pre-pass census:

| band | ladders | truth pairs | reversal pairs | ladders broken | share |
|---|---:|---:|---:|---:|---:|
| all-authoritative | 3,888 | 128,891 | **16** | **13** | **0.3%** |
| contains a pass-2 guess | 158 | 21,207 | **148** | **35** | **22.2%** |

Guess-containing ladders are 3.9% of the population and carry 90% of the
reversals. This is the first falsification test the resolution pipeline has ever
had that uses no model, no price and no second source — only logic — and it
indicts the guesser at 74× the settlement feed's rate.

**The settlement feed is not clean either**, and that is the part worth filing.
Thirteen all-authoritative ladders are logically impossible, e.g. `30784010`
*S&P price on Jun 2, 2026 at 4pm EDT?* — `above 7000` graded LOST, `above 7025`
graded WON.

**Control:** the same law on `kalshi/crypto` fires **0 times in 36,591
authoritative pairs across 1,078 ladders**. The law is not manufacturing
violations; it finds none where there are none.

## 3. THE PUBLISHED FOLD — AND THE REFUSAL IT FORCES

⚠️ Lesson 19, applied first this time. Everything in §2a is a RAW-CELL count.
The exact rail on the published population is the only thing that decides
anything.

### `kalshi/economics --by truth --holdout-at 25928982` (self-check +5.48% rows)

| arm | n | share | ECE | gap |
|---|---:|---:|---:|---:|
| `b_price_reversed` | 19,212 | 63.7% | 6.50 | −0.89 |
| `z_not_a_cumulative_ladder` | 7,674 | 25.4% | **3.38** | +1.80 |
| `c_ladder_clean` | 3,191 | 10.6% | **6.90** | −5.70 |
| `a_truth_reversed` | 104 | 0.3% | **17.79** | +15.57 |

### `kalshi/crypto --by truth --holdout-at 57542639` (self-check +1.29% rows)

| arm | n | share | ECE | gap |
|---|---:|---:|---:|---:|
| `b_price_reversed` | 4,149 | 89.7% | 7.21 | +1.89 |
| `c_ladder_clean` | 402 | 8.7% | **9.21** | −2.39 |
| `z_not_a_cumulative_ladder` | 73 | 1.6% | 20.21 | −12.68 |
| `a_truth_reversed` | — | — | — | (none exist) |

**REFUSAL 1 — the price law is not an exclusion rule at this site, on two cells
running.** On both cells **the arm the rule would KEEP scores WORSE than the arm
it would DROP**: 6.90 vs 6.50 on economics, 9.21 vs 7.21 on crypto. Dropping
price-incoherent ladders leaves behind a worse population than it removes. It
reproduces in both holdout halves on crypto (OLD 7.67 vs 7.02, NEW 11.4 vs 9.94)
and in sign on economics.

🔴 **AND IT IS THE OPPOSITE SIGN FROM CAL-P133.** The identical law at the NAME
site on `polymarket/economics` read `drop` 10.87 against `coherent` 4.47 — a
2.4× hit. Same law, same instrument, different source and different site,
**verdict inverted**. CAL-P133's result must not be generalized past the site it
was measured on. This is lesson 1 in its sharpest form so far and it is now
lesson 20.

**REFUSAL 2 — the truth arm is real, reproduces, and is far too small to be an
exclusion rule.** `a_truth_reversed` is the worst arm anywhere on this board at
**ECE 17.79** and it holds in both halves (OLD 26.49, NEW 14.04) — but it is
**104 rows, 0.3%** of a 30,181-row cell. Lesson 18: an exclusion rule can only
remove a defect that is concentrated. Removing all 104 rows cannot move a cell
from 5.39 toward the 3.0 bar. **No design banked.** Its value is diagnostic, not
calibrational — see §2a and the Alex item.

## 4. THE STRUCTURAL FINDING NOBODY WAS LOOKING FOR

On `kalshi/economics` the cumulative-ladder mechanism covers **74.6% of the
published cell** (22,507 of 30,181 rows), and every ladder arm sits at 6.5–6.9
against **3.38** for the non-ladder remainder. **The cell's error IS its ladder
book** — roughly double the rest of the cell — but it is spread evenly across
coherent and incoherent ladders alike, which is exactly why no exclusion rule
reaches it. This is a recalibration/ingest shape, not a row-drop shape, and it
converges with the parked **CAL-P132-1** slope fit.

⚠️ **This does NOT replicate on crypto and must not be quoted as if it did.**
Crypto is 98.4% ladder, so its `z` arm is 73 rows and there is no control to
compare against. One cell, one observation.

## 5. WHAT SHIPPED

* **`app/utils/ladder_monotonicity.py` (+~200 lines)** — `parse_cumulative_leg`
  (the three Kalshi leg shapes plus the existing `X+`),
  `cumulative_outcome_ladder`, `truth_reversals`, `outcome_ladder_report`. The
  outcome site's whole safety argument is unchanged and is what makes the
  extension legal: **every** leg must be a cumulative threshold pointing the
  **same way**, no duplicate rung, or the market is refused outright — because a
  `quantity` market's legs are usually mutually exclusive brackets (`<5`, `5-6`,
  `>16`) that partition rather than nest, and condemning those would delete
  correctly priced markets. Still INERT: `grep -rl ladder_monotonicity
  backend/app` returns only the file itself.
* **`--by truth`, rail dimension #19** — `TRUTH_ROWS_SQL` carries no name filter,
  same as `MONO_ROWS_SQL`, so Python stays the only definition of a rung.
  economics **268 s**, crypto **92 s**.
* **`backend/tests/test_ladder_monotonicity.py` — 72 → 116 guards** (44 new).
  Every leg string in them is copied from a real `kalshi/economics` market.
* **The context-routing table.** `main()` routed per-chunk context with a
  two-branch `if/else`; a third dimension took the `else` and overwrote `_MONO`.
  That is an empty partition at the end of a fifteen-minute fold rather than an
  error at the start — the same failure the `PER_CHUNK_CONTEXT` guard exists to
  stop, one layer down. Now a table, with a guard asserting it covers every
  registered dimension.
* **`artifacts/cal-p134/`** — both census scripts (the row pull is cached to
  `rows-kalshi-economics.json.gz`, ten minutes of production load, so every
  re-analysis after the first is free), both folds, the raw census.

## 6. LESSON 20 — THE SAME LAW CAN HAVE OPPOSITE SIGNS AT TWO SITES OF THE SAME MECHANISM

Lesson 1 says an inherited mechanism is a hypothesis until the exact rail scores
it. CAL-P134 is the version of that with the rail on both sides: CAL-P133's rail
result on `polymarket/economics` (name site) said the price rule works, 10.87 vs
4.47. The same rail, same law, on `kalshi/economics` and `kalshi/crypto` (outcome
site) says it is backwards, twice. **A rail result is a claim about the cell AND
the site it was measured at.** Carrying it to a new site is a hypothesis again,
at full strength, and the cost of not re-measuring here would have been a banked
design that made two cells worse.
