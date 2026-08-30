# CAL-P137 — both of CAL-P136-2's hypotheses are dead, and one cell's defect turns out to be in our own rows

Published number at session start and end: **1.88 pp** (`generated_at`
`2026-08-29T23:35:53Z`, `q268`, 925,400 outcomes, NEEDLE 30/49). **FLAT** —
byte-identical at both ends, because the producer did not beat during this
session either. The freeze gate is unchanged at `2/24 clean, NOT_MET`, so there
is still exactly ONE post-repair beat and the falsifier re-measure, the amended
N-of-M window check and the re-baseline artifact all stay shut.

CAL-P136 reached the Polymarket O/U book for the first time and then refused to
bank a rule, because the package condemns 28–70% of what it ladders and the
holdout reverses on two cells of four. It parked the diagnosis as **CAL-P136-2**
with two hypotheses. This queue tested them.

**Both are refuted, on all four cells. So is a third the data suggested on the
way — on three of them. And what the evidence points at instead is not a ladder
defect at all: on `polymarket/baseball` it is a leg-assignment bug in our own
rows, which the monotonicity law has been correctly detecting all along.**

🔴 **Four cells, four different answers.** Baseball is the leg swap. Basketball
and esports are families that hold a settled rung and a live one at the same
time. Soccer — the largest laddered book of the four — is mostly *one-point*
disagreements that none of these mechanisms explains, and where the "it is just
noise" reading survives. There is no single sentence that covers the O/U book,
and the most useful thing this queue produced may be the evidence that there
never was one.

No rule is banked. Still five. But the reason is now completely different from
CAL-P136's reason, and that difference is the result.

---

## 1. What was measured, and on what

`pull_eras.py` re-pulls CAL-P136's exact rows with the `COALESCE` **split into
its two branches** plus the two as-of stamps that exist. Population check against
`artifacts/cal-p136/legs-*.json.gz`, per cell:

| cell | p136 rows | p137 rows | new | price drift | structural mismatch |
|---|---|---|---|---|---|
| baseball | 64,889 | 64,894 | 5 | **0** | **0** |
| basketball | 25,825 | 25,825 | 0 | **0** | **0** |
| esports | 102,194 | 102,232 | 38 | **0** | **0** |
| soccer | 190,155 | 190,198 | 43 | **0** | **0** |

Zero price drift and zero structural mismatch across 383,063 shared markets, so
every number below is comparable to CAL-P136's table row for row (lesson 14).
Arm D reproduces CAL-P136's published drop rates exactly — baseball 28.92%,
basketball 69.70%, esports 56.18%, soccer 27.65% — which is the self-check that
the two sessions are measuring the same thing.

`markets_with_more_than_one_leg_of_a_name` is **0** on every cell, so the
`MAX(CASE WHEN ...)` hazard both pulls carry is a measured zero rather than an
assumption.

---

## 2. 🔴 Hypothesis (b) — the COALESCE mixes two eras — REFUTED, three ways

Reading the writer first changed the instrument. `compute_calibration_prices`
does not compute one thing: it has **five producers** — Part A (last snapshot
before the EVENT's commence_time), A2 (before the MARKET's), B (first snapshot
≥1h after opening, i.e. a *settled* price), C (last non-extreme snapshot before
start) — and a **Fallback that executes `SET calibration_probability =
fo.opening_probability`**. Nothing records which one ran.

So a row on the CAL branch is not necessarily a row from the calibration era.
The Fallback leaves a signature — `calibration_probability = opening_probability`
— which `backfill_winners` itself reads as exactly that signal in two places, and
`pull_eras.branch` classifies it as its own state (`cal_eq_open`) rather than
folding it into either branch. It is a signature and not a proof, and it biases
the class large, which is the safe direction for a suspect.

**(i) No association.** Condemnation rate, era-pure families vs era-mixed:

| cell | pure | mixed | condemned that are mixed | eligible that are mixed |
|---|---|---|---|---|
| baseball | 22.11% | **21.69%** | 18.2% | 18.4% |
| basketball | 55.97% | **54.35%** | 8.0% | 8.3% |
| esports | 30.01% | 66.80% | 40.3% | 23.3% |
| soccer | 20.73% | 34.18% | 13.3% | 8.5% |

