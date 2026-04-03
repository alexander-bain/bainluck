# Bain Luck: Code Audit & Strategic Recommendations
## March 6, 2026

---

## 1. Code Audit: Where Things Are Awkwardly Patched

### Critical Issues (Fix Now)

**Silent error swallowing.** Multiple task modules still use bare `print()` instead of `logger.error()` — especially in `espn_sync.py` and `odds_polling.py`. When these tasks fail, errors don't flow to Sentry, don't have timestamps, and can be lost entirely if the Heroku worker crashes. Combined with broad `except Exception` blocks that catch everything (including `SystemExit` and memory errors), this means production failures are invisible. **Fix: grep for `print(` in `backend/app/tasks/`, replace with `logger.error(..., exc_info=True)`, and narrow exception types.**

**admin.py is 5,493 lines.** Every admin feature — EI recalculation, Kalshi polling, Polymarket backfill, ESPN cleanup, prediction market linking, event merging, duplicate detection, audit endpoints — lives in a single file. This is the #1 DX pain point. **Fix: split into `admin/ei.py`, `admin/futures.py`, `admin/prediction_markets.py`, `admin/events.py`, `admin/tasks.py`, `admin/audit.py`.** Each becomes a focused 500-700 line module.

**Task beat schedule uses magic strings.** The Celery beat schedule has 30+ entries like `"task": "app.tasks.discover_events"`. If a task gets renamed, the schedule silently stops running it — no error, no warning, just missing data for hours/days until someone notices. There's no compile-time verification.

### Architectural Debt (Fix This Quarter)

**Event model has ~159 columns.** EI metadata, LLM metadata, ESPN enrichment, StatPal enrichment, opening odds, tournament fields, box score data, taxonomy tags — all on one model. Every query pulls all 159 columns even when you need 3. This should be decomposed: `Event` (20 core columns) + `EventMetadata` (EI, LLM, ESPN, StatPal as separate tables or JSONB sections loaded on demand).

**Copy-paste polling loops.** The "fetch → parse → upsert → snapshot" pattern is repeated nearly identically in `odds_polling.py`, `futures.py`, `kalshi.py`, and `polymarket.py`. A bug fix in one isn't propagated. Rate limiting, error handling, dedup logic — all slightly different across 4 files.

**Win probability snapshots created via multiple paths.** ESPN sync, MLB sync, prediction market matching, and odds polling all create `win_prob_snapshots` via slightly different code paths. If dedup logic changes, you need to update 4 places.

**`OddsAggregated` table exists but nothing writes to it.** Dead schema that's been "Phase 2 someday" since January. Either implement archival or drop the table.

### Frontend Architecture

**OddsChart.tsx (1,472 lines) and RelatedFutures.tsx (1,513 lines)** are the two biggest components. OddsChart has 9+ `useMemo` blocks in a cascade where each depends on the previous — a change to any upstream memo recomputes everything downstream. RelatedFutures has 7 regex pattern arrays, 15+ helper functions, and 5 sub-components all in one file.

**CSS system has three sources of truth.** `globals.css` defines `--surface-card`. `design-tokens.css` defines `--color-status-live`. `tailwind.config.ts` extends both. Legacy aliases (`--color-snow`, `--color-white`) in globals.css are unused dead code. When someone changes a brand color, they don't know which of three files to edit.

**Dynamic imports without error boundaries.** The event detail page has 7 `dynamic()` imports with `ssr: false` and no fallback — if any import fails, the entire page crashes with no error message.

**Source config hardcoded in frontend.** `FALLBACK_SOURCE_CONFIG` in OddsChart.tsx duplicates the backend's `win_prob_sources.py`. When a new source is added on the backend, the frontend silently fails to render it.

---

## 2. Design Strategy: Turning Weakness Into Strength

The honest diagnosis: you've been trying to improve design through code refactoring (CSS variables, design tokens, shadcn Card wrappers). That's plumbing, not design. No user will ever notice that `<div>` became `<Card>`.

### What Actually Works

