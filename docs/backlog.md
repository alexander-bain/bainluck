# Backlog (SINGLE SOURCE OF TRUTH)

All outstanding work items for Bain Luck. Shipped items live in `docs/completed-features.md`.

## Current Priority: Semantic Matching Excellence

The product's magic depends on **perfectly understanding every event, market, and source** — then grouping and matching them so the user sees one unified view. This is the #1 technical priority and the area with the most measurable room for improvement.

**Matching health dashboard:** `GET /api/admin/prediction-markets/link-rate` + `GET /api/admin/prediction-markets/tier1-compliance`

**Current state (May 7, 2026):** Open link rate: **68.2%**. Kalshi baseball open: **95.5%**. Tier 1 compliance: **100%** for today's games (NHL). MLB Kalshi matching fixed (ticker abbreviation bug — ATH, WSH_MLB added).

**Target: 100%** Tier 1 compliance — every MLB/NBA/NHL/NFL/PGA event with all sources linked.

**Audit tooling:** `scripts/audit_grid_accuracy.py` (51/51, 100%), `scripts/audit_event_matching.py`, Tier 1 compliance endpoint

---

## Tier 0 — Semantic Matching Accuracy (ACTIVE HILL-CLIMB)

### Four-Layer Matching Audit System

All 4 layers at 100% (April 24): Event Existence, Market→Event Linking, Futures Surfacing, Market Completeness. **Next:** Monitor during live games for regression.

**Files:** `backend/scripts/audit_event_matching.py`, `Manus/prompts/event_matching_ground_truth.md`

---

## Tier 0.25 — Cross-Source Market Matching for Non-Sport Categories

**Problem:** Non-sport markets (politics, entertainment, economics, weather) from Kalshi and Polymarket show as separate cards even when they're the same question.

**Current state (May 7):** Politics page now has cross-source matching built in:
- Presidential hero merges candidates across Kalshi + Polymarket by name
- Cross-source spotlight section finds markets on both platforms (normalized question matching), ranked by disagreement
- **Remaining:** Entertainment, economics, weather pages still show duplicates. Canonical market key coverage incomplete.

**Remaining phases:** Apply same approach to entertainment/economics/weather → Audit script for coverage → Backfill NULL canonical keys.

**Target:** <10% unmatched duplicates across all category pages.

**Files:** `tasks/kalshi.py`, `tasks/polymarket.py`, `routes/politics.py` (done), `routes/entertainment.py`, `routes/economics.py`
**Parallel Safety:** Yellow

---

## Tier 0.5 — Feed & Navigation Quality

### 0u. Discover Feed: Curated First Page Mixer + Positive Quality Eval — ACTIVE

**Problem:** Recent ranking fixes removed the worst Discover failures, but the first page can still feel too same-textured: many important cards, not enough editorial variety.

**Current state (May 7-8):**
- ✅ Production first-page quality: `boring-rate@20=0/20`, `ladder/bucket-rate@20=0/20`, `duplicate-family-rate@20=0/20`
- ✅ Deterministic explanations moved `explanation-coverage@20` from **4/20 → 20/20** without OpenAI hook spend
- ✅ Hook enrichment bounded to feed-shaped markets only; do **not** run hooks for all ~56K open markets
- ✅ First-page category mixer added: score-preserving reorder with caps for politics/geopolitics/economics/etc.
- ✅ Positive audit metrics added: archetype coverage, category spread/concentration, archetype distribution
- ✅ Archetype/story caps added: first page now limits single-archetype and hot-story overload, with a required-texture pass for strong tech/culture/weather/sports/weird cards.
- ✅ Strict variety metrics added: top-10 non-politics/geopolitics count, top-10 fun item, top-20 world-event cap, weird-news presence, max category cap.

**Next phases:**
1. Tune strict variety thresholds from real production audits: target `positive-archetypes@20 >= 5/6`, `strict-variety@20 >= 4/5`, `category-spread@20 >= 6`, `max category count <= 5`.
2. Expand editorial archetypes (`breaking_news`, `big_name`, `absurd_but_real`, `sports_drama`) once current archetypes expose remaining blind spots.
3. Improve hook worker observability so queued enrichment reports ran/skipped/error without log streaming.
4. Build an admin/debug viewer that compares current Discover feed against Kalshi/Polymarket/email ground-truth examples.

