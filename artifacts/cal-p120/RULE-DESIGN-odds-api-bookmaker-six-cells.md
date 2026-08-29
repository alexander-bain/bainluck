# CAL-P120 — `odds_api_bookmaker`: no rule is owed, and five cells behind rank 5 go with it

**Queue:** calibration 019 (prebuild conveyor) · **Branch:** `program/calibration-115` ·
**Date:** 2026-08-29 · **Issue:** #1978

**Verdict: REFUSED — and the refusal is a board correction, not a shrug.** Rank 5
(`odds_api_bookmaker/basketball_nba`) has no designable defect, because its excess over the bar is
**not established once the unit of observation is a game rather than a bookmaker-row**. The same
correction applies to **all six** `odds_api_bookmaker` cells on the board — 6 of 20 queued cells,
**82,345 of 478,677 excess-outcomes (17.2%)** — and every one of them falls below the board's own
`SIGMA_GATE = 2.0`.

Nothing here is an exclusion, a filter, or a change to the published curve. The published number is
untouched. What changes is **which cells the board says are worth a cycle.**

---

## 0. The instrument had to exist first, and its absence was not a scoping bug

The conveyor's note predicted this cell would need neither the bundle playbook nor the
Polymarket-writer playbook. It needed something more basic: **a rail.**

`calibration_cell_shape_fold`, `calibration_cell_replica` and `calibration_cell_exact` all fold the
population that `precompute_calibration._calibration_population_ctes()` builds, and that chain is
rooted in `futures_markets`. Pointing the exact rail at this cell does not return a wrong answer; it
crashes in `sweep()` on `MIN(id)`/`MAX(id)` returning `NULL`, because — measured 2026-08-29 — the
whole `source` domain of `futures_markets` is:

| source | rows |
|---|--:|
| `polymarket` | 644,038 |
| `kalshi` | 255,104 |
| `datagolf` | 330 |
| `odds_api` | 12 |

**There are zero `odds_api_bookmaker` rows in `futures_markets`.** This source reaches the payload by
a separate road entirely: `backfill_winners._precompute_bookmaker_calibration()` runs one
self-contained statement over `events` + `odds_snapshots`, aggregates to `(bucket_idx, category)`,
and writes to the Redis key `bainluck:bookmaker_calibration`; the producer reads that key in Phase 3
Query 5 and republishes it. **The rows are aggregated before the producer ever sees them**, so there
is no per-outcome population for the exact rail to fold — and no `--source` string that would fix it.

New instrument: **`backend/scripts/calibration_bookmaker_cell_fold.py`**, 21 guards / 7 mutations /
7 reds (`backend/tests/test_calibration_bookmaker_cell_fold_p120.py`).

### It reproduces the published cell EXACTLY, which no rail on this board has managed before

```
odds_api_bookmaker/basketball_nba  (--grain bucket, --check-payload)
  fold      n=10,186  ECE=5.18 pp  gap=+1.03 pp
  published n=10,186  ECE=5.18 pp  gap=+1.03 pp
  DRIFT     rows +0 (+0.00%)  ECE -0.00 pp
  ✅ every bucket reproduces the published row count exactly
```

Set against what the Polymarket rails manage on their own cells — **−5.7% of rows** on
`polymarket/baseball` (CAL-P117 §6c) and **−5.06% of rows / −0.53 pp of ECE** on `polymarket/soccer`
(CAL-P118 §6e) — this is a different quality of measurement, and the reason is structural rather
than lucky:

* **Chunking here cannot perturb a value.** Every grouping in the statement is per-event
  (`event_bookmakers` groups on `(event_id, bookmaker)`; the closing-line `LATERAL` is scoped to one
  `event_id`), and the chunking is on `commence_time`, which partitions events. Contrast
  `calibration_cell_exact`, which chunks on `fm.id` while `virtual_market`'s "≥3 markets in the same
  source" test groups *across* markets — an approximation it documents and cannot remove.
* **There is no staged mosaic.** CAL-P118 traced Polymarket's disagreement to the producer publishing
  a bank of units staged hours apart (`frozen_over_drift`). This source is one Redis blob recomputed
  wholesale every 6h from a deterministic statement.

**The one place it does not reproduce is itself evidence, not noise.** `basketball_wnba` reads +66
rows (+2.11%) — and every disagreeing bucket is an **addition**, none lost a row:

| bucket | fold | published |
|--:|--:|--:|
| 3 | 305 | 283 |
| 5 | 462 | 451 |
| 8 | 353 | 335 |
| 9 | 30 | 15 |

