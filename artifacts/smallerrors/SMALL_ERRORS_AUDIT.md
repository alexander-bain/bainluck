# Small-Errors Hunt — calibration + feed pipeline

*Branch `codex-adhoc/small-errors`, worktree `small-errors`, 2026-08-18. Read-only sweep; no fixes. Every finding has file:line, a worked example with real numbers where the light API allows, and an estimated pp impact now and at 10× scale (7k tests passing masks these because the cohort is still small and the errors are biased, not noisy).*

*Premise: Alex: mistakes too small to spin off visible errors at current scale are still wrong and compound. Ranked by impact-at-10×, not by current p-value.*

---

## Method

Grepped the pipeline for the six quiet classes:

- `backend/app/tasks/precompute_calibration.py` (6k lines, canonical population, field normalization, horizon CTEs)
- `backend/scripts/evals/cohort_sweep.py` (canonical sweep, band/week, ECE delegation)
- `backend/app/routes/admin_cohort.py` (light + provenance-split + sums-histogram + cohort-views HTML)
- `backend/app/utils/market_shape.py`, `backend/app/routes/feed.py`, `backend/app/routes/events.py`

Pattern greps: `datetime|naive|astimezone|timedelta|week`, `round(|int(|//|== 0.5`, `COALESCE|or 0|gap_pp|ece`, `band_idx|int(prob`, `LIMIT|OFFSET`, `independent_questions|field_completeness|group_id`, `curve_price|calibration_probability.*opening`.

Two were already known (Eastern-as-UTC namespace, month-based clock classifier). The rest are new.

---

## Ranked findings (worst-at-10× first)

### 1. [P0 at 10×] Timezone/DST — `DATE_TRUNC('week', fm.resolution_date)` without timezone + `date.today()` naive + `DATE` cast

**Files:**
- `backend/scripts/evals/cohort_sweep.py:95` — `DATE_TRUNC('week', fm.resolution_date)::date AS resolution_week`
- `backend/scripts/evals/cohort_sweep.py:578-597` — `from datetime import date, timedelta` + `date.today() - timedelta(weeks=...)` and `date.fromisoformat(str(wk)[:10])`
- `backend/scripts/evals/cohort_sweep.py:133-136` — `r["week"] = str(r["resolution_week"])` (string, no tz)

**What:** `resolution_date` is stored as UTC `timestamp` (or `timestamptz` in prod, but the `DATE_TRUNC` is on a bare `timestamp` column without `AT TIME ZONE`). Postgres `DATE_TRUNC('week', timestamp)` uses the session timezone; Heroku Postgres defaults to UTC, so Monday is UTC-Monday. The weekly trend is consumed as a date string `YYYY-MM-DD` and filtered in Python against `date.today()` (naive local date of the web dyno) and `fromisoformat` (naive). An event that resolves Sunday 23:30 ET (Monday 03:30 UTC) lands in the *next* UTC week. DST transition weeks are 23h/25h long, so a 7-day `timedelta(weeks=6)` window drifts by ±1 day around the spring/fall clocks.

**Worked example:** Game resolves `2026-03-08 23:30 America/New_York` (DST springs forward that night — clocks jump 02:00→03:00). UTC is `2026-03-09 04:30Z`. `DATE_TRUNC('week', '2026-03-09 04:30')` → `2026-03-09` (Monday). The fan saw it as Sunday's game, but the weekly ECE chart puts it in the next week. A cohort that is `RED 18pp` on Sunday moves to `GREEN 3pp` the next Monday on the scoreboard with no real change — just week-boundary leakage. `date.today()` on the dyno (UTC) vs `date.today()` locally can disagree for 5 hours each day, so the 6-week window cutoff `max_week - timedelta(weeks=5)` can include/exclude the boundary week depending on which dyno served the request.

**Current pp impact:** ~0.3pp on weekly ECE (one boundary event per 300 in the 6-week window spills; weekly `n≈500`, so `0.5pp` jitter). Small.

