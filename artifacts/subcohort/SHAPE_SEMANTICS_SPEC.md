# Shape Semantics Spec — exclusivity, correct treatment, and the sums-to-1 trap

*Branch `codex-adhoc/cohort-views` at `e151007a` → `05277cba`. No product code; this spec is the calibration lane's fix-queue input alongside the provenance split. Every market shape in the codebase is classified by its probabilistic exclusivity, with the classifier code cited, the correct treatment, the violation census SQL (header-only, post-merge), and the reconciliation with the sums-histogram that was shipped on the same branch. The trap this exists to prevent: threshold ladders (quantity: Over 7.5/8.5/9.5) are **cumulative** and `sum(p) > 1` is **correct** for them — blanket sum-to-1 would corrupt them.*

## 0. Vocabulary and where it lives

Display shapes are the `market_type` enum in `backend/app/utils/market_shape.py:59-65` (`claim | quantity | duel | field | participation | container_member | unshaped`) and `backend/app/models/models.py:700` / `:1326-1330`. Probabilistic semantics are the `outcome_relation` enum in `backend/app/utils/market_shape.py:90-96` (`complements | competitors | cumulative_thresholds | exclusive_ranges | independent_participation | conditional | unknown`) plus `exhaustive`, `expected_winners`, `push_void_capable` (`:537-544`). The single source of truth is `backend/app/utils/market_shape.py:253` `classify_market_shape` (display geometry) and `:470` `classify_market_semantics` (full contract, v2 via `CLASSIFIER_VERSION=2` `:88`), with pure-function helpers `:_looks_like_quantity` (`:196-215`), `:_is_yes_no` (`:186-189`), `:_is_participation` (`:218-226`), and `:_outcome_relation` (`:360-467`) that decides the relation from outcome names + `group_id`/`group_size` + `source_kind`/`expected_winners`/`mutually_exclusive`. Census-derived comments enumerate the shapes (`:36-46`) and the 2026-07-14 census that found `market_type` 100% NULL and `mutually_exclusive` TRUE for both claims and duels (`:3-8`), so shape must be inferred, not read.

Calibration's field-normalization branch is gated not on `market_type='field'` alone but on the *persisted* semantics `shape.exhaustive=true AND shape.expected_winners=1 AND outcome_relation='competitors'` (`backend/app/tasks/precompute_calibration.py:998-1010` "only sets `exhaustive` when the source proves it — never inferred from `>2`", `:1028-1036` "the persisted shape classifier (market_type='field' AND shape.exhaustive=true AND expected_winners=1 AND exclusive relation), not the `mutually_exclusive` DEFAULT TRUE"). The 51,424 `field`/`unknown`/`exhaustive` NULL, 27,958 cumulative-threshold ladders (`exhaustive=false`, gotcha #17), and 31,197 `field/competitors/exhaustive=true/1` counts there are the census.

## 1. Classify every market shape by exclusivity semantics (cite the classifier)

