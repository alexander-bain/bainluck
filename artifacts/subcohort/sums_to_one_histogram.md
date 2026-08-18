# Sums-to-1 Check — Σ(member probabilities) per market/event group (Polymarket container_member/quantity)

*Generated 2026-08-17, branch codex-adhoc/cohort-views. Meaningful only if the provenance split survives venue-graded-only (i.e., ECE stays 30–50pp after excluding defaults). If the provenance split collapses, this histogram is not the fix — the backfill is.*

## Why this histogram is the normalization defect made visible

A ladder market (e.g., "How many X?" with thresholds ≥1, ≥2, ≥3 … or a roster container with members A/B/C …) is **one question with exhaustive, mutually exclusive rungs** — exactly one threshold will hit / one member will win. If each rung/member is treated as an **independent binary at raw price** (e.g., each at 0.50), the group sums to **≫1** (e.g., 5 rungs × 0.50 = 2.50). After proper **exclusive-sum-to-1 normalization** (divide each rung's price by the group's sum, or capture the group's joint distribution), each rung's calibrated probability drops (0.50 → 0.20 in the 5-rung example) and the 30–50pp overconfidence collapses.

This check computes **Σ p_i per group** (market `group_id` or `event_id` grouping — whichever the poller used) using the **curve price** (`COALESCE(calibration_probability, opening_probability)`) that the calibration curve actually scores. A histogram centered at 1.0 is healthy; a mass at 2–5 is the defect.

## Exact SQL (Polymarket container_member/quantity groups)

```sql
-- Per-group sum of member probabilities (Polymarket ladders)
WITH group_sums AS (
  SELECT fm.group_id,
         fm.event_id,
         fm.id AS market_id,
         COUNT(*) AS members,
         SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob,
         AVG(COALESCE(fo.calibration_probability, fo.opening_probability)) AS avg_prob,
         -- venue-graded flag for the group (if any member is venue-graded)
         BOOL_OR(fo.resolution_source IS NOT NULL) AS has_venue_grade
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.status='resolved'
    AND fm.source='polymarket'
    AND fm.market_type IN ('container_member','quantity')
    AND COALESCE(fo.calibration_probability, fo.opening_probability) > 0
    AND COALESCE(fo.calibration_probability, fo.opening_probability) < 1
    AND fo.opening_probability IS NOT NULL
    AND fo.is_winner IS NOT NULL
  GROUP BY fm.group_id, fm.event_id, fm.id
  -- For true ladder groups, prefer fm.group_id; for single-market containers, event_id groups are small and sum≈1 anyway
),
-- Also compute per-event-group sums (when group_id is present, event groups are the ladder)
event_sums AS (
  SELECT COALESCE(fm.group_id::text, 'event:'||fm.event_id::text) AS group_key,
         COUNT(*) AS members,
         SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_prob
  FROM futures_markets fm
  JOIN futures_outcomes fo ON fo.market_id = fm.id
  WHERE fm.status='resolved'
    AND fm.source='polymarket'
    AND fm.market_type IN ('container_member','quantity')
    AND fo.resolution_source IS NOT NULL  -- venue-graded only, if provenance survives
  GROUP BY group_key
)
SELECT
  -- Histogram buckets for sum_prob: 0–1, 1–1.5, 1.5–2, 2–3, 3–5, 5+
  CASE
    WHEN sum_prob < 1.0 THEN '0–1.0 (under)'
    WHEN sum_prob < 1.5 THEN '1.0–1.5 (slightly over)'
    WHEN sum_prob < 2.0 THEN '1.5–2.0 (over)'
    WHEN sum_prob < 3.0 THEN '2.0–3.0 (ladder)'
    WHEN sum_prob < 5.0 THEN '3.0–5.0 (strong ladder)'
    ELSE '5.0+ (extreme ladder)'
  END AS bucket,
  COUNT(*) AS groups,
  ROUND(AVG(sum_prob),2) AS avg_sum,
  ROUND(AVG(members),1) AS avg_members,
  -- Example group for inspection
  MIN(group_key) AS example_group
FROM event_sums
GROUP BY bucket
ORDER BY MIN(sum_prob);
```

```sql
-- Per-group size distribution (how many groups have 2,3,4,5+ members)
SELECT members, COUNT(*) AS groups,
       ROUND(AVG(sum_prob),2) AS avg_sum,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY sum_prob),2) AS median_sum
FROM event_sums
GROUP BY members
ORDER BY members;
```

## What to look for

* **Healthy (already normalized or truly independent):** median `sum_prob` ≈ 1.00, 90th percentile ≤1.20, independent of `members`. `container_member` with `members=10` still sums ≈1.0.
* **Ladder defect (raw binary prices):** `sum_prob` grows with `members` — e.g., `members=2 → sum≈1.0`, `members=3 → sum≈1.5`, `members=5 → sum≈2.5`, `members=10 → sum≈5.0`. Histogram mass in buckets `2.0–3.0` and `3.0–5.0`. This is the smoking gun.

## Expected shape (from light-table ECE)

The light ECE of 30–50pp at ~0.50 predicted implies the **true** per-rung probability after normalization is ~0.00–0.20, so the **implied sum** is ~2.5–5.0. That is, a 5-rung quantity ladder at 0.50 each sums to 2.50, which is exactly the histogram this query will show if the defect is real. The venue-graded-only provenance split decides whether to run this at all — but the SQL is ready to run in one `heroku pg:psql` or via `GET /api/admin/cohort-sums-histogram` (header-only auth, added alongside the provenance endpoint).

## Status

* SQL ready, interpretation ready.
* Histogram: **pending DB run** (same network block as above; will be filled post-land). If provenance collapses, this file will be updated to "not meaningful — backfill is the fix" and the histogram will not be treated as the defect.
