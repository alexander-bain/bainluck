# THE CHART CENSUS

**Queue:** L2-148 Item 2 · **Produced:** 2026-07-21 · **Scope:** fact-finding only, ZERO chart code changes.
**Purpose:** the "our side" half of the win-prob chart competitive audit ("Kalshi and ESPN are meaningfully better at data viz"). Step one is knowing exactly what we have before any redesign or taste call.

All paths under `frontend/`. Two rendering technologies coexist:
- **recharts** (`recharts@^2.12.0`, the only chart lib in `package.json`) — OddsChart, ScoreDifferentialChart, EvolutionChart, TournamentChart.
- **hand-rolled SVG** (`<path>`/`<polyline>` + manual scale math) — FuturesChart and everything else.
No d3. One `<canvas>` (`components/weather/MapCanvas.tsx`) is a geographic map, NOT a data chart, so it is out of scope.

## The four standing chart principles (the audit rubric)
1. **NO smoothing** — draw raw linear segments between real observations; never interpolate a curve the data didn't take.
2. **Fixed 0–100 axis** — probability charts pin Y to 0–100% so magnitude reads honestly and charts are comparable.
3. **Prominent blend + very faint sources** — the Bain Luck blended line is the hero; individual sources are thin/faint context (the "#883 blend-line principle", L2-131).
4. **Kalshi-minimal chrome** — as little gridline/legend/axis furniture as the chart can carry and still be read.

---

## PART 1 — PER-COMPONENT INVENTORY

### 1. `components/FuturesChart.tsx` — the shared multi-line kernel (hand-rolled SVG)
The single most-reused real chart; the backbone of every event-concept chart via 4 wrappers.
- **Surfaces:** `app/futures/[id]/page.tsx` (futures detail hero), `app/categories/golf/page.tsx`, and — via the wrappers below — the event-concept page `app/event/[domain]/[slug]/page.tsx` (SettledPathChart, RaceToTitleChart, WinnerEvolutionChart, TwoSidedTimeline).
- **Props/variants** (lines 39–63): `mini`, `height`, `showLegend`, `showAxes`, `goldTheme`, `greenTheme` (golf/Augusta), `stepInterpolation`, `fixedYAxis`, `timeMarkers` (golf R1–R4 boundaries), `selectedOutcomes`, `onToggleOutcome`.
- **Axis:** Y **auto-scales by default** (`maxProb = fixedYAxis ? 1 : Math.min(1, maxProb * 1.1)`, line 145) — only honors fixed-0–100 when the caller passes `fixedYAxis` (every event-concept wrapper does). X is time-based linear. Gridlines at `[0,0.25,0.5,0.75,1]`.
- **Color:** three index-based palettes — `DEFAULT_COLORS` (blue/red/green/…, line 6), `GOLD_COLORS` (leader gold + grays), `GREEN_COLORS` (Augusta green + grays). All lines equal weight — **no faint-source treatment**.
- **Smoothing:** ✅ **NONE.** Raw `M/L` segments (line 359) or explicit step (`H…V…`, lines 350–357 when `stepInterpolation`).
- **Chrome:** dashed gridlines `#e5e7eb`, ≤5 x-ticks, flex-wrap legend, crosshair hover tooltip. Minimal.
- **Line cap:** `historyData.slice(0, 5)` when nothing is selected (line 89); "Showing top 5 outcomes" note.
- **Live:** none itself — parents feed SWR data. **Mobile:** `overflow-x-auto`, `min-w-[600px]`, mouse-only crosshair.
- **Principle scorecard:** smoothing ✅ · fixed-axis ⚠️ (opt-in, default auto) · faint-blend ❌ (all equal) · minimal chrome ✅.