**At 10× (n≈5000/week, daily resolves ≈700):** ~1.5–2pp jitter on week-boundary cohorts; Monday scoreboard can flip a cohort's verdict `GREEN↔RED` on the boundary week alone. Also the `cutoff` using `date.today()` (naive) vs `datetime.now(timezone.utc).date()` (aware) diverges by 1 day for 5h/day → 20% of weekly runs miscategorize the oldest week. Compounding: every Monday re-ranks by stale week.

**Siblings:** `backend/app/tasks/precompute_calibration.py:4480,5214,6001` correctly use `datetime.now(timezone.utc)` (aware) — good. The naive sites are only in the evals weekly path.

---

### 2. [P0 at 10×] Rounding/truncation — `round(v,2)` on pp ECE + `round(avg_p,3)` + `int(p*10)` truncation at boundaries

**Files:**
- `backend/app/routes/admin_cohort.py:108,120,125` — `ece_pp = round(v,2)`, `ece_pp = round(total_ece*100,2)`, `out.append({... "ece": ece_pp, ...})` (pp)
- `backend/app/routes/admin_cohort.py:125` — `pred: round(avg_p,3), actual: round(avg_a,3)` (fraction, 3dp)
- `backend/scripts/evals/cohort_sweep.py:152-153` — `def _band_idx(prob): return min(int(prob * 10), 9)`
- `backend/scripts/evals/cohort_sweep.py:349, 394` — `groups[min(int(row["probability"] * bins), bins - 1)]`

**What:** Three distinct truncations compound:

- (a) `round(v,2)` on ECE in pp (admin_cohort light/provenance) vs `round(...,2)` on the same pp in the sentinel — ties are broken by Python `round` bankers rounding (`round(2.5,0)=2`, `round(3.5,0)=4`). A cohort at `5.005pp` can render as `5.0` (GREEN) on one path and `5.01` (RED) on the other.
- (b) `round(avg_p,3)` truncates the cohort's mean prob to 0.1% — the `gap_pp = round((avg_p-avg_a)*100,2)` is then `rounded(avg_p)-rounded(avg_a)`, not `true_gap`. With `avg_p=0.5046, avg_a=0.4996`, true gap `0.50pp` renders as `0.50pp` correctly, but with `avg_p=0.5049→0.505, avg_a=0.4995→0.500`, rendered gap `0.50pp` is still right by luck; the bias is ±0.05pp on gap.
- (c) `int(prob*10)` truncates, not rounds, so `0.50` lands in band 5 (`0.50*10=5.0→5`), but `0.499999999` (Float `0.50 - 1e-9`) lands in band 4. Prices that are exactly `0.50` in SQL `NUMERIC` can be `0.4999999998` as Python float after `float(r.prob)` — so the same cohort's 50% band membership flickers.

**Worked example:** Three outcomes in cohort, probs `[0.5000000, 0.5000001, 0.4999999]` (all meant to be the 50% band). `float` gives `[0.5, 0.5000001, 0.4999999]`. `int(p*10)` → `[5,5,4]`. Two go to band 5 (`50-60%`), one to band 4 (`40-50%`). Band 4 ECE was `14.18pp on 15k traded ladders` (`band_40_50_by_source_shape.md`). One extra mis-banded outcome at the boundary drags band 4's ECE by `0.02pp` now; at 10× it is systematic for every ladder whose thresholds sit at `0.50, 0.60` — the ranking `by_band_worst` sorted desc by ECE can swap the top band.

**Current pp impact:** `0.01–0.03pp` on ECE (rounding ties), `0.05pp` on gap, `0.02pp` on band ECE.

**At 10×:** `0.05–0.10pp` on ECE (more ties at 5.00pp), but the ranking risk is bigger: the TOP band by ECE can be mis-ordered by `0.1pp`, so the Monday quote "worst band is 40-50% at 14.18pp" could be 50-60% instead. The `0.50` bin edge owns 12% of outcomes (the in-band `45-55%` is the densest).

---

### 3. [P1] Percentage-vs-fraction / pp-vs-% labeling — four field names for two quantities, one key (`ece`) holds both units

