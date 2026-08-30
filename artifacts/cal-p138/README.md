# CAL-P138 — the leg-swap class reaches 0.5% of the published cell, and every exclusion built on it makes the cell worse

Published number at session start and end: **1.88 pp, FLAT**. The payload MOVED
during the session — `generated_at` went `2026-08-29T23:35:53Z` →
`2026-08-30T00:35:55Z`, 925,400 → 925,440 outcomes — but the headline, the
NEEDLE (30/49), the queued count (19) and the queued excess (460,827) are all
unchanged. `producer_beats_missed` went **1 → 0**.

**The gates are still shut and I did not take an exception.** The freeze score is
`2/24 clean, NOT_MET`, byte-identical at both ends of the session — same window
(`2026-08-29T01:38:36Z → 2026-08-30T00:35:55Z`), same 168 observations, same two
clean marks adjacent at the newest end. So the conveyor's step 1 has no legal
answer for a fifth session and this queue did what the header says to do in that
case: instrument repair and diagnosis, on orders 2 and 3.

🔴 **AND ONE PROCESS FINDING THAT CHANGES HOW THIS LANE READS ITS OWN EVIDENCE.**
See §0. CAL-P136 and CAL-P137 both reported "the payload was byte-identical at
my start and end, so the producer did not beat". At my session start
`GET /api/calibration` returned the `23:35:53Z` generation while the freeze ring
had **already recorded** the `00:35:55Z` one. The endpoint is 1h-cached and can
lag the ring by a whole generation, so byte-identity of that payload is not
evidence of a missed beat. The ring is.

---

## 0. 🔴 THE PAYLOAD ENDPOINT LAGS THE FREEZE RING, AND TWO SESSIONS HAVE READ IT AS A BEAT COUNT

At session start I fetched `/api/calibration` and got
`generated_at 2026-08-29T23:35:53.447146Z`. In the same minute
`calibration_freeze_score.py` printed a ring whose newest observation was
`2026-08-30T00:35:55.963312Z` — a generation the payload endpoint had not yet
served me. Later in the session the endpoint caught up and returned
`00:35:55.197127Z`, and the freeze score did **not** move: same 2/24, same
window, same 168 observations. Nothing new happened; the endpoint simply arrived
late.

That matters because it is the exact evidence CAL-P136 and CAL-P137 used:

> "Byte-identical at my start and end — the producer did NOT beat during
> CAL-P137 either. That is now TWO consecutive silent sessions."

The conclusion may well be right, but the reasoning is not sound, and a session
that fetches the payload twice inside one cache window will "prove" a silent
producer no matter what the producer did. **The freeze ring is the beat counter;
`/api/calibration` is a cached view of it.** Anyone re-baselining off "N silent
sessions" should re-derive N from the ring.

This is CAL-P138's lesson 27 and it costs nothing to adopt: quote the ring's
observation count and window, never the payload's byte-identity.

---

## 1. What this queue was for

CAL-P137 measured that 1,511 of `polymarket/baseball`'s 2,175 condemned O/U
families are fixed by reading exactly ONE rung from the other leg, and that
81.2% of their over/under pairs sum to 1.00 — so the monotonicity law has been
correctly reporting that our stored prices are attached to the wrong side. It
then refused to propose anything, for two stated reasons, and parked both:

* **CAL-P137-1** — every number in it is a RAW-CELL count (lesson 19), and
  nobody had asked how many of those markets reach the PUBLISHED curve. Called
  "the one item that could still turn into a ship".
* **CAL-P137-3** — 571 baseball and 3,843 soccer condemned families admit NO
  flip assignment, "a bulk `1 - p` would corrupt them", and nobody knows what
  they are.

Both are answered. **Neither turns into a ship, and the reasons are worth more
than a ship would have been.**

---

## 2. The partition, and it reproduces CAL-P137 exactly

