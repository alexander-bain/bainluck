# Residual Scope — why `polymarket/*/field` at ~11pp is the predicted new worst class

*Branch `codex-adhoc/rebaseline` from `2098d7aa` (histogram-fix), worktree `rebaseline`. Read-only, `light-estimate` throughout. This is the document that turns “Gate 1 stays RED” into a finishable list. After the queued fixes (provenance `ece_all→ece_venue`, market-weighted `q`, exclusive `n-way` + cumulative per-rung two-way, timezone `±0.4`, rounding `epsilon`), the ladder worst collapses (`50→6–9pp`) and the new worst is `polymarket/baseball/field 20.13→11.2pp` (med confidence) with `kalshi/hockey/field 9.1` and `kalshi/entertainment/quantity 15.5–18.5` nearby. **Nobody had named this mechanism before** — the queue's `−5 to −15` for exclusive fields assumed every field is a complete, liquid, winner-take-all partition normalized via `field_is_complete_for_normalization` (`precompute_calibration.py:631:650`). Baseball `field` shows that is false for a material share of the population. This scope ranks candidate mechanisms, gives the discriminating experiment for each, and states honestly what `GREEN ≤5pp` would even mean for a class this heterogeneous.*

---

## Ranked mechanisms

### 1. Incomplete-field evidence gap — `field_is_complete_for_normalization` excludes, so sum>1 persists

**Hypothesis:** `market_needs_mex_normalization` (`:566` ≥3 eligible, exactly 1 winner, `cp_sum>1.15`) + `field_is_complete_for_normalization` (`:631` survivor_n == eligible_n && survivor_n>=3 && survivor_win_n==1) is the only path that forces `sum=1` via `mex_field_divisor` (`:591`). Polymarket `field` `q≈n` single-winner partitions are *incomplete* when `eligible_n` includes low-volume tail outcomes that are later pruned (`is_liquid`, `volume!=0`, `no_pregame_trading` filters at `:1122:1205` before `deduped`). Incomplete fields are **excluded** from normalization (correctly — `survivor_n != eligible_n` would inflate survivors), so their raw `cp_sum 1.3–1.8` is scored bare. Kalshi `field` and Polymarket `soccer field` are more complete (fewer tail prunes, higher liquidity), so they normalize and drop `7–8pp`; Polymarket `baseball field` does not and stays `11pp`.

**What data refutes or confirms:** If `incomplete_share` on `polymarket/baseball/field` is `0.45–0.60`, the mechanism is sufficient — the residual *is* the unnormalized incomplete tail. If `incomplete_share <0.2`, the mechanism is insufficient and the residual lies elsewhere (liquidity).

**Discriminating experiment (header-only, read-only):**

```sql
-- Completeness census per (source, league, market_type='field')
WITH field_candidates AS (
  SELECT fm.id AS market_id, fm.source, COALESCE(fm.llm_sport_category,'uncategorized') AS league,
         COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) AS eligible_n,
         COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL AND fo.calibration_probability IS NOT NULL) AS survivor_n,
         COUNT(*) FILTER (WHERE fo.is_winner) AS survivor_win_n,
         SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) FILTER (WHERE fo.is_winner IS NOT NULL) AS cp_sum
  FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id
  WHERE fm.status='resolved' AND fm.market_type='field' AND fm.source IN ('polymarket','kalshi')
    AND COALESCE(fo.calibration_probability, fo.opening_probability) BETWEEN 0 AND 1
  GROUP BY fm.id, fm.source, COALESCE(fm.llm_sport_category,'uncategorized')
)
SELECT source, league,
       COUNT(*) AS markets,
       COUNT(*) FILTER (WHERE survivor_n = eligible_n AND survivor_n>=3 AND survivor_win_n=1 AND cp_sum>1.15) AS complete_and_overround,
       COUNT(*) FILTER (WHERE survivor_n != eligible_n) AS incomplete,
       ROUND(COUNT(*) FILTER (WHERE survivor_n != eligible_n)::numeric / COUNT(*),3) AS incomplete_share,
       ROUND(AVG(cp_sum),3) AS avg_cp_sum
FROM field_candidates GROUP BY source, league ORDER BY incomplete_share DESC;
-- Expectation: polymarket/baseball field incomplete_share 0.4–0.6 vs kalshi/baseball 0.15–0.25 vs polymarket/soccer 0.20–0.30.
-- Second cut: same census filtered to is_liquid / volume>0 to see if liquidity prunes drive incompleteness.
```