On baseball and basketball mixed families are condemned at *exactly* their base
rate — 18.2 against 18.4, 8.0 against 8.3. That is a textbook null. Esports and
soccer do show an association, and (ii) kills it on both.

**(ii) No counterfactual.** Arm H prices the whole book from the calibration ERA
— the CAL column minus the Fallback rows — removing era mixing by construction
rather than by correlation:

| cell | D coalesce | F cal column | G open column | **H cal era** |
|---|---|---|---|---|
| baseball | 28.92% | 27.47% | 33.20% | **22.13%** |
| basketball | 69.70% | 58.46% | 80.13% | **45.45%** |
| esports | 56.18% | 55.85% | 56.51% | **60.57%** |
| soccer | 27.65% | 27.93% | 28.43% | **34.47%** |

A perfectly era-pure book still condemns 22–61%. And on **both** cells where the
association appeared, arm H comes out *higher* than arm D — esports 60.57 against
56.18, soccer 34.47 against 27.65 — so the counterfactual contradicts the
correlation outright, on exactly the cells the correlation was supposed to
explain (lesson 13, again).

**(iii) The association does not survive its own holdout.** On baseball's early
half mixed families condemn *more* (54.57% vs 35.17%); on the late half they
condemn *less* (12.93% vs 18.11%). The correlation reverses.

⚠️ Read arm H's population, not just its rate. Basketball's late-half arm H is
`0.0%` **of 7 laddered markets** and means nothing; it is printed because
suppressing it would be worse, not because it is evidence.

---

## 3. 🔴 Hypothesis (a) — the rungs are priced at different TIMES — REFUTED, and it runs BACKWARDS

CAL-P136 parked (a) as needing the price-history table, on the ground that
`futures_outcomes` has no as-of. **That is true of the CAL branch and false of
the rest.** Where the price *is* an opening price — the `open` branch, and the
`cal_eq_open` rows the Fallback filled from it — `opening_captured_at` dates the
exact number the law compared, and it covers **81.9%** of baseball's priced leg.
So (a) was answerable offline from rows already in hand.

Condemnation rate by the wall-clock spread between a family's earliest and
latest rung, over families where *every* rung is dated:

| cell | dated families | `<1h` | `1h–1d` | `1d–7d` | `>7d` |
|---|---|---|---|---|---|
| baseball | 2,051 (20.8%) | **30.72%** | 3.66% | — | 100% (n=2) |
| basketball | 392 (70.4%) | **68.13%** | 100% (n=1) | 100% (n=5) | — |
| esports | 1,139 (51.5%) | 21.47% | 26.39% | 28.0% | 100% (n=1) |
| soccer | 24,845 (83.6%) | **21.02%** | 14.93% | 0% (n=3) | 0% (n=1) |

Families whose rungs were written **within the same hour** are condemned *most*
on baseball, basketball and soccer — soccer on a population of 24,845 dated
families, which is not a corner of the cell but most of it. Staleness is not the
mechanism; if anything the freshest, most internally consistent families are the
ones the law condemns. Esports is the only cell with a gradient in the predicted
direction, and it is 6.5 points across a 7-day span — nowhere near a 56%
condemnation rate.

⚠️ The `>7d` and `1h–1d` cells on basketball are n=1 and n=5, and soccer's two
long buckets are n=3 and n=1. They are printed, not read.

---

## 4. 🔴 A third hypothesis, tested and refuted: it is not NOISE

Once (a) and (b) were dead the obvious remaining reading was that a two-rung
family is condemned by a single wrong pair, so a dense O/U book would be
condemned by coin-flip alone. It is not:

| cell | `≤0.5pp` | `0.5–2pp` | `2–5pp` | `5–10pp` | **`>10pp`** | median worst | p90 worst |
|---|---|---|---|---|---|---|---|
| baseball | 2.5% | 9.5% | 10.7% | 12.4% | **64.8%** | 18.5pp | 42.5pp |
| basketball | 3.9% | 15.8% | 13.4% | 11.6% | **55.3%** | 29.9pp | 54.9pp |
| esports | 9.1% | 26.5% | 10.3% | 10.9% | **43.2%** | 29.8pp | 56.0pp |
| soccer | 0.5% | **59.8%** | 13.5% | 6.1% | 20.1% | **1.0pp** | 21.5pp |

On three cells the typical condemned family carries a reversal of **18–30
probability points**. That is not a tick. And the condemnation rate *rises* with
ladder length on every cell (baseball 16.6% at two rungs → 58.2% at five-plus;
basketball 31.8% → 85.7%; soccer 9.9% → 50.9%), which is the opposite of what a
short-family artifact looks like.

🔴 **SOCCER IS THE EXCEPTION AND IT MATTERS.** Its median worst reversal is
**1.0pp** and 59.8% of its violating pairs sit in the 0.5–2pp band. On soccer —
the largest laddered book of the four, 98,582 markets — the noise reading is
*not* refuted, and a rule condemning 27.65% of that book would be deleting rows
over one-point disagreements. Lesson 5, and it cuts against the tidy version of
this queue's story rather than for it.

---

## 5. 🔴 WHAT IS ACTUALLY WRONG — and it is our rows, not the book

`worst_examples` prints the widest condemned families in full, because after
CAL-P136's lesson 23 no guard is left standing between `group_id` and a
condemnation and a human has to look. The families are **not** mis-grouped —
every one is a single event, a single match, one proposition:

```
polymarket:385417  76ers vs. Celtics        209.5 → 0.99   210.5 → 0.01   212.5 → 0.99
polymarket:586223  Jordan Walker: Home Runs   0.5 → 0.20     1.5 → 0.989
```

`Home Runs O/U 1.5` at 0.989 is impossible as an Over price — a player cannot be
less likely to hit one home run than two. As an **Under** it is unremarkable:
`1 − 0.989 = 0.011`, exactly the P(2+) that 0.20 implies.

So the question is not "how wrong is the price" but "how many rungs would have
to be read from the OTHER leg for the family to obey the law". `_min_flips`
answers it exactly — a two-state DP over the rungs, not a greedy guess:

| cell | condemned | **1 flip** | 2 | 3 | 4+ | no assignment | 1-flip share | `1−over` IS the stored Under |
|---|---|---|---|---|---|---|---|---|
| baseball | 2,175 | **1,511** | 60 | 19 | 14 | 571 | **69.5%** | **81.2%** (n=3,771) |
| basketball | 311 | 106 | 24 | 8 | 5 | 168 | 34.1% | 42.7% (n=440) |
| esports | 853 | 223 | 35 | 7 | 43 | 545 | 26.1% | 72.2% (n=**72**) |
| soccer | 6,496 | **2,358** | 259 | 27 | 9 | 3,843 | 36.3% | **97.2%** (n=7,895) |

**On baseball the histogram is a spike, not a spread** — 1,511 families at
exactly one flip against 60, 19 and 14 at two, three and four-plus. And 81.2% of
the over/under pairs in those families sum to 1.00 within a point, so "flip this
rung" and "read this market's stored Under column" are the *same operation*. The
swap stops being an inference about arithmetic and becomes a claim about a
specific column in a specific row.

