# SUBCOHORT DIAGNOSIS — ranked on `ece_eligible`, re-ranked 2026-08-24 (CAL-P094)

**Ranking metric (authoritative since 2026-08-24):** `n_eligible × (ece_eligible − 3)`. Truth-eligible
rows only — the legs whose winner was established INDEPENDENTLY of the market's own price
(`CALIBRATION_TRUTH_ELIGIBLE_SOURCES`), which is what the published curve actually grades.  
**Ranking source:** `artifacts/cal-p094/eligible_fold_all_cells.json` (22 cells, sargable id-range
fold, 0 irreducible). The historical input `ARTIFACT-CAL-P076-1978-ALL-CELLS-CENSUS.json` at
`4eb2a725` v3859 is retained below as evidence, not as ordering.  
**Bar:** Alex verbatim "anything with a reasonable sample size that has ECE over 3 is miscalculated,
unless you convince me otherwise."  
**Method per cell — mechanism-ranked, each number EXECUTED with stored output:** `price-source
fallback share` (#1978 class) → `de-vig vs venue` → `shape semantics (sum-to-1)` →
`capture-age/hindsight` → `grading truth` → `binning noise floor` (calculation, not shrug).

---

# THE CERT BOARD — one cell, one cert (CAL-P993, 2026-09-03)

> **THIS SECTION IS THE QUEUE.** Everything below the next `---` is the chronological
> investigation stack that produced it, kept as evidence and no longer as ordering. Read this
> table; read a `## STATUS` block only when you need the working for one cell.

**Ranked on the PUBLISHED board, big to small** — `excess_outcomes = (ece − bar) × n`, the amount
of wrongness a cell puts in front of readers. Read live off production with the lane's own
instrument, `backend/scripts/calibration_scorecard.py --live`, against
`generated_at 2026-09-03T04:33:51Z`, `population_version q269`, self-check
`by_category 34/34 · by_source 7/7` reproduced exactly.

**Board state:** `cells_at_bar 34 / 48` · `cells_queued 14` · `queued_excess_outcomes 200,573` ·
headline `mce_closing_line 1.71 pp` (target 2.0, PASS).

**A cell is done when three things are on the record, in this order and no other:**

1. **MECHANISM NAMED** — not a description of the symptom. A named mechanism is one that predicts
   a number before the fold is run.
2. **FIX** — a change, guarded, with a red-first arm.
3. **ECE BEFORE → AFTER, MEASURED ON PRODUCTION AFTER A PUBLISH.** Not a fold of a working tree.
   A fold is what earns a fix its cert; only a published curve closes a cell, because the curve is
   what a reader sees. The two are in different columns below and they never merge.

🔴 **Eleven of the fourteen queued cells have no cert because they have no named mechanism yet.**
That is the honest state of the board and it is written as `—`, not as "in progress".

## The four NAMED cells

| # | cell | mechanism (named) | fix | ece before → after |
|---|---|---|---|---|
| ★ | **polymarket/baseball** | **K′ `is_player_props_placeholder`** — three rules under one predicate: R1 the both-legs-0.5000 half-spike pair, R2 published-pair incoherence (two legs whose prices do not sum to ~1), R3 the props container. Named by CAL-P168; CAL-P119 pre-registered **4.71 → 2.71** | **SHIPPED.** CERT-652 → CERT-662, merged `2aac5843` 2026-09-01 | **4.71 → 2.85 pp** (n 45,252 → 15,496), **measured on production** at q269. **AT BAR.** Prediction 2.71 vs actual 2.85 — corroborated, *not isolated*: q269 also carries D5 de-dup, RULE E, D12 and the `odds_api_bookmaker` writer repair, and the population moved −66% |
| 9 | **polymarket/basketball** (`quantity`) | 🔴 **THE BOARD'S NAMED MECHANISM IS REFUTED.** Rank 6 said "price-value (#1978), fallback share 0 EXECUTED, value pending". Measured: R1's class is **3.00 pp on 180 legs** here — for basketball the half-spike is *not* the mechanism. The real one is a **HALF-BOOK**: Polymarket writes only the Over from a real order book (**1,045 / 1,045 Overs carry a book; 652 / 1,045 Unders never showed a bid or a trade**), `POLY_PLACEHOLDER_EXCLUDE` is a PER-LEG rule, so it deletes 398 bookless Unders and publishes their Over partners alone — **407 orphan Overs at a mean 0.4966 that win 9.8%.** Venue-checked 3/3: the Overs really did lose, so this is not a grading defect | **BUILT, GUARDED, NOT COMMITTED.** C2 pair symmetry (one clause on `POLY_PLACEHOLDER_EXCLUDE`) + `tests/test_calibration_poly_pair_symmetry_992.py` (7 tests, all executing the real SQL). Banked `artifacts/cal-p992/C2-pair-symmetry-SHIPPABLE.patch`, verified to apply to HEAD. **Alex ruled calibration-027 = A.** Blocked on ruling 009 — and, since CAL-P993, on a second thing: see the STOP below | **4.43 → 2.25 pp** (n 7,591 → 7,130, gap +3.17 → +0.88) — **FOLDED through the producer's own chain, NOT on production.** `basketball/field` control moves zero rows. Sub-cohort `quantity` 15.43 → 8.85, gap **−9.45 → −0.35** |
| 9b | **polymarket/basketball** (`container_member`) | Same half-book, same rule, one twentieth of the volume | Rides C2; nothing of its own | 9.99 → 9.53, gap −3.10 → −0.29 (folded). 🔴 **Still 9.53 over a 3.0 bar** — C2 removes the half-book bias and the residual miscalibration of the pairs that DO have two books **is not diagnosed**. This cell is NOT closed by C2 and must not be reported as such |
| — | **polymarket/baseball/quantity** (the spike exclusion, sub-cohort of ★) | R1, the half-spike pair, in the cell where it WAS the mechanism (CAL-P094 measured 924 / 924 no-book Unders) | Shipped inside K′ | Published q269: **6.74 pp on n 5,730**, gap +1.88. ⚠️ **NOT comparable to the board's old `ece_eligible 15.86`** — that column folds the RAW cell (no dedup, no producer exclusions) restricted to truth-eligible rows; this folds what publishes. On basketball the two instruments disagree by 10 pp. **A before/after across them would be a fabrication and is not offered.** The parent cell ★ is the honest before/after |

### 🛑 The STOP on cell 9, found by CAL-P993 and not by the freeze

Lifting ruling 009 does **not** ship C2. The producer cancels roughly **one beat in three**, so the
commit would land and the cell still would not publish — and a cell only closes on a published
curve. Measured 2026-09-03 over the 168-beat ring: **23 beats died mid-unit and 21 of them had a
Heroku release inside their own window**; the last four terminated **16–28 s** after one. Sentry
names the exception `CancelledError()`. It is a deploy cycling `worker-heavy`, not calibration.

Worse, and measured the same night: **the rolling restage cannot converge.** The served bank is
**73% drifted within one hour and 100% drifted within four**; the rebuild that would replace it
banks 5 units a beat and needs ~20 hours for 128. It therefore consumes ~87% of every beat's window
buying a bank that is always fully drifted — and that window is precisely the exposure a deploy
kills. Full working: `PROGRAM-CALIBRATION-REPORT-2.md` CAL-P993, `calibration-028` in alex-inbox.

## The rest of the queue, big to small (live q269)

No cell below has a named mechanism. Listed so the ordering is a fact rather than a memory, and so
the next queue picks the top row rather than the most recently discussed one.

| # | cell | class | ece | n | gap | bar | excess-outcomes | σ | mechanism |
|---:|---|:-:|---:|---:|---:|---:|---:|---:|---|
| 1 | kalshi/entertainment | C | 6.29 | 8,922 | +3.44 | 3.0 | **29,353** | 6.2 | — 🔴 **WENT THE WRONG WAY**: 5.09 → 6.29 at q269. Now the board's largest cell. Undiagnosed |
| 2 | odds_api_bookmaker/basketball_nba | A | 5.18 | 10,186 | +1.03 | 2.5 | 27,298 | 5.4 | — |
| 3 | kalshi/golf | B | 4.10 | 21,085 | +4.00 | 3.0 | 23,194 | 3.2 | — |
| 4 | odds_api_bookmaker/baseball_mlb_preseason | A | 8.24 | 3,253 | −7.67 | 2.5 | 18,672 | 6.5 | — |
| 5 | polymarket/cricket | B | 7.92 | 2,944 | −3.79 | 3.0 | 14,484 | 5.3 | — |
| 6 | polymarket/economics | C | 4.36 | 9,656 | −0.56 | 3.0 | 13,132 | 2.7 | — |
| 7 | odds_api_bookmaker/icehockey_nhl | A | 3.89 | 8,658 | +3.04 | 2.5 | 12,035 | 2.6 | — |
| 8 | odds_api_bookmaker/basketball_wncaab | A | 6.05 | 3,382 | −0.35 | 2.5 | 12,006 | 4.1 | — |
| **9** | **polymarket/basketball** | **B** | **4.43** | **7,591** | **+3.17** | **3.0** | **10,855** | **2.5** | **half-book — C2 built, blocked (above)** |
| 10 | polymarket/golf | B | 5.18 | 4,339 | +3.82 | 3.0 | 9,459 | 2.9 | — |
| 11 | kalshi/tech | C | 10.41 | 1,246 | −8.66 | 3.0 | 9,233 | 5.2 | — |
| 12 | odds_api_bookmaker/basketball_wnba | A | 4.92 | 3,267 | +0.13 | 2.5 | 7,906 | 2.8 | — |
| 13 | polymarket/hockey | B | 7.54 | 1,730 | +1.65 | 3.0 | 7,854 | 3.8 | — |
| 14 | odds_api_bookmaker/basketball_euroleague | A | 5.39 | 1,762 | −4.53 | 2.5 | 5,092 | 2.4 | — |

**Five cells crossed off at q269** and are no longer queued: `polymarket/baseball` (★ above),
`kalshi/economics`, `polymarket/esports` (7.03 → 2.35), `polymarket/soccer`, `kalshi/crypto`.
🔴 Only ★ has an isolated before/after; the other four crossed on a rebuild carrying several ships
at once and **none of them may be claimed by a single cert**.

**`measured_sigma`: 0 of 14 queued cells measured.** No queued cell is currently refuted by the
sigma ledger, so `cells_at_bar_if_applied` equals `cells_at_bar` — the overlay is not flattering
this board.

---

## STATUS 2026-08-31 19:5xZ (CAL-P161) — **CHECK 1 IS NOT "REFUTED" ANYWHERE ON THE TOP OF THE BOARD. IT IS UNMEASURED — THE SAMPLE IT RESTS ON IS BIASED LOW BY A FACTOR WE HAVE ALREADY MEASURED AS ∞ (0.000 → 0.148 ON THE SAME CELL).**

*Executes CAL-P160's board-wide method correction — re-bound every cell's check 1 as
`share × mean |price − outcome|` instead of `share` — from stored artifacts, zero queries. Doing
the arithmetic did not re-close the rungs. It showed the **share input itself is void** for ranks
1, 2, 3 and 4. This overturns CAL-P160's own "strengthened" soccer/cm bound, and it retires the
`fallback share is 0.00–0.04 → ruled out` reading that has stood over this file since round 1.*

### SESSION STATE (measured, `GET /api/admin/calibration-beat-gauges?full=true`)

| gauge | session start (`18:37:31Z`) | session end (`19:42:39Z`) |
|---|---|---|
| `staged:units_banked` / `units_planned` | **65 / 128** — **NOT zeroed**; CAL-P160's Finding A signature did not fire | **70 / 128** |
| `input_fingerprint` | `75faaed6`, unchanged | `75faaed6`, unchanged — **14** straight beats since `06:37Z` |
| `staged:unit_ms_mean` | 217,588 | **186,191** |
| `staged:beats_to_publish` | 9 | 5 |

Published curve unchanged: `mce_closing_line` **1.86 pp**, `generated_at 2026-08-31T04:37:36Z`,
population `q268`. Stale by design; the page is not broken. Hold per D34 remains ON —
`precompute_calibration.py` untouched this session.

Swap still in flight: `heroku pg:info -a bainluck` → `Status: Upgrading Plan: Replacing Primary`,
plan still `Standard 0`, `66.1 GB / 64 GB (103.35%)`. **No folds ran.** Everything below is read
from JSON already in this repo.

### 🟢 FINDING 0 — CAL-P160'S "REFUTED AT THE FIRST MEASURABLE BEAT" IS ITSELF OVERTURNED: IT WAS THE SWAP'S TRANSIENT, EXACTLY AS ITS OWN HONEST BOUND ALLOWED

CAL-P160 pre-registered the test: *"if `unit_ms_mean` returns toward 187,000 the degradation was
the swap's transient; if it holds above 210,000 the prediction is refuted outright."* The
`19:42:39Z` beat is the answer and it is unambiguous:

| gauge | `17:37Z` pre | `18:37Z` degraded | **`19:42Z`** | verdict |
|---|---:|---:|---:|---|
| `staged:unit_ms_mean` | 187,139 | 217,588 | **186,191** | back to baseline — **transient** |
| `staged:unit_ms_worst` | 135,937 | 250,681 | **146,637** | back in the 112–136k band |
| `staged:units_banked` | 60 | 65 | **70** | +5, unbroken |
| `staged:beats_to_publish` | 6 | 9 | 5 | — |

**CAL-P160's Finding B verdict is withdrawn.** One degraded beat during a live primary swap was a
transient, not a trend, and this lane called it a refutation on n=1. *(P159's underlying
prediction is not thereby confirmed: it predicted cost would fall **toward 80,658 ms**. Cost
returned to 186,191 — its pre-swap baseline, 2.3× above the predicted figure. The correct grade is
**NOT YET SUPPORTED**, not "refuted": the upgrade has not settled, so the prediction has still
never been tested under its own stated condition.)*

### 🔴 FINDING 0b — **THE ETA THE HOLD RESTS ON IS WRONG BY ~2.3×. `beats_to_publish` IS NOT AN ETA.**

Every directive since CAL-P158 has quoted `staged:beats_to_publish` as "the producer's OWN
disclosed ETA, not an estimate." **It does not behave like one.** Over the 14 beats on fingerprint
`75faaed6` the bank rose 5 → 70 — **65 units, +5 every single beat, zero exceptions** — while
`beats_to_publish` fell only 9 → 5, and spiked back to 9 mid-run:

```
bank  5 10 15 20 25 30 35 40 45 50 55 60 65 70   (+5, 13/13 intervals)
b2p   9  9  8  8  8  8  7  7  6  5  6  6  9  5   (non-monotonic; fell 4 while 65 units banked)
```

A real remaining-work ETA would have fallen ~13. This one tracks *recent in-beat throughput*, not
remaining work, so it implies **11.6 units/beat** — a rate the producer has never once achieved.

**The empirical clock is the trustworthy one.** 58 units remain at a measured, perfectly linear
+5/beat, over a measured mean beat interval of 60.4 min (`06:37:31Z` → `19:42:39Z`, 13 intervals):

> **≈ 11.6 beats ≈ 11.7 hours → publish ≈ `2026-09-01 07:20Z` ≈ 00:20 PT tonight.**
> Not the ~5 beats the gauge advertises.

This does not change the hold — it changes what the hold *costs*, and that is Alex's call, so it
is filed in `YOUR-TURN.md`. Any future directive quoting `beats_to_publish` as an ETA should quote
`(units_planned − units_banked) / 5` instead and say so.

### 🔴 FINDING A — THE RE-BOUND WAS EXECUTED, AND IT FAILED CLOSED, NOT OPEN

CAL-P160 prescribed `share × mean |price − outcome|`. `mean |price − outcome|` is not stored, so
each cell is bounded at its **maximum**: every fallback leg maximally wrong (`|p−o| = 1`), on the
95% Clopper–Pearson **upper** bound of the sampled share. That is a hard ceiling — no
distributional assumption. Read against `ece_eligible` from `artifacts/cal-p094/eligible_fold_all_cells.json`:

| rank | cell | `ece_e` | `n_e` | sample | share | share↑95 | **ceiling pp** | **ceiling / ECE** |
|---:|---|---:|---:|---|---:|---:|---:|---:|
| 1 | baseball/quantity | 15.86 | 6,778 | **head** | 0.0045 | 0.0070 | 0.70 | 0.04 |
| 2 | soccer/quantity | 8.51 | 5,749 | **head** | 0.0026 | 0.0095 | 0.95 | 0.11 |
| 3 | soccer/container_member | 6.27 | 7,682 | **head** | 0.0050 | 0.0145 | 1.45 | 0.23 |
| 4 | economics/quantity | 5.13 | 4,705 | **head** | 0.0448 | 0.0524 | **5.24** | **1.02** |
| 6 | basketball/quantity | 5.73 | 2,104 | **random** | 0.1481 | 0.1798 | **17.98** | **3.14** |
| 8 | tennis/quantity | 5.01 | 1,512 | **random** | 0.0304 | 0.0442 | 4.42 | 0.88 |
| 9 | baseball/container_member | 12.44 | 286 | **head** | 0.0000 | 0.0130 | 1.30 | 0.10 |
| 10 | golf/container_member | 25.11 | 118 | **head** | 0.0000 | 0.0081 | 0.81 | 0.03 |
| 11 | esports/container_member | 3.15 | 8,217 | **head** | 0.0206 | 0.0443 | **4.43** | **1.41** |

Taken at face value this closes ranks 1–3 hard (≤23% of the cell) and reopens 4, 6 and 11. **Do
not take it at face value. The `sample` column is the whole story.**

### 🔴 FINDING B — THE HEAD SAMPLE IS NOT MERELY BIASED; ITS BIAS HAS BEEN MEASURED, AND IT IS TOTAL

Seven of the nine rows above are `ORDER BY id ASC LIMIT 500` head samples. Exactly one cell on
this board was ever sampled **both** ways, and the two answers do not overlap:

| basketball/quantity | n | fallback | share | artifact |
|---|---:|---:|---:|---|
| **head** (`ORDER BY id ASC LIMIT 500`) | 370 | 0 | **0.0000** | `round2/basketball_quantity_head_fallback.json` `179bbf20e2748d4c` 28.3ms |
| **random** (Bernoulli 4%, unbiased) | 574 | 85 | **0.1481** | `round2/basketball_quantity_random_fallback.json` `c133ef220f2d71f1` 289.8ms |

**The head sample read zero on a cell whose true share is ~15%.** The mechanism is already stated
in this file (line ~969): oldest ids have `calibration_probability` backfilled to 100%, so the
head is the one region of the id space where fallback *cannot* appear. This is not a wide error
bar — it is a sample drawn from the complement of the population of interest. Corroborated in the
same direction, never the other, on all three cells with both reads: tennis/q head 0.000 →
random 0.0304; tennis/cm head 0.000 → random 0.0150; hockey/cm unordered heap 145/584 = **0.2483**.

**Consequence, and it is the finding:** a Clopper–Pearson interval quantifies *sampling* error and
says nothing about *selection* error. Every ceiling in Finding A's table marked `head` is
therefore **not a bound at all** — it is a bound on the wrong population. The correct entry for
those seven cells is **VOID**, not a number.

**How much fallback would each head cell need to explain itself?** `ECE / (max(avg_open, 1−avg_open) × 100)`:

| cell | `ece_e` | `avg_open` (fallback rows) | **required share** | is that reachable? |
|---|---:|---:|---:|---|
| golf/container_member | 25.11 | — | 25.1% | ~ hockey's measured 24.8% |
| baseball/quantity | 15.86 | 0.843 | 18.8% | above basketball's 14.8%, below hockey's 24.8% |
| baseball/container_member | 12.44 | — | 12.4% | **below basketball's measured 14.8%** |
| economics/quantity | 5.13 | 0.538 | 9.5% | **below basketball's measured 14.8%** |
| soccer/quantity | 8.51 | 0.010 | 8.6% | **below basketball's measured 14.8%** |
| soccer/container_member | 6.27 | 0.977 | **6.4%** | **well below 14.8%** |
| esports/container_member | 3.15 | 0.665 | **4.7%** | **well below 14.8%** |

Every required share sits inside the range this project has actually measured on unbiased samples
(1.5% – 24.8%). **Fallback alone can account for any of these cells at a share we have observed
elsewhere on the same table.** Nothing here says it *does*. It says the rung is open.

🔴 **This retires CAL-P160's own soccer/cm bound.** That entry wrote "check 1 refuted **by cost**,
`0.005 × 97.7` ≈ ≤0.5 pp of 6.27" and called the rung closed-by-a-bound. The `0.005` is a head
share on the cell class whose head reads zero when the truth is 0.148. The arithmetic was right;
its input was void. **soccer/cm check 1 is reopened.** The correct statement is: *fallback would
need to be ≥6.4% of soccer/cm legs, and we have never measured soccer/cm on an unbiased sample.*

🟢 **One cell is genuinely closed, and only one.** `tennis/quantity`: unbiased random sample, 95%
upper 0.0442, ceiling 4.42 pp against ECE 5.01 → **0.88×**. Closed — but only under the maximal
`|p−o| = 1` assumption, with no margin. It is the sole check-1 verdict on this board currently
resting on an unbiased measurement.

### 🔴 FINDING C — THE `13.51` DISCRIMINATOR CANNOT RUN FROM STORED DATA, AND ITS PRE-REGISTRATION NEEDS ONE AMENDMENT

`artifacts/cal-p094/pairclass_ece.json` stores **scalars only** (`ece`, `n`, `gap`, `winners` per
class) — no per-bin vectors. CAL-P160's discriminator therefore genuinely requires a query and
stays parked behind the swap. Confirmed, not assumed.

The scalars do carry one structural fact that **amends** the pre-registration. Across every cell,
the `ok` and `identical_noncomp` classes sit at *exactly* `winners = n/2` (soccer/cm ok
2,834/5,668; baseball/q ok 2,439/4,880). That is **definitional, not a finding** — `pairclass`
classifies two-leg pairs, and a well-formed pair contributes exactly one winner. But it has a
consequence: in an exactly-paired class `mean(outcome)` is pinned at 0.5 by construction, so the
class `gap` is **entirely** `mean(price) − 0.5`, i.e. a pair-sum deficit (soccer/cm pairs sum
0.944, baseball/q 0.875), not a directional forecasting bias.

**Amendment:** CAL-P094 rejected the collision partly because the gaps differ (−2.78 vs −6.23).
Under the pairing, differing gaps mean nothing more than *differing pair-sum deficits* — so that
half of CAL-P094's argument is void on a second, independent ground. **But the pair-sum route does
not explain the collision either**: `golf/container_member`'s `ok` class sums to 0.9984 (near
perfect) at ECE **25.11**, while soccer/cm sums to 0.944 at 13.51. Deficit and ECE do not track.
When the discriminator runs it must record the **price histogram** alongside the per-bin error
vector — under exact pairing the error vector is mirror-symmetric, so the price distribution is
the part that actually carries cell identity.