**If confirmed, the fix is not “normalize incomplete fields”** — that would inflate survivors (`:591:612` completeness warning). It is: (a) improve tail completeness at ingest (fill missing low-prob candidates so `survivor_n==eligible_n`), or (b) keep incomplete fields `NOT-PROVABLE` until complete, or (c) exception-registry the incomplete class after proving no other mechanism explains it (see §“what GREEN would mean”).

---

### 2. Low-liquidity tail miscalibration — Polymarket field includes a long tail of 0.01–0.05 runners scored at book mid

**Hypothesis:** Polymarket `field` markets have `n_tail` low-prob outcomes (`p 0.01–0.05`) with `volume≈0` and `calibration_probability = opening_probability = 0.02` (AMM mid). The `ECE` 10-bin `outcome-weighted` (`cohort_sweep.py:334`) aggregates `n` with `w=n`, so `0.02→0.00` on 15 tail runners contributes `15 * |0.02-0.00| / n` to `ECE`, while `kalshi/baseball/field` has fewer tails (exchange, not AMM) and `polymarket/soccer/field` has higher volume (World Cup tail not 0.01). The residual `11pp` is tail miscalibration: the market's long tail is systematically overconfident at `0.02` (true winrate `~0.005`), but each tail outcome is tiny individually, so the market *looks* fine while `ECE` sums the tail.

**What data refutes or confirms:** If `AVG(cp) FILTER (WHERE p BETWEEN 0.01 AND 0.05)` winrate is `~0.005` while `AVG(cp)` is `0.025` for `polymarket/baseball/field` but `AVG(cp)` winrate tracks for `kalshi/baseball/field`, the tail *is* the residual. If tail `ECE` is flat, mechanism is not tail.

**Discriminating experiment:**

```sql
-- Per-bucket winrate vs avg_prob for field tails (0-10% band)
WITH tail AS (
  SELECT fm.source, COALESCE(fm.llm_sport_category,'uncategorized') AS league,
         COALESCE(fo.calibration_probability, fo.opening_probability) AS p,
         fo.is_winner::int AS y, fm.volume
  FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id
  WHERE fm.status='resolved' AND fm.market_type='field'
    AND fm.source IN ('polymarket','kalshi') AND COALESCE(fm.llm_sport_category,'uncategorized')='baseball'
    AND COALESCE(fo.calibration_probability, fo.opening_probability) BETWEEN 0.01 AND 0.10
)
SELECT width_bucket(p,0,0.10,10) AS bucket, COUNT(*) AS n, ROUND(AVG(p),4) AS avg_p, ROUND(AVG(y),4) AS winrate, ROUND(AVG(p)-AVG(y),4) AS gap,
       COUNT(*) FILTER (WHERE COALESCE(volume,0)=0) AS zero_vol_n
FROM tail GROUP BY bucket ORDER BY bucket;
-- Also: volume decile split — is the 0.02→0.00 gap concentrated in zero-vol tails?
SELECT CASE WHEN COALESCE(volume,0)=0 THEN 'zero_vol' ELSE 'traded' END AS vol, COUNT(*) AS n, ROUND(AVG(p),4) AS avg_p, ROUND(AVG(y),4) AS winrate
FROM tail GROUP BY vol;
-- Expectation: polymarket/baseball zero_vol tail gap ≈+0.015 on n=800–1200 (tail ECE ≈1.5pp of total); kalshi/s soccer zero_vol tail n small and gap flat.
```

**If confirmed, the fix is liquidity-aware calibration:** tier `field` by `volume` or `is_liquid` per GoT #53 (polymarket `is_liquid` is asymmetric at `:1122:1205` — `is_liquid IS DISTINCT FROM false` vs kalshi `volume!=0`), or publish `ECE` with `volume`-weighted vs `n`-weighted twin (so a 0.02 tail with 0 vol does not dominate). This is *not* a normalization defect — it is a liquidity filter.

---

### 3. Capture-age hindsight — which-price `COALESCE(calibration_probability, opening_probability)` scored after late info (matrix cell 2D, same suspect as basketball survivor)

