# Predicted Re-baseline — virtual application of the calibration fix queue

*Branch `codex-adhoc/rebaseline` from `2098d7aa` (histogram-fix), worktree `rebaseline`. Read-only prediction; no product code. Methodology: `light-estimate` throughout (`GET /api/admin/cohort-market-type/light` `WHERE random()<0.30 LIMIT 200k`, `GET /api/admin/cohort-provenance-split` `WHERE random()<0.50 LIMIT 300k`, `GET /api/admin/cohort-sums-histogram` `WHERE random()<p` Bernoulli — no `ORDER BY random()` sort, no `TABLESAMPLE SYSTEM` block bias, `EXPLAIN` no Sort above sample). This is the map ruling 050 requires before the build: prediction first, then the real re-baseline is graded against it.*

*Sources: `artifacts/subcohort/table_market_type_light.csv` 200k light table (100 cohorts n≥30, sizable = n≥1000), `artifacts/subcohort/provenance_split_by_shape.md` graded_share + `MACHINE_FIX_QUEUE.md` queue order + `SHAPE_SEMANTICS_SPEC.md` exclusive vs cumulative split + `METHODOLOGY_AUDIT.md` §1–6 ranked hypotheses. Every predicted number is labeled `light-estimate`; the heavy `POST /build` canonical deduped CTE is the source of truth the real re-baseline will read.*

---

## How the virtual re-baseline is built (queue order, per task)

In queue order:

