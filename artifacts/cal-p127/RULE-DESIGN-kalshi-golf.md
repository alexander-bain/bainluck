# CAL-P127 — rank 9, `kalshi/golf`: the cell is not established, and the quarter that is broken is a real forecast

**Pillar: TRUTH. Ship: the calibration page stops carrying a golf cell on the finish
line that its own sample cannot distinguish from passing — and names, with a number,
the two round-scoped classes where the product's golf probabilities are actually
wrong.**

Status: **diagnosed on the producer's own chain, holdout-split, exhaustively searched
over eight partitions, NO RULE BANKED, and the cell is recommended OFF the board.**
Nothing in this document changes a published row;
`git diff origin/master...HEAD -- backend/app frontend` is empty on this branch.

| | |
|---|---|
| board rank | 9 of 14 (live scorecard, 2026-08-29) |
| published cell | `kalshi/golf` — ECE **3.88** pp, n **20,500**, gap **+3.72** |
| class / bar | B_exchange_contest / **3.0** pp |
| excess | **+0.88** pp = **18,040** excess-outcomes |
| board σ | 2.5 (row grain) |
| **measured σ** | **1.42 (cluster bootstrap) — NOT ESTABLISHED** |
| curve | `2026-08-29T00:36:47Z`, population `q268` |

> Rank moved 8 → 9 between the hand-off and this session: `kalshi/entertainment`
> (18,465) now outranks it. Entertainment is already diagnosed (CAL-P122) and blocked
> on 12-CAL, so golf remained the highest-excess cell with no design **and** no
> recorded reason to skip. It has now been deferred by three consecutive handoffs;
> this document is why it should have been picked up sooner and why it is now closed.

---

## 0. The three cheap checks first

**Can the rail reach the cell?** Yes, and this is the tightest reproduction the
futures-rooted rail has achieved on a non-crypto cell.

| cell | exact rail | payload | Δn |
|---|---|---|--:|
| `kalshi/crypto` (CAL-P121) | 4,566 / 7.61 / +1.83 | 4,565 / 7.60 / +1.84 | +0.02% |
| **`kalshi/golf`** | **20,666 / 3.84 / +3.68** | 20,500 / 3.88 / +3.72 | **+0.81%** |
| `kalshi/economics` (CAL-P114) | 28,738 / 5.29 / −0.47 | 28,613 / 5.29 / −0.47 | +0.55% |

ECE reproduces to −0.04 and the gap to −0.04. `--edge-check` at half the chunk width
returns `n=20666 ECE=3.84 gap=+3.68` — **IDENTICAL**, so chunk boundaries move nothing
here. `calibration_cluster_spread` reads **NO_CLUSTERS** (zero `group_id`/`event_id`
clusters of ≥3), so the id-range rail is in its own domain. Every number below is on
that rail.

**Is the population the published one?** Yes, provably. `calibration_phantom_curve
--scan` (CAL-P126) reports `combos == 1` for this cell — `multi_vms = 0`, `cat_vms = 0`,
`grp_vms = 0` over all 3,279 resolved markets — which is the scan's one EXACT claim, not
its estimate column (lesson 10). **Zero phantom, proved.** The 18,040 excess figure means
what it says and needs no re-bench.

**Is the cell's name evidence of what is in it?** Mostly, and the exception matters.
63 series, and the mass is real golf: `KXPGATOP20` 11.7%, `KXPGATOP10` 11.1%,
`KXPGATOP5` 10.6%, `KXPGAMAKECUT` 8.0%. But the cell also carries `KXCHESSTOURNAMENT`
(8 rows), `KXPBAGAME` (bowling, 1), `KXITFWMATCH` (tennis, 2) and `KXRT` (Rotten
Tomatoes, 18) — 29 rows, 0.14%, too small to matter to this verdict and logged here so
the next reader does not re-discover it.

---

## 1. 🔴 THE σ CORRECTION, MEASURED — AND IT TAKES THE CELL OFF THE BOARD

This is CAL-P120's lesson 4, the check that removed six cells from this board, firing on
a seventh. `calibration_cluster_sigma`, 2,000 resamples, seeded:

```
kalshi/golf — 20,666 published rows / 1,045 distinct markets / 19.78 rows per market

  basis                                 SE pp    sigma
  row grain (the board today)           0.348     2.42
  market grain (perfect-corr bound)     1.547     0.54
  cluster bootstrap (MEASURED)          0.593     1.42

  bootstrap ECE 95% interval  [2.86, 5.17] pp      design effect  2.91

  VERDICT  NOT ESTABLISHED — measured sigma 1.42 against SIGMA_GATE 2.0
```

**The bootstrap's own 95% interval contains the 3.0 bar.** On its own sample, this cell
cannot be distinguished from a cell that passes.

The board disagrees because it computes σ from a binomial standard error on the ROW
count, and this cell averages **19.78 published rows per market** — a golf field market
lists eighty players against one tournament, and those eighty rows are one observation of
one weekend, not eighty. The design effect is **2.91**: the row-grain SE understates the
true one by a factor of 1.7.

`calibration_scorecard` classifies a cell with σ below `SIGMA_GATE = 2.0` as
`OVER_BAR_UNESTABLISHED` rather than queued. Golf is currently in the queued 20 only
because the scorecard's σ is row-grain. **On the measured σ it belongs in the
unestablished bucket, and the board should read 19 queued cells, not 20.**

⚠️ **This is a claim about the SAMPLE, not an all-clear about the cell.** The point
estimate is over the bar and §3 finds a real defect inside it. "We cannot yet prove this
cell misses" and "this cell is fine" are different sentences, and only the first one is
supported.

---

## 2. Seven partitions, and five of them refuse at ANY retention

Lesson 7: *"no rule found" and "no rule exists" are different claims, and the second is
cheap.* `calibration_rule_search` was run over every partition this rail carries, with
**no retention floor at all** — so these are exhaustive statements about the whole 2^k
lattice, not about the subsets a human would have tried.

| partition | arms | subsets | under the 3.0 bar | best, and what it costs |
|---|--:|--:|--:|---|
| `shape` | 4 | 15 | **0** | 3.47 deleting 67.4% |
| `cpdrift` | 5 | 31 | **0** | 3.15 deleting 31.4% |
| `price_moved` | 2 | 3 | **0** | — both arms over the bar |
| `market_type` | 5 | 31 | **0** | 97.6% of the cell is one arm (`field`) |
| `age` | 7 | 127 | **0** | every arm 3.29–7.51, every gap positive |
| `sumband` | 12 | 4,095 | 582 | 2.43 deleting **40.0%** |
| `pairsum` | 5 | 31 | 8 | 1.25 deleting **75.2%** |
| **`golfround`** (new, §3) | 4 | 15 | 2 | **2.12 deleting 23.8%** |

Five partitions cannot reach the bar by deleting anything at all. The two that can —
`sumband` and `pairsum` — reach it the same way, and it is the wrong way:

```
sumband            n    share    ECE     gap
bundle|e_sum_gt_15   7262   35.1%   4.91   +3.98
bundle|d_sum_5_15    6009   29.1%   3.85   +3.85
field1|a_sum_le_1.15 4617   22.3%   1.50   +0.44   <- the clean control
field1|d_sum_5_15     581    2.8%  13.17  +13.17
field1|e_sum_gt_15    207    1.0%  43.59  +43.59
```