The WNBA season is live — the fold's span runs to today. The NBA season ended 2026-06-14 and
reproduces to the row. **Dead seasons reproduce exactly; live seasons only grow.** That is the
signature of games finishing between the staged population and the live read, and it is the opposite
of the Polymarket case, where rows went *missing* in both directions.

---

## 1. What is actually wrong with rank 5: the outcome is counted 17.78 times

The cell publishes **10,186 outcomes**. They come from **573 games**.

```
games=573  book-rows=10,186  replication=17.78x
books/game: median 18 (min 2, max 21)
```

Each of a game's ~18 rows is one bookmaker's devigged closing home-price paired with **the same
game's result**. So within a game:

* **`won` is byte-identical across all 18 rows.** It is a function of `event_id` alone — see the
  statement: `(eb.home_score > eb.away_score)`. The intra-cluster correlation on the *response
  variable* is therefore **exactly 1, by construction**, not by estimate.
* **`prob` is very nearly identical too.** Measured across the 573 games: median inter-book SD
  **0.0068** (0.68 pp), p90 0.0111, median range 0.0258. **403 of 573 games (70.3%) have all ~18
  books inside a single decile bucket.**

Eighteen near-copies of one number, attached to one identical outcome, are not eighteen
observations. The design effect for a clustered mean is `1 + (m−1)·ρ`; with `ρ = 1` it collapses to
`m`, the cluster size. **Effective n = 10,186 / 17.78 = 573 — the game count, exactly.**

### The board's σ column is computed on the wrong n

`calibration_scorecard.cell_se_pp(n) = 50/sqrt(n)`, `sigma = excess / se`, `SIGMA_GATE = 2.0`.

| | n used | se | excess | σ |
|---|--:|--:|--:|--:|
| board today | 10,186 book-rows | 0.495 pp | +2.68 | **5.4 — QUEUED** |
| per game | 573 games | 2.089 pp | +2.68 | **1.28 — not established** |

### The point estimate is NOT what moves, and that matters

Re-folded at game grain, one row per game at the consensus price:

```
GAME GRAIN  n=573   ECE=5.32 pp  gap=+1.01 pp   σ over bar = 1.35
BOOK GRAIN  n=10,186 ECE=5.18 pp  gap=+1.03 pp   σ over bar = 5.41
```

**The ECE is essentially unchanged (5.18 → 5.32).** Replication does not create the error; it creates
the *confidence*. This is not "the cell is fine" — it is "the sample cannot tell this cell from its
bar", which is the precise condition `SIGMA_GATE` was added to catch. The gate's own docstring says
so: chasing a point estimate the sample cannot distinguish from the bar *"burns a cycle per cell and
moves nothing."*

### The holdout split says the same thing without any variance theory at all

Split on `commence_time` (CAL-P117 lesson 2 — always split, and believe the halves):

| half | n | ECE | gap |
|---|--:|--:|--:|
| OLD (01-29 … 03-14) | 286 | 6.24 | **+3.32** |
| NEW (03-14 … 06-14) | 287 | 4.86 | **−1.28** |

**The gap reverses sign between the halves.** A mechanism does not change direction halfway through a
season; a small sample does. Neither half is established (1.26σ, 0.80σ).

And the two buckets that look most alarming on the board dissolve completely once counted as games:

* **b0**: 170 rows, 0 winners, predicted 8.24% — reads as a 4.5e-7 impossibility. It is **10 games**.
  P(0 of 10) = **0.42**.
* **b9**: 376 rows, 375 winners, predicted 92.1%. It is **22 games**, all won. P = **0.16**.

---

## 2. The same correction takes the other five, and none survives

| cell | pub n | games | repl | ECE | excess | σ board | **σ per game** | verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| `basketball_nba` | 10,186 | 573 | 17.8x | 5.18 | +2.68 | 5.42 | **1.28** | not established |
| `baseball_mlb_preseason` | 3,253 | 217 | 15.0x | 8.24 | +5.74 | 6.55 | **1.69** | not established |
| `icehockey_nhl` | 8,658 | 495 | 17.5x | 3.89 | +1.39 | 2.58 | **0.62** | not established |
| `basketball_wncaab` | 3,382 | 583 | 5.8x | 6.05 | +3.55 | 4.13 | **1.72** | not established |
| `basketball_wnba` | 3,135 | 300 | 10.4x | 4.81 | +2.31 | 2.58 | **0.80** | not established |
| `basketball_euroleague` | 1,762 | 162 | 10.9x | 5.39 | +2.89 | 2.43 | **0.74** | not established |

**6 of 6.** Not one clears 2.0σ, and four are under 1.3σ.