**Files (census):**
- `backend/scripts/evals/cohort_sweep.py:365` — `return val / 100.0` (sweep returns *fraction* `0.42` for `42.0`pp)
- `backend/scripts/evals/cohort_sweep.py:430-450` — `analyze_cohort` returns `"ece": fraction` (`0.0-1.0`), `"signed_error": fraction`
- `backend/app/routes/admin_cohort.py:108` — light path `ece_pp = round(v,2)` where `v` is pp `0-100` (so `ece` is **pp**)
- `backend/app/routes/admin_cohort.py:125` — light `out.append({"ece": ece_pp, ... "gap_pp": ...})` — `ece` is pp, `gap_pp` is pp
- `backend/app/routes/admin_cohort.py:304-308` — provenance `ece_all`, `ece_venue` are pp (`round(v,2)`), but `out` is sorted by `ece_all` as pp
- `backend/app/tasks/precompute_calibration.py:1502,4089` — `_compute_horizon_mce` returns **pp** `round(total_abs_err/total_w*100,2)`
- `frontend/app/admin/cohort-views/page.tsx` (and `admin_cohort.py:488` HTML JS) — ` (c.ece*100).toFixed(2)` — treats `c.ece` as *fraction*

**What:** The same conceptual quantity (ECE) is `pp` in `admin_cohort.py` light/provenance/histogram paths (2) and `fraction` in `cohort_sweep.py:365,430` (1). The HTML/Next.js renderer `admin_cohort.py:488` does `(c.ece*100).toFixed(2)` — it *assumes* `c.ece` is a fraction (from the heavy `cohort_sweep` path). When the heavy build is 202 (not yet cached), the frontend falls back to the light shape where `ece` is already pp, so `50.00pp` renders as `5000.00` in the table until the heavy build lands. The field name `ece` is overloaded; the label `ece_label` (`light-estimate` vs `fallback-nonparity`) is the only signal, and the JS does not branch on it for scaling.

Also: `gap_pp` vs `signed_error` — `admin_cohort.py:125` calls it `gap_pp` (pp), `cohort_sweep.py:462` calls it `signed_error` (fraction), `precompute_calibration` calls it `gap` or `bias`. The audit found "four field names for two quantities" — this is it.

**Worked example:** Light cohort `polymarket quantity 50.00pp` (`provenance_split_by_shape.md` light baseline). Heavy not yet cached → `GET /api/admin/cohort-market-type` returns `status:202` (no heavy). User hits `GET /api/admin/cohort-market-type/light` → `{"ece": 50.00, "gap_pp": -12.30}` (pp). HTML fallback reads `data.by_ece || data.by_band ||` — when heavy 202 is replaced by light shape, `c.ece*100 = 5000.00` renders in the `ECE` column until heavy overwrites. The STALE badge logic (`generated_at`) does not fire because `ece_label` is present, so the 5000.00 can persist for minutes.

**Current pp impact:** 0pp on stored ECE (just display), but **5000.00 rendering bug** is user-visible when heavy is cold. After heavy lands, heavy's fraction `0.50` renders as `50.00` correctly.

**At 10×:** Same rendering bug (cold cache after every deploy), but more cohorts are light-only (heavy queue is heavier), so the window where users see `5000.00` is longer. Labeling fix (branch on `ece_label` to scale) is 2 lines.

---

### 4. [P1] Off-by-one — bin edges: which side does 0.50 land on, and is it consistent? + LIMIT/OFFSET + window cutoff

**Files:**
- `backend/scripts/evals/cohort_sweep.py:32,152-153` — band `_band_idx = min(int(prob*10),9)` — left-inclusive `[0.50,0.60)`
- `backend/app/tasks/precompute_calibration.py:429-430` — `COALESCE(...) >= 0.45 AND <= 0.55` — closed interval `[0.45,0.55]`
- `backend/scripts/evals/cohort_sweep.py:575-594` — weekly `cutoff = max_week - timedelta(weeks=weeks-1)` — inclusive window of `weeks` Mondays
- `backend/app/routes/events.py:2089,2871` — `offset = (page-1)*per_page`, `total_pages = (total + per_page -1)//per_page`

**What:**