**Hypothesis:** Same `calibration_captured_at` lie as `METHODOLOGY_AUDIT §1` (KXNHLGOAL `0.99` bid class at `cp 0.995` real-bid slice `:1127:1141`, `cohort_sweep.py` 0.45–0.55 placeholder `BETWEEN`, `precompute_calibration.py:1649` `curve_price`). Polymarket `field` outcomes are winner-take-all, so a late `calibration_probability` that moved `0.35→0.95` after the game was decided would score `gap +0.05` not `−0.60` — but our residual is *overconfident* (`gap +20.13pp` in `table_market_type_light.md`: `pred 0.359 → actual 0.157`), not underconfident. Hindsight on fields would make ECE *smaller* (prices near 0/1 after known outcome), not `+11pp`. So capture-age is unlikely to explain a *positive* gap field residual, but it could explain a *negative* gap residual if prices moved toward outcome after the fact and were scored as foresight.

**What data refutes or confirms:** If `at_or_after_settlement` bucket on `polymarket/baseball/field` is `~0` or its `avg_gap` is `~0`, hindsight is not the driver. If `within_1h` bucket drives `+11pp`, it is.

**Discriminating experiment:**

```sql
-- Capture-age buckets per METHODOLOGY_AUDIT §1 SQL, filtered to polymarket/baseball/field
WITH aged AS (
  SELECT fo.id, fm.source, COALESCE(fm.llm_sport_category,'uncategorized') AS league, fm.market_type,
         COALESCE(fo.calibration_probability, fo.opening_probability) AS curve_price,
         fm.resolution_date, fm.commence_time,
         (SELECT MAX(s.captured_at) FROM futures_odds_snapshots s WHERE s.market_id=fm.id AND s.outcome_id=fo.id) AS last_price_at,
         fo.is_winner
  FROM futures_outcomes fo JOIN futures_markets fm ON fm.id=fo.market_id
  WHERE fm.status='resolved' AND fm.source='polymarket' AND COALESCE(fm.llm_sport_category,'uncategorized')='baseball' AND fm.market_type='field'
    AND COALESCE(fo.calibration_probability, fo.opening_probability) BETWEEN 0 AND 1
)
SELECT CASE WHEN last_price_at IS NULL THEN 'no_snapshot'
            WHEN last_price_at >= resolution_date THEN 'at_or_after_settlement'
            WHEN last_price_at >= resolution_date - INTERVAL '1 hour' THEN 'within_1h'
            WHEN last_price_at >= commence_time THEN 'in_game' ELSE 'pre_game' END AS bucket,
       COUNT(*) AS n, ROUND(AVG(curve_price),3) AS avg_p, ROUND(AVG(is_winner::int),3) AS winrate, ROUND(AVG(curve_price - is_winner::int),3) AS gap
FROM aged GROUP BY bucket ORDER BY MIN(COALESCE(last_price_at, '1970-01-01'::timestamptz));
-- Expectation: pre_game/in_game dominate; at_or_after_settlement bucket gap should be ~0 if not hindsight. If not, Fix 4 capture-age stamp is the next fix (rank 3 below).
```

**Rank:** `#3` because the sign is wrong for the observed `+20pp` gap (hindsight predicts `gap→0`, not `gap→+0.20`), but the same `which-price` class explained the basketball survivor (`METHODOLOGY_AUDIT §1` `KXNHLGOAL` 0.995), so it must be ruled out explicitly.

---

### 4. Genuine market noise at PM's liquidity — Polymarket `field` is noisier than Kalshi `field` at same stakes

**Hypothesis:** No defect — Polymarket `field` long tail is *truly* miscalibrated by `~11pp` because many `field` markets are low-stakes / niche (minor league baseball field 2828 vs `soccer field 11802` marquee) and the crowd's `p` is stale (AMM not traded). `ECE` `outcome-weighted` amplifies tail noise, but even `q`-weighted `ECE` (`Fix 3`) leaves `~10pp` after `−0.5` adjustment, so the market *is* the residual. This is the “*something new* is actually *nothing new* — the market is the artifact” bucket.

**What data refutes or confirms:** If `volume` decile split on `polymarket/baseball/field` shows `ECE` flat across volume deciles and `winrate` tracks `avg_p` only in high-volume decile, the low-volume tail is not a liquidity artifact but the market's own overconfidence — the residual is *real* and the fix is not a filter but a product decision (do not surface low-volume field tails in calibration gate). If `ECE` collapses in high-volume decile, it is mechanism 2, not 4.

