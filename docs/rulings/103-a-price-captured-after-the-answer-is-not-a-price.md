# RULING 103 — A price captured after the answer is not a price

date: 2026-08-20
author: Alex
via: Fable, on CAL-P077
issues: #1145 · #1978 · #2007 · #1912 · #1544

## AMENDMENT 2 — 2026-08-21 (Fable, on CAL-P085): THE NUMBER NOW MEASURES THE POLICY

`C-APPLY-PRE-WHICHPRICE-R2` returned **BLOCK** against amendment 1, on three P1s, and all three
were right. This amendment discharges them. **The decision is unchanged for the third time; what
changes is that the headline is now measured under the predicate this ruling actually authorises.**

### P1 #3 — the load-bearing one: the measurement was at the wrong granularity

This ruling approves an exclusion that drops **whole markets**. `PROVENANCE_FOLD_SQL` ended
`GROUP BY 1, 2, 3, 4`, so market identity was aggregated away **in SQL** and `FoldRow` carried
none. `3.7630 -> 1.7662 pp` therefore measured a **row-level** policy: on a mixed market it kept
the clean legs and dropped only the hindsight ones. That is not a policy anyone approved, and on
that data structure the approved one was **not expressible** — not unimplemented, inexpressible.

Repaired in CAL-P085 (#2087) by aggregating **legs -> market before folding**
(`WHOLE_MARKET_FOLD_SQL`), and re-measured over the full population, 49 of 49 cells, no sampling,
every statement fingerprinted:

| policy | row-level | **WHOLE-MARKET** | granularity Δ | n kept |
|---|---:|---:|---:|---:|
| `A_today` (control) | 3.7226 | **3.7226** | 0.0000 | 372,293 |
| `B_exclude_cp_absent` | 2.6560 | 2.8703 | +0.2143 | 300,876 |
| **`C_exclude_hindsight`** (approved) | 1.7434 | **1.7422** | **−0.0012** | **337,927** |
| `D_moved_price_only` | 3.8214 | 7.2437 | +3.4223 | 39,921 |
| `E_pregame_or_unknown_ts` | 2.9007 | 2.9074 | +0.0067 | 38,059 |

**The approved policy's headline is `3.7226 pp -> 1.7422 pp` (Δ −1.9804), dropping 34,366 of
372,293 rows (9.231%).** The granularity correction is **−0.0012 pp**. Twenty-six of the 32
cells with a measurable ECE on both sides move by **exactly zero** — they contain no mixed market
at all; the other 17 of the 49 are below `MIN_CELL_N` under policy C — and the largest
single-cell move is **−0.0102 pp** (`entertainment/quantity`).

**So the objection was correct AND the number survives it.** Those are not in tension and the
distinction is the whole reason the gate exists: R2 could not know the delta was 0.0012 pp, because
nobody had computed it, and "the mixed markets are only 0.0217% so it cannot matter much" is a
prediction, not a measurement. It is recorded here as a measurement.

**And it was NOT negligible for the comparators**, which is why "recompute the proposed one" would
have been the wrong repair: `D_moved_price_only` moves **+3.42 pp** under the lift and
`B_exclude_cp_absent` **+0.21 pp**. This strengthens the general clause below rather than weakening
it — whole-market, the intuitive fix is not `+0.073 pp` worse than doing nothing, it is
**+3.52 pp** worse.

**Which legs vote — a design choice this ruling made without writing down.** The apply's CTE is an
unfiltered `EXISTS` over `futures_outcomes`, so a market is condemned by **any** leg, including
legs the curve never reads. Measured both ways: deciding on curve-population legs only gives
**1.7417 pp** on 337,963 rows — **0.0005 pp and 36 rows** from the all-legs reading. Immaterial,
now on the record, and no longer an unexamined assumption.

Reconciliation, because a new statement that quietly reads a different population would move every
number below it in the same direction and look like nothing: `A_today` — untouched by any policy —
agrees with the row-level fold on **all 49 cells**, `n_delta 0`, `delta_pp 0.0`.

Artifact: `artifacts/cal-p085/price-provenance-whole-market.json`,
SHA-256 `e8b1d7d45df341138675cf28c4ab43799f45c14a6b6d6c03f8e6fe4a0482ec0d`, 113 statement
fingerprints, 0 missing, 0 cells unmeasured.

### P1 #1 — one denominator, stated consistently

Amendment 1 wrote "99.3%" and "the remaining 0.7%" over a population where neither is the
complement of 1.34%. The corrected line, replacing amendment 1's quoted block:

> Re-pricing was not declined. It is **unavailable for 98.663% of hindsight rows** — of **35,976**
> across 49 cells, only **481 (1.337%)** have any `futures_odds_snapshots` row before their own
> `resolution_date` and **27 (0.075%)** have one before `commence_time`; `hockey/container_member`
> is **0 of 1,259** and `basketball/quantity` is **0 of 8,387**. For the available **1.337%** it IS
> available, and those **481 rows are KNOWINGLY EXCLUDED for now**, tracked as a follow-up with the
> snapshot evidence attached.

The old "0.7%" was **`baseball/quantity` alone** (258/35,976 = 0.717%) wearing the whole
population's clothes.

### P1 #2 — the residual is 15 cells, not one

Amendment 1 named 258 baseball rows as though they were the re-priceable population. They are
**53.638% of it**. The other **223 of 481 (46.362%)** sit in 14 further cells, and several are
above the staged apply queue's own 1% falsifier: `weather/container_member` **24.000%** (6/25),
`politics/quantity` **7.000%** (7/100), `tech/quantity` **5.714%** (2/35), `entertainment/quantity`
2.469%, `soccer/quantity` 2.194%, `esports/quantity` 2.007%, `weather/quantity` 1.893%,
`esports/container_member` 1.210%, plus `weightlifting/quantity` (3/3) and `olympics/quantity`
(2/2) at 100% of two tiny cells. Full enumeration owed to **#2059**; the follow-up is scoped to all
481 rows, not to baseball.

### What this amendment does not do

It does not weaken the exclusion, it does not claim a new ruling number, and **it does not treat
R2's BLOCK as retracting Alex's re-consent to the ~17 h cost.** Those remain two objects: the
consent was to a **cost**, the BLOCK was about the **benefit**. The benefit is now measured at the
approved granularity and lands **0.0238 pp** from the figure Alex consented against — inside the
±0.05 pp band Fable set for "existing consent covers it" (CAL-P085 directive). Of that 0.0238,
**0.0012 is granularity** and the rest is population drift between the 08-20 and 08-21 reads
(`A_today` itself moved 3.7630 -> 3.7226).

### The general clause this amendment adds

**A measurement certifies a decision only if it was taken at the decision's granularity — and
"the difference must be tiny" is a prediction until someone folds it.** Three reviews and a ruling
passed over `GROUP BY 1, 2, 3, 4` because the *classes* being grouped were the right classes; the
defect was in what the grouping threw away, not in what it kept. The tell is available without any
measurement: the policy's own text said "whole markets" and the fold's output row could not name a
market. When a decision's unit of action is not a column in the evidence, the evidence is about
something else.

## AMENDMENT — 2026-08-20 (Alex, via Fable, on CAL-P081): EXCLUDE NOW, RE-PRICE AS FOLLOW-UP

`C-APPLY-PRE-WHICHPRICE` returned **BLOCK** against the premise below, and it was right to. The
premise said re-pricing "was measured to be unavailable over the whole population". That is true
of 99.3% of the population and **false of one cell**: **258 of 4,354 `baseball/quantity`
hindsight rows (5.93%) carry a `futures_odds_snapshots` row before their own `resolution_date`,
and those 258 are 53.6% of all 481 re-priceable hindsight rows in the corpus.** A policy
described as impossible is executable for a majority of the rows where it is executable at all.

**The ruling's DECISION is unchanged; its PREMISE is corrected, and the gap is filed rather than
closed by wording.** The uniform exclusion ships exactly as ruled, because 481 of 35,976 rows
cannot be re-priced into a curve and a per-row re-price of 258 of them is a different piece of
work with its own evidence bar. Those 258 are **KNOWINGLY EXCLUDED for now** — named, counted,
and owed — not swept in behind a claim that nothing could be done for them.

The correct premise line, replacing the sentence marked below:

> Re-pricing was not declined. It is **unavailable for 99.3% of hindsight rows** — of **35,976**
> across 49 cells, only **481 (1.34%)** have any `futures_odds_snapshots` row before their own
> `resolution_date` and **27 (0.075%)** have one before `commence_time`;
> `hockey/container_member` is **0 of 1,259** and `basketball/quantity` is **0 of 8,387**. For
> the remaining 0.7% it IS available, and **258 `baseball/quantity` rows with verifiable
> pre-resolution snapshots are KNOWINGLY EXCLUDED for now**, tracked as a follow-up with the
> snapshot evidence attached.

Two things this amendment deliberately does not do. It does not weaken the exclusion — a
hindsight price is still not a price, and a row we could re-price is still not a row we have
re-priced. And it does not claim a new ruling number: the decision is the one Alex already made,
and re-banking it as ruling 112 would put two authorities on one question.

**The cert re-runs against THIS text.** `C-APPLY-PRE-WHICHPRICE` certifies the measurement as now
stated, not the old claim; the BLOCK it returned was against a premise that no longer exists.

## The general clause the amendment adds

**A measurement that holds for 99% of a population is not a measurement about the population —
name the residual and file it.** "Unavailable" and "unavailable except for 258 rows we can point
at" support the same decision and describe different worlds, and only the second one leaves a
successor able to find the rows. The failure mode is not the decision; it is that the strong
phrasing removes the follow-up from existence.

## The ruling

**The hindsight-capture exclusion — `MC-PACK-CAL-P077-HINDSIGHT-CAPTURE.md` policy C — is
APPROVED, GATED ON CERT.**

`opening_captured_at > resolution_date` means our earliest observation of the row postdates the
market's resolution. Such a row carries **the answer wearing a price's clothes**. Those are
phantoms under standing ruling 8, and they are excluded from the published curve.

**Exclusion is the measured-only-sound option, not the fallback.** Re-pricing was not declined —
it was measured to be unavailable over the whole population, not a sample: of **35,976** hindsight
rows across 49 cells, **481 (1.34%)** have any `futures_odds_snapshots` row before their own
`resolution_date`, and **27 (0.075%)** have one before `commence_time`. `hockey/container_member`
is **0 of 1,259**; `basketball/quantity` is **0 of 8,387**. "Re-price against venue close" has
nothing to read. A policy cannot be preferred over one that cannot execute.

## The three conditions — the apply fires only when ALL THREE hold

1. **`C-APPLY-PRE-WHICHPRICE` passes its named attacks.** Not a review — the four attacks in
   §8.3 of the pack, verbatim, with Control 1 as the falsifier.
2. **`program/calibration-74` is DEPLOYED.** The instrument that measured this
   (`calibration_price_provenance.py`) and the disclosure that makes the page honest about what
   it is serving both ride that branch. An apply graded against a page that cannot describe its
   own inputs is ungradeable (#2007).
3. **The scoped exception GO file exists** — `GO-CAL-P078-HINDSIGHT-EXCLUSION-EXCEPTION.md`,
   ruling 033: a GO file binds only its addressee, and an exception nobody wrote down is not one.

Any one of the three absent means the apply does not fire. This is a conjunction, not a checklist
to be argued down.

## The ruling-009 exception — GRANTED, and scoped to exactly one thing

**Scope: EXACTLY ONE exclusion CTE in `_calibration_population_ctes`, in the CAL-P039 GO-file
shape.** Nothing else in the frozen file is opened by this ruling. Not a refactor that happens to
pass through, not a "while we are in here", not a second predicate that shares the same edit.
`_main_input_fingerprint()` moving is an EXPECTED consequence of the one CTE and is the cost
accepted; it is not a licence for a second cause to move it.

Three properties are required of the apply, all three specified rather than hoped for:

* **READ-SIDE.** No write to `is_winner`, no write to `calibration_probability`, no write to
  `opening_probability` (gotcha #21). The rows stay in the database with their provenance intact
  and stop entering the curve.
* **WHOLE MARKETS.** `opening_captured_at` is per-outcome and `resolution_date` is per-market, so
  the naive predicate could split a field and break the sum-to-1 invariant. It drops whole
  markets: winners and losers together, which is the standing requirement for every exclusion on
  this curve. The **101 mixed markets in 464,777 (0.0217%)** go whole too.
* **REVERSIBLE IN ONE COMMIT.** A re-grade would not be. That asymmetry is why the read-side form
  is the approved one and the write-side form was never on the table.

## Why this is a decision and not a fix

It removes **9.3% of the published curve** (34,336 of 370,677 rows) and moves the product's
most-cited number from **3.763 pp to 1.766 pp**. A change that large to the headline is Alex's
call, and CAL-P077 was right to stop at PLAN ONLY and ask.

The honest costs are ruled accepted, all of them named rather than discovered later:

* `politics/container_member` gets **worse** by +0.28 pp while losing 15.9% of its rows. Named,
  accepted, and specifically routed to the cert as a second look.
* `football/quantity` (37 → 29) and `weather/container_member` (37 → 12) fall below `MIN_CELL_N`
  and become an **ABSENCE with a reason**, never a fixed cell. A vanished cell read as a fixed one
  is ruling 075's second clause arriving on the scoreboard.
* The predicate is outcome-blind in **definition** and not in **effect** — hindsight rows have a
  different winrate (hockey 0.296 vs 0.430). That is the corruption itself, and Control 1 is the
  only thing carrying the argument against the other reading. The cert attacks it there.

`tech/quantity` is **not** explained and is **not** claimed. A mechanism that explained all five of
#1145's cells would be a mechanism fitted to five points.

## The general clause

**A row-dropping fix is graded on the rows it keeps, and on the cells where the mechanism is
absent.** Dropping rows can always lower an error metric by dropping hard rows, so the load-bearing
evidence is never the headline delta — it is (a) the cells with no mechanism that did not move, and
(b) the kept sub-population being calibrated rather than merely better. Policy D is the proof: the
intuitive fix, discarding 69% of the population, makes the pooled curve **worse** (+0.073 pp). A
fallback price is not a bad price. A hindsight price is.

Routed to `docs/doctrine.md` when the numbering permits — the clause survives deleting this case,
and the calibration curve is not the only place something gets dropped to make a number look
better. **Do not renumber to fill a gap** (see ruling 102's debt: clauses 15/16 are claimed and
unmerged by latency, and 16 depends on 15).

## Sibling rulings

- **009** — the freeze this scopes an exception to. The exception is one CTE; the freeze stands
  for everything else.
- **033** — a GO file binds only its addressee. Condition 3 exists because of it.
- **039 (GO-CAL-P039-EXCEPTION.md)** — the SHAPE this exception copies: one predicate, proved
  sound by construction, nothing else in the file moves.
- **075, second clause** — "could not check" must never render as "nothing to report". The two
  cells that fall below `MIN_CELL_N` are the specimen on this curve.
- **102** — the instrument that measured this obeyed ruling 102 and the rule still caught its
  author twice. That is the argument for both.