Both searches clear the bar by deleting `bundle|*sum>5` — 64% of the cell. **RULE E's
premise does not hold in golf.** RULE E treats a market whose published prices sum past
1.15 as "not a partition, whatever it happened to realize", and in golf that is exactly
backwards: "will player X finish top 10" is an **independent binary**, eighty of them
priced against ten slots legitimately sum to fifteen (gotcha #23). Deleting them deletes
the category.

The one structurally sound arm in that table is small: a market that realized **exactly
one** winner but whose prices sum past 1.15 is genuinely incoherent — a field is a
partition or it is nothing. Dropping all four such arms (1,747 rows, 8.5%) moves the cell
**3.84 → 3.31**. Real, one-directional, and still over the bar. Recorded, not banked.

### The three refutations these seven partitions bought

Three mechanisms have been attached to golf calibration in this repo for over a year.
All three are refuted **as this cell's mechanism**, on the producer's own chain:

1. **Illiquid one-sided-ask placeholders (#938a/#940).** Already shipped — the Kalshi
   liquidity filter (`KALSHI_LIQUIDITY_EXISTS`) and the `did_not_play`/`withdrew` void
   filter both run in the authoritative precompute path. The 3.88 pp is what survives
   them.
2. **Wrong capture date (gotcha #67, the gated `_fix_golf_commence_times`).** `--by age`
   folds the cell on `commence_time − last_snapshot` and **every one of seven arms is
   over the bar with a positive gap** (3.29 to 7.51). There is no cohort captured close
   to commence that is clean, so capture timing is not the discriminator. Separately,
   `_fix_golf_round_leader_dates` is scoped to **OPEN markets only** and therefore never
   touches the resolved calibration population at all — a discriminator this session
   proposed and refuted in ten minutes of reading.
3. **Missing winners (CAL-P122's class, mirrored).** Round-scoped top-N markets grade
   5–8 winners per market, the same distribution as their tournament-scoped
   counterparts. The grading is not collapsed. **This is a pricing defect, not a
   resolution one** — which also means `--by shape` finds no `void_0win` arm at all.

---

## 3. The partition that does name something — and 76% of the cell is already fine

`series` folds this cell into 63 arms. `rule_search` refuses anything past
`MAX_CLASSES` rather than sampling, so the only move left would be to read the table and
pick the bad-looking rows by hand — an exhaustive search for an overfit performed by a
human instead of a loop. **`golfround`** (new dimension, 19 guards) collapses those 63
arms onto the two properties the Kalshi ticker genuinely encodes and nothing else:
does the ticker name a **round** (`R[0-9]`), and does it ask for a **top-N cut**, the
**lead**, or something else.

```
class                    n   share     ECE      gap
tourney|other         8296   40.1%    2.13    +0.36     PASS
tourney|topn          7460   36.1%    2.49    +2.46     PASS
round|topn            2488   12.0%   14.99   +14.99     <-
round|lead            2422   11.7%    7.24    +7.18     <-
```

**76.2% of `kalshi/golf` is already under its bar.** The published 3.88 is not a golf
problem; it is a *round-scoped derivative* problem wearing golf's name. Tournament-level
questions — who wins, who makes the cut, who finishes top 5/10/20 — are calibrated.

The digit in `R[0-9]` is load-bearing and the guard suite pins the counterexamples by
name: `KXPGAROUNDSCORE` (679 rows), `KXPGAROUNDLOW` and `KXOWGRRANK` all carry an R that
is not a round, and a bare-`R` predicate would pull all three into the round arm and
flatter it.

---

## 4. The holdout — and it kills the small rule

Split on `market_id 26,515,295`, the point that halves the cell **by published rows**
(10,399 OLD / 10,267 NEW) rather than by markets, read off `cluster_rows` in
`sigma-kalshi-golf.json`. The id is a chunk edge, so neither half is contaminated. The
partition was never re-fitted on either half — it is structural.

Ranked on the **worse** half, over all 15 subsets:

| keep | pooled ECE | worst half | dropped |
|---|--:|--:|--:|
| `tourney|other`, `tourney|topn` | **2.12** | **2.60** | 23.8% |
| `tourney|other` | 2.13 | 2.69 | 59.9% |
| `tourney|other`, `tourney|topn`, `round|lead` | 2.62 | **3.01** | 12.0% |
| as published | 3.84 | 4.63 | 0% |

**The small rule fails.** Dropping `round|topn` alone reads 2.62 pooled — comfortably
under the bar, and exactly the number a pooled-only analysis would have banked — and
**3.01 on the worse half**, over the bar by 0.01. Lesson 2 says believe the holdout over
the pooled number, and here the two disagree at the third significant figure in the one
direction that matters. Only the 23.8% rule survives both halves.

### Why the two round arms are not one mechanism

| arm | OLD | NEW |
|---|--:|--:|
| `round|topn` | 1,422 @ **11.23** | 1,066 @ **20.24** |
| `round|lead` | 1,145 @ **0.98** | 1,277 @ **12.85** |

`round|lead` reverses by a factor of thirteen. That looked like a regression, and the
first draft of this document said so. It is not — or not only — and the check that caught
it is the composition split:

| `round|lead` series | OLD n | OLD ECE | NEW n | NEW ECE |
|---|--:|--:|--:|--:|
| `KXPGAR1LEAD` | 545 | 1.26 | 308 | **0.64** |
| `KXPGAR2LEAD` | 274 | 0.61 | 313 | **3.87** |
| `KXPGAR3LEAD` | 170 | 0.84 | 373 | **7.73** |
| `KXLPGAR1LEAD` | 0 | — | 97 | 39.39 |
| `KXLPGAR2LEAD` | 0 | — | 28 | 45.50 |
| `KXLPGAR3LEAD` | 0 | — | 24 | 48.56 |
| `KXDPWORLDTOURR2LEAD` | 0 | — | 70 | 46.10 |
| `KXDPWORLDTOURR3LEAD` | 0 | — | 50 | 44.72 |
| `KXLIVR2LEAD` | 0 | — | 1 | 48.00 |

Two things happened at once and they compound:

* **A composition shift.** Non-PGA rows go 13.6% → 22.2% of the arm, and **six non-PGA
  round-lead series exist only in NEW**, every one of them at 39–49 pp with ECE equal to
  gap — uniform over-prediction of about 0.4 on every row. Kalshi opened LPGA, DP World
  and LIV round-leader books, and they are priced like placeholders.
* **A real within-series degradation.** On comparable n and the same ticker,
  `KXPGAR2LEAD` runs 0.61 → 3.87 and `KXPGAR3LEAD` runs 0.84 → 7.73. `KXPGAR1LEAD`
  *improved*. That is not composition; something got worse in later rounds specifically.

`round|topn` is the opposite and cleaner: **all seven series are PGA on both halves, so
there is no composition shift at all**, and every series is over the bar on both halves
(OLD 5.72–16.54, NEW 10.81–29.17). It is durable, stable in membership, and getting
worse.

| `round|topn` series | OLD n | OLD ECE | NEW n | NEW ECE |
|---|--:|--:|--:|--:|
| `KXPGAR1TOP10` | 536 | 13.98 | 354 | 23.36 |
| `KXPGAR1TOP5` | 480 | 14.11 | 302 | 12.59 |
| `KXPGAR2TOP10` | 87 | 6.42 | 208 | 29.02 |
| `KXPGAR3TOP10` | 75 | 16.54 | 84 | 24.36 |
| `KXPGAR2TOP5` | 83 | 11.08 | 59 | 10.81 |
| `KXPGAR3TOP5` | 76 | 14.70 | 53 | 11.56 |
| `KXPGAR1TOP20` | 85 | 5.72 | 6 | 29.17 |

---

## 5. Verdict — NO RULE BANKED, and two reasons either of which is sufficient

**1. The cell is not established.** Measured σ 1.42 against a 2.0 gate, bootstrap CI
[2.86, 5.17] containing the bar. Banking an exclusion for a cell whose sample cannot
distinguish it from passing is spending a disclosed exclusion to buy a number that was
never measured. CAL-P120 set this precedent on six cells; this is the seventh.

**2. The only rule that survives the holdout deletes 23.8% of the cell, and what it
deletes is real.** "Who leads after round two" and "will X be top 10 after round one"
are complete, scoreable forecasts that this product publishes. They are not a population
defect, not a placeholder class the liquidity filter should have caught, and not a
grading failure — §2 refutes all three. They are **forecasts we are bad at**, by 15 and
7 pp respectively.

Excluding them would move the published golf cell from 3.88 to 2.12 and delete, in the
same motion, the only quantified evidence that the product's round-scoped golf
probabilities are wrong — including the six brand-new LPGA / DP World / LIV round-leader
books that are being published at 39–49 pp error **right now**. That is CAL-P122's
argument arriving on a second cell, and CAL-P120's standing rule binds: *a lane must not
quietly change a headline in either direction, least of all the one that flatters it.*

**Recommended: take `kalshi/golf` off the queued board as UNESTABLISHED, and file the
round-scoped classes as a writer-side defect for the lane that owns Kalshi golf
pricing.** The board goes 14 → 13 cells and the finish line goes 29/49 → 29/48 with no
row changed and no exclusion disclosed.

---

## 6. What is owed to Alex

**17-CAL — `kalshi/golf` is not established; take it off the board.** Measured σ 1.42 vs
gate 2.0, design effect 2.91, bootstrap CI [2.86, 5.17] straddling the 3.0 bar. The
board's 2.5 is row-grain over a cell averaging 19.78 rows per market. This is mechanical
under CAL-P120's precedent and is recommended as **(a) take it off**, with (b) leave it
on and accept that the cell may already pass, as the only alternative. **No published row
changes either way.**

**18-CAL — the round-scoped golf classes are a REAL defect and belong to a writer lane,
not to this one.** 4,910 published outcomes, 23.7% of the cell:

* `round|topn` — 2,488 rows, ECE **14.99**, gap **+14.99** (pure one-directional
  over-prediction), durable across the holdout, all-PGA, **worsening** 11.23 → 20.24.
* `round|lead` — 2,422 rows, ECE **7.24**, two compounding causes: six new non-PGA
  round-leader series at 39–49 pp, and PGA R2/R3 degrading on comparable n
  (0.61 → 3.87, 0.84 → 7.73) while R1 improved.

⚠️ **These are not an exclusion candidate and this queue is not asking to exclude them.**
The ask is that they be routed to whoever owns Kalshi golf price capture. The six
all-NEW non-PGA round-leader series at a uniform ~0.4 over-prediction are the sharpest
lead: they pass the #940 liquidity filter (some bid exists) yet price like placeholders,
which is a class that filter was not built to catch.

**Re-check on 14-CAL, cheap and adjacent.** `polymarket/cricket` was ruled unrepairable
on 1,971 candidate rules. This session's `golfround` result shows a cell can be
unrepairable on every partition a rail carries and still have a clean rule one dimension
away. That is not a claim cricket has one — it is a reason its refusal should name the
dimensions it searched, as this one does.

---

## 7. Parked, not dropped

* **CAL-P127-1 — measure σ for `round|topn` on its own.** `calibration_cluster_sigma`
  takes only `--source`/`--category`, so the subclass has no measured σ. Applying this
  cell's design effect of 2.91 to a 2,488-row class at +11.99 excess *estimates*
  comfortably established, but that is an estimate sitting in the same column as a
  measurement, which is exactly lesson 10. **The instrument needs a `--where` on a
  dimension arm.** Until it has one, 18-CAL's two classes are reported with their ECEs
  and without a σ.
* **CAL-P127-2 — the incoherent one-winner fields, 1,747 rows.**
  `field1` markets whose published prices sum past 1.15 run 3.43–43.59 pp, rising
  monotonically with the sum (b 3.43 → c 5.19 → d 13.17 → e 43.59).
  A field that realized exactly one winner and priced past a partition is incoherent by
  construction, and unlike the `bundle` mass this cannot be defended as an independent
  binary. It moves this cell 3.84 → 3.31 and it is **not golf-specific** — the same
  arm exists on every cell `sumband` reaches. Worth one sweep across the board before
  anyone designs a per-cell rule for it.
* **CAL-P127-3 — 29 non-golf rows in `kalshi/golf`.** `KXCHESSTOURNAMENT` (8),
  `KXRT` (18), `KXITFWMATCH` (2), `KXPBAGAME` (1). 0.14% of the cell, changes nothing,
  but it is a live `llm_sport_category` mis-shelving and the next reader should not have
  to re-find it.

---

## 8. Files

| file | what it is |
|---|---|
| `backend/scripts/calibration_cell_exact.py` | +`golfround` dimension; +bounded 429 retry on the payload fetch |
| `backend/tests/test_calibration_cell_exact_p127.py` | 13 guards — the retry stays bounded, loud, uncached |
| `backend/tests/test_calibration_cell_exact_p127_golfround.py` | 19 guards — the partition, pinned to the real 63-series corpus |
| `artifacts/cal-p127/exact-kalshi-golf-*.json` | eight folds, the rail's own output |
| `artifacts/cal-p127/sigma-kalshi-golf.json` | the σ measurement — the finding |
| `artifacts/cal-p127/rulesearch-*.json` | the exhaustive refusals |
| `artifacts/cal-p127/score_subset.py` | scores one NAMED subset, pooling imported from the searcher |
