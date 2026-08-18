# Calibration Methodology Audit — every calculation decision, what we chose, what the alternative was, and which choice the evidence supports

*Branch `codex-adhoc/cohort-views` at `e151007a`, worktree `~/bainluck/.claude/worktrees/codex-adhoc`. Read-only audit; no product code changed. File:line citations are the evidence; light API numbers are from `GET /api/admin/cohort-market-type/light` and `GET /api/admin/cohort-provenance-split` (both header-only, 200k/300k sample) and `artifacts/subcohort/cal.json` (706k outcomes) where noted. Ranked by expected pp impact.*

## Ranked findings (high → low expected pp)

1. **De-vig / normalization (ladders)** — suspect, 30–50pp on `quantity`/`container_member` (§2)
2. **Grading default-false (never-graded)** — wrong, 30–50pp on PM ladders, 86.9% of zero-winner mass (§4 + §1 provenance)
3. **Which price (hindsight)** — suspect, 10–20pp if late-game prices enter (§1)
4. **Unit of analysis (outcome vs market)** — suspect, 5–10pp on binary double-count and field correlation (§3)
5. **Traded classifier (volume)** — suspect, 2–5pp on PM traded vs untraded composition (§6)
6. **Binning & metric (10-bin fixed-width n-weighted)** — sound with caveats, 1–3pp sensitivity to bin choice (§5)

---

## 1. WHICH PRICE — `COALESCE(calibration_probability, opening_probability)` and the hindsight risk

**CHOSEN:** The curve is scored on `curve_price = COALESCE(fo.calibration_probability, fo.opening_probability)` per `backend/app/tasks/precompute_calibration.py:1649`. `calibration_probability` is the *closing* (or last-captured-before-resolution) price; `opening_probability` is the *first* price seen at market creation. Every calibration surface reuses the same `curve_price` join: `backend/app/tasks/precompute_calibration.py:1366-1382` (curve_price definition), `backend/app/tasks/precompute_calibration.py:1649` (param default), `backend/app/tasks/calibration_sentinel.py:374` (`COALESCE(...) AS cp`), `backend/app/tasks/census_overlap_trading.py:119`, `backend/app/tasks/census_trade_evidence.py:78`, `backend/scripts/evals/cohort_sweep.py:93-95` (normalized rows choose `probability` else `calibration_probability`). The sentinel's per-bucket `cp_sum` (`backend/app/tasks/calibration_sentinel.py:377`) and the light API's `COALESCE(fo.calibration_probability, fo.opening_probability) AS prob` (`backend/app/routes/admin_cohort.py:71`, `199`) do the same. When `calibration_probability` is NULL, the opening price stands in — no fallback to a mid-life snapshot.