**Files:** `backend/app/routes/feed.py`, `backend/app/utils/feed_market_quality.py`, `backend/app/utils/feed_reasons.py`, `backend/scripts/audit_feed_quality.py`
**Parallel Safety:** Yellow

### 0n. Navigation Redesign — NEEDS DESIGN BRIEF

**Problem:** Inconsistent nav across platforms. Desktop web: Feed | Search | Weather | Economics | My Stuff. Mobile web: Feed | Search | My Stuff. iOS/Mac: Feed | Leagues | Search | My Stuff.

**Proposed:** Feed | Categories (dropdown + full page) | My Stuff + Search bar. Categories include Sport (with league subcategories), Weather, Economics, Politics, Entertainment.

**Requires:** Design brief before implementation.

**Files:** `components/DesktopNav.tsx`, `components/BottomNav.tsx`, `ios/.../MainTabView.swift`, new `/categories` routing
**Parallel Safety:** Red

### 0s. League Pages — Phases 3 & 4 REMAINING

**Phase 1 (backend):** ✅ SHIPPED (May 6) — `GET /api/leagues/{sport_key}` returns series, awards, props grouped by market type.

**Phase 2 (frontend):** ✅ SHIPPED (May 6) — 4 new components: SeriesCard, AwardCard, PropGroupCard, LeagueMarketSection. Wired into league page below championship grid.

**Phase 3: Cross-sport generalization** — Apply same sectioned layout to NHL (series, Conn Smythe, playoff props), MLB (pennant races, awards, World Series props), NFL (division winners, MVP, draft props). Each sport gets the same sections, populated by the same league-scoped endpoint.

**Phase 4: iOS parity** — Port the new sections to `LeagueView.swift`. Reuse existing card components where possible.

**Files:** `backend/app/routes/leagues.py`, `ios/.../Views/LeagueView.swift`
**Parallel Safety:** Yellow (backend endpoint exists; frontend touches league page)

### 0r. Golf Data Quality Issues

**Problem:** Tour misclassification (Hainan = Asian Tour, not PGA Tour) — seasonal, not reproducible. Other 6 bugs fixed (April 17-19).

**Action:** Monitor during next Asian Tour event. If reproducible, investigate DataGolf tournament metadata parsing.

**Files:** `backend/app/tasks/datagolf.py`, `backend/app/routes/golf.py`
**Parallel Safety:** Green

---

## ~~Rage Shake Triage (May 7-8)~~ — ALL 14 ITEMS RESOLVED

All 16 bug reports triaged, 14 new items identified, all resolved May 8 across two parallel sessions. Details in `docs/completed-features.md`.

**Only remaining from original triage:** RS-5 (iPad sign-in) is FIXED but needs TestFlight build to verify on physical device.

---

## Tier 1 — High Leverage, Do Next

### Production Observability — Latency, Crash Rate, Quality Indicators

We measure per-request latency (X-Response-Time header, slow-request logging >500ms/>1s) but have no aggregation, dashboards, or percentile tracking. Can't answer "what's our p50/p95?" or "which endpoints are slowest?" or "what's our crash rate over time?"

**Need:** A solution that tracks latency percentiles (p50/p95/p99), error/crash rates, endpoint-level breakdown, and trends over time. Options range from free (sample + store in Redis/Postgres, build admin dashboard) to paid (Sentry Performance, Datadog, New Relic). Evaluate tradeoffs and pick one.

**Parallel Safety:** Green

### ~~Manus Sweep May 6~~ — ALL 12/12 FIXED (May 7)

All issues resolved. Details in `docs/completed-features.md`.

### 0e-3. GA4 Console Configuration

Not code — configuration in the GA4 property (analytics.google.com):
1. **Custom definitions**: Register `sport`, `league`, `event_id`, `event_status`, `source_section`, `position_index`, `is_live`, `is_close_game` as custom dimensions
2. **Key events (conversions)**: Mark `sign_up`, `onboarding_complete`, `event_detail_view` as key events
3. **Audiences**: Create "Sports Enthusiasts" (3+ event_detail_view / 7d), "NBA Fans" (sport=basketball_nba 5+), "Power Users" (5+ sessions / 7d)
4. **Funnels** (Explore): Acquisition, Onboarding, Retention
5. **Dashboards**: DAU by platform, top sports by engagement time, feed CTR, onboarding completion rate