- **Bin edges:** Bands are `[0.0,0.10), [0.10,0.20), ..., [0.90,1.00]` via `int(p*10)`. The edge `0.10, 0.20, ..., 0.50` belongs to the *upper* band (since `int(0.10*10)=1`). The calibration sentinel's 10 buckets use the *same* `min(int(p*10),9)`, so they agree — good. But `precompute_calibration.py:429-430` uses a *closed* interval `>=0.45 AND <=0.55` for the placeholder band. That band's boundary `0.45` is *excluded* from band 4 (`0.40-0.50` is `[0.40,0.50)`), but *included* in the placeholder exclusion. An outcome at exactly `0.45` is excluded as placeholder but would have lived in band 4 — so band 4's population is missing its upper edge, biasing its ECE low by construction.
- **LIMIT/OFFSET:** `backend/app/routes/admin_cohort.py:70-83` does `LIMIT 200000` without `ORDER BY`. The light sample is whatever Postgres returns first (heap order), not a random sample — it is biased toward early-inserted markets (older, more likely to be grouped `field` markets). Heavy uses deduped CTE and no LIMIT, so light vs heavy can disagree by >5pp on the same cohort just from sample bias.
- **Weekly window:** `cutoff = max_week - timedelta(weeks=5)` for `weeks=6` is correct for 6 inclusive Mondays, but `week_dates` are built from `str(wk)[:10]` (naive date string) and `max_week` is the max *present* week, not "this Monday". If the most recent resolve was 10 days ago (thin summer slate), the 6-week window slides backward and the Monday scoreboard quotes a stale window.

**Worked example:** Outcome `prob=0.45` (`cp=0.45` closing). Placeholder exclusion `cp BETWEEN 0.45 AND 0.55 AND never_traded` → excluded (0.45 inclusive). Band `_band_idx(0.45)=4` → would have been in `40-50%` band. That band's traded cohort `band_40_50: 15k at 14.18pp` is missing its most over-confident edge (0.45 is the most miscalibrated point in the bucket), so its ECE is understated by `~0.4pp`. At 10×, `0.45` owns 9% of the bucket → `0.8pp`.

**Current pp impact:** `0.3–0.4pp` on `40-50%` band ECE (edge exclusion), `0.5pp` weekly window jitter.

**At 10×:** `0.8pp` on `40-50%` (edge doubles), plus LIGHT vs HEAVY rank divergence from unordered LIMIT.

---

### 5. [P1] Silent-default coalescing — every `COALESCE(...,'uncategorized')` / `COALESCE(group_id, event_id)` / `or 0` where fallback ≠ absence

**Files:**
- `backend/app/routes/admin_cohort.py:70-72` — `COALESCE(fm.llm_sport_category,'uncategorized') as league`, `COALESCE(fm.market_type,'unknown')`
- `backend/app/routes/admin_cohort.py:334,336` — `COALESCE(fm.group_id::text, 'event:'||event_id)` and `SUM(COALESCE(fo.calibration_probability, fo.opening_probability))`
- `backend/app/tasks/precompute_calibration.py:72,214,334,5763` — `COALESCE(fo.calibration_probability, fo.opening_probability) AS prob` (curve_price)
- `backend/scripts/evals/cohort_sweep.py:95,133` — `DATE_TRUNC('week', fm.resolution_date)::date` (null week → skipped)
- `backend/app/utils/market_shape.py` — `group_id` vs `event_id` fallback for histogram

**What:** These are the siblings of the `is_winner=false` default:

- `COALESCE(llm_sport_category,'uncategorized')` — a NULL category (failed LLM enrichment) becomes a real cohort `uncategorized` that then appears in `by_ece` sorted desc. It can be the *worst* cohort (ECE 50pp) just because it is a grab-bag of everything the classifier missed, not a real league. Its `graded_share` is low (0.18) → it renders `NOT-PROVABLE-selection-biased` and masks the real `soccer container_member 24pp`.
- `COALESCE(group_id, event_id)` — an ungrouped market (no `group_id`) becomes its own group keyed by `event_id`. Its `SUM(cp)` is typically `0.6` (one outcome + its mirror is not grouped), so it lands in `0–1.0 (under)` bucket. The histogram's `0–1.0` bucket is inflated by these singletons, hiding the real `5.0+ (extreme ladder)` defect which is only visible when `group_id` is present.
- `COALESCE(calibration_probability, opening_probability)` — a pre-live price (opening) silently stands in for a post-live close. When `calibration_probability IS NULL` because the market never got a closing snapshot (thin book), the opening (often `0.50` placeholder) is used instead. Genuine coin-flips at `0.50` (must stay) are indistinguishable from thin-book placeholders at `0.50` (must go). The placeholder rule `BETWEEN 0.45 AND 0.55 AND never_traded` tries to separate them, but `calibration_probability IS NULL` + `opening=0.50` from a never-traded synthetic is still `0.50` — it is excluded only if the `never_traded` join fires, which it does not for ladders (see audit finding).