**Wrappers (ride on FuturesChart — NOT distinct implementations):**
- `components/event/SettledPathChart.tsx` — settled path; `fixedYAxis stepInterpolation`, greenTheme for golf, `golfRoundMarkers`, champion-first ordering, `slice(0, 6)` (line 98). Uses `lib/chartWindow.ts` + `ChartRangeChips`.
- `components/event/RaceToTitleChart.tsx` — live race; Top 5 / Top 10 / Full-field picker, 24h/7d/All ranges, `fixedYAxis`, greenTheme for golf.
- `components/event/WinnerEvolutionChart.tsx` — live winner field; `fixedYAxis stepInterpolation`, SWR `refreshInterval: live?60000:0`, top-5-by-latest-prob.
- `components/event/TwoSidedTimeline.tsx` — **duel**; split bar + FuturesChart on `fieldOrder(competitors).slice(0, 2)`, `fixedYAxis`, legend off.
- Shared helpers: `components/event/ChartRangeChips.tsx` + `lib/chartWindow.ts` (`CHART_RANGES` = All/1M/1W/1D/Since-start).

### 2. `components/OddsChart.tsx` — win-probability chart (recharts, ~1595 lines) — the largest chart
- **Surfaces:** `app/events/[id]/page.tsx` (single-game event page). Drives x-axis sync into ScoreDifferentialChart.
- **Two documented modes** (lines 144–156): **Mode A multi-source** — one prominent "Bain Luck" blend line (`#059669`, `strokeWidth={3}`) + each source at `strokeWidth={1} strokeOpacity={0.28}` (lines 1359–1364) — **the only true implementation of principle 3**. **Mode B sportsbooks-only** — consensus line prominent, individual books thin grey.
- **Props:** ~35 (lines 49–101) incl. `isLive`, `winProbHistory`, `winProbSources`, `aggregateLine`, `scoringPlays`, `periodBoundaries`, team colors, `externalTimeRange`/`sharedTicks`/`chartStartTime`/`chartEndTime`.
- **Axis:** Y **FIXED 0–100** (`yDomain = [0,100]`, `yTicks = [0,25,50,75,100]`, lines 843–844) + 50% ReferenceLine. X **categorical** bucketed by minute with gap-fill + forward-fill (lines 657–756).
- **Color:** `FALLBACK_SOURCE_CONFIG` (lines 30–40): betting `#0f172a`, espn `#f97316`, stat_model `#8b5cf6`, kalshi `#22c55e`, polymarket `#3b82f6`, fangraphs `#06b6d4`. Area gradient uses team colors.
- **Smoothing:** ❌ **VIOLATES** — every `<Line type="monotone">` (recharts monotone curve, e.g. 1343/1359/1376). Actual-score line uses `stepAfter`.
- **Chrome:** `CartesianGrid strokeDasharray="3 3"`, rich game-state tooltip, period ReferenceLines, lead-change diamonds (default off), current-prob callout, legend linking to `/events/{id}/models`. Heaviest chrome of any chart.
- **Live:** `isLive` defaults range to "Since Start"; re-renders on new history. **Mobile:** `ResponsiveContainer`.
- **Scorecard:** smoothing ❌ · fixed-axis ✅ · faint-blend ✅ (Mode A) · minimal chrome ⚠️ (feature-rich).

### 3. `components/ScoreDifferentialChart.tsx` — spread / score-diff (recharts, ~798 lines) — near-sibling of OddsChart
- **Surfaces:** `app/events/[id]/page.tsx` (paired below OddsChart, shares x-axis).
- **Axis:** Y **symmetric around 0** (auto — `domainMax = max(2, ceil(maxAbs/2)*2)`, lines 482–487) — NOT 0–100 (a spread chart, not a probability chart). X categorical-by-minute, shares `chartStartTime/chartEndTime/sharedTicks` with OddsChart.
- **Color:** projected `#10b981`, actual `#f97316`, kalshi `#7c3aed`, polymarket `#db2777`, books `rgba(0,0,0,0.12)`.
- **Smoothing:** ❌ **VIOLATES** on projected/PM lines (`type="monotone"`); actual uses `stepAfter` (line 747).
- **Chrome:** shares OddsChart scaffolding (time-range pills, vertical team-label rail, period ReferenceLines, legend).
- **Duplication:** replicates OddsChart's minute-bucket / gap-fill / forward-fill / time-range machinery almost verbatim.

