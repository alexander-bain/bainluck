# RULE DESIGN — `polymarket/baseball` (rank 1)

**CAL-P117, 2026-08-28.** Designed, benched on the producer's own CTE chain, holdout-validated.
**Not built. Worth 0.00 pp today.** Banked so that freeze-lift day is a merge and not a cold start.

| | |
|---|---|
| cell | `polymarket/baseball`, class **B**, bar **3.0 pp** |
| board position | **rank 1 of 20**, 78,782 excess-outcomes on the `2026-08-28T20:37:41Z` curve |
| payload | n=43,768 · ECE **4.80** · gap **+3.03** |
| exact rail | n=41,260 · ECE **4.69** · gap **+3.29** |
| designed policy | **K′ = R1 + R2 + R3 + M1** → n=**17,827** · ECE **2.71** · gap −1.21 · **excess-outcomes 0** |
| holdout | OLD 13,982 @ **2.90** · NEW 3,845 @ **2.63** — **both halves pass** |
| cost | removes ≈2.7% of the entire published curve — **Alex's call**, same footing as ruling 103's 9.3% and `kalshi/economics`'s 3.0% |

---

## 0. What this queue found first, and it changes the premise

The board carried this cell as *"✅ two named mechanisms (0.5000 placeholder pair;
published-pair incoherence), both branch-only on `program/calibration-99`"*. Both are real. Both
were diagnosed on the **subcohort board's** `baseball/quantity` cell (n=6,778 truth-eligible
Polymarket quantity legs) — and that population is **3.1% of the published cell**.

Measured on the published cell, the two of them together are worth **−0.53 pp** and leave the cell
at 4.16, comfortably failing its 3.0 bar. They are not rank 1's mechanism. They are a **historical
residue of it**: of the 1,284 rows they remove, **1,258 sit in the OLD half and 26 in the NEW**
(R1 929/14, R2 329/12) — while the mechanism named in §3 runs the other way, **1,892 OLD against
20,561 NEW**. One class is a dead tail; the other is the live and growing one. The forward writer
guard CAL-P094 names
(`_resolve_market_probability_with_source` declining a fabricated midpoint) is already shipped, and
the census shows it working.

**Rank 1's live mechanism is a different member of the same family, arriving through the other
column on a market with 37 legs instead of two.**

---

## 1. The instrument, and its worst reproduction so far

`calibration_cell_exact.py` folds the cell through `_calibration_population_ctes()` — the producer's
own function, imported, not re-implemented — scoped through the chain's documented
`market_info_extra` hook. Every run prints its number beside the payload's:

| fold | exact rail | payload | Δn |
|---|---|---|--:|
| `--by sumband` | 41,247 / 4.69 / +3.29 | 43,768 / 4.80 / +3.03 | **−5.76%** |
| `--by pairtype` | 41,148 / 4.64 / +3.22 | " | −5.99% |
| `--by pairsum` | 41,294 / 4.72 / +3.35 | " | −5.65% |
| `--by policy` | 41,260 / 4.69 / +3.29 | " | −5.73% |
| `--by cpdrift` | 41,266 / 4.69 / +3.29 | " | −5.72% |

> 🔴 **This is 5x the drift CAL-P114 recorded, and the edge check cannot see it.** On four cells the
> rail reproduced to ±1.22% on n. Here it is short by 5.65–5.99% on every one of five folds — a
> stable shortfall, not noise. `--edge-check` re-ran the whole sweep at half the chunk width and
> moved n by **35 rows (0.08%)** and ECE by **0.01**, so *chunking is not the cause*: the cause is
> the **cell scope itself**. `market_info_extra` restricts `market_info` to one
> `(source, category)`, and Polymarket's `virtual_market` grouping is built over `group_id` /
> `event_id` clusters that do not respect `llm_sport_category` — so a market that groups in
> production can read ungrouped here and take the `rn = 1` branch. The rail reports 94.3% of the
> cell and every number below is a number about those rows.
>
> **What that means for this design, stated rather than waved at:** the ECEs are trustworthy (they
> agree with the payload to 0.11 pp on a 41,000-row fold), the *class shares* are trustworthy, and
> the *absolute row counts* are 5.7% low. Where a row count decides something — the 1,000-outcome
> materiality floor — the survivor is quoted at both the rail's count and the scaled count, and
> both clear it by an order of magnitude.