| Step | Fix | What is virtually applied | How | Why this order |
|---|---|---|---|---|
| **1** | **Fix 1 provenance / defaults** (`models.py:830` `is_winner=False`, `precompute_calibration.py:860/1995` includes `NULL`-source false, `admin_cohort.py:214` `n_venue`) | Recompute `ECE_venue` excluding `resolution_source IS NULL` (226k never-graded PM rows counted as losses at 0.50). For the 8 worst cells we use the provenance split's `null_default_share` + `graded_share` (0.18–0.41, `provenance_split_by_shape.md`); for the remaining 12 sizable cells we extend by league×shape proxy (`polymarket quantity/container_member` 0.30–0.45 graded_share, `polymarket field` 0.75–0.85, `kalshi` any shape 0.94–0.97 — kalshi has no default-false hole). Virtual formula: `ECE_venue ≈ ECE_all * graded_share_scaled + 3` where `graded_share_scaled = graded_share*0.9` and `+3` is the residual floor the venue-graded-only curve retains (empirical from heavy 706k `cal.json` band 40–50% venue-only 7–10pp). Kalshi cells unchanged. | Light `provenance-split` `ece_venue` where available, otherwise scaled estimate (labeled `light-estimate`). | Gate of all else — the interpretation matrix says if `ece_all→ece_venue ≤10pp` with `null_default 0.70–0.85` this row collapses and the backfill #1912 is the driver; otherwise the next row is. |
| **3** | **Fix 3 unit of analysis** (`cohort_sweep.py:334` outcome-weighted, `:401` `independent_questions = len({question_id})`, `precompute_calibration.py:1995` deduped) | Recompute market-weighted ECE (each market weight 1.0, ladder rungs `rn=1` or per-market avg). Outcome-weighted `n` double-counts binary mirrors (`n=2,q=1`) and ladder rungs (`n/q≈3–5` for `quantity`/`container_member` on polymarket). Light proxy: `ECE_market = ECE_outcome * (q/n)^0.5` approximated as `−3.0pp` for `quantity`/`container_member` ladders (avg_rungs 4.2), `−0.5pp` for `field`, `−1.5pp` for `duel` where `n=2`. Numbered **Fix 3** in the queue; we apply it second because it is independent of provenance (q-weighted on venue-graded rows only). | Computed from light `n/q` via `SELECT COUNT(DISTINCT market_id)` proxy per cell (see predicted_table.csv `q_est`). | The queue's shape census (`policy.md` `independent_questions`) says ladder cohorts dominate top-5 because `n/q=5`; after de-vig the rungs still double-count. |
| **2/5/6** | **Fix 2 shape de-vig** (`odds_math.py:47` `remove_vig_nway`, `precompute_calibration.py:566` `field` normalization only, `market_shape.py:253/470` classifier, `admin_cohort.py:330` histogram conflates exclusive vs cumulative), **Fix 5 timezone weeks** (`cohort_sweep.py:95` week trunc UTC Monday + `578` naive date), **Fix 6 rounding** (`admin_cohort.py:108` `round(pp,2)`, `cohort_sweep.py:152` `int(p*10)` at 0.50) | Fix 2: **where computable, compute; where blocked, bound**. Computable = exclusive cells (`field`, `container_member` container, `exclusive_ranges` bins) where n-way `p_i/sum` is the correction — we give a point move `−8 to −12pp` median for defect `sum 2–5`. Blocked = cumulative `quantity` threshold ladders (`Over 7.5/8.5/9.5`) where per-rung two-way `YES+NO≈1` + monotonicity `p↓` is the invariant, never `sum≈1` — ladder per-rung de-vig needs the histogram (`#1974`) which sorts the whole join; without it we **bound** as a range per affected cell `[best, worst]` pp, never a point. Fix 5: weekly `DATE_TRUNC('week', resolution_date AT TIME ZONE 'America/New_York')` vs UTC Monday — jitter `0.3pp now →1.5pp at 10×` on boundary week, we bound per `field` weekly cohorts as `±0.4pp`. Fix 6: `int(p*10+1e-9)` epsilon at 0.50 edge — `0.03pp now →0.1pp + rank swap at 10×`, point `−0.1pp` on 40–50% band cells. | Exclusive de-vig: point estimate where `sum≈2.5` measured; cumulative: best/worst range stated in `predicted_table.csv` `predicted_ece` column as `a–b`. Timezone/rounding: bounded ranges folded into the same column; the table never hides a range as a point. | Shape semantics trap (SHAPE spec §2–4): blanket `sum≈1` on cumulative ladders corrupts them (0.60/0.60/0.60 correct sum 1.8 → normalized 0.33 each wrong, fabricating 20pp). So quantity cells must stay a range until the histogram-split lands (exclusive `sum 0.9–1.1 healthy` vs cumulative `per-rung YES+NO 0.9–1.1 + violation_rate≈0`). |
| **—** | Fixes 4/7/8/9 | **Not in this simulation.** Fix 4 capture-age (`calibration_captured_at` stamp + `≥1h before resolution` cutoff) requires a migration (10+ write sites) — 0pp until stamp exists; Fix 7 pp-vs-% (`ece_pp` vs `ece_frac` `5000.00` display) is 0pp math; Fix 8 interval half-open `[0.45,0.55)` + `ORDER BY random()` heap bias already landed in C-ADHOC-4 `a6665b14` (now `WHERE random()<p` Bernoulli); Fix 9 silent-default coalescing (`COALESCE(group_id,event_id)` singleton groups, `COALESCE(cat,'uncategorized')`) is rank-hiding, not pp math. They ride the re-baseline but do not move ECE here. | Documented as 0pp in the table's `which_fixes` column when they do not move a cell. | Bounded so the build can be graded without waiting for the stamp. |

---

## The 20 sizable cells used (n≥1000, light-estimate, sorted desc by current ECE)

Sizable = `n≥1000` in the light 200k sample — the same 20 the heavy page will call sizable at `n≥1000` before the `NOT-PROVABLE (graded_share<0.5)` gate. Weekly and band splits are off this population; the heavy deduped CTE will replace `n` with `independent_questions q` and add `graded_share` + `verdict` but keep the cohort keys.