| Display shape `market_type` | Typical outcome names | `group_id` / `group_size` | `outcome_relation` | `exhaustive` | `expected_winners` | Exclusivity class | Classifier cite |
|---|---|---|---|---|---|---|---|
| **claim** | `Yes` / `No` (single question) | lone, `group_size=1` | `complements` | `true` (`:397-400` `yes_no_pair`) | `1` | **MUTUALLY-EXCLUSIVE** (Yes+No are complements, sum≈1) | `market_shape.py:306-310` `n==2 && _is_yes_no` → `claim` |
| **duel** | `Team A` / `Team B` (or with `Draw`) | lone | `competitors` (or with draw) | `bool(mutually_exclusive)` (`:437-438`) | `1` if MX | **MUTUALLY-EXCLUSIVE** (exactly one named competitor wins; `mutually_exclusive` proves it) | `market_shape.py:311-312` `n==2 && !yes_no` → `duel`; `:_outcome_relation` `:436-441` competitors |
| **field** | `>2` named competitors (`Horse A/B/C…`) | lone or `group_id` but `display_shape` is `field` (not member) | `competitors` | `true` only when `mutually_exclusive==True && ew==1` (`:457-458`, `:998-1010` census) | `1` | **MUTUALLY-EXCLUSIVE** (single-winner partition; `market_needs_mex_normalization` `:566-588` requires `n_eligible≥3 && n_winners==1 && cp_sum>threshold`) | `market_shape.py:314-319` `>2` + `!participation` → `field`; `:_outcome_relation` `:444-458` |
| **participation** | `Top 5`, `Make Cut`, `Qualify` (DataGolf `top_5`, `make_cut`, Kalshi `top_N` suffix) | lone | `independent_participation` | `false` (`:422-423`) | `>1` (`:224-225` `>1` or `_TOP_N_RE`) | **INDEPENDENT** (many winners; probabilities do not sum to 1) | `market_shape.py:317-318` `_is_participation` → `participation`; `:_outcome_relation` `:421-425` |
| **quantity** | Numeric ladder: `Over 7.5`, `Over 8.5`, `≥75`, `100-150`, `0-10` (majority of named outcomes are numeric `:196-215` `numeric >=2 && >=½`) | lone market with `k` outcomes (a *group* in one market) or `group_id` with `k` markets each 2-outcome Over/Under per threshold | **Either `cumulative_thresholds` or `exclusive_ranges` depending on names**: `cumulative` if `≥2` outcomes match `_CUMULATIVE_RE` (`:144-147` `>=|at least|over|or more`) *and* `_NUMBER_RE` (`:414-417`), else `exclusive_ranges` if `≥2` match `_RANGE_RE` (`:138-139` `100-150`) (`:426-435`) | `false` for `cumulative` (`:433`), `bool(MX)` or `None` for `ranges` (`:428`) | `None` or `1` | **Split class**: `cumulative_thresholds` → **CUMULATIVE** (non-exclusive; a later rung implies earlier ones); `exclusive_ranges` → **MUTUALLY-EXCLUSIVE** (bins, one holds) | `market_shape.py:292-296` quantity check before duel/field; `:_outcome_relation` `:426-435` |
| **container_member** | `Yes`/`No` sub-market of a decomposed field (Polymarket nested `condition_id`, 72-member Presidential run) | `group_id` present, `group_size>1`, `n==2`, `yes_no` (`:298-303`) | `complements` *per member* (Yes vs No of that member), but the *container* `group_id` is `competitors` | `true` per member (Yes+No complement), but the container's exhaustiveness is the field's | `1` per member (Yes+No) | **MUTUALLY-EXCLUSIVE at both levels**: each member's Yes+No sums≈1, and the *container's* `YES` legs across members are `competitors` (exactly one member's YES wins; the group's YES probs sum≈1). The current `group_id` grouping in the sums-histogram (`admin_cohort.py:330` `COALESCE(group_id, event_id)`) measures the container's YES-sum. | `market_shape.py:298-303` `group_id && group_size>1 && n==2 && yes_no` → `container_member` |
| **unshaped** | 0/1 outcome, incomplete | any | `unknown` (`:394-395`) | `None` | `None` | **UNKNOWN — exclude from calibration** | `market_shape.py:286-290` `n<2` → `unshaped` |

The trap is in the `quantity` row: a quantity market whose outcomes are `Over 7.5`, `Over 8.5`, `Over 9.5` is `REL_CUMULATIVE` (`cumulative` count ≥2, `:431-432`), `exhaustive=false`, and `sum(p) > 1` is **correct by semantics** — a later threshold implies all earlier ones (if `≥9.5` then necessarily `≥8.5` and `≥7.5`). A quantity market whose outcomes are `0-10`, `11-20`, `21-30` is `REL_RANGES` (`range_count ≥2`, `:426-428`), `exhaustive` = `bool(MX)`, and `sum(p) ≈ 1` is correct. The `quantity` display shape alone does not tell you which — the outcome names do (`_CUMULATIVE_RE` vs `_RANGE_RE`).

