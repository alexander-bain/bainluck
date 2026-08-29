# CAL-P128 — the board's σ column, measured on twelve cells

**Published curve 1.89 pp, FLAT →** (population `q268`, unmoved for a fourteenth
reading — per §6e a re-publish is not a datapoint and none was recorded).

Queue 027 item 1: *"σ-sweep the board first… find out how many of them are real
before designing another rule. This is the highest-value thing on the board right
now and it may shorten the merge-fest considerably."*

It was worth doing. **It does not shorten the merge-fest.**

---

## 1. The result

Twelve of the fourteen working board cells now have a measured cluster-bootstrap
σ. (The board is 20 queued cells; six are `odds_api_bookmaker` and stay off per
CAL-P120 §6g.) `polymarket/esports` and `polymarket/soccer` are outstanding.

| cell | ECE | excess | σ board | σ measured | var ratio | coverage | verdict |
|---|--:|--:|--:|--:|--:|--:|---|
| `polymarket/baseball` | 4.80 | +1.80 | 7.53 | **5.26** | 1.93 | 0.939 | ESTABLISHED |
| `kalshi/economics` | 5.29 | +2.29 | 7.75 | **5.82** | 1.82 | 1.027 | ESTABLISHED |
| `polymarket/esports` | 7.59 | +4.59 | 10.88 | — | — | — | *unmeasured* |
| `polymarket/soccer` | 3.42 | +0.42 | 2.75 | — | — | — | *unmeasured* |
| `kalshi/crypto` | 7.60 | +4.60 | 6.22 | **6.82** | 0.83 | 1.005 | ESTABLISHED |
| `kalshi/entertainment` | 5.21 | +2.21 | 4.04 | **4.52** | 0.81 | 1.014 | ESTABLISHED |
| `kalshi/golf` | 3.88 | +0.88 | 2.52 | **1.48** 🔴 | 2.91 | 1.008 | **NOT ESTABLISHED** |
| `polymarket/cricket` | 8.11 | +5.11 | 5.83 | **8.36** | 0.48 | 0.998 | ESTABLISHED |
| `polymarket/basketball` | 4.24 | +1.24 | 2.84 | (1.51) | 2.29 | **0.641** | **CANNOT DECIDE** |
| `polymarket/golf` | 5.45 | +2.45 | 3.94 | **2.50** | 2.47 | 0.997 | ESTABLISHED |
| `polymarket/economics` | 3.90 | +0.90 | 2.04 | **2.05** | 1.00 | 1.005 | ESTABLISHED |
| `polymarket/hockey` | 7.36 | +4.36 | 4.16 | (4.29) | 0.73 | **0.780** | **CANNOT DECIDE** |
| `kalshi/tech` | 10.96 | +7.96 | 5.52 | **4.13** | 1.81 | 1.012 | ESTABLISHED |
| `polymarket/tech` | 4.91 | +1.91 | 2.01 | **2.23** | 0.81 | 0.988 | ESTABLISHED |

**Nine established, one refuted, two undecidable.** The one refutation is
`kalshi/golf`, which CAL-P127 already found and filed as 17-CAL. The sweep
removed no cell that was not already off.

---

## 2. Why the sweep did not shorten the board — the inherited framing was
half right

The handoff's reasoning was: rows inside a market are correlated, a binomial SE
over ROWS therefore under-states the true SE, so the board's σ is too big, so
cells are on the queue that the sample cannot distinguish from the bar. Seven
cells had already fallen to that argument.

That mechanism is real and it is visible here — `kalshi/golf` 2.91, `polymarket/golf`
2.47, `polymarket/basketball` 2.29, `polymarket/baseball` 1.93. But it is only
one of two effects, and **the second one points the other way.**

The board's SE is `50/sqrt(n)` — a binomial at `p = 0.5`, the *maximum-variance*
case. The scorecard's own docstring calls this "CONSERVATIVE" and it is right
about that. On cells whose bins sit far from 0.5, the true variance is well under
that bound, and the slack **outweighs** the clustering inflation:

- `polymarket/cricket` — variance ratio **0.48**. Board 5.83 σ, measured **8.36**.
- `polymarket/hockey` 0.73 · `kalshi/entertainment` 0.81 · `polymarket/tech` 0.81 ·
  `kalshi/crypto` 0.83.

Five of twelve cells come out **more** established than the board thought, one
lands exactly on 1.00, and six come out less. So:

> **The board's σ column is wrong in both directions, and the net effect on the
> queue is approximately zero.** A sweep that removes one already-known cell out
> of twelve is not a shortcut to the merge-fest; it is a confirmation that the
> merge-fest is real work.

This also renames a number. CAL-P127 quoted golf's **2.91** as a "design effect".
It is reproduced exactly here, but it is not a textbook design effect — a design
effect divides by the SRS variance and cannot fall below 1 through clustering.
This ratio divides by the board's max-variance bound, which is why cricket's is
0.485. The ledger stores it as `variance_ratio_vs_board` for that reason.

---

## 3. The trap: the one cell the sweep would have removed is the one it cannot
measure

`polymarket/basketball` reads σ 1.51 measured against 2.84 on the board — a clean
refutation, 16,287 excess-outcomes, and it is the cell whose candidate rule
(parked CAL-P125-2) has been waiting three sessions for a holdout.

**It is not a refutation, because the rail and the payload are not looking at the
same cell.** The exact rail selects 8,426 rows where the payload publishes 13,135
— coverage 0.641.

The tempting reading is "the rail is under-selecting, so the SE is measured on a
subsample, so it is too big, so the σ is too small". That reasoning is sound only
if the payload is the correct side. **Here it is not.** CAL-P126 measured this
exact cell at **43.44% phantom**: 13,116 published rows carrying only **7,419
distinct outcomes**, 11,394 rows duplicated. The rail's 8,426 is far nearer 7,419
than the payload's 13,135 is.

So on basketball the rail is closer to the truth, and it is the *board's*
`50/sqrt(13,135)` that is computed over a population which does not exist.

Either way the σ cannot decide: the SE and the excess are measured on different
row sets, and their ratio is not a σ of either one. The ledger flags this as
`POPULATION_DIVERGENCE` — deliberately not `LOW_COVERAGE`, which was the first
draft's name and which smuggles in the assumption that the payload is right.

`polymarket/hockey` (0.780) is the same flag with **no** explanation: it is one of
CAL-P126's 21 unmeasured cells, so there is no phantom figure to attribute the gap
to and no warrant for assuming basketball's cause.

**Consequence for the conveyor:** CAL-P125-2 is blocked on the phantom, not on a
holdout. Do not spend another session designing a rule for `polymarket/basketball`
until its population is settled — the ECE, the σ and any rule's margin are all
computed over rows that are 43% duplicates.

---

## 4. What this discharges