**Parallel Safety:** Green (no code changes)

### 0f-4e. Slow Headshot Loading (~60s)

**Problem:** Player prop cards show initials for ~60 seconds before headshots load.

**Investigation needed:** Either the roster data fetch is slow or headshot URLs need preloading.

**Files:** Frontend image loading, backend roster sync timing
**Parallel Safety:** Green

### 0f-13c-native. 2nd Half Margin/Total Maps Not Showing (NATIVE ONLY)

**Problem:** Only 1st half maps show. 2nd half maps don't appear on either platform.

**Investigation needed:**
1. Check if Kalshi poll has run since adding 2H tickers to supplementary fetch
2. Check if 2H spread/total markets exist in `futures_markets` with `event_id` set
3. Check if `_classify_game_market()` returns `half_spread`/`half_total` for them
4. Check if frontend grouping logic picks them up

**Files:** `backend/app/services/kalshi_api.py`, `backend/app/routes/events.py`, `frontend/components/MarketMapSection.tsx`, `ios/.../Components/MarketMapSection`
**Parallel Safety:** Yellow

### 0f-13h. Player Award Headshots Missing on WEB

**Problem:** Native shows player headshots (from roster data) next to award names. Web shows only colored initials circles.

**Fix:** The web "Bigger Picture" section needs to use the `PlayerHeadshot` component (already exists for player props). Check if award data from the `team-progression` endpoint includes player image URLs. If not, backend needs to enrich award outcomes with headshot URLs from roster data.

**Files:** `frontend/app/events/[id]/page.tsx`, `backend/app/routes/events.py`
**Parallel Safety:** Yellow

### BR1-2. Source Attribution Looks Duplicated — NEEDS DESIGN (Rage Shake Bug #1 confirms)

**Problem:** The source list (sportsbooks contributing to the aggregate) appears to show twice — once as a static list and once inside a collapsible dropdown.

**Design question:** How should source attribution work? Options:
- Show just the count ("Aggregated from 12 sportsbooks") with dropdown for details
- Show the dropdown only, collapsed by default
- Inline chips for the top 3 sources + "+9 more" expander

**Files:** `ios/.../Views/EventDetailView.swift` (~line 824), `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow (design brief needed)

### 0f-3. Live Box Score Integration for Player Props

**Problem:** Player prop cards should show actual stats from `box_score_data` during live games (e.g., "Jayson Tatum: 18 points so far vs 24.5 O/U"). The `boxScore` prop is wired but matching logic needs work — player names from Kalshi props don't always match ESPN box score names.

**Files:** `frontend/components/PlayerPropsDashboard.tsx` (matching), `backend/app/routes/events.py` (box score in response)
**Parallel Safety:** Yellow

### 0f-3d Issue 4: Series Markets Not Surfaced

**Problem:** Kalshi has rich series-level markets (Series Winner, Series Exact Score, Series Game Spread, Series Total Games) that should show on every game's event detail page during a playoff series.

**Two sub-problems:**
1. **Linking:** Series markets may not be linked to individual game events via `event_id`. The ticker team extraction had a parsing bug and series tickers (`KXMLBSERIES`, `KXNHLSERIES`, `KXNBASERIES`) need to be in `KALSHI_TICKER_TO_SPORT_KEY`.
2. **Display:** Even if linked, series markets need a dedicated "Series" section on the event detail page — separate from player props and game-level markets.

**Fix:**
- Debug ticker team extraction for series prefixes
- Add series market detection to `is_game_prop()` or create `is_series_prop()`
- Link series markets to ALL games in the series (not just one game)
- Add "Series Context" section to event detail page

**Files:** `backend/app/utils/prediction_market_matching.py`, `backend/app/tasks/prediction_market_matching.py`, `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow

### 0f. Event Detail Below-the-Fold Redesign — TradeWatch Rethink

**Problem:** TradeWatch is one-sided and needs layout fix. Steps 1-5 shipped April 22. Only TradeWatch rethink remains (highest-prob destination only, disclaimer added).

