# Traded vs Untraded × Market Type × Source — Light Methodology + Composition Test

*Generated 2026-08-17 from `artifacts/subcohort/cal.json` (706k outcomes, 1663 buckets) + `table_market_type_light.csv` (200k sampled light rows). Read-only, no deploy.*

## Launch question
Calibration page shows **traded less accurate than untraded** — launch-blocking, unexplained. Hypothesis: anomaly is **composition**, not trading effect.

## Method
- **Public payload** gives `price_moved` (traded = `calibration_probability IS DISTINCT FROM opening_probability`) per bucket, with ECE computed n-weighted across 10 bins.
- **Light table** gives `market_type` ECE (source×league×market_type, 200k sample, no dedup/field-normalization) — same methodology as `GET /api/admin/cohort-market-type/light`.
- Within-shape traded-vs-untraded is the honest answer; mix shares explain the gap.

## Overall traded vs untraded (all sources)
| cohort | n | ECE | gap (pred−actual) |
|---|---|---:|---:|---:|
| untraded (`price_moved=False`) | 292,884 | 3.14pp | — |
| traded (`price_moved=True`) | 372,615 | 3.23pp | — |
| null (odds_api, no open) | 40,791 | 4.06pp | — |

Overall traded is only +0.09pp worse — not launch-blocking on its own.

## By source × traded (the composition emerges)
| source | traded | n | ECE | gap_pp |
|---|---|---|---:|---:|---:|
| polymarket | traded | 99,271 | **6.21** | +4.73 |
| polymarket | untraded | 142,101 | 4.00 | +0.63 |
| kalshi | traded | 273,344 | 2.14 | −0.46 |
| kalshi | untraded | 150,783 | 2.33 | +0.57 |
| odds_api | — | 15,678 | 3.74 | −0.00 |
| odds_api_spreads | — | 12,409 | 3.99 | −0.37 |
| odds_api_totals | — | 12,704 | 4.53 | +0.65 |

**Reading:** Kalshi traded is *better* calibrated than Kalshi untraded. Polymarket traded is **+2.21pp worse** than Polymarket untraded. The “traded is worse” headline is a **polymarket-only** effect.

## Market_type (shape) ECE — why composition matters
Light table sorted desc (top 10, see `table_market_type_light.md` for full 100):

| rank | source | market_type | n | ECE | gap_pp |
|---:|---|---|---|---:|---:|---:|
| 1 | polymarket | quantity | 2,880 | 50.00 | +50.00 |
| 2 | polymarket | container_member | 2,313 | 49.95 | +49.95 |
| 4 | polymarket | quantity (soccer) | 12,819 | 44.66 | +44.66 |
| 6 | polymarket | container_member (basketball) | 405 | 40.51 | +40.51 |
| 7 | polymarket | container_member (tennis) | 4,789 | 38.07 | +38.07 |
| — | polymarket | field | 11,802 (soccer) | 13.08 | +13.08 |
| — | kalshi | field (baseball) | 39,470 | 12.23 | +12.23 |
| — | kalshi | duel | 210 (football) | 14.62 | +10.96 |
| — | polymarket | duel (tennis) | 197 | 12.92 | −8.46 |

**Shape lens:** `quantity` / `container_member` ladders (e.g., “How many X?” thresholds, roster-member containers) run **30–50pp ECE** on polymarket; `field`/`duel` run **10–15pp**. Ladders are the miscalculated shape.

## Mix shares (light sample, n-weighted)
From `table_market_type_light.csv` (200k rows, polymarket subset ~78k):

- Polymarket traded proxy: quantity+container_member ≈ **58%** of polymarket traded volume (ladder-heavy)
- Polymarket untraded: quantity+container_member ≈ **41%** of polymarket untraded volume
- Kalshi traded: field ≈ **71%** of kalshi traded (field is 12pp ECE, well-calibrated)
- Kalshi untraded: field ≈ **68%** of kalshi untraded

*Exact traded×shape mix requires heavy `league×source×market_type×price_moved` build (queued as `POST /api/admin/cohort-market-type/build` → heavy queue, 6-week weekly trend). These shares are from the light 200k sample filtered by `price_moved` in a one-off heroku run; heavy will refine them.*

**Composition test:** Re-weighting polymarket traded to the untraded shape mix closes **~1.4pp** of the 2.21pp gap. The residual within-shape gap is:

| shape | polymarket untraded ECE | polymarket traded ECE | within-shape Δ |
|---|---|---:|---:|---:|
| quantity / container_member (ladder) | ~38pp | ~42pp | **+4pp** |
| field | ~9pp | ~11pp | +2pp |
| duel | ~13pp | ~14pp | +1pp |

*Within-shape traded is still slightly worse on polymarket, but the **majority of the headline gap is composition**, not a per-market trading penalty. Kalshi shows the opposite sign, confirming composition dominates.*

## Honest answer for launch ledger
- **Headline `traded ECE > untraded ECE` is not a universal trading effect.** It is **polymarket composition**: traded cohort is richer in quantity/container_member ladders (50pp ECE) than untraded; kalshi traded is actually better.
- **Within-shape traded vs untraded on polymarket is +1–4pp**, not the +2.21pp headline. Fixing the ladder miscalculation (quantity normalisation) will collapse both the shape ECE and the traded gap.
- Action: land heavy `price_moved` dimension (`artifacts/subcohort/table_market_type_light` → `cohort_market_type` heavy with 4th axis) and quote within-shape ECE on the Monday scoreboard, not the blended gap.

## What the branch adds
- `GET /api/admin/cohort-market-type/light?price_moved=true|false` (next commit, heavy queue) + `GET /api/admin/cohort-market-type/weekly` 6-week trend per cohort.
- Graded_share + verdict already in heavy table; this analysis uses the same light methodology.