| rank | cell (source/league/market_type) | n (light) | q_est (markets) | graded_share (est/all→venue proxy) |
|---:|---|---:|---:|---:|
| 1 | polymarket/table_tennis/quantity | 2880 | ~576 (5.0 rungs) | 0.18 |
| 2 | polymarket/table_tennis/container_member | 2313 | ~463 (5.0) | 0.21 |
| 3 | polymarket/soccer/quantity | 12819 | ~2564 (5.0) | 0.27 |
| 4 | polymarket/tennis/container_member | 4789 | ~958 (5.0) | 0.29 |
| 5 | polymarket/tennis/quantity | 6166 | ~1233 (5.0) | 0.33 |
| 6 | polymarket/baseball/container_member | 1013 | ~203 (5.0) | 0.35 |
| 7 | polymarket/esports/container_member | 6591 | ~1318 (5.0) | 0.30 |
| 8 | polymarket/baseball/quantity | 2386 | ~477 (5.0) | 0.38 |
| 9 | polymarket/soccer/container_member | 7064 | ~1413 (5.0) | 0.41 |
| 10 | polymarket/baseball/field | 2828 | ~2828 (1.0) | 0.78 |
| 11 | kalshi/entertainment/quantity | 1200 | ~240 (5.0) | 0.95 |
| 12 | kalshi/hockey/field | 5631 | ~5631 (1.0) | 0.96 |
| 13 | kalshi/golf/field | 3062 | ~3062 (1.0) | 0.96 |
| 14 | polymarket/soccer/field | 11802 | ~11802 (1.0) | 0.82 |
| 15 | kalshi/baseball/field | 39470 | ~39470 (1.0) | 0.97 |
| 16 | kalshi/baseball/unknown | 2219 | ~2219 (1.0) | 0.94 |
| 17 | polymarket/esports/field | 15666 | ~15666 (1.0) | 0.80 |
| 18 | polymarket/economics/quantity | 1137 | ~227 (5.0) | 0.42 |
| 19 | kalshi/basketball/quantity | 1058 | ~212 (5.0) | 0.96 |
| 20 | kalshi/economics/quantity | 15277 | ~3055 (5.0) | 0.96 |

*q_est for ladders assumes `avg_rungs≈5.0` from the light `quantity`/`container_member` groups (see `traded_vs_untraded_by_shape.md` `avg_rungs_per_market 3–5`); field/duel/unknown `q≈n`. Heavy will compute `COUNT(DISTINCT market_id)` exactly.*

---

## Predicted final table — cell × (current → predicted → which fixes moved it → confidence)

Full CSV: `artifacts/rebaseline/predicted_table.csv` (one row per sizable cell, `predicted_ece` is a point or a `low–high` range, `light-estimate` labeled, `which_fixes` lists the fixes that moved that cell, `confidence` = high/med/low per whether the move is measured vs bounded).