**Files:** `frontend/app/events/[id]/page.tsx`
**Parallel Safety:** Yellow (frontend only)

### 0t-2. 47% of Events Have Zero Period Markers

**Problem:** 21/45 completed events have no game state indicators (period/quarter/inning vertical lines on charts). All are non-ESPN events: soccer, tennis, KBO/NPB baseball.

**Current coverage:** ESPN-matched events have markers via `espn_history.period` + `game_state_backfill.py`. Non-ESPN events have nothing.

**Fix options (needs investigation):**
- Can StatPal provide period/half data for these events?
- Can we match more events to ESPN? (the coverage gap might be addressable)
- For sports like soccer, official APIs (e.g., API-Football) provide halftime timestamps
- Do NOT generate synthetic/guessed markers — only use authoritative sources

**Files:** `backend/app/tasks/game_state_backfill.py`, `backend/app/routes/events.py`
**Parallel Safety:** Green

### ~~0t-3. Chart Domain Mismatch~~ — LIKELY FIXED

`sharedChartDomain` (computed in `events/[id]/page.tsx` lines 382-488) already passes identical `chartStartTime`, `chartEndTime`, and `sharedTicks` to both OddsChart and ScoreDifferentialChart. Game-end source filtering clips post-game prediction market drift. Needs live verification.

### 1b-monitor. Hockey Kalshi Link Rate — MONITOR

**Context:** Health check (April 27) found Hockey Kalshi at 59%, Polymarket at 23.8% — both well below 80% target. The ticker-based fallback (1b) shipped April 27; check if it moved the needle.

**Action:** Re-check `/api/admin/prediction-markets/link-rate` hockey rates. If 1b didn't help, prioritize 1c (sport key validation) next.

**Files:** `backend/app/tasks/prediction_market_matching.py`
**Parallel Safety:** Yellow

### macOS Polish (7 items)

| # | Item | Effort | Files | Safety |
|---|------|--------|-------|--------|
| MAC-1 | Live-updating title bar (show live score) | 1-2h | `Bain_LuckApp.swift` | Green |
| MAC-3 | Keyboard navigation (tab/arrow between cards) | 2-3h | Various SwiftUI views | Green |
| MAC-5 | Menu bar extra (live scores) | 3-4h | `MenuBarController.swift` (new) | Green |
| MAC-6 | Push notifications | 2-3h | Various | Green |
| MAC-8 | Right-click context menus (Share, Open, Copy) | 1h | Various SwiftUI views | Green |
| MAC-9 | Share button + universal links | 2-3h | Various | Green |
| MAC-12 | macOS widgets (Today view) | 3-4h | New widget extension | Green |

---

## Tier 2 — Important But Bigger Scope

### 2. God Functions — Deeper Extraction

**First pass shipped:** 5 functions, 82 tests, 4 utility modules (April 21).

**Remaining targets:** `get_golf` (686L), `_match_prediction_markets` (649L), `operations_dashboard` (595L), `_build_golf_tour_grid` (549L), `_get_march_madness_data` (406L).

**Large route files:** `admin.py` (8,684L), `events.py` (5,042L), `playoffs.py` (3,539L), `futures.py` (2,866L), `golf.py` (2,294L).

**Parallel Safety:** Yellow

### 3. Golf Data Quality

1 remaining bug: Tour misclassification (Hainan = Asian Tour, not PGA Tour) — seasonal, not reproducible. All other 6 bugs fixed (April 17-19).

### 4. Site Navigation Hierarchy (B1)

`/basketball/nba` hierarchy instead of flat `/playoffs/nba`. Blocked on golf strategy decisions.

**Parallel Safety:** Red (restructures frontend routing)

### 5. Playoff Series Matchup Markets

Polymarket has rich playoff series markets ("Celtics vs Cavaliers"). Need: stage classification in `tournament_stages.py`, grid column, event detail display, trend charts. Timely with NBA/NHL playoffs in progress.

**Files:** `backend/app/config/league_configs.py`, `backend/app/utils/tournament_stages.py`, `backend/app/routes/playoffs.py`, `backend/app/routes/events.py`
**Parallel Safety:** Yellow