`legswap_classes.py` turns CAL-P137's family-grain histogram into a market-grain
partition. It computes no law of its own: the grammar, the family key, the price
selection and the monotonicity verdict are all imported from
`app.utils.ladder_monotonicity`, and the rows are `pull_eras.as_dicts` unchanged.

What it adds is the **assignment**. `era-fold._min_flips` returns the COST of the
cheapest repair; to accuse a specific row you need to know WHICH rung, and to
trust the accusation you need to know the assignment is UNIQUE.
`min_flip_assignment` returns cost, uniqueness and the flipped rung indices from
the same two-state DP with backpointers and a bounded optimal-path count.

🔴 **It is checked against `_min_flips`, not trusted.** `self_check` runs both
over every condemned family of every cell:

| cell | condemned families checked | cost disagreements |
|---|---|---|
| baseball | 2,175 | **0** |
| basketball | 311 | **0** |
| esports | 853 | **0** |
| soccer | 6,496 | **0** |

9,835 families, zero disagreements, and the min-flips histograms come out
identical to CAL-P137's published table (baseball 1,511 / 60 / 19 / 14 / 571).
Lesson 9 — a claim about agreement, not about truth — but agreement with the
function that produced the numbers this session re-uses is precisely the claim
needed before re-using them.

**The accusation pins to a row almost always:** 1,509 of baseball's 1,511
one-flip families have a UNIQUE minimum assignment; 2,277 of soccer's 2,358.

`markets_in_two_arms_before_precedence` is **0** on all four cells, so the
"a market can be a rung of two families" hazard is a measured zero here rather
than a resolved-by-precedence guess.

---

## 3. 🔴 CAL-P137-1 ANSWERED — the leg-swap class is 0.5% of the published cell

`published-legswap-fold.py` folds the cell through
`_calibration_population_ctes` — the producer's own chain, imported from the
frozen file — at **market grain**, and does every arm question offline against
that one cached fold.

Why market grain and not an arms dimension: measured, the eight-arm id-array
dimension renders **58,230 characters** of SQL against a 60,000-character cap, so
nearly every chunk splits on LENGTH before it is sent — about 1.7 hours per cell
for one fixed partition. The market-grain fold costs one static dimension, no
arrays, and turns the arms, the holdout, the counterfactual and every CAL-P137-3
question into re-reads of one cache.

`polymarket/baseball`, curve `2026-08-30T00:35:55Z`, `q268`:

| arm | markets in cell | published | reach | n | share of cell | ECE | gap |
|---|---|---|---|---|---|---|---|
| `a_flip1_suspect` | 1,509 | 102 | **6.8%** | **224** | **0.5%** | **19.54** | −9.70 |
| `b_flip1_sibling` | 1,812 | 247 | 13.6% | 501 | 1.2% | 18.56 | −5.84 |
| `c_flip1_ambiguous` | 6 | 0 | 0% | 0 | — | — | — |
| `d_flip2plus` | 444 | 101 | 22.7% | 186 | 0.5% | 24.95 | +0.63 |
| `e_no_assignment` | 3,445 | 957 | 27.8% | 1,752 | 4.3% | 15.89 | −4.81 |
| `f_mono_ambiguous` | 0 | 0 | — | 0 | — | — | — |
| `g_mono_coherent` | 17,737 | 1,416 | 8.0% | 3,401 | 8.3% | 12.19 | −5.76 |
| `z_not_in_a_ladder` | 2,595 | 2,595 | 100% | 35,075 | 85.3% | **5.59** | +4.75 |

**The accused rows are 224 outcomes — half a percent of the cell.** CAL-P137's
1,511-family finding, weighed against the published population for the first
time, cannot move `polymarket/baseball`'s ECE by anything a reader would see.
The whole leg-swap class including siblings is 725 outcomes, 1.8%. That is the
answer to CAL-P137-1 and it is a **negative**: this is not a calibration ship.