**The banked five now have measured σs, and every one measured is ESTABLISHED.**
The handoff flagged this as a live question ("⚠️ AND NONE OF THE FIVE HAS A
MEASURED σ. Golf's verdict makes that a live question about all of them"):

| rank | cell | banked rule | σ measured | verdict |
|--:|---|---|--:|---|
| 1 | `polymarket/baseball` | K′ → 2.71 | **5.26** | ESTABLISHED |
| 2 | `kalshi/economics` | E+E2+E3 → 2.61 | **5.82** | ESTABLISHED |
| 3 | `polymarket/esports` | E → 3.29 | *running* | — |
| 6 | `kalshi/crypto` | RULE C | **6.82** | ESTABLISHED |
| 17 | `kalshi/tech` | T → 3.80 | **4.13** | ESTABLISHED |

Four of five confirmed. None of the banked designs is chasing noise.

**Criteria 3 and 6 are discharged as a by-product.** Alex's answer was to report
`effective_n` and a design effect as a pair. Both are now computed per cell in the
ledger, from the same run, and rendered on the board — no separate measurement was
needed. Golf: 20,500 rows, 7,054 effective. `kalshi/tech`: 1,203 rows, **665
effective** — the smallest information content on the queue.

---

## 5. What was built

The measurements are not the deliverable on their own; seven cells' worth of this
has already been re-derived by hand and carried forward as handoff prose.

- **`backend/scripts/calibration_sigma_ledger.py`** — the committed ledger. Stores
  the **SE**, not the σ, so a re-ratified bar (Alex moved them on 2026-08-28)
  cannot silently invalidate an entry; the consumer recomputes σ against the
  current excess. Carries `population_version`, `exact_coverage`,
  `variance_ratio_vs_board` and `effective_n`. `validate()` refuses a ledger whose
  stored σ does not reproduce from its own stored SE — **that check caught a real
  defect on its first run**, the exact-rail-vs-payload ECE basis (golf 3.84 vs
  3.88), which the first draft had silently conflated.
- **`artifacts/calibration-scorecard/measured-sigma.json`** — 12 cells, committed,
  4 KB. Rebuilt with `--build`.
- **`calibration_scorecard.py`** — reports the measured column, `var ratio`,
  `eff n` and the divergence flag. **The verdict, `cells_at_bar` and `done` are
  untouched.** The projection is rendered as a projection: *"the needle would read
  30/49 if the gate were applied to the measured SE. It is NOT applied."*
- **39 guards** in `backend/tests/test_calibration_sigma_ledger_p128.py`.

### Why the overlay reports rather than decides

Making `verdict` key off the measured σ is one line, and on the evidence it is the
correct end state: `SIGMA_GATE` is a ratified rule about *standard errors*, the
row-grain figure is a documented estimate of that quantity, and a measurement
beats an estimate. Substituting one for the other honours the ratified rule rather
than changing it.

But it moves `cells_at_bar` — the needle, and the number Alex reads. Moving a
lane's headline metric as a side effect of an instrument landing is how a board
starts flattering itself, and this program is already carrying 16-CAL for exactly
that. **A finding that shortens the queue deserves more suspicion than one that
lengthens it.** So the flip is Alex's call, and everything he needs to make it is
now on the board rather than in a handoff paragraph.

---

## 6. Owed to Alex

- 🔴 **19-CAL (NEW): `polymarket/basketball` cannot be scored until its phantom is
  resolved, and the parked CAL-P125-2 rule design is blocked on that, not on a
  holdout.** 43.44% phantom (CAL-P126), rail/payload coverage 0.641. Recommend
  **(a) park CAL-P125-2 behind the phantom repair** rather than spend a session on
  a rule whose margin is computed over 43% duplicate rows. No published row changes.
- **20-CAL (NEW): `polymarket/hockey` has an unexplained 0.780 rail/payload
  divergence.** 9,945 excess-outcomes. It is in CAL-P126's unmeasured 21; a phantom
  measurement would say whether it is basketball's cause or a second one. Routing
  note, no decision.
- **17-CAL: CONFIRMED by an independent path.** `kalshi/golf` measured 1.48 here
  against CAL-P127's 1.42 (the difference is the documented payload-vs-rail excess
  basis, both far under the 2.0 gate). Recommendation unchanged: **(a) take it off.**
- **criteria 3 + 6: DISCHARGED BY BUILD**, not staged as a measurement-lane job.
- **13-CAL / 16-CAL: unchanged and still unanswered.** No freeze exception taken.

## 7. Parked

- **CAL-P128-1** — `polymarket/soccer` σ unmeasured. It is the 4th-largest cell
  (44,857 excess-outcomes) and the only working cell with a row-grain σ (2.75) close
  enough to the gate that a measurement could plausibly flip it either way.
- **CAL-P128-2** — the six `odds_api_bookmaker` cells have no measured σ. They are
  off the board by CAL-P120 §6g, so this is not blocking, but their σ column is the
  same row-grain estimate and `calibration_cluster_sigma`'s docstring notes that a
  bookmaker dedup is *exact* — so they are the one family where the correction has a
  known closed form and was never applied.
