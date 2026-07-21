# THE CHART CENSUS

**Queue:** L2-148 Item 2 (produced) · L2-149 (field-kernel consolidation applied) · **Produced:** 2026-07-21.
**Purpose:** the "our side" half of the win-prob chart competitive audit ("Kalshi and ESPN are meaningfully better at data viz"). Step one is knowing exactly what we have before any redesign or taste call.

> **L2-149 UPDATE (2026-07-21):** The field multi-line kernel has been consolidated onto **FuturesChart** (Part 2A finding executed). The two competing recharts engines — **EvolutionChart** and **TournamentChart** — are **deleted**. EvolutionView now renders FuturesChart directly (windowing/combined/highlight/round-markers preserved, colors shared with the leaderboard via a `outcomeColors` map); TournamentChart was already dead code (imported nowhere since the #883 refactor). FuturesChart's `fixedYAxis` is now the **NON-OPTIONAL default** (opt-out), so every field/futures surface honors principle 2. Implementation count **15 → 13**. Sections below are annotated with `[L2-149]` where the state changed; the original descriptive text is retained for history.

All paths under `frontend/`. Two rendering technologies coexist:
- **recharts** (`recharts@^2.12.0`, the only chart lib in `package.json`) — OddsChart, ScoreDifferentialChart. `[L2-149]` EvolutionChart + TournamentChart **removed** — the recharts family is now the two single-game event charts only.
- **hand-rolled SVG** (`<path>`/`<polyline>` + manual scale math) — FuturesChart (the sole field kernel) and everything else.
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
- **Axis:** `[L2-149]` Y is now **fixed 0–100 by default** (`fixedYAxis = true`, opt-out via `fixedYAxis={false}`; `maxProb = fixedYAxis ? 1 : Math.min(1, maxProb * 1.1)`). X is time-based linear. Gridlines at `[0,0.25,0.5,0.75,1]`.
- **Color:** three index-based palettes — `DEFAULT_COLORS` (blue/red/green/…), `GOLD_COLORS` (leader gold + grays), `GREEN_COLORS` (Augusta green + grays). `[L2-149]` plus an optional `outcomeColors` map (per-outcome override keyed by `outcome_id`) so a caller can keep lines in sync with an external leaderboard; eliminated contenders draw thin + dashed + faded grey. All contender lines still equal weight (no blend-hero — a field chart has no single blend line; that treatment lives in OddsChart).
- **Smoothing:** ✅ **NONE.** Raw `M/L` segments or explicit step (`H…V…` when `stepInterpolation`).
- **Chrome:** dashed gridlines `#e5e7eb`, ≤5 x-ticks, flex-wrap legend, crosshair hover tooltip. `[L2-149]` optional round/state `timeMarkers`, hover-highlight dimming (`highlightedOutcomeId`/`onHoverOutcome`), and an opt-in dashed "Combined" summed line — all migrated from EvolutionChart. Still minimal.
- **Line cap:** `historyData.slice(0, 5)` when nothing is selected; "Showing top 5 outcomes" note.
- **Live:** none itself — parents feed SWR data. **Mobile:** `overflow-x-auto`, `min-w-[600px]`, mouse-only crosshair.
- **Principle scorecard `[L2-149]`:** smoothing ✅ · fixed-axis ✅ (now default-on) · faint-blend n/a (field kernel, no single blend) · minimal chrome ✅. **This is the sole field multi-line engine.**

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

### 6. `components/EvolutionChart.tsx` — futures evolution (recharts LineChart) — **`[L2-149]` DELETED**
- **Status:** removed. Its sole consumer `EvolutionView.tsx` now renders **FuturesChart** directly. Behavior preserved: time-range windowing (moved into EvolutionView's `windowByTimeRange`), the "Combined" summed line, hover-highlight dimming, round-boundary markers (→ FuturesChart `timeMarkers`), and eliminated treatment. Colors now come from a shared `outcomeColors` map so the chart lines and the leaderboard dots match exactly.
- **Why it violated:** was recharts `<Line type="monotone">` (smoothing ❌) on an **auto-scaled + padded** Y axis (fixed-0–100 ❌). Both violations are gone: FuturesChart draws raw segments on a fixed 0–100 axis. *(Historical: surfaced on `app/futures/[id]`, `app/sport/[sport]/[league]` (+ `[slug]`), `app/categories/golf` + `/tournaments/[slug]`.)*

### 7. `components/TournamentChart.tsx` — tournament probability timeline (recharts) — **`[L2-149]` DELETED (was already dead code)**
- **Status:** removed. Imported **nowhere** — the futures-detail hero replaced it with FuturesChart in the #883 refactor (only a past-tense comment referenced it). Deleting it removes one recharts `ComposedChart` engine at zero surface risk. *(Historical: `<Line type="monotone">` smoothing ❌ on `domain={[0,"auto"]}` fixed-0–100 ❌; carried its own leaderboard table + cross-source panel.)*

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

**A. `[L2-149]` RESOLVED — ONE field engine now.** Was three separate multi-line time-series engines grown apart (the core drift); consolidated onto FuturesChart.
| Engine | Tech | Smoothing | Y axis | Status |
|--------|------|-----------|--------|--------|
| `FuturesChart` | hand-rolled SVG | NONE ✅ | **fixed 0–100 default** ✅ | **the sole field kernel** |
| `EvolutionChart` | recharts | `monotone` ❌ | auto-scaled + padding | **DELETED** (EvolutionView → FuturesChart) |
| `TournamentChart` | recharts | `monotone` ❌ | `[0,"auto"]` | **DELETED** (was dead code) |
Same job (top-N probability lines over time) is now served by one implementation that honors no-smoothing + fixed-axis. **This closes the drift class that hid the `slice(0,5)` bug** — line selection and axis are derived in exactly one place.

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

**`[L2-149]` Distinct chart implementations: 13** (was 15; EvolutionChart + TournamentChart deleted). Excludes the 5 FuturesChart wrappers, the golfLive leaderboard table, and pure bar widgets:

1. FuturesChart · 2. OddsChart · 3. ScoreDifferentialChart · 4. CalibrationChart · 5. DisagreementChart · 6. MarketMap(+Section) · 7. ThresholdSparkline · 8. TotalPointsSpectrum · 9. weather/DistributionPanel · 10. weather/Sparkline · 11. event/Sparkline · 12. story/CaseStudyChart · 13. FuturesHero inline sparkline.

**13 distinct implementations → 4 conceptual kernels:**

| Kernel | Implementations | Redundancy |
|--------|-----------------|-----------|
| **(a) Duel 2-line** | OddsChart (home vs away across 50%), TwoSidedTimeline (FuturesChart `slice(0,2)`) | 2 |
| **(b) Field multi-line** | **FuturesChart** (+ wrappers RaceToTitle/WinnerEvolution/SettledPath, and EvolutionView, all ride FuturesChart) | **`[L2-149]` 1 engine** (was 3) |
| **(c) Single-market line** | DisagreementChart, ScoreDifferentialChart (spread-over-time), story/CaseStudyChart (line), event/Sparkline, weather/Sparkline, FuturesHero inline | **6 copies** |
| **(d) Distribution** | CalibrationChart (reliability), MarketMap (density rail), ThresholdSparkline (threshold dots), TotalPointsSpectrum (scoring ladder), weather/DistributionPanel (histogram), story/CaseStudyChart (bars) | **6 unrelated renderers** |

So **13 implementations collapse to 4 kernels**. `[L2-149]` closed kernel (b)'s 3-engine drift (now 1). Remaining redundancy: (c) has 6 copy-pasted line/sparkline renderers, (d) has 6 unrelated distribution renderers — candidates for a future pass.

---

## PART 4 — PRINCIPLE-ADHERENCE SUMMARY (the audit scorecard)

| Principle | HONORED | VIOLATED |
|-----------|---------|----------|
| **NO smoothing** | FuturesChart (+all wrappers, +EvolutionView), CalibrationChart, DisagreementChart, event/Sparkline, CaseStudyChart, FuturesHero | **OddsChart, ScoreDifferentialChart** (recharts `type="monotone"`) + **weather/Sparkline** (cubic bezier). `[L2-149]` EvolutionChart + TournamentChart removed from this list — deleted. |
| **Fixed 0–100 Y** | OddsChart (`[0,100]`), CalibrationChart (both axes), DisagreementChart, **FuturesChart (now default) + all its wrappers + EvolutionView** | (ScoreDiff is intentionally symmetric-around-0 — a spread, not a probability, so out of rubric.) `[L2-149]` the three prior offenders (EvolutionChart, TournamentChart, bare-FuturesChart default) are all resolved. |
| **Prominent blend + faint sources** | **ONLY OddsChart Mode A** (`strokeWidth 3` blend vs `strokeWidth 1, opacity 0.28` sources) | FuturesChart, DisagreementChart draw contender lines at comparable weight. *(A field chart has no single blend line, so this principle is really an OddsChart/duel-kernel concern — out of scope for the field kernel.)* |
| **Kalshi-minimal chrome** | FuturesChart, Calibration, Disagreement, sparklines | OddsChart / ScoreDiff carry the heaviest chrome (period lines, lead-change diamonds, dual legends) |

### Headline findings for the program (fact, not recommendation)
1. `[L2-149 RESOLVED]` **The recharts field engines are gone.** Of the original 4 recharts charts, EvolutionChart + TournamentChart (both `type="monotone"`) are deleted; only OddsChart + ScoreDiff (the two single-game event charts) remain on recharts. weather/Sparkline's bezier is the last hand-rolled smoothing outlier.
2. **The blend-hero treatment exists in exactly one place** (OddsChart Mode A). This is a duel-kernel property (one blend vs faint sources); the field kernel has no single blend line, so it is out of scope for FuturesChart.
3. `[L2-149 RESOLVED]` **Fixed-axis is now the default in the field kernel.** FuturesChart defaults to `fixedYAxis` (opt-out); every field/futures surface honors principle 2 without remembering a prop.
4. `[L2-149 RESOLVED]` **Kernel (b) is now 1 engine.** The field multi-line kernel is consolidated onto FuturesChart — findings 1 & 3 resolved for the futures/tournament surfaces, and the `slice(0,5)`-style drift class is closed (line selection + axis derived in one place).

*This census was descriptive; the L2-149 annotations record the field-kernel consolidation that executed the standing rulings (no smoothing · fixed 0–100 · minimal chrome). Redesign/taste calls remain the next program's job.*