`--edge-check` verdict text reads **⚠️ DIFFERENT** because it tests exact equality on three
numbers. The measured difference is 35 rows in 41,247 and 0.01 pp. It is recorded as
"different-and-immaterial" rather than suppressed.

---

## 2. The cell is not what its neighbours are

`kalshi/economics`, `kalshi/tech` and `polymarket/esports` were all one defect — a non-partition
bundle. The obvious move was to try RULE E here. **It is refused, and by a wide margin.**

| policy | n | ECE | gap | verdict |
|---|--:|--:|--:|---|
| control | 41,247 | 4.69 | +3.29 | |
| **RULE E** — keep only markets whose published prices sum ≤ 1.15 | 8,153 | **9.02** | −2.76 | 🔴 **nearly doubles the error** |
| extend `esports_multi_bundle_filter`'s allowlist to `(polymarket, baseball)` | 11,788 | **8.35** | +0.83 | 🔴 **worse** |

The reason is in the sum ladder, and it is **not monotone**:

| published price sum band | n | ECE | gap |
|---|--:|--:|--:|
| ≤ 1.15 | 8,153 | **9.02** | −2.76 |
| 1.15 – 2 | 2,415 | 5.44 | −0.56 |
| 2 – 5 | 6,245 | **2.28** | +0.62 |
| 5 – 15 | 18,460 | 5.77 | +4.78 |
| > 15 | 5,974 | **13.00** | +11.29 |

The best-calibrated class in this cell is a class that is **not a partition** (sum 2–5, 2.28 pp),
and the worst is the one that looks most like a partition (sum ≤ 1.15, 9.02 pp). **Whatever is
wrong here is not the bundle shape.** Third cell, third time the allowlist has to be decided per
`(source, category)` and not by family resemblance — CAL-P114's correction, confirmed again.

---

## 3. The mechanism: the writer overwrites a real price with a coin flip

Market **56675315**, `Miami Marlins vs. Houston Astros - Player Props` — 37 legs, published price
sum 19.13, 8 winners. A sample of its rows, `opening_probability` → published
`calibration_probability`:

| leg | open | published | won |
|---|--:|--:|:-:|
| Yordan Alvarez: Home Runs O/U 1.5 | 0.0355 | **0.5005** | no |
| Xavier Edwards: Home Runs O/U 1.5 | 0.0110 | **0.5005** | no |
| Griffin Conine: Home Runs O/U 0.5 | 0.1050 | **0.5050** | no |
| Jose Altuve: Home Runs O/U 0.5 | 0.0850 | **0.5050** | no |
| Isaac Paredes: Home Runs O/U 0.5 | 0.0900 | **0.9050** | yes |
| Tyler Phillips: Strikeouts O/U 3.5 | 0.4850 | **0.0950** | no |

The opening column is a coherent, monotone prop ladder — a home run at O/U 0.5 prices above the
same player at O/U 1.5, every time. The published column is a spray of `0.5000 / 0.5005 / 0.5050 /
0.9050 / 0.0950` that carries no relationship to it. **The curve publishes
`COALESCE(calibration_probability, opening_probability)`** (gotcha #144 / ruling 103 — the coalesce
is a fallback, not an exclusion), so the curve publishes the spray.

Cell-wide, on markets `56,000,000 ≤ id < 57,000,000`, both columns non-null:

| | legs | mean open | mean published | mean \|drift\| | corr(pub, open) | published in [0.45, 0.55] | open in [0.45, 0.55] |
|---|--:|--:|--:|--:|--:|--:|--:|
| NOT "Player Props" | 4,193 | 0.4992 | 0.4995 | 0.0926 | **0.897** | 1,079 | 1,084 |
| **"Player Props"** | 1,359 | **0.1765** | **0.2709** | 0.1283 | **0.677** | **242** | **39** |

