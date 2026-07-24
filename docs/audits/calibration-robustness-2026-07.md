# Calibration Robustness Audit — July 2026

**Queue #251 (SQL-aggregate pass) + Queue #253 (authoritative raw-row/per-event census). Read-only audit — NO fixes shipped.**
Measured live against production 2026-07-24 (PT). #251 used server-side `db-query` aggregates (the raw-row loader and a per-event scan were infeasible under the web-path statement timeout). **#253 ran the deferred deliverables off the request path** — a Heroku one-off (`scripts/evals/cal_robustness_census.py`, `performance-l`) that (a) ran the landed `cohort_sweep.load_from_session` + `sweep()` over the **full 1,279,310-row** calibratable population, and (b) computed the **literal per-event / per-outcome density** across `win_prob_snapshots` and `futures_odds_snapshots` (167.9M rows) with worst-100 tables + recoverability flags. Results were persisted as `cal_robustness_253:*` marker rows and read back via `db-query`.

The deliverable is findings for Fable to read *before* any backfill/recalibration queue is staged. Fix-ordering discipline throughout: **assume-our-bug first — capture / linkage / grading / denominator before source-bias.** The #253 census **confirms every #251 headline** (duel ECE 2.44pp; shape is the axis; field overround) and adds two new discriminators (calibration slope; near-universal anti-calibration on the worst cohorts) plus corrected full-population dedup magnitudes.

---

## Queue #253 — authoritative raw-row / per-event census (supersedes #251's estimates where they differ)

### Item 2 — full raw-row sub-cohort sweep (1,279,310 rows · 374 cohorts)

**The discriminator holds on the real rows: shape, not source, is the defect axis.**

| shape | N | predicted | actual | signed error | ECE |
|---|---:|---:|---:|---:|---:|
| field | 713,573 | 0.3765 | 0.2916 | **+0.0849** | 0.0849 |
| quantity | 262,822 | 0.3922 | 0.3210 | **+0.0712** | 0.0722 |
| container_member | 208,126 | 0.4559 | 0.3643 | **+0.0916** | 0.0987 |
| **duel** (binary) | 80,849 | 0.4849 | 0.4777 | **+0.0073** | **0.0244** |
| **unshaped** | 13,940 | 0.5059 | 0.4923 | **+0.0136** | 0.0345 |

By source (shape-confounded — polymarket carries proportionally more multi-outcome fields): polymarket +8.92pp (ECE 9.04), kalshi +6.15pp (ECE 6.15), datagolf +4.19pp (ECE 5.04).