⚠️ **Two things it is NOT.** It is not a statement that the defect is small — see
§5, the accused rows carry **3.5× the cell's ECE** and the finding remains a real
TRUTH bug. And it is not a statement about the cell: 6.8% reach means most of
these markets are simply not graded or not truth-eligible, not that they are
fine.

### The reach column is the surprise, and it runs the wrong way for the story

`e_no_assignment` reaches the curve at **27.8%** — four times the flip class's
6.8% — and `g_mono_coherent`, the arm that obeys the law, reaches at only 8.0%.
So the published slice of the laddered book is enriched in exactly the families
nobody can explain and depleted in the ones that behave. Whatever selects rows
into the published population is not independent of the defect, and nothing in
this queue explains why.

---

## 4. 🔴 THE FLIP COUNTERFACTUAL DOES NOT REPRODUCE ON THE PUBLISHED ROWS

`ece_if_flipped` re-prices each arm as though every one of its prices were read
from the other leg. If the leg-swap story held on the published rows, the
accused arm's flipped ECE would be the SMALLER of the two. It is not — and it is
not on any arm:

| arm | mean_p | realized | ECE | ECE if flipped | ratio |
|---|---|---|---|---|---|
| `a_flip1_suspect` | 0.3806 | 0.4777 | 19.54 | **47.31** | 2.42× |
| `b_flip1_sibling` | 0.4147 | 0.4731 | 18.56 | 38.73 | 2.09× |
| `d_flip2plus` | 0.4741 | 0.4677 | 24.95 | 27.92 | 1.12× |
| `e_no_assignment` | 0.4359 | 0.4840 | 15.89 | 34.76 | 2.19× |
| `g_mono_coherent` | 0.3511 | 0.4087 | 12.19 | 52.87 | 4.34× |
| `z_not_in_a_ladder` | 0.2591 | 0.2116 | 5.59 | 63.60 | 11.38× |

Lesson 26, and this time pointed at CAL-P137's own finding: a counterfactual
that runs backwards is evidence against, not weak evidence for.

⚠️ **BUT READ WHAT THIS DOES AND DOES NOT REFUTE, because the honest reading is
narrower than the table looks.**
1. Flipping *every* price in *any* well-behaved population makes it worse, so
   `ECE_flip > ECE` on its own discriminates nothing. The only thing with
   content is the RATIO, and the accused arm is the second-closest to being
   inverted of the six while the untouched control `z` is 11.4× — a gradient in
   the direction the story predicts, and far too weak to carry it.
2. **The fold does not know which leg published.** `deduped`'s binary branch is
   `ELSE ro.rn = 1` ordered by `ABS(fo.opening_probability - 0.5)`, and for a
   pair summing to one the two legs are EQUIDISTANT from 0.5 — the tie falls to
   `fo.id`. So for a swapped market the curve may already be publishing the leg
   that carries the *correct* number, and flipping it would break it. Separating
   that needs the outcome id of the published leg, which this fold does not
   carry. **Parked as CAL-P138-1.**

So §4 does not refute CAL-P137's leg-swap finding — the arithmetic corroboration
(81.2% of pairs summing to 1.00) is untouched. What it refutes is the idea that
a bulk `1 - p` on the accused rows would improve the published curve. It would
not, and nobody should run one from these numbers.

🔴 **WHY GAP IS THE WRONG COLUMN HERE AND ECE IS THE RIGHT ONE.** A swapped pair
puts a loser in bucket 9 and a winner in bucket 0; the signed error cancels and
gap is close to blind to this defect by construction. A reader who scans the gap
column will conclude the class is fine. Every reading above is on ECE for that
reason.

---

## 5. 🔴 EVERY EXCLUSION RULE BUILT ON THIS SITE MAKES THE CELL WORSE

CAL-P136 refused to bank its package because "a rule deleting a third of a book
is disagreeing with the book". CAL-P137 superseded the reason. **Neither ever
priced the rule on the population it would have shipped against.** The cached
fold makes that free:

`polymarket/baseball`, baseline n=41,139 ECE=4.68 gap=+3.25:

| candidate rule | dropped | % of cell | ECE after | ΔECE | gap after | Δgap |
|---|---|---|---|---|---|---|
| **CAL-P136 package (every condemned family)** | 2,663 | 6.47% | 4.78 | **+0.10** | +3.82 | +0.57 |
| drop only the leg-swap families | 725 | 1.76% | 4.46 | −0.22 | +3.43 | +0.18 |
| drop only the accused row | 224 | 0.54% | 4.63 | −0.05 | +3.32 | +0.07 |
| drop only the families no swap can fix | 1,752 | 4.26% | 4.80 | +0.12 | +3.60 | +0.35 |
| drop every laddered market (doctrine 18's outer bound) | 6,064 | 14.74% | 5.59 | **+0.91** | +4.75 | +1.50 |

**CAL-P136's package makes the cell worse.** The condemned rows are the worst
calibrated in it — ECE 15.12 against 4.68 — and removing them still raises the
cell's ECE, because their gap is **−5.03** against the cell's **+3.25**: they
were partially cancelling the cell's overpricing bias, and the exclusion removes
the offset along with the defect. Lesson 18 said an exclusion can only remove a
defect that is CONCENTRATED; this one is concentrated in ECE and
anti-concentrated in gap.

Dropping the whole laddered book — the outer bound doctrine 18 grades a
row-dropping fix against — costs **+0.91 ECE**. There is no exclusion at this
site worth having. **CAL-P136's and CAL-P137's refusals are now measured rather
than argued, and both were right.**

The two rules that do help help by 0.22 and 0.05 against a cell that needs 1.7pp
to reach its 3.0 bar, they are exclusions CAL-P137 §7 rules out on pillar
grounds, and the banked rank-1 design already takes this cell to 2.71. **Nothing
here is queued.**

---

## 6. 🔴 CAL-P137-3 ANSWERED — and there are two populations, separated by one measurement

The arithmetic first, because it is checkable without any data: a TWO-rung family
can always be repaired — for `dec`, all four readings of `(p0, p1)` fail only if
`p1 < 1-p0` and `p1 > 1-p0` at once — so `no_assignment` is impossible below
three rungs. **Measured `min_rungs` is 3 on all four cells**, and the one-flip
class is 89.7% two-rung families on baseball. The two classes are structurally
different objects, not two ends of one distribution.

**Over-grouping is refuted.** Distinct `event_id`s per no-assignment family:
**0.0%** span more than one on baseball and basketball, 0.2% on esports, 1.2% on
soccer. This mattered more than usual: `duplicate_values` — the guard
`ladder_coherence` calls load-bearing — fires on **ZERO** families under the
scoped key on all four cells (lesson 23: the key fix removed the guard that was
compensating for the key), so nothing else was watching this seam. It is sound.

### The tolerance ladder, which is what separates them

"No assignment exists" is a statement about an EXACT law. Re-asking the DP with
slack says how much of the class is tick noise:

| cell | no-assign families | repairable @0.5pp | @2pp | @10pp | @25pp | **still infeasible** | % of condemned |
|---|---|---|---|---|---|---|---|
| baseball | 571 | 7.0% | 15.1% | 49.9% | 86.3% | **78** | 3.6% |
| basketball | 168 | 3.0% | 15.5% | 37.5% | 60.1% | **67** | 21.5% |
| esports | 545 | 25.5% | 38.2% | 58.7% | 66.6% | **182** | 21.3% |
| soccer | 3,843 | **42.9%** | **57.4%** | 77.5% | **98.3%** | **65** | **1.0%** |

**Soccer's 3,843 "unexplained" families are tick noise** — 57.4% repairable at
two points, 98.3% at twenty-five, and only 65 families in the whole cell
genuinely block anything. That confirms and sharpens CAL-P137 §4's soccer
reading. **Baseball's and basketball's are not** — 15% repairable at 2pp, median
worst reversal 22.0pp and 42.9pp.

### 🔴 AND READING THE WORST FAMILIES IN FULL FOUND A THIRD DEFECT

`Tunisia vs. Netherlands: O/U 6.5` is stored `over=0.5, under=0.5`, sitting
between rungs priced 0.085 and 0.015. `Cincinnati Reds vs. Milwaukee Brewers:
O/U 6.5` is `over=0.001, under=0.001`. `New York Mets vs. San Francisco Giants:
O/U 11.5` is `over=0.95, under=0.95`.

**A rung at 0.5 is FLIP-INVARIANT** — `1 - 0.5` is the same number — so it offers
the DP no second reading and no assignment can route around it. That is the
mechanism, and it is the coin-flip writer class the lane already tracks on
`kalshi/entertainment`, `polymarket/golf` and `polymarket/economics`, found here
on the O/U ladders of two more cells.

The raw count conflates a placeholder with a genuinely even line, so
`_has_isolated_half` asks whether the half rung breaks the law against a sibling
by more than 15 points. That discriminator rises monotonically with hardness on
**all four cells**, where the raw count does not:

| cell | isolated-half %: one-flip → no-assignment → still-infeasible | `under == over` %: same three |
|---|---|---|
| baseball | 3.8 → 6.8 → **14.1** | 8.9 → 34.7 → **55.1** |
| basketball | 6.6 → 16.7 → **29.9** | 66.0 → 88.1 → **94.0** |
| esports | 12.4 → 45.1 → **71.4** | 12.4 → 0.6 → 0.0 |
| soccer | 4.0 → 10.9 → **55.4** | 80.5 → 79.5 → 66.2 |

Soccer is why the discriminator was needed: its RAW flip-invariant rate is
80.7% / 78.9% / 63.1% — flat, because soccer totals genuinely are near-even —
while the isolated version goes 4.0 → 10.9 → 55.4. **esports' unrepairable core
is 71.4% isolated-half placeholders**, which makes the coin-flip writer the
dominant mechanism there.

And `over + under = 1` falls as the family gets harder — baseball 84.6% → 48.0%
→ 37.2% — which is the leg-swap corroboration draining away exactly where the
leg-swap explanation stops working. Two independent signatures, same gradient,
opposite directions.

⚠️ `under == over` is the signature
`_regrade_polymarket_under_signflip` (#137 Item 1) already repairs on the
GRADING side, since it fires exactly where `cp(under) ≈ cp(over)`. Its
appearance here is a statement about SCOPE: that repair saw these rows and the
PRICE was left wrong. **Four cells, four answers, again** — and the notes'
standing hazard that "the coin-flip writer class is on THREE cells" should now
read five.

---

## 7. The self-check, and the one number that stays open

The producer's own chain reproduces **n=41,139** against the payload's
**45,240** — a **−9.06%** shortfall. That is not clean and it is not shrugged at,
because `calibration_cell_exact`'s docstring names a mechanism that would produce
it and says it bites on exactly this population: chunking on `fm.id` can split a
`group_id` cluster, and an O/U ladder IS such a cluster. The sign fits too —
`rn = 1` publishes one leg where the multi branch publishes several.

So `edge-check.py` re-ran the identical fold at HALF the chunk width and compared
the arms row by row:

| arm | n @1M | n @500K | delta | ECE @1M | ECE @500K |
|---|---|---|---|---|---|
| `a_flip1_suspect` | 224 | 226 | +2 | 19.54 | 19.54 |
| `b_flip1_sibling` | 501 | 507 | +6 | 18.56 | 18.51 |
| `d_flip2plus` | 186 | 186 | 0 | 24.95 | 24.95 |
| `e_no_assignment` | 1,752 | 1,751 | −1 | 15.89 | 15.90 |
| `g_mono_coherent` | 3,401 | 3,413 | +12 | 12.19 | 12.62 |
| `z_not_in_a_ladder` | 35,075 | 35,155 | +80 | 5.59 | 5.60 |
| **pooled** | **41,139** | **41,238** | **+99 (+0.241%)** | 4.68 | — |

The pooled total moves **0.241%** against a **9.06%** shortfall — two orders of
magnitude apart — and every arm's ECE is stable to a few hundredths. **The chunk
boundaries do not explain the miss.** The shortfall is something both widths
share, it is unexplained, and it is recorded as open rather than absorbed.

It does not change any conclusion here: the flip class is 224 outcomes against
either denominator, 0.54% of 41,139 or 0.50% of 45,240.

⚠️ The first run of `edge-check.py` printed "the arms MOVE with the chunk width"
off a strict `==`, for a table whose largest arm moved 12 rows in 3,401. The
verdict is now a magnitude and the strict flag is kept as a sub-fact. A binary
test at the wrong granularity reads as "these numbers are unusable" when the
measurement says the opposite — **lesson 28**.

---

## 8. Where this leaves the finding

CAL-P137 staged `alex-inbox/calibration-909`: our Polymarket O/U prices are
stored on the wrong leg, it is wrong on the event page too, and it belongs to
TRUTH rather than calibration. **That stands, and this queue narrows it in three
ways and widens it in one:**

* it is **0.5% of the published baseball cell**, so it is not a calibration ship
  and should never be queued as one;
* a **bulk `1 - p` must not be run** — the flip counterfactual does not
  reproduce on the published rows, and the fold cannot yet tell which leg the
  curve published (CAL-P138-1);
* the **no-assignment class must be excluded from any repair**, and it is now
  characterised rather than feared: mostly tick noise on soccer, mostly
  placeholder rungs and mixed settlement on the other three, with 78/67/182/65
  families genuinely unrepairable;
* it is **wider than a leg swap**. A third defect — rungs priced at exactly 0.5,
  and markets whose Under carries the Over's number — is present on all four
  cells and dominates esports' unrepairable core at 71.4%.

**No design is banked. Still five.** And this time the refusal is priced: §5 says
every exclusion at this site costs the cell ECE, including CAL-P136's own
package.

---

## 9. Files

| file | what |
|---|---|
| `legswap_classes.py` | the market-grain partition; `min_flip_assignment` (cost + uniqueness + accused rungs) and `self_check` against `era-fold._min_flips` |
| `era_fold_import.py` | six-line loader so the self-check compares against CAL-P137's real function, not a copy of it |
| `published-legswap-fold.py` | the published fold at market grain through `_calibration_population_ctes`, plus the arm table, the holdout and the flip counterfactual |
| `noassign-anatomy.py` | CAL-P137-3: the tolerance ladder, the structural readings, `_has_isolated_half`, and the worst families printed in full |
| `rule-pricing.py` | what each candidate exclusion does to the published cell |
| `edge-check.py` | the same fold at half the chunk width, compared arm by arm |
| `published-marketgrain-baseball.json`, `edge-marketgrain-*.json` | the cached folds — the only production cost in this queue |
| `published-legswap-*.json`, `noassign-*.json`, `rule-pricing.json`, `edge-check-baseball.json` | the outputs |

**No shipped code was changed.** `git diff origin/master...HEAD --stat -- backend
frontend` is empty. `min_flip_assignment` stays out of
`app/utils/ladder_monotonicity` for CAL-P137's reason, unchanged — the module is
the one the frozen curve reads, the leakage line runs through the middle of it,
and a detector earns its way in behind a named ship. CAL-P137-2 is still parked.

Gate `-k "calibration or bookmaker or ladder"`: see the report line. Re-running
any analysis after the cached fold is free and offline; the fold is ~11 minutes
of production load per cell at 1M width, ~11 more at 500K for the edge check.

⚠️ **Only `polymarket/baseball` was folded through the published curve.** The
other three cells are partitioned and anatomised offline but NOT sized against
the curve — soccer especially, which is the largest laddered book and the one
whose reach column would say most about §3's surprise. Parked as **CAL-P138-2**.