Two numbers do the work. **`corr` 0.897 → 0.677**: outside these containers the published price
tracks the open; inside them it substantially does not. **242 published near-0.50 legs where 39
opened there** — a **6.2x manufacture** of coin flips on a population whose realized base rate is
0.18. That is the #1578/#151 phantom-midpoint family, and it inflates the mean published price of
the class by **+9.4 points** against a base rate that did not move.

The row-level signature is unmistakable when folded directly (`--by cpdrift`, whole cell):

| class | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| published price forced INTO [0.45, 0.55] from an open > 0.25 away | **1,915** | 4.6% | **44.36** | **+44.36** |
| pulled in from > 0.10 away | 453 | 1.1% | 6.60 | +6.60 |
| moved > 0.25 but NOT to a coin flip *(the control)* | 3,473 | 8.4% | 12.62 | **−2.92** |
| neither | 35,302 | 85.5% | **2.02** | +1.65 |
| no published price at all — the `opening_probability` fallback | 123 | 0.3% | 2.78 | −2.78 |

`ECE == gap` on the forced class means every bin errs in one direction: these rows are published at
~0.50 and lose. And the **control earns its place** — rows that moved just as far but landed
somewhere other than 0.50 read 12.62 with a *two-sided* −2.92 gap. Ordinary line movement and a
placeholder overwrite are distinguishable, so a rule may name one without deleting the other.

---

## 4. The rule

Four arms, an ordered partition, folded together so no overlap is inferred. §4's table is
`--by policy` (three arms); §7 adds the fourth on `--by policy2` and is where the final design
lands.

| arm | predicate | provenance |
|---|---|---|
| **R1** | both legs of a two-leg Over/Under market open at exactly `ROUND(opening_probability, 4) = 0.5000` | CAL-P094 / `half_spike_pair_exclusion`, branch-only on `program/calibration-99` |
| **R2** | two-leg O/U market, opening pair sums to 1 within `PAIR_SUM_TOLERANCE` (0.02) and the **published** pair does not; both legs leave | CAL-P100 / `published_pair_coherence_filter`, branch-only, shipped there with **"NO ECE CLAIM"** |
| **R3** | a Polymarket market whose name matches `%player props%` **and** whose published prices sum to **> 1.15** | **new here** |
| **M1** | one row whose published price landed in [0.45, 0.55] having opened more than 0.25 away | **new here**, §7 |

R3's threshold is **RULE E's own constant**, not a fitted one. It is doing real work: the props
containers below it (1,077 rows) read 2.15 and 2.61 and are left in.

### Every arm is load-bearing, and only the conjunction passes

`n × (ECE − 3.0)` is the board's excess-outcomes; σ = `50/√n`; holdout splits on `market_id`
45,000,000, monotone with creation, rule never re-fitted.

| policy | n | ECE | gap | σ | (ECE−3)/σ | excess | OLD | NEW |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| control | 41,260 | 4.69 | +3.29 | 0.25 | +6.87 | 69,676 | 6.83 (17,281) | 4.90 (23,979) |
| R1 | 40,317 | 4.28 | +3.53 | 0.25 | +5.14 | 51,671 | 5.99 | 4.90 |
| R2 | 40,919 | 4.58 | +3.44 | 0.25 | +6.39 | 64,537 | 6.56 | 4.92 |
| R3 | 19,245 | 4.00 | −1.59 | 0.36 | +2.77 | 19,314 | 4.47 | 2.69 |
| R1+R2 *(the two banked mechanisms)* | 39,976 | 4.16 | +3.68 | 0.25 | +4.64 | 46,531 | 5.69 | 4.92 |
| R1+R3 | 18,302 | 3.10 | −1.33 | 0.37 | +0.27 | 1,867 | 3.36 | 2.67 |
| R2+R3 | 18,904 | 3.73 | −1.36 | 0.36 | +2.01 | 13,713 | 4.12 | 2.66 |
| **K — R1+R2+R3** | **17,961** | **2.79** | −1.08 | 0.37 | **−0.56** | **0** | **2.96** (14,141) | **2.64** (3,820) |