### 6. API Route Contract Tests — Expand Coverage (PARTIALLY DONE May 8)

~~110~~ 158 contract tests shipped. Seeded-data tests added (May 8):
- ✅ Feed: scoring/ordering, event data shape, futures data shape, sport filter, pagination (16 tests)
- ✅ Events: detail response shape, current_odds structure, game-markets sections, related-futures, history (17 tests)
- Playoffs: column data, probability sums, monotonicity
- Related futures: market grouping, dedup, gender filtering

**Files:** `tests/integration/test_route_feed_scoring.py` (new), `tests/integration/test_route_events_seeded.py` (new)
**Parallel Safety:** Green

---

## Tier 3 — Valuable But Can Wait

### Operational Health

| # | Item | What | Files | Safety |
|---|------|------|-------|--------|
| 9 | **Structured Logging** | JSON logging for Heroku (python-json-logger or structlog) | `app/main.py`, `app/tasks/__init__.py` | Yellow |
| 11 | **Hardcoded Conference Maps → Data-Driven** | Pull from `Team.standings_data` instead of static dicts | `routes/playoffs.py` | Yellow |

### Product Features

| # | Item | What | Depends on | Safety |
|---|------|------|-----------|--------|
| 12 | **Evolution Chart: Combined Probability** | Multi-source merged trend line on charts | Nothing | Yellow |
| 13 | **Line Movement Explainer v2** | Causal analysis, key moment identification | Nothing | Green |
| 14 | **Freshness-Weighted Blending** | Time-decay for stale prediction market prices | More eval data | Yellow |
| 15 | **DS/Analytics Infrastructure** | Analytical columns, `v_completed_events` view, Brier scores | Migration slot | Red |
| 16 | **Golf Tournament Related Futures** | "Bigger Picture" section on tournament detail | Nothing | Yellow |
| 17 | **Golf Evolution Chart Redesign** | Tournament-aware time ranges, round markers | Nothing | Green |

### ~~18. Non-Sports Category Pages~~ — ALL SHIPPED (May 7)

Economics, Politics, Entertainment all live on web + iOS. Details in `completed-features.md`.

---

## Search — Phase 4c & Phase 5b & Phase 6 (REMAINING)

**Phases 1-3:** ✅ SHIPPED (team pages, typeahead enrichment, recent searches, mobile search, keyboard shortcuts)
**Phase 4a-b:** ✅ SHIPPED (`pg_trgm` extension, GIN trigram indexes, did-you-mean suggestions)
**Phase 4d:** ✅ SHIPPED (did-you-mean suggestions)
**Phase 5a, 5c-e:** ✅ SHIPPED (recent searches, results page redesign, mobile search, keyboard shortcut)

**REMAINING:**

### P4c. Weighted `ts_vector` Full-Text Search

Team names weight A, market names weight B, outcome names weight C. Use PostgreSQL full-text search with weighted ranking.

**Files:** `backend/app/routes/events.py`, new migration for ts_vector columns
**Parallel Safety:** Yellow

### P5b. Trending/Popular Searches

Track queries server-side, surface top 5 as zero-state chips when search bar is focused.

**Files:** `backend/app/routes/events.py`, new migration for `search_queries` table, `frontend/components/SearchBar.tsx`
**Parallel Safety:** Green

### Phase 6: Semantic Search (2-3 weeks, aspirational)

- **P6a. Embedding-based search** — OpenAI embeddings for queries like "Will the Celtics repeat?" matching championship markets
- **P6b. pgvector extension** — Store embeddings in Postgres, nearest-neighbor search
- **P6c. Query intent classification** — Is the user looking for a team, game, market category, or asking a question?
- **P6d. Personalized ranking** — Boost results from leagues/teams the user has viewed or predicted on

**Files:** Various
**Parallel Safety:** Yellow

---

## iOS App — Web Parity & Polish

### iOS App — Web Parity & Polish

| # | Item | Description | Files | Safety |
|---|------|-------------|-------|--------|
| iOS-4 | Dead/stale views cleanup | TournamentChartView/CardView — audit for staleness | `ios/.../Views/` | Green |
| iOS-6 | Feed `limit=200` override | Fixed April 22, needs build verification | `FeedView.swift` | Green |
| iOS-GD12 | Trevor Story missing headshot | Verify if URL missing in API or not loading. Add generic silhouette fallback | `RelatedFuturesView.swift`, backend roster | Green |

