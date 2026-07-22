# THE CHART CENSUS

**Queue:** L2-148 Item 2 (produced) · L2-149 (field-kernel consolidation) · L2-150 (single-market-kernel consolidation) · **Produced:** 2026-07-21, **updated:** 2026-07-22.
**Purpose:** the "our side" half of the win-prob chart competitive audit ("Kalshi and ESPN are meaningfully better at data viz"). Step one is knowing exactly what we have before any redesign or taste call.

> **L2-149 UPDATE (2026-07-21):** The field multi-line kernel has been consolidated onto **FuturesChart** (Part 2A finding executed). The two competing recharts engines — **EvolutionChart** and **TournamentChart** — are **deleted**. EvolutionView now renders FuturesChart directly (windowing/combined/highlight/round-markers preserved, colors shared with the leaderboard via a `outcomeColors` map); TournamentChart was already dead code (imported nowhere since the #883 refactor). FuturesChart's `fixedYAxis` is now the **NON-OPTIONAL default** (opt-out), so every field/futures surface honors principle 2. Implementation count **15 → 13**. Sections below are annotated with `[L2-149]` where the state changed; the original descriptive text is retained for history.

> **L2-150 UPDATE (2026-07-22):** The **single-market line kernel (c)** has been consolidated onto ONE shared renderer, **`components/Sparkline.tsx`** (SSR-safe, no client hooks). Five copy-pasted single-market line/sparkline renderers now ride it: **event/Sparkline** (deleted), **weather/Sparkline** (deleted — its cubic **bezier is KILLED**, the last hand-rolled smoothing outlier), the **FuturesHero inline** `<path>` (replaced), the **politics-table inline** `Sparkline` (replaced — a census miss, it was never in the original 13), and **story/CaseStudyChart**'s `type:"line"` (its line/area/50%-ref/annotated-moment now come from the shared component via props; CaseStudyChart keeps only its `bars` variant). The shared component takes a `domain` mode (**default [0,100] pins probability honestly** per ruling #2; `[0,1]` for 0–1 inputs; `"auto"` for physical quantities) and the genuinely-needed variants (size, stroke, filled-area gradient/flat, end dot, reference line, annotation+label, caption, draw-on animation w/ CSS reduced-motion). Implementation count **13 → 11**. **NOTE on the miscategorization:** the original Part-3 kernel-(c) table lumped **ScoreDifferentialChart** and **DisagreementChart** under "single-market line," but they are NOT single-market — ScoreDiff is a 5-series recharts spread chart on a symmetric-around-0 axis, coupled to OddsChart's shared-x-axis scaffolding (duplication **class B**), and DisagreementChart is a hand-rolled *multi-source* admin chart sharing CalibrationChart's px/py skeleton (duplication **class D**). Folding either into a sparkline would be an architectural/taste call this queue explicitly forbade, so they are **recategorized to their true classes (B and D)** and left for those kernel passes — kernel (c) is now genuinely 1 renderer. This is why the count lands at 11, not the census's arithmetic "8" (which assumed all 6 kernel-(c) rows collapse). Sections below carry `[L2-150]` annotations.

> **L2-152 UPDATE (2026-07-22) — CENSUS CLOSE-OUT.** Three remnants finished; this closes the census program. (1) **Class D dedup:** CalibrationChart's and DisagreementChart's genuinely-identical px/py skeleton (plot-box geometry + the two linear scale closures) is extracted to **`lib/chartScale.ts`** (`plotDims`/`scaleX`/`scaleY`, pure math, no React) — arithmetic mirrors both originals so output is byte-for-byte pixel-identical. (2) **Kernel (d) honest pass:** the 6 distribution renderers were evaluated the way L2-150 evaluated kernel (c) — consolidate only true near-copies. Verdict: **all 6 stay separate**; they are genuinely-distinct chart types on distinct tech (see the per-renderer reasons in Part 3). The only real kernel-(d) dedup was Calibration↔Disagreement's px/py skeleton, and that is (1) — note DisagreementChart is a multi-source *timeline*, not itself a kernel-(d) member. (3) **Admin monotone sweep:** the 14 `type="monotone"` in `app/admin/page.tsx` (5) + `app/admin/analytics/page.tsx` (9) — admin ops charts never inventoried in the 15 — are now `type="linear"`, completing a **literal codebase-wide zero `type="monotone"`** (OddsChart + ScoreDiff were already flipped in L2-151; the stale Part-1/Part-4 text below is corrected). Implementation count is **unchanged at 11** (a dedup of shared skeleton, not of whole renderers). See the **CLOSING SUMMARY** at the end.

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
- **Smoothing:** `[L2-151]` ✅ **NONE** — every prob `<Line>`/`<Area>` is now `type="linear"` (raw segments); actual-score line uses `stepAfter`. *(Historical: was `type="monotone"` — the recharts monotone curve; flipped to linear in L2-151.)*
- **Chrome:** `CartesianGrid strokeDasharray="3 3"`, rich game-state tooltip, period ReferenceLines, lead-change diamonds (default off), current-prob callout, legend linking to `/events/{id}/models`. Heaviest chrome of any chart.
- **Live:** `isLive` defaults range to "Since Start"; re-renders on new history. **Mobile:** `ResponsiveContainer`.
- **Scorecard `[L2-151]`:** smoothing ✅ (linear) · fixed-axis ✅ · faint-blend ✅ (Mode A) · minimal chrome ⚠️ (feature-rich).

### 3. `components/ScoreDifferentialChart.tsx` — spread / score-diff (recharts, ~798 lines) — near-sibling of OddsChart
- **Surfaces:** `app/events/[id]/page.tsx` (paired below OddsChart, shares x-axis).
- **Axis:** Y **symmetric around 0** (auto — `domainMax = max(2, ceil(maxAbs/2)*2)`, lines 482–487) — NOT 0–100 (a spread chart, not a probability chart). X categorical-by-minute, shares `chartStartTime/chartEndTime/sharedTicks` with OddsChart.
- **Color:** projected `#10b981`, actual `#f97316`, kalshi `#7c3aed`, polymarket `#db2777`, books `rgba(0,0,0,0.12)`.
- **Smoothing:** `[L2-151]` ✅ **NONE** on projected/PM lines (now `type="linear"`); actual uses `stepAfter` (line 723). *(Historical: was `type="monotone"`; flipped in L2-151.)*
- **Chrome:** shares OddsChart scaffolding (time-range pills, vertical team-label rail, period ReferenceLines, legend).
- **Duplication (class B):** `[L2-151]` the genuinely-identical minute-bucket / point-seed / gap-fill primitives now live in the shared `lib/chartTimeline.ts`; each chart still owns its column shapes, domain derivation, and time-range vocabulary (the remaining, intentionally-coupled scaffolding). The two `type="monotone"` smoothing violations that class B also carried are resolved (both linear).

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

### 12. `components/weather/Sparkline.tsx` — smoothed sparkline (SVG) ⚠️ smoothing outlier — **`[L2-150]` DELETED**
- **Status:** removed. WildCards + WeatherHero now render the shared **`components/Sparkline.tsx`** with `area="gradient" endDot animate`. The **cubic Catmull-Rom→bezier is KILLED** — the shared renderer draws raw `M/L` segments (ruling #1). *(Historical: built a `C${cp1x}…` bezier path, lines 37–52 — the only true bezier sparkline in the codebase; gradient area fill, draw-on animation, end dot.)*

### 13. `components/event/Sparkline.tsx` — straight sparkline (SVG) — **`[L2-150]` DELETED (→ `components/Sparkline.tsx`)**
- **Status:** removed. EventLeaderboard now renders the shared **`components/Sparkline.tsx`** (`domain={[0,1]}`, trend color). *(Historical: `<polyline>` straight segments citing the "D1 bind" no-smoothing rule; trend-based color (green up / danger down / muted flat); `<2` points → null.)*

### 14. `components/story/CaseStudyChart.tsx` — case-study visual (SVG, server-safe) — **`[L2-150]` line variant folded**
- **Surfaces:** `components/story/CaseStudyCard.tsx` (data from `lib/story-content.ts`; rendered only from the two `"use client"` pages `app/about` + `app/admin/story`).
- **Type:** `[L2-150]` the `type:"line"` variant (prob line + 50% ref + annotated moment + caption) now delegates entirely to the shared **`components/Sparkline.tsx`** (`area="flat" referenceValue={50} annotation={…} caption={…} domain={[0,100]}`); CaseStudyChart keeps only its `type:"bars"` (DOM bars) renderer + the type dispatcher. **Axis:** prob 0–100 fixed. **Smoothing:** ✅ NONE — `M/L`. It therefore stays counted as an implementation for its **bars** kernel (d), not the single-market line kernel (c).

### 15. `components/FuturesHero.tsx` — inline mini sparkline (SVG) — **`[L2-150]` replaced by shared `Sparkline`**
- **Status:** the inline `<svg viewBox="0 0 116 50">` `<path>` (formerly lines 114–139) is replaced by the shared **`components/Sparkline.tsx`** (`domain={[0,1]}`, `color="var(--accent-brand)"`, `endDot`). FuturesHero itself remains (it is a hero layout, not a chart) but no longer carries its own chart implementation. **Smoothing:** ✅ NONE. *(Historical: raw `M/L`, end dot, `var(--accent-brand)`, ≥3 points — the fourth copy-pasted sparkline.)*

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

**B. `[L2-151]` PARTIALLY RESOLVED — OddsChart ↔ ScoreDifferentialChart.** Both replicated minute-bucket `ensurePoint`/`toMinuteKey`, gap-fill loop, forward-fill, per-source time-range `useMemo` filters, the vertical writing-mode team-label rail, period-boundary dedup, and the `sharedTicks`/`chartStartTime`/`chartEndTime` contract. `[L2-151]` the genuinely-identical minute-bucket / point-seed / gap-fill primitives are extracted to **`lib/chartTimeline.ts`** (`toMinuteKey`/`makeEnsurePoint`/seed-every-minute, pure logic, no React); both charts' `type="monotone"` lines were flipped to `type="linear"`. Remaining is the intentionally-coupled shared-x-axis scaffolding (column shapes, domain derivation, team-label rail) — kept per-chart deliberately, not copy-paste drift.

**C. `[L2-150]` RESOLVED — ONE shared single-market renderer now.** Was FOUR (really FIVE — the census missed one) copy-pasted sparkline implementations with no shared helper; consolidated onto **`components/Sparkline.tsx`**:
- ~~`components/event/Sparkline.tsx`~~ — DELETED (trend-colored polyline → shared).
- ~~`components/weather/Sparkline.tsx`~~ — DELETED; the cubic **bezier is killed** (was the smoothing outlier), area + animation preserved as shared-component props.
- ~~`components/FuturesHero.tsx` inline~~ — replaced (straight `M/L`, end dot).
- ~~`components/story/CaseStudyChart.tsx` (line variant)~~ — folded (straight `M/L`, area fill, annotation, 50%-ref, caption — all now shared props).
- ~~`app/politics/page.tsx` inline `Sparkline`~~ — replaced (a fifth copy the census originally missed).
Same shape (normalize → path), now one implementation that honors ruling #1 (no smoothing) and ruling #2 (fixed 0–100 for probability via a `domain` mode). *(Not folded: `app/categories/golf/page.tsx`'s `TrendSparkline` is a **multi-line** auto-scaled field mini-chart — kernel (b) territory, not single-market — so it stays out of this pass.)*

**D. `[L2-152]` RESOLVED — the two hand-rolled "px/py-scale" SVG charts.** `CalibrationChart.tsx` and `DisagreementChart.tsx` shared the same skeleton (`padL/padR/padT/padB` → `plotW/plotH`, the `px()`/`py()` linear scale closures, `<rect>` bg, grid map, `<polyline>` series, rotated y-label, inline legend). `[L2-152]` the genuinely-identical primitives — the plot-box geometry and the two linear scale closures — are extracted to **`lib/chartScale.ts`** (`plotDims`/`scaleX`/`scaleY`, pure math, no React). Both charts consume it; arithmetic mirrors the originals exactly so output is byte-for-byte pixel-identical. Each chart still owns its own domain (Calibration fixed 0–100 × 0–100; Disagreement time × 0–1), grid, marks, and legend — those are genuinely-distinct, not copies. *(NB: DisagreementChart is a multi-source win-prob **timeline**, not a distribution renderer — it is NOT a kernel-(d) member; the shared skeleton is what links it to CalibrationChart.)*

**E. DUPLICATED color systems.** Five near-identical index palettes: `DEFAULT_COLORS` (FuturesChart:6), `GOLD_COLORS`/`GREEN_COLORS` (FuturesChart), `EVOLUTION_COLORS` (EvolutionChart:21), `POSITION_COLORS` (TournamentChart:24). PLUS three copies of the per-source config map with **different hexes for the same source**: `FALLBACK_SOURCE_CONFIG` (OddsChart:30, betting `#0f172a`), `SOURCE_COLORS` (DisagreementChart:5, betting `#374151`), `SOURCE_DISPLAY` (TournamentChart:34). No single source-color registry.

> **`[L2-155]` SOURCE-COLOR HALF RESOLVED — one registry, `frontend/lib/sourceColors.ts`.** The per-source drift is fixed at the root. On a full sweep the drift was worse than the census's "3 copies": **12** source-color definition sites disagreed on the same source (kalshi was green in charts, indigo `#6366F1` in SourceAggregationBlock, blue `#2563eb` in calibration, red `#ef4444` in the admin coverage chart; betting/odds_api was `#0f172a` / `#374151` / `#16a34a` / `#3b82f6` across surfaces). All are now migrated to ONE registry (canonical hex + faint/fg + alias/case resolver); canonicalization rule = the flagship OddsChart hex wins on conflict (globals.css carries no per-source token), no new colors invented. Migrated: OddsChart config+inline, events/[id]/models `FALLBACK_SOURCES`, DisagreementChart, admin/source-intelligence, calibration page, categories/golf `SOURCE_META`, weather/data `SOURCES`, SourceAggregationBlock (kalshi/poly; sportsbook brand palette kept), CombinedMarketCard / CombinedFeedCard / my-stuff (Tailwind classes → registry hex). Grep guard green: no per-source hex or `{dot,text}` map outside the registry. **One documented exception:** `app/admin/page.tsx`'s "Source Coverage Trend" is an internal 7-series diagnostic whose keys include non-source buckets (`ESPN WP`/`Model`/`StatPal`) and must stay visually separable — intentionally not migrated (commented in-code).
>
> **Still open (index/outcome-palette half):** the FIVE index palettes above (`DEFAULT_COLORS`/`GOLD_COLORS`/`GREEN_COLORS`/`EVOLUTION_COLORS`/`POSITION_COLORS`) color per-**outcome/competitor** series, NOT data sources — a distinct unification (a shared "series palette") that L2-155 does not touch. Left as a separate follow-up.

**F. The `slice(0, N)` / top-N cap, scattered across 8+ sites** (each chart re-implements its own line cap; no shared "top-N contenders" selector):
`FuturesChart:89` `slice(0,5)` · `TotalPointsSpectrum:79` 5 thresholds · `RaceToTitleChart:37` Top-5 default · `SettledPathChart:98` `slice(0,6)` · WinnerEvolutionChart top-5 · `TournamentChart:209` `slice(0,3)` / `:225` `slice(0,topN)` / `:482` `slice(0,15)` · `TwoSidedTimeline:36` `slice(0,2)` · `FuturesCard:88` `slice(0,5)`.

**G. FOUR time-range vocabularies.** `lib/chartWindow.ts` `CHART_RANGES` (All/1M/1W/1D/Since-start, used only by FuturesChart wrappers); OddsChart/ScoreDiff own `TIME_RANGE_OPTIONS` (All/Since-Start); EvolutionView own (full/tournament/7d/24h/today); RaceToTitle/TwoSided own (24h/7d/All).

---

## PART 3 — COUNT: IMPLEMENTATIONS vs KERNELS

**`[L2-152]` Distinct chart implementations: 11** (was 13; L2-150 deleted weather/Sparkline + event/Sparkline + the FuturesHero-inline chart and added the one shared `components/Sparkline.tsx`; **L2-152 dedups a shared *skeleton* across two of the 11 but deletes no whole renderer, so the count holds at 11**). Excludes the 5 FuturesChart wrappers, the golfLive leaderboard table, and pure bar widgets:

1. FuturesChart · 2. OddsChart · 3. ScoreDifferentialChart · 4. CalibrationChart · 5. DisagreementChart · 6. MarketMap(+Section) · 7. ThresholdSparkline · 8. TotalPointsSpectrum · 9. weather/DistributionPanel · 10. **`components/Sparkline.tsx`** (the shared single-market line kernel) · 11. story/CaseStudyChart (now `bars`-only + type dispatcher).

**11 distinct implementations → 4 conceptual kernels:**

| Kernel | Implementations | Redundancy |
|--------|-----------------|-----------|
| **(a) Duel 2-line** | OddsChart (home vs away across 50%), TwoSidedTimeline (FuturesChart `slice(0,2)`) | 2 |
| **(b) Field multi-line** | **FuturesChart** (+ wrappers RaceToTitle/WinnerEvolution/SettledPath, and EvolutionView, all ride FuturesChart) | **`[L2-149]` 1 engine** (was 3) |
| **(c) Single-market line** | **`components/Sparkline.tsx`** (event leaderboard, weather ×2, politics, futures hero, story case-study line — all ride it) | **`[L2-150]` 1 renderer** (was 6, incl. 2 miscategorized — see below) |
| **(d) Distribution** | CalibrationChart (reliability), MarketMap (density rail), ThresholdSparkline (threshold dots), TotalPointsSpectrum (scoring ladder), weather/DistributionPanel (histogram), story/CaseStudyChart (bars) | **`[L2-152]` 6 genuinely-distinct renderers — evaluated, stay separate** |

So **11 implementations collapse to 4 kernels**. `[L2-149]` closed kernel (b)'s 3-engine drift (3→1); `[L2-150]` closed kernel (c)'s copy-paste class (6→1). **`[L2-150]` recategorization:** the two rows the original table listed under (c) that are NOT single-market — **ScoreDifferentialChart** (5-series spread, symmetric axis, OddsChart-coupled scaffolding) and **DisagreementChart** (admin *multi-source* timeline, px/py skeleton) — move to their true duplication classes **B** and **D** respectively (they were never sparklines; folding them would be an architectural/taste call).

**`[L2-152]` kernel (d) — HONEST evaluation (evaluated like L2-150, not force-folded).** The census labeled these "6 unrelated distribution renderers." Evaluated pairwise for true near-copy status; verdict: **all 6 stay separate.** They are genuinely-distinct chart *types* on distinct rendering tech and data shapes — consolidating any would be the "forced consolidation" this queue explicitly forbade. One line each on why:
- **CalibrationChart** — the only **2-axis SVG px/py scatter** (predicted × actual reliability diagram): polyline + √n-sized dots + CI bars + perfect-calibration diagonal + ±5pp band. No other renderer is a 2D scatter. *(Its px/py skeleton — the one real dedup — is now shared via `lib/chartScale.ts`, class D above.)*
- **MarketMap** — the only **horizontal density-rail** chart: intensity `<rect>` cells + marker dots with SVG leader lines + `ResizeObserver`-driven layout + hover ladder. Value-position rail, not a bar/dot chart.
- **ThresholdSparkline** — a **1D value-positioned dot strip** built in **absolutely-positioned DOM + framer-motion** (dot size ∝ prob, color-by-tier, `whileHover`/`whileTap`). Not SVG; interactivity model is unique.
- **TotalPointsSpectrum** — a **stateful multi-mode composite** (pre/live/done): CSS-grid bar ladder + projection strip + pace overlay bars + HIT/MISS badges + monotonicity enforcement + minimal/full tiers. Far more than a bar renderer.
- **weather/DistributionPanel** — a **vertical histogram** over temp buckets (flex `items-end`, height ∝ prob), with a distinct **grouped cross-source paired-bar** variant (Poly vs Kalshi) + peak highlighting. Vertical, bucketed, cross-source — unlike any other.
- **story/CaseStudyChart (bars)** — **static horizontal `label | track | value` bar rows** for a case-study illustration (no state, no interactivity), design-system tokens only. Its line variant already rides the shared Sparkline; the bars variant is a presentational figure.
- **Why the bar-based trio does NOT fold:** DistributionPanel (vertical histogram), TotalPointsSpectrum (stateful horizontal ladder), and CaseStudyChart-bars (static horizontal rows) share only the ~5-line **percentage-bar `<div>` idiom** — but that idiom is a **design-system atom already shared by the explicitly-non-chart bar widgets** (`ProbabilityBar`, `SeriesProbability`, `ProgressionLadder`). Extracting it is a design-system task spanning those widgets, not a chart-kernel consolidation; folding just the three "charts" would be arbitrary and forced.

Remaining after L2-152: **class B** (OddsChart↔ScoreDiff) is the intentionally-coupled shared-x-axis scaffolding — its genuine primitives already share `lib/chartTimeline.ts` and its smoothing violations are gone; what's left is deliberate. **No open dedup class remains for this program.**

---

## PART 4 — PRINCIPLE-ADHERENCE SUMMARY (the audit scorecard)

| Principle | HONORED | VIOLATED |
|-----------|---------|----------|
| **NO smoothing** | **ALL CHARTS.** FuturesChart (+all wrappers, +EvolutionView), CalibrationChart, DisagreementChart, **`components/Sparkline.tsx`** (event/weather/politics/futures-hero/case-study line), **`[L2-151]` OddsChart + ScoreDifferentialChart** (flipped `type="monotone"`→`type="linear"`), **`[L2-152]` the admin ops charts** (14 monotone→linear). | **NONE.** `[L2-152]` literal codebase-wide zero `type="monotone"`. `[L2-150]` weather/Sparkline's cubic bezier killed; `[L2-149]` Evolution/Tournament deleted; `[L2-151]` the two recharts game charts flipped; `[L2-152]` admin charts flipped. Every renderer draws raw linear/step segments. |
| **Fixed 0–100 Y** | OddsChart (`[0,100]`), CalibrationChart (both axes), DisagreementChart, **FuturesChart (now default) + all its wrappers + EvolutionView**, **`[L2-150]` `components/Sparkline.tsx`** (probability `domain` defaults to [0,100]; physical quantities opt into `"auto"`) | (ScoreDiff is intentionally symmetric-around-0 — a spread, not a probability, so out of rubric.) `[L2-149]` EvolutionChart/TournamentChart/bare-FuturesChart offenders resolved; `[L2-150]` the single-market sparklines now pin probability honestly. |
| **Prominent blend + faint sources** | **ONLY OddsChart Mode A** (`strokeWidth 3` blend vs `strokeWidth 1, opacity 0.28` sources) | FuturesChart, DisagreementChart draw contender lines at comparable weight. *(A field chart has no single blend line, so this principle is really an OddsChart/duel-kernel concern — out of scope for the field kernel.)* |
| **Kalshi-minimal chrome** | FuturesChart, Calibration, Disagreement, sparklines | OddsChart / ScoreDiff carry the heaviest chrome (period lines, lead-change diamonds, dual legends) |

### Headline findings for the program (fact, not recommendation)
1. `[L2-149 RESOLVED]` **The recharts field engines are gone.** Of the original 4 recharts charts, EvolutionChart + TournamentChart (both `type="monotone"`) are deleted; only OddsChart + ScoreDiff (the two single-game event charts) remain on recharts.
2. `[L2-152 RESOLVED]` **No smoothing anywhere — literal codebase-wide zero `type="monotone"`.** weather/Sparkline's cubic bezier was killed (L2-150), the two recharts game charts were flipped to `linear` (L2-151), and the 14 admin ops charts were flipped (L2-152). Every renderer now draws raw linear/step segments.
3. **The blend-hero treatment exists in exactly one place** (OddsChart Mode A). This is a duel-kernel property (one blend vs faint sources); the field kernel has no single blend line, so it is out of scope for FuturesChart.
4. `[L2-149 RESOLVED]` **Fixed-axis is now the default in the field kernel** (FuturesChart `fixedYAxis` opt-out); `[L2-150 RESOLVED]` **and in the single-market kernel** (shared Sparkline `domain` defaults to [0,100] for probability).
5. `[L2-149 RESOLVED]` **Kernel (b) is 1 engine** (FuturesChart); `[L2-150 RESOLVED]` **kernel (c) is 1 renderer** (`components/Sparkline.tsx`); `[L2-152]` **kernel (d)'s 6 renderers were evaluated and correctly stay separate** (genuinely distinct types/tech). Implementation count 15 → 13 → **11**.

---

## CLOSING SUMMARY — the census program (L2-148 → L2-152)

**The program's job was truth, then bounded consolidation of true copies — never a minimal-count target.** Five queues took the frontend chart layer from 15 drifting implementations to 11 genuinely-distinct ones, plus three shared skeletons for the primitives that WERE identical, and drove every standing ruling to green.

**Implementations, before → after:**
| Stage | Count | What changed |
|-------|-------|--------------|
| L2-148 (census produced) | **15** | Baseline inventory |
| L2-149 (field kernel) | **13** | Deleted EvolutionChart + TournamentChart (recharts); EvolutionView → FuturesChart |
| L2-150 (single-market kernel) | **11** | Deleted weather/Sparkline + event/Sparkline + FuturesHero-inline chart → one shared `components/Sparkline.tsx` (also folded a 5th missed copy: politics-inline; killed the cubic bezier) |
| L2-151 (class B primitives) | **11** | Extracted `lib/chartTimeline.ts` (minute-bucket/seed/gap-fill); flipped OddsChart + ScoreDiff `monotone`→`linear` |
| L2-152 (class D + kernel-d + admin) | **11** | Extracted `lib/chartScale.ts` (px/py skeleton, Calibration + Disagreement); kernel (d) evaluated → stays 6 distinct; 14 admin charts `monotone`→`linear` |

**Shared skeletons created** (dedup of true primitives without deleting whole renderers): `components/Sparkline.tsx` (single-market line, 6 riders), `lib/chartTimeline.ts` (class-B time-axis), `lib/chartScale.ts` (class-D px/py).

**Final violations table — the four standing principles:**
| Principle | Status | Exceptions (explicit) |
|-----------|--------|-----------------------|
| **1. NO smoothing** | ✅ **ALL GREEN** — codebase-wide zero `type="monotone"`; every renderer draws raw linear/step | none |
| **2. Fixed 0–100 Y** | ✅ **GREEN** for all probability charts (field + single-market kernels default-on) | ScoreDiff (symmetric-around-0 spread, not a probability); physical-quantity sparklines (`domain="auto"`) — both out of rubric by design |
| **3. Prominent blend + faint sources** | ✅ honored where applicable (OddsChart Mode A) | Field/multi-source charts have no single blend line — a duel-kernel property, out of scope for field/distribution kernels |
| **4. Kalshi-minimal chrome** | ✅ minimal across the layer | OddsChart / ScoreDiff carry the heaviest (game-state) chrome by necessity — a taste/redesign call, deliberately deferred |

**Duplication classes — final state:** A (field engines) RESOLVED · B (OddsChart↔ScoreDiff) primitives shared, remainder intentionally coupled · C (single-market sparklines) RESOLVED · D (Calibration↔Disagreement px/py) RESOLVED · E (color systems) OPEN, deferred as a redesign concern · F (top-N cap) / G (time-range vocabularies) OPEN, deferred. **No copy-paste dedup class remains open;** E/F/G are cross-cutting design-token/API-shape decisions the redesign program owns, not census cleanups.

**Bottom line:** all four principles are green or explicitly-excepted; every genuine near-copy is consolidated; the remaining 11 implementations are genuinely distinct (proven by the kernel-(d) honest pass, which correctly declined to force-fold). **The census program is complete.** All further chart work flows through the redesign (competitive audit + Alex's MC), not this census.

*This census is descriptive; the L2-149→L2-152 annotations record the consolidations that executed the standing rulings (no smoothing · fixed 0–100 · minimal chrome). Redesign/taste calls are the next program's job.*