**R2 is worth −0.11 pp alone and is load-bearing in the conjunction**: drop it and the cell lands at
3.10, over the bar. That is CAL-P112's *"T and E ship together or a cell gets worked twice"*
arriving on a different cell — a rule whose solo delta is a rounding error can still be the arm that
decides a pass.

### Three policies that pass on the pooled number and are REFUSED on the holdout

| refused policy | pooled | OLD | NEW | why refused |
|---|--:|--:|--:|---|
| R1+R2+R3 restricted to sum > 15 | **2.94** | **4.12** | **3.48** | passes pooled, fails **both** halves — a pass by cancellation, not by fixing anything |
| R1+R2+R3 restricted to sum > 5 | 2.70 | **3.06** | 2.17 | OLD over the bar |
| R1+R2+R3, all props regardless of sum | 2.86 | 2.95 | **3.10** | NEW over the bar, and it deletes 1,077 rows measured at 2.15/2.61 |

The holdout refused three candidate thresholds and admitted the one that was already a constant in
the codebase. That is the single most useful thing in this document.

### Verdict on the cell

`polymarket/baseball` becomes the **second** cell on this board whose rule leaves it **PASSING and
MATERIAL**: 17,827 surviving rows on the rail, ≈18,900 scaled to the payload — 18x the 1,000-row
floor. Rank 1 crosses off, **78,782 excess-outcomes → 0**.

And the honest edge: 2.71 against a 3.0 bar is **0.77σ under it**. This is a pass, not a
comfortable one, and it is said here rather than discovered after deploy.

---

## 5. What it costs, and why that is Alex's call and not this lane's

K′ removes **23,300 of 41,127 rows — 56.7% of the cell**, ≈24,800 rows scaled to the payload, which
is **≈2.7% of the entire published curve** (913,849 outcomes on the `20:37Z` payload).

That is the same footing as `kalshi/economics`'s ~3.0% (CAL-P114) and ruling 103's 9.3%. With both
banked, **two queued rules now propose removing ≈5.7% of the published curve between them**, and
they should be ruled together for the same reason criteria 3 and 6 should be: a reader who accepts
each 3% in isolation has not been shown the 6%.

The defence of the removal is the same one ruling 103 accepted: **these rows were never scoreable
forecasts.** A leg published at 0.5005 whose market quoted 0.011 is not a bad forecast of a home
run; it is not a forecast at all. Grading the platform on it flatters nobody — it is the exact
"invented price becomes a published forecast" failure `pair_opening_coherence` was written to
refuse, on the read side instead of the write side.

---

## 6. Scope, and the two things this design does NOT claim

**Scope is `(source, category) = (polymarket, baseball)`.** Not category-only — CAL-P114 measured
what category-only scoping costs (`polymarket/economics` 3.91 → 17.75) and that correction is
inherited here without re-deriving it.

1. **R3's arm is keyed on a provider's market TITLE, and that is a real weakness.** `%player props%`
   breaks the day Polymarket renames the container. §7 measures the candidate successor and finds
   it is a **complement, not a replacement** — the weakness is reduced, not removed, and the design
   ships with it named.
2. **Widening beyond baseball is unmeasured.** The writer defect is a *writer* property and is very
   likely wider — `Player Props` containers exist in basketball and football too — but "likely" is
   not measured, and ruling 134 puts that census in the measurement lane. Appended to
   `PARKED-MEASUREMENTS.md`.

---

## 7. The successor, measured: **M1 does not retire the name match — it completes it**

`cpdrift` said a column-level predicate for the same rows exists. Whether it can *replace* R3
cannot be answered by putting two sweeps side by side, because the two populations overlap and by
how much is the whole question. `--by policy2` folds five arms as one ordered partition, crossed
with a flag for "is this row in R3's population", so every combination is a pooling rather than an
inference. **M1** = published price landed in [0.45, 0.55] from an open more than 0.25 away;
**M2** = the same at > 0.10.