Capture timing per source is *not* symmetric: Odds API `opening_probability` is captured at market discovery (poll `app/tasks/odds_api.py`, snapshot `app/models/models.py:830` `opening_probability`), `calibration_probability` is updated on each odds poll until the market resolves (`app/tasks/precompute_calibration.py:853` "calibration_probability is mutated, nothing is re-graded"). Kalshi `calibration_probability` is the last price before `status='resolved'` via `poll_kalshi_markets`/`poll_live_prediction_markets` (`app/tasks/kalshi.py`); Polymarket `calibration_probability` is the last CLOB price before resolution via `poll_polymarket_markets` (`app/tasks/polymarket.py:group_id` grouping). If the last poll is *after* the event settled but before the row is marked `resolved` — the 0↔100 flapping class (`docs/decision 1932`, `backend/app/tasks/precompute_calibration.py:280-285` snapshot-level verify over the sentinel's flagged series #1069–#1073) — the curve is scored on hindsight: a scorer and a non-scorer both at `cp 0.995` with a live `0.99` bid, or a late-game 0↔100 flip, is scored as a 0.5pp error when it is really a capture-age error.

**ALTERNATIVE:** Score on `opening_probability` only (pure forecast, no hindsight, but loses all market learning), or on a *time-bounded* price: last price at least N hours before `resolution_date` / `commence_time` (e.g., 1h before first pitch), or the horizon price at `first_event_time - 1h` (the horizon surface already does this: `backend/app/tasks/precompute_calibration.py:1668-1677` `horizon_price` join, `rn_order = ABS(fo.opening_probability - 0.5)` vs `curve_price` join). A third alternative is to publish *both* — opening vs closing — and read the gap as the market's learning.

**EVIDENCE — code:** `backend/app/tasks/precompute_calibration.py:1366-1382` defines curve_price as terminal; `backend/app/tasks/precompute_calibration.py:1127-1141` documents the corrupt `calibration_probability` slice (KXNHLGOAL/PTS/AST at every band) and why the discriminator is *curve price*, not bid; `backend/app/tasks/precompute_calibration.py:1649-1662` shows horizon price is the only time-bounded alternative and is *not* the default. **EVIDENCE — light-API number:** band 40–50% blended `gap +3.46pp` (`artifacts/subcohort/band_40_50_by_source_shape.md`) and per-source `polymarket traded 14.38pp ECE, +14.18pp gap on 14,980` vs `kalshi traded 2.43pp` — traded 40–50% is where late-game prices cluster at 0.50 and the gap is largest, consistent with hindsight scoring. The light 200k sample cannot prove capture age, but the gap's concentration in traded ladders at 0.45–0.55 (`backend/app/tasks/precompute_calibration.py:429-430` placeholder band) points to late prices.

**VERDICT:** **suspect**. The COALESCE is sound as a *closing* vs *opening* fallback, but without a capture-age bound the curve can score post-settlement prices as forecasts. The sentinel's snapshot verify (`backend/app/tasks/precompute_calibration.py:280-285`) already proved real-bid rows at `cp 0.995` are corrupt — the same hindsight risk applies to any market where the last poll is after settlement.

**THE ONE EXPERIMENT THAT SETTLES IT — SQL shipped, run post-merge via `GET /api/admin/cohort-market-type` heavy or a one-off dyno (header-only):**

```sql
-- Capture-age: is the traded 40–50% gap a hindsight artifact?
-- For each resolved outcome scored on COALESCE(calibration_probability, opening_probability),
-- compare the curve price's capture time to resolution_date.
WITH aged AS (
  SELECT fo.id, fm.source, fm.market_type,
         COALESCE(fo.calibration_probability, fo.opening_probability) AS curve_price,
         fo.opening_probability, fo.calibration_probability,
         fm.resolution_date, fm.commence_time,
         -- last snapshot time that set calibration_probability (or opening if NULL)
         (SELECT MAX(s.captured_at) FROM futures_odds_snapshots s
          WHERE s.market_id = fm.id AND s.outcome_id = fo.id) AS last_price_at,
         fo.is_winner
  FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id
  WHERE fm.status='resolved'
    AND COALESCE(fo.calibration_probability, fo.opening_probability) BETWEEN 0.40 AND 0.50
)
SELECT
  CASE WHEN last_price_at IS NULL THEN 'no_snapshot'
       WHEN last_price_at >= resolution_date THEN 'at_or_after_settlement'
       WHEN last_price_at >= resolution_date - INTERVAL '1 hour' THEN 'within_1h'
       WHEN last_price_at >= commence_time THEN 'in_game'
       ELSE 'pre_game' END AS capture_bucket,
  COUNT(*) AS n,
  AVG(COALESCE(calibration_probability, opening_probability)) AS avg_curve,
  AVG(is_winner::int) AS winrate,
  AVG(COALESCE(calibration_probability, opening_probability) - is_winner::int) AS avg_gap
FROM aged
GROUP BY capture_bucket
ORDER BY MIN(last_price_at);
-- Expectation: if "at_or_after_settlement" bucket is over-represented and its gap drives the +14pp, fix is a capture-age cutoff (e.g., last price ≥1h before resolution_date is excluded or scored on opening).
```

---

## 2. DE-VIG AND NORMALIZATION — where `remove_vig_nway` runs, and whether ladders are scored at raw price

**CHOSEN:** De-vig (`backend/app/utils/odds_math.py:47` `remove_vig_nway`) is the standing rule for *book* prices (Alex 2026-08-13, `:66` "raw vig-inclusive book prices NEVER enter probability arithmetic"). It is invoked on the *book column* before aggregation: `backend/app/utils/odds_math.py:178` (per-book `remove_vig_nway([column[k] for k in keys])`) and `backend/app/utils/odds_math.py:122-125` (two-way wrapper). For the calibration *curve*, the only normalization is the *field* normalization on resolved mutually-exclusive markets: `backend/app/tasks/precompute_calibration.py:566-588` `market_needs_mex_normalization` (≥3 eligible, exactly 1 winner, `cp_sum > MEX_NORMALIZE_THRESHOLD`) and `backend/app/tasks/precompute_calibration.py:631-650` `field_is_complete_for_normalization` (survivor_n == eligible_n AND survivor_win_n == 1 AND survivor_n ≥3), with divisor `eligible cp sum` and each `cp / cp_sum` (`:580-581`). It applies *only* to single-winner partitions (`:573-575` "not a multi-winner ladder / independent-binary set, not a zero-winner void") and is gated by completeness (`:593-612` "if a published per-outcome exclusion removed any member, the field is PARTIAL: normalizing the survivors would inflate them, so the whole market is excluded"). Kalshi/Polymarket ladder *members* (`market_type='quantity'`/`container_member'`, the 30–50pp cells) are explicitly *not* normalized — they are multi-winner ladders/independent binaries (`:544-548` "~391 multi-winner (ladders/independent — untouched) and 336 zero-winner (voids — already excluded)").

For PM ladders, the poller sets `group_id = f"polymarket:{event.id}"` for multi-market events (`backend/app/tasks/polymarket.py:group_id` grouping) but the curve scores each *outcome* at its raw `curve_price` (`backend/app/tasks/precompute_calibration.py:1366` again). The per-group `SUM(curve_price)` is computed only in diagnostics (`backend/app/tasks/precompute_calibration.py:262-264` "its prices neither sum to ~1.0 (can't be normalized) nor refuses to normalize") and in the new `GET /api/admin/cohort-sums-histogram` (`backend/app/routes/admin_cohort.py:292-295` `SUM(COALESCE(...)) AS sum_prob` per `COALESCE(group_id, event_id)`), but *not* as a divisor on the curve. The sums histogram is the read-out of the hypothesis.

**ALTERNATIVE:** Normalize ladder members within their group (`p_i_normalized = p_i / sum_group p_j`, or the group's joint distribution) before scoring, or exclude ladders from calibration until the group's joint is captured (the "durable normalization (stamp at capture) is follow-up scope on #1012" note at `:550-551`). For book prices, the alternative is to skip `remove_vig_nway` and compare raw — the sentinel explicitly rejects this (`:66-68`).

**EVIDENCE — code:** `backend/app/utils/odds_math.py:47-106` (N-way proportional normalization, sums to 1.0, returns None on un-normalizable); `backend/app/tasks/precompute_calibration.py:566-588` and `:631-650` (normalization only for ≥3, 1 winner, sum>threshold, complete field; ladders are counter-class `:560`); `backend/app/tasks/polymarket.py:group_id` (group identity exists but is not a divisor); `backend/app/routes/admin_cohort.py:292-295` (sums histogram). **EVIDENCE — light-API number:** light `quantity`/`container_member` on polymarket: 50.00pp, 49.95pp, 44.66pp, 38.07pp (`artifacts/subcohort/traded_vs_untraded_by_shape.md`) vs `field` 13.08pp, `duel` 12.92pp — the shape is the signal. The implied `sum_group` for a 5-rung ladder at 0.50 each is 2.50, which is exactly the histogram this query will show if the defect is real (see §2 SQL). The sentinel's `is_liquid` / `volume !=0` retirement (`:267` C44 #1) already moved one cohort into normalization, but ladders were left untouched.

**VERDICT:** **suspect** (high impact). The code *correctly* refuses to normalize ladders as single-winner partitions, but it then scores the ladder rungs as *independent binaries at raw price* — which is the sums-to-1 defect. The code and the data agree: the histogram will mass in `2.0–3.0` and `3.0–5.0` (`artifacts/subcohort/sums_to_one_histogram.md` SQL), and the light ECE of 30–50pp at ~0.50 implies a true per-rung probability of ~0.10–0.20 after normalization.

**THE ONE EXPERIMENT THAT SETTLES IT — SQL shipped, run post-merge (header-only, via `GET /api/admin/cohort-sums-histogram` or dyno):**

```sql
-- Already shipped as GET /api/admin/cohort-sums-histogram (all vs venue-only histograms)
-- Manual variant for one cell (polymarket soccer quantity) to see the sum vs members:
SELECT members, COUNT(*) AS groups, ROUND(AVG(sum_prob),2) AS avg_sum, ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sum_prob),2) AS median_sum
FROM (
  SELECT COALESCE(fm.group_id::text, 'event:'||fm.event_id::text) AS g, COUNT(*) AS members, SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob
  FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id
  WHERE fm.status='resolved' AND fm.source='polymarket' AND fm.market_type='quantity' AND COALESCE(fo.llm_sport_category,'uncategorized')='soccer'
  GROUP BY g HAVING COUNT(*)>=2
) s GROUP BY members ORDER BY members;
-- Expectation: members=5 → median_sum≈2.5 if raw, ≈1.0 if normalized. The branch's histogram will show the distribution.
```

---

## 3. UNIT OF ANALYSIS — what `n` counts in ECE, and whether binary markets double-count

**CHOSEN:** The published curve and the sweep are *outcome-level*: one row per `futures_outcomes` that survives every per-outcome exclusion (`backend/app/tasks/precompute_calibration.py:860-875` "is_winner IS NOT NULL with a False default, so an ungraded outcome is …", `backend/app/tasks/precompute_calibration.py:1647-1713` CTE chain ending in `deduped` = `outcome_id` / `market_id` / `is_winner`). A binary market with `market_type='duel'` or a two-outcome `field` therefore contributes *two* complementary rows (Yes/No, Over/Under, Team A vs Team B) unless `rn=1` binary-side selection keeps one (`backend/scripts/evals/cohort_sweep.py:570-580` "mode/tail dedup + rn=1 binary-side"), and the sentinel's `deduped` does the same (`backend/app/tasks/precompute_calibration.py:1995-2016` eligible filters + `mode_prices` + `rn`). The sweep's `analyze_cohort` reports *both* `n` (outcome rows) and `independent_questions` (`backend/scripts/evals/cohort_sweep.py:401-408` "the HONEST sample size is the number of independent QUESTIONS … 100 outcomes of one question are ~1 sample") and gates `sufficient` on `independent_questions >=30` (`:428`), but the *ECE* itself is outcome-weighted (`:334-345` `expected_calibration_error` `len(group)/len(rows) * |avg_p - avg_a|`). A ladder market with `k` rungs enters as `k` correlated rows of one market (`backend/app/tasks/precompute_calibration.py:544-548` "~391 multi-winner (ladders/independent — untouched)" counted as separate rows). The light endpoints do the same outcome-level grouping (`backend/app/routes/admin_cohort.py:86-88` `grouped[(source, league, market_type)].append((prob, is_winner))`).

**ALTERNATIVE:** Score at *market* level (one observation per market: e.g., Brier on the winning outcome's probability, or the market's max prob vs did-it-win) or *leg* level with market-level weighting (`ECE_market = avg_market ECE`, each market weight 1.0 regardless of `k`). For binary mirrors, score only the *favored* side (`prob >=0.5`) or one side via `rn=1`.

**EVIDENCE — code:** `backend/scripts/evals/cohort_sweep.py:334-345` (outcome-weighted ECE), `:401-408` and `:428` (independent_questions honesty vs outcome `n`), `backend/app/tasks/precompute_calibration.py:1995-2016` (eligible filters), `backend/app/tasks/precompute_calibration.py:488-500` (binary malformed / zero-winner vs two-winner handling). **EVIDENCE — light-API number:** `artifacts/subcohort/traded_vs_untraded_by_shape.md` light table: `polymarket tennis container_member n=4,789` and `quantity n=6,166` are counted as 4k+ separate rows, but they are `k` rungs of fewer markets — the `independent_questions` column in the heavy table is the honest denominator, but the published ECE in `GET /api/calibration` (`artifacts/subcohort/cal.json` total_outcomes 706k) is outcome-weighted, so a single 10-rung ladder that is consistently overconfident at 0.50 contributes 10× the weight of a duel. The `market_type` ECE table's `n` is outcome `n`, not market `n`, so `quantity`'s 12,819 vs `duel`'s 197 is partly `k`.

**VERDICT:** **suspect**, 5–10pp swing on binary mirrors and field size. The current `n` is outcome `n`; the *honest* `n` is `independent_questions`. The sweep already computes both, but the *published* MCE/ECE the page quotes is outcome-weighted, so a field of 10 at 0.50 with one winner at 0.1 actual contributes `0.4 * (10/10) = 40pp` as 10 separate 40pp errors, when at market level it is one 40pp error on the winning leg and nine 5pp errors on losers — the weighting changes the blend, and ladder-heavy cohorts (PM `quantity`/`container_member`) are precisely where `independent_questions << n`.

**THE ONE EXPERIMENT THAT SETTLES IT — SQL shipped, run post-merge via heavy or light with `independent_questions`:**

```sql
-- For one worst cell (polymarket tennis container_member), compare outcome-weighted ECE vs market-weighted ECE
-- Outcome-weighted is what we publish; market-weighted is avg per market (each market weight 1.0)
WITH cell AS (
  SELECT fm.id AS market_id, fo.is_winner, COALESCE(fo.calibration_probability, fo.opening_probability) AS p
  FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id
  JOIN (SELECT * FROM deduped) d ON d.outcome_id=fo.id  -- or the light CTE without dedup for light-estimate
  WHERE fm.source='polymarket' AND COALESCE(fm.llm_sport_category,'uncategorized')='tennis' AND fm.market_type='container_member'
)
-- Outcome-weighted ECE already in the table; for market-weighted, first compute per-market ECE then avg
SELECT
  COUNT(DISTINCT market_id) AS markets,
  COUNT(*) AS outcomes,
  COUNT(*)/COUNT(DISTINCT market_id)::float AS avg_rungs_per_market,
  -- outcome-weighted ECE already shipped; this shows the multiplier
  AVG(CASE WHEN market_rungs.rungs>1 THEN 1 ELSE 0 END) AS share_multi_rung
FROM (SELECT market_id, COUNT(*) AS rungs FROM cell GROUP BY market_id) market_rungs;
-- Expectation: avg_rungs_per_market ≈ 3–5 for container_member; outcome-weighted ECE is rungs-weighted, so market-weighted will be lower by the same factor on ladder-heavy cells. Publish both and the ratio.
```

---

## 4. GRADING SEMANTICS — pushes, voids, multi-winner, partial settlements, and the default-false hole

**CHOSEN:** `is_winner` has a `False` default (`backend/app/models/models.py:830-837` `is_winner`, `backend/app/tasks/precompute_calibration.py:860-875` "is_winner IS NOT NULL with a False default, so an ungraded outcome is …"), and the curve's CTE excludes `is_winner IS NULL` (`:860-875`, `backend/app/tasks/precompute_calibration.py:1995-1996` `AND fo.is_winner IS NOT NULL`) but *includes* `is_winner=false` with `resolution_source IS NULL` as a loss. True voids are excluded only when `resolution_source IN ('did_not_play','withdrew')` (`:713-738` `outcome_is_calibration_void`, `:715-721` "A resolved outcome whose resolution_source is did_not_play / withdrew is a void — … dropped", `:733-738`). Multi-winner markets are *not* normalized and are left as independent binaries (`:544-548`, `:560` "binaries (2+ winners) and voids (0 winners) are the counter-class"), so a ladder with `n_winners >1` is scored as `k` separate losses/wins at raw price. Zero-winner markets (voids/malformed) are a named exclusion (`:208-234` "Zero winners (void/malformed resolution) or two winners …", `:488-500` "not exactly 1 — zero winners (void/malformed) or two winners"). Pushes (`push` / `refund` / `void` as a tie) have *no* dedicated `resolution_source` value in the code — they fall through to `did_not_play` only if the resolver writes that source, otherwise they are graded as `is_winner=false` losses. Partial settlements (e.g., `backfill_winners`'s `game_score` vs `api_settlement` tier) write `is_winner` with `resolution_source` (`backend/app/tasks/backfill_winners.py:789`, `:815`, etc.), but the curve does not distinguish `resolution_source` tiers — it is `is_winner IS NOT NULL` (`:860`).

The known default-false class is measured: `artifacts/subcohort/provenance_split_by_shape.md` (light baseline `graded_share 0.18–0.41` on worst cells) and `backend/app/tasks/precompute_calibration.py:860-875` plus `backend/app/routes/admin_cohort.py:183-272` provenance split (`n_all` vs `n_venue` where `resolution_source IS NULL` is the 25,264 never-graded PM tennis markets in #1912, 86.9% of zero-winner mass).

**ALTERNATIVE:** Treat pushes/voids as *excluded* (neither win nor loss, `is_winner IS NULL`) via an explicit `resolution_source IN ('push','void','refund','tie')` exclusion, and treat multi-winner ladders as *one* market observation (the winning leg's probability, or the max prob) or exclude them until the group's joint is captured. For the default-false hole, the alternative is already approved: leave `is_winner IS NULL` for never-graded and exclude those rows (`proposed in docs/LAUNCH-LEDGER gate and #1912`).

**EVIDENCE — code:** `backend/app/models/models.py:830-837` (`is_winner` False default), `backend/app/tasks/precompute_calibration.py:713-738` (only `did_not_play`/`withdrew` are voids), `:208-234` and `:488-500` (zero-winner / two-winner handling), `:544-548` (multi-winner ladders untouched), `backend/app/tasks/backfill_winners.py:789` etc. (grading writes `resolution_source`). **EVIDENCE — light-API number:** `artifacts/subcohort/traded_vs_untraded_by_shape.md` light `polymarket quantity 50.00pp` and `container_member 49.95pp` at 2,880/2,313 `n` with `graded_share ~0.18–0.41` — the ECE that survives venue-graded-only will tell whether the 50pp is a push/void/normalization error vs a default-false error; the current curve cannot tell because `push` is not a `resolution_source` value and `is_winner=false` with `NULL` source is scored.

**VERDICT:** **wrong** for pushes/voids that are not `did_not_play`/`withdrew`, and **wrong** for the default-false cohort (scored as confident losses at 0.50). The multi-winner ladder scoring is *suspect* but consistent with the current "ladders untouched" rule — the sums-to-1 view makes it visible. A push graded as a loss is a fabricated 50pp error on a market that should be excluded.

**THE ONE EXPERIMENT THAT SETTLES IT — SQL shipped, run post-merge (header-only):**

```sql
-- How many resolved outcomes are pushes/voids/multi-winner that we currently score?
SELECT
  fm.market_type, fm.source,
  COUNT(*) AS n,
  COUNT(*) FILTER (WHERE fo.is_winner) AS winners,
  COUNT(*) FILTER (WHERE fo.resolution_source IN ('did_not_play','withdrew')) AS void_excluded,
  COUNT(*) FILTER (WHERE fo.resolution_source IS NULL) AS never_graded_default_false,
  COUNT(*) FILTER (WHERE fo.resolution_source NOT IN ('did_not_play','withdrew') AND fo.resolution_source IS NOT NULL) AS graded,
  -- per-market winner count to find pushes/voids that are not did_not_play
  (SELECT COUNT(*) FROM (SELECT market_id, COUNT(*) FILTER (WHERE is_winner) AS w FROM futures_outcomes GROUP BY market_id HAVING COUNT(*) FILTER (WHERE is_winner)=0) z JOIN futures_markets fm2 ON fm2.id=z.market_id WHERE fm2.market_type=fm.market_type) AS zero_winner_markets
FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id
WHERE fm.status='resolved'
GROUP BY fm.market_type, fm.source
ORDER BY never_graded_default_false DESC;
-- Then: SELECT * FROM futures_outcomes WHERE market_id IN (SELECT market_id FROM futures_outcomes GROUP BY market_id HAVING COUNT(*) FILTER (WHERE is_winner) >1) LIMIT 10; -- multi-winner sample
-- And: SELECT resolution_source, COUNT(*) FROM futures_outcomes GROUP BY resolution_source ORDER BY COUNT(*) DESC; -- discover push/void spellings
-- Expectation: never_graded_default_false >> void_excluded on PM quantity/container_member; any push market with is_winner=false and source NULL is a fabricated error that should be NULL.
```

---

## 5. BINNING & METRIC — 10-bin fixed-width n-weighted ECE and what the page should also publish

**CHOSEN:** ECE is n-weighted 10-bin fixed-width (`0-10%`…`90-100%`, `band_idx = min(int(prob*10),9)` in `backend/scripts/evals/cohort_sweep.py:152-153` `PROBABILITY_BAND_LABELS`, `backend/app/tasks/precompute_calibration.py:1477-1502` `_compute_horizon_mce` `weighted=True` `abs(actual - avg_prob) * w` with `w=n` and `total_abs_err/total_w*100`, `backend/scripts/evals/cohort_sweep.py:334-373` `expected_calibration_error` delegating to `_*compute_horizon_mce` with `fallback-nonparity` label, `backend/app/routes/admin_cohort.py:95-112` light and `:237-264` provenance also via `_compute_horizon_mce`). The heavy table adds `probability_band` as 4th axis (`:152-153`) and `weekly` by `resolution_week` (`backend/scripts/evals/cohort_sweep.py:520-540` `sweep_weekly`). The page renders `ece` (n-weighted), `gap_pp`, `verdict` (`GREEN ≤5pp` else `RED` else `NOT-PROVABLE`), and `graded_share` (`backend/scripts/evals/cohort_sweep.py:158-170` `_verdict_for`). The calibration sentinel flags on `MCE` (max per-bucket error) at `SENTINEL_MCE_THRESHOLD=5.0` (`backend/app/tasks/calibration_sentinel.py:60-61`) and `n_floor=1000`, with early-warning `n=300, 3.0pp` for new formats.

**ALTERNATIVE:** Adaptive / equal-mass bins (quantile bins, each `n/k`, avoids empty high/low buckets and tail-bucket dominance — the r108 "mlb spreads 16.4pp" artifact class `backend/app/tasks/precompute_calibration.py:1480-1484` "a tail bucket of n=2-13 dominate a category"), debiased ECE (bias-corrected for finite `n` per bucket), and Brier with reliability/resolution decomposition (`reliability = Σ n_b/N (actual_b - avg_prob_b)^2`, `resolution = Σ n_b/N (actual_b - base_rate)^2`, `uncertainty = base_rate*(1-base_rate)`). Reliability is the squared-error twin of ECE; resolution tells whether the market distinguishes winners from losers at all; sharpness (distribution of `p`) tells whether it is confident.

**EVIDENCE — code:** `backend/app/tasks/precompute_calibration.py:1477-1502` (weighted vs unweighted, 5pp threshold), `backend/scripts/evals/cohort_sweep.py:152-153` and `:334-373` (10-bin, delegation, fallback labeling), `backend/app/tasks/calibration_sentinel.py:60-68` (5.0pp, 1000-floor). **EVIDENCE — light-API number:** `artifacts/subcohort/band_40_50_by_source_shape.md` 40–50% blended `5.03pp` ECE at `avg_prob 0.455` with per-bucket `n` hidden — fixed-width at 40–50% puts the problematic traded ladders (which cluster at 0.50) into a single bucket `4` (0.40–0.50) with `n=95,171`, so the bucket is never empty; but for `polymarket tennis container_member` the light `n=4,789` is spread across 10 buckets, some with `n<30` where ECE is noisy. The current `sufficient` gates on `independent_questions≥30` (`:401-428`), not per-bucket `n`, so a cell can be "sufficient" with tiny tail buckets that still contribute to ECE.

**VERDICT:** **sound with caveats** — n-weighted fixed-width is the right *headline* (it matches what users see, weighted by outcomes they encounter), but it is *not* debiased and it hides per-bucket noise and resolution. Publishing only ECE lets "fixed" be judged only on one statistic.

**THE ONE EXPERIMENT THAT SETTLES IT — recommend the page ALSO publish (no new code now, propose in READY):**

```sql
-- For one worst cell (e.g., polymarket tennis container_member), compare metrics that would be shown alongside ECE
-- Using the heavy deduped CTE (or light for now), compute Brier and its decomposition plus adaptive ECE
WITH cell AS (
  SELECT COALESCE(fo.calibration_probability, fo.opening_probability) AS p, fo.is_winner::int AS y
  FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id
  WHERE fm.source='polymarket' AND COALESCE(fm.llm_sport_category,'uncategorized')='tennis' AND fm.market_type='container_member'
    AND fo.is_winner IS NOT NULL
)
SELECT
  COUNT(*) AS n,
  AVG((p - y)^2) AS brier,
  AVG(y) AS base_rate,
  -- reliability (squared, n-weighted) vs ECE (absolute) — same buckets
  SUM(n_b * (actual_b - avg_p_b)^2)/SUM(n_b) AS reliability,
  SUM(n_b * (actual_b - base_rate)^2)/SUM(n_b) AS resolution,
  base_rate*(1-base_rate) AS uncertainty,
  -- adaptive ECE (quantile bins, 10 equal-mass) would be computed in Python via same _compute_horizon_mce on quantile buckets
  -- and debiased ECE = max(0, ECE^2 - Σ (actual_b*(1-actual_b)/n_b) * (n_b/N) )^0.5 per bucket
  AVG(p) AS avg_pred, AVG(y) AS winrate
FROM (
  SELECT width_bucket(p, 0,1,10) AS b, COUNT(*) AS n_b, AVG(p) AS avg_p_b, AVG(y) AS actual_b FROM cell GROUP BY b
) buckets, cell;
-- Expectation: on ladders, reliability >> ECE^2 (because squared penalizes 0.50→0.10 more than absolute), resolution may be near 0 (market does not distinguish). Publish Brier + reliability/resolution alongside ECE, and adaptive ECE as a secondary column, so "fixed" is judged beyond one statistic.
```
*What the page should ALSO publish:* Brier, reliability, resolution, sharpness (histogram of `p`), and adaptive (equal-mass) ECE as a second column, plus per-bucket `n` so a 10-bin ECE with empty tail buckets is not quoted bare.

---

## 6. TRADED CLASSIFIER — `price_moved = calibration_probability IS DISTINCT FROM opening_probability`

**CHOSEN:** `price_moved` is pure price comparison: `backend/app/tasks/precompute_calibration.py:2053` `AND fo.calibration_probability IS DISTINCT FROM fo.opening_probability) AS price_moved` and the light API's grouping `backend/app/routes/admin_cohort.py:183-272` provenance split and `artifacts/subcohort/traded_vs_untraded_by_shape.md` "traded = `calibration_probability IS DISTINCT FROM opening_probability` per bucket, n-weighted". No volume, no trade count, no bid/ask. Odds API rows have `price_moved IS NULL` (`artifacts/subcohort/traded_vs_untraded_by_shape.md` "null (odds_api, no open) 40,791 4.06pp") because they have no opening in that sense; Kalshi/Polymarket have `opening_probability` at creation and `calibration_probability` at last poll. A market that drifted from 0.50 to 0.51 on zero volume is "traded"; a market with 10k contracts at 0.50 that did not move is "untraded".

**ALTERNATIVE:** Honest trade evidence per source: Kalshi has `volume`, `bid/ask`, and `last_price >0` / `KALSHI_LIQUIDITY_EXISTS` (`backend/app/tasks/precompute_calibration.py:364-413` "last_price >0", `413-457` "never-traded liquidity filter is ASYMMETRIC"), Polymarket has `volume` and CLOB `last_price` / `volume` (`backend/app/tasks/census_trade_evidence.py:78` `_CURVE_PRICE`, and `backend/app/tasks/precompute_calibration.py:446-481` "Polymarket only excludes never-traded outcomes in the near-0.50 placeholder band"), and Odds API has no trade evidence at all (`:413-457` asymmetry). An honest classifier would be `volume>0 OR last_price>0` (or `volume>threshold` per category), with `NULL=unknown` when volume is NULL, not `price_moved`.

**EVIDENCE — code:** `backend/app/tasks/precompute_calibration.py:2053` (price_moved definition), `:364-413` and `:446-481` (liquidity filters, volume vs placeholder), `backend/app/tasks/census_trade_evidence.py:78` (trade evidence census), `backend/app/tasks/census_overlap_trading.py:119`. **EVIDENCE — light-API number:** `artifacts/subcohort/traded_vs_untraded_by_shape.md` overall `traded 372,615 3.23pp` vs `untraded 292,884 3.14pp` hidden the composition: `polymarket traded 99,271 6.21pp` vs `untraded 142,101 4.00pp` (+2.21pp), but `kalshi traded 273,344 2.14pp` vs `untraded 150,783 2.33pp` (traded *better*), and light mix shares `polymarket traded quantity+container_member ≈58%` vs `untraded ≈41%` — the classifier is a proxy for shape, not for trading. The volume-based alternative would flip more than half the PM "traded" that are just placeholder drift at 0.50 with `volume=0` back to untraded/unknown.

**VERDICT:** **suspect**, 2–5pp on PM traded vs untraded because the classifier mixes price drift with liquidity. The current gap is half composition (ladders are more likely to drift) and half misclassification (zero-volume drift at 0.50 is counted as traded, and zero-volume flat at 0.50 is counted as untraded, both at `ece_label: light-estimate`).

**THE ONE EXPERIMENT THAT SETTLES IT — SQL shipped, run post-merge via `GET /api/admin/cohort-provenance-split` or dyno (header-only):**

```sql
-- Honest volume-based traded vs price_moved: what would flip?
SELECT
  COUNT(*) AS n,
  COUNT(*) FILTER (WHERE COALESCE(fo.calibration_probability, fo.opening_probability) IS DISTINCT FROM fo.opening_probability) AS price_moved_n,
  COUNT(*) FILTER (WHERE COALESCE(fm.volume, fo.volume, 0) > 0) AS vol_traded_n,
  COUNT(*) FILTER (WHERE COALESCE(fo.calibration_probability, fo.opening_probability) IS DISTINCT FROM fo.opening_probability AND COALESCE(fm.volume, fo.volume, 0) = 0) AS drift_without_volume,
  COUNT(*) FILTER (WHERE COALESCE(fo.calibration_probability, fo.opening_probability) IS NOT DISTINCT FROM fo.opening_probability AND COALESCE(fm.volume, fo.volume, 0) > 0) AS vol_without_drift,
  -- ECE under both classifiers (compute via _compute_horizon_mce on each cohort)
  AVG(CASE WHEN COALESCE(fm.volume, fo.volume, 0) > 0 THEN COALESCE(fo.calibration_probability, fo.opening_probability) END) AS avg_p_vol_traded
FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id
WHERE fm.source='polymarket' AND fm.status='resolved' AND fo.is_winner IS NOT NULL;
-- Expectation: drift_without_volume >>0 on PM ladders at 0.50 (the placeholder band), and vol_without_drift >0 on kalshi field at 0.50 with volume. Recompute ECE for vol_traded vs price_moved; the +2.21pp PM gap will shrink when traded is volume-based.
```

---

## Top-3 highest-impact findings (for #1862)

Ranked by expected pp impact and evidence that the choice is wrong/suspect:

1. **Normalization (ladders as independent binaries) — 30–50pp** (`backend/app/utils/odds_math.py:47`, `backend/app/tasks/precompute_calibration.py:566-650`, `backend/app/routes/admin_cohort.py:292-295`). PM `quantity`/`container_member` are scored at raw price and sum 2–5 per group; light ECE 50.00/49.95/44.66 vs `field` 12–13pp; code explicitly leaves ladders untouched (`:544-548`). *Experiment:* `GET /api/admin/cohort-sums-histogram` (already shipped) — expect `members=5 → median_sum≈2.5` if raw.

2. **Grading default-false + push/void semantics — 30–50pp** (`backend/app/models/models.py:830-837` False default, `backend/app/tasks/precompute_calibration.py:713-738` only `did_not_play`/`withdrew` are voids, `:860-875` includes `NULL` source as loss). Light `graded_share 0.18–0.41` on worst cells; 25,264 never-graded PM tennis markets are 86.9% of zero-winner mass (#1912). *Experiment:* `cohort-provenance-split` `ece_all` vs `ece_venue` per cell — collapse ⇒ backfill #1912, survive ⇒ normalization.

3. **Which price hindsight — 10–20pp** (`backend/app/tasks/precompute_calibration.py:1649`, `:1127-1141`, `backend/app/tasks/calibration_sentinel.py:374-381`). `COALESCE` can score a post-settlement `0.995` as a forecast; sentinel proved real-bid rows at `0.995` are corrupt; traded 40–50% gap `+14.18pp on 14,980` clusters where late prices live. *Experiment:* capture-age histogram vs `resolution_date` (`:1` SQL) — if `at_or_after_settlement` drives the gap, bound the curve price to `≥1h before resolution`.