### 4. `components/CalibrationChart.tsx` — reliability diagram (hand-rolled SVG)
- **Surfaces:** `app/calibration/page.tsx` (public), `app/admin/source-intelligence/page.tsx`.
- **Type:** predicted-vs-actual scatter + connecting `<polyline>`, perfect-calibration diagonal, ±5pp band, CI error bars. Distribution kernel, not time-series.
- **Axis:** BOTH axes **FIXED 0–100%** (`px`/`py` map 0–100, lines 50–51; grid every 10%).
- **Color:** per-series `s.color`; dot radius ∝ √(n/maxN); thin buckets (`n < thinFloor`, default 30) faded + dashed.
- **Smoothing:** ✅ NONE — raw `<polyline>` (line 107). **Chrome:** grid, axis labels, wrapping legend, `<title>` tooltips, dot-size key. Minimal.

### 5. `components/DisagreementChart.tsx` — multi-source win-prob (hand-rolled SVG)
- **Surfaces:** `app/admin/source-intelligence/page.tsx` ONLY (admin).
- **Axis:** Y 0–100% fixed (grid `[0,0.25,0.5,0.75,1]`), X time-based linear.
- **Color:** `SOURCE_COLORS` (lines 5–12) — near-copy of OddsChart's config with a different betting color (`#374151` vs `#0f172a`).
- **Smoothing:** ✅ NONE — `<polyline>` (line 123). **Chrome:** grid, time axis, rotated y-label, inline legend.

### 6. `components/EvolutionChart.tsx` — futures evolution (recharts LineChart)
- **Surfaces:** via `components/EvolutionView.tsx` + `components/EvolutionLeaderboard.tsx` → `app/futures/[id]/page.tsx`, `app/sport/[sport]/[league]/page.tsx` (+ `[slug]`), `app/categories/golf/page.tsx`, `app/categories/golf/tournaments/[slug]/page.tsx`.
- **Axis:** Y **auto-scales with padding** (`domain = [max(0,min-pad), min(1,max+pad)]`, `pad = max(0.02,(max-min)*0.1)`, line 142) — NOT fixed 0–100. X time-based, per-day ticks. Ranges: full/tournament/7d/24h/today.
- **Color:** `EVOLUTION_COLORS` (line 21, 10-color white-bg palette); eliminated outcomes `#b5b9c3` dashed; combined line `#111827` dashed.
- **Smoothing:** ❌ **VIOLATES** — `<Line type="monotone">` (379/395).
- **Chrome:** horizontal-only grid, round-boundary ReferenceLines, hover dims non-hovered to 0.2, rich tooltip.
- **Live:** `EvolutionView` SWR `refreshInterval: 60_000`, `keepPreviousData`. **Line cap:** auto-selects top `defaultTopN` (default 8).

### 7. `components/TournamentChart.tsx` — tournament probability timeline (recharts, ~27KB)
- **Surfaces:** `app/futures/[id]/page.tsx`.
- **Type:** `ComposedChart` multi-line + a "Field" aggregate line + leaderboard table + highlight panel.
- **Axis:** Y `domain={[0, "auto"]}` (line 420) — auto-scaled, NOT fixed 0–100. X time-based `interval="preserveStartEnd"`.
- **Color:** `POSITION_COLORS` (line 24, 20-color palette), `FIELD_COLOR="#6b7280"`, cross-source `SOURCE_DISPLAY`. Leader `strokeWidth 2.5`; non-selected dimmed to opacity 0.12; field line dashed.
- **Smoothing:** ❌ **VIOLATES** — `<Line type="monotone">` (450/464).
- **Line cap:** `TopFilter = 5|10|"all"`; `slice(0,3)` default selection, `slice(0,topN)`, `slice(0,15)` highlight. **Live:** SWR.

### 8. `components/MarketMap.tsx` (+ `MarketMapSection.tsx`) — distribution rail (hand-rolled)
- **Surfaces:** `MarketMapSection` → `app/events/[id]/page.tsx`.
- **Type:** horizontal density rail (intensity cells) + marker dots (pre/proj/actual/final) with SVG leader lines + hover ladder. Distribution, not time-series.
- **Variants:** `variant: "margin"|"total"`, `status: "pre"|"live"|"done"`.
- **Axis:** value-position rail via `posOnRail(value, min, max)` (`lib/marketMapUtils.ts`); left/mid/right labels; optional zero line.
- **Color:** `DOT_COLORS` (lines 39–44): actual `#16a34a`, final `#0f172a`, pre `#94a3b8`; density tinted by intensity. **Mobile:** tap popover, `ResizeObserver` recomputes leader lines.