| class | n | ECE | gap | OLD | NEW |
|---|--:|--:|--:|--:|--:|
| `keep` inside R3's population | 19,980 | 4.66 | +4.11 | **28.36** (1,650) | 2.64 (18,330) |
| `keep` outside it | 17,542 | 2.85 | −1.28 | 3.06 | 2.62 |
| `m1` inside R3's population | 1,739 | **47.84** | +47.84 | 44.50 | 48.31 |
| `m1` **outside** it | 168 | 12.87 | +12.87 | 11.71 | — |
| `m2` inside / outside | 164 / 285 | 12.77 / 5.86 | | | |

**91.2% of M1 lives inside a Player Props container** — the two rules really are aimed at one
defect. But they are not substitutes:

| policy | n | ECE | (ECE−3)/σ | OLD | NEW | verdict |
|---|--:|--:|--:|--:|--:|---|
| control | 41,127 | 4.71 | +6.94 | 6.83 | 4.96 | |
| R1+R2 | 39,878 | 4.19 | +4.75 | 5.71 | 4.97 | fails |
| **M1 alone** | 39,220 | **2.76** | −0.95 | **6.31** | 1.99 | 🔴 **passes pooled, OLD fails at 6.31** |
| **R1+R2+M1** | 37,971 | **2.16** | −3.27 | **5.13** | 2.00 | 🔴 **best pooled number on the page — and OLD fails at 5.13** |
| R1+R2+M1+M2 | 37,522 | 2.11 | −3.45 | 5.13 | 1.96 | 🔴 same |
| R1+R2+R3 | 17,995 | 2.78 | −0.59 | 2.99 | 2.56 | ✅ passes everywhere |
| **K′ — R1+R2+R3+M1** | **17,827** | **2.71** | **−0.77** | **2.90** | **2.63** | ✅ **best policy that passes on both halves** |
| R1+R2+R3+M1+M2 | 17,542 | 2.85 | −0.40 | **3.06** | 2.62 | 🔴 M2 pushes OLD back over |

> **The pooled number and the holdout point at different rules, and the holdout is right.**
> `R1+R2+M1` reads **2.16** — by some distance the best pooled ECE any policy in this document
> produces — and it leaves the OLD half at **5.13**, because M1 is a *forward* signature: 1,525 of
> its 1,739 props rows are in the NEW half. A reader shown only the pooled column would ship the
> one policy here that fixes nothing about the back catalogue. **This is the fourth time in this
> document that the holdout refuses a policy the pooled number admits.**

**So the answer to the succession question is no, and the rule gets better for it.** M1 is
*additive*: it removes 168 rows the name arm cannot see (forced-to-half legs in markets that are
not Player Props containers, ECE 12.87), and R3 removes 19,980 rows M1 cannot see (the props
residual, 28.36 on the OLD half). **The design is K′ = R1 + R2 + R3 + M1**, and the name arm stays
— with its weakness recorded, and with M1 now standing beside it as the arm that does not depend on
a title.

*Run-to-run: six folds of the same control cell across five dimensions read n 41,127–41,294
(0.41% spread), ECE 4.64–4.72, gap +3.22–3.35. Every number in this document is quoted from the
fold it was measured in and the folds are not mixed; where two folds disagree (R1+R2+R3 at 2.78 here
vs 2.79 in §4) both are printed rather than averaged.*

---

## 8. Parked, not dropped

* **`polymarket/baseball` contains table-tennis markets.** Ids around 56.78–56.79M carry names like
  `Buianov Eduard vs. Bulat Alexandru` and `Emets Ihor vs. Solomko Serhii` with
  `llm_sport_category = 'baseball'` — Setka-Cup-shaped table tennis, `market_type = 'field'`, 4–5
  legs. **They do not reach the published curve** (every price on the sampled market is NULL, so
  `adj_opening_probability` excludes them), so this is not part of rank 1's defect and no number
  above moves if they are reclassified. It is the `#1081` football / motorsports misclassification
  family in a new category and belongs to whichever queue owns that.