**The honest baseline — duel (binary) reliability curve, ECE = 2.44pp** (matches #251's aggregate to the basis point):

| decile | N | predicted | actual |
|---:|---:|---:|---:|
| 0.0–0.1 | 14,459 | 0.019 | 0.005 |
| 0.1–0.2 | 2,850 | 0.149 | 0.117 |
| 0.2–0.3 | 4,017 | 0.251 | 0.209 |
| 0.3–0.4 | 6,238 | 0.352 | 0.299 |
| 0.4–0.5 | 14,630 | 0.465 | 0.432 |
| 0.5–0.6 | 13,476 | 0.528 | 0.556 |
| 0.6–0.7 | 5,623 | 0.644 | 0.665 |
| 0.7–0.8 | 4,263 | 0.745 | 0.768 |
| 0.8–0.9 | 3,064 | 0.846 | 0.861 |
| 0.9–1.0 | 12,229 | 0.981 | 0.985 |

Mild low-end over-confidence, mild mid-range under-confidence that roughly cancel — genuinely well-calibrated once the multi-outcome artifact is removed.

**Worst-25 cohorts by severity (|error|·√N, N≥30) — now with two NEW columns the raw-row sweep exposes:** `slope` (calibration slope) and `anti` (anti-calibration flag: high-priced ≥0.75 outcomes lose materially more than their implied rate).

| source | league/cat | shape | N | pred | act | err | sev | slope | anti |
|---|---|---|---:|---:|---:|---:|---:|---:|:--:|
| polymarket | tennis | quantity | 36,243 | 0.498 | 0.278 | +0.220 | 41.8 | 0.67 | ✓ |
| kalshi | baseball | field | 125,937 | 0.379 | 0.284 | +0.095 | 33.6 | 0.66 | ✓ |
| polymarket | tennis | container_member | 28,789 | 0.507 | 0.321 | +0.186 | 31.5 | 0.71 | ✓ |
| polymarket | LOL | field | 34,487 | 0.459 | 0.319 | +0.139 | 25.9 | **1.02** | ✗ |
| polymarket | US | field | 3,414 | 0.558 | 0.115 | +0.443 | 25.9 | **0.11** | ✓ |
| kalshi | hockey | field | 27,694 | 0.321 | 0.175 | +0.146 | 24.3 | **0.18** | ✓ |
| polymarket | esports | field | 37,684 | 0.515 | 0.396 | +0.119 | 23.1 | **1.00** | ✓ |
| kalshi | golf | field | 20,898 | 0.273 | 0.136 | +0.137 | 19.7 | 0.47 | ✓ |
| polymarket | soccer | field | 113,547 | 0.276 | 0.220 | +0.056 | 18.8 | 0.92 | ✓ |
| polymarket | soccer | quantity | 22,899 | 0.471 | 0.350 | +0.122 | 18.4 | 0.87 | ✓ |
| polymarket | politics | field | 5,904 | 0.506 | 0.281 | +0.225 | 17.3 | **0.35** | ✓ |
| kalshi | entertainment | quantity | 10,526 | 0.416 | 0.253 | +0.163 | 16.7 | 0.58 | ✓ |
| polymarket | basketball | quantity | 11,248 | 0.399 | 0.243 | +0.157 | 16.6 | 0.67 | ✓ |
| polymarket | DOTA | field | 25,546 | 0.467 | 0.369 | +0.098 | 15.7 | **1.04** | ✗ |
| polymarket | esports | container_member | 31,695 | 0.488 | 0.401 | +0.087 | 15.5 | 0.90 | ✓ |
| polymarket | entertainment | field | 5,200 | 0.389 | 0.176 | +0.214 | 15.4 | 0.41 | ✓ |
| polymarket | UCL | field | 1,255 | 0.717 | 0.309 | +0.407 | 14.4 | 0.35 | ✓ |
| polymarket | football | field | 2,039 | 0.395 | 0.090 | +0.305 | 13.8 | 0.52 | ✓ |
| kalshi | PGA | field | 4,768 | 0.302 | 0.134 | +0.169 | 11.7 | 0.39 | ✓ |
| kalshi | NASCAR | field | 3,420 | 0.379 | 0.197 | +0.182 | 10.7 | 0.46 | ✓ |
| polymarket | tennis | field | 39,856 | 0.511 | 0.460 | +0.051 | 10.2 | 0.97 | ✓ |

**NEW — the calibration slope splits the over-prediction into two mechanistically distinct classes (this is the #253 finding #251 could not see):**

1. **Slope ≈ 1.0, well-ordered, uniformly shifted** (LOL 1.02, DOTA 1.04, esports 1.00, tennis-field 0.97, soccer 0.92): the ranking is *correct*, the whole curve is just shifted up. This is the **overround / un-normalized independent-binary** signature — a multi-way `field` whose legs sum >1. Fix = **normalize the field to sum→1** (the politics-normalization / cycling-GC lesson). Cheap, deterministic, no regrade.
2. **Slope ≪ 1.0, genuinely mis-ordered** (US field 0.11, hockey field 0.18, motorsports 0.21 [in drill-down], politics 0.35, UCL 0.35): high prices don't track outcomes at all — the ranking itself is wrong. This is **illiquid one-sided-ask placeholders + ungraded-as-loser contamination** (the #940/#762 golf-FIELD lesson; `is_winner` defaults False so an ungraded leg counts as a loss). Fix = **exclude illiquid/never-traded legs and re-check grading** BEFORE trusting these actuals; normalization alone will not fix a slope-0.1 cohort.

**Anti-calibration is near-universal on the worst cohorts** (23 of 25 flagged): e.g. kalshi baseball field has 19,622 outcomes priced ≥0.75 losing at **40.3%** vs an implied 5.2%. The concrete worst examples are the smoking gun for both classes — kalshi baseball `"Japan -2.5 first 5 innings"` stored at prob **0.0** but graded `actual=1`; polymarket tennis `"Under"` at **0.0005** graded `actual=1` (and `0.9995 → 0`). These are grading/placeholder defects, not source over-confidence.

**Fix ordering (assume-our-bug, unchanged from #251 but now slope-informed):** (1) normalize multi-outcome `field` legs to sum→1 (collapses the slope≈1.0 class); (2) exclude illiquid one-sided-ask placeholders (the slope≪1.0 class); (3) re-check `field`/`quantity` for ungraded-as-loser before trusting actuals; (4) only then assess residual source bias — which on the honest binary core is already **2.44pp ECE**.

### Item 1 — literal per-event / per-outcome density census

**Full-population dedup magnitude (corrects #251's 1-day samples — the collapse is much larger than the sample suggested):**

| table | rows | effective (Σ reading_count) | avg reading_count | max | % deduped (rc>1) |
|---|---:|---:|---:|---:|---:|
| win_prob_snapshots | 960,261 | 2,877,006 | **3.00** | 5,415 | **22.85%** |
| futures_odds_snapshots | **167,920,481** | 250,384,255 | 1.49 | 17,352 | 3.30% |

Raw `COUNT(*)` under-counts true win-prob sampling density by **~3×** (not the 1.18×/3.9% a single day suggested). So the "indistinguishable graph" is even more a *rendering* problem than #251 credited: a flat 48h stretch on a Tier-1 game is one row carrying up to 5,415 real polls + `valid_until`. `futures_odds` has no write-time dedup (only the 24h turbo-collapse), so its 3.3% is all retention-job work.

**Games — per-event density (35,017 settled events since March). Tier-1 is dense; sparsity is minor-league / unclassified / tennis:**

| league | events | avg_eff | avg_rows | avg_sources | % sparse (eff<6) |
|---|---:|---:|---:|---:|---:|
| MLB | 1,720 | 357.7 | 138.2 | 2.76 | 11.3 |
| MLS | 168 | 325.4 | 99.1 | 1.09 | 9.5 |
| NBA | 477 | 263.7 | 146.7 | 2.07 | 11.5 |
| NHL | 523 | 194.7 | 86.0 | 1.22 | 14.7 |
| WNBA | 320 | 187.1 | 74.8 | 1.39 | 5.0 |
| NCAAB | 1,841 | 142.2 | 51.3 | 1.23 | 10.9 |
| ATP (tennis) | 70 | 4.7 | 3.6 | 1.00 | **98.6** |
| WTA (tennis) | 64 | 3.2 | 3.0 | 1.00 | **98.4** |
| AHL | 65 | 12.3 | 3.7 | 1.00 | **95.4** |
| `(none)` (unclassified) | 12,255 | 11.7 | 6.8 | 1.00 | **64.4** |
| `Other` | 10,209 | 52.1 | 19.6 | 1.00 | 29.7 |

The **worst-100 settled games are all `(none)`/`Other`/one NCAA_Baseball — eff=2, single-source** (open + close snapshots only). None are Tier-1. Game win-prob (ESPN/betting/MLB live) is **not** historically backfillable, so these are permanent upstream coverage limits on off-brand events, not a fixable capture regression. (Note: several carry span_h 40–102h on a `closed` status — worth a spot-check against the inverted-`completed_at` class, gotcha #46, but eff=2 alone just means two points.)

**Futures — per-outcome density (2,031,130 outcomes; 461,771 = 22.7% genuinely sparse: span≥3d AND <1pt/day):**

| source | outcomes | avg_eff | avg_span_d | % single-row |
|---|---:|---:|---:|---:|
| polymarket | 932,173 | 152.6 | 10.6 | 5.6 |
| datagolf | 42,290 | 2040.2 | 10.6 | 13.8 |
| odds_api | 1,450 | 1689.5 | 96.4 | 0.0 |
| kalshi | 1,055,217 | **18.4** | 18.1 | **21.1** |

Kalshi futures are the sparse source (avg ~1 point/day over an 18-day span, 21% single-row) — the settled-market freeze (gotcha #33: settled markets stay `status='open'`, polling stops seeing them). Polymarket/DataGolf are dense. The **worst-100 sparse futures are 100% kalshi baseball duels, eff=2 over 68–70 days** — captured at open and close only, then frozen. Recoverability: **all flagged `kalshi_time_gated_2-3mo`** (gotcha #35 — `GET /markets/{ticker}` 404s and settled-event pagination caps ~5,000/series after ~2–3 months), so a large share of this tail is **already permanently lost**; only the recently-settled slice is recoverable, and only via capture-at-settlement going forward. Polymarket's sparse tail (not in the worst-100) is recoverable via the CLOB backfill.

**Item-1 conclusion:** density is healthy where the product leans (Tier-1 games multi-source & dense; polymarket/datagolf futures dense). The remaining sparsity is (a) a chart-rendering issue for deduped flat stretches — now measured at ~3× undercount on win_prob, the largest & cheapest win — and (b) genuine minor-league/tennis game gaps + the kalshi settled-freeze tail, most of which is upstream-limited or past the recovery window. **No backfill should precede the dedup-rendering fix**, and any kalshi history backfill must run oldest-recoverable-first within the 2–3-month window.

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
- **#251 (aggregate pass):** every figure is a live prod read on 2026-07-24 via `POST /api/admin/db-query`. The endpoint's tight statement timeout precludes `count(DISTINCT)` and multi-table joins over the raw snapshot tables, so #251 sampled representative in-season days and used per-shape/source aggregates rather than a full per-event scan. **These estimates are now superseded by the #253 census where they differ** (notably dedup magnitude: #251's 1-day win_prob sample read 1.18×/3.9%; the full population is 3.00×/22.85%).
- **#253 (authoritative census):** run off the request path as a `performance-l` Heroku one-off (`scripts/evals/cal_robustness_census.py`). It ran `cohort_sweep.load_from_session` + `sweep()` over the full 1,279,310-row population and computed per-event/per-outcome density over the full 167.9M-row `futures_odds_snapshots` and 960K-row `win_prob_snapshots` — the literal worst-100 tables + per-row recoverability flags. Results persisted as `cal_robustness_253:*` marker rows on `entities` (kind='seed_diag'), read back via `db-query` (`entity_metadata->>'payload'`, a TEXT read — sidesteps the JSONB-repr gotcha #40). Full drill-down of all 374 cohorts is in `cal_robustness_253:sweep_drill`.
- **Census-build notes (for the next off-request-path job):** three iterations were needed. (1) a bind-param date (`.bindparams(start=...)`) sends the value as VARCHAR → `timestamptz >= varchar` has no operator → crash; use a SQL literal or `CAST(:p AS timestamptz)` (never `:p::cast`, the asyncpg text()-drops-bind gotcha). (2) `statement_timeout=0` is connection-local, so pool churn from mid-run marker commits loses it; hold ONE `engine.connect()` for all heavy reads. (3) a detached dyno's stdout/logs are EPERM-blocked (gotcha #48) — an `:error` marker capturing the traceback is what made the bind bug visible. All three are documented in the script header.
- **PREREQ still stands (from #250 C4 / this queue's note):** do NOT stage any backfill/recalibration from these findings until the dedup chart-rendering fix and field normalization land — both would mis-attribute present-but-collapsed data or an overround artifact to "source bias." This queue produced the report; Fable sequences the fixes.