### 9. `components/ThresholdSparkline.tsx` — threshold dot-strip (DOM + framer-motion)
- **Surfaces:** `components/GroupedFeedRenderer.tsx` (discover/grouped feed).
- **Type:** horizontal track, dots positioned by threshold value, dot size ∝ probability, color by tier (green/amber/orange/red). **Mobile:** motion `whileTap`.

### 10. `components/TotalPointsSpectrum.tsx` — scoring ladder (DOM bars)
- **Surfaces:** `app/events/[id]/page.tsx`, `components/RelatedFutures.tsx`.
- **Type:** distribution/ladder of over-probabilities as bars + pre/live/done projection strip. **Slice default:** picks **5** representative thresholds (lines 79–90); monotonicity enforced. No time axis.

### 11. `components/weather/DistributionPanel.tsx` — temperature histogram (DOM bars)
- **Surfaces:** `components/weather/TemperatureMap.tsx` (weather page).
- **Type:** probability histogram over temp buckets, single-source or grouped cross-source (Poly vs Kalshi) bars; peak bucket highlighted. **Chrome:** hover tooltips, peak labels, legend.

### 12. `components/weather/Sparkline.tsx` — smoothed sparkline (SVG) ⚠️ smoothing outlier
- **Surfaces:** `components/weather/WildCards.tsx`, `components/weather/WeatherHero.tsx`.
- **Smoothing:** ❌ **VIOLATES** — builds a **cubic Catmull-Rom→bezier** path (`C${cp1x}…`, lines 37–52). The only true bezier sparkline in the codebase. **Chrome:** gradient area fill, draw-on animation, end dot.

### 13. `components/event/Sparkline.tsx` — straight sparkline (SVG)
- **Surfaces:** `components/event/EventLeaderboard.tsx`, `app/event/[domain]/[slug]/page.tsx`.
- **Smoothing:** ✅ NONE — `<polyline>` straight segments (line 55; comment cites the "D1 bind" no-smoothing rule). **Color:** trend-based (green up / danger down / muted flat). `<2` points → null.

### 14. `components/story/CaseStudyChart.tsx` — case-study visual (SVG, server-safe)
- **Surfaces:** `components/story/CaseStudyCard.tsx` (data from `lib/story-content.ts`).
- **Type:** `type:"line"` (prob line + 50% ref + annotated moment) OR `type:"bars"` (DOM bars). **Axis:** line maps prob 0–100 to fixed height. **Smoothing:** ✅ NONE — `M/L` segments. **Color:** design tokens via `currentColor`.

### 15. `components/FuturesHero.tsx` — inline mini sparkline (SVG, no separate component)
- **Surfaces:** the futures hero. Inline `<svg viewBox="0 0 116 50">` `<path>` from `sparklinePoints` (lines 114–139), raw `M/L`, end dot, `var(--accent-brand)`. Renders only for ≥3 points. **Smoothing:** ✅ NONE. A fourth copy-pasted sparkline.

### Not a chart (noted to prevent mis-triage)
- **The "golfLive" branch** — `components/event/EventLeaderboard.tsx:471`: `golfLive = live && competitors.some(c => c.thru != null || c.position != null)` → renders a golf leaderboard **TABLE** (pos · name · to-par · thru · win% · finish cols, "Missed cut" group), NOT a data-viz chart. Golf's actual chart treatment is the `greenTheme`/`timeMarkers` (R1–R4) props threaded into FuturesChart by the wrappers.
- **Bar widgets** (not line/scatter charts): `ProbabilityBar.tsx`, `SeriesProbability.tsx`, `ProgressionLadder.tsx`.
- **Discover card "kernels"** (`components/discover/kernels/*`: Claim/Duel/Field/Quantity/Container) are the CARD family (bars/badges), no line/scatter charts inside. NB: this card taxonomy shares the word "kernel" with the CHART kernels in Part 3 — they are different taxonomies.