### 🟡 THE CELLS WHERE `ok` IS *NOT* PAIRED ARE A SEPARATE, UNNAMED CLASS

Three `ok` classes break `winners = n/2` badly, and all three have **positive** gap:
`economics/quantity` 1,752/4,705 = 37.2% (gap +4.20), `politics/quantity` 102/1,152 = 8.9%
(+6.12), `geopolitics/quantity` 5/60 = 8.3% (+19.36). These are non-complementary multi-leg
populations misclassified into a class whose name asserts they are clean pairs. **`economics/quantity`
is rank 4 and is also one of the cells Finding A reopened** — two independent signals on the same
cell. Not diagnosed here; recorded so it is not rediscovered a fourth time.

### 🔴 WHAT THIS DOES TO THE NEXT QUERY — A RE-PRIORITISATION, STATED NOT SUBSTITUTED

CAL-P160 pre-registered the per-bin `13.51` discriminator as the next query. **It should now run
second.** The first query, when the swap settles, should be a **Bernoulli-random fallback
re-measure on ranks 1–4** (`baseball/quantity`, `soccer/quantity`, `soccer/container_member`,
`economics/quantity`), reusing the exact pattern already proven on basketball —
`random() < 0.04 LIMIT 500` → `ANY` aggregation, `~290ms` measured, four cheap queries. Rationale:
the collision check refines the *localisation* of a driver inside two cells; the random re-measure
decides whether a **known, already-shipped defect class (#1978) is the driver of the top four
cells at once**, and it is the rung every other rung on this board is stacked on top of. Also
capture `avg(|price − outcome|)` over the fallback rows in the same pass so the next re-bound is
exact instead of a ceiling.

### CARRIED TO THE NEXT SESSION

1. Read the gauge ring first (CAL-P160 Finding A signature — did not fire this session).
2. CAL-P160's Finding B is **graded and withdrawn** (Finding 0). Nothing left open there. The live
   number to carry is the bank and the **empirical** ETA, never `beats_to_publish` (Finding 0b).
3. **Query 1 when the swap settles:** random fallback re-measure, ranks 1–4, + `avg|p−o|`.
4. **Query 2:** the per-bin `13.51` discriminator, amended per Finding C to record price histograms.
5. Check 1's status board-wide: **VOID on 7 cells, OPEN on basketball/q (3.14×), CLOSED on
   tennis/q alone (0.88×).** Do not re-cite "fallback share is 0.00–0.04" — it is retired.

---

## STATUS 2026-08-31 19:3xZ (CAL-P160) — **THE HOLD IS CORRECT BUT ITS STATED REASON IS WRONG: THE BANK IS IN POSTGRES, AND POSTGRES IS BEING REPLACED RIGHT NOW.**

*Agrees with CAL-P159 on the verdict (do not touch the file) and corrects it on two load-bearing
facts. P159 recorded a prediction so it could be graded; this entry grades it, and it is refuted
at the first measurable beat. Rank 3's ladder is advanced four rungs with **zero database load**.*

### SESSION STATE (measured, `GET /api/admin/calibration-beat-gauges?full=true`, beat `18:37:31Z`)

| gauge | value |
|---|---|
| `staged:units_banked` / `units_planned` | **65 / 128** (was 60 when P159 read it at `17:37Z`) |
| `staged:beats_to_publish` | **9** — the producer's OWN disclosed ETA, not an estimate |
| `input_fingerprint` | `75faaed6`, **unchanged across all 13 beats since `06:37Z`** |
| rate | **+5 units/beat**, perfectly linear, 13 consecutive beats |

Published curve unchanged: `mce_closing_line` **1.86 pp**, population `q268`, `generated_at`
`2026-08-31T04:37:36Z`. Stale by design — the bank is mid-rebuild and the page correctly serves
the last complete snapshot.

### 🔴 FINDING A — "THE UNIT BANK IS IN REDIS, SO THE 60 UNITS SURVIVE THE PRIMARY SWAP" IS FALSE

P159 wrote that sentence, and it is the reason the hold was believed safe across Alex's plan
upgrade. **The bank is in PostgreSQL.** `app/tasks/task_checkpoint.py`'s module docstring is
explicit, and explains why Redis was *rejected*:

> *"The checkpoint goes in `durable_state_snapshots` (Queue 298's store), **not Redis**. Redis on
> this project is a 50MB `allkeys-lru` instance running at ~97% of maxmemory — a checkpoint key
> there is not 'persisted with a TTL', it is a key waiting to be evicted."*

**Why this matters, and it is not academic.** `load_checkpoint()` (same file, l.97–121) is
documented *"Any read problem at all yields a fresh checkpoint"* — on any non-`missing` read
status it returns `new_checkpoint(...)` with action `invalidate`. The returned checkpoint is
**empty**. So **one failed Postgres read zeroes the 65-unit bank** — and `heroku pg:info` right
now reads `Status: Upgrading Plan: Replacing Primary`, i.e. a live failover whose defining event
is exactly a dropped connection.

The hold protects the bank from **our deploys**. Nothing protects it from **the swap**, and the
recorded reasoning was wrong in the direction that hid the exposure.

*Not a hazard, checked and cleared:* `CHECKPOINT_MAX_AGE_S = 14 * 86400`. Hours of failed beats
during a swap cannot fossilise the bank. The age rule is not the risk; the read rule is.

**Detection signature for the next session — check this FIRST:**
* log line `checkpoint for <task> not resumable (<status>) — starting fresh`
* gauge signature: `staged:units_banked` collapsing to ~5–7 on a beat, with `input_fingerprint`
  **unchanged** at `75faaed6`. Fingerprint-unchanged is what distinguishes a swap-zeroed bank
  from a deploy-invalidated one — a deploy moves the fingerprint, the swap does not.

### 🔴 FINDING B — P159'S RECORDED PREDICTION, GRADED: **REFUTED AT THE FIRST MEASURABLE BEAT**

P159 predicted: *"once the upgrade settles, per-unit cost should fall toward its former 80,658 ms;
the remaining 68 units then need ~5 beats, not ~14."* Alex started the upgrade at **11:02 PT
(18:02Z)**. The `18:37Z` beat is the first to overlap it. Every number moved the **wrong way**:

| gauge | `17:37Z` (pre) | `18:37Z` (first overlapping beat) | direction |
|---|---:|---:|---|
| `staged:unit_ms_mean` | 187,139 | **217,588** | **+16%** — predicted to fall toward 80,658 |
| `staged:unit_ms_worst` | 135,937 | **250,681** | **+84%** |
| `staged:beats_to_publish` | 6 | **9** | **moved AWAY from publish** |
| `staged:units_this_beat` | 7 | 6 | fewer |

Corroborated independently: `heroku pg:info` reports `Rollback: earliest from 2026-08-31 18:37` —
the rollback horizon was reset at **exactly** the beat that degraded, which is the swap starting
real work. Plan still reads `Standard 0`, `66.1 GB / 64 GB (103.35%)`: **the upgrade has not
settled, and while it is settling the producer is slower, not faster.**

⚠️ **Honest bound: this is ONE beat.** The direction and the mechanism (a replacement primary
streaming WAL competes for the same I/O) are coherent, but a single degraded beat is not a trend.
**The grading completes at the `19:37Z` and `20:37Z` beats** — if `unit_ms_mean` returns toward
187,000 the degradation was the swap's transient and P159's prediction is merely early; if it
holds above 210,000 the prediction is refuted outright.

### 🟢 FINDING C — RANK 3 (`soccer/container_member`) ADVANCED FOUR RUNGS, **ZERO DATABASE LOAD**

Every number below is read from artifacts already stored in this repo. No fold was executed
(see "why no folds ran" below). Cell: **6.27 pp, n=7,682, 5.7σ, impact 25,120.**

| # | check | result | verdict |
|---:|---|---|---|
| 1 | price-source fallback (#1978) | share **0.005** (3 of 603) at `avg_open` **0.977** → worst case `0.005 × 97.7` ≈ **≤0.5 pp of 6.27** | **refuted BY COST, not just by share** |
| 3 | shape / pair coherence | identical pairs are **1,882 of 7,682 (24.5%)** at 19.29 ECE / gap −15.14 — but excluding them makes the cell **WORSE, +6.54 → 12.81** | **present and large, but NOT the driver** |
| 6 | binning noise floor | **5.7σ** | **real, not noise** |
| — | **driver localised** | the structurally-**healthy** `ok` class: **n=5,668 = 73.8% of the cell, at 13.51 pp, gap −2.78** | **this is where the mechanism lives** |

🔴 **A METHOD CORRECTION THAT APPLIES TO THE WHOLE BOARD, NOT JUST THIS CELL.** The check-1
"Reading" paragraph further down this file concludes *"fallback share is 0.00–0.04 — this rules
out the #1978 price-source fallback"*. That conclusion is drawn from **share alone**, and this
lane has already proven twice (CAL-P094 item 1, CAL-P095's spike) that **share is not cost**. The
stored `avg_open` column is the missing half, and it is null exactly when `fallback = 0`, which
means it is the mean opening price **of the fallback rows only** — the rows that actually enter
the curve at that price. Those prices are **degenerate**: soccer/cm **0.977**, soccer/q **0.010**,
baseball/q 0.843, geopolitics/cm 0.763, esports/cm 0.665. A leg entering at 0.977 that loses
contributes ~95 pp of bucket error. **The right statistic is `share × mean |price − outcome|`,
never `share`.**

**Completing that arithmetic here does not overturn the conclusion — it strengthens it.** At
≤0.5 pp of a 6.27 pp cell, fallback is genuinely not the driver for soccer/cm. But the rung is
now closed **by a bound** instead of by an incomplete argument, which is what the ladder needs.
Every other cell's check 1 is closed on the incomplete argument and should be re-bounded the same
cheap way — from stored artifacts, no queries.

🔴 **THE `13.51` COLLISION IS REOPENED — ONE CHEAP CHECK, PRE-REGISTERED.** Rank 1
(`baseball/quantity`) and rank 3 (`soccer/container_member`) **both** put ~72–74% of their mass in
a structurally-healthy `ok` class measuring **13.51 pp**. CAL-P094 ruled this "a 2-decimal
collision, not a shared computation", on the grounds that n differs (4,880 vs 5,668) and gap
differs (−6.23 vs −2.78). **That argument is not airtight.** ECE is |bias| aggregated over bins;
gap is signed mean bias. A shared *upstream binning or rounding* cause would produce matched ECE
with **unmatched** gap — precisely the pattern observed. Two independent cells landing on the same
13.51 is worth one cheap discriminating check, not a closed question, and both are the top of the
burn-down. **Pre-registered discriminator:** compare the two `ok` classes' **per-bin** error
vectors, not their scalars — a shared mechanism matches bin-by-bin, a coincidence does not.

### WHY NO FOLDS RAN, AND WHY THAT IS THE CHARTER AND NOT A GAP

The primary swap is in flight (Finding A). A heavy fold competes for I/O with the producer, and
the producer's failure mode under a failed read is **not a slow beat — it is a zeroed bank**.
Running diagnosis that could destroy the artefact the hold exists to protect inverts the point of
the hold. This is the same call the lane made correctly this morning, and CLAUDE.md LANE ROLES
already says it: *"Heavy measurement queries never run while an attended fold or apply is in
flight."* The ladder was advanced four rungs from stored artifacts instead, and the one query that
would close it is pre-registered above.

### CARRIED TO THE NEXT SESSION

1. Read the gauge ring **first** and check Finding A's detection signature before anything else.
2. Grade Finding B at the `19:37Z` / `20:37Z` beats.
3. Rank 3's driver is the `ok` class; run the pre-registered per-bin discriminator **after** the
   swap settles.
4. `CERT-530` needs nothing — GREEN and **already merged** into master as `cadf104e`.

---

## STATUS 2026-08-31 18:1xZ (CAL-P159) — **NO CELL TAKEN, DELIBERATELY: TAKING ONE TODAY WOULD DESTROY A CURVE DELTA ALREADY PAID FOR.**

*This supersedes the CAL-P158 entry below on mechanism, and agrees with it on the verdict. P158
said "the publisher is down, so nothing can be re-measured." That was right but incomplete, and
the missing half reverses the recommendation from "wait" to "actively do not ship."*

**What the gauge ring says (measured, `GET /api/admin/calibration-beat-gauges?full=true`, beat
`17:37Z`):** `units_done 60 / units_planned 128`, `+5 units/beat`, `unit_ms_mean 187,139`,
`cursor_resume 0`. The producer is **resuming correctly and banking durably.** It is not broken.

**Why it restarted:** the `06:04Z` deploy (v3956/v3957) carried the three curve-affecting D-rules,
all of which edit `precompute_calibration.py`. `_main_input_fingerprint()` hashes the *source* of
`compute_calibration_payload` / `_calibration_population_ctes` / `_main_futures_sql`, so it moved
(`b1820040 → 75faaed6`), and `_load_main_checkpoint()` correctly returned `INVALIDATE`. **The
128-unit bank went to zero and has rebuilt to 60 across 13 beats.**

🔴 **THE CONSEQUENCE FOR THIS FILE'S CHARTER.** A cell rule *is* an edit to those functions — that
is where cell rules live. So landing the top open cell today would move the fingerprint again,
reset 60 → 0, and push the next publish out another ~13 beats. It would also discard the delta
from `67f5a6d3` / `fd033079` / `9c9f7abf` — **already merged, already deployed, never yet
published**, and the dedup-join fix alone de-duplicates 36.65% of published rows. Trading a
banked, paid-for delta for an unmeasurable new one is strictly negative under the finish-line
ruling. **Working "big to small" today means protecting the queue, not adding to it.**

**The unblock is real and it is in flight:** the 187 s/unit is Postgres `standard-0` at **103.3%
of cap (66.1/64 GB)**; Alex started the plan upgrade at **11:02 PT today** (v3958/v3959). The unit
bank is in **Redis**, so the 60 units survive the primary swap.

**Prediction, recorded now so it can be graded:** once the upgrade settles, per-unit cost should
fall toward its former `80,658 ms`; the remaining 68 units then need **~5 beats, not ~14**. The
next published census should carry the three pending fixes. **Resume the burn-down at the first
census with `generated_at` after the upgrade — and take rank 1 (`polymarket/baseball`) then, not
before.**

---

## STATUS 2026-08-31 (CAL-P158) — NO CELL TAKEN, AND THAT IS THE FINDING: **THE PUBLISHER HAS BEEN DOWN FOR 12 HOURS, SO NO CELL FIX CAN SHOW A PUBLISHED DELTA.**

*This entry exists to answer the charter's own question — the file went five days without an
update; which reading is true? **Neither cleanly — it is a blend, and the second half is the
defect.** `git log` on this file: last commit `ee25e1cd` (2026-08-25, CAL-P095). Most of
CAL-P150→157 is publisher machinery (publish gate, staged-futures cursor, phase budgets,
`is_winner` nullability, instrument rings) and correctly has nothing to say here. **But three
commits on 2026-08-30 are curve-affecting and were never written back to this file** —
`67f5a6d3` (D5: the curve's dedup join grouped on two of its five columns; 36.65% of published
rows were the same outcome twice), `fd033079` (D12: rank 6 deleted, not fixed — the cell called
`crypto` is 99.5% metal), `9c9f7abf` (D13: a lone claim published iff it WON). All three are in
the deployed release v3957. So the write-back discipline this charter asks for did lapse, on
exactly the commits that move the board.*

### THE BLOCKER: the hourly producer has not published since 04:37Z, and cannot get near its own deadline

Measured against production 2026-08-31 16:29–16:40Z (09:29–09:40 PT).

| fact | value | source |
|---|---|---|
| last successful publish | `2026-08-31T04:37:36Z` | `/api/calibration` `generated_at` |
| served payload age | **42,700 s (11.9 h)** | `cache.age_s` |
| cache status / reason | `stale` / **`main_key_absent`** | `cache` |
| fresh-key TTL | 7,200 s (`_MAIN_CACHE_TTL`) | `precompute_calibration.py:37` |
| fresh key observed gone | `06:38Z` — exactly TTL after the 04:37Z publish | `artifacts/cal-p148/serve-phase-log.jsonl` (`"redis": null`) |
| producer | `beats_missed: 11`, **`stalled: true`** | `/api/calibration` `producer` |
| hourly failure | "futures generation incomplete — units banked, nothing published" | Sentry `7677340087`, **15 events in 24 h**, last 15:36Z |

**The producer is not crashing — it is losing a race it cannot win.** The staged-futures build
banks units durably and resumes, exactly as designed; it simply cannot finish a generation
inside the window its output is allowed to live in:

| quantity | measured | ledger key |
|---|---:|---|
| units planned per generation | **128** | `staged:units_planned` |
| units banked so far | **55** | `staged:units_done` |
| units **completed this beat** | **5** | `staged:units_completed_this_beat` |
| units attempted this beat | 7 (2 cancelled) | `staged:units_this_beat` |
| per-unit mean, completions | 92,265 ms | `staged:unit_ms_mean_completed` |
| per-unit mean, **attempts** | **185,161 ms** | `staged:unit_ms_mean` |
| futures phase budget / beat | 1,188,617 ms | `plan.phases[futures].budget_ms` |
| futures phase **measured floor** | **1,351,045 ms** | `plan.phases[futures].floor_ms` |
| **the build's own estimate** | **`beats_to_publish: 6`** | `staged:beats_to_publish` |

Three numbers decide it:

1. **`floor_ms` (1,351,045) EXCEEDS `budget_ms` (1,188,617).** The futures phase is allocated
   less time than its own measured floor — `budget_basis: measured_elastic_cut`. It is cut
   because the task's soft limit is 1,500 s and futures' floor alone (1,351 s) plus diagnostics
   (124 s) plus sports (5 s) already reaches 1,480 s. There is no headroom left to give it.
2. **A generation is ~6 beats away on the build's own optimistic estimate, ~15 on observed
   throughput** (73 units remaining ÷ 5 completed/beat). Beats are hourly.
3. **The fresh key lives 2 hours.** So even a perfect publish keeps the page fresh for 2 h out
   of every ~6–15 h. **The page is structurally stale most of the time, and no calibration cell
   fix can be shown to move the published curve until this is true no longer.**

### The cancellation policy's own cost model no longer holds

`STAGED_UNIT_MAX_CANCELLATIONS = 2` is documented as costing "at most eight units of an ~18-unit
beat — under half". Observed this beat: **2 cancellations burned 835 s (417,647 ms + 417,175 ms)
of a 1,340 s beat — 62%** — and the beat completed 7 units, not 18. The constant is not wrong;
the measurement it was sized against has moved. It is **not** a livelock: the two cancelled units
differed from the five that completed, so cancellation is load-dependent slowness, not two poison
slots. Convergence is real. It is just slower than the deadline.

### THE SECOND BLOCKER, LATENT BEHIND THE FIRST: the publish gate refuses a completed build

The last time a build actually COMPLETED — 05:37Z, one hour after the last publish — the publish
gate **rejected** it (Sentry `7677836808`):

> population fell **−10.5% (930,149 → 832,872)**, limit −5%, and population_version was not
> bumped (still `'q268'`) — resolution only ADDS outcomes, so a shrink is a lost cohort or a
> changed rule, never elapsed time

This matters because it is **downstream of the throughput problem and therefore invisible**: no
build has completed since, so the gate has not been reached in 11 hours. The moment throughput
is fixed, this is what the build hits next.

`calibration_publish_gate.py:815-865` is explicit that a shrink is excused by exactly one thing —
`if verdict.version_bumped: return verdict`. A matching predicate never excuses it. So the
sanctioned remedy for a deliberate rule change is to bump `CALIBRATION_POPULATION_VERSION`
(`precompute_calibration.py:603`, currently `"q268"`) and, per that constant's own docstring,
ship `COMPATIBLE_PREVIOUS_POPULATION_VERSIONS` **empty** if the methodology moved.

**WHAT IS NOT ESTABLISHED, AND MUST NOT BE ASSUMED.** The tempting story is that yesterday's
freeze-lift batch caused the shrink and simply forgot the bump. **That story is refuted by the
clock:** the 05:37Z rejection ran on **v3955**, and `67f5a6d3` / `fd033079` / `9c9f7abf` are all
NOT ancestors of v3955 — they arrived in v3956 (05:41Z) / v3957 (06:04Z), *after* the rejection.
The gate class also has 51 lifetime events since 2026-08-18, so the shrink is a recurring
condition that predates the batch, not a fresh side-effect of it.

So the −10.5% is **cause-unestablished**, and the candidate it was measured on is already
obsolete: the staged cursor's `input_fingerprint` has moved `b1820040… → 75faaed6…` across the
v3957 deploy, so the next completed build is a *different* candidate whose population nobody has
seen. **Do not bump the version to "fix" this.** A bump discards the 128-unit bank and restarts
from zero (~14 beats by the q268 precedent, ~26 at today's 5-units/beat) — trading a page that is
stale-but-showing-a-curve for one that could be dark indefinitely. The bump is only safe once
throughput is fixed AND a completed build's population has been read and understood. Both
sequencing constraints are the finding; neither is a task to start today.

### Root cause of the throughput half is not in calibration code

`unit_ms` has gone **80,658 ms → 185,161 ms (2.3×)** between the prior measurement and this beat
(`staged:prior_unit_ms` vs `staged:unit_ms_mean`). Production Postgres is **still
`standard-0`** (`heroku addons -a bainluck`, verified 16:35Z) — 4 GB RAM against a ~66 GB
database. The plan upgrade Alex was handed on 2026-08-30 (`YOUR-TURN.md` §1, Step A) **has not
been run**: `heroku data:maintenances:info DATABASE` reports `addon_plan: standard-0` and
`reason: routine_maintenance`, not the changeover.

**Consequence for this file's charter.** "Work big to small until we don't have a problem"
presumes the board can be re-measured after a fix. It cannot right now. The top unclosed cell is
still rank 1 `baseball/quantity`; it is untouched this session **deliberately**, because shipping
a mechanism fix into a pipeline that has not published in 12 hours produces exactly the
activity-without-progress the finish-line ruling forbids. **The next cell gets taken when the
producer publishes again.**

### The cells-at-bar number, corrected

The needle is **31/49**, not the 29 carried in `YOUR-TURN.md` §5 nor the 30 attributed to the
page. Both rails agree and cross-check clean (`calibration_threshold_table.py --payload`, exit 0;
its `agreement()` fails the run if the scorecard disagrees). The 30-vs-29 split was a one-day
disagreement fixed by CAL-P115 and pinned by
`test_calibration_threshold_table_p112.py::test_no_class_is_looser_than_the_reader_bar`. It moved
**29 → 31 overnight** (banked scorecards `20260830T223624` → `20260831T021905`). Headline MCE
**1.86 pp** closing-line, CI [0.84, 1.95] — but on a payload frozen at 04:37Z, so it is 31/49 *as
of yesterday evening*, and cannot advance while the publisher is down.

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

🔴 **RETIRED 2026-08-31 (CAL-P161) — DO NOT CITE THE READING BELOW.** Every row in this table
except the ones marked otherwise is an `ORDER BY id ASC LIMIT 500` **head** sample, and the head
sample has been measured against an unbiased random sample on one cell: basketball/quantity read
**0.000** on the head and **0.1481** on the random draw. Oldest ids have `calibration_probability`
backfilled to 100%, so the head is drawn from the one region of the id space where fallback cannot
appear. These shares are not low-precision estimates of the cell — they are estimates of a
different population. **Treat every head share here as VOID, not as a bound.** See CAL-P161
Findings A/B at the top of this file for the per-cell ceilings, the required-share table, and the
pre-registered random re-measure that replaces this reading.

~~**Reading (VOID):** In the 1000-market samples where outcomes exist, **fallback share is 0.00–0.04** — i.e., almost every outcome has `calibration_probability IS NOT NULL`. This **rules out** the #1978 price-source fallback (using opening where calib missing) as the driver for these cells at this sample.~~ Basketball's known 24pp mechanism must be verified on the full cell with `ece_complete` split: if fallback is rare, the mechanism is not fallback share but **which-price value** (opening vs closing value difference) even when calib exists. See basketball section.

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