## 2. Per class, the correct treatment

**MUTUALLY-EXCLUSIVE** — `claim` (`complements`), `duel`/`field` (`competitors` + `exhaustive=true`/`ew=1`), `exclusive_ranges` bins, and the container-member container (`competitors` across YES legs).

- Invariant: `sum(p) ≈ 1` (after de-vig). Each market/group is one distribution.
- De-vig: **n-way** `remove_vig_nway` (`backend/app/utils/odds_math.py:47-106` proportional `p_i / sum(p)`, sums to 1.0, returns `None` on `None`/negative/non-finite) on the *group's* `k` raw book probabilities, not per-outcome. This is the standing rule at `:66-68` "raw vig-inclusive book prices NEVER enter probability arithmetic", exercised in `devig_consensus` (`:174-178` per-book `remove_vig_nway([column[k] for k in keys])`).
- Calibration normalization: the field branch (`precompute_calibration.py:566-588` `market_needs_mex_normalization`) *is* this class, applied read-side via `mex_field_candidates` → `field_completeness` → `mex_field_divisor` (`:591-644` completeness: `survivor_n==eligible_n && survivor_win_n==1 && survivor_n≥3`; survivor `cp / cp_sum`). Only when `shape_exhaustive=true && expected_winners=1 && competitors` (`:998-1010`).
- What is wrong today: fields are handled there; `claim`/`duel` are two-way and already sum≈1 after book de-vig; `exclusive_ranges` quantity bins are currently scored at raw price and would benefit from the same n-way normalization if the group's `exhaustive` were proven.

**CUMULATIVE** — `quantity` with `REL_CUMULATIVE` (threshold ladders: Over `N`, At least `N`, `Or More`, `≥N`).

- Invariant: **per-rung `YES+NO` overround ≈0, and monotonicity `p_i` decreases as threshold rises** (`p(Over 7.5) ≥ p(Over 8.5) ≥ p(Over 9.5)`), **never `sum(p)≈1`**. `sum(p)` of `k` cumulative thresholds *should* be >>1 (e.g., 3 rungs at 0.60 each → sum 1.80 is correct; they are not exclusive).
- De-vig: **per-rung two-way** `remove_vig` / `remove_vig_nway([yes_p, no_p])` on each threshold's *own* YES/NO book column (`odds_math.py:109-125` two-way wrapper), not across rungs. The group never gets an n-way divisor. This is the `cumulative` counter-class at `precompute_calibration.py:542-544` "EXACTLY ONE winner. Cumulative-threshold ladders (`Over 3.5 maps` + `Over 4.5` …) … multi-winner … `n_winners>1` is CORRECT for cumulative ladders" and `:785-796` "Total Kills Over/Under ladders (Over 17.5, 18.5 …) resolves with `≥2` winners. Because the Over rungs are cumulative, many YES are legitimate".
- What is wrong today: the curve scores each rung at raw `curve_price = COALESCE(calibration_probability, opening_probability)` (`precompute_calibration.py:1649`) as an independent binary without checking per-rung overround or monotonicity — the "ladder" ECE 30–50pp on `quantity` in `traded_vs_untraded_by_shape.md` (50.00, 44.66) is partly this, but the *sum* is not the diagnostic — violation is a rung's `YES+NO ≠1` or a monotonicity flip.

**INDEPENDENT** — `participation` (`Top 5`, `Make Cut`, `Qualify`, `independent_participation`) and any `REL_UNKNOWN`.

- Invariant: **no cross-outcome invariant**. Each outcome is its own question; `sum(p)` is meaningless (Top 5 can have 5 winners at 0.40 each → sum 2.0 correct).
- De-vig: **per-market two-way only** if the outcome itself has a YES/NO book; never across outcomes. The sweep and curve already treat these as `INDEPENDENT` (`market_shape.py:421-425`) and the calibration branch excludes them from field normalization (`precompute_calibration.py:560` "binaries (2+ winners) and voids are the counter-class and left …").
- What is wrong today: nothing on this class — the quantity 30–50pp is *not* from `participation` (it is `quantity`/`container_member`), but `participation` markets that happen to be `market_type='field'` without `exhaustive=true` must stay out of the `field` cohort (they already do via `:314-318` split and `:998-1010`).

