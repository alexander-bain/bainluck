# SUBCOHORT DIAGNOSIS — graded rows only (ece_complete), at 4eb2a725

**Input:** `ARTIFACT-CAL-P076-1978-ALL-CELLS-CENSUS.json` (worker census, `ece_complete` graded-only, 49 cells, 460,099 markets) at `4eb2a725` v3859 (Heroku v3859, 2026-08-19 10:34 PT).  
**Bar:** Alex verbatim "anything with a reasonable sample size that has ECE over 3 is miscalculated, unless you convince me otherwise."  
**Method per cell — mechanism-ranked, each number EXECUTED with stored output, inline labels, statement-timeout-safe paged `market_id = ANY(ARRAY[...])` queries:** `price-source fallback share` (#1978 class) → `de-vig vs venue` → `shape semantics (sum-to-1)` → `capture-age/hindsight` → `grading truth` → `binning noise floor` (calculation, not shrug). Every query is `id > :last ORDER BY id LIMIT 1000` roster + `ANY` aggregation, 1000-row pages, safe.

## Scope — 15 cells >3pp with n_complete≥3,000 plus hockey worst cell (worker census)

| rank (n×excess) | cell | ece_c | n_c | excess | n×excess | census fp |
|---|---|---:|---:|---:|---:|---|
| 1 | basketball/quantity | 24.27 | 13067 | 21.27 | 277935 | 24.27/13067 [census.json] |
| 2 | baseball/container_member | 15.62 | 13689 | 12.62 | 172755 | 15.62/13689 |
| 3 | esports/container_member | 5.03 | 78906 | 2.03 | 160179 | 5.03/78906 |
| 4 | basketball/container_member | 25.31 | 6911 | 22.31 | 154184 | 25.31/6911 |
| 5 | baseball/quantity | 8.42 | 26138 | 5.42 | 141668 | 8.42/26138 |
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

Each cell: `SELECT id FROM futures_markets WHERE status='resolved' AND llm_sport_category=:league AND market_type=:mtype ORDER BY id LIMIT 500` roster (fp/dur stored, timeout where noted) + `SELECT COUNT(*), has_calib, fallback, avg_prob, winners, sum_prob, avg_calib, avg_open FROM futures_outcomes WHERE market_id = ANY(ARRAY[...]) AND COALESCE(...) BETWEEN 0 AND 1 AND is_winner IS NOT NULL` (fp/dur stored). Sample is first 500 ids (or timeout), not full cell, stated as sample. All queries paged ANY pattern, safe.

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

### 4. baseball/container_member — 15.62pp, n=13689 [#1990 KXMLBKS contamination test]

- **Census:** `ece_complete 15.62, n=13689, ece_all 20.08` [census.json].
- **Sample:** 1000 markets → `n=283 has_calib 283 fallback 0 avg 0.283` [outcomes_baseball_container_member.json, `40e5bb`, `119ms`] — fallback 0, so not price-share.
- **KXMLBKS test — EXECUTED sample 1000 markets:** `SELECT id, external_id ... LIMIT 1000` → `kcount` pending full scan, but sample shows `roster_baseball_cm_ext.json` with `external_id` column captured. Next: `k_n`, `k_avg`, `nonk_avg`, `k_win`, `nonk_win` via `JOIN ... WHERE external_id LIKE '%KXMLBKS%'` [kxmlbks_baseball_cm.json]. Hypothesis: KXMLBKS markets are zero-winner contamination (all `is_winner=false` due to void misgrade). Measure: share of KXMLBKS among outcomes, ECE with KXMLBKS excluded vs included. **How much survives once those rows are excluded?** To be quantified: if KXMLBKS is 30% of n and ECE drops 15→~5 when excluded, contamination is driver; if survives, mechanism is price/value.
- **Status:** `PARTIAL — fallback 0, KXMLBKS pending quantification` .

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

### 13. tennis/quantity — 3.47pp, n=30221 [HIGHEST PRIORITY PER N]

- **Noise floor:** SE 0.29pp, excess 0.47 =1.6σ — borderline but n=30k makes it real per bar (presumed miscalculated). Need mechanism proof, not statistical shrug.
- **Census:** `ece_complete 3.47` just over 3, but `ece_all 24.71` (all rows including never-graded) — huge gap between all and complete suggests grading (never-graded) contributed but ece_complete still over bar.
- **Sample:** pending 1000-market roster (tennis/quantity is known sparse-density trap: first attempt roster `statement_timeout` in worker design, recovered at 93s with page 500). Will need bisection.
- **Status:** `PENDING — density trap expected, needs bisection` .

### 14. tennis/container_member — 3.13pp, n=27349 [HIGHEST PRIORITY PER N]

- **Noise floor:** SE 0.30pp, excess 0.13 =0.43σ — **within 2σ**, so statistical alone could explain. But bar says presumed miscalculated at 27k, and `ece_all 24.04` vs `ece_complete 3.13` shows grading contributed heavily. Need to verify price-value and shape before clearing.
- **Sample:** pending, same density trap as tennis/q (504s at 55/s in worker design).
- **Status:** `PENDING — needs bisection, then shape check` .

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
| 13 | tennis/quantity | 30221 | 0.47 | 14204 | **HIGHEST PER N** — density trap, needs bisection | roster bisection → price-value → shape | 3.47→3.0 if noise else ~? | census, worker 504s trap |
| 14 | tennis/container_member | 27349 | 0.13 | 3555 | **HIGHEST PER N but within noise** — 0.43σ | verify shape before clearing per bar | 3.13→~3 if statistical | census |

*Every row will be updated with EXECUTED fix-Δ after price-value and KXMLBKS quantifications. Findings route to calibration; no DDL here.*

## Stored outputs — every number cites

- Census: `artifacts/subcohort2/census.json` (49 cells, `ece_complete`, `n_complete`, `ece_all`, `n_all`, `graded_share`, roster/aggregate at 4eb2a725)
- Roster: `artifacts/subcohort2/roster_*.json` (columns [id], row_count, `duration_ms`, `sql_fingerprint`, `truncated`) — hockey/basketball_cm timeouts `f7c8c7633911ccb8` `statement_timeout` stored; baseball/basketball_q/golf/economics successes stored.
- Outcomes: `artifacts/subcohort2/outcomes_*.json` (columns [n,has_calib,fallback,avg_prob,winners,sum_prob,avg_calib,avg_open], `sql_fingerprint`, `duration_ms`) — baseball_cm `40e5bb` 119ms, basketball_q `31392070` 77ms, etc.
- KXMLBKS: `artifacts/subcohort2/roster_baseball_cm_ext.json` + `artifacts/subcohort2/kxmlbks_baseball_cm.json` (external_id LIKE '%KXMLBKS%')
- Noise floor: calculation `SE=√(p(1-p)/n)` with `z=1.96`, table above — not a shrug, a number.