---

## PART 2 — DUPLICATION MAP

**A. THREE separate multi-line time-series engines (the "field" kernel), grown apart — the core drift:**
| Engine | Tech | Smoothing | Y axis |
|--------|------|-----------|--------|
| `FuturesChart` | hand-rolled SVG | NONE ✅ | `fixedYAxis` opt-in (default auto) |
| `EvolutionChart` | recharts | `monotone` ❌ | auto-scaled + padding |
| `TournamentChart` | recharts | `monotone` ❌ | `[0,"auto"]` |
Same job (top-N probability lines over time), three axis philosophies, two smoothing behaviors. FuturesChart is the only one that can honor no-smoothing + fixed-axis; the two recharts engines predate/diverge from it. **This is exactly the drift class that hid the `slice(0,5)` bug** — three engines each re-deriving line selection and axis independently.

**B. OddsChart ↔ ScoreDifferentialChart — near-copy scaffolding.** Both replicate minute-bucket `ensurePoint`/`toMinuteKey`, gap-fill loop, forward-fill, per-source time-range `useMemo` filters, the vertical writing-mode team-label rail, period-boundary dedup, and the `sharedTicks`/`chartStartTime`/`chartEndTime` contract. Intentionally coupled (shared x-axis) but copy-pasted rather than sharing helpers.

**C. FOUR sparkline implementations, no shared helper:**
- `components/event/Sparkline.tsx` — `<polyline>` straight, trend-colored.
- `components/weather/Sparkline.tsx` — cubic **bezier** (the smoothing outlier), area fill, animation.
- `components/FuturesHero.tsx` inline `<path>` — straight `M/L`, end dot.
- `components/story/CaseStudyChart.tsx` (line variant) — straight `M/L`, area fill, annotation.
Same shape (min/max normalize → path), four copies, one of which smooths against principle 1.

**D. TWO hand-rolled "px/py-scale" SVG charts** — `CalibrationChart.tsx` and `DisagreementChart.tsx` share the same skeleton (`padL/padR/padT/padB`, `px()`/`py()` scale closures, `<rect>` bg, grid map, `<polyline>` series, rotated y-label, inline legend). Independent copies.

**E. DUPLICATED color systems.** Five near-identical index palettes: `DEFAULT_COLORS` (FuturesChart:6), `GOLD_COLORS`/`GREEN_COLORS` (FuturesChart), `EVOLUTION_COLORS` (EvolutionChart:21), `POSITION_COLORS` (TournamentChart:24). PLUS three copies of the per-source config map with **different hexes for the same source**: `FALLBACK_SOURCE_CONFIG` (OddsChart:30, betting `#0f172a`), `SOURCE_COLORS` (DisagreementChart:5, betting `#374151`), `SOURCE_DISPLAY` (TournamentChart:34). No single source-color registry.

**F. The `slice(0, N)` / top-N cap, scattered across 8+ sites** (each chart re-implements its own line cap; no shared "top-N contenders" selector):
`FuturesChart:89` `slice(0,5)` · `TotalPointsSpectrum:79` 5 thresholds · `RaceToTitleChart:37` Top-5 default · `SettledPathChart:98` `slice(0,6)` · WinnerEvolutionChart top-5 · `TournamentChart:209` `slice(0,3)` / `:225` `slice(0,topN)` / `:482` `slice(0,15)` · `TwoSidedTimeline:36` `slice(0,2)` · `FuturesCard:88` `slice(0,5)`.

**G. FOUR time-range vocabularies.** `lib/chartWindow.ts` `CHART_RANGES` (All/1M/1W/1D/Since-start, used only by FuturesChart wrappers); OddsChart/ScoreDiff own `TIME_RANGE_OPTIONS` (All/Since-Start); EvolutionView own (full/tournament/7d/24h/today); RaceToTitle/TwoSided own (24h/7d/All).

---

## PART 3 — COUNT: IMPLEMENTATIONS vs KERNELS

**Distinct chart implementations: 15** (excluding the 5 FuturesChart wrappers, the golfLive leaderboard table, and pure bar widgets):