## 3. Per class, the violation census SQL (post-merge, header-only)

All are read-only, header-only `Authorization: Bearer` via `GET` or a one-off dyno. Run via the worktree's new endpoints (`/api/admin/cohort-sums-histogram` already covers the exclusive case) or the SQL below.

### Exclusive class — sum(p) defect (container_member containers + field + exclusive_ranges bins)

```sql
-- Exclusive groups: sum should be ≈1. Histogram buckets are DEFECT when sum≫1.
-- Groups are COALESCE(group_id, event_id) for containers, and per-market for field/bins.
-- Header-only: curl -H "Authorization: Bearer $ADMIN_TOKEN" https://api.bainluck.com/api/admin/cohort-sums-histogram
-- Manual:
SELECT bucket, COUNT(*) AS groups, ROUND(AVG(sum_p),2) AS avg_sum, ROUND(AVG(members),1) AS avg_members
FROM (
  SELECT COALESCE(fm.group_id::text, 'event:'||fm.event_id::text) AS g,
         COUNT(*) AS members,
         SUM(COALESCE(fo.calibration_probability, fo.opening_probability)) AS sum_p,
         MAX((fm.market_metadata->'shape'->>'outcome_relation')) FILTER (WHERE true) AS rel
  FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id
  WHERE fm.status='resolved' AND fm.market_type IN ('field','container_member')  -- exclusive display shapes
    AND COALESCE(fo.calibration_probability, fo.opening_probability) BETWEEN 0 AND 1
    AND fo.is_winner IS NOT NULL
    -- restrict to exclusive semantics: container containers + field with exhaustive=true
    AND (fm.market_metadata->'shape'->>'outcome_relation' IN ('competitors','complements') OR fm.market_type='field')
  GROUP BY g HAVING COUNT(*)>=2
) s
CROSS JOIN LATERAL (
  SELECT CASE WHEN sum_p<0.9 THEN '0–0.9 (under, missing members?)'
              WHEN sum_p<1.1 THEN '0.9–1.1 (healthy)'
              WHEN sum_p<1.5 THEN '1.1–1.5 (mild overround)'
              WHEN sum_p<2.0 THEN '1.5–2.0 (over)'
              WHEN sum_p<3.0 THEN '2.0–3.0 (defect)'
              ELSE '3.0+ (strong defect)' END AS bucket
) b
GROUP BY bucket ORDER BY MIN(sum_p);
-- Expect: healthy single block at 0.9–1.1 for exclusive; mass in 1.5+ is the defect (un-normalized field or container YES-sum >1).
-- Per-size: SELECT members, COUNT(*), AVG(sum_p) FROM (...) GROUP BY members ORDER BY members;
-- members=5 → median_sum≈1.0 is healthy; ≈2.5 is the old sums-to-1 bug on containers.
```

### Cumulative class — monotonicity + per-rung YES+NO overround

