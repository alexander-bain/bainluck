# Provenance Split — venue-graded rows only vs all rows per worst shape cell

*Generated 2026-08-17, branch codex-adhoc/cohort-views, read-only. DB network-blocked from this runner (heroku pg:psql → EPERM), so this artifact ships the exact queries + the decision rule + the light-table baseline. The heavy build (POST /api/admin/cohort-market-type/build) will fill the venue-graded numbers once landed.*

## The experiment that picks the fix

For each of the worst shape cells (polymarket quantity/container_member by league, light ECE 30–50pp), recompute ECE **twice**:

* **All rows** — as published today (includes 226k never-graded PM markets where `is_winner=false` is a column default, `resolution_source IS NULL`)
* **Venue-graded only** — `resolution_source IS NOT NULL` (`api_settlement`, `game_score`, `chain`, etc. — populated only when a venue actually graded the outcome)

Also report **NULL-default share** per cell: `ungraded / total` where `ungraded = resolution_source IS NULL`.

**Decision rule (per launch ledger #1912):**

* If the 30–50pp **collapses** on venue-graded-only (e.g., ECE_all ≈ 40pp → ECE_venue ≈ 5–10pp, graded_share ≈ 20–30%), the overconfidence is **our fabricated-grade artifact** — we scored 0.50 predictions as losses because we defaulted `false`. The approved backfill (#1912 — set `is_winner` only from venue settlement, leave ungraded as NULL and exclude from calibration) is the fix.
* If it **survives** venue-graded-only (ECE_venue ≈ 30–50pp, graded_share ≈ 70–90%), it's a **real normalization defect** — ladders treated as independent binaries at raw price, not a provenance artifact. Then the fix is the sums-to-1 normalization (see next artifact).

## Light baseline (all rows, from table_market_type_light.md, n≥30)

| rank | league | market_type | n_all | ECE_all | gap_all | graded_share* |
|---:|---|---|---:|---:|---:|---:|
| 1 | table_tennis | quantity | 2,880 | 50.00 | +50.00 | 0.18 |
| 2 | table_tennis | container_member | 2,313 | 49.95 | +49.95 | 0.21 |
| 4 | soccer | quantity | 12,819 | 44.66 | +44.66 | 0.27 |
| 6 | basketball | container_member | 405 | 40.51 | +40.51 | 0.31 |
| 7 | tennis | container_member | 4,789 | 38.07 | +38.07 | 0.29 |
| 10 | tennis | quantity | 6,166 | 37.14 | +36.85 | 0.33 |
| 11 | baseball | container_member | 1,013 | 36.99 | +34.01 | 0.35 |
| — | soccer | container_member | 7,064 | 24.12 | +24.12 | 0.41 |
| — | baseball | quantity | 2,386 | 29.31 | +27.22 | 0.38 |

*graded_share estimated from `total_n` vs `graded_n` in the light 200k sample; heavy deduped CTE will refine. The 226k never-graded PM markets are concentrated here — these cells have the lowest graded_share.*

## Exact SQL (run on a Heroku one-off dyno or via the new admin endpoint after landing)

```sql
-- Provenance split per worst cell: polymarket quantity/container_member by league
WITH base AS (
  SELECT fm.source, COALESCE(fm.llm_sport_category,'uncategorized') AS league,
         COALESCE(fm.market_type,'unknown') AS market_type,
         COALESCE(fo.calibration_probability, fo.opening_probability) AS prob,
         fo.is_winner,
         fo.resolution_source
  FROM futures_outcomes fo
  JOIN futures_markets fm ON fm.id = fo.market_id
  WHERE fm.status='resolved'
    AND fm.source='polymarket'
    AND fm.market_type IN ('quantity','container_member')
    AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
    AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
    AND fo.opening_probability IS NOT NULL
    AND fo.is_winner IS NOT NULL
)
SELECT league, market_type,
       COUNT(*) AS n_all,
       COUNT(*) FILTER (WHERE resolution_source IS NOT NULL) AS n_venue,
       COUNT(*) FILTER (WHERE resolution_source IS NULL) AS n_default,
       ROUND(COUNT(*) FILTER (WHERE resolution_source IS NULL)::numeric / COUNT(*), 3) AS null_default_share,
       -- ECE computed in Python (10 bins, n-weighted) per cohort, once for n_all and once for n_venue
       -- See scripts/evals/cohort_sweep.py: expected_calibration_error()
       COUNT(*) FILTER (WHERE resolution_source IS NOT NULL)::float / COUNT(*) AS graded_share
FROM base
GROUP BY league, market_type
HAVING COUNT(*) >= 30
ORDER BY null_default_share DESC, n_all DESC;
```

```sql
-- Venue-graded-only ECE: same CTE but with WHERE resolution_source IS NOT NULL
-- Run the Python ECE calc on the filtered rows; compare to the unfiltered ECE from above.
-- The heavy CTE (app.tasks.precompute_calibration._calibration_population_ctes) already
-- carries resolution_source, so the cohort_sweep can add a `provenance='venue'` flag
-- without re-implementing the population.
```

## What to expect and how to read it

* **If null_default_share ≈ 0.70–0.85** in the top cells (table_tennis, soccer quantity) and **ECE_venue drops to ≤10pp** while **ECE_all ≈ 40–50pp**, the 30–50pp is a **provenance artifact**. The 226k defaults (is_winner=false at 0.50) create a fake 0.50→0.00 gap. The fix is provenance: exclude `resolution_source IS NULL` from calibration (or backfill via #1912) — do not re-normalize.

* **If null_default_share ≈ 0.20–0.40** and **ECE_venue ≈ 30–50pp** (survives), the overconfidence is **not** from defaults — it's a **normalization defect** (ladders at raw price sum >1, so each rung at 0.50 is really ~0.10 after normalization). Then the fix is the sums-to-1 histogram (next artifact) → exclusive-sum-to-1 per group.

* **Current light graded_share (≈0.18–0.41)** suggests the top cells are **heavily default-dominated**, so the collapse hypothesis is plausible — but the venue-graded-only run is the decider. This artifact will be updated with the two ECE numbers per cell once the heavy build is queryable via `GET /api/admin/cohort-provenance-split` (added in the same branch, header-only auth).

## Status

* SQL ready, decision rule ready, light baseline ready.
* Venue-graded numbers: **pending DB run** (network-blocked here, will be filled post-land via the heavy queue or a one-off dyno). The commit that adds `GET /api/admin/cohort-provenance-split` is alongside this artifact, so the next `heroku run` can populate it without a second code change.
