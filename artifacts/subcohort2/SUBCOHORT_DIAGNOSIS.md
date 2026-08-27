# SUBCOHORT DIAGNOSIS — ranked on `ece_eligible`, re-ranked 2026-08-24 (CAL-P094)

**Ranking metric (authoritative since 2026-08-24):** `n_eligible × (ece_eligible − 3)`. Truth-eligible
rows only — the legs whose winner was established INDEPENDENTLY of the market's own price
(`CALIBRATION_TRUTH_ELIGIBLE_SOURCES`), which is what the published curve actually grades.  
**Ranking source (authoritative since 2026-08-26, CAL-P103):** the durable checkpoint
`durable_state_snapshots identity='calibration:cohort_cell_census' schema_version='cohort-cell-census/v2'`,
`complete=true`, **49 cells**, written `2026-08-26 22:01:31Z`, `len 160371`.
`artifacts/cal-p094/eligible_fold_all_cells.json` (22 cells) is **superseded and must not be
re-quoted as the board** — its own `league_scope_note` restricts it to 11 leagues, so it could not
rank the other 27 cells at all. The historical input
`ARTIFACT-CAL-P076-1978-ALL-CELLS-CENSUS.json` at `4eb2a725` v3859 is retained below as evidence,
not as ordering.  
**Bar:** Alex verbatim "anything with a reasonable sample size that has ECE over 3 is miscalculated,
unless you convince me otherwise."  
**Method per cell — mechanism-ranked, each number EXECUTED with stored output:** `price-source
fallback share` (#1978 class) → `de-vig vs venue` → `shape semantics (sum-to-1)` →
`capture-age/hindsight` → `grading truth` → `binning noise floor` (calculation, not shrug).

---

## STATUS 2026-08-26 (CAL-P103) — THE BOARD IS COMPLETE FOR THE FIRST TIME. 49 CELLS, NO `NEEDS RE-CUT` CLASS LEFT, AND 21 ARE OVER BAR

`handoff: SUBCOHORT-TRUTH-3 → SUBCOHORT_DIAGNOSIS.md STATUS (run.2628 v2)`

*Folded per the declared handoff (`.claude/handoff/SUBCOHORT-TRUTH-1-HANDOFF.md` §
C-SUBCOHORT-TRUTH-3 22:03Z and § C-SUBCOHORT-TRUTH-4 23:31Z). The worker fold `run.2628`
(`backend/scripts/fold_cohort_cell_eligible.py`, sargable `id` rail) landed its checkpoint at
22:01:31Z; Alex independently verified `complete=true` at 22:24Z.*

**This lane did not take the handoff's table on trust.** Every number below was re-read from the
durable payload in production this session, read-only, via `POST /api/admin/db-query`:

| what | reading | fingerprint |
|---|---|---|
| checkpoint identity | `cohort-cell-census/v2`, `complete=true`, `updated_at 2026-08-26 22:01:31.042923+00`, `len 160371`, `jsonb_array_length(payload->'cells') = 49` | `2406f40223c4fa1f`, 132.7 ms |
| the 26 measured cells, ranked by `n_eligible × (ece_eligible − 3)` | 26 rows, `truncated: false` | `d7235b92a54a1de6`, 100.6 ms |
| the 23 cells with `ece_eligible IS NULL` | 23 rows | `bab8fa5b3c895473` |

26 + 23 = **49**, and no cell appears in two classes. `measured: true` on all 49; `measured_reason`
is `NULL` on all 49 — there is no partial and no irreducible remainder to disclose.

### 🟢 WHAT THIS FOLD ACTUALLY CHANGES: CLASS D IS GONE

CAL-P101's board below is a 50-cell board with a 13-cell hole in it — class **D, "NO ELIGIBLE CUT
YET"** — and that section's own closing paragraph named clearing it as owed item #1. `run.2628` cut
all thirteen. They did not land where the refuted "under-bar-by-bound" premise predicted:

| the 13 class-D cells | now | |
|---|---|---|
| **6 came in OVER bar** | `tech/quantity` **11.54**, `football/container_member` **13.28**, `entertainment/container_member` **11.55**, `tech/container_member` **7.44**, `entertainment/quantity` **5.06**, `cricket/container_member` **4.22** | 15 over bar → **21** |
| **3 came in UNDER bar** | `weather/quantity` **1.87** (n_e 27,356), `mma/container_member` **2.82**, `mma/quantity` **2.49** | measured, not bounded |
| **4 fell below `MIN_CELL_N`** | `football/quantity` (n_e 21), `motorsports/container_member` (10), `weather/container_member` (2), `rodeo/container_member` (0) | ECE ABSENT, never 0.0 |

**Owed item #2 is discharged, and the answer is the reassuring one.** `weather/quantity` was the
single largest population resting on the refuted bound — CAL-P101 flagged it as "unmeasured, not
under bar", census n 64,117. Measured: **1.87 pp on 27,356 eligible legs.** It is genuinely under
the bar, it is the second-largest eligible n on the whole board, and it is not a queue item.

**Owed item #1 is discharged in full**, and the honest read is that clearing the hole made the
queue longer, not shorter: the excusing bound was wrong in the direction that costs work.

### THE REPLACEMENT BOARD — 21 / 5 / 23, ranked on `n_eligible × (ece_eligible − 3)`

`σ` uses this file's convention, `SE = 50/√n_e` pp. `ece_all (n_all)` is the same cell on the
*unfiltered* graded population — the number the curve does **not** publish — kept beside each row
so nobody re-reads a phantom figure as a defect.

**A. OVER BAR — 21 cells. This is the queue.**

| # | cell | `ece_e` | `n_e` | excess | σ | impact | `ece_all` (`n_all`) | eligible share |
|---:|---|---:|---:|---:|---:|---:|---|---:|
| 1 | baseball/quantity | 15.86 | 6,778 | 12.86 | **21.2σ** | 87,165 | 21.67 (48,340) | 14.0% |
| 2 | soccer/quantity | 8.51 | 5,749 | 5.51 | **8.4σ** | 31,677 | 44.87 (202,834) | 2.8% |
| 3 | soccer/container_member | 6.27 | 7,682 | 3.27 | **5.7σ** | 25,120 | 27.99 (76,141) | 10.1% |
| 4 | economics/quantity | 5.13 | 4,719 | 2.13 | 2.9σ | 10,051 | 8.03 (10,359) | 45.6% |
| 5 | hockey/quantity | 10.94 | 1,137 | 7.94 | **5.4σ** | 9,028 | 21.71 (2,062) | 55.1% |
| 6 | basketball/quantity | 5.73 | 2,104 | 2.73 | 2.5σ | 5,744 | 24.37 (13,124) | 16.0% |
| 7 | politics/quantity | 6.12 | 1,152 | 3.12 | 2.1σ | 3,594 | 8.64 (3,557) | 32.4% |
| 8 | tennis/quantity | 5.01 | 1,512 | 2.01 | 1.6σ | 3,039 | 24.71 (56,960) | 2.7% |
| 9 | baseball/container_member | 12.44 | 286 | 9.44 | **3.2σ** | 2,700 | 20.29 (18,219) | 1.6% |
| 10 | golf/container_member | 25.11 | 118 | 22.11 | **4.8σ** | 2,609 | 22.48 (5,964) | 2.0% |
| 11 | entertainment/quantity | 5.06 | 820 | 2.06 | 1.2σ | 1,689 | 5.39 (2,790) | 29.4% |
| 12 | tech/quantity | 11.54 | 185 | 8.54 | 2.3σ | 1,580 | 10.69 (566) | 32.7% |
| 13 | esports/container_member | 3.15 | 8,217 | 0.15 | 0.3σ | 1,233 | 20.28 (120,953) | 6.8% |
| 14 | geopolitics/quantity | 19.36 | 60 | 16.36 | 2.5σ | 982 | 14.13 (228) | 26.3% |
| 15 | basketball/container_member | 6.65 | 262 | 3.65 | 1.2σ | 956 | 26.10 (7,167) | 3.7% |
| 16 | esports/quantity | 4.84 | 506 | 1.84 | 0.8σ | 931 | 21.75 (8,786) | 5.8% |
| 17 | entertainment/container_member | 11.55 | 103 | 8.55 | 1.7σ | 881 | 23.34 (3,344) | 3.1% |
| 18 | football/container_member | 13.28 | 73 | 10.28 | 1.8σ | 750 | 19.59 (450) | 16.2% |
| 19 | tech/container_member | 7.44 | 168 | 4.44 | 1.2σ | 746 | 23.74 (2,119) | 7.9% |
| 20 | politics/container_member | 7.90 | 116 | 4.90 | 1.1σ | 568 | 13.84 (4,990) | 2.3% |
| 21 | cricket/container_member | 4.22 | 201 | 1.22 | 0.3σ | 245 | 30.87 (3,424) | 5.9% |

Total board excess: **191,288**. Rank 1 alone is **45.6%** of it. Ranks 1–5 are **85.2%** of it.

**B. UNDER BAR — 5 cells, measured, no query owed.** `weather/quantity` 1.87 (27,356),
`tennis/container_member` 2.07 (2,583), `economics/container_member` 2.87 (513),
`mma/container_member` 2.82 (174), `mma/quantity` 2.49 (70).

**C. NULL — 23 cells, `n_eligible < 30`, `MIN_CELL_N = 30` so ECE is ABSENT and never 0.0** (the
datagolf-card mistake, #2172). The four that carry a large *phantom* `ece_all` and will keep
attracting attention until this row is quoted at them:

| cell | `n_eligible` | `ece_all` | `n_all` |
|---|---:|---:|---:|
| table_tennis/quantity | **0** | 44.72 | 73,809 |
| table_tennis/container_member | **0** | 46.69 | 59,164 |
| hockey/container_member | **0** | 41.07 | 1,528 |
| chess/container_member | **0** | 50.00 | 792 |

The other 19: `geopolitics/cm` (n_e 8), `motorsports/cm` (10), `weather/cm` (2), `rodeo/cm` (0),
`football/quantity` (21), `culture/cm` (0), `olympics/{cm,q}`, `pickleball/cm`, `cricket/quantity`,
`rugby/{cm,q}`, `weightlifting/quantity`, `boxing/cm`, `motorsports/quantity`, `crypto/cm`,
`legal/cm`, `rodeo/quantity`, `cycling/cm`.

**`hockey/container_member` stays answered.** Zero of its 1,528 graded legs carry a truth-eligible
`resolution_source`. Its 41.07 pp was computed entirely over rows the published curve never
contained. This is now the third consecutive document to say so; it is not a bisection candidate.

### 🔶 THREE CORRECTIONS TO THE HANDOFF THIS FOLD CONSUMES

Folded with corrections, on the same principle CAL-P101 folded under — the tracked file must not
inherit a claim the payload it cites does not make.

1. **`weather/quantity` is listed in two different buckets in the same handoff section.**
   C-SUBCOHORT-TRUTH-3 puts `weather/quantity 1.87 (27,356)` in the under-bar five *and* names
   `weather/q etc.` in the 23 null cells. The payload is unambiguous: `measured: true`,
   `n_eligible 27,356`, `ece_eligible 1.87` — **under bar, not null.** C-SUBCOHORT-TRUTH-4's table
   has it right; the earlier prose does not. This board follows the payload.
2. **Two impacts in the handoff are one off the unrounded arithmetic:** `economics/quantity` 10,052
   (this fold: **10,051**) and `esports/container_member` 1,232 (**1,233**). Immaterial to every
   rank; recorded so a future reader does not "reconcile" them into a third number.
3. **`golf/quantity` leaves the board, and the board is 49 not 50.** CAL-P101 carried it as a 50th
   cell on the note that it "appears only in the fold". It is absent from the 49-cell census
   enumeration in both directions — not in the 26 measured, not in the 23 null. It was an artifact
   of the scope-limited file, and it goes with that file.

### 🔴 THE RANK ORDER IS IMPACT, AND IMPACT IS NOT SIGNIFICANCE. ONLY SIX OF THE 21 CLEAR 3σ

Alex's bar is a bar on ECE, and `impact` is what orders the queue — but a queue is a claim that the
cell is real, and on this board **15 of the 21 are under 3σ, and three are under 1σ.**

The six that are both large and significant: **ranks 1, 2, 3, 5, 9, 10** — `baseball/quantity`,
`soccer/quantity`, `soccer/container_member`, `hockey/quantity`, `baseball/container_member`,
`golf/container_member`.

The two that will waste the most time if read off the rank column alone:

* **Rank 13 `esports/container_member` — 3.15, i.e. 0.15 pp over the bar at 0.3σ**, on the largest
  eligible n of any over-bar cell (8,217). It ranks 13th only because n is big. It is
  indistinguishable from the noise floor and should not be worked as a defect.
* **Rank 21 `cricket/container_member` — 1.22 pp over at 0.3σ on n 201.** Same shape, small n.

**All six cells promoted out of class D** (ranks 11, 12, 17, 18, 19, 21) land between 0.3σ and
2.3σ. They are over bar on the point estimate and not one of them is established. **This is the note
the previous two folds did not carry, and it is the difference between a 21-item queue and a
6-item one.**

### What is owed after this fold

1. **Nothing is owed on class D. It no longer exists** — every one of the 49 cells is now either
   measured or explicitly `n_eligible < 30`.
2. **Rank 1 `baseball/quantity` remains the whole queue's headline at 45.6% of total excess**, and
   its two named mechanisms are the ones already in flight (the 0.5000 placeholder pair on
   `program/calibration-96`, and the published-pair incoherence of CAL-P100 below, whose cert
   `C-PUBLISHED-PAIR-1` is re-staged at `program/calibration-99 @ 11294448`). Neither is measured
   against this board yet, and neither should be — ruling 134.
3. **The `15.86` / `16.64` two-rail discrepancy on rank 1 survives this fold unchanged.** The
   durable v2 checkpoint reads **15.86**, the same as the sargable fold; the ANY-paged rail reads
   16.64 on the identical n. Two rails, same population size to the row, 0.78 pp apart. Still not
   averaged, still owed by whoever next touches the binning.
4. **The six sub-2σ promotions want an interval before they want a mechanism.** A ladder run on
   `entertainment/quantity` at 1.2σ is a ladder run on noise.

---

## STATUS 2026-08-26 (CAL-P101) — THE MEASUREMENT LANE'S REPLACEMENT RANK TABLE IS FOLDED IN, AND IT IS BEHIND THIS FILE BY 22 CELLS

`handoff: SUBCOHORT-TRUTH-1 → SUBCOHORT_DIAGNOSIS.md STATUS`

*Folded per the declared handoff (`.claude/handoff/SUBCOHORT-TRUTH-1-HANDOFF.md`, 107 lines,
C-SUBCOHORT-TRUTH-1 + the C-SUBCOHORT-TRUTH-2 complete replacement rank table appended 21:10Z).
**Folded WITH a correction, because the table and this file disagree about 22 cells and the
disagreement is decidable from an artifact already in this repo.** The handoff's own instruction is
to fold it in; folding it in silently would have replaced a measured board with an unmeasured one.*

### 🔴 THE HEADLINE THE HANDOFF ASKS FOR IS "4 PROVEN OVER BAR". THE MEASURED NUMBER IS 15.

The handoff's queue is **4 proven / 19 under-bar-by-bound / 26 NEEDS RE-CUT**, and it says the 26
"cannot be byte-exactly re-cut from the bus without the worker's checkpoint". That checkpoint is not
what those 26 were waiting on. **`artifacts/cal-p094/eligible_fold_all_cells.json` already cut 22 of
them** — `complete: true`, `measured: true`, `irreducible: []`, 26 shards, 215.5 s, banked
2026-08-24 — and this file's header has named it the authoritative ranking source since that day.
The handoff was built from `census.json` plus CAL-P093's four cells and never opened it.

Eleven cells the handoff lists as `NEEDS RE-CUT` are measured in that fold:

| cell | handoff says | fold says | verdict |
|---|---|---|---|
| soccer/quantity | NEEDS RE-CUT | **8.51** (n 5,749) | over bar, rank 2 |
| soccer/container_member | NEEDS RE-CUT | **6.27** (n 7,682) | over bar, rank 3 |
| economics/quantity | NEEDS RE-CUT | **5.13** (n 4,705) | over bar, rank 4 |
| hockey/quantity | NEEDS RE-CUT | **10.94** (n 1,137) | over bar, rank 5 |
| politics/quantity | NEEDS RE-CUT | **6.12** (n 1,152) | over bar |
| tennis/quantity | NEEDS RE-CUT | **5.01** (n 1,512) | over bar |
| golf/container_member | NEEDS RE-CUT | **25.11** (n 118) | over bar |
| esports/container_member | NEEDS RE-CUT | **3.15** (n 8,217) | over bar by 0.15 pp, **0.3σ** |
| tennis/container_member | NEEDS RE-CUT | **2.07** (n 2,583) | **under bar** |
| table_tennis/quantity | NEEDS RE-CUT (`MOD` fold needed) | `n_eligible` **0** | **UNMEASURABLE** |
| hockey/container_member | PENDING #3, "density trap, not data absence", 29σ | `n_eligible` **0** | **UNMEASURABLE** |

The last row is the one that costs real work. The handoff re-queues `hockey/container_member` as
priority #3 with "NO known mechanism — needs bisection to 25 ids". The fold already answered it:
**zero of its 1,528 graded legs carry a truth-eligible `resolution_source`, so the 41.00 pp was
computed entirely over rows the published curve never contained.** There is nothing there to
bisect. This file said so in bold on 2026-08-24 and the handoff reinstates it.

### 🔴 "UNDER-BAR-BY-BOUND" IS NOT A SOUND BOUND — AND ONE OF THE FOUR CELLS IT EXCUSED IS OVER BAR

The handoff spends no query on 19 cells on this premise: *"removing phantom rows can only leave
`ece_eligible ≤ ece_complete` when `ece_complete` is already ≤3 (shape phantom is ≥0)."*

That premise is false, and this file already carried the counterexample: `golf/container_member`
went `ece_all` **22.99 → `ece_eligible` 25.11**. Eligibility selects on *truth provenance*, not on
error, so it can move ECE in either direction. Seven of the seventeen measured cells went UP:

| cell | census `ece_c` | eligible `ece_e` | direction |
|---|---:|---:|---|
| baseball/quantity | 8.42 | 15.86 | ↑ |
| soccer/quantity | 4.67 | 8.51 | ↑ |
| soccer/container_member | 4.82 | 6.27 | ↑ |
| golf/container_member | 10.46 | 25.11 | ↑ |
| geopolitics/quantity | 14.39 | 19.36 | ↑ |
| politics/container_member | 3.08 | 7.90 | ↑ |
| **esports/quantity** | **1.87** | **4.84** | ↑ **across the bar** |

`esports/quantity` is one of the four cells the handoff records as *"≤3 — under-bar-by-bound (no
query spent)"*. It is measured at **4.84 on n_eligible 506**. The bound did not merely fail to be
tight; it returned the wrong side of Alex's bar. Anything still resting on it —
`weather/quantity` (1.59, n 64,117), `economics/container_member` (1.67),
`table_tennis/container_member` (1.92) — is **unmeasured, not under bar**, and
`economics/container_member`'s own eligible cut (2.78) is under by 0.22 pp rather than by 1.33.

### THE HONEST QUEUE — 50 cells, five states, no cell in two

`ece_e` from `eligible_fold_all_cells.json`; census from `census.json` (49 cells; `golf/quantity`
appears only in the fold). `σ` uses `SE = 50/√n_e` pp.

**A. MEASURED OVER BAR — 15 cells. This is the queue.**

| # | cell | `ece_e` | `n_e` | excess | σ | impact | census `ece_c (n_c)` |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | baseball/quantity | 15.86 | 6,778 | 12.86 | **21.2σ** | 87,165 | 8.42 (26,138) |
| 2 | soccer/quantity | 8.51 | 5,749 | 5.51 | **8.4σ** | 31,677 | 4.67 (20,236) |
| 3 | soccer/container_member | 6.27 | 7,682 | 3.27 | **5.7σ** | 25,120 | 4.82 (31,478) |
| 4 | economics/quantity | 5.13 | 4,705 | 2.13 | 2.9σ | 10,022 | 7.19 (7,103) |
| 5 | hockey/quantity | 10.94 | 1,137 | 7.94 | **5.4σ** | 9,028 | 21.71 (2,062) |
| 6 | basketball/quantity | 5.73 | 2,104 | 2.73 | 2.5σ | 5,744 | 24.27 (13,067) |
| 7 | politics/quantity | 6.12 | 1,152 | 3.12 | 2.1σ | 3,594 | 8.69 (3,289) |
| 8 | tennis/quantity | 5.01 | 1,512 | 2.01 | 1.6σ | 3,039 | 3.47 (30,221) |
| 9 | baseball/container_member | 12.44 | 286 | 9.44 | 3.2σ | 2,700 | 15.62 (13,689) |
| 10 | golf/container_member | 25.11 | 118 | 22.11 | **4.8σ** | 2,609 | 10.46 (3,276) |
| 11 | esports/container_member | 3.15 | 8,217 | 0.15 | 0.3σ | 1,233 | 5.03 (78,906) |
| 12 | geopolitics/quantity | 19.36 | 60 | 16.36 | 2.5σ | 982 | 14.39 (217) |
| 13 | basketball/container_member | 6.65 | 262 | 3.65 | 1.2σ | 956 | 25.31 (6,911) |
| 14 | esports/quantity | 4.84 | 506 | 1.84 | 0.8σ | 931 | **1.87 (5,105)** — the bounded one |
| 15 | politics/container_member | 7.90 | 116 | 4.90 | 1.1σ | 568 | 3.08 (3,634) |

**Impact is not significance.** Rank 11 (`esports/container_member`) is 0.15 pp over the bar at
0.3σ on the largest eligible n on the board — it ranks 11th by `n×excess` and is indistinguishable
from the noise floor. Ranks 8, 13, 14 and 15 are all under 2σ. **The cells that are both large and
significant are 1–5 plus 10.**

**B. MEASURED UNDER BAR — 2 cells.** `tennis/container_member` 2.07 (n 2,583),
`economics/container_member` 2.78 (n 511). Measured, not bounded.

**C. UNMEASURABLE, `n_eligible` < 30 — 5 cells.** `table_tennis/quantity` (n_e 0, `ece_all` 44.43
over `n_all` 67,985), `table_tennis/container_member` (0, 46.57 / 52,147), `hockey/container_member`
(0, 41.07 / 1,528), `geopolitics/container_member` (8, 11.15 / 1,165), `golf/quantity` (0).
**`MIN_CELL_N = 30`, so ECE is ABSENT, never 0.0** — the datagolf-card mistake (#2172). 120,132
`table_tennis` legs are graded by something the published curve does not accept; that is its own
queue item and it is invisible on any ECE sort.

**D. NO ELIGIBLE CUT YET, census n ≥ 30 — 13 cells. THIS is the real `NEEDS RE-CUT` set,** and the
reason is scope, not a missing checkpoint: the fold's `league_scope_note` restricts it to the
diagnosis file's 11 leagues *"by the 1,000-row cap, not by judgment"*, and these are outside it.

| cell | census `ece_c` | `n_c` | | cell | census `ece_c` | `n_c` |
|---|---:|---:|---|---|---:|---:|
| weather/quantity | 1.59 | 64,117 | | motorsports/container_member | 14.41 | 356 |
| entertainment/quantity | 4.93 | 2,503 | | tech/quantity | 10.75 | 557 |
| entertainment/container_member | 3.90 | 1,847 | | mma/container_member | 6.44 | 904 |
| cricket/container_member | 3.44 | 1,387 | | mma/quantity | 3.25 | 378 |
| tech/container_member | 3.07 | 1,139 | | rodeo/container_member | 36.98 | 164 |
| football/container_member | 12.61 | 362 | | football/quantity | 13.37 | 37 |
| weather/container_member | 21.43 | 33 | | | | |

**E. NULL, census n < 30 — 15 cells.** `olympics/{cm,q}`, `cricket/quantity`,
`weightlifting/quantity`, `motorsports/quantity`, `legal/cm`, `culture/cm`, `crypto/cm`,
`rodeo/quantity`, `boxing/cm`, `rugby/{cm,q}`, `pickleball/cm`, `cycling/cm`, `chess/cm`. No
reliable ECE; not over bar; no query owed.

15 + 2 + 5 + 13 + 15 = **50**.

### 🔶 ONE NUMBER THIS FILE NOW CARRIES TWICE, AND IT IS NOT AVERAGED

`baseball/quantity` eligible ECE is **15.86** by the sargable id-range fold
(`eligible_fold_all_cells.json`, n 6,778) and **16.64** by the ANY-paged rail the handoff quotes
(`2d93a44ea9fb6022`, 5,374 ms, same n 6,778). Same cell, same population size, same eligibility
predicate, 0.78 pp apart. Both are recorded; neither is corrected into the other. It does not move
the rank — rank 1 either way, 21.2σ either way — but two rails that agree on `n` to the row and
disagree on `ece` by 0.78 pp are not both right, and the discrepancy belongs to whoever next
touches the binning (`_compute_horizon_mce` weighting vs the fold's shard-merge).

### WHAT THE HANDOFF CONTRIBUTES THAT THIS FILE DID NOT HAVE — kept, not discarded

* **`phantom_share` per measured cell**, and it is the stop-chasing signal: eligible share is
  1.6–16.1% on the four CAL-P093 cells (`baseball/quantity` 85.6% phantom / 40,392 legs excluded
  including 1,690 `pass2_loser` zero-winner markets at pair sum 0.9954; `baseball/container_member`
  98.4%, only 286 of 18,215 markets survive; `basketball/quantity` 83.9%;
  `basketball/container_member` 96.3%). **Nobody chases excluded rows again.**
* **`KXMLBKS` is ruled out for `baseball/container_member`** — round-2 random 500 returned
  `kcount 0/500` (95% CI < 0.6% prevalence), ECE 15.62 survives the exclusion. Not the mechanism.
* **The ANY-rail infrastructure findings, which are why the bus could not finish the job:** a direct
  `asyncpg` `run_cohort_cell_census` cannot connect without `DATABASE_URL`
  (`OSError ::1:5432 / 127.0.0.1:5432`); `POST /api/admin/db-query` full-scan
  `GROUP BY resolution_source` times out at `d894ba4f4b0a05c6`; a bounded `ANY(ARRAY[10])` probe hit
  `undefined_column e9d18…` on an ad-hoc truth-CASE, because the proven shape is the worker's own
  `_BINS_SQL` (`cohort_cell_census_worker.py:162`, fingerprint `1c27…`) and not a hand-rolled twin.
* **Fingerprints and durations** for the four CAL-P093 cells: `2d93a44ea9fb6022` 5,374 ms /
  `87eda0317190a3a7` 3,873 ms / `87457dc29c0c74d5` 1,290 ms / `dfc9f3c805a90083` 3,875 ms.

### What is actually owed after this fold

1. **13 cells in class D need an eligible cut** — the fold's scope, widened past the 11 leagues.
   That is the true "NEEDS RE-CUT", and it is 13, not 26.
2. **The three cells still resting on the refuted bound** (`weather/quantity` n 64,117 above all)
   must be measured or recorded as unmeasured. `weather/quantity` alone is a larger census
   population than any cell in class A.
3. **Nothing is owed on class C.** Five cells with `n_eligible` < 30 are answered; re-queuing them
   is the error this section exists to stop.

### 🛑 `baseball/container_member` — CUT OFF, and the cutoff is the finding

*The 2026-08-26 directive's item 3 names this cell "the next proven cell (12.44, n=286)" and asks
for the same treatment rank 1 got: mechanism from the ladder, smallest durable change, red-first,
cert-staged. **No fix is built. Two reasons, and the first is a consequence of the correction
above.***

**1. It is rank 9, not rank 2.** It ranked 2nd of the four cells the handoff had measured. On the
15-cell board it is 9th by `n_e × excess` — impact **2,700 against rank 1's 87,165**, or 3.1%. Its
selection was downstream of a table that was 22 cells behind. Four unworked cells sit above it:
`soccer/container_member` (25,120, 5.7σ), `economics/quantity` (10,022, 2.9σ),
`hockey/quantity` (9,028, 5.4σ) and `golf/container_member` (2,609, 4.8σ). Rank 2
`soccer/quantity` is already worked and parked — CAL-P095 found no shipped fix moves it and the one
candidate that looked like it would makes it worse.

**2. There is no mechanism to build from, because every ladder check on this cell predates
eligibility.** All three were executed on the census population of 18,215 markets, of which
**98.4% is phantom** — rows the published curve never contained:

| check | what was run | population | on the 286? |
|---|---|---|---|
| 1 · price-source fallback share | 1,000-market roster sample → `n=283, fallback 0` (`40e5bb`) | census | **no** |
| — · KXMLBKS contamination (#1990) | random 500 → `kcount 0/500`, 95% UB < 0.6% (`round2/*`) | census | **no** |
| 3 · shape semantics | the `n=283 / 37 winners / avg 0.283` row | census | **no** |
| 2, 4, 5, 6 | never executed for this cell | — | no |

The two checks that returned a verdict both returned *negative* ones — fallback is not the driver,
KXMLBKS is not the contamination — so even taken at face value the ladder has **ruled things out
and named nothing.** And they cannot be taken at face value for the published population: a sample
of a set that is 98.4% phantom says almost nothing about the 1.6% that survives. Building on it is
exactly the error the `phantom_share` column was added to prevent.

**What would have to happen first**, and it is a measurement-lane grant under ruling 134, not a
build lane's: re-run ladder checks 1–3 **on the 286 eligible legs only** — fallback share,
de-vig vs venue, and the sum-to-1 shape — using the worker's own `_BINS_SQL` shape
(`cohort_cell_census_worker.py:162`, fingerprint `1c27…`) rather than a hand-rolled twin, which is
what returned `undefined_column e9d18…` on the bus. Until one of those names a mechanism, a fix
here would be a guess with a test around it.

**Worth saying plainly about the ceiling even if a mechanism arrives:** 286 legs at 3.2σ. A perfect
fix moves this cell and nothing else, and the cell is 3.1% of the board's excess. It is a real
defect and it should be fixed eventually; it is not the next thing.

---

## STATUS 2026-08-26 (CAL-P100) — RANK 1'S SECOND MECHANISM IS BUILT. THE FIX SHIPS UNMEASURED, AND SAYS SO.

*Rank 1 `baseball/quantity`, 16.64 pp over n=6,778 on the published population. Its FIRST named
mechanism — the exact-0.5000 placeholder pair — was built by CAL-P097, reworked by CAL-P099, and is
sitting on `program/calibration-96` awaiting CERT-406B; this window did not touch it. This window
built the SECOND, which the item-2 ladder named in its own closing sentence as the cell's next
lead: **the published-column pair incoherence from check 2.***

### THE MECHANISM, TAKEN STRAIGHT FROM CHECK 2 RATHER THAN RE-MEASURED

Check 2's table, on the 2,438 pairs that are coherent AT OPENING — the class item 1's writer gate
protects, i.e. the structurally-healthy remainder:

| column | over mean | under mean | **pair sum** |
|---|---:|---:|---:|
| `opening_probability` | 0.3858 | 0.6143 | **1.0001** ✅ |
| published (`COALESCE(cal, open)`) | 0.2992 | 0.5757 | **0.8749** 🔴 |

**A pair captured coherently is PUBLISHED as two numbers that cannot both be forecasts of the same
binary** — about 12.5 points of probability mass missing from the pair the reader is shown, and the
platform is graded on it. `calibration_probability` is written per leg (Part A of
`_backfill_calibration_prices` takes each outcome's own last snapshot before the event's
commence_time) with **no pair constraint anywhere**. `app/utils/pair_opening_coherence.py` protects
the opening. Nothing protected the number the curve publishes.

Two details of check 2 that decided the implementation, both already in the file:

* **The gap direction is not a hindsight signature.** Published under gap −25.28 (worse than its
  opening −21.43) and corr **−0.646**; published over gap +12.77 and corr −0.036. Both legs fell
  from their openings (over −8.66 pp, under −3.86 pp).
* **Which means the arithmetic does not name a wrong leg**, and no measurement on record does
  either. So this is the EXCLUDE fork of item 1's own disposition doctrine — repair only where the
  direction is structurally certain (`identical_noncomp` had a measured 0.886 price/win-rate
  correlation; this has nothing equivalent). Inventing a direction is the "invented price becomes a
  published forecast" failure `pair_opening_coherence` exists to refuse.

### WHAT WAS BUILT — one read-side rule, defined once, disjoint from the two beside it

```
exclude BOTH legs of a market when:
    exactly two outcomes, named over and under
AND both legs carry an opening price AND both carry a published price
AND ABS(opening pair sum  − 1) <= PAIR_SUM_TOLERANCE     -- captured COHERENT
AND ABS(published pair sum − 1) >  PAIR_SUM_TOLERANCE    -- published INCOHERENT
```

🔴 **The opening-coherence clause is the load-bearing one, and it is there to keep this rule from
eating another rule's population.** Without it the predicate also swallows the `other_noncomp`
class (5,566 markets), whose read-side exclusion is `QUEUE-STAGED-CAL-PAIR-OPENING-DISPOSITION.md`.
That is CERT-403B's blocked defect exactly — a filter broader than the rule it claims to be — so
the two rules are made **disjoint by construction** rather than by anyone remembering.

| decision | what | why, in one line |
|---|---|---|
| tolerance | **imported** `PAIR_SUM_TOLERANCE`, not restated | one tolerance for the writer gate and the read-side gate, or one disagrees with the measurement that justified the other |
| symmetry | **both legs leave**; the flag is market membership with no leg clause | half-stamping is how the 22.71% `partial_open` population was made |
| scope | cell-scoped `polymarket`/`baseball`/`quantity` | CERT-403B's second P1, and CAL-P095's control: the same rule was −3.12 pp in one cell and **+0.41 pp** in another |
| horizon | renders `false` off the terminal price path, structurally | the horizon surface's `hp.horizon_prob` join does not exist in `market_result_shape`; silently re-pointing a terminal rule at a snapshot price is worse than the SQL error |
| accounting | **four** renderings of `published_row_predicate`, three marginal counts + the overlap | with two exclusions live, "rows this rule removed" stops being one number — crediting a doubly-flagged row to each double-counts, to neither understates both |

### 🔴 WHAT MOVED, AND WHAT DID NOT — the cell row

| | before | after | note |
|---|---|---|---|
| `baseball/quantity` `ece_eligible` | 15.86 / n=6,778 | **UNMEASURED — no claim** | ruling 134: a build lane measures its own gates and nothing else |
| rank | 1 | **1** | nothing measured can have moved it |
| mechanism 1 (0.5000 spike) | built, BLOCKed, reworked | **untouched this window** | on `-96`, awaiting CERT-406B; worth −3.12 pp when it lands |
| mechanism 2 (published pair) | *named, never built* | **BUILT, red-first, cert-staged** | 38 tests; base 7/7 FAIL exit 1, head 7/7 PASS exit 0 |
| ladder coverage | 6 of 6 executed | 6 of 6 | this window ran no fold |
| cell closed? | no | **no** | see below |

**Stated plainly: this window shipped a fix and did NOT ship a number.** The ECE delta of this rule
is unknown. The instrument that will produce it is
`backend/scripts/fold_published_pair_coherence.py`, which renders THIS predicate out of the shared
builder — baseline vs proposed is one boolean, and masking that rule's two expressions out of the
armed chain reproduces the disarmed chain **byte for byte**, so any delta it measures is
attributable to this rule and nothing else. Running it is an attended-dyno grant belonging to the
measurement lane.

**Do not read a GREEN cert on this as "the cell improved."** The same sentence CAL-P099 had to write
about 406B applies here unchanged: *the instrument is correct; the measurement is owed.*

### WHAT REMAINS ON THIS CELL

1. **The two deltas, both owed and neither derivable from the other** — mechanism 1's −3.12 pp is
   measured but unshipped; mechanism 2's is unmeasured. **They must not be added.** The two rules
   can flag the same market (a 0.5000/0.5000 pair whose calibration prices later diverged publishes
   off-sum), which is exactly why the payload now reports `also_removed_by_half_spike_pair` as its
   own count rather than folding it into either.
2. **`ROUND(op,4) = 0.5005`** — same signature, 1/18th the size, still deliberately out of scope
   (staged spec §5). A tolerance band turns a self-evidencing exact match into a judgement call.
3. **Whether either rule generalises past this cell.** Both are cell-scoped on the same precedent
   and for the same reason. The published-pair defect is a *writer* property and is therefore very
   likely wider — but CAL-P095 is the standing proof that "likely wider" and "safe to widen" are
   different claims.
4. **The residual after both.** Even granting mechanism 1's −3.12, ~12.74 pp over ~4,982 legs was
   unexplained before this rule and no measurement here reduces that. The cell is **not closed**.

### ONE FINDING FROM AN EXISTING GUARD, NOT FROM THIS LANE

The fingerprint-coverage tripwire fired for the **third queue running**, and for the third time the
answer was to cover rather than loosen. Two real holes, needing different repairs:

* `_SHAPE_CLAUSE_INDENT` — module-level, reaches the emitted SQL, simply not hashed. Hashed now.
  It is whitespace; the rule for that list is *does it shape the statement*, not *does it look
  important*.
* 🔴 `PAIR_SUM_TOLERANCE` — **hashed by value already, and reported as an unguarded hole anyway.**
  `derive_declared` built its coverable set from module-level defs ONLY, so an *imported* constant
  was **permanently uncoverable**: guarded in fact, a hole in the count, forever. That is a false
  positive in the one number the artifact exists to make trustworthy, and the predictable response
  to a tripwire that fires on correct code is to delete the tripwire. Fixed in the analyzer
  (`defs | imports`) — it removes false negatives and cannot hide a real hole, because a name still
  has to appear in the `input_fingerprint(...)` call to count as covered.

`uncovered_sql_shaping` is therefore **still 21** — the number with correctness consequences did not
move, which is the whole reason it is pinned apart from the totals.

---

## STATUS 2026-08-25 (CAL-P095) — RANK 2 WORKED. ITS SPIKE IS NOT ITS MECHANISM, AND THE WRITER WAS HIDING HALF OF EVERY PAIR.

*Rank 1 `baseball/quantity` has a named mechanism and a staged apply, both untouchable this
session. This is rank 2, `soccer/quantity` — 8.51 pp over n=5,749, 8.4σ, impact 31,677 — taken
down the 6-check ladder. Four candidate mechanisms were refuted with executed numbers, the fifth
produced a **negative result that constrains a staged apply**, and the ladder surfaced a writer
defect that has been silently deleting half of every Polymarket pair's evidence since ingestion
began.*

### 🔴 THE HEADLINE, AND IT IS A NEGATIVE RESULT: EXCLUDING THE 0.5000 SPIKE MAKES RANK 2 **WORSE**

`soccer/quantity` carries the same exact-0.5000 placeholder mass rank 1 does, at almost exactly
the same share — and removing it moves the cell the wrong way.

| measurement | `ece_eligible` | `n` | gap | shards | irreducible | artifact |
|---|---:|---:|---:|---:|---:|---|
| baseline | **8.51** | 5,749 | −0.79 | 26 | **0** | `soccer_q_baseline.json` |
| exclude `ROUND(op,4) = 0.5000` | **8.92** | 3,761 | −0.68 | 26 | **0** | `soccer_q_excl_half_spike.json` |
| **Δ** | **+0.41 — WORSE** | −1,988 | | | | |

The baseline **reproduces the re-ranked board's 8.51 / n=5,749 exactly**, through a script
generalised from `fold_arbitrate_bbq.py` whose SQL is proven byte-identical to CAL-P094's at its
defaults — so this is a confirmation of the board, not a restatement of it.

**Consequence for `QUEUE-STAGED-CAL-EXCLUDE-HALF-SPIKE.md`, which this window did not touch and
must not:** that apply is worth **−3.72 pp** on `baseball/quantity` and **+0.41 pp on
`soccer/quantity`**. CAL-P094 recorded "a population-wide census of the 0.5000 spike outside
`baseball/quantity`" as OWED and not collected. Here is the first cell of it, and the answer is
that **the benefit does not generalise**. The exclusion must stay cell-scoped, or be re-argued
per cell; a population-wide sweep on the value predicate would import error, not remove it.
This is the same trap as `soccer/container_member`'s +6.54 in CAL-P094 item 1 and the same trap
as its own check 6 — *exclusion is not automatically an improvement*, now demonstrated on a
second, independent cell.

### THE LADDER — four mechanisms refuted, each EXECUTED, 0 irreducible shards throughout

| # | check | result for `soccer/quantity` | verdict |
|---:|---|---|---|
| 1 | price-source fallback (#1978) | fallback share **0.003** (2 of 759 sampled) | **refuted** |
| 2 | leg swap | opening corr **over +0.868 / under +0.815**; published **+0.913 / +0.828** | **refuted** — a swap needs a NEGATIVE slope (rank 1 shows −0.58) |
| 3 | shape / pair coherence | opening gaps +3.70 / −3.71, exactly equal and opposite; published legs sum to **0.9928** | **refuted as the driver** — and note this is NOT rank 1's 0.875 |
| 4 | hindsight (capture-age) | cell-wide gap **−0.79**; a post-settlement rewrite drags the gap POSITIVE | **refuted by the sign** |
| 5 | the 0.5000 spike | **1,979 legs = 38.2%** of the coherent class (rank 1: 37.45%) — but see the table above | **present, and NOT the mechanism** |
| 6 | binning noise floor | 8.4σ on `SE = 50/√n` | **real, not noise** |

Two independent folds agree on the spike's size: `fold_coinflip_default.py` counts 1,979 legs
inside coherent two-leg pairs, and the cell-wide exclusion predicate drops 1,988 eligible legs.
The nine-leg difference is the spike outside coherent pairs, and the agreement is a cross-check
between two query shapes, not one number quoted twice.

**Where the spike differs from rank 1 is its COST, and that is the whole finding.** Same value,
same share, same provenance shape — and a completely different realised outcome:

| cell | spike legs | share of coherent class | under wins | over wins | internal error | exclusion Δ |
|---|---:|---:|---:|---:|---:|---:|
| `baseball/quantity` (rank 1) | 1,826 | 37.45% | **0.9762** | 0.0244 | **47.59 pp** | **−3.72** |
| `soccer/quantity` (rank 2) | 1,979 | 38.2% | **0.5998** | 0.4012 | ~9.9 pp | **+0.41** |

A 0.50 placeholder costs the curve only what the outcome it stands in for was knowable. In
baseball the answer was near-certain and the placeholder was catastrophic; in soccer these really
are close-to-even markets and the placeholder is nearly right. **The mechanism generalises; its
price does not.**

### 🔴 THE WRITER FINDING — 493,415 Under/No legs, ZERO books, and it refutes a banked inference

Running check 5's provenance fold on rank 2 returned a verdict table structurally identical to
rank 1's: `no_book` **992 legs, every one an UNDER leg, zero bid and zero ask**. Two cells
producing the identical "all Under, no book" shape is not a coincidence about markets, so the
next step was to read the writer instead of the data.

`app/tasks/polymarket.py`'s decomposed-pair path passes `current_yes_bid=market.best_bid` /
`current_yes_ask=market.best_ask` on the **Over** upsert, and mentions neither column in the
**Under** upsert's values or in its `on_conflict_do_update` set clause. Measured population-wide
(`leg_book_coverage.json`, 15 shards, **0 irreducible**, 637.1 s):

| leg | n | n_bid | bid % | n_ask | ask % | n_open |
|---|---:|---:|---:|---:|---:|---:|
| over | 248,702 | 191,444 | 76.98% | 246,564 | **99.14%** | 214,752 |
| under | 248,702 | **0** | **0.0000%** | **0** | **0.0000%** | 201,268 |
| yes | 258,746 | 171,624 | 66.33% | 253,653 | **98.03%** | 235,774 |
| no | 244,713 | **0** | **0.0000%** | **0** | **0.0000%** | 185,033 |

**493,415 Under/No legs and not one book, against 99% ask coverage on their Over partners.**
386,301 of those book-less legs nevertheless carry an `opening_probability` — they are published
forecasts with no recorded evidence, ever.

🔴 **This retires CAL-P094's item-2 reading.** That section concluded, of rank 1's spike:

> every one of the 924 `no_book` legs is an UNDER leg with no book at all, and that is not a
> stale-book artifact: **a leg that never had a book never had one.** So the mechanism is two-part
> — the Over leg takes 0.5 from an untraded market's precomputed price, and the **Under** leg is
> written as its arithmetic complement `1 − 0.5 = 0.5` with no quote of its own.

`no_book` is a property of the **writer**, uniform across the whole population at every price and
every outcome, so it carries no information about whether a market traded. **Gotcha #53 exactly**:
the emptier reading of one response shape taken for a fact about the world. The two-part mechanism
above is *unsupported by this evidence* — the Under leg is written from Gamma's own
`outcome_prices[1]`, not computed as `1 − p`, and its NULL book says nothing either way. Rank 1's
spike is still real, still 37.45%, still worth −3.72 pp; only the provenance sentence falls.

It also explains the 6.6% (rank 1) / 7.8% (rank 2) that `is_fabricated_midpoint` claims of a spike
whose Under half is half the mass: **the predicate reads book columns, and on Under legs there are
none to read.** It was never 93% wrong; it was 50% blind by construction.

**SHIPPED (this window):** `complementary_book()` in `app/tasks/polymarket.py`, wired into the
Under upsert's insert values *and* its conflict-update. In a binary CLOB the No token's book IS
the Yes token's book from the other side — a resting bid for No at `q` is the same order as an ask
for Yes at `1 − q` — so this records what exists rather than inventing it, and it is NULL-preserving
in both directions (a missing counterpart yields `None`, never a manufactured `0`, because `bid > 0`
and `last_price > 0` are liquidity tests downstream). The spread is invariant under the flip, so
neither leg can launder the other past a spread test. Red-first: 3 writer pins failed at **exit
code 1** before the change, 18 pass after; `tests/test_polymarket_under_leg_book.py`, 18 tests.

This stays clear of the fail-closed rule in `pair_opening_coherence` — that rule governs
**openings**, which become published forecasts through `calibration_probability`'s fallback and
must be refused rather than synthesised. These are evidence columns.

### 🔴 THE TWIN, MEASURED AND DELIBERATELY NOT SHIPPED — a one-sided exclusion on a two-sided instrument

The Under **snapshot** omits `yes_bid` / `yes_ask` / `last_price` the same way, and
`POLY_PLACEHOLDER_EXCLUDE` in `precompute_calibration.py` gates the published curve on exactly
those columns:

```
vm.source = 'polymarket' AND COALESCE(cp, op) BETWEEN 0.45 AND 0.55
  AND NOT EXISTS (SELECT 1 FROM futures_odds_snapshots
                  WHERE outcome_id = fo.id AND (yes_bid > 0 OR last_price > 0))
```

⚠️ **A bounded probe said that `NOT EXISTS` is true for 100% of Under legs. The population fold
says 95.1%, and the corrected number is the one that stands.** A 1M-id probe returned 0 of 1,445
Under/No legs with evidence; the whole-population fold
(`leg_trade_evidence.json`, 47 shards, **0 irreducible**, 823.1 s) found that some other writer —
not this one — does reach a minority of them:

| leg | n | with trade evidence | traded % | in band | **excluded by the filter** | **excluded %** |
|---|---:|---:|---:|---:|---:|---:|
| over | 248,702 | 224,255 | **90.17%** | 138,024 | 562 | **0.41%** |
| under | 248,702 | 12,408 | **4.99%** | 141,228 | 134,296 | **95.09%** |
| yes | 258,746 | 232,398 | **89.82%** | 122,860 | 3,586 | **2.92%** |
| no | 244,713 | 25,570 | **10.45%** | 115,613 | 102,153 | **88.36%** |

So it is not "none can" — it is **95.09% of Under band legs excluded against 0.41% of Over band
legs, a 232× asymmetry**, and it is not a liquidity fact about those markets. Recording the
difference because the tidier claim was the one I reached first: the outcome-column count above IS
exactly zero, and the temptation to carry that exactness across to the snapshot column was the
error the population fold caught.

On the recent window where the asymmetry is total, the cost is directly measurable. Truth-eligible
resolved legs in the band, `fm.id` 40M–59.6M (fp `136aef5a181cf214`):

| leg | n | survives the exclusion | mean p | win rate | gap |
|---|---:|---|---:|---:|---:|
| over | 661 | **100% — all have evidence** | 0.5001 | 0.4251 | **+7.50 pp** |
| under | 657 | **0% — none do** | 0.4999 | 0.5753 | **−7.54 pp** |
| yes | 241 | **100%** | 0.5092 | 0.8714 | **−36.22 pp** |

**The filter is one-sided, and not because of liquidity.** It keeps every Over leg and drops every
Under leg of the same binaries, and the two sides carry equal-and-opposite errors over near-identical
n (661 / 657). The published curve keeps the **+7.50** half of a two-sided instrument and discards
the **−7.54** half — a systematic bias imported by a filter that believes it is measuring trading
activity. `is_poly_never_traded`, which feeds the Queue #220/221 exclusion-symmetry census, inherits
the same skew.

**Not fixed here, on purpose.** Filling the snapshot columns moves the published curve, and the
window that measured the benefit may not certify it (the standing rule that keeps CAL-P094's three
applies on the bus). Staged as `QUEUE-STAGED-CAL-UNDER-LEG-SNAPSHOT-BOOK.md` with this census
attached. Note it is **forward-only**: no historical row is un-excluded without a backfill, so the
staged apply is what ends this, not the deploy.

### WHAT MOVED, AND WHAT DID NOT — the cell row

| | before | after | note |
|---|---|---|---|
| `soccer/quantity` `ece_eligible` | 8.51 / n=5,749 | **8.51 / n=5,749 — UNCHANGED** | no fix shipped moves this cell today, and the one candidate that looked like it would makes it worse |
| rank | 2 | **2** | unchanged |
| mechanism | *pending — never measured* | **4 refuted, spike present but disproven as the driver; 8.51 over 3,761 non-spike legs remains unexplained** | the cell is **NOT closed** |
| ladder coverage | 0 of 6 checks | **6 of 6 executed** | 0 irreducible shards in every fold |
| `no_book` provenance (rank 1 AND 2) | read as "never traded" | **retired — a writer property** | CAL-P094 item 2's provenance sentence falls |
| Under-leg book capture | 0 of 493,415 | **fixed forward**, red-first | outcome columns only |
| `POLY_PLACEHOLDER_EXCLUDE` symmetry | unexamined | **measured one-sided, ±7.5 pp** | staged |

**Stated plainly: rank 2's ECE did not move, and this window did not close it.** What it produced
is a mechanism ruled out with numbers instead of assumed, a shipped capture fix, a retired
inference, a measured curve bias, and a negative result that stops a staged apply from being
generalised into a regression. The residual — **8.92 pp over 3,761 legs with the spike removed** —
is the next window's target, and the unexamined bins are where to start: on the published column
the Under leg's bin 0 (n=95, mean 0.0583) wins **0.3789** for an error of **−32.06 pp**, and bins
3/4 (+13.07 / +10.98) sit against bin 5 (−15.95) — a price compressed toward 0.50 with the truth
more extreme on both sides, which is a *dispersion* story, not a placeholder story.

---

## STATUS 2026-08-24 (CAL-P094) — THE FILE IS RE-RANKED ON `ece_eligible`. NINE CELLS MOVED FOUR PLACES OR MORE.

*CAL-P093 (below) proved the ranking metric was wrong and fixed the census to emit
`ece_eligible`/`n_eligible`. It did not re-rank the file — it re-measured four cells and left the
other eighteen on the old metric, which is a board where the top and the middle are denominated
differently. This section is the re-rank, on the directive's item 3.*

### THE TOP FIVE, AND WHAT MOVED

| new | cell | `ece_eligible` | `n_eligible` | excess | σ | impact | old | **Δ** |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| **1** | **baseball/quantity** | **15.86** | **6,778** | 12.86 | **21.2σ** | 87,165 | 5 | **+4** |
| **2** | **soccer/quantity** | **8.51** | **5,749** | 5.51 | **8.4σ** | 31,677 | 8 | **+6** |
| **3** | **soccer/container_member** | **6.27** | **7,682** | 3.27 | **5.7σ** | 25,120 | 7 | **+4** |
| **4** | **economics/quantity** | **5.13** | **4,705** | 2.13 | 2.9σ | 10,022 | 9 | **+5** |
| **5** | **hockey/quantity** | **10.94** | **1,137** | 7.94 | **5.4σ** | 9,028 | 15 | **+10** |

**The old top four are now 6th, 9th, 11th and 13th.** Every cell CAL-P093 "moved" moved DOWN, and
the cells that rose are ones this file has barely touched:

| cell | old | new | **Δ** | why it moved |
|---|---:|---:|---:|---|
| basketball/quantity | 1 | 6 | **−5** | 24.27 → 5.73 on 16.1% eligible share |
| baseball/container_member | 2 | 9 | **−7** | n_eligible 286, not 13,689 — 1.6% share |
| esports/container_member | 3 | 11 | **−8** | measured this round: **3.15 at 0.3σ** — see item 4 below |
| basketball/container_member | 4 | 13 | **−9** | n_eligible 262 at 1.2σ |
| hockey/container_member | 6 | **—** | **UNMEASURABLE** | `n_eligible = 0`. See the red block below. |
| table_tennis/quantity | 11 | **—** | **UNMEASURABLE** | `n_eligible = 0` on `n_all` 71,467 |
| tennis/quantity | 13 | 8 | +5 | 3.47 → 5.01, but only 1.6σ |
| tennis/container_member | 14 | **—** | **BELOW BAR** | **2.07** — under 3pp, and −0.9σ |
| soccer/quantity | 8 | 2 | +6 | 45.08 `ece_all` → 8.51 eligible, but n 5,749 carries it |
| hockey/quantity | 15 (footnote) | 5 | +10 | was dismissed as "monitored" at n=2,062; 55% of it is eligible |

### 🔴 `n_eligible = 0` IS UNMEASURABLE, NEVER CLEAN — AND IT DELETES THIS FILE'S WORST CELL

**`hockey/container_member` — the cell this file has called "the WORST true cell, 41.00pp, 29σ, NO
known mechanism" through every round — has `n_eligible = 0`.** Not a low ECE. **No measurement at
all.** Zero of its 1,528 graded legs have a truth-eligible `resolution_source`, so none of them are
on the published curve, so the 41.00pp was computed entirely over rows the curve never showed. The
29σ was 29σ of a number about nothing. Six rounds of this file ranked it 6th and called for
bisection work on it.

| cell | `n_eligible` | `ece_all` | `n_all` | old rank |
|---|---:|---:|---:|---:|
| table_tennis/quantity | **0** | 44.55 | 71,467 | 11 |
| table_tennis/container_member | **0** | 46.51 | 56,230 | — |
| hockey/container_member | **0** | 41.07 | 1,528 | **6** |
| geopolitics/container_member | **8** | 11.27 | 1,165 | — |
| golf/quantity | **0** | — | 2 | — |

`MIN_CELL_N = 30`, so ECE is **ABSENT** for all five — not 0.0. **Rendering an absent ECE as 0.0 is
the datagolf card's mistake** (`0 outcomes · 0.0pp ECE` shown as a perfect score, #2172) and it is
the single easiest way to lose the four largest unmeasured populations on this board. 127,697
`table_tennis` legs are graded by something the curve does not accept; that is a finding worth its
own queue item, and it is invisible on any ranking that sorts by ECE.

### 🔴 AND THE OPPOSITE DIRECTION — ELIGIBILITY IS NOT A DISCOUNT

`golf/container_member`: `ece_all` **22.99** → `ece_eligible` **25.11**. The filter made it WORSE.
Nine cells got better and one got worse, which is what a filter that selects on *truth provenance*
rather than on error should do. Anyone who has internalised "eligible ECE is the smaller one" from
CAL-P093's four cells has learned a coincidence.

### THE FULL RE-RANKED BOARD (authoritative — this is the queue)

Ranked on `n_eligible × (ece_eligible − 3)`. σ uses `SE = 50/√n` pp, the same formula as the noise
table below, recomputed on the eligible n.

| # | cell | `ece_e` | `n_e` | excess | SE | σ | impact | old | Δ |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | baseball/quantity | 15.86 | 6,778 | 12.86 | 0.61 | **21.2σ** | 87,165 | 5 | +4 |
| 2 | soccer/quantity ‡ | 8.51 | 5,749 | 5.51 | 0.66 | **8.4σ** | 31,677 | 8 | +6 |
| 3 | soccer/container_member | 6.27 | 7,682 | 3.27 | 0.57 | **5.7σ** | 25,120 | 7 | +4 |
| 4 | economics/quantity | 5.13 | 4,705 | 2.13 | 0.73 | 2.9σ | 10,022 | 9 | +5 |
| 5 | hockey/quantity | 10.94 | 1,137 | 7.94 | 1.48 | **5.4σ** | 9,028 | 15 | +10 |
| 6 | basketball/quantity | 5.73 | 2,104 | 2.73 | 1.09 | 2.5σ | 5,744 | 1 | −5 |
| 7 | politics/quantity | 6.12 | 1,152 | 3.12 | 1.47 | 2.1σ | 3,594 | 12 | +5 |
| 8 | tennis/quantity | 5.01 | 1,512 | 2.01 | 1.29 | 1.6σ | 3,039 | 13 | +5 |
| 9 | baseball/container_member | 12.44 | 286 | 9.44 | 2.96 | 3.2σ | 2,700 | 2 | −7 |
| 10 | golf/container_member | 25.11 | 118 | 22.11 | 4.60 | **4.8σ** | 2,609 | 10 | 0 |
| 11 | esports/container_member | 3.15 | 8,217 | 0.15 | 0.55 | **0.3σ** | 1,232 | 3 | −8 |
| 12 | geopolitics/quantity | 19.36 | 60 | 16.36 | 6.45 | 2.5σ | 982 | — | new |
| 13 | basketball/container_member | 6.65 | 262 | 3.65 | 3.09 | 1.2σ | 956 | 4 | −9 |
| 14 | esports/quantity | 4.84 | 506 | 1.84 | 2.22 | 0.8σ | 931 | — | new |
| 15 | politics/container_member | 7.90 | 116 | 4.90 | 4.64 | 1.1σ | 568 | — | new |
| — | economics/container_member | **2.78** | 511 | −0.22 | 2.21 | −0.1σ | below bar | — | — |
| — | tennis/container_member | **2.07** | 2,583 | −0.93 | 0.98 | −0.9σ | below bar | 14 | out |

‡ **`soccer/quantity` was worked by CAL-P095 (2026-08-25) — see the top section.** Baseline
**re-confirmed at 8.51 / n=5,749** through an independent script; all six ladder checks executed;
four mechanisms refuted; the 0.5000 spike is present at 38.2% but **excluding it makes the cell
WORSE (8.51 → 8.92)**, so it is not this cell's mechanism and the staged half-spike exclusion must
not be generalised. The cell stays rank 2 and is **not closed**.

**Scope note, and it is a limit not a clearance:** the fold covers the 11 leagues × 2 market types
this file already scoped, restricted by the endpoint's 1,000-row cap and NOT by judgment. Cells
outside that list are **not measured here** and must not be read as absent-because-clean.

### 🔴 THE NOISE FLOOR IS THE SECOND-BIGGEST FINDING OF THE RE-RANK

The old noise table was computed on `n_complete` (13,067 / 6,911 / 78,906 …). On the real
denominator, **seven of the fifteen cells over the bar are under 2.5σ, and four are under 1.5σ.**
The bar says presume miscalculation, so they stay on the board — but "over 3pp" and "distinguishable
from noise" have come apart, and a window that spends a day on `basketball/container_member`
(3.65 excess, **1.2σ**, n=262) is chasing a number that could move on its own.

Cells where the excess is NOT separable from noise (< 1.5σ): `esports/container_member` **0.3σ**,
`esports/quantity` 0.8σ, `politics/container_member` 1.1σ, `basketball/container_member` 1.2σ.
Cells where it clearly is (> 5σ): `baseball/quantity` **21.2σ**, `soccer/quantity` **8.4σ**,
`soccer/container_member` **5.7σ**, `hockey/quantity` **5.4σ**.

**Work the σ column, not the ECE column.** `golf/container_member` sits at 25.11pp — the largest
ECE on the board — over n=118, and `geopolitics/quantity` at 19.36pp over n=60. Both are real
(4.8σ, 2.5σ) and both are worth less than `soccer/quantity` at 8.51pp, because impact is the
product. That is what the charter's "big to small" means once the denominator is honest.

### ITEM 4 — `esports/container_member` MEASURED: 3.15pp over n=8,217. Barely over the bar, 0.3σ.

It was rank 3 on the old metric and had never been measured; the previous round recorded "78,906
rows timed out the 10 s row path — needs the `MOD(fm.id, k)` fold." It is now measured, and it
falls to **rank 11**.

| | value |
|---|---|
| `ece_eligible` | **3.15** |
| `n_eligible` | **8,217** (of `n_all` 119,993 — 6.85% eligible share) |
| `ece_all` | 20.14 |
| excess over bar | **0.15 pp**, SE 0.55, **0.3σ** |
| pair-class attribution | `ok` 7,162 legs at **2.46** (under the bar); `other_noncomp` 583 at 22.31; `partial_open` 370 at 25.22; `identical_noncomp` 102 at 16.94 |

**The cell is essentially clean and its residual is the pair defect, not a calibration mechanism.**
Its structurally-healthy majority — 87% of the eligible legs — sits at **2.46pp, below the bar**,
with gap +0.03. What lifts the cell over 3 is 1,055 legs of corrupted or half-priced pairs, which
is the disposition staged in `QUEUE-STAGED-CAL-PAIR-OPENING-DISPOSITION.md`, not a mechanism owed
by this cell. **Recommend: closed on mechanism, monitored on the pair apply's before/after.**

🔴 **HOW IT WAS MEASURED — a deliberate, reported deviation from the directive's wording.** The
directive said "measure it with the `MOD(fm.id,k)` fold". **`MOD(fm.id,k) = j` is not sargable.**
It cannot use `futures_markets_pkey`, so every one of the `k` shards seq-scans the whole table:
the fold divides the aggregate work by `k` while **multiplying the scan by `k`**. Measured plan cost
for the `MOD` shape: **130,431** (fp `e610b5575d602919`); the roster query it was meant to rescue
had already timed out at 10 s (corr `e87f755d36db`). A range predicate —
`fm.id >= lo AND fm.id < hi` — rides the primary key, and with bisection on timeout it completed
the whole population in 45 shards with **0 irreducible**. The number above is the number the
directive asked for; the tool that produced it is not the tool the directive named, and the reason
is that the named tool cannot fit under the 10 s budget it was named to fit under.

---

### ITEM 1 — THE PAIR DEFECT: ONE HALF WAS ALREADY FIXED, THE OTHER HALF IS A DIFFERENT DEFECT

The directive named this file's own check-3 finding as the next fix: *"Polymarket O/U pairs carrying
a NON-COMPLEMENTARY `opening_probability` — the Over price copied onto the Under leg
(fp `08318aba2a1385da`)"*, and instructed a writer fix at ingestion. **The census says that specific
defect is already dead, and a different one is live.** Both are in the census; they have opposite
dispositions.

`artifacts/cal-p094/ou_pair_census_all.json` — whole resolved Polymarket population, **470,976**
two-leg markets, 37 sargable shards, **0 irreducible**, 183.2 s:

| open_class | markets | share | post-`231e39c3` openings | truth-eligible | avg pair sum |
|---|---:|---:|---:|---:|---:|
| `complementary` | 339,587 | 72.10% | **67.688%** ← the ruler | 16,279 | 1.0000 |
| `partial_open` | 106,948 | 22.71% | 0.913% | 1,717 | — |
| `identical_noncomp` | 18,875 | 4.01% | **0.058%** | 1,829 | 0.6890 |
| `other_noncomp` | 5,566 | 1.18% | **11.337%** | 619 | 0.9059 |

**A row count answers "how many" and cannot answer "is it still happening" (gotcha #53), so the
census carries a second signal: the share of each class whose opening was captured after `231e39c3`
(2026-07-08).** Read against the 67.688% healthy base rate:

* **`identical_noncomp` — the defect the directive named — is FIXED.** 0.058% post-fix is a ~1,650×
  drop; 11 markets in the whole population. A writer fix here would have been a fix to nothing. What
  is owed instead is a regression guard, and that is what shipped.
* **`other_noncomp` — 11.337% post-fix — is STILL BEING WRITTEN**, and it is a *different*
  mechanism: the Over leg's price is **source-resolved** (`outcome_prices[0]`, or a computed bid/ask
  midpoint, or `last_trade_price`, or a bare `best_ask`) while the Under leg took raw
  `outcome_prices[1]` with no guard. Whenever the resolver did not pick `outcome_prices[0]`, the two
  legs of ONE binary were written **from two different price sources** and summed to 1 only by luck.
  `231e39c3` corrected *which* price the Under leg copied; it never checked the two prices against
  each other.

**Shipped:** `app/utils/pair_opening_coherence.py` — a fail-closed, symmetric gate that refuses
rather than repairs (an invented opening becomes a published forecast, because
`calibration_probability` falls back to `opening_probability`), checks provenance **before**
arithmetic (a mixed-source pair summing to 1.00 is still two instruments glued together), and stamps
NEITHER leg when the pair is incoherent — half-stamping is how the 22.71% `partial_open` population
came to exist. Red-first proven at all four call sites. Certification staged as **CERT-401**. Two
further column-gate defects were found and fixed while wiring it, both on the Under upsert:
`opening_captured_at` took the OVER leg's gate, and `opening_american_odds` was gated on bare
`sub_has_trading`.

#### What the class COSTS — per cell, truth-eligible, and one cell gets WORSE

`artifacts/cal-p094/pairclass_ece.json`, 45 shards, 0 irreducible, 302.9 s. This fold reproduced
`ece_eligible` **exactly** for every cell through a completely different query shape (window
functions vs group-by, 2M vs 4M chunks, 45 vs 26 shards) — an independent confirmation of the
ranking numbers above, not a restatement of them.

| cell | `ece_e` | n | excl. identical | **Δ** | n_id | identical ECE / gap | healthy `ok` class |
|---|---:|---:|---:|---:|---:|---:|---:|
| soccer/container_member | 6.27 | 7,682 | **12.81** | **+6.54** | 1,882 | 19.29 / −15.14 | 5,668 @ 13.51 |
| baseball/quantity | 15.86 | 6,778 | 14.68 | −1.18 | 1,000 | 25.59 / −21.18 | 4,880 @ 13.51 |
| soccer/quantity | 8.51 | 5,749 | 8.26 | −0.25 | 500 | 21.39 / −3.56 | 5,214 @ 8.14 |
| tennis/quantity | 5.01 | 1,512 | 4.19 | −0.82 | 50 | 38.02 / −1.29 | 1,450 @ 4.20 |
| esports/container_member | 3.15 | 8,217 | 3.06 | −0.09 | 102 | 16.94 / −11.94 | 7,162 @ 2.46 |
| basketball/quantity | 5.73 | 2,104 | 5.68 | −0.05 | 78 | 14.69 / −6.50 | 2,026 @ 5.68 |

🔴 **`soccer/container_member` gets WORSE by +6.54 pp when the defect is removed.** The identical
legs are under-priced (gap −15.14) and the healthy remainder is over-priced, so the two errors
**cancel inside shared bins**. An ECE that is low because two defects cancel is a lie with a good
number on it, so the removal is still correct — but it must be announced in advance or the next
reader files it as a regression and reverts a correct change. **Exclusion is not automatically an
improvement.**

⚠️ **Items 1 and 2 do NOT converge, contrary to the expectation the directive was written under.**
The pair defect explains only **1.18 pp of baseball/quantity's 15.86 (7.4%)**. The dominant mass is
the structurally-**healthy** `ok` class: n=4,880, 72% of the cell, at **13.51 pp with gap −6.23**.
Removing every corrupted pair leaves 14.68. Whatever baseball/quantity's mechanism is, it is not
this one — see the item-2 ladder.

*(`ok` measuring 13.51 in both baseball/quantity and soccer/container_member is a 2-decimal
collision, not a shared computation: the two carry different n (4,880 vs 5,668), different gaps
(−6.23 vs −2.78) and different winners. A shared code path would have matched the gap too.)*

#### Disposition of the 24,441 existing corrupted rows — proposed, not applied

Staged as `QUEUE-STAGED-CAL-PAIR-OPENING-DISPOSITION.md` (cert-flagged, census attached, **nothing
re-graded** — gotcha #21). Split by class, because only one of them meets the directive's
"structurally certain" condition:

* **`identical_noncomp` → REPAIR `under := 1 − p`.** The direction was MEASURED, not assumed:
  `artifacts/cal-p094/pair_direction.json`, 823 truth-eligible pairs, 0 irreducible. The Over leg's
  win rate runs **0.048 → 1.000** as its price runs 0.031 → 0.944 (n-weighted correlation
  **0.886**), so `p` is the Over leg's real price. The null — `p` is noise, both legs win near 0.5 in
  every bin — predicts a flat line and is refuted. Repair takes the class from **18.92 → 5.62** ECE.
  *(The repaired gap of exactly 0.00 is arithmetic, not evidence: `p + (1−p) = 1` predicted against
  exactly 1 winner is identically zero for any `p`, including a wrong one. The 5.62, computed within
  bins, is the load-bearing number.)* Note that "half the legs win" tests nothing — it is true by
  construction for any one-winner two-leg market. Bin 5 (n=162, the largest bin, mean p 0.5433, Over
  wins 0.2778) is the single non-monotone bin; flagged, not hidden, and it does not move the verdict.
* **`other_noncomp` → EXCLUDE, read-side.** Mixed-source: neither leg is a leg of the same
  normalised pair as the other, so no repair direction exists in either direction and the directive's
  "structurally certain" condition is not met.

---

## ITEM 2 — `baseball/quantity` MECHANISM NAMED: a 0.5000 placeholder on 30.9% of the cell

The directive set this cell at **16.64 pp over n=6,778**. Two things had to be settled before a
mechanism could be named, and the first was the number itself.

### The 16.64-vs-15.86 discrepancy is TEMPORAL, and that is now measured, not assumed

Three measurements now exist for one cell, and the arbitration matters because a sharded fold and a
whole-range query disagreeing over identical rows would put every number on the re-ranked board in
doubt:

| when | shape | `ece_eligible` | n | `ece_all` | n_all |
|---|---|---:|---:|---:|---:|
| CAL-P093 | whole-range single query | 16.64 | 6,778 | 25.96 | 47,170 |
| CAL-P094 15:59 | `fold_cohort_cell_eligible`, 26 shards | **15.86** | 6,778 | 23.05 | 47,170 |
| CAL-P094 16:14 | `fold_pairclass_ece`, 45 shards, different shape | **15.86** | 6,778 | — | — |
| CAL-P094 now | `fold_arbitrate_bbq_sharded`, 16 shards | **15.86** | 6,778 | — | 47,170 |

**Both ECEs moved while BOTH denominators stayed byte-identical** (6,778 and 47,170). Same rows,
different prices — so the probability column was rewritten, not the population. Confirmed
mechanically: **6,770 of the 6,778 eligible legs carry a live `calibration_probability`** (only 8
fall back to the write-once `opening_probability`), and the cell's newest leg was touched at
`2026-08-24 23:46 UTC`, minutes before this fold. 16.64 was correct when taken; 15.86 is correct
now; the cell is live and its published ECE drifts under it.

*The single-shot shape is no longer reproducible at all — it answered in 5,374 ms for CAL-P093 and
hits `statement_timeout` at 10 s today (`arbitrate_bbq.json`, `measured: false`, kept as the
negative). So the arbitration was settled by re-measuring, not by re-running.* **Every ECE in this
file is a reading at a timestamp, not a property of a cell.** Dates on the numbers are load-bearing.

### The mechanism: 30.9% of the cell is priced at exactly 0.5000, and it wins 97.6% / 2.4%

Item 1 established that the pair defect explains only 1.18 pp here, leaving the structurally-healthy
coherent `ok` class — n=4,880, 72% of the cell, 13.51 pp at gap **−6.23**. Six checks, on that class:

**1. The sign kills the obvious suspect.** `gap = (Σp − winners)/n`, so −6.23 means the class
**under-prices its winners**. A `calibration_probability` rewritten after settlement would drag
prices *toward* the known outcome and make the gap POSITIVE. Hindsight contamination is refuted by
the sign, even though it is mechanically available (6,770 live legs, touched minutes ago).

**2. A leg swap predicts that sign — and is invisible to item 1's gate.** If Over and Under prices
are exchanged, the pair still sums to 1.0000 and passes every coherence check, while each leg carries
its own complement. Tested with item 1's instrument (`fold_leg_swap.py`, coherent class only,
truth-eligible, 0 irreducible):

| column | leg | n | mean p | win rate | gap | corr(p, win rate) |
|---|---|---:|---:|---:|---:|---:|
| `opening_probability` | over | 2,438 | 0.3858 | 0.1715 | **+21.44** | **−0.583** |
| `opening_probability` | under | 2,438 | 0.6143 | 0.8285 | **−21.43** | **−0.584** |
| published (`COALESCE`) | over | 2,438 | 0.2992 | 0.1715 | +12.77 | −0.036 |
| published (`COALESCE`) | under | 2,438 | 0.5757 | 0.8285 | −25.28 | −0.646 |

The two opening gaps are exactly equal and opposite, as one-winner coherent pairs require — a
built-in check that the fold is measuring what it claims. **Both legs are ANTI-correlated with their
own outcome (−0.58).** A published price that is anti-correlated with reality is worse than a useless
one. But it is not a swap: a swap would show Over rising while Under falls, not both falling.

*(Note the published Over/Under means sum to 0.875, not 1. The pair is coherent at OPENING and
incoherent once published — `calibration_probability` is written per leg with no pair constraint, so
item 1's gate protects the opening and nothing protects the published number. Separate defect,
recorded, not fixed here.)*

**3. Bin 5 is 47% of the class and its outcome is 94/6.** On openings, `over` bin 5 holds n=1,119 at
mean 0.5044 winning **3.84%**; `under` bin 5 holds n=1,184 at mean 0.5072 winning **93.92%**. 2,303
of 4,876 legs priced at a coin flip against a near-certain outcome.

**4. It is a SPIKE at one value, not a spread of near-even quotes** — and a mean of 0.504 cannot tell
those apart, only the value distribution can (`fold_coinflip_default.py`, 357 distinct values, 0
irreducible):

| leg | opening value | n | share of class | win rate | `cal == open` |
|---|---:|---:|---:|---:|---:|
| under | **0.5000** | 924 | 18.9% | **0.9762** | 704/924 |
| over | **0.5000** | 902 | 18.5% | **0.0244** | 275/902 |
| over | 0.5005 | 52 | 1.1% | 0.0000 | 39/52 |
| under | 0.5005 | 51 | 1.0% | 1.0000 | 33/51 |

**1,826 legs at exactly `0.5000` — 37.45% of the coherent class, a 17× cliff over the next distinct
value.** Its own internal calibration error is **47.59 pp**. Cell-wide the exact-0.5000 predicate
catches **2,092 of 6,778 eligible legs = 30.9%**. This is a forecast the market never quoted, and it
is the most perfectly complementary pair possible — `0.5000 + 0.5000 = 1.0000` — so **item 1's
coherence gate passes every one of them.** That is the gate's blind spot, stated plainly: *"the pair
is coherent" was never evidence that the price is real.*

**5. It is the #1578/#151 phantom FAMILY — but the shipped predicate catches only 6.6% of it.** The
forward writer guard already exists (`_resolve_market_probability_with_source` declines a fabricated
midpoint; its docstring records the census — 179,888 outcomes, the 1,580 graded ones winning 0.13%
while asserting 50%). Attributing these rows to it (`fold_spike_provenance.py`, 0 irreducible):

| verdict under `is_fabricated_midpoint` | n | share | win rate | book |
|---|---:|---:|---:|---|
| `no_book` (both sides NULL) | 924 | 50.6% | 0.9762 | **all 924 are UNDER legs; 0 bid, 0 ask** |
| `wide_book_not_midpoint` | 643 | 35.2% | 0.0047 | all OVER; ask on 643, bid on 14 |
| `tight_book` (spread < 0.20) | 138 | 7.6% | 0.1232 | all OVER |
| **`fabricated_midpoint`** | **121** | **6.6%** | 0.0165 | all OVER |

Two readings, and the split by leg is what separates them. `current_yes_bid`/`current_yes_ask` are
**current** columns on a market that has since resolved, so a non-match is not proof of a non-phantom
— the book may have been overwritten after capture, and that asymmetry runs one way only. But
**every one of the 924 `no_book` legs is an UNDER leg with no book at all**, and that is not a
stale-book artifact: a leg that never had a book never had one. So the mechanism is two-part —

> the **Over** leg takes 0.5 from an untraded market's precomputed price, and the **Under** leg is
> written as its arithmetic complement `1 − 0.5 = 0.5` with no quote of its own.

**The consequence for the fix is concrete: the historical exclusion CANNOT be written on
`is_fabricated_midpoint`,** because the columns that predicate reads no longer support it (6.6%). It
has to be written on the self-evidencing value spike — `ROUND(opening_probability, 4) = 0.5000` on a
two-leg pair — which depends on no column that gets overwritten.

**6. ⚠️ Excluding the spike moves the cell 15.86 → 12.14, NOT 15.86 → 4.16.** Measured
(`bbq_excl_half_spike.json`, n 6,778 → 4,686, gap −7.55 → −4.94): **−3.72 pp, 23.5% of the cell.**
I predicted 4.16 by hand and was wrong, in the direction that flatters the fix, so the arithmetic is
worth spelling out: the spike carries **80.8% of the cell's Σ|err|·n** when scored as its own
cohort, and that figure is true — but **ECE is computed WITHIN bins, and removing a term from the
numerator is not the same operation as recomputing the bins without it.** The spike sits in bin 5
alongside real legs it was partially cancelling; take it out and the survivors show their own error.
Same trap as `soccer/container_member`'s +6.54 in item 1, and the same trap as `gap = 0.00` being
arithmetic. **Never quote a decomposition share as an exclusion delta.**

**Verdict.** `baseball/quantity`'s dominant named mechanism is the **exact-0.5000 placeholder
(#1578/#151 family, forward-guarded, historically un-excluded)** — 30.9% of the cell, 47.59 pp
internally, worth **3.72 pp of the cell's 15.86 on exclusion**. The cell stays **rank 1** afterwards
(impact 87,165 → 42,830 vs soccer/quantity's 31,677), so 12.14 pp over 4,686 legs remains unexplained
and this cell is not closed. Recommended next: the published-column pair incoherence from check 2
(openings sum to 1, published legs sum to 0.875) — a second, unguarded writer.

---

## STATUS 2026-08-24 (CAL-P093) — cells 1, 2, 4, 5 MOVED. The ranking metric itself was the largest defect.

**Mechanism NAMED and it is SHARED across all four cells measured today**, so they were taken in one
fix exactly as the directive asked. It is not a calibration mechanism at all — it is a **population**
mechanism, which is why the six-check ladder kept finding real-but-secondary things above it:

> **This file ranks cells by an ECE computed over rows the published curve ALREADY EXCLUDES.**
> The cohort-cell census filters on `source/status/market_type` only. `precompute_calibration`
> additionally requires `resolution_source IN CALIBRATION_TRUTH_ELIGIBLE_SOURCES` — the legs whose
> winner was established INDEPENDENTLY of the market's own price. Nothing was wrong with the census
> (it faithfully mirrors `GET /api/admin/cohort-provenance-split`); the queue was ranked on it.

**The single largest block, executed:** in `basketball/quantity`, **1,690 markets** graded
`resolution_source = 'pass2_loser'` are priced coherently (mean pair sum **0.9954**) and carry
**ZERO winning legs** — a resolved two-leg mutually-exclusive market in which nothing won. They alone
contribute **12.92 pp** of the cell's 24.27. `basketball/container_member` carries the same shape at
966 markets / 14.64 pp. This is the known `#754`/gotcha-#21 poison class, already curve-excluded, and
it was never excluded here. **Not re-graded** (gotcha #21) — reported out, left where it sits.

### MEASURED DELTA — same predicate, eligibility filter the only difference (all executed 2026-08-24)

| cell | census ECE (n) | truth-eligible ECE (n) | **delta** | eligible share | fp (eligible) |
|---|---:|---:|---:|---:|---|
| 1 basketball/quantity | 24.27 (13,067) | **5.73** (2,104) | **−18.54 pp** | 16.1% | `87457dc29c0c74d5` 1,290 ms |
| 4 basketball/container_member | 28.73 (7,161) | **6.65** (262) | **−22.08 pp** | 3.7% | `dfc9f3c805a90083` 3,875 ms |
| 5 baseball/quantity | 25.96 (47,170) | **16.64** (6,778) | **−9.32 pp** | 14.4% | `2d93a44ea9fb6022` 5,374 ms |
| 2 baseball/container_member | 27.08 (18,215) | **12.44** (286) | **−14.64 pp** | 1.6% | `87eda0317190a3a7` 3,873 ms |

Cell-1 census reproduction is EXACT before the filter: `ECE 24.27 / n 13,067 / gap +3.00`
(fp `1c27a01bf22e3f77`, 4,424 ms) — the delta is the filter and nothing else. The n columns here are
grade-unrestricted, so they sit slightly above this file's `n_complete`; the deltas are computed
within one predicate and are unaffected.

**Read the n column, not just the ECE column.** Eligible share is 1.6–16.1%. These cells did not get
better; **most of what they were measuring was never on the curve.** A reader who takes −22.08 pp as
an improvement has made the datagolf card's mistake (`0 outcomes · 0.0pp ECE` rendering as perfect).

### Fix shipped — `8c2cefd6`, read-side, additive, no writer touched

`ece_eligible` / `n_eligible` / `gap_eligible` / `eligible_share` added to the census as a SECOND
twin axis beside the existing grade twins. Eligibility is a **projected column** in leg B, never a
`WHERE`, so `ece_all` / `ece_venue` / `ece_complete` / `ece_incomplete` are byte-identical and parity
with the provenance-split endpoint holds (asserted by test). Schema `v1 → v2` so a persisted v1
checkpoint is refused rather than resumed into a 5-part fold. 14 new tests + 55 in the census
suites, all green. **Rank future rounds by `ece_eligible × n_eligible`, never by `ece_all`.**

### The other four ladder checks, since they were run and two are REAL residuals

* **fallback (check 1) — REAL, secondary.** Unbiased `fallback_share` 14.3% in cell 1. Its damage is
  10.36 pp, and it is a *symptom* of check 3.
* **shape semantics (check 3) — REAL, and it is the cause of check 1.** 13,803 of 13,807 graded
  cell-1 markets are 2-leg Over/Under pairs, yet `avg_sum_prob = 0.632`. Cross-tab: when **both**
  legs carry `calibration_probability` the pair sums to **1.00** (n=3,730 markets); when one does,
  **0.207**; when neither, **0.017** (fp `014a3e8dadd040ad`). Sampled pairs show both legs carrying an
  **identical** `opening_probability` rather than complements — the Over leg's price copied onto the
  Under leg (`Purdue/UCLA O/U 143.5`: Over 0.040 / Under 0.040, Under wins). The census's
  `COALESCE(calibration_probability, opening_probability)` then prices a ~82%-winrate Under leg at
  ~1%. **This survives the eligibility filter partially** (512 eligible outcomes in baseball/quantity
  are still calib-partial, ECE 22.09) and is the next named item.
* **grading truth (check 5) — REAL, and it is what the eligibility filter removes.** 100% of the
  zero-winner and two-winner markets in cell 1 carry ineligible sources (`pass2_loser`, `(null)`,
  `clean_resolution`, `pass3_threshold`). The eligibility predicate — designed for a *different*
  reason, price-independence — captures the entire winner-count defect exactly. That coincidence is
  itself evidence the predicate is the right one.
* **de-vig (check 2), capture-age/hindsight (check 4), binning floor (check 6) — NOT the dominant
  term for these cells.** The residual after eligibility is 5.73 / 6.65 / 12.44 / 16.64 pp, all still
  over the 3 pp bar, so they remain open — but they are now the *whole* remaining question rather
  than 20% of it. `baseball/*` residuals are 2× basketball's and are the next cells to work.

### What this does NOT claim

It does not claim the published curve is wrong, and it does not move the published curve at all —
the excluded rows were already excluded there. It claims **this file's ranking** was wrong, and that
every cell below must be re-ranked on `ece_eligible` before more mechanism work is spent on it. The
remaining 11 cells have NOT been re-measured; their `ece_c` column is still the old metric.

---

## Round 2 — bias fixed, contradiction resolved, hockey via flattened walk (EXECUTED at 4eb2a725)

**Sample bias — NAMED AND FIXED:** Round 1's 500-market pages were the HEAD (`ORDER BY id ASC LIMIT 500`) = oldest markets. That is biased: oldest markets have calib backfilled, newest are sparse. Round 2 uses **random Bernoulli `random() < 0.04 LIMIT 500` (unbiased, heap scan, no sort)** and **unordered `LIMIT 500` (heap-order, no pkey walk)** for sparse cells, bias stated per number. Head vs random side-by-side below proves bias.

**Contradiction — RESOLVED with both queries side by side, same definition, same population type:**

| cell | query | n | fallback | fallback_share | avg_abs_diff (price VALUE) | fp/dur | bias |
|---|---|---:|---:|---:|---:|---|---|
| basketball/quantity HEAD (oldest 500) | `ORDER BY id ASC LIMIT 500` → `ANY` | 370 | 0 | **0.000** | 0.173 | `179bbf 28ms` / `23d760 381ms` [basketball_quantity_head_fallback.json, basketball_quantity_head_pricevalue.json] | **biased old** — oldest ids have calib backfilled to 100% |
| basketball/quantity RANDOM (Bernoulli 4%) | `random()<0.04 LIMIT 500` → `ANY` | 574 | 85 | **0.148** | 0.074 | `c133ef 289ms` / `8c0e60 21ms` [basketball_quantity_random_fallback.json, basketball_quantity_random_pricevalue.json] | **unbiased** — matches calibration 14–18% [census 14-18% on full cell] |

**Resolution:** Same definition (`calibration_probability IS NULL`), same table, different sample. Head sample is 0% because it is oldest 500; random sample is 14.8% and **reproduces calibration's 14–18%**. Round 1's 0% was sample bias, not population truth. Calibration is correct; round 1 head is biased. Both queries stored side by side. *(This paragraph was a ninth row inside the table above until 2026-08-24; a two-pipe row in a nine-column table breaks the render, so the table showed one data row and swallowed the resolution. Content unchanged.)*

**Hockey 29σ cell — flattened walk, not re-derived pagination:** Deployed #1978 worker's flattened-id-walk is `SELECT id FROM futures_markets WHERE status='resolved' LIMIT 500` unordered (heap, no `ORDER BY id` pkey walk). `ORDER BY id LIMIT 500` walks pkey filtering 59M ids for 1304 sparse hockey markets → `statement_timeout` [hockey_ordered_roster.json, `f7c8c763` timeout, 10s]. Unordered `LIMIT 500` succeeds heap-order in 14K/~~? [hockey_unordered_roster.json, 500 rows, 14K] with `fallback 145/584 = 24.8%` [hockey_unordered_fallback.json, `a8db30 173ms`]. Worker pattern is `LIMIT` without `ORDER BY` + `truncated` assertion, or bisection below 25 ids if heap still timeouts — bisection not needed here because unordered succeeded. **Reuse deployed pattern; bisection only if unordered genuinely cannot serve.**

**Other cells — same stratified method applies:** baseball, tennis, etc. now use random Bernoulli 4% for unbiased share; head sample retained only as bias demonstration, not as estimate. All round-2 numbers below state bias per row.


## ⛔ SUPERSEDED 2026-08-24 (CAL-P094) — Scope, 15 cells ranked on `n_complete`

> **THIS TABLE'S ORDERING IS WRONG AND IS RETAINED ONLY AS EVIDENCE. DO NOT WORK IT.**
> `n_complete` counts graded legs; the published curve grades only the **truth-eligible** subset,
> which is 1.6–55% of it depending on the cell. The authoritative board is
> **THE FULL RE-RANKED BOARD** at the top of this file. Nine cells here are four or more places
> out, `hockey/container_member` (rank 6, "WORST true cell") is **unmeasurable** on the real
> denominator, and `tennis/container_member` (rank 14) is **below the bar** at 2.07.
> The per-cell diagnoses and `EXECUTED` numbers below remain valid as measurements of what they
> measured; their *priority* does not.

| ~~rank (n×excess)~~ SUPERSEDED | cell | ece_c | n_c | excess | n×excess | census fp |
|---|---|---:|---:|---:|---:|---|
| 1 | basketball/quantity | 24.27 | 13067 | 21.27 | 277935 | **2026-08-24 MOVED → ece_eligible 5.73 / n 2,104 (−18.54pp), fix `8c2cefd6`. Residual OPEN (shape/de-vig).** |
| 2 | baseball/container_member | 15.62 | 13689 | 12.62 | 172755 | **2026-08-24 MOVED → ece_eligible 12.44 / n 286 (−14.64pp vs 27.08 unfiltered). Residual 12.44 OPEN — worst residual on the board.** |
| 3 | esports/container_member | 5.03 | 78906 | 2.03 | 160179 | 2026-08-24 NOT re-measured — 78,906 rows timed out the 10 s row path in the combined query; needs the `MOD(fm.id, k)` fold. **NEXT.** |
| 4 | basketball/container_member | 25.31 | 6911 | 22.31 | 154184 | **2026-08-24 MOVED → ece_eligible 6.65 / n 262 (−22.08pp). SHARED mechanism with cell 1, taken in the same fix.** |
| 5 | baseball/quantity | 8.42 | 26138 | 5.42 | 141668 | **2026-08-24 MOVED → ece_eligible 16.64 / n 6,778 (−9.32pp vs 25.96 unfiltered). Residual 16.64 OPEN at the largest eligible n on the board — highest-value remaining cell.** |
| 6 | hockey/container_member | 41.00 | 1514 | 38.00 | 57532 | **WORST true cell, NO known mechanism, n<3k but 99% graded** |
| 7 | soccer/container_member | 4.82 | 31478 | 1.82 | 57290 | — |
| 8 | soccer/quantity | 4.67 | 20236 | 1.67 | 33794 | — |
| 9 | economics/quantity | 7.19 | 7103 | 4.19 | 29762 | — |
| 10 | golf/container_member | 10.46 | 3276 | 7.46 | 24439 | — |
| 11 | table_tennis/quantity | 5.84 | 7556 | 2.84 | 21459 | — |
| 12 | politics/quantity | 8.69 | 3289 | 5.69 | 18714 | — |
| 13 | tennis/quantity | 3.47 | 30221 | 0.47 | 14204 | **HIGHEST PRIORITY PER N (30k)** |
| 14 | tennis/container_member | 3.13 | 27349 | 0.13 | 3555 | **HIGHEST PRIORITY PER N (27k)** |
| 15 | hockey/quantity 21.71 n=2062 (monitored), geopolitics/quantity 14.39 n=217 below bar | | | | | |

*Ordered by `n_complete × (ece_complete −3)` — calibration impact. Tennis at 27–30k with 0.13–0.47 excess is top priority per n despite small excess because noise floor is tiny.*

### ⛔ SUPERSEDED — Noise floor per cell, computed on `n_complete`

> **The σ values below are inflated by the wrong denominator** — every one of them divides by a
> population 2× to 60× larger than the graded curve. The live noise table is in
> **THE NOISE FLOOR IS THE SECOND-BIGGEST FINDING OF THE RE-RANK** at the top. Two entries here
> are outright wrong as conclusions: hockey's "29σ, not noise" is 29σ over `n_eligible = 0`, and
> esports cm's "11σ" is **0.3σ** on the real n. The formula is retained because it is the same one
> the new table uses.

For ECE with 10 bins, `SE_ece ≈ 1/√n` (approx, worst-case p=0.5) or `SE_gap ≈ √(p(1−p)/n)`. At 95% (`z=1.96`):

| n | SE (pp) | 2×SE (95%) | 3pp excess in σ |
|---|---:|---:|---:|
| 1514 (hockey) | 1.28 | 2.56 | 38.0/1.28 = 29.7σ — **29σ, not noise** |
| 6911 (bball cm) | 0.60 | 1.20 | 22.31/0.60=37σ |
| 13067 (bball q) | 0.44 | 0.88 | 21.27/0.44=48σ |
| 3276 (golf) | 0.87 | 1.74 | 7.46/0.87=8.6σ |
| 30221 (tennis q) | 0.29 | 0.58 | 0.47/0.29=1.6σ — **borderline, but bar says presumed miscalculated at 30k** |
| 27349 (tennis cm) | 0.30 | 0.60 | 0.13/0.30=0.43σ — **within noise, needs mechanism proof or re-grade** |
| 78906 (esports cm) | 0.18 | 0.36 | 2.03/0.18=11σ |

Every "statistical" claim below cites this table. Tennis cm at 0.13 excess is the only cell where noise alone could explain 3pp.

---

## Executed sample — price-source fallback share (check 1 of 6), 1000-market roster sample per cell

Each cell Round 1: `ORDER BY id ASC LIMIT 500` head sample (biased old) + `ANY` aggregation — bias stated. Round 2: `random()<0.04 LIMIT 500` Bernoulli random (unbiased) or `LIMIT 500` unordered heap for sparse (bias: heap-order) — bias stated per row. See Round 2 table above for basketball head vs random side-by-side. All queries paged ANY pattern, safe.

| cell | roster n (sample) | outcomes n (sample) | has_calib | fallback | fallback_share | avg_prob | winners | avg_calib | avg_open | roster fp/dur | outcomes fp/dur |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| baseball/container_member | 500 | 283 | 283 | 0 | 0.000 | 0.283 | 37 | 0.283 | null | `2766a3e398d8dff8` 1614ms [roster_baseball_container_member.json 500 rows] | `40e5bb65475b33a5` 119.7ms [outcomes_baseball_container_member.json n=283] |
| baseball/quantity | 500 | 4209 | 4190 | 19 | 0.005 | 0.543 | 2429 | 0.542 | 0.843 | `727f5a18568b3bae` 285ms [roster_baseball_quantity.json 500 rows] | `33fc93d28113594b` 384ms [outcomes_baseball_quantity.json n=4209] |
| basketball/quantity | 500 | 364 | 364 | 0 | 0.000 | 0.493 | 191 | 0.493 | null | `de76c95ded78fb81` 808ms [roster_basketball_quantity.json 500 rows] | `31392070f9f04bae` 77.8ms [outcomes_basketball_quantity.json n=364] |
| basketball/container_member | — | — | — | — | — | — | — | — | — | **timeout** `f7c8c7633911ccb8` [roster_basketball_container_member.json 500 `statement_timeout`] | — density trap, needs bisection below 25 ids (worker design) |
| hockey/container_member | — | — | — | — | — | — | — | — | — | **timeout** `f7c8c7633911ccb8` [roster_hockey_container_member.json 500 `statement_timeout` corr 670ba54da805] | — sparse 1304 markets over 10M id range, `ORDER BY id` walks pkey |
| golf/container_member | 500 | 456 | 456 | 0 | 0.000 | 0.365 | 150 | 0.365 | null | `06095b6d6a1d4880` 61ms [roster_golf_container_member.json 500] | `b4403bd7bb110c14` 41.7ms [outcomes_golf n=456] |
| economics/quantity | 500 | 3306 | 3158 | 148 | 0.045 | 0.439 | 1341 | 0.434 | 0.538 | `41e461bc48448b01` 135ms [roster_economics_quantity.json 500] | `e6464ae790a62005` 581ms [outcomes_economics n=3306 fallback 148 share 0.045] |
| esports/container_member | 500 | 291 | 285 | 6 | 0.021 | 0.474 | 103 | 0.470 | 0.665 | `4d78f1521648bdee` 940ms [roster_esports_container_member.json 500] | `8ade5a9137773521` 79ms [outcomes_esports n=291] |
| soccer/container_member | 500 | 603 | 600 | 3 | 0.005 | 0.467 | 285 | 0.465 | 0.977 | `051cad3ec5d46420` 748ms [roster_soccer_container_member.json 500] | `dc033005f6073aed` 124ms [outcomes_soccer_cm n=603] |
| soccer/quantity | 500 | 759 | 757 | 2 | 0.003 | 0.433 | 344 | 0.434 | 0.010 | `4a2bad1c0d116ab0` 506ms [roster_soccer_quantity.json 500] | `655b480dd2fd38a5` 283ms [outcomes_soccer_q n=759] |
| table_tennis/quantity | 500 | 1000 | 1000 | 0 | 0.000 | 0.500 | 36 | 0.500 | null | `02a4b6a74838e20a` 3266ms [roster_table_tennis_quantity.json 500] | `3b51a00c939dfdc5` 178ms [outcomes_table_tennis n=1000] |
| politics/quantity | — | — | — | — | — | — | — | — | — | **timeout** [roster_politics_quantity.json 500 `statement_timeout`] | — sparse 417 markets, needs unordered |
| tennis/quantity | 500 | 58 | 58 | 0 | 0.000 | 0.452 | 21 | 0.452 | null | `dd97667d5eee2b08` 653ms [roster_tennis_quantity.json 500] | `d1bdb465d56a1add` 233ms [outcomes_tennis_q n=58] |
| tennis/container_member | 500 | 86 | 86 | 0 | 0.000 | 0.319 | 12 | 0.319 | null | `5f466f7e9c782e2d` 823ms [roster_tennis_container_member.json 500] | `c47e6fac67da488a` 278ms [outcomes_tennis_cm n=86] |
| geopolitics/container_member | 500 | 591 | 568 | 23 | 0.039 | 0.302 | 186 | 0.283 | 0.763 | `59b82ff0efe18b12` 4050ms [roster_geopolitics_container_member.json 500] | `0ed89a509dfe3171` 138ms [outcomes_geopolitics n=591] |

**Reading:** In the 1000-market samples where outcomes exist, **fallback share is 0.00–0.04** — i.e., almost every outcome has `calibration_probability IS NOT NULL`. This **rules out** the #1978 price-source fallback (using opening where calib missing) as the driver for these cells at this sample. Basketball's known 24pp mechanism must be verified on the full cell with `ece_complete` split: if fallback is rare, the mechanism is not fallback share but **which-price value** (opening vs closing value difference) even when calib exists. See basketball section.

*Every number above cites stored JSON: `artifacts/subcohort2/roster_*.json` (columns [id], row_count, duration_ms, sql_fingerprint) and `artifacts/subcohort2/outcomes_*.json` (columns [n,has_calib,fallback,avg_prob,winners,sum_prob,avg_calib,avg_open], fingerprint, duration_ms). Sample is 1000-market head, not full census — stated inline.*

---

## Per-cell diagnosis — mechanism-ranked, each claim EXECUTED or pending

### 1. hockey/container_member — 41.00pp, n=1514, NO known mechanism [WORST, n=1514]

- **Census:** `ece_complete 41.00, n_complete 1514, graded_share 0.991, gap_complete -6.58` [census.json, measured true, 14 never-graded].
- **Roster:** `SELECT id ... WHERE hockey/container_member ORDER BY id LIMIT 1000` → `statement_timeout` [roster_hockey_container_member.json, `reason statement_timeout`, `correlation 670ba54da805`, `fingerprint f7c8c7633911ccb8`] — **density trap**: 1304 markets sparse over id space, `ORDER BY id` walks pkey filtering (same as tennis/quantity trap in worker design §1). **Not a data absence — a query-shape absence.** Fix: unordered single page + `truncated` assertion or bisection; worker design says bisect on timeout below 25 ids.
- **Fallback sample:** cannot sample until roster succeeds via bisection. From census, `n_complete 1514` at `ece 41` with `gap -6.58` (prob 6pp high vs actual) — if fallback were driver, gap would be opposite sign? Needs price-value check, not share.
- **Next checks (pending bisection):** de-vig — hockey is venue `container_member` (field vs container?); shape — hockey markets are `container_member` (team) not quantity ladder, so sum-to-1 not applicable; capture-age — check `futures_odds_snapshots.captured_at` vs `resolution_date` for hindsight; grading — `resolution_source` is 99% venue (1514/1528), so grading is truth.
- **Noise floor:** SE 1.28pp, excess 38pp = 29σ — **not statistical**, presumed miscalculated per bar. Fix must explain 38pp.
- **Status:** `INCOMPLETE — roster timeout stored, needs bisection page 25 ids` [EXECUTED timeout above]. Fix queue: roster bisection → price-value check → capture-age.

### 2. basketball/quantity — 24.27pp, n=13067 [KNOWN #1978 which-price fallback — VERIFY]

- **Census:** `ece_complete 24.27, n=13067, gap_complete 3.0` [census.json].
- **Sample:** roster 1000 markets → outcomes `n=364 has_calib 364 fallback 0 share 0.000 avg 0.493` [outcomes_basketball_quantity.json, `fp 31392070`, `77.8ms`] — fallback share 0 rules out fallback-share, but #1978 is **which-price value**, not share: even when calib exists, its value may be opening price (wrong capture). Need to compare `calibration_probability` vs `opening_probability` value difference where both exist, and `captured_at` vs `commence_time`.
- **Verify step (pending):** for same 1000 ids, `SELECT AVG(ABS(calibration_probability - opening_probability)) WHERE both NOT NULL` and `SELECT ... JOIN futures_odds_snapshots` for capture-age. Expected post-fix ECE: if price is hindsight/ stale, fixing to venue close should drop 24→~3–5 (estimate, to be measured).
- **De-vig:** basketball `quantity` is points total — not field, so no de-vig; skip.
- **Shape:** quantity is threshold ladder (Over/Under) — cumulative, not exclusive; sum≠1 is correct, no fix.
- **Noise floor:** SE 0.44pp, excess 21.27 =48σ — **not noise**.
- **Status:** `PARTIAL — fallback share 0 EXECUTED, value difference pending` . Fix queue: price-value audit → capture-age.

### 3. basketball/container_member — 25.31pp, n=6911 [KNOWN #1978]

- **Census:** `ece_complete 25.31, n=6911, gap 0.26` [census.json].
- **Roster:** same density trap as hockey — `statement_timeout` on `ORDER BY id LIMIT 1000` [roster_basketball_container_member.json, `670ba54da805`]. Needs bisection.
- **Status:** `INCOMPLETE — roster timeout, needs bisection` . Same price-value verification as quantity.

### 4. baseball/container_member — 15.62pp, n=13689 [#1990 KXMLBKS contamination test — ROUND 2 RANDOM SAMPLE shows KXMLBKS rare]

- **Census:** `ece_complete 15.62, n=13689, ece_all 20.08` [census.json].
- **Sample:** 1000 markets → `n=283 has_calib 283 fallback 0 avg 0.283` [outcomes_baseball_container_member.json, `40e5bb`, `119ms`] — fallback 0, so not price-share.
- **KXMLBKS test — ROUND 2 RANDOM 500 EXECUTED:** `random()<0.04 LIMIT 500` → `kcount 0/500` [round2/baseball_cm_random_roster.json], `k_total 0 of 1000 outcomes` [round2/baseball_cm_k_detail.json], `k_markets 0 of 715` [round2/baseball_cm_k_outcomes.json]. **Finding:** In unbiased random 500, KXMLBKS appears 0 — 95% upper bound <0.6% prevalence. **How much survives once those rows are excluded?** All of it — exclusion does nothing in this sample, ECE 15.62 survives. Either KXMLBKS is not in `external_id` substring, or contamination is not 30% as hypothesized. Next: run `SELECT COUNT(*) FILTER (WHERE external_id LIKE '%KXMLBKS%')` over full cell via ANY-paged count, not sample, and check market name pattern.
- **Status:** `EXECUTED — KXMLBKS rare in random sample (0/500), ECE 15.62 survives exclusion in this sample` .


### 5. baseball/quantity — 8.42pp, n=26138 [#1990]

- **Sample:** `n=340 has_calib 325 fallback 15 share 0.044 avg 0.48` — small fallback 4%, not driver.
- **KXMLBKS:** same test as cm, but quantity should have fewer KXMLBKS (quantity is runs, not team). Pending.
- **Status:** `PARTIAL` .

### 6. golf/container_member — 10.46pp, n=3276

- **Sample:** `n=118 has_calib 118 fallback 0` — no fallback.
- **Shape:** golf is field (players) — exclusive container, sum-to-1 applies; check `SUM(prob) per market_id` histogram. If sum≈2.5, de-vig missing. Pending.
- **Status:** `PARTIAL` .

### 7–12. esports/cm 5.03 (n=78906), soccer/cm 4.82 (31478), soccer/q 4.67 (20236), economics/q 7.19 (7103), table_tennis/q 5.84 (7556), politics/q 8.69 (3289)

- **Census:** all >3pp with n≥3k, excess 1.6–5.7, n×excess 18k–160k. Noise floor 0.18–0.60, excess 8–11σ — **not noise** except table_tennis q at 2.84 excess vs SE 0.58 =4.9σ still significant.
- **Samples:** pending same ANY pattern. Economics 1000-sample already: `n=98 has_calib 98 fallback 0` — no fallback.
- **Status:** `PENDING — samples scheduled` .

### 13. tennis/quantity — 3.47pp, n=30221 [HIGHEST PRIORITY PER N — RANDOM SAMPLE EXECUTED]

- **Noise floor:** SE 0.29pp, excess 0.47 =1.6σ — borderline but n=30k makes it real per bar (presumed miscalculated). Need mechanism proof, not statistical shrug.
- **Census:** `ece_complete 3.47` just over 3, but `ece_all 24.71` — huge gap vs complete suggests grading contributed but ece_complete still over bar.
- **Head 500 (biased old):** `n=58 has_calib 58 fallback 0` [outcomes_tennis_quantity.json, head 500] — head shows 0% fallback, but head is oldest 500 biased.
- **Random 500 (Bernoulli 4% unbiased):** `n=855 fallback 26/855 = 3.0%` [round2/tennis_quantity_random_fallback.json `0d6627 282ms`], `avg|calib−opening| where both NOT NULL` pending but random fallback 3% vs head 0% shows head bias underestimates fallback, though still far below 14% basketball level. Random is unbiased estimate.
- **Status:** `EXECUTED — random 3.0% fallback, head 0% shows bias, not yet 14% driver` .


### 14. tennis/container_member — 3.13pp, n=27349 [HIGHEST PRIORITY PER N — RANDOM SAMPLE EXECUTED]

- **Noise floor:** SE 0.30pp, excess 0.13 =0.43σ — **within 2σ**, so statistical alone could explain. But bar says presumed miscalculated at 27k, and `ece_all 24.04` vs `ece_complete 3.13` shows grading contributed.
- **Head 500:** `n=86 has_calib 86 fallback 0` [outcomes_tennis_container_member.json] — head 0%.
- **Random 500 (Bernoulli 4% unbiased):** `n=935 fallback 14/935 = 1.5%` [round2/tennis_cm_random_fallback.json `506faf 346ms`], `avg|calib−opening|` pending — random 1.5% vs head 0%, still low. At n=27349, 0.13pp excess is within noise, so **provisionally statistical** unless shape/price proves otherwise — per bar, need mechanism proof to convince otherwise, but noise calculation supports statistical for this cell.
- **Status:** `EXECUTED — random 1.5% fallback, within noise, presumed statistical pending shape check` .


---

## ⛔ SUPERSEDED 2026-08-24 (CAL-P094) — Fix queue ordered by `n_complete × excess`

> **This is the same wrong ordering as the scope table, with proposed fixes attached, so it is the
> more dangerous of the two — a reader can act on it.** The queue is
> **THE FULL RE-RANKED BOARD** at the top of this file. Three specific rows here are now known to
> be misdirected work: row 3 (esports cm) is measured at **3.15pp / 0.3σ** and needs no mechanism;
> row 6 (hockey cm, "must beat 29σ") has `n_eligible = 0` and cannot be measured at all; row 14
> (tennis cm) is **below the bar**. The `EXECUTED` evidence in the `cites` column stands.

| ~~order~~ SUPERSEDED | cell | n_c | excess | n×excess | mechanism (ranked) | proposed fix | expected ΔECE | cites |
|---|---|---:|---:|---:|---|---|---|---|
| 1 | basketball/quantity | 13067 | 21.27 | 277935 | price-value (#1978) — fallback share 0 EXECUTED, value pending | audit `calibration_probability` vs `opening_probability` + `captured_at` vs `commence_time` for hindsight, fix to venue close price | 24→~3–5 (pending measure) | census.json, outcomes_basketball_quantity.json `31392070` |
| 2 | baseball/container_member | 13689 | 12.62 | 172755 | KXMLBKS contamination (#1990) — fallback 0 EXECUTED | quantify KXMLBKS share via `kxmlbks_baseball_cm.json`, exclude KXMLBKS zero-winners, recompute ECE_complete without them | 15.6→~5 if contamination, else price-value | outcomes_baseball_container_member.json `40e5bb` |
| 3 | esports/container_member | 78906 | 2.03 | 160179 | pending — sample shows ? | shape/capture-age pending | 5.0→~? | census |
| 4 | basketball/container_member | 6911 | 22.31 | 154184 | price-value (#1978) — roster timeout, needs bisection | same as basketball/q | 25→~3–5 | roster timeout `670ba54` |
| 5 | baseball/quantity | 26138 | 5.42 | 141668 | KXMLBKS — sample fallback 0.044 | same KXMLBKS test on quantity | 8.4→~? | sample fallback 15/340 |
| 6 | hockey/container_member | 1514 | 38.00 | 57532 | **UNKNOWN — NO known mechanism, 29σ** | roster bisection → price-value → capture-age → grading | 41→? (must beat 29σ) | roster timeout `670ba54` |
| 7 | soccer/container_member | 31478 | 1.82 | 57290 | pending | shape pending | 4.8→? | census |
| 8 | soccer/quantity | 20236 | 1.67 | 33794 | pending | — | 4.6→? | census |
| 9 | economics/quantity | 7103 | 4.19 | 29762 | pending — sample fallback 0 | — | 7.1→? | outcomes_economics 440B |
| 10 | golf/container_member | 3276 | 7.46 | 24439 | pending — sample fallback 0, shape check next | sum-to-1 histogram | 10.4→? | outcomes_golf |
| 11 | table_tennis/quantity | 7556 | 2.84 | 21459 | pending | — | 5.8→? | census |
| 12 | politics/quantity | 3289 | 5.69 | 18714 | pending — sparse cell, needs unordered | — | 8.6→? | census |
| 13 | tennis/quantity | 30221 | 0.47 | 14204 | **HIGHEST PER N** — random 3.0% fallback (unbiased) vs head 0%, density trap bisection not needed (random succeeded) | random Bernoulli 4% → price-VALUE → shape | 3.47→~3.0 if noise else price fix | round2/tennis_quantity_random_fallback.json `0d6627` |
| 14 | tennis/container_member | 27349 | 0.13 | 3555 | **HIGHEST PER N but within noise** — random 1.5% fallback, 0.43σ | verify shape, presumed statistical | 3.13→~3.0 statistical | round2/tennis_cm_random_fallback.json `506faf` |

*Every row will be updated with EXECUTED fix-Δ after price-value and KXMLBKS quantifications. Findings route to calibration; no DDL here.*

## Stored outputs — every number cites

- Census: `artifacts/subcohort2/census.json` (49 cells, `ece_complete`, `n_complete`, `ece_all`, `n_all`, `graded_share`, roster/aggregate at 4eb2a725)
- Roster: `artifacts/subcohort2/roster_*.json` (columns [id], row_count, `duration_ms`, `sql_fingerprint`, `truncated`) — hockey/basketball_cm timeouts `f7c8c7633911ccb8` `statement_timeout` stored; baseball/basketball_q/golf/economics successes stored.
- Outcomes: `artifacts/subcohort2/outcomes_*.json` (columns [n,has_calib,fallback,avg_prob,winners,sum_prob,avg_calib,avg_open], `sql_fingerprint`, `duration_ms`) — baseball_cm `40e5bb` 119ms, basketball_q `31392070` 77ms, etc.
- KXMLBKS: `artifacts/subcohort2/roster_baseball_cm_ext.json` + `artifacts/subcohort2/kxmlbks_baseball_cm.json` (external_id LIKE '%KXMLBKS%')
- Noise floor: calculation `SE=√(p(1-p)/n)` with `z=1.96`, table above — not a shrug, a number.