* **The exact rail's cell-scoping approximation is now bounded at 5.7% on a grouped-source cell.**
  §1. Worth a `--scope-check` that folds the same cell with and without the category conjunct, the
  way `--edge-check` folds it at two widths.

---

## 9. THE RULING — Alex, 2026-08-28: **EXCLUDE NOW + FIX WRITER**

Staged to this lane as `runner-inbox/calibration/018-baseball-exclusion-ruled.md`, in Alex's
decision:

> *Option (b) EXTENDS to `polymarket/baseball`: the miswritten Player-Props rows leave the published
> curve with the same named, counted on-page disclosure as `kalshi/economics` (rank 1 crosses off,
> 4.71 → 2.71pp, cell stays material). The writer bug is being chased by lane1 (queue 022) — your
> exclusion is explicitly TEMPORARY-BY-DESIGN: when the writer is repaired the rows return and the
> exclusion empties itself; write that into the rule doc and the disclosure copy so the page never
> claims those rows are gone forever.*

This is the second of the four banked designs to have its decision taken, and it takes the pair to
**~5.7% of the published curve removed between two ruled rules** — the number §5 said had to be put
in front of Alex rather than accumulated one 3% at a time. It was, and it was ruled.

Rank 1's status moves from *designed* to **landable**. It still ships nothing today: K′ lives in the
frozen file and waits for ruling 009's amended lift.

### 9.1 🔴 This exclusion is NOT the same kind as `kalshi/economics`'s, and the difference is the reader's

The two cells now leave the curve through one filter and for two different reasons. Conflating them
is the specific error this section exists to prevent:

| | `kalshi/economics` (rank 2) | `polymarket/baseball` (rank 1) |
|---|---|---|
| what is wrong | the **rows** — an intraday index ladder's rungs were never competing answers to one question, at a price sum of 15–72 | the **price we wrote** — a real prop question, quoted 0.0355 by the market, published at 0.5005 by our own writer (§3) |
| the market's own quote | there is no single quote to be right about | **intact.** `opening_probability` is a coherent monotone prop ladder; only `calibration_probability` is a spray |
| ruled | option (b), APPROVED WITH DISCLOSURE | **EXCLUDE NOW + FIX WRITER** |
| when it ends | **never.** Structural and permanent | **when lane1 queue 022 repairs the writer** |

**So the honest sentence for rank 1 is not "these rows are ineligible". It is "we do not currently
have a price for these rows that is ours to publish."** ~2.7% of the published curve is being set
aside because *we* got it wrong, not because the market did, and a page that does not say so has
written off 24,000 real forecasts on our own defect and left no way back.

### 9.2 TEMPORARY BY DESIGN — the exclusion must empty itself

The design constraint, stated so a later reader cannot mistake it for an oversight:

1. **The allowlist entry `(polymarket, baseball)` is expected to be REMOVED.** It is not permanent
   scope. It is a hold placed on a cell while a named defect elsewhere is repaired.
2. **The rows return as good data.** They are not deleted, regraded, or written off. When the writer
   publishes the market's own quote again, K′'s M1 arm (rows forced into `[0.45, 0.55]` from an open
   >0.25 away) stops matching, R3 stops carrying them, and **the count in the payload falls to zero
   on its own.**
3. **The disclosure is rendered from the payload, never hard-coded.** When the backend stops
   emitting `polymarket/baseball` in `temporary_by_cell`, the sentence disappears from the page
   without a copy change. A hard-coded "baseball is temporary" line would still be on the page a
   year after the fix — the same lie in the other direction.
4. 🔴 **The falsifier.** If the writer fix lands and this exclusion does *not* empty, then the
   diagnosis in §3 was wrong — the near-0.50 spray was not the writer — and **the exclusion must be
   re-argued from scratch, not extended.** An exclusion that outlives its stated cause is an
   exclusion with no stated cause.

