# THE THRESHOLD TABLE — the per-cohort finish line, for Alex's ratification

**PRE-RATIFICATION.** Nothing on this page is live. `calibration_scorecard.py` still renders the
flat 3.0 pp bar and will keep doing so until Alex rules. Re-render with
`python3 backend/scripts/calibration_threshold_table.py --live --markdown`.

Payload `2026-08-28T17:33:03Z`, population `q268`, headline `mce_closing_line` **1.90 pp**.

---

## THE ASK, in one table

| class | what a cell in it is | **bar** | change |
|---|---|--:|---|
| **A** `A_multibook_consensus` | every `odds_api*` cell — devigged consensus of many bookmakers | **2.5 pp** | 🔻 tighter |
| **B** `B_exchange_contest` | Kalshi/Polymarket on a scheduled contest (baseball, soccer, esports, golf …) | **3.0 pp** | unchanged |
| **C** `C_exchange_standalone` | Kalshi/Polymarket on a standalone or long-horizon question (economics, tech, politics, weather …) | **3.0 pp** | unchanged |

Everything else in `CALIBRATION-SCORECARD.md` §1 is unchanged: materiality floor n ≥ 1,000 (the
payload's own `min_category_outcomes`), significance gate 2.0σ with σ = 50/√n, headline regression
guard ≤ 2.0 pp, and the live-curve criterion.

### What it costs, measured on today's payload

| table | bar A / B / C | **cells at bar** | queued | queued excess-outcomes |
|---|---|--:|--:|--:|
| incumbent (flat) | 3.0 / 3.0 / 3.0 | **30/49** | 19 | 480,342 |
| **proposed** | **2.5 / 3.0 / 3.0** | **29/49** | 20 | 503,236 |

One cell moves: `odds_api_bookmaker/icehockey_nhl` (3.89 pp on 8,658 rows) goes from
over-bar-unestablished at 1.65σ to queued at 2.59σ. **The finish line barely moves, and that is the
point** — this is a hole being closed, not a target being redrawn.

| class | bar | cells | at bar | queued | outcomes |
|---|--:|--:|--:|--:|--:|
| A | 2.5 | 18 | 12 | 6 | 104,984 |
| B | 3.0 | 20 | 11 | 9 | 637,723 |
| C | 3.0 | 11 | 6 | 5 | 112,905 |

---

## 1. The derivation, and the derivation it rejects

The obvious way to set a per-cohort bar is from the cohort's own current distribution — "the bar is
the class's 25th percentile." **That is circular and this proposal refuses it.** A bar that moves
every time a cell improves is not a finish line; the program can never arrive at it. A finish line
must be derived from something outside today's measurement.

Two such quantities exist, and they justify exactly one departure from a single flat bar.

**Reader actionability — 3.0 pp, and it does not vary by cohort.** A 3 pp error means a market
published at 60% comes in between 57% and 63%, which is inside the width a reader can act on. That
is a property of what a person does with the number, not of the venue that produced it. It is
already the bar the program has ranked against for four weeks (`n × (ece − 3)`), so adopting it
keeps every banked mechanism comparable to its own history.

**Estimator averaging — the one reason to hold a class tighter.** `odds_api*` cells are a *devigged
consensus of many bookmakers*: the published price is an average of independent estimates, so its
idiosyncratic quoting error is smaller by construction than a single thin order book's. This is
structural, fixed in advance, and does not move as cells improve. Class A also carries the game
cards — the most-read surface in the product — so it is where a residual error costs the most
readers. **2.5 pp.**

## 2. The measurement that KILLS a looser bar for the thin cohorts

The natural counter-proposal is a *looser* bar for class C: thin books, wide spreads, distant
settlement — surely 3 pp is unreasonable there. The payload says no.

| class | best cell | 2nd best | median | over 3.0 |
|---|---|---|--:|--:|
| A | `odds_api_totals/basketball_ncaab` **0.80** | `odds_api_spreads/basketball_ncaab` 1.26 | 3.08 | 10 of 18 |
| B | `kalshi/hockey` **0.92** | `kalshi/basketball` 1.33 | 3.33 | 11 of 20 |
| **C** | `polymarket/weather` **1.63** | `kalshi/politics` **2.08** | 4.48 | 9 of 11 |

**Every class already contains a published cell far under 3.0 pp, class C included.** A class that
has proved 3.0 pp reachable on its own rows has not earned a bar above it. The honest reading of
"thin books and long horizons" is that they raise the *variance* of a cell's estimate — which the
2.0σ gate already prices — not that they license a larger *bias*.

This is encoded, not just argued: `test_no_class_is_looser_than_the_reader_bar` fails if a future
edit relaxes any class above the reader bar. Relaxing one has to delete a test to do it.

## 3. The precondition that is NOT a threshold

CAL-P112 diagnosed the two cells the directive named, and neither is miscalibrated. Both are
**mis-populated**:

- **`kalshi/tech`** (11.10 pp, worst on the board) is **79% cumulative-threshold ladder rows by n** —
  40-rung "Price of NVIDIA H200 compute" markets where every rung resolves YES. Remove that class
  and the cell reads **3.80 pp, gap −0.30**.
- **`polymarket/esports`** (8.08 pp) is **29% one-winner realizations of the same non-partition
  shape**, surviving a filter whose test is the realized winner count. Remove it and the surviving
  core reads **3.02 pp, gap −0.85**.

A 40-rung ladder is not a forecast of one question, and **no bar — tight or loose — is the right
response to a row that should not be in the population.** So the table carries a precondition
rather than a fourth threshold:

> **Criterion 6 (proposed).** A cell whose published population is dominated by non-partition
> bundle rows is queued for a **population** fix, not scored as a calibration failure. The
> disposition is an exclusion rule, and it is evidence-gated per cohort on the census the payload
> already publishes (`nonexclusive_bundle_census.by_category`: the bundle cohort's ECE must
> materially exceed the remainder's before the category joins the exclusion allowlist).

Without criterion 6 the two worst cells on the board get worked as calibration problems, which is a
cycle each and moves nothing. The rule designs are banked at
`artifacts/cal-p112/RULE-DESIGN-kalshi-tech.md` and
`artifacts/cal-p112/RULE-DESIGN-polymarket-esports.md`.

## 4. Two things this proposal deliberately does not do

- **It does not touch the materiality floor or the σ gate.** Both are inherited from
  `calibration_scorecard.py` rather than re-declared, so the scorecard and this table can never
  disagree about which cells are in scope.
- **It does not change what "DONE" means.** DONE is still: every material cell at its bar, headline
  ≤ 2.0 pp, curve live, holding across two consecutive producer beats. Only the per-cell bar's
  cohort-dependence is on the table.

## 5. What ratification changes

Three lines in `calibration_scorecard.py` (`BAR_PP` → the class map + `classify`), and the scorecard
re-renders. Until then the flat bar is the live one and every CAL report says so.

---

## THE NEEDLE, pre-ratification

```
NEEDLE: calibration 29/49 cells-at-bar @ 2026-08-28T17:33:03.920530+00:00
```

Under the incumbent flat table the same payload reads **30/49**. Per
`.claude/handoff/NEEDLE-SPEC.md` the metric changes only by Alex ruling — so if the proposal is
declined, the series starts at 30/49 and this line is void.