1. FuturesChart · 2. OddsChart · 3. ScoreDifferentialChart · 4. CalibrationChart · 5. DisagreementChart · 6. EvolutionChart · 7. TournamentChart · 8. MarketMap(+Section) · 9. ThresholdSparkline · 10. TotalPointsSpectrum · 11. weather/DistributionPanel · 12. weather/Sparkline · 13. event/Sparkline · 14. story/CaseStudyChart · 15. FuturesHero inline sparkline.

**15 distinct implementations → 4 conceptual kernels:**

| Kernel | Implementations | Redundancy |
|--------|-----------------|-----------|
| **(a) Duel 2-line** | OddsChart (home vs away across 50%), TwoSidedTimeline (FuturesChart `slice(0,2)`) | 2 |
| **(b) Field multi-line** | FuturesChart, EvolutionChart, TournamentChart (+ wrappers RaceToTitle/WinnerEvolution/SettledPath ride FuturesChart) | **3 full engines** |
| **(c) Single-market line** | DisagreementChart, ScoreDifferentialChart (spread-over-time), story/CaseStudyChart (line), event/Sparkline, weather/Sparkline, FuturesHero inline | **6 copies** |
| **(d) Distribution** | CalibrationChart (reliability), MarketMap (density rail), ThresholdSparkline (threshold dots), TotalPointsSpectrum (scoring ladder), weather/DistributionPanel (histogram), story/CaseStudyChart (bars) | **6 unrelated renderers** |

So **15 implementations collapse to 4 kernels**, and within kernels the redundancy is stark: (b) has 3 competing engines, (c) has 6 copy-pasted line/sparkline renderers, (d) has 6 unrelated distribution renderers.

---

## PART 4 — PRINCIPLE-ADHERENCE SUMMARY (the audit scorecard)

| Principle | HONORED | VIOLATED |
|-----------|---------|----------|
| **NO smoothing** | FuturesChart (+all wrappers), CalibrationChart, DisagreementChart, event/Sparkline, CaseStudyChart, FuturesHero | **OddsChart, ScoreDifferentialChart, EvolutionChart, TournamentChart** (all recharts `type="monotone"`) + **weather/Sparkline** (cubic bezier) |
| **Fixed 0–100 Y** | OddsChart (`[0,100]`), CalibrationChart (both axes), DisagreementChart, all FuturesChart wrappers (`fixedYAxis`) | **EvolutionChart** (padded auto), **TournamentChart** (`[0,"auto"]`), bare **FuturesChart** default. (ScoreDiff is intentionally symmetric-around-0 — a spread, not a probability, so out of rubric.) |
| **Prominent blend + faint sources** | **ONLY OddsChart Mode A** (`strokeWidth 3` blend vs `strokeWidth 1, opacity 0.28` sources) | FuturesChart, EvolutionChart, TournamentChart, DisagreementChart all draw lines at comparable weight |
| **Kalshi-minimal chrome** | FuturesChart, Calibration, Disagreement, sparklines | OddsChart / ScoreDiff carry the heaviest chrome (period lines, lead-change diamonds, dual legends) |

### Headline findings for the program (fact, not recommendation)
1. **The recharts family violates no-smoothing uniformly.** All 4 recharts charts (OddsChart, ScoreDiff, EvolutionChart, TournamentChart) use `type="monotone"`; the hand-rolled family does not. Smoothing correlates 1:1 with the rendering tech.
2. **The blend-hero treatment exists in exactly one place** (OddsChart Mode A). Every futures/field chart draws all lines at equal weight — the single most visible gap vs "prominent blend."
3. **Fixed-axis is opt-in in the most-reused engine.** FuturesChart defaults to auto-scale; only the callers that remember to pass `fixedYAxis` honor principle 2. The two recharts field engines can't honor it at all today.
4. **Kernel (b) has 3 engines.** Consolidating the field multi-line kernel onto one implementation (FuturesChart is the only principle-honoring candidate) would resolve findings 1–3 for the futures/tournament surfaces in one move — and is where the `slice(0,5)`-style drift bugs live.

*This census is descriptive only. No redesign, ranking, or taste call is made here — that is the next program's job.*