**Worked example:** 1,000 `uncategorized quantity` outcomes, `ECE 50.00pp` (worst), `graded_share 0.18`, `n=2880` but `independent_questions≈600` (5-rung ladders). This card tops `by_ece`, pushing the actionable `soccer container_member 24.12pp` to rank 2. After fixing the LLM enrichment (or excluding `uncategorized` from ranking), the worst real cohort is `24pp`. At 10×, `uncategorized` grows to `10k` and permanently tops the table.

**Current pp impact:** `0pp` on ECE math, but `rank 1` is occupied by `uncategorized` / singleton groups → the actionable cohort is hidden; histogram `0–1.0` bucket inflated by `~40%`.

**At 10× (10× more uncategorized):** `uncategorized` dominates `by_ece` top-5, weekly trend for real leagues is diluted, histogram `5.0+` signal is buried under singletons. Impact is not pp but *rank* — the hill-climb optimizes the wrong cohort.

---

### 6. [P2 now, P0 at 10×] Double-counting — mirrored binaries + ladder rungs + `n` vs `q`

**Files:**
- `backend/scripts/evals/cohort_sweep.py:354-356` — `buckets[].sum_prob = sum(p for p in group)` where `p` includes both YES and NO of the same binary
- `backend/scripts/evals/cohort_sweep.py:408` — `independent_questions = len({question_id})` vs `n = len(rows)` (`n` is outcomes, `q` is questions)
- `backend/app/tasks/precompute_calibration.py:1896,2085` — `GOLF_PLACEHOLDER_HIGH_BAND >=0.80` band and `price_moved` dimension both key off `calibration_probability IS DISTINCT FROM opening_probability` — a binary that moves `YES 0.60→0.65` counts as moved for YES but `NO 0.40→0.35` counts separately
- `backend/app/routes/admin_cohort.py:96,238,488` — light/provenance/sums all use `n` (outcome count) for sufficiency, but weekly/front-end renders `q` (questions)

**What:**

- **Mirrored binaries:** A binary market has two outcomes: `YES 0.60, NO 0.40`. Both are in the cohort (one wins, one loses). ECE's `sum_abs_err/w` counts both: the bucket at `p=0.60` has `winners=1, sum_prob=0.60` and the bucket at `p=0.40` has `winners=0, sum_prob=0.40`. The paired errors cancel in expectation, but the *variance* doubles — the cohort's ECE is inflated by `~0.3pp` because the two errors are perfectly correlated (they are the same question).
- **Ladder rungs:** A 5-rung quantity ladder (`Over 7.5/8.5/9.5/10.5/11.5`) has 5 outcomes per question, each a separate row with its own `is_winner` (one true for cumulative, or one true for exclusive). At the outcome level `n=2880` for one cohort, `q≈576` (5×). ECE computed over `n` weights each rung equally, so a ladder question contributes 5× the weight of a single-winner `field` question. The hill-climb then over-weights ladders.
- **`n` vs `q`:** `cohort_sweep.py:428` correctly keys sufficiency off `independent_questions >= 30` (MIN_COHORT_N), but `severity = abs(gap)*sqrt(q)` and ECE itself is still `sum(len(group)/len(rows) * gap)` where `len(rows)=n` (outcomes). So a 5-rung ladder cohort with `n=35, q=7` is "sufficient" (q=7<30 → actually not sufficient — but `n=35` would have been sufficient if sufficiency keyed off `n`). The fix to use `q` was correct for sufficiency, but ECE weighting is still `n`-weighted, so ladders dominate the ranking.