---

## Discover Feed Enhancement

### Discover Feed Enhancement

| # | Item | Description | Files | Safety |
|---|------|-------------|-------|--------|
| DN-9 | Swipe to dismiss (iOS) | Web has swipe left/right with like/dismiss overlays. **Rage Shake Bug #7 confirms.** | `ios/.../DiscoverView.swift` | Green |
| DN-10 | Onboarding flow | "Build Your Feed" modal with category selection on first launch | `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | Green |
| DN-11 | Grouped market cards | Markets with name prefix collapse into single expandable card | `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | Green |
| D-4a | Click/view tracking | `user_interactions` table logging detail views. Backend middleware | New migration, `main.py`, `utils/personalization.py` | Yellow |
| D-10a | Dismiss persistence | Persist dismissed IDs server-side (extend `user_seen_markets`) | `routes/predictions.py`, `app/discover/page.tsx`, `ios/.../DiscoverView.swift` | Yellow |
| D-10b | Like/dismiss → ranking | New `user_market_feedback` table. `_score_futures()` personalization multiplier | New migration, `routes/feed.py`, `utils/personalization.py` | Yellow |
| D-6 | Push notifications for moves | Alert when pinned markets/categories move >10% in 1h. Firebase Cloud Messaging | New migration, `tasks/notifications.py`, FCM setup | Green |
| D-7 | Live game companion mode | Full-screen second-screen mode. Giant win prob, play-by-play, sparkline, alerts | `app/events/[id]/companion/page.tsx` (new), `ios/.../CompanionModeView.swift` (new) | Green |
| D-8 | Daily digest email | Morning email: movers, top markets, resolved predictions. Celery + SendGrid | `tasks/daily_digest.py` (new), email templates | Green |
| D-9 | Friend challenges | Shareable URL, no account required for friend, `prediction_challenges` table | New migration, `routes/challenges.py` (new), `app/challenge/[id]/page.tsx` (new) | Green |

---

## Event Detail Parity Items (from April 29 Sweep #3)

Items 2, 4, 5, 6, 8 remain:

- **Web x-axis alignment**: Win Prob and Score Diff charts need identical tick positions. Generate explicit ticks from shared domain with dynamic intervals (hourly for long games, 30-min for short).
- **1st half margin mismatch**: Web shows BOS +6.5, native shows BOS +1.0. Use spread threshold directly from period market with probability closest to 50%.
- **Half map FINAL values**: Derive half scores from ESPN history halftime data point.
- **2nd half maps missing**: Check if API returns 2H period markets; render if present.
- **Double/triple doubles → player props**: Sport-generic: scan `other` markets for player-named outcomes, inject into player prop cards.

**Files:** `frontend/components/OddsChart.tsx`, `frontend/components/ScoreDifferentialChart.tsx`, `frontend/components/MarketMapSection.tsx`, `ios/.../Components/MarketMapSection`
**Parallel Safety:** Yellow

---

## Tier 4 — Someday / Maybe

### 20. Market Interestingness Scoring

**Goal:** Algorithmic scorer calibrated against Kalshi/Polymarket marketing emails as ground truth.

**Phases:** (1) Ground truth collection (Gmail → Apps Script → Sheet, 50-100 labeled markets), (2) Scoring formula (8 weighted features: decisiveness, multi-source, recency, movement, resolution proximity, category novelty, volume, LLM quality), (3) Calibration (hill-climb weights, Precision@20/Recall@50/NDCG), (4) Integration (explore page, feed ranking, trending, push, featured hero).

**Files:** `utils/market_interestingness.py` (new), `scripts/calibrate_interestingness.py` (new), Google Sheet
**Parallel Safety:** Green

### 21. Rage Shake — In-App Bug Reporting

**Goal:** Shake phone (iOS) or click button (web) to instantly report a bug with screenshot, page, device info, app state.

**Platforms:** iOS (UIKit `motionEnded`), macOS (`Cmd+Shift+F`), Web (floating button or `Ctrl+Shift+F`).