Their holdout halves are correspondingly unstable — `icehockey_nhl` reads **1.31 then 7.34**
(its OLD half is *below the 2.5 bar*), `baseball_mlb_preseason` reads **3.91 then 14.09**. Two of the
six also reverse the sign of their gap. A cell whose two halves read 1.31 and 7.34 has no stable ECE
for a rule to be designed against.

---

## 3. The two counter-arguments, answered with numbers rather than confidence

**"Maybe the books carry independent information."** They cannot, on the axis that matters. `won` is
a deterministic function of `event_id`, so ρ on the response is 1 exactly — this is an algebraic
property of the statement, not a measurement that could come out otherwise. The measured price
agreement (median SD 0.68 pp; 70.3% of games entirely within one bucket) says the *predictor* is
nearly duplicated too, so even the tiny cross-bucket spread buys almost nothing.

**"`50/sqrt(n)` is already conservative — it assumes p=0.5 — so maybe it absorbs this."** It does not,
and it is off by a factor of three or more. Measured per cell, convention SE vs the true
`p̂`-based SE:

| cell | conservatism bought | deflation needed |
|---|--:|--:|
| `basketball_nba` | 1.18x | **4.22x** |
| `baseball_mlb_preseason` | 1.04x | **3.87x** |
| `icehockey_nhl` | 1.02x | **4.18x** |
| `basketball_wncaab` | 1.19x | **2.41x** |
| `basketball_wnba` | 1.13x | **3.23x** |
| `basketball_euroleague` | 1.09x | **3.30x** |

The p=0.5 conservatism is a *within-row* effect worth 1.02–1.19x. The clustering is a *between-row*
effect needing 2.41–4.22x, and it points the other way. So the docstring's promise — *"a cell this
gate clears is clear by at least the margin shown"* — **is false on this source**, and this is by how
much. That sentence is true for `futures_markets` sources, where one row is one market; it was never
checked against a source that publishes one game eighteen times.

---

## 4. What is owed, and what is explicitly NOT proposed

**Proposed (board only, no published row changes):** move all six `odds_api_bookmaker` cells from the
queue to §6's *"material cells over bar but NOT established — do not work these"* list, and give
`calibration_scorecard.py` a per-source **effective-n** so the σ column stops counting a game
eighteen times. Queue 20 → 14 cells; excess-outcomes 478,677 → 396,332.

**NOT proposed, and deliberately so:** nothing about the published curve. In particular this queue
does **not** propose excluding these rows, and does not touch `precompute_calibration.py` (ruling 009)
or `backfill_winners.py`.

### 🔴 The larger thing this uncovers is Alex's call, and this lane must not act on it

The same 17.78x replication that inflates the σ column also **weights the published headline**.
`odds_api_bookmaker` contributes **96,026 of 913,851 published outcomes (10.5%)** — which, at these
replication factors, is on the order of **~5–6 thousand real games counted ten to eighteen times
each**. Every other source on the curve publishes roughly one row per question.

Two reasons this lane stops at naming it:

1. **It cuts against us.** `odds_api_bookmaker`'s own MCE is **1.43**, well below the published
   headline of **1.89** — so this source is currently pulling the headline *down*. De-weighting it
   would very likely make the published number **worse**. That is exactly the kind of change a lane
   must never make quietly on its own initiative, in either direction.
2. **It is a producer-weighting question**, and the producer is frozen (ruling 009).

Filed as **YOUR-TURN item 10** and parked in `PARKED-MEASUREMENTS.md` as **CAL-P120-1**. The
measurement that would settle it — recomputing `mce_closing_line` with `odds_api_bookmaker`
de-replicated to game grain — is a measurement-lane job under ruling 134, and it should be run
*before* anyone rules, not after.

---

## 5. Reproduce

```bash
source ~/.claude/.env

# the self-check: does the fold land on the published cell?
python3 backend/scripts/calibration_bookmaker_cell_fold.py \
    --sport-key basketball_nba --grain bucket --check-payload \
    --out artifacts/cal-p120/fold-nba-bucket.json

# the finding: how many independent games is the cell made of?
python3 backend/scripts/calibration_bookmaker_cell_fold.py \
    --sport-key basketball_nba --grain game \
    --out artifacts/cal-p120/fold-basketball_nba-game.json

cd backend && python3 -m pytest tests/test_calibration_bookmaker_cell_fold_p120.py -q
```

Artifacts: `fold-nba-bucket.json`, `fold-{basketball_nba,baseball_mlb_preseason,icehockey_nhl,
basketball_wncaab,basketball_wnba,basketball_euroleague}-game.json`, `fold-wnba-bucket.json`.