```sql
-- Cumulative ladders: sum>1 is CORRECT. Violations are monotonicity flips and per-rung YES+NO≠1.
WITH ladder AS (
  SELECT fm.id AS market_id, fm.group_id, fm.event_id,
         fo.outcome_name, fo.id AS outcome_id,
         COALESCE(fo.calibration_probability, fo.opening_probability) AS p,
         -- Extract numeric threshold for ordering (best-effort; NULL if not parseable)
         NULLIF((regexp_match(fo.outcome_name, '([0-9]+(?:\.[0-9]+)?)'))[1], '')::float AS threshold,
         -- Per-outcome YES+NO overround: need both sides. We have per-outcome p; per-rung YES+NO requires the market's other side.
         -- For a 2-outcome Over/Under ladder market per threshold, this is the market's sum; for a single OUTCOME of a decomposed ladder, skip.
         COUNT(*) OVER (PARTITION BY fm.id) AS market_outcomes
  FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id
  WHERE fm.status='resolved' AND fm.market_type='quantity'
    AND COALESCE(fo.calibration_probability, fo.opening_probability) BETWEEN 0 AND 1
    AND (fm.market_metadata->'shape'->>'outcome_relation')='cumulative_thresholds'
)
, per_market_overround AS (
  SELECT market_id, SUM(p) AS yes_no_sum, COUNT(*) AS n
  FROM ladder GROUP BY market_id HAVING COUNT(*)=2
)
SELECT 'per_rung_YES+NO' AS check,
       CASE WHEN yes_no_sum BETWEEN 0.9 AND 1.1 THEN '0.9–1.1 (healthy)'
            WHEN yes_no_sum <0.9 THEN 'under'
            WHEN yes_no_sum <1.2 THEN '1.1–1.2 (mild vig)'
            ELSE '1.2+ (defect: un-de-vigged book price on rung)' END AS bucket,
       COUNT(*) AS markets
FROM per_market_overround GROUP BY bucket ORDER BY MIN(yes_no_sum);

-- Monotonicity: p must decrease as threshold rises.
WITH ordered AS (
  SELECT group_id, threshold, p, outcome_name,
         LAG(p) OVER (PARTITION BY COALESCE(group_id::text, 'm:'||market_id::text) ORDER BY threshold) AS prev_p
  FROM ladder WHERE threshold IS NOT NULL
)
SELECT COUNT(*) AS ladder_rungs_checked,
       COUNT(*) FILTER (WHERE p > prev_p + 0.01) AS violations,  -- 1pp tolerance
       ROUND(100.0*COUNT(*) FILTER (WHERE p > prev_p + 0.01)/COUNT(*),2) AS violation_rate_pct,
       COUNT(DISTINCT group_id) FILTER (WHERE p > prev_p + 0.01) AS groups_with_violation
FROM ordered WHERE prev_p IS NOT NULL;
-- Expect: violation_rate ≈0 is healthy; any violation is the ladder defect (thresholds out of order or scored at stale post-settlement price — see METHODOLOGY_AUDIT §1 hindsight).
```

### Independent class — no cross-outcome invariant; just count that we do not normalize

```sql
-- Independent (participation) — no sum invariant. Census that we indeed never normalize it.
SELECT COALESCE(fm.llm_sport_category,'uncategorized') AS league,
       fm.market_type, COUNT(*) AS outcomes,
       COUNT(DISTINCT fm.id) AS markets,
       AVG((fm.market_metadata->'shape'->>'expected_winners')::int) AS avg_expected_winners
FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id
WHERE fm.status='resolved' AND fm.market_type='participation'
GROUP BY league, market_type ORDER BY outcomes DESC;
-- Expect: avg_expected_winners >1; no normalization applied (correct). If any participation market was ever routed through market_needs_mex_normalization, that is the bug.
```

## 4. Reconcile with your sums-histogram design

The branch shipped `GET /api/admin/cohort-sums-histogram` (`backend/app/routes/admin_cohort.py:330`) as `SUM(COALESCE(curve_price)) per COALESCE(group_id, event_id)` with buckets `0–1.0 … 5.0+` plus per-size median. That design is **correct for the EXCLUSIVE class and by construction wrong for the CUMULATIVE class**. Label the buckets per class so nobody reads a cumulative ladder's 2.5 sum as a bug:

| Histogram bucket `sum(p)` | EXCLUSIVE (field / container YES-sum / exclusive_ranges bins) | CUMULATIVE (quantity threshold ladder) |
|---|---|---|
| `0–0.9` | DEFECT — missing members or partial field that should have been excluded (`precompute_calibration.py:591-612` completeness), not normalized | CORRECT-BY-SEMANTICS — early thresholds at low p (e.g., Over 3.5 at 0.95 + Over 12.5 at 0.02 = 0.97) can sum <1; not a defect |
| `0.9–1.1` | HEALTHY — exhaustive partition sums to 1 | CORRECT-BY-SEMANTICS but rare — would require thresholds that happen to sum near 1 by accident; not a health signal |
| `1.1–1.5` | MILD DEFECT — un-de-vigged book column or partial-field survivor sum (`:604` survivor inflation) | CORRECT-BY-SEMANTICS — 2–3 cumulative thresholds at 0.50–0.60 each sum 1.2–1.5 by design |
| `1.5–2.0` | DEFECT — container YES-sum >1 (ladders scored as independent binaries at raw price) | CORRECT-BY-SEMANTICS — 3–4 thresholds at 0.50 each sum 1.5–2.0 by design |
| `2.0–3.0` | STRONG DEFECT — the old sums-to-1 bug on containers/fields | CORRECT-BY-SEMANTICS — 4–6 thresholds at 0.50 each sum 2.0–3.0 |
| `3.0–5.0` / `5.0+` | STRONG DEFECT — extreme ladder/container defect | CORRECT-BY-SEMANTICS — `quantity` with 6–10 thresholds at 0.50 each sums 3–5+ (the light `quantity 50.00` and `container_member 49.95` in `traded_vs_untraded_by_shape.md` are cumulative thresholds, not containers — their 2.5 sum is *expected*) |

Hence the histogram must be **split by relation**, not just by `market_type`. The current endpoint groups `market_type IN ('container_member','quantity')` together (`admin_cohort.py:350`) and will conflate the two correct sums. The fix is to add a `relation` filter: exclusive histogram = `outcome_relation IN ('competitors','complements','exclusive_ranges')` and `exhaustive=true`; cumulative histogram = `outcome_relation='cumulative_thresholds'` with the two checks above (per-rung overround + monotonicity), never `sum(p)`.

## 5. Fix-shaped summary — which code path changes, for which class, with the invariant test each change ships with

**No product code is changed in this artifact** — this is the queue input that the calibration lane will implement from the worktree after cert. Each row is one code change, the class it fixes, and the invariant test it ships with.