> **Note what this does NOT license.** R1 (half-spike pair) and R2 (published-pair incoherence) are
> the *historical residue* of the same family (§0) — 1,258 of their 1,284 rows are in the OLD
> holdout half. Fixing the writer forward does not un-write the back catalogue, so **R1 and R2 are
> expected to stay** after the writer is repaired, and only the M1/R3 population returns. The
> exclusion emptying itself means the *temporary* part empties, and the payload's per-cell count is
> what will say by how much. Nobody should promise the count reaches literally zero until it is
> measured — what is promised is that the rows come back and the count falls.

### 9.3 What lands in the frozen file, when the freeze lifts

| | |
|---|---|
| predicate | **K′ = R1 + R2 + R3 + M1**, §4. Every arm load-bearing; dropping R2 alone puts the cell back over the bar at 3.10 |
| scope | the **same** `(source, category)` allowlist as rank 2, gaining `('polymarket','baseball')`. **Not** `is_nonexclusive_bundle` — extending that flag to this cell is **REFUSED by measurement** (8.35, §2), and RULE E alone is 9.02. The allowlist is shared; the *predicate behind each entry is not* |
| payload key | the **same** `nonexclusive_bundle_filter`, with `excluded_by_cell["polymarket/baseball"]` and **`temporary_by_cell["polymarket/baseball"]`** carrying the revert condition |
| never | with M2 (pushes OLD back over at 3.06), nor with R3 restricted to sum > 15 (passes pooled, fails BOTH halves) |
| verdict | 4.71 → **2.71 pp**, 17,827 rows, **excess-outcomes 78,782 → 0**, holdout OLD 2.90 / NEW 2.63 |

**One honest caveat carried forward from §4:** 2.71 against a 3.0 bar is **0.77σ under it** — a pass,
and not a comfortable one. And because the temporary population is expected to *return*, this cell
will be re-scored when it does. **Crossing rank 1 off is a claim about the curve as it will be
published, not a claim that the cell is permanently solved.**

### 9.4 The disclosure contract, and it is BUILT

The page half is on this branch and green, in the same list item as rank 2's — one filter, one
bullet, so a reader who meets *"3.9% of the curve was removed"* meets *"and part of that is coming
back"* in the same breath rather than two bullets later.

* type: `CalibrationNonexclusiveBundleFilter.temporary_by_cell?: Record<string, string>` in
  `frontend/lib/api.ts` — keyed `"<source>/<category>"`, valued with **the condition that ends the
  exclusion**, so the page can name it without knowing it.
* page: `frontend/app/calibration/page.tsx`, gated on the map being present AND non-empty — a
  payload with only `kalshi/economics` in it renders **no** claim that anything comes back, because
  the ruling that approved rank 2 said no such thing.
* guard: `frontend/__tests__/lib/calibrationNonexclusiveBundleDisclosure.test.tsx`, `describe`
  **CAL-P119**, 7 tests, **6 mutations / 6 reds** — dropping the "gone for good" promise reds it;
  dropping the *rows re-enter the curve* promise reds it; hard-coding the cell name instead of
  binding to the payload reds it; removing the non-empty gate reds it; blurring "the price was
  wrong" into a generic "temporarily excluded" reds it; weakening the type reds it.

Four things the copy says, each pinned because each is a clause of the ruling: **temporary by
design**; the named cell **and the condition that ends it**; **the rows re-enter the curve and the
exclusion empties itself**; and *"we are not claiming they are gone for good — if this sentence
outlives the fix, the exclusion is the thing that is wrong."*

### 9.5 The handoff this rule depends on

**lane1 queue 022 owns the writer** (`022-baseball-writer-bug.md`), and its item 1 is the question
this lane could not answer: **is that writer feeding user-facing probabilities anywhere, or only the
calibration pipeline's copy?** If it is user-facing it is a P0 and it outranks everything here —
this exclusion cleans our *measurement* of a defect that would still be on event pages. Nothing in
this document should be read as fixing the defect. It hides it from the curve, deliberately and
disclosed, so the curve stops reporting our writer's error as the market's miscalibration.

Its item 3 is the return path: *"when fixed, note it in the report for calibration: the excluded
rows return as good data and CAL's exclusion empties itself."* **That report is the trigger to
remove `('polymarket','baseball')` from the allowlist and re-score the cell.**
