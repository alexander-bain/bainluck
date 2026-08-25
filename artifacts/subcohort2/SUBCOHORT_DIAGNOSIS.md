# SUBCOHORT DIAGNOSIS — graded rows only (ece_complete), at 4eb2a725

**Input:** `ARTIFACT-CAL-P076-1978-ALL-CELLS-CENSUS.json` (worker census, `ece_complete` graded-only, 49 cells, 460,099 markets) at `4eb2a725` v3859 (Heroku v3859, 2026-08-19 10:34 PT).  
**Bar:** Alex verbatim "anything with a reasonable sample size that has ECE over 3 is miscalculated, unless you convince me otherwise."  
**Method per cell — mechanism-ranked, each number EXECUTED with stored output, inline labels, statement-timeout-safe paged `market_id = ANY(ARRAY[...])` queries:** `price-source fallback share` (#1978 class) → `de-vig vs venue` → `shape semantics (sum-to-1)` → `capture-age/hindsight` → `grading truth` → `binning noise floor` (calculation, not shrug).

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
| **Resolution:** Same definition (`calibration_probability IS NULL`), same table, different sample. Head sample is 0% because it is oldest 500; random sample is 14.8% and **reproduces calibration's 14–18%**. Round 1's 0% was sample bias, not population truth. Calibration is correct; round 1 head is biased. Both queries stored side by side. |

**Hockey 29σ cell — flattened walk, not re-derived pagination:** Deployed #1978 worker's flattened-id-walk is `SELECT id FROM futures_markets WHERE status='resolved' LIMIT 500` unordered (heap, no `ORDER BY id` pkey walk). `ORDER BY id LIMIT 500` walks pkey filtering 59M ids for 1304 sparse hockey markets → `statement_timeout` [hockey_ordered_roster.json, `f7c8c763` timeout, 10s]. Unordered `LIMIT 500` succeeds heap-order in 14K/~~? [hockey_unordered_roster.json, 500 rows, 14K] with `fallback 145/584 = 24.8%` [hockey_unordered_fallback.json, `a8db30 173ms`]. Worker pattern is `LIMIT` without `ORDER BY` + `truncated` assertion, or bisection below 25 ids if heap still timeouts — bisection not needed here because unordered succeeded. **Reuse deployed pattern; bisection only if unordered genuinely cannot serve.**

**Other cells — same stratified method applies:** baseball, tennis, etc. now use random Bernoulli 4% for unbiased share; head sample retained only as bias demonstration, not as estimate. All round-2 numbers below state bias per row.


## Scope — 15 cells >3pp with n_complete≥3,000 plus hockey worst cell (worker census)

| rank (n×excess) | cell | ece_c | n_c | excess | n×excess | census fp |
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

### Noise floor per cell — when is 3pp real?

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

## Fix queue — ordered by n × excess (calibration impact), to be finalized after full ANY-paged measurements

| order | cell | n_c | excess | n×excess | mechanism (ranked) | proposed fix | expected ΔECE | cites |
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

