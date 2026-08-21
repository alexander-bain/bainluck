# RULING 103 — A price captured after the answer is not a price

date: 2026-08-20
author: Alex
via: Fable, on CAL-P077
issues: #1145 · #1978 · #2007 · #1912 · #1544

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

## SECOND AMENDMENT — 2026-08-21 (Alex: **AMEND + PROCEED** on WHICHPRICE-R2's BLOCK)

`C-APPLY-PRE-WHICHPRICE-R2` returned **BLOCK** and it was right on all three counts. Alex ruled
**amend the premise and proceed** — the exclusion decision stands, the numbers describing it do
not. Every figure below is codex's, reproduced from
`artifacts/cal-p077/price-provenance.json` (SHA-256 `196748fa…54162`), not re-derived here.

### 1. The denominator, stated once and consistently

The first amendment's premise line above says **99.3% / 0.7%**. That is arithmetically false, and
the 0.7% is the baseball subset wearing the whole population's clothes. Corrected:

| quantity | value |
|---|---|
| hindsight rows, 49 cells | **35,976** |
| with a pre-resolution snapshot (**recoverable**) | **481** = **1.337%** |
| **unavailable** | **35,495** = **98.663%** |
| with a pre-commence snapshot | 27 = 0.075% |
| of the 481: `baseball/quantity` | **258** (53.638% of the recoverable set; 5.926% of its own 4,354) |
| of the 481: **everywhere else** | **223** (46.362%) |

The zero controls reproduce exactly: `hockey/container_member` **0 of 1,259**,
`basketball/quantity` **0 of 8,387**.

**The premise line above is SUPERSEDED by this table.** It is left in place, unedited, so the
correction is legible — the same treatment the ~5-6-beat cost figure got on the GO file.

### 2. Baseball is not the residual — 223 of the 481 are elsewhere, and eight cells clear 1%

The first amendment named 258 baseball rows as though they were the knowingly-excluded set. They
are 53.6% of it. The full residual is **15 nonzero cells**, and the queue's own >1% falsifier
fires on eight of them:

`weather/container_member` **24.000%** (6/25) · `politics/quantity` **7.000%** (7/100) ·
`tech/quantity` **5.714%** (2/35) · `entertainment/quantity` **2.469%** (2/81) ·
`soccer/quantity` **2.194%** (12/547) · `esports/quantity` **2.007%** (6/299) ·
`weather/quantity` **1.893%** (31/1,638) · `esports/container_member` **1.210%** (103/8,513) ·
plus two tiny 100% cells (`weightlifting/quantity` 3/3, `olympics/quantity` 2/2).

**#2059's scope is hereby the full 481 across 15 cells, at MARKET granularity** (see 3), not
258 baseball rows.

### 3. 🔴 The granularity, stated truthfully — the apply drops WHOLE MARKETS, and the headline pp was measured ROW-BY-ROW

This is R2's load-bearing finding and the one that changes what this file may claim.

The approved apply excludes **whole markets**. The measurement behind `3.7630 → 1.7662 pp` does
not: `PROVENANCE_FOLD_SQL` ends `GROUP BY 1, 2, 3, 4` over `(price_class, capture_class, grade,
bin)`, so **market identity is aggregated away in SQL before any Python selector runs**;
`FoldRow` carries no market id and `C_exclude_hindsight` is a per-row predicate. codex's
adversarial specimen is the whole argument in one market:

> **the mixed two-leg specimen** — one market, one hindsight leg and one pregame leg. Policy C as
> measured **retains the pregame leg** (`n=1`). The approved whole-market policy **retains
> neither** (`n=0`). Same market, same data, two different answers.

So **`3.7630 → 1.7662 pp` is a number about a different predicate from the apply this ruling
authorises.** It is not withdrawn as a measurement; it is withdrawn as *this apply's* benefit.

**What the market-level evidence does say**, summed across all 49 cells' `leg_split.totals`:

| | markets |
|---|---|
| total | **464,777** |
| all legs after resolution | **24,774** |
| **mixed** (≥1 after-resolution leg, ≥1 not) | **101** (0.0217%) |
| no after-resolution leg | 439,902 |

⚠️ **N — the count of markets holding the 481 recoverable legs — IS NOT IN THE EVIDENCE, and I
am not going to invent it.** The artifact carries `reprice_feasibility` at ROW level only
(`n_after_resolution`, `with_any_snapshot`, `with_pre_resolution_snapshot`) and `leg_split` at
MARKET level, and nothing joins them. A direct production count timed out at the read-guard's
25 s ceiling. What is known:

* **24,875 markets are dropped whole** by the approved apply (24,774 all-after + 101 mixed).
* The markets holding the 481 recoverable legs are a **subset of those 24,875**, bounded
  **1 ≤ N ≤ 481**.
* Naming N exactly is now part of **#2059**, whose scope this amendment makes market-granular.

Stating a bound instead of a number is the point of the whole exercise: this is the third premise
correction on one ruling, and every one of the three was a figure that read as measured and was
not.

### 4. This is the third correction, and that is the cert working — not a smoothing job

Written into the history deliberately, at Alex's instruction, rather than tidied away:

| # | when | what was wrong | who caught it |
|---|---|---|---|
| 1 | 2026-08-20 | "re-pricing was declined" — it was *unavailable*, and for 481 rows it was available and being excluded | CAL-P081 |
| 2 | 2026-08-21 | the ~5-6-beat cost was really **~17 h** (7.67 units/beat over 128 units) — 3× what was consented to | CAL-P083 (re-consent taken) |
| 3 | 2026-08-21 | **this one** — 99.3% is 98.663%, 258 is 481 across 15 cells, and the headline pp measures a row-level predicate against a whole-market apply | `C-APPLY-PRE-WHICHPRICE-R2` |

**A ruling that needed its premise corrected three times by its own certification gate is a gate
doing its job, not a ruling failing.** Each correction was found before the apply spent anything;
the exception is still unspent. The reading to refuse is that three corrections discredit the
decision — the decision (a hindsight price is not a price) has never moved, and none of the three
touched it. What moved every time was a *number describing* it, which is exactly the class of
claim a cert exists to attack.

### What remains OWED before Gate B can go green

1. **#2087** — a market-aware fold, so whole-market policy C is computable at all.
2. The approved policy's **real** ECE delta, recomputed on that fold. If it differs materially
   from 1.77 pp, **Alex sees the new number** — the re-consent was to ~17 h for *that* benefit.
3. **#2059** at market granularity: the full 15-cell, 481-row residual, and N.
4. **`C-APPLY-PRE-WHICHPRICE-R3`**, certifying against the corrected measurement. It does not
   exist and is not staged; `CODEX-NEXT.md` holds a different apply and that chain is depth one.

Alex's re-consent to the cost stands and is not retracted by any of this.

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