**Destination:** GitHub Issues API (`POST /repos/alexander-bain/bainluck/issues`), auto-labeled `bug/rageshake`.

**Files:** `ios/.../Utils/RageShake.swift` (new), `components/FeedbackButton.tsx` (new)
**Effort:** iOS 2-3h, Web 2-3h
**Parallel Safety:** Green

### 22. Interestingness-Powered Discovery Feed (LLM Blurbs + Images)

**Goal:** Social-media-style feed where each card has image + LLM-written blurb + probability bar.

**Phases:** (1) Score everything, store `interestingness_score`, re-score hourly. (2) GPT-4o-mini blurbs for top 100, store `llm_blurb`, regenerate weekly. (3) Images: stock/icon mapping, entity lookups, optionally AI-generated for top 20. (4) Feed integration.

**Files:** `utils/market_interestingness.py`, `tasks/blurb_generation.py`, new migration, `components/DiscoveryCard.tsx` (new)
**Effort:** P1: 2h, P2: 3h, P3: 2h, P4: 4h
**Parallel Safety:** Green

### 23. Prediction Market Game / Social Picks

**Formats:** (1) Feed-as-game (Higher/Lower buttons, leaderboard), (2) Daily picks (5 markets, Wordle-style), (3) Head-to-head (challenge friend), (4) Ambient screensaver (Apple TV/Mac/web), (5) Portfolio mode (track "returns").

**Depends on:** Item 22, auth (shipped), preferences (shipped).
**Parallel Safety:** Green

---

## Platform Parity Checklist

**iOS/Mac gaps (web has, native doesn't):**

| Priority | Feature | Web Component | Effort |
|----------|---------|--------------|--------|
| Medium | Game Segments (quarter/half breakdown) | `GameSegments.tsx` | Small |
| Medium | Total Points Spectrum (spread+total viz) | `TotalPointsSpectrum.tsx` | Medium |
| Medium | Series Probability (playoff series outcomes) | `SeriesProbability.tsx` | Small |
| Low | Evolution Chart (championship race over time) | `EvolutionChart.tsx` | Medium |
| Low | Line Movement Explainer | `LineMovementExplainer.tsx` | Small |
| Low | Weather page | 16 components | Large |
| Low | Economics page | `/economics` | Medium |
| Low | Explore / faceted browser | `/explore` | Medium |

**Web gap (iOS has, web doesn't):** EI Rankings standalone page (iOS has `EIRankingsView.swift` with sport filters)

---

## Housekeeping

### Other Housekeeping
- **Monthly**: Update `QUOTA_GUARD_EXPIRY` in `redis_state.py`
- Clean up ~90 remote git branches

### Mystery Shopper Findings (April 22, 2026 — Manus AI Audit)

**Critical (user-facing, broken):**

| # | Finding | Status | Notes |
|---|---------|--------|-------|
| M1 | Golf tournaments: 100%/0% probability | **Fixed** May 7 | DataGolf UniqueViolation fix |
| M2 | Event detail doesn't load on mobile | **Needs verification** | May have been transient |
| M3 | Future golf majors marked as "LIVE" | **Fixed** | DataGolf schedule fix |
| M4 | Player props showing 97-98% uninteresting thresholds | Open | Filter needed for props where interesting side <5% |

**Warning (data quality):**

| # | Finding | Status | Notes |
|---|---------|--------|-------|
| M5 | Tiger Woods -57.5% daily change | **Fixed** | Stale trend data filtering |
| M6 | Weather: LA showing 33°F | **Fixed** | Weather staleness + C/F fix |
| M7 | Economics: recession showing "30" without % | **Likely fixed** | ProbNum component has `suffix="%"` default |
| M8 | Economics: CPI distribution sums >100% | Open | Independent binary markets as distribution |
| M9 | Weather: stale featured market | **Fixed** May 7 | 7-day staleness + 6h grace |
| M10 | "Projected final: 3 – -1" notation | **Likely fixed** | Guard: `> 0` on both scores filters negatives |
| M11 | Half/quarter/period markets not displayed | **Fixed** May 8 | RS-11: inning pattern classification |
| M12 | Halftime/spread markets missing | **Fixed** May 8 | RS-11 + half patterns in _classify_game_market |