There is already a repair for a neighbouring class —
`_regrade_polymarket_under_signflip` (#137 Item 1), which flipped 26,756
outcomes whose Under had *inherited* the Over's value. It fires only where
`cp(under) ≈ cp(over)`. **The class measured here is the one where the two sides
sum correctly to 1 and are attached to the wrong sides**, which that repair
cannot see and does not touch.

**Soccer corroborates hardest of all: 97.2% of 7,895 pairs.** Its one-flip share
is lower than baseball's (36.3%), and 3,843 of its condemned families admit no
flip at all — consistent with §4, where soccer's violations are mostly
one-point. So soccer holds two populations at once: a real leg-swap class, and a
much larger tick-noise class the law should never have been pointed at.

⚠️ **esports' 72.2% is computed over 72 pairs.** Esports is priced by the YES leg
(78,959 of them), so the over/under corroboration barely applies there; the
number is real and it is not load-bearing.

---

## 6. The second mechanism, and the four cells do not agree

Baseball's story is the leg swap. Basketball's and esports' is different: a
family holding BOTH a settled rung and a live one, which asserts two moments at
once. Soccer's is neither.

| cell | all_live | all_settled | **mixed_settlement** | condemned that are mixed | eligible that are mixed |
|---|---|---|---|---|---|
| baseball | 26.84% | 8.96% | **13.99%** | 21.8% | 34.4% |
| basketball | 39.08% | 22.97% | **86.49%** | 61.7% | 39.9% |
| esports | 28.59% | 9.39% | **69.55%** | 50.9% | 28.2% |
| soccer | 22.02% | 4.75% | 42.55% | **0.6%** | **0.3%** |

On basketball and esports the mixed-settlement class is heavily
over-represented among the condemned. **On baseball it is UNDER-represented** —
13.99% against an all-live rate of 26.84%, and 77% of baseball's condemned
families are all-live. **On soccer it is 94 families and explains nothing at
all** — 0.6% of the condemned. Lesson 5, paid for again: one cell's answer is not
the book's, and these mechanisms are not one finding wearing several hats.

A fully-settled O/U ladder is a step function — every line below the game's
total settles Over, every line above settles Under — so it can be checked
against arithmetic with no threshold and no opinion. Almost none fail: **1 of
212** on baseball, **0 of 74** on basketball, **0 of 379** on soccer, and the handful of condemned
all-settled families are micro-variation *inside* the settled band (0.99 against
0.9995), not contradictions. The settled book is coherent. It is the
half-settled book that is not.

---

## 7. 🔴 Why no rule is banked, and it is NOT CAL-P136's reason

CAL-P136 refused because a rule deleting a third of a book is disagreeing with
the book. That reading is now superseded: **the law is not disagreeing with the
book, it is correctly reporting that a large share of our stored Polymarket O/U
prices are attached to the wrong leg.**

Which changes the pillar, not the threshold. An exclusion rule here would delete
the evidence of a defect that is *also wrong everywhere else the price is read*
— the event page, the card, the blend — and would buy a calibration cell by
hiding a TRUTH bug. A leg-assignment defect is repaired by fixing the rows.

So the honest output of this queue is a **repair candidate, not an exclusion
rule**, and it is staged as such rather than banked as a sixth design.

⚠️ **And the repair candidate does not cover the whole book either.** Four cells
gave four different answers: baseball is the leg swap (69.5% one-flip),
basketball and esports are mixed-settlement families, and soccer — the largest
laddered book of the four — is mostly one-point disagreements that no mechanism
in this document explains and that probably should never have been measured
against this law at all. Anyone quoting "the O/U book" as one object after
reading this has read it wrong.

⚠️ **The repair is not proposed here and must not be run from these numbers.**
Every measurement above is a RAW-CELL measurement (lesson 19): whether any of
these markets reach the published population is a question only the exact rail
can answer, and 571 baseball families (26%) admit **no** flip assignment at all,
so the class is not clean. Sizing it against the published curve, and separating
the flip class from the no-assignment class, is the next queue's work.

---

## 8. Files

| file | what |
|---|---|
| `pull_eras.py` | the row pull, `COALESCE` split into branches + the as-of stamps; `verify_against_p136` is the population check |
| `eras-polymarket-*.json.gz` | the cached rows (gitignored) |
| `era-fold.py` | every arm above. No law of its own — the grammar, the family key and the monotonicity law are all imported from `app.utils.ladder_monotonicity` |
| `era-fold-*.json`, `era-fold.json` | its output, per cell and merged |

**No shipped code was changed by this queue.** `_min_flips` is a real detector
and promoting it into `ladder_monotonicity` is deliberately NOT done here: the
module is the one the frozen curve reads, the leakage line runs through the
middle of it, and a detector earns its way in behind a named ship rather than
behind a diagnosis. Parked as CAL-P137-2.

Re-running the analysis after the pull is free; the pull is ~30 minutes of
production load for four cells.