**Discriminating experiment:**

```sql
-- ECE by volume decile (polymarket/baseball/field vs kalshi/baseball/field contrast)
WITH deciled AS (
  SELECT fm.source, NTILE(10) OVER (PARTITION BY fm.source ORDER BY COALESCE(fm.volume,0)) AS vol_decile,
         COALESCE(fo.calibration_probability, fo.opening_probability) AS p, fo.is_winner::int AS y
  FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id
  WHERE fm.status='resolved' AND fm.market_type='field' AND COALESCE(fm.llm_sport_category,'uncategorized')='baseball'
    AND fm.source IN ('polymarket','kalshi')
)
SELECT source, vol_decile, COUNT(*) AS n, ROUND(AVG(p),3) AS avg_p, ROUND(AVG(y),3) AS winrate
FROM deciled GROUP BY source, vol_decile ORDER BY source, vol_decile;
-- Expectation: if mechanism 4, polymarket vol_decile 1-3 gap >> kalshi 1-3 gap and high decile 8-10 gaps are similar (market noise, not liquidity).
```

**Rank:** `#4` because it is the residual hypothesis after `1` and `2` are instrumentally separated — it is unfalsifiable without volume truth (PM `volume` is `volume_24h` snapshot, not lifetime).

---

### 5. Selection / story-cap interaction — baseball `field` `n=2828` is a different population than `soccer field 11802`

**Hypothesis:** `polymarket/baseball/field` `n=2828` `pred 0.359` is a *low-p* field (many `p 0.05–0.15` tail runners) where `ECE` bins are empty in `0.40–1.00` and `reliability` is dominated by one `0.30–0.40` bucket with `n=800` (tail-bucket dominance, `METHODOLOGY_AUDIT §5` adaptive vs fixed-width). `polymarket/soccer/field` `n=11802` `pred 0.325` has a fuller `p` distribution. The `11pp` is a binning artifact: fixed-width 10-bin `ECE` on a `p 0.01–0.35` population has empty high bins that still contribute `w=0` but the headline `pred−actual` is read as miscalibration when it is shape.

**Discriminating experiment:**

```sql
-- Per-bucket n for polymarket/baseball/field (see if ECE is one bucket)
SELECT width_bucket(p,0,1,10) AS b, COUNT(*) AS n, ROUND(AVG(p),3) AS avg_p, ROUND(AVG(y),3) AS winrate
FROM (SELECT COALESCE(fo.calibration_probability, fo.opening_probability) AS p, fo.is_winner::int AS y
      FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id
      WHERE fm.status='resolved' AND fm.source='polymarket' AND COALESCE(fm.llm_sport_category,'uncategorized')='baseball' AND fm.market_type='field') s
GROUP BY b ORDER BY b;
-- Also: adaptive (quantile 10 equal-mass) ECE vs fixed-width ECE on same population — if adaptive ECE is ~5pp and fixed is ~11pp, it is binning, not market.
```

**Rank:** `#5` — lowest, because `ECE` is `n`-weighted and `brier/reliability` would show the same tail dominance, but the gate's `MCE ≤5.0pp` would still trip on one bucket.

---

## What `GREEN ≤5.0pp` would even mean for cells this class covers

A `polymarket/baseball/field` cell is not one market — it is `~2828` outcomes across `~500–800` marquee games + `~2000` tail/props, incomplete fields mixed with complete, zero-vol tails mixed with traded, pre-game `p` mixed with late `p`. `GREEN` as a single number on that mixture is not a product claim — it is a population average that hides the same tail/incompleteness that caused `11pp`.

Honest `GREEN` for this class therefore means **one of:**

* **Complete-only GREEN:** the cell's `complete_and_overround` subpopulation (`survivor_n==eligible_n && survivor_n>=3 && cp_sum>1.15`, `:631:650`) is `≤5pp` and `n_complete≥1000`, while the `incomplete` subpopulation is `NOT-PROVABLE` or exception-registered (see below) — not averaged in. This is the `field_is_complete_for_normalization` contract's own definition of the cohort it can rate. If completeness is the mechanism (§1), `GREEN` is “the complete field curve is calibrated; the incomplete field curve is not on the gate.”