**Use v0.dev (Vercel's AI UI generator).** You're already on Next.js + Tailwind + shadcn/ui — v0.dev generates production-ready React components in exactly this stack. The workflow:

1. Go to v0.dev, describe a component: "Dark mode sports event card showing two teams with logos, probability bar between them, live score, and excitement index badge"
2. v0 generates 3-4 variations with working code
3. Pick the best one, iterate in chat
4. Copy the code into your codebase

This is the single highest-leverage thing you can do. Instead of spending 8 hours writing CSS, you spend 20 minutes iterating with an AI that's seen thousands of dashboard designs. Do this for: EventCard, FuturesCard, the feed layout, the event detail page header, the OddsChart container.

**Study the right references.** Your product is closest to these (look at them on your phone too):

- **The Athletic** — dark mode, clean typography, team colors done right
- **FiveThirtyEight** (archived) — probability visualization with explanatory context
- **Smarkets** — prediction market odds display, how they show cross-source comparison
- **Action Network** — sports odds cards, live game state display
- **Linear** — not sports, but the gold standard for dark mode SaaS with data density

The common thread: generous whitespace, restrained color palette (dark background, team colors as the ONLY accent), typography doing the heavy lifting (not borders and boxes).

**Install the `interface-design` skill.** You have it available but haven't used it. For any major component redesign, invoke it — it has specific guidance for dashboard/data visualization interfaces.

### Concrete Design Moves (High Impact, Low Effort)

**1. Kill the borders.** Your cards have `border-surface-border` which creates a grid of boxes. Replace with: dark card backgrounds that are slightly lighter than the page, no visible border, subtle shadow on hover. This one change makes the entire site feel more premium.

**2. Make probability numbers huge.** Your north star is "60% vs 40% instead of -150 / +130." But the probability numbers on your cards are the same size as everything else. Make them 2-3x larger. Monospace font. Let them dominate the card.

**3. Team colors should bleed, not badge.** Right now team colors appear as tiny dots or borders. Instead: use team primary color as a subtle gradient background tint on each team's half of the card. The card itself becomes team-colored without any explicit "color badge."

**4. Typography hierarchy.** You have 11 font size tokens defined in Tailwind but components use inline `text-2xl` instead. Pick 4 sizes for cards: probability (huge), team name (medium-bold), context/reason (small), metadata (tiny). Apply them consistently across every card.

**5. Use v0.dev to redesign EventCard.** This is the component every user sees 20+ times per visit. A single v0.dev session redesigning this card will have more visual impact than all 8 prompts from the previous session combined.

### Services Worth Pulling In

| Service | What It Does | Why |
|---------|-------------|-----|
| **v0.dev** | AI component generation | Generates production React/Tailwind components from descriptions |
| **Figma** (free tier) | Design mockups | Mock up 3-4 key screens before coding them; use as reference |
| **Vercel Analytics** | Real User Monitoring | See which pages are slow, what devices users have |
| **unDraw** or **Storyset** | Illustrations | Empty states, onboarding, error pages — avoid the "developer built this" feel |

### What NOT To Do

- Don't install more CSS frameworks or design systems. shadcn/ui + Tailwind is sufficient.
- Don't write "design token migration" PRs. Users don't see tokens.
- Don't add animations first. Get the static design right, then animate.

---

## 3. Win Probability Chart: Path to Perfection

### Current State

The OddsChart is **70% robust for standard two-team games, 40% for multi-participant events, and 20% for elimination tournaments.**

The chart works well for: NFL, NBA, MLB, NHL, NCAAB, NCAAF, soccer — standard matchups with betting odds + optional ESPN/stat model lines.

### Where It Breaks

**Empty/sparse data → silent failure.** TournamentChart returns `null` when data is sparse. User sees nothing — no loading state, no "no data" message. OddsChart has a better empty state but still doesn't distinguish "no data yet" from "data fetch failed."

**Elimination tournaments are unsupported.** Tennis Grand Slams (128 → 64 → 32 → ... → 1), March Madness (68 teams), MLB Playoffs — when players/teams are eliminated, their probability drops to 0 and stays there. The chart renders flat 0% lines for eliminated participants, cluttering the visualization. There are no round boundaries, no "eliminated" markers, no bracket context.

**iOS is missing prediction market lines.** SwiftUI Charts doesn't support dashed line styles natively. Kalshi and Polymarket trend lines simply don't appear on iOS. Users on iPhones can't see the cross-source comparison that's a key differentiator.

**Game start delays break the smart-start heuristic.** If a game is delayed >2 hours (rain delay, broadcast issue), the chart clips meaningful pre-game market reaction.

**Stale source data has no indicator.** During live games, if ESPN sync falls behind by 5+ minutes, the ESPN trend line shows stale data but looks current. No dimming, no "delayed" badge.

### Short-Term Fixes (This Month)

1. **Add explicit error/empty states everywhere.** "No odds data yet" for scheduled games, "Market closed" for resolved tournaments, "Chart unavailable" for API failures. Never return null silently.

2. **Add source freshness indicators.** Backend includes `last_updated_at` per source in the history response. Frontend dims lines >5 minutes stale during live games and labels them "Delayed."

3. **Fix iOS prediction market display.** Either use a custom SwiftUI view with manual path drawing for dashed lines, or display prediction markets as a separate data strip below the main chart. This is a real feature gap.

4. **Validate Field probability in TournamentChart.** The client-side Field re-aggregation can double-count the server-provided Field. Add assertion: `sum(outcomes) ≤ 1.0`.

### Medium-Term (Next 2 Months)

5. **Implement round boundaries for elimination events.** Backend: detect when cohorts of outcomes hit 0% simultaneously (elimination round). Return `round_boundaries: [{round_name, timestamp}]` in the probability-timeline response. Frontend: draw vertical lines between rounds, auto-hide eliminated outcomes (or gray them out), add a "Show eliminated" toggle.

6. **Break OddsChart.tsx into composable pieces.** Extract data transformations into hooks: `useChartDataPoints()`, `useWinProbSources()`, `useYAxisDomain()`. Extract `<ChartTooltip>` as a sub-component. This makes the chart testable and extensible.

7. **Backend provides period markers as API data.** Instead of the frontend inferring period boundaries from ESPN history points, the backend computes and returns `period_markers: [{timestamp, label}]`. Both web and iOS consume the same data — no more duplicated inference logic.

### Long-Term (Make It Perfect)

8. **Tournament bracket view.** For elimination events, add a bracket/tree visualization alongside or instead of the line chart. Show probability flowing through bracket rounds. Eliminated teams grayed out with their exit probability. This is the "holy grail" visualization for March Madness, Grand Slams, and playoff brackets.

9. **Annotated chart moments.** Overlay ESPN play-by-play events on the odds chart: "Interception at 2:34 Q4" appears at the inflection point. Scoring plays with wall-clock timestamp alignment. Users see WHY the line moved, not just that it moved.

10. **Chart replay mode.** After a game ends, a "replay" scrubber lets users watch the odds chart evolve over time. High-EI games become shareable highlights. This is a unique feature no competitor has.

---

## 4. Futures Grouping: From Good Plumbing to Great UX

### What Works Today

The system has solid foundations: canonical market keys link the same market across Polymarket/Kalshi/Sportsbooks. Threshold variant detection groups numeric progressions (Bitcoin $80K/$90K/$100K). Golf progression tables show tournament stages beautifully.

### What's Missing

**Playoff round progressions don't exist.** NBA Playoffs have 1st Round → Conference Semis → Conference Finals → Championship. This is high-value data that the system CAN group but doesn't have stage definitions for. The golf progression infrastructure (`tournament_stages.py`) could be extended to basketball, football, hockey, and college tournaments with sport-specific stage hierarchies.

**Cross-market stat prop grouping doesn't exist.** "LeBron Points: Over 25.5", "Over 26.5", "Over 27.5" exist as separate markets. Threshold detection only works within a single market's outcomes, not across markets. Users can't see all available thresholds for a player stat in one view.

**Grouped markets are buried.** There's no "Featured Grouped Markets" section on the homepage. No "Biggest Cross-Source Spreads" card. No "browse by group type" interface. Users have to navigate to a specific market to discover grouping exists.

**No divergence explanation.** When Polymarket shows Celtics at 22% and sportsbooks show 18%, there's no context for why they differ or which source tends to be more accurate.

### Priority Fixes

**1. Define playoff stage hierarchies** (~6h of work). Add stage definitions for NBA, NFL, NHL, NCAAB, NCAAF to `tournament_stages.py`. Pattern-match market names ("First Round", "Conference Finals", "Championship"). The progression endpoint then automatically works — same infrastructure as golf.

**2. Surface grouped markets in the feed** (~4h). Add a "Cross-Source Comparison" section to the homepage showing markets where Polymarket and sportsbooks diverge >5%. This surfaces existing data that's currently invisible.

**3. Cross-market threshold grouping** (~8h). Extend threshold detection to work across markets sharing a stem (e.g., all "LeBron Points" markets across sportsbooks, grouped by threshold value). New endpoint: `GET /api/stat-prop-group?player=LeBron&stat=Points`.

**4. Add divergence context** (~2h). When CombinedMarketCard shows a >5% cross-source spread, add a one-line explanation: "Polymarket traders are more bullish than sportsbooks" or "This spread has narrowed from 12% to 5% over the past week."

---

## Recommended Execution Order

| Priority | Task | Impact | Effort |
|----------|------|--------|--------|
| 1 | Replace `print()` with `logger.error()` in tasks | Stops silent failures | 2h |
| 2 | Redesign EventCard using v0.dev | Visible to every user | 3h |
| 3 | Add chart empty states + error boundaries | Fixes "broken" perception | 2h |
| 4 | Split admin.py into focused routers | Unblocks dev velocity | 4h |
| 5 | Fix iOS prediction market lines | Feature parity | 4h |
| 6 | Define playoff stage hierarchies | High-value grouping | 6h |
| 7 | Surface grouped markets in homepage feed | Discovery | 4h |
| 8 | Break OddsChart into composable hooks | Maintainability | 6h |
| 9 | Implement elimination round boundaries | Chart quality | 8h |
| 10 | Cross-market stat prop grouping | Differentiated feature | 8h |
