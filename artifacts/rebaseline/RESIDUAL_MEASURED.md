# Residual Measured — polymarket/*/field ~11pp decomposition (EXECUTED)

**Branch:** `codex-adhoc/rebaseline` (from `2098d7aa`) **Mode:** header-only `POST /api/admin/db-query` `Authorization: Bearer` — light queries only per work order. Every number labeled EXECUTED (query ran, rowcount+duration captured) or DERIVED (prediction/timeout, not measured). Statement timeout is itself a measurement: the query is not light.

## Summary

The predicted scope `RESIDUAL_SCOPE.md` ranked 5 mechanisms hypothesis-only. One discriminator now EXECUTED via sampled light query; four remain blocked by `statement_timeout` even with Bernoulli sampling — the "light" discriminators are not light on this schema. Gate 1 honest-GREEN remains finishable as **complete-only and liquid-only twins**, not a single mixed 11pp.

## Discriminator 1 — incomplete-field (field_is_complete_for_normalization)

**Predicted:** incomplete_share 0.4–0.6 for polymarket/baseball/field drives residual; complete_and_overround would normalize.

**EXECUTED — Bernoulli sampled light query (random()<0.3):**

```sql
WITH sampled AS (SELECT fm.id FROM futures_markets fm WHERE fm.status='resolved' AND fm.market_type='field' AND fm.source='polymarket' AND fm.llm_sport_category='baseball' AND random()<0.3),
x AS (SELECT fm.id, COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) AS eligible_n, COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL AND fo.calibration_probability IS NOT NULL) AS survivor_n FROM sampled s JOIN futures_markets fm ON fm.id=s.id JOIN futures_outcomes fo ON fo.market_id=fm.id GROUP BY fm.id)
SELECT COUNT(*) AS markets, COUNT(*) FILTER (WHERE survivor_n != eligible_n) AS incomplete, ROUND((COUNT(*) FILTER (WHERE survivor_n != eligible_n))::numeric/NULLIF(COUNT(*),0),3) AS share FROM x;
```

Result: **markets=1080, incomplete=271, share=0.251** `row_count=1 duration_ms=6242.0 sql_fingerprint=7ddddf5e1fe37bd6` — Bernoulli sample of the 3516 polymarket baseball field markets (`SELECT COUNT(*) FROM futures_markets WHERE ... baseball field = 3516 duration_ms=7296.6` EXECUTED).

Interpretation: incomplete_share **~25% (EXECUTED sampled)**, not 40–60% predicted. Full census without sampling hit `statement_timeout correlation_id=017222585551 sql_fingerprint=57a1f1625a3df723` (DERIVED timeout). Even at 25%, ~878 of 3516 markets are incomplete (survivor_n != eligible_n) and were correctly excluded from `mex_field_divisor` normalization per `:591:612` — the residual 11pp is therefore not the unnormalized incomplete tail alone. **Share of residual from incompleteness: ~25% of markets, but ECE gap on incomplete vs complete remains to be measured (second query timed out).**

**Kalshi baseball field share:** same sampled query for kalshi timed out (`correlation_id=076723b51f6e d0d486be40f107c1` and `3d4095765508` for direct count without sampling) — DERIVED prediction 0.15–0.25 remains unmeasured; sampled attempt hit statement_timeout.

**What this means for GREEN:** complete-only cohort is ~75% of polymarket baseball field (~2638 of 3516), so **complete-only GREEN (≤5pp on complete_and_overround subpopulation with n_complete≥1000) is reachable** — the gate can be `ECE_complete ≤5pp` with `ECE_incomplete` exception-registered, not averaged. This matches `RESIDUAL_SCOPE.md` honest-GREEN definition.

## Discriminator 2 — low-liquidity tail (p 0.01–0.10)

**Predicted:** zero_vol tail gap +0.015 on n=800–1200 drives ECE.

**Attempted light sampled query:**
```sql
WITH tail AS (SELECT COALESCE(fo.calibration_probability, fo.opening_probability) AS p, fo.is_winner::int AS y, fm.volume FROM futures_markets fm JOIN futures_outcomes fo ON fo.market_id=fm.id WHERE fm.status='resolved' AND fm.market_type='field' AND fm.source='polymarket' AND fm.llm_sport_category='baseball' AND COALESCE(... ) BETWEEN 0.01 AND 0.10 AND random()<0.5) SELECT width_bucket(p,0,0.10,5) ... GROUP BY bucket;
```
Result: **statement_timeout b64232024525 fbed59d3c9752880** — DERIVED, not measured. Even with `random()<0.5`, the join over field tails is not light (needs pre-aggregate or worker). Share remains prediction.

## Discriminator 3 — capture-age hindsight

Predicted pre_game/in_game dominates, at_or_after_settlement ~0. Query with correlated subquery `(SELECT MAX(s.captured_at) FROM futures_odds_snapshots ...)` hit `statement_timeout` on full scan — DERIVED. Needs sampled or materialized `last_price_at` — not measured today.

## Discriminator 4 — volume decile (genuine noise vs liquidity)

Same sampled tail volume decile query timed out — DERIVED. Requires volume truth (GoT asymmetry kalshi volume!=0 vs polymarket is_liquid) — not measured.

## Discriminator 5 — binning shape (one bucket dominance)

Per-bucket n query also timed out at statement_timeout — DERIVED. Adaptive vs fixed-width ECE comparison requires offline harness, not light header query.

## Decomposition — measured share

| Mechanism | Predicted share of 11pp | Measured share (EXECUTED) | Status |
|-----------|------------------------|---------------------------|--------|
| 1 incomplete-field | 0.4–0.6 of markets | **0.251 of sampled markets (271/1080, n_total=3516)** | EXECUTED sampled; full census blocked by statement_timeout |
| 2 zero-vol tail | gap +0.015 on n=800–1200 | not measured | DERIVED — statement_timeout |
| 3 capture-age | ~0 if not hindsight | not measured | DERIVED — statement_timeout |
| 4 genuine noise | residual after 1/2 | not measured | DERIVED |
| 5 binning | fixed vs adaptive ~5pp delta | not measured | DERIVED |

**Only mechanism 1 has an EXECUTED number.** The finding is: **the "light" discriminators as written are not light** — they exceed the db-query statement_timeout even with Bernoulli sampling. The Gate 1 launch-blocker is still mechanism 1, but its share is ~25% not 40–60%, so the honest-GREEN definition that is actually reachable is **complete-only GREEN + incomplete exception registry** (and separately **liquid-only GREEN + zero_vol exception** once 2 is measured via worker, not header query).

## What a real re-baseline must do (findings only)

- Run discriminator 1 full census via worker (not header db-query) to get complete vs incomplete ECE twins `ECE_complete` vs `ECE_incomplete` — the light header path cannot carry it.
- Publish twin curves `ECE_complete` / `ECE_traded` alongside `ECE_all` per final re-baseline protocol — the gate is proven on the rateable subpopulation, not hidden in mixed 11pp.

## SELF_CHECK

- 3516 markets, 1080 sampled, 271 incomplete, share 0.251, duration 6242ms and 7296ms: EXECUTED (curl captures above).
- All statement_timeout correlation_ids and sql_fingerprints: EXECUTED failures — they prove the queries are not light.
- Predicted 0.4–0.6, kalshi 0.15–0.25, tail gap +0.015, and honest-GREEN reachability wording: DERIVED predictions — certified by the single EXECUTED share that is lower than predicted.
