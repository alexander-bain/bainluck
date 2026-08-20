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