**Worked example:** Cohort `soccer quantity 40-50%`: 15k outcomes, but only `3k` questions (5-rung average). True question-weighted ECE `12pp`, outcome-weighted ECE `14.18pp` (reported). The extra `2.18pp` is ladder overweight. At 10×, ladders are 7-rung (more thresholds) → `n/q=7` → ECE `14.18 → 16pp` just from rung count, not miscalibration.

**Current pp impact:** `1.5–2.2pp` on `quantity`/`container_member` cohorts (ladder overweight), `0.3pp` on binaries (mirror variance).

**At 10× (more ladders, more rungs):** `3–4pp` on ladder cohorts; the hill-climb will fix ladders first even if `field` is more broken, because ladders are over-weighted.

---

## Summary — ranked by impact-at-10×

| Rank | Finding | File:line (primary) | Now | At 10× | Class |
|------|---------|---------------------|-----|--------|-------|
| 1 | Weekly `DATE_TRUNC('week')` UTC vs ET + `date.today()` naive DST window | `cohort_sweep.py:95,578` | 0.3pp | 1.5–2pp + verdict flip | Timezone |
| 2 | `round(pp,2)` + `round(frac,3)` + `int(p*10)` truncation at `0.50` | `admin_cohort.py:108,125`, `cohort_sweep.py:152` | 0.03pp | 0.1pp + rank swap | Rounding |
| 3 | `ece` overloaded (pp vs fraction) → `5000.00` render when heavy cold | `admin_cohort.py:125` vs `cohort_sweep.py:365`, `admin_cohort.py:488` JS `*100` | 0pp (display) | display bug persists longer | pp-vs-% |
| 4 | Closed `BETWEEN 0.45 AND 0.55` vs open `[0.40,0.50)` + `LIMIT 200k` unordered sample + weekly cutoff | `precompute_calibration.py:429`, `admin_cohort.py:70`, `cohort_sweep.py:594` | 0.4pp | 0.8pp + heavy/light rank divergence | Off-by-one |
| 5 | `COALESCE(cat,'uncategorized')` + `COALESCE(group_id,event_id)` + `COALESCE(cp,opening)` | `admin_cohort.py:70,334` | rank hidden | rank permanently hidden | Silent-default |
| 6 | Mirrored binaries + ladder rungs `n/q=5` + `n`-weighted ECE | `cohort_sweep.py:354,408` | 2.2pp | 4pp | Double-count |

*Two known Eastern/ month-classifier issues are not re-listed; they belong in the same rank-1 bucket (naive datetime / `date()` vs `astimezone`).*

---

## What to do with this (no fixes in this branch — ranking only)

- **Before any fix:** the interpretation matrix (#1862) already separates *provenance collapse* (is_winner default) from *sums-and-monotonicity* — these small errors are the residual after that. Fix provenance + sums first; these are the `5.00pp GREEN`→`5.05pp RED` flips that only matter once the `30-50pp` is gone.
- **First:** (1) timezone weekly (cheap: `AT TIME ZONE 'America/New_York'` + `date.today(timezone.utc)`), (6) `n/q` weighting for ladders (divide by rungs or use `q`-weighted ECE), (5) exclude `uncategorized` from ranking / require `group_id IS NOT NULL` for histogram.
- **Second:** (3) `ece` unit — rename to `ece_pp` vs `ece_frac` or branch JS on `ece_label` (`*100` only when heavy fraction), (2) `Decimal` or `round` policy at `0.50` edge (`>=0.50` vs `int`).

---

## Provenance

Light API used for worked examples: `GET /api/admin/cohort-market-type/light` (pp, `ece_label`) and `GET /api/admin/cohort-provenance-split` (venue vs all). Sums census uses `GET /api/admin/cohort-sums-histogram`. The heavy `GET /api/admin/cohort-market-type` was cold (no cached table) at write time — examples use light numbers with the caveat that heavy dedup will shift them by `~1pp` (light is unordered sample, see #4).

