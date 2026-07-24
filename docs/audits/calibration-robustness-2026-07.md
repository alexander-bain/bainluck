# Calibration Robustness Audit — July 2026

**Queue #251 (Fable-designed, the twice-promised sweep). Read-only audit — NO fixes shipped.**
Measured live against production 2026-07-24 (PT) via the admin `db-query` endpoint.
All numbers are real prod reads; the deliverable is findings for Fable to read *before* any backfill/recalibration queue is staged. Fix-ordering discipline throughout: **assume-our-bug first — capture / linkage / grading / denominator before source-bias.**

---

## TL;DR (the two headlines)

1. **The population "miscalibration" is almost entirely a multi-outcome normalization artifact, not source over-confidence.** Binary (`duel`/`unshaped`) markets — the honest core — are near-perfectly calibrated (mean signed error **+0.7pp / +1.4pp**; duel ECE ≈ **2.4pp**). Every multi-outcome shape over-predicts **7–9pp**, and the mechanism is confirmed: `field` markets store un-normalized independent binaries whose probabilities **sum to 4.56 on average** (should be ~1.0), 67.8% overround, max sum 153.9. Any headline population ECE is dominated by this artifact and overstates true miscalibration. **Fix ordering: normalize/exclude un-normalized fields + drop illiquid placeholders BEFORE assessing residual source bias.**

2. **History density is healthy where it matters and the "indistinguishable graph" is largely a dedup-rendering issue, not a capture gap.** Tier-1 game win-prob series are dense (NBA 145, EPL 135, NHL 123, MLB 63 pts/event, ~0 sparse); futures average 12.4 pts/outcome/day. Apparent futures "flatness" is often densely-polled-but-**unchanged**: `futures_odds_snapshots` dedups identical prices into one row with `reading_count` up to **4504** + `valid_until`. Flat 48h stretches are legitimately captured and renderable — they should be **exempt** from any "sparse/broken" classification, and the fix is chart-side (expand deduped rows across `valid_until`), not a backfill.

---

## Item 2 — Sub-cohort calibration sweep

Ran the landed `backend/scripts/evals/cohort_sweep.py` math (source × league/category × market_type; signed error, severity = |error|·√N, anti-calibration, N-honest) against prod. Because the raw-row loader would pull ~1.28M rows (infeasible under the db-query statement timeout), the sweep math was reproduced as **server-side SQL aggregates** — identical definitions to the script's `analyze_cohort`.

### Population
1,279,576 calibratable futures outcomes (`calibration_probability IS NOT NULL`):
- polymarket **762,204** · kalshi **481,710** · datagolf **35,662**

### The discriminator: calibration by market shape (all sources)

| shape | N | predicted | actual | signed error |
|---|---:|---:|---:|---:|
| field | 713,839 | 0.3765 | 0.2916 | **+0.0849** |
| quantity | 262,822 | 0.3922 | 0.3215 | **+0.0707** |
| container_member | 208,126 | 0.4559 | 0.3643 | **+0.0916** |
| **duel** (binary) | 80,849 | 0.4849 | 0.4776 | **+0.0073** |
| **unshaped** | 13,940 | 0.5059 | 0.4924 | **+0.0135** |

Binary markets (sum-to-100% by construction) are essentially calibrated. Every multi-outcome shape over-predicts 7–9pp. This is the single most important cut in the audit: **shape, not source, is the axis of the defect.**

### Mechanism confirmed — field overround
Per-market probability-sum distribution for `field` markets (≥3 outcomes):
- **average sum = 4.561** (a calibrated field sums to ~1.0)
- 67.8% of field markets are overround (sum > 1.05)
- min 0.000, **max 153.881**

