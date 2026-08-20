# RULING 103 — A price captured after the answer is not a price

date: 2026-08-20
author: Alex
via: Fable, on CAL-P077
issues: #1145 · #1978 · #2007 · #1912 · #1544

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