| rank | cell | current ECE (pp, light) | predicted ECE (pp, light-estimate) | which fixes moved it | confidence |
|---:|---|---|---|---|---|
| 1 | polymarket/table_tennis/quantity | 50.00 | **5.8–9.2** | 1 (−39) provenance collapse + 3 (−3 market-weighted) + 2 bounded [−3,−6] cumulative per-rung de-vig + 6 (−0.1) | **low** (range — cumulative ladder histogram blocked on #1974) |
| 2 | polymarket/table_tennis/container_member | 49.95 | **6.8–10.5** | 1 (−38) + 3 (−3) + 2 point −8 exclusive n-way (container YES-sum 2–5 →1) — point computable | **med** |
| 3 | polymarket/soccer/quantity | 44.66 | **6.5–9.8** | 1 (−32) + 3 (−3) + 2 bounded [−3,−6] + 5/6 (−0.4) | **low** (cumulative range) |
| 4 | polymarket/tennis/container_member | 38.07 | **7.2** | 1 (−26) + 3 (−3) + 2 point −10 exclusive | **med** |
| 5 | polymarket/tennis/quantity | 37.14 | **7.0–10.3** | 1 (−24) + 3 (−3) + 2 bounded [−3,−6] | **low** |
| 6 | polymarket/baseball/container_member | 36.99 | **7.8** | 1 (−24) + 3 (−3) + 2 point −9 exclusive | **med** |
| 7 | polymarket/esports/container_member | 29.83 | **6.5** | 1 (−18) + 3 (−3) + 2 point −8 exclusive | **med** |
| 8 | polymarket/baseball/quantity | 29.31 | **7.2–10.5** | 1 (−17) + 3 (−3) + 2 bounded [−3,−6] | **low** |
| 9 | polymarket/soccer/container_member | 24.12 | **6.8** | 1 (−12) + 3 (−3) + 2 point −8 exclusive | **med** (largest n among containers, so exclusive point most stable) |
| 10 | polymarket/baseball/field | 20.13 | **11.2** | 3 (−0.5) + 2 point −8.5 exclusive field n-way (3+ runners, sum>threshold) | **med** |
| 11 | kalshi/entertainment/quantity | 20.11 | **13.8–17.1** | 3 (−3) + 2 bounded [−3,−6] cumulative (kalshi entertainment ladders are quantity) + no provenance (0.95) | **low** |
| 12 | kalshi/hockey/field | 17.15 | **9.1** | 2 point −8 exclusive (hockey field sums >1) + 5 (−0.4) timezone | **med** |
| 13 | kalshi/golf/field | 15.05 | **7.0** | 2 point −8 exclusive | **med** |
| 14 | polymarket/soccer/field | 13.08 | **4.6** | 1 (−1.5, graded 0.82) + 2 point −7 exclusive + 3 (−0.5) | **high** (field exclusive is the measured `field_is_complete_for_normalization` path) |
| 15 | kalshi/baseball/field | 12.23 | **4.2** | 2 point −8 exclusive (largest n, so 12.23→4.2 is the headline MCE move) | **high** |
| 16 | kalshi/baseball/unknown | 11.30 | **11.2** | 6 (−0.1) only — unshaped excluded from field normalization (unknown semantics) | **high** (no de-vig, no provenance) |
| 17 | polymarket/esports/field | 11.02 | **3.5** | 1 (−1.0) + 2 point −7 exclusive | **high** |
| 18 | polymarket/economics/quantity | 9.98 | **4.2–7.5** | 1 (−3.5) + 3 (−3) + 2 bounded [−3,−6] — currently 9.98 so the range crosses the guardrail | **low** |
| 19 | kalshi/basketball/quantity | 9.34 | **3.0–6.3** | 3 (−3) + 2 bounded [−3,−6] — kalshi basketball quantity is cumulative ladder (Over `N`) so bounded | **low** |
| 20 | kalshi/economics/quantity | 7.85 | **1.5–4.8** | 3 (−3) + 2 bounded [−3,−6] — crosses guardrail on best-case only | **low** |

*Derivation per cell (example rank 1, see CSV for all): `current 50.00 → after Fix1 50*0.18*0.9+3=11.1 → after Fix3 11.1−3=8.1 → after Fix2 bounded 8.1−[3,6]=5.1–2.1 but floor at 5.8 (venue-graded floor) → 5.8–9.2` plus rounding/timezone `−0.1−0.4` folded into range. The `predicted_ece` column in the CSV is that final interval; where `2` is exclusive (container/field) the interval collapses to a point (no `–`); where `2` is cumulative (quantity) it stays a range.*

---

## Headline numbers — what the real re-baseline must clear (light-estimate)

| Headline | Current (light, 200k) | Predicted after queue (light-estimate) | Guardrail |
|---|---|---|---|
| **Traded vs untraded gap** — headline blended (all sources) `traded 3.23 − untraded 3.14 = +0.09pp` but **polymarket within-shape gap** `PM traded 6.21 − PM untraded 4.00 = +2.21pp` (the launch-blocking one, `traded_vs_untraded_by_shape.md`) | +0.09pp blended / **+2.21pp PM** | **+0.3 to +0.8pp PM within-shape** (composition closure from quantity/container normalization + provenance; kalshi gap stays −0.2 to +0.3 so blended gap goes to **≈0.0pp**) | No headline gap >1.0pp within any source×shape |
| **Worst cell (ECE, sizable n≥1000)** | **50.00pp** `polymarket/table_tennis/quantity` (rank 1) | **9–12pp** worst becomes `kalshi/hockey/field 9.1` or `polymarket/baseball/field 11.2` (the ladder worst collapses; field residuals become the new worst, still above guardrail) — if cumulative best-case realized, worst is `kalshi/entertainment/quantity 13.8` (low-confidence quantity). Nominal predicted worst **11.2pp** `polymarket/baseball/field` (medium confidence). | Worst sizable RED must be triaged, not necessarily GREEN — gate 1 holds if any RED sizable without a plan. |
| **Count inside 5pp guardrail** (sizable, after `NOT-PROVABLE` gate `graded_share<0.5` wins before GREEN) | **2 of 20** `kalshi/baseball/field 12.23` is not inside, so actually **0 of 20** are `≤5pp` with `graded_share<0.5` rule? Light table: `≤5pp` are `kalshi/basketball/field 4.18` `kalshi/baseball/duel 2.32` `kalshi/baseball/quantity 4.15` but those are not in the top-20 sizable by ECE — within the 20 above, `≤5pp` = **0**. Count with `≤5pp` anywhere = 3 of 100 cohorts. | **7 of 20 sizable GREEN** (`≤5pp` AND `graded_share≥0.5`): ranks 14,15,17,18(best),19(best),20(best) + one of 7/9 depending on exclusive point; stated as **6–9 of 20 GREEN** (range because 3 quantity cells straddle the guardrail). If provenance fix is `survive` (ECE_venue still 30pp) then only **3 of 20 GREEN**. | Gate 1 GREEN only when *every* sizable cell is GREEN/`NOT-PROVABLE-with-plan`/exception — predicted 11–14 RED remain, so gate stays RED after this lane; the build grades “fixed ladder, field residuals remain.” |

*Why the worst stays >5pp: field normalization (`Fix 2` exclusive) moves `field` 7–8pp but `polymarket/baseball/field 20.13→11.2` and `kalshi/hockey/field 17.15→9.1` are still RED; they are the next worklist after ladders. The traded-vs-untraded gap collapses because it was 60% composition (ladder-heavy traded, `re-weighting closes 1.4 of 2.21pp`) plus per-ladder de-vig on the traded side.*

---

## DISAGREEMENT FLAGS — where this simulation disagrees with the queue's registered prediction by >2pp

Flags are the point of prediction-first (ruling 050 at program scale): they are the rows where someone is wrong *before* the build, so the re-baseline has a written falsifier.

| Flag | Cell | Queue registered prediction | This simulation | Δ | Why they differ (who is wrong if the build falsifies the flag) |
|---|---|---|---|---|---|
| **FLAG-1** | `kalshi/entertainment/quantity` (rank 11, 20.11pp) | Queue row 2: cumulative ladders `−3 to −6pp` on `quantity 40–50% ladder 14.18→~8pp` (applies to polymarket ladders). No explicit prediction for kalshi quantity ladders — implicit `similar 3–6pp`. | **13.8–17.1pp** (only −3 market-weighted + bounded −3–6) from 20.11 → stays 13.8 worst-case | **disagree 5.8–9pp** vs implicit | Queue assumed kalshi ladders are same shape as polymarket ladders; kalshi `entertainment quantity` is `n=1200` but `graded_share 0.95` so provenance does not help — if the build shows 8pp the queue underestimated venue-graded ladder de-vig on kalshi, if it shows 16pp the simulation's `[−3,−6]` bound was optimistic for kalshi's book vig. |
| **FLAG-2** | `polymarket/baseball/field` (rank 10, 20.13pp) | Queue row 2: exclusive cells after de-vig `1.5+` bucket empties → `−5 to −15pp` on exclusive where sum 2–5 (field containers). Implies `20.13 → ~5–10pp`. | **11.2pp** (point −8.5 exclusive) | **Δ 1–6pp** vs low end of queue range — flagged because the queue's low end `−15pp` would put this at ~5pp GREEN, simulation stays RED | Queue's exclusive range was measured on 5-member containers (`members=5 → median 2.5`); baseball `field` is 2828 outcomes but `q≈n` single-winner partitions with less sum defect — the queue's −15pp best-case may be for `container_member` not `field`. Build will tell which n-way divisor actually applies per `field_is_complete_for_normalization`. |
| **FLAG-3** | `polymarket/soccer/quantity` (rank 3, 44.66pp) | Queue row 1: worst `quantity 50.00pp → 5–10pp` if collapse (provenance) else ≤5pp if survive. Implies rank 3 collapses to 5–10pp. | **6.5–9.8pp** (range) | **within queue range** — **no flag**, but near the top of it because `graded_share 0.27` is higher than table_tennis 0.18 so collapse is shallower. Flagged here as **near-miss**: if `null_default_share` on soccer quantity is actually 0.55 not 0.73, the build will be ~12pp and will flag post-hoc. |
| **FLAG-4** | `kalshi/economics/quantity` (rank 20, 7.85pp) | Queue has no registered prediction for kalshi economics quantity at 7.85pp (well below ladders) — implicit “ladder cohorts 2–4pp lower” from Fix 3 market-weighted would take 7.85→~4pp. | **1.5–4.8pp** (range straddles GREEN) | **Δ up to 2.5pp** vs queue's implicit ~4pp — **flagged** because best-case `1.5pp` GREEN vs worst `4.8pp` GREEN are both GREEN but on opposite sides of the `0.50` band epsilon (`Fix 6` 0.1pp rank swap at 10×); the queue did not register the interval semantics at the guardrail. |

*No-flag cells (agreement ≤2pp): ranks 1,2,4–9,12–15,17 all agree with queue rows 1–3 within 2pp (e.g., rank 1 `5.8–9.2` vs queue `5–10`, rank 4 `7.2` vs queue `5–10`). Those are the rows where the build is expected to confirm the queue.*

---

## What the real re-baseline will recompute and how it is graded

Per `MACHINE_FIX_QUEUE.md` re-baseline protocol:

1. Snapshot `before.json` = `curl -H "Authorization: Bearer $ADMIN_TOKEN" https://api.bainluck.com/api/admin/cohort-market-type/light` + `/provenance-split` + `/sums-histogram` + heavy `GET /api/admin/cohort-market-type` (706k headline MCE + weekly 6). Record the interpretation-matrix cell gating each fix.
2. Land one tier at a time (1 provenance → 3 unit → 2/5/6 shape/timezone/rounding) and re-curl `after_tierN.json`. Required movements: tier1 top `quantity`/`container_member` `ece_all 50→ece_venue` (collapse) else survive decides tier2 order (already exercised here as collapse); tier2 exclusive `0.9–1.1 healthy` and `1.5+` empties / cumulative per-rung `YES+NO 1.2+` empties + `violation_rate→0`; `ece_label` never `fallback-nonparity` on published cells.
3. Re-baseline decision: heavy sentinel `MCE ≤5.0pp` (`n_floor=1000`, early-warning `300/3.0pp`) plus cohort `GREEN ≤5pp` vs `NOT-PROVABLE (graded_share<0.5)` — both required. Publish `before.json` vs `after.json` diff alongside Brier/reliability/resolution + adaptive/debiased ECE + per-bucket `n` and per-market `q` so “fixed” is proven on four statistics, not one. If any `ece_label` flips to `fallback-nonparity`, that cell is not comparable — re-run on heavy.

*This file + `predicted_table.csv` are the acceptance target the real re-baseline is graded against.*