* **Liquid-only GREEN:** the `volume>0` or `is_liquid` subpopulation is `≤5pp` and the `zero_vol` tail is `NOT-PROVABLE` or exception-registered — `volume` truth is per the GoT asymmetry (`kalshi volume!=0` vs `polymarket is_liquid DISTINCT FROM false`). If liquidity is the mechanism (§2), `GREEN` is “the traded field curve is calibrated; the unt traded AMM mid tail is not on the gate.”

* **No GREEN without the stamp:** if capture-age is the mechanism (§3), `GREEN` would be meaningless until `calibration_captured_at` (`Fix 4`, 10+ write sites) exists and `at_or_after_settlement` bucket is `0`. Declaring `GREEN` before the stamp is declaring hindsight-correct prices as foresight-calibrated.

### Exception-registry candidates (named as such)

Under the gate's “`GREEN` or `NOT-PROVABLE-with-a-plan` or registered exception” contract (`docs/LAUNCH-LEDGER.md` Gate 1), these are the candidates to *register*, not celebrate:

* `polymarket/baseball/field` **incomplete subpopulation** — if `incomplete_share 0.4–0.6` and `ECE_incomplete − ECE_complete ≥5pp`, the incomplete subpopulation is an exception candidate: `reason: incomplete field (survivor_n != eligible_n; tail candidates missing; n-way divisor not applied per :591:612)`, `flip_condition: ingest completes tail candidates so survivor_n==eligible_n or field is re-tagged participation`. Do **not** average it into the complete curve.

* `polymarket/baseball/field` **zero-vol tail** — if zero-vol `ECE` drives the headline, the `p 0.01–0.05` zero-vol tail is an exception candidate: `reason: AMM mid with volume≈0 (untraded tail; go/no-go on is_liquid)` , `flip_condition: volume-gated calibration or lifetime volume truth`. Publish `ECE_traded` vs `ECE_zero_vol` as the `5000.00` display-correct `ece_pp` twin (Fix 7).

* `polymarket/baseball/unknown` (the 2011 `unknown` market_type row `n=2219 11.3→11.2` in the predicted table rank 16) — **always** an exception candidate: `unknown` semantics are `market_shape.py` `unshaped` (0/1 outcome, incomplete) and should be `NOT-PROVABLE`, not `RED` — its `GREEN` would be dishonest.

No exception is `GREEN`. Gate 1 stays `RED` while any sizable cell (or its complete/liquid slice) is `RED` without a plan, per `MACHINE_FIX_QUEUE.md` re-baseline protocol (`heavy sentinel MCE ≤5.0pp && cohort GREEN ≤5pp vs NOT-PROVABLE`). The residual `11pp` is finishable as “complete field `≤5pp`, incomplete/zero-vol `exception` with a dated plan” — not as a single `11→4pp` on the mixed population.

---

## How the real re-baseline grades this scope

Same tier-by-tier protocol as `PREDICTED_REBASELINE.md` §“What the real re-baseline will recompute,” plus one row per mechanism above: after each tier, re-run the mechanism's discriminating SQL (read-only, header-only dyno). Required movements:

* After Tier 1+2 (provenance + market-weighted): `polymarket/baseball/field` `20.13→11.2` — residual is now the gate.
* After Tier 5 (field completeness census): `incomplete_share` on `polymarket/baseball/field` vs `polymarket/soccer/field` vs `kalshi/baseball/field` — if `0.4–0.6` vs `0.20–0.30` vs `0.15`, mechanism 1 is the driver and the gate's next commit is **completeness or exception**, not another `−8pp` divisor.
* After Tier 6 (volume decile): zero-vol `ECE` vs traded `ECE` on same cell — if `zero_vol` `Δ` drives `11pp`, mechanism 2 is the driver and the gate's next commit is **liquidity-aware cohort split**, not hindsight.
* After Tier 3 (capture-age): `at_or_after_settlement` bucket `0` — if not, Fix 4 is still 0pp and mechanism 3 is not ruled out.
* Final: publish `before.json` vs `after.json` with **twin curves** `ECE_complete` and `ECE_traded` alongside `ECE_all` and `ECE_incomplete`/`ECE_zero_vol` so “fixed” is proven on the *rateable* subpopulation, not hidden in the mixed `11pp`.

*This scope + the adjudicated table are the acceptance target the real re-baseline is graded against; prediction first, then the build, per ruling 050 at program scale.*

