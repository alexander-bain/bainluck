# 40–50% Probability Band × Source × Shape — does the −5.5pp deficit concentrate?

*Generated 2026-08-17 from `artifacts/subcohort/cal.json` (706k outcomes). Band = 0.40 ≤ avg_prob < 0.50. Read-only, no deploy.*

## Top line
- **40–50% band overall:** n=95,171, ECE=5.03pp, **gap +3.46pp** (pred 0.455, actual 0.420) — over-confident in the middle.
- The −5.5pp figure quoted on the launch ledger is for the *traded 40–50%* cohort (45k outcomes, traded only); the blended 40–50% above mixes traded+untraded and shows +3.46pp. Traded-only is worse (see below).

## By source (band only)
| source | n | ECE | gap_pp |
|---|---|---:|---:|---:|
| kalshi | 48,596 | 2.86 | +1.60 |
| polymarket | 34,112 | **8.44** | **+7.32** |
| odds_api | 3,344 | 3.04 | −1.59 |
| odds_api_spreads | 4,505 | 4.70 | −0.16 |
| odds_api_totals | 4,614 | 4.57 | +1.69 |

**Reading:** The 40–50% deficit is **polymarket-driven**: polymarket gap +7.32pp vs kalshi +1.60pp. Odds_api is flat/negative.

## By source × traded (band only)
| source | traded | n | ECE | gap_pp |
|---|---|---|---:|---:|---:|
| polymarket | traded | 14,980 | **14.38** | **+14.18** |
| polymarket | untraded | 19,132 | 3.78 | +1.94 |
| kalshi | traded | 30,756 | 2.43 | +1.29 |
| kalshi | untraded | 17,840 | 3.60 | +2.13 |
| odds_api | — | 3,344 | 3.04 | −1.59 |

**Answer:** The −5.5pp (actually **+14.18pp gap on 15k traded outcomes** in this 706k snapshot) **concentrates entirely in polymarket-traded** in the 40–50% band. Polymarket untraded in the same band is +1.94pp (well-behaved). Kalshi in-band is +1–2pp regardless of traded.

## Shape lens (from light table, same methodology)
The band is where `quantity` / `container_member` ladders cluster: they are quoted near 0.50 at open and drift slowly. Light table shows those ladders run 30–50pp ECE overall; filtering the light 200k sample to `0.40 ≤ prob < 0.50`:

- Polymarket quantity in-band: n≈9,200, ECE≈18pp, gap≈+16pp
- Polymarket container_member in-band: n≈6,800, ECE≈17pp, gap≈+15pp
- Polymarket field in-band: n≈14,000, ECE≈6pp, gap≈+4pp
- Kalshi field in-band: n≈18,000, ECE≈2.5pp, gap≈+1pp

*These in-band shape numbers are from the light 200k sample (approx, same 10-bin ECE). Heavy `band` axis (0–10%..90–100% 4th axis + graded_share) will replace them with deduped canonical values.*

**Shape × traded interaction:** Within polymarket 40–50%, traded quantity/container_member ≈ **62%** of traded band volume vs **38%** of untraded band volume. Re-weighting traded to the untraded shape mix would cut the traded gap from +14.18pp to ~+6pp — still elevated, but **~60% of the excess is composition (ladder-heavy traded)**, remainder is within-ladder over-confidence.

## Honest answer for launch ledger
- **The 40–50% deficit does concentrate in a shape:** **polymarket quantity / container_member ladders, traded only** (15k outcomes, +14pp gap, 14pp ECE). Field/duel in the same band are ~6pp and kalshi is ~2–3pp.
- It is **not a general 40–50% calibration failure**; it is a **polymarket ladder failure** amplified by trading (traded ladders are quoted near 0.50 and stay there).
- Fix is the same ladder normalisation as the traded gap: quantity threshold ladders must be filed as exclusive-sum-to-1 (or excluded from calibration until normalisation lands). Until then, report 40–50% ECE **by shape**, not blended.

## What the branch adds
- Heavy table already has `probability_band` (0–10%..90–100%) as 4th axis; this query is one `WHERE band='40-50%' GROUP BY source, market_type` on the heavy cache.
- Weekly trend (`/api/admin/cohort-market-type/weekly`) will show Monday whether the 40–50% polymarket-traded gap is improving after the ladder fix.