That is un-normalized independent-binary storage (gotcha #23: Kalshi candidate binaries sum well over 100%; cf. the cycling-GC 184-way overround bug and the politics-normalization work #968) plus illiquid one-sided-ask placeholders (the #940/#762 golf-FIELD lesson: illiquid asks that never resolve true). Both are **our-side data-quality issues (denominator + capture)**, not source over-confidence.

### The honest baseline — duel reliability curve (ECE ≈ 2.4pp)

| decile | N | predicted | actual |
|---:|---:|---:|---:|
| 0.0–0.1 | 14,459 | 0.019 | 0.005 |
| 0.1–0.2 | 2,850 | 0.149 | 0.117 |
| 0.2–0.3 | 4,017 | 0.251 | 0.209 |
| 0.3–0.4 | 6,238 | 0.352 | 0.299 |
| 0.4–0.5 | 14,630 | 0.465 | 0.432 |
| 0.5–0.6 | 13,476 | 0.528 | 0.556 |
| 0.6–0.7 | 5,623 | 0.644 | 0.665 |
| 0.7–0.8 | 4,263 | 0.745 | 0.767 |
| 0.8–0.9 | 3,064 | 0.846 | 0.861 |
| 0.9–1.0 | 12,229 | 0.981 | 0.985 |

Population-weighted ECE ≈ **0.024 (2.4pp)**. A mild low-end over-confidence and a mild mid-range under-confidence that roughly cancel — genuinely well-calibrated. This is what the source bias looks like once the multi-outcome artifact is removed.

### Worst cohorts by severity (|error|·√N), N ≥ 50

**Kalshi**
| league/cat | shape | N | pred | act | err | severity |
|---|---|---:|---:|---:|---:|---:|
| baseball | field | 125,958 | 0.379 | 0.284 | +0.095 | 33.58 |
| hockey | field | 27,694 | 0.321 | 0.175 | +0.146 | 24.33 |
| golf | field | 20,898 | 0.273 | 0.136 | +0.137 | 19.75 |
| entertainment | quantity | 10,526 | 0.416 | 0.253 | +0.163 | 16.72 |
| PGA | field | 4,768 | 0.303 | 0.134 | +0.169 | 11.66 |
| NASCAR | field | 3,420 | 0.379 | 0.197 | +0.183 | 10.67 |
| MLB | field | 447 | 0.318 | 0.034 | +0.284 | 6.01 |
| UCL | field | 191 | 0.422 | 0.120 | +0.301 | 4.17 |

**Polymarket**
| league/cat | shape | N | pred | act | err | severity |
|---|---|---:|---:|---:|---:|---:|
| tennis | quantity | 36,243 | 0.498 | 0.278 | +0.220 | 41.83 |
| tennis | container_member | 28,789 | 0.507 | 0.321 | +0.186 | 31.53 |
| LOL | field | 34,487 | 0.459 | 0.319 | +0.140 | 25.90 |
| US | field | 3,414 | 0.558 | 0.115 | +0.443 | 25.88 |
| esports | field | 37,684 | 0.515 | 0.396 | +0.119 | 23.06 |
| soccer | field | 113,547 | 0.276 | 0.220 | +0.056 | 18.79 |
| politics | field | 5,904 | 0.506 | 0.281 | +0.226 | 17.33 |
| UCL | field | 1,255 | 0.717 | 0.309 | +0.407 | 14.43 |

**DataGolf**
| league/cat | shape | N | pred | act | err | severity |
|---|---|---:|---:|---:|---:|---:|
| golf | field | 35,107 | 0.150 | 0.108 | +0.042 | 7.81 |
| PGA | field | 555 | 0.152 | 0.099 | +0.053 | 1.24 |

Every worst cohort is a multi-outcome shape (`field`/`quantity`/`container_member`) with a **positive** error — the same artifact, not a per-source pathology. (DataGolf's field error is the smallest, consistent with it being a model that already normalizes.)

### Item-2 conclusion & recommended fix ordering (assume-our-bug)
1. **Denominator/normalization first**: normalize multi-outcome fields to sum→1 before writing `calibration_probability` (or exclude un-normalized fields from the curve entirely). This alone should collapse most of the 7–9pp population bias.
2. **Capture second**: exclude illiquid one-sided-ask placeholders (the FIELD/"other" and never-traded asks) — the #940/#762 gate, applied to the curve.
3. **Grading check**: `is_winner` defaults to `False`, so any calibration-bearing outcome that was never graded counts as a loser and inflates over-prediction. The duel near-parity says grading is largely correct for binaries; **field/quantity must be re-checked for ungraded-as-loser contamination** before trusting their actual rates.
4. **Only then** assess residual source bias. On the honest binary core it is already ~2.4pp ECE — excellent; there is no evidence of systematic source over-confidence once the artifact is removed.

---

## Item 1 — History-density census (March → today)

The "indistinguishable graph" bar: does each series carry enough points across its open→settle span to render a real chart? Thresholds: live ≥1pt/30min · pregame ≥1pt/day · full span. **Interpretation caveat:** the admin `db-query` statement timeout blocks `count(DISTINCT)` and multi-table joins over the multi-million-row snapshot tables, so the census uses single-day per-event samples (no-join or 1-day-scoped joins) and per-shape/source aggregates rather than a full per-event March→today scan. A literal per-event worst-100 table needs a Heroku one-off off the request path (see Limits).

### Snapshot volume by month — `win_prob_snapshots` (games)
| month | rows |
|---|---:|
| Mar 2026 | 220,406 |
| Apr 2026 | 236,523 |
| May 2026 | 233,153 |
| Jun 2026 | 135,907 |
| Jul 2026 | 132,482 |

The Jun/Jul dip is the seasonal sports lull (NBA/NHL/MLB winding down), **not** an outage — consistent with `season_windows` break-awareness.

### Game win-prob density — per-event, in-season daily samples
(sparse = <6 points, i.e. below ~1pt/30min over a ~3h game)

| sample day | events | avg pts/event | frac sparse |
|---|---:|---:|---:|
| Mar 6 | 172 | 60.2 | 0.122 |
| Apr 6 | 195 | 17.3 | **0.841** |
| May 6 | 163 | 49.9 | 0.117 |
| Jun 6 | 194 | 35.5 | 0.191 |
| Jul 6 | 72 | 43.9 | 0.042 |

**Apr 6 is an anomaly (84% sparse, avg 17.3)** — either a minor-league-heavy slate that day or a partial polling gap. Flagged for a targeted look; single-day samples are noisy, so treat as a lead, not a verdict.

### By league (May 6 in-season slate)
| league | events | avg pts/event | sparse |
|---|---:|---:|---:|
| NBA | 2 | 145.5 | 0 |
| EPL | 6 | 135.2 | 0 |
| NHL | 2 | 123.0 | 0 |
| NCAAB | 23 | 73.8 | 0 |
| MLB | 26 | 63.0 | 0 |
| UFC | 3 | 56.0 | 1 |
| NCAA_Baseball | 40 | 14.9 | 3 |
| Serie_A | 6 | 19.2 | 0 |
| La_Liga | 6 | 20.2 | 0 |
| Bundesliga | 8 | 18.8 | 0 |
| Ligue_1 | 3 | 15.0 | 0 |
| Brazil Campeonato | 4 | 3.0 | **4 (all)** |

Tier-1 leagues are dense; sparsity is concentrated in minor leagues (Brazil, NCAA baseball) — an upstream win-prob-source coverage limit (ESPN/betting cover Tier-1 densely, minor leagues thinly), not a matching or capture regression.

### Futures history density — `futures_odds_snapshots` (May 6 day)
97,231 outcomes with snapshots · avg **12.4 pts/outcome/day** · max 186 · only **5.6%** single-point.

### The flatness question — dedup vs real (48h identical-price exemption)
`reading_count`/`valid_until` dedup means an unchanged price is stored **once** with the counter incremented, so raw row-count *undercounts* true poll density for flat stretches:

| table | avg reading_count | max | frac deduped (rc>1) |
|---|---:|---:|---:|
| win_prob_snapshots | 1.18 | 81 | 0.039 |
| futures_odds_snapshots | 2.01 | **4504** | 0.047 |

- **win_prob**: dedup is minimal → row-count ≈ true density; flatness there is **real** sparsity (and confined to minor leagues, above).
- **futures_odds**: dedup is material — a single row can represent up to 4504 consecutive unchanged polls. A flat 48h stretch = 1 row + `valid_until`, i.e. **legitimately captured, not a gap.** So a chunk of apparent futures "flatness" is a *rendering* problem (charts must expand deduped rows across `valid_until`), and such stretches must be **exempt** from any "sparse/broken" classification.

### Recoverability (for whatever residual is genuinely sparse)
- **Polymarket** sparse series → **recoverable** via the CLOB API (`backfill_polymarket_history` already targets sparse outcomes).
- **Kalshi** → recoverable **only within ~2–3 months** of settlement (gotcha #35: `GET /markets/{ticker}` 404s and settled-event pagination caps at ~5,000/series after that); older history is permanently lost — capture-at-settlement is the only window.
- **Game win-prob** (ESPN/betting/MLB live sources) → **not** historically back-fillable; sparse minor-league games stay sparse (upstream limit).

### Item-1 conclusion
Density is healthy where the product leans (Tier-1 games, actively-traded futures). The "indistinguishable graph" is a mix of (a) a chart-rendering issue for deduped flat stretches — the largest and cheapest win — and (b) genuine minor-league / stale-Kalshi sparsity that is only partly recoverable (Poly CLOB yes, Kalshi >3mo no). **No backfill should be staged before the dedup-rendering fix is confirmed**, or it will "fix" data that is already present.

---

## Limits / methodology
- Every figure is a live prod read on 2026-07-24 via `POST /api/admin/db-query` (durations 20ms–7s; all under the endpoint's statement timeout).
- The endpoint's tight statement timeout precludes `count(DISTINCT)` and multi-table joins over the raw snapshot tables (multiple attempts 400'd with `QueryCanceledError`). The census therefore samples representative in-season days and uses per-shape/source aggregates rather than a full per-event March→today scan; the worst-density picture is given as league/shape cohorts rather than a literal 100-row event list.
- **Follow-up if Fable wants the literal per-event worst-100 with per-row recoverability flags:** run it as a Heroku one-off (off the 30s request-path timeout) using `cohort_sweep.load_from_session` + a per-event density query, writing the result to a retrievable artifact. Not done here to keep the queue read-only and within the request-path budget.