| # | Class | Code path that changes | What changes | Invariant test shipped with it |
|---|---|---|---|---|
| 1 | **EXCLUSIVE** — `field` / `container_member` container / `exclusive_ranges` bins | `backend/app/utils/market_shape.py:_outcome_relation` (`:426-428` ranges vs `:431-435` cumulative threshold) + `backend/app/tasks/precompute_calibration.py:566-650` field-normalization gate (`market_needs_mex_normalization` + `field_is_complete_for_normalization` + `mex_field_divisor`) | Persist `outcome_relation` + `exhaustive` at ingest (already `market_metadata.shape` `exhaustive`/`expected_winners`/`outcome_relation` `precompute_calibration.py:767-777`) and **only** route `REL_COMPETITORS`/`REL_RANGES`/`REL_COMPLEMENTS` with `exhaustive=true` and `expected_winners==1` through the field/container n-way divisor; `REL_CUMULATIVE` never enters that branch (today `exhaustive=false` gates it, but make it explicit on `outcome_relation`, not just `field` display shape). | Unit test in `backend/tests/test_market_shape.py` + `backend/tests/evals/test_shape_semantics_v2.py`: `classify_market_semantics` on a 5-bin `0-10`/`11-20` market returns `exclusive_ranges`/`exhaustive=NULL or true` and normalizes; `backend/tests/test_calibration_result_authority_299.py` already asserts `market_exclusivity_is_proved("container_member", True, 1, "complements") is False` (`:197`) — add `SUM(group YES) buckets 0.9–1.1` assert on `GET /api/admin/cohort-sums-histogram` filtered to `outcome_relation='competitors'` with `members=5 → median_sum≈1.0`. |
| 2 | **CUMULATIVE** — `quantity` threshold ladders (`Over 7.5/8.5/9.5`, `At Least N`) | `backend/app/utils/odds_math.py:47` + `backend/app/tasks/polymarket.py` (or the odds API ingestion that writes `quantity` ladder thresholds) — introduce **per-rung two-way de-vig** (`remove_vig_nway([yes_p, no_p])` per threshold) and drop any cross-rung sum. Calibration scoring stays at `curve_price` per rung *after* per-rung de-vig, not at raw `calibration_probability`. | No sum-to-1. Instead, two invariants: **(a) per-rung `YES+NO` overround** `0.9–1.1` (after per-rung de-vig, `odds_math.py:102-106` `sum(values)` check) and **(b) monotonicity** `p(Over N) ≥ p(Over M)` for `N<M` (1pp tolerance). Tests: `backend/tests/evals/test_shape_semantics_v2.py` fixture `shape_semantics_v2.json` — a 3-rung `Over 7.5/8.5/9.5` market with raw `0.60/0.60/0.60` and book overround `1.20` on each rung must de-vig to `0.50/0.50/0.50` per rung (not `0.33` via n-way), and `p` is non-increasing with threshold; `GET /api/admin/cohort-provenance-split` `ece_all` vs `ece_venue` per `quantity` cell must *not* use sum-to-1 as a signal. |
| 3 | **INDEPENDENT** — `participation` / `unknown` | `backend/app/utils/market_shape.py:317-318` `SHAPE_PARTICIPATION` + `backend/app/tasks/precompute_calibration.py:560` ("binaries (2+ winners) and voids are the counter-class and left") | **Nothing changes to probabilities** — `participation` is already excluded from `market_needs_mex_normalization` (requires `1 winner`), but tighten the display-shape split (`:317-318`) so a DataGolf `top_5` that happens to have 3 outcomes never masquerades as `field` (it is already `participation`, keep it). | `backend/tests/test_market_shape.py`: `classify_market_shape` with `source_kind='top_5'` → `participation` (not `field`), and `market_needs_mex_normalization` returns `False` when `expected_winners>1` (`precompute_calibration.py:584-585` `n_winners==1`); `precompute_calibration.py:991-1010` census: 51k `field/unknown`, 27k cumulative ladders `exhaustive=false`, 31k `field/competitors/true/1` — assert those counts do not move into the normalized pile. |
| 4 | **Cross-cutting** — sums-histogram design fix | `backend/app/routes/admin_cohort.py:330` `cohort-sums-histogram` (currently `market_type IN ('container_member','quantity')` together) | Split the endpoint into **two histograms** (or two filtered queries): `exclusive_sum` filtered to `outcome_relation IN ('competitors','complements','exclusive_ranges')` and `cumulative_monotonicity + per-rung overround` filtered to `outcome_relation='cumulative_thresholds'`. Label buckets per class as in §4 table, so a cumulative ladder's `2.5` sum renders as `CORRECT-BY-SEMANTICS` in green, not `DEFECT` in red. | Contract test `backend/tests/evals/test_cohort_sums_histogram_split.py` (new): `container_member` group with `exhaustive=true` `members=5` `sum≈1.0` → exclusive bucket `0.9–1.1` `HEALTHY`; `quantity` cumulative group `Over 7.5/8.5/9.5` at `0.50` each `sum=1.50` → cumulative bucket `1.5–2.0` `CORRECT-BY-SEMANTICS` (not defect), and `violation_rate≈0` on monotonicity. |

*In one line:* **Exclusive** → n-way de-vig, invariant `sum≈1`; **Cumulative** → per-rung two-way de-vig, invariant monotonicity `p↓` with threshold and per-rung `YES+NO≈1`, never `sum≈1`; **Independent** → per-market two-way only, no cross-outcome sum. Blanket sum-to-1 on cumulative ladders is the corruption the audit's finding #1 trap warns against — it would turn a correct `Over 7.5 0.60, Over 8.5 0.55, Over 9.5 0.50` (sum 1.65 correct) into `0.36, 0.33, 0.30` (sum 1.0 wrong) and fabricate a 15–20pp ECE swing on 2,880 `quantity` rows (`traded_vs_untraded_by_shape.md` rank 1, 50.00pp light).

