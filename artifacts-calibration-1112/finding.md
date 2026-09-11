# calibration/1112 — the per-bookmaker defect is owned by NONE of the three layers, and the two US Open cells split

Stamped from `TZ=America/Los_Angeles date`: **Fri 2026-09-11, 12:00pm PT / 19:00Z**.

Branch `program/calibration-1111-threshold-ladder-one-forecast`, off master `ab88bad1`.

CAL-P1112 ARM 1 is **still blocked** (#5001 open at 18:12Z — verified, not assumed), so this session
took ARM 3: *"Establish which of the three layers owns it before editing."* That instruction was the
right one and it paid: **the answer is that none of them does, and no layer needed editing.**

---

## 1. The question ARM 3 asked, and the answer

The directive framed "nine sportsbooks quoting one match counted as nine forecasts" as owned by one of:

1. the producer — `_precompute_bookmaker_calibration` (`backfill_winners.py:8806`)
2. the reader — `read_bookmaker_curve_rows` (`precompute_calibration.py:243`)
3. the consumer — how subcohort scoring consumes those rows

**It is none of the three.** Layer by layer:

* **The producer is correct, and its own SQL proves the clustering rather than causing it.** The grain
  is `DISTINCT ON (ee.id, os.bookmaker)` — one row per (game, sportsbook). Its stated contract is
  "each bookmaker's closing moneyline paired with the game outcome", and one row per (bookmaker, game)
  is what a *per-bookmaker* curve IS. The directive's caution here was well placed.
* **The reader is transport.** It owns the named-refusal behaviour (D21) and nothing about grain.
* **The consumer's model is correct AND the remedy is already built.** `calibration_scoring` does not
  assume independence as a matter of design — it carries `sigma_basis`, and the basis
  `measured_cluster_bootstrap` clusters by the GAME. That is exactly the correction the defect
  describes.

**The actual gap is COVERAGE of the measured-sigma ledger.** The overlay's own served field says so:
`ledger_cells: 20`, `material_cells: 51`, `material_by_ledger_status: {ABSENT: 32, CARRIED: 1,
FRESH: 6, STALE: 12}`. The two US Open cells were among the 32 ABSENT, so they were decided by
`binomial_row_estimate` — a sigma that assumes 1,300-odd independent forecasts on a population the
producer's own `DISTINCT ON (event, bookmaker)` guarantees is clustered by match.

**Why the fallback is not merely conservative here.** For this source the within-cluster correlation
of the response is **exactly 1 by construction** — every sportsbook quoting one match shares one
realised `won` (`calibration_bookmaker_cell_fold.py:442`). This is not a modelling assumption that
might hold; it is arithmetic. So a row-grain sigma on any `odds_api_bookmaker` cell is known-wrong
before it is computed, and the board still *decided* with it (D62 made sigma decide).

**The evidence that this was never speculative:** of the six `odds_api_bookmaker` cells that had been
measured before today, **six of six** had their sigma cut (1.7x–3.3x) and **four of six** moved
`OVER_BAR_ESTABLISHED → OVER_BAR_UNESTABLISHED`. Not one survived unchanged. The two US Open cells
were simply never run — the tournament is two weeks old, so they are new material cells.

## 2. What I measured

Existing tooling, unmodified: `scripts/calibration_bookmaker_cell_fold.py --grain game_bucket --sigma`
(bounded through the read-only `/api/admin/db-query` rail, week-chunked, seeded). Both folds
**reproduced the published ECE exactly** — 6.53 vs 6.53 and 10.19 vs 10.19 — so this is a measurement
of the published cell, not of a reconstruction.

| cell | book-rows | games | replication | ECE | bar | sigma_row | **sigma measured** | verdict |
|---|---|---|---|---|---|---|---|---|
| `odds_api_bookmaker/tennis_atp_us_open` | 1,306 | 124 | **10.53x** | 6.53 | 2.5 | 2.91 | **1.57** | **NOT established** |
| `odds_api_bookmaker/tennis_wta_us_open` | 1,325 | 126 | **10.52x** | 10.19 | 2.5 | 5.60 | **3.08** | **still established** |

"Nine sportsbooks quoting one match" is measured at **10.5** on both cells. `effective_n` is 381 (ATP)
and 402 (WTA), against raw n of 1,306 and 1,325.

**The two cells split, and that is the whole value of measuring rather than assuming.** A blanket
"correct for replication and both come off the queue" would have been wrong: the WTA cell's ECE of
10.19pp against a 2.5pp bar survives a 3.3x variance correction and is a **real, established
miscalibration** that stays on the repair queue. The ATP cell's does not.

## 3. What I shipped

`backend/app/data/calibration_measured_sigma.json` rebuilt via the documented path
(`calibration_sigma_ledger.py --build artifacts/cal-p1*/sigma-*.json`), plus the two artifacts under
`artifacts/cal-p1112/` so the glob keeps working for the next session.

Rebuild verified against a backup rather than trusted: **22 entries from 27 artifacts; 2 ADDED,
0 REMOVED, 0 CHANGED.** (`--build` rebuilds the *whole* ledger from the globbed set, so building from
only the two new artifacts would have silently dropped the other twenty. Worth banking.)

No change to any of the three layers. No population change, so the q269 fingerprints are untouched and
ARM 1's two deliberate tripwires stay exactly as red as they were.

## 4. The served effect, stated honestly

Rescoring the live payload with the new ledger: **queued cells 11 → 10**, and the needle
**40 → 41 of 51 cells at bar**.

**That needle move is not an accuracy improvement and must not be reported as one.** `cells_at_bar` is
defined as `len(material) - len(queued)` — "not on the repair queue" — so it bundles PASS with
"over bar but not established". The ATP cell's ECE is still 6.53pp against a 2.5pp bar; nothing about
its pricing improved. What changed is that we can no longer *establish* that gap from 124 matches, so
the cell stops claiming a verdict it had not earned and stops occupying a repair slot.

This is the same distinction §7 of calibration/1111's finding drew about the ladder, and it is the
sentence Alex should get: **a cell left the queue because the evidence was never sufficient, not
because the number got better.**

I predicted before measuring that the needle would NOT move, reasoning that `cells_at_bar` counted
only PASS cells. That was wrong — I checked the definition instead of asserting it, and the
measurement is what stands.

## 5. Residual — named, not fixed

* **`MIN_CELL_N = 1000` is applied to raw n, never to `effective_n`.** The ATP cell is "material"
  on 1,306 book-rows while carrying 381 effective forecasts; on the same arithmetic the WTA cell has
  402. Every `odds_api_bookmaker` cell in the board's material set is admitted on a count roughly 10x
  its independent content. Changing that is a methodology change — it moves which cells are scored —
  so it needs the population-bump protocol and a ruling, and it is **not** in this session's scope.
  It belongs in the same conversation as ARM 1's q270 bump. Filed as the next item, not silently done.
* **30 material cells remain ABSENT from the ledger** after today (32 − 2). The six previously
  measured `odds_api_bookmaker` cells moved 4 of 6; there is no reason to think the remaining ABSENT
  cells are better served by a row-grain sigma. Measuring them is cheap and mechanical per cell.
* The ledger entries added today are `population_version: q269`. ARM 1's q270 bump will mark them
  STALE — which still decides (12 STALE entries decide on today's board), so this is not wasted work,
  but a re-measure after q270 is the tidy follow-up.

## 6. Traps banked

1. **A `--build` that globs is a full rebuild, not an append.** Diff against a backup and assert
   ADDED/REMOVED/CHANGED counts; "22 cells from 27 artifacts" alone would not have told me the other
   twenty survived intact.
2. **A payload probe that reads `source`/`category` on a scorecard cell gets `None` on both** — the
   field is `cell` ("kalshi/golf"). My first read printed eleven rows of `null` and looked like a
   serving defect. Print the key list before believing an absence.
3. **BSD `find` has no `-newermt`** — it exits non-zero and prints nothing, which reads exactly like
   "the files were never written". They had been.
4. **A backgrounded command whose stdout you redirected leaves the harness task file 0 bytes.** The
   0-byte file is not evidence the run produced nothing; read your own redirect target.
5. `--out` on a script invoked from `backend/` resolves against `backend/`, not the repo root.
