# Completed Features (Shipped)

## May 17, 2026 — Native iOS Code Quality + Navigation Cleanup

### Rage Shake / Native Discover Fixes
- ✅ **Native Discover swipe/replenishment fixes** — positive swipes now complete, dismissed cards are replaced instead of emptying the feed, refresh resets local visible/dismissed state, and guess cards skip nil-probability markets.
- ✅ **Native Discover feed quality pass** — sports-heavy first pages were downranked with stronger category diversity, regional/context signals, and Red Sox/Boston-style affinity hooks. Backend feed now emits stable grouping metadata for native dedupe.
- ✅ **Sports/My Stuff/native page decode fixes** — Sports feed now backfills beyond live cards; My Stuff hides noisy global category futures; league/native pages use corrected probability field types and response decoding.
- ✅ **Futures tab removed from prod navigation** — The unfinished native Futures browser entry point is hidden from production sidebar/tab navigation and tracked as iOS-7 for rebuild. The 🍀 Bain Luck sidebar title and Calibration entry point remain visible.
- ✅ **Native onboarding/sidebar polish** — fixed truncated percentage text, line-broken sidebar labels, and the oversized placeholder icon in the sidebar title.
- ✅ **App Store launch navigation state documented** — release notes and review notes now describe the launch-safe native state: Futures browser hidden pending iOS-7, Calibration visible, 🍀 sidebar branding preserved, and production push entitlement complete.

### Native Maintainability Sweep
- ✅ **All native ViewModels moved into `ViewModels/`** — extracted embedded `ObservableObject` classes from view files, including Discover, Feed, My Stuff, Event Detail, category pages, Search, Calibration, Daily Challenge, league/category grids, and futures detail/list.
- ✅ **Daily Challenge component extracted** — `NativeDailyChallengeCard` and `NativeChallengeSheet` moved out of `DiscoverView.swift` into `Components/DailyChallengeCard.swift`.
- ✅ **Resolution card component extracted** — `NativeResolutionCard` moved out of `DiscoverView.swift` into `Components/ResolutionCard.swift`.
- ✅ **Hidden Futures browser rebuild groundwork** — the native Futures browser remains hidden, but now has a grouped category rail, polished market rows, reusable browse components, and loading/error/empty states for iOS-7 review.
- ✅ **View-model state access tightened** — read-only view-model-owned `@Published` state is now `private(set)`; fields that views bind to or assign remain mutable.
- ✅ **Shared native utilities** — extracted clipboard, share URL, formatting, sport display, flag URL, flow layout, and color helpers. Share links now avoid force-unwrapped URLs.
- ✅ **Native model/service docs** — added concise doc comments across native model types and key API/auth/navigation service methods.
- ✅ **Native build verified** — full `xcodebuild -project 'ios/Bain Luck/Bain Luck.xcodeproj' -scheme 'Bain Luck' -destination 'generic/platform=iOS Simulator' -configuration Debug build` passed for the pushed batches.

### Backend Cleanup
- ✅ **Playoff conference maps made data-driven** — removed large static conference fallback maps from `routes/playoffs.py`; playoff grouping now uses `Team.standings_data` with tolerant label parsing and tests for string/object standings payloads.

**Files:** `ios/Bain Luck/Bain Luck/ViewModels/`, `ios/Bain Luck/Bain Luck/Utilities/`, `ios/Bain Luck/Bain Luck/Components/`, `ios/Bain Luck/Bain Luck/Views/DiscoverView.swift`, `ios/Bain Luck/Bain Luck/Views/MainTabView.swift`, `ios/Bain Luck/Bain Luck/Models/`, `docs/backlog.md`, `docs/ios-code-quality-plan.md`, `docs/app-store-launch-plan.md`

## May 17, 2026 — Rage Shake Triage #7 + Infrastructure + Polish

### Shareable Prediction Scorecards
- ✅ **OG image generation** — Next.js `ImageResponse` generates dynamic scorecard images with accuracy, streak, and prediction count. Unique daily URLs.
- ✅ **Share button on `/discover/stats`** — Users can share their prediction performance.
- ✅ **Scorecard page at `/discover/scorecard`** — Standalone shareable page with OG metadata for social previews.

### Production Latency Tracking
- ✅ **Latency middleware** — Per-request timing with p50/p95/p99 percentile tracking, endpoint-level breakdown, slow-request logging.
- ✅ **Admin stats endpoint** — Aggregated latency metrics available at admin endpoint for monitoring.

### Bug Report Categories + Lifecycle Fields
- ✅ **Category field on BugReport model** — Admin dropdown for categorizing reports. Migration: `add_bugreport_cat`.
- ✅ **Lifecycle fields** — `resolution_summary` and `backlog_ref` fields for tracking bug resolution workflow.
- ✅ **Bug report auth fix** — Bug report submissions never had `user_id` because `request.state.user_id` was never set. Fixed by using `get_optional_user` dependency instead.

### About Page v2
- ✅ **Scroll-triggered animations** — Sections animate in on scroll with staggered entry.
- ✅ **Dynamic API data** — Live market/event/source counts pulled from API instead of hardcoded.
- ✅ **Refined typography and hover effects** — Polished visual presentation.

### ErrorState Component + Standardized Error Handling
- ✅ **Unified `ErrorState` component** — Standardized error display across all pages replacing 3 inconsistent patterns.
- ✅ **Applied across league, category, and hub pages** — Consistent error UX site-wide.

### Bug-Fixed Email Notifications
- ✅ **Trigger on "actioned" status** — Gmail API sends "your bug was fixed" email when admin marks bug report as actioned.
- ✅ **Opt-in via rage shake form** — Users check a box to receive fix notifications.

### Push Notification Foundation
- ✅ **DeviceToken model** — Database model for storing device push tokens.
- ✅ **Registration endpoint** — Backend endpoint for iOS/macOS to register device tokens.
- ✅ **Test send endpoint** — Admin endpoint for testing push delivery.

### League Pages Phase 3
- ✅ **MoversRibbon component** — Shows biggest probability movers across league markets.
- ✅ **Sport-aware layout** — NHL, MLB, NFL now use the same sectioned layout as NBA. Cross-sport generalization complete.

### macOS Push Notifications
- ✅ **AppDelegate for push** — macOS `AppDelegate` handles push notification registration.
- ✅ **UNUserNotificationCenterDelegate** — Notification presentation and handling on macOS.

### Rage Shake Triage #7 Bug Fixes (May 17)
- ✅ **BR49: Yes/No display** — Non-binary multi-outcome markets no longer show "Yes" as the hero outcome.
- ✅ **BR50: Sparse chart** — Market detail charts handle sparse snapshot data gracefully.
- ✅ **BR51: Search + binary chart** — Multi-word search matching improved; binary markets show trend lines.
- ✅ **BR52/53: Team associations** — Sport-scoped matching prevents cross-sport name collisions (e.g., WNBA "Boston" no longer matches NHL Bruins).
- ✅ **BR54/56: Feed quality** — Minor sport suppression, Netflix/Spotify #1 surfacing, stronger dismiss signal penalties.
- ✅ **BR57/58: Equal odds** — Feed normalization renormalizes to displayed outcomes only for multi-outcome markets.

### Other Fixes (May 17)
- ✅ **MS-8: MLB chart gaps** — Chart gap handling improved for MLB games.
- ✅ **MS-11: Stale live probability** — Completed markets no longer show stale pre-settlement probabilities.
- ✅ **WATCH-1: Apple Watch reliability** — Reduced feed limit, aggressive timeout, improved decode stability.
- ✅ **Golf DQ: import crash + tour misclassification** — Fixed DataGolf import crash and tour classification errors.
- ✅ **Site navigation hierarchy** — Canonical `/sport/[sport]/[league]` URL pattern shipped.
- ✅ **God function extraction: `operations_dashboard`** — Extracted from monolithic admin route.
- ✅ **TradeWatch redesign** — Improved layout and data presentation on event detail pages.
- ✅ **Onboarding category persistence** — Category selections now persist to server via `useCategoryInterests` hook.

**Files:** `backend/app/main.py`, `backend/app/routes/admin.py`, `backend/app/routes/feed.py`, `backend/app/routes/feedback.py`, `backend/app/models/models.py`, `frontend/app/about/page.tsx`, `frontend/app/discover/stats/page.tsx`, `frontend/app/discover/scorecard/page.tsx`, `frontend/components/ErrorState.tsx`, `ios/Bain Luck/Bain Luck/Bain_LuckApp.swift`

## May 15, 2026 — Rage Shake Triage #5 + Backlog Blitz (22 items, 4 waves)

### Rage Shake Triage #5 — Bugs #32-40 (6 fixed, 4 transient)
- ✅ **BR40: Apple Sign-In audience mismatch** — iOS Apple Sign-In had NEVER worked. Backend validated JWT audience against web Services ID (`com.bainluck.web`) but iOS sends bundle ID (`com.bainluck.Bain-Luck`). Fix: accept both as valid audiences. (`auth.py`)
- ✅ **BR39: Preferences pill text wrapping** — Love/Big/Wild/Nah pills wrapped text ("Wil\nd") on wider screens. Added `.lineLimit(1)` + `.fixedSize()`. (`PreferencesView.swift`)
- ✅ **BR37: Economics page parse error** — Three iOS Decodable mismatches: `prob` Int→Double, `peakIs` String→Int, added missing `sideMarkets` field. (`WeatherModels.swift`, `EconomicsView.swift`)
- ✅ **BR36: Politics probabilities >100%** — Independent binary markets showed raw probabilities (Fujimori 98.8% + Newsom 24.5%...). Added `_normalize_outcome_probs()` to politics route with same >105% threshold as feed. 14 tests. (`politics.py`)
- ✅ **BR32: My Stuff irrelevant markets** — "Top Markets" showed generic NBA markets unrelated to user. Set `includeFutures: false` (matching web), team futures via dedicated section only. (`MyStuffView.swift`)
- ✅ **BR-MARKUP: Rage shake annotation offset (recurring)** — PKCanvasView overlay was wider than rendered image. Fixed frame sizing, scroll lockdown, retina-aware scale factors. (`BugReportView.swift`)
- BR38/33/35/34: Feed API failures — confirmed transient (20-min window May 14 evening). Feeds healthy now.

### P0 Security
- ✅ **Gate 20 admin GET endpoints** — Celery health, odds API usage, taxonomy debug, matching review, schedule accuracy, and 15 more diagnostic endpoints now require `_check_admin_secret`. (`admin.py`)

### P1 Engineering
- ✅ **API rate limiting** — ASGI middleware: 60 req/min anonymous, 120 req/min authenticated, admin/docs exempt. Redis storage in prod (reuses Celery REDIS_URL), in-memory fallback. Graceful degradation. 23 tests. (`main.py`, `utils/rate_limit.py`)

### P1 Design
- ✅ **Eliminate hardcoded colors** — ~200 replacements across 35 frontend files mapped to design tokens (text-primary, text-secondary, text-muted, surface-card, surface-secondary, surface-border). Skipped intentional brand colors. Zero visual change. (35 frontend files)
- ✅ **Decompose DiscoverCard.tsx** — 1,041-line monolith → 12 focused files under `components/discover/`. Main file is 91-line thin dispatcher. Public API unchanged. (`DiscoverCard.tsx`, `discover/`)

### Data Quality Bugs
- ✅ **Alcaraz "ATP Indian Wells" team card** — Individual-sport athletes (tennis/MMA/boxing/golf) no longer show misleading "Team" cards in search. Still appear via event/futures results. (`events.py`)
- ✅ **French Open "Player B 100%" placeholders** — Polymarket placeholder sub-markets detected and filtered at 3 layers: ingestion (`_is_placeholder_outcome()`), search display, and 5 futures endpoint code paths. 9 tests. (`polymarket.py`, `events.py`, `futures.py`)

### P1 Design (Wave 3)
- ✅ **PRD rewrite** — 310→249 lines. Restructured: Vision, Target Users, User Journeys, Feature Map, Data Architecture, Metrics, Principles, Non-Goals. Written in present tense. (`docs/PRD.md`)
- ✅ **Formal button system** — `components/ui/button.tsx`: 3 variants (primary/ghost/text), 3 sizes (sm/md/lg), focus-visible accessibility ring, `asChild` support. Applied to 10 buttons across Discover, My Stuff, Daily, Challenge pages.
- ✅ **Remove max-width constraint** — Global content 1200→1600px, sport pages 5xl→7xl, calibration 4xl→6xl, search xl→3xl. Text-heavy/admin pages left narrow. (14 files)
- ✅ **Archive dead pages** — Deleted `/oscars`, `/pulse`, `/ei`, `/explore`, `/masters` + orphaned `OscarsModal.tsx`, `oscarsData.ts`, 9 API functions, 10 type interfaces. Routes 39→34.

### P1 DS (Wave 3-4)
- ✅ **Calibration confidence intervals** — Wilson score CIs per bucket, bootstrap MCE CI (1000 resamples), error bars on calibration chart, "95% CI" column in bucket table, "How We Compare" updated. (`calibration.py`, `CalibrationChart.tsx`, `calibration/page.tsx`)

### Data & Infrastructure (Wave 3-4)
- ✅ **2nd half market maps fixed** — Backend lacked `period` field in game-markets response; frontend guessed from names but Kalshi strips period indicators. Fix: `_extract_period_from_ticker()` derives period from ticker prefix, added `period` field. Web/iOS both use `derivePeriod()` with backend-first fallback. Added missing 2H tickers for NHL/MLB/NCAAB/NCAAF. 27 tests. (`events.py`, `sport_keys.py`, `MarketMapSection.tsx`, `MarketMapView.swift`)
- ✅ **Structured JSON logging** — `python-json-logger` configured for web dyno + Celery workers. Production-only via `DYNO` env var. Local dev stays human-readable. (`main.py`, `tasks/__init__.py`)
- ✅ **68 new contract tests** — Futures browse/categories/movers (33), market moves (8), search with individual-sport filtering (24), calibration bucket validation (9), politics normalization + economics (5). Total: 461 integration tests. (`tests/integration/`)
- ✅ **iOS views audit** — All 27 views, 18 components, 16 Route cases, 15 model files verified reachable. No dead code found.

## May 14, 2026 — Calibration Deep Dive: MCE 4.5pp → 2.65pp

### Golf commence_time Fix — Root Cause Found
- ✅ **Kalshi sets `commence_time = close_time` (resolution date)** — For Masters Top 10, commence_time was Sunday night (tournament end). Calibration grabbed in-play Round 3-4 prices instead of pre-tournament closing line. Also caused stale golf cards in Discover/Sports (feed thinks tournament hasn't started).
- ✅ **Fix via DataGolf schedule** — `_fix_golf_commence_times()` runs after Kalshi poll, matches each golf market to DataGolf schedule using existing `_normalize_tournament()` from the golf route (no new matching system). Sets commence_time to tournament `start_date`. Resets calibration_probability to NULL for recomputation.
- ✅ **Outcome timeline debug endpoint** — `/api/calibration/outcome-timeline` shows full snapshot history for any market's outcomes. Used to prove DeChambeau Masters Top 10 had opening=99% (garbage), calibration=13% (in-play), real pre-tournament price=44% (stable for 10 days pre-event).

### Price History Backfills — Polymarket Rewrite + Kalshi New
- ✅ **Polymarket backfill rewritten** — Targets resolved zero-snapshot outcomes (was: all <24 snaps). NOT EXISTS query instead of expensive GROUP BY. Sleep reduced 0.3s→0.1s. Limit raised 50→500.
- ✅ **Kalshi price history backfill (NEW)** — Uses `GET /markets/{ticker}/candlesticks` for hourly price data. Same pattern: resolved zero-snapshot outcomes. Scheduled every 6h, admin trigger available.
- ✅ **Both APIs serve resolved market history** — Confirmed Polymarket CLOB and Kalshi candlestick APIs return data for resolved/settled markets.
- ✅ **First run recovered 5,432 zero-snapshot outcomes** — Reduced zero-snap from 23K to 17.7K, price-stuck from 63K to 49K.

### Source Intelligence Preserved
- ✅ **Moved to admin page** — `/source-intelligence` → `/admin/source-intelligence`. Dramatic Disagreements section preserved for data quality monitoring. Backend API unchanged.

### VP-Level Audits Completed (4 parallel)
- ✅ **Engineering, DS, Product, Design** — Full audit results integrated into backlog priority stack. Key findings: build `/daily` Wordle-style page, add calibration CIs, eliminate hardcoded design tokens, split admin.py.

## May 14, 2026 (earlier) — Calibration Deep Dive: MCE 4.5pp → 2.7pp

### Calibration Probability Rescue — 18,947 Outcomes Fixed
- ✅ **Part C rescue** — Polymarket outcomes all had `commence_time` set before any snapshots existed, so the closing-line backfill found nothing and fell back to opening prices. Part C uses the last non-extreme snapshot regardless of commence_time. Rescued 18,947 outcomes with real closing prices.
- ✅ **Batch rescue endpoint** — `POST /api/calibration/rescue` runs Part C in 2K batches to avoid Celery worker timeouts on the DISTINCT ON query against the large snapshots table.

### Untradeable Outcome Filter — Strengthened
- ✅ **Extended `_null_untradeable_openings()`** — Now catches outcomes with ≤2 snapshots (was only 0-snap). Also nulls `calibration_probability` (was only nulling `opening_probability`, leaving stale values from prior backfill runs). LIMIT increased 10x to 100K/50K per pass.

### Baseball MLB Fix — Doubled Sample Size
- ✅ **`status IN ('completed', 'closed')`** — 52% of finished MLB games had `status = 'closed'` (set by staleness detector) instead of `'completed'`. Calibration and closing-line queries now include both. MLB outcomes: 614 → 1,164. Total odds_api: 15,916 → 18,568.

### ECE Metric + Trading Activity Analysis
- ✅ **Sample-weighted ECE** — Added Expected Calibration Error alongside MCE on the calibration page. ECE weights buckets by sample size, preventing tiny tail buckets (n=3) from dominating category metrics. baseball_mlb: 28pp MCE → 2.2pp ECE.
- ✅ **`price_moved` dimension** — Calibration API now returns `price_moved: bool` per bucket row, indicating whether the outcome's price changed from opening. Enables splitting calibration curves by trading activity.
- ✅ **"Does Trading Activity Matter?" section** — New calibration page section showing side-by-side curves for outcomes with vs without price movement, with ECE comparison and insight callout.

### Polymarket Price History Backfill — Pipeline Fix
- ✅ **Root cause found** — `backfill_polymarket_history` task existed but was NOT in the Celery beat schedule. 23,327 outcomes (7%) had zero snapshots because their historical prices were never fetched from Polymarket's CLOB API.
- ✅ **Wired into beat schedule** — Every 6h, 500 outcomes/run, background queue. Admin trigger at `POST /api/admin/backfill-polymarket-history`.

### `is_multi` Classification Fix — MCE 5.2pp → 3.8pp (prior session)
- ✅ **`(cv.is_grouped OR cv.eligible >= 3)`** — Markets with 3+ eligible outcomes treated as multi-outcome regardless of `group_id`. Highest single-impact calibration fix.

### Diagnostic Endpoints (6 new)
- ✅ **`/api/calibration/diagnostics`** — Full diagnostic: by-category breakdown, rescue check, timing analysis
- ✅ **`/api/calibration/price-quality`** — Per source×category: same_as_open counts, avg volume, median volume
- ✅ **`/api/calibration/volume-distribution`** — Volume bucket distribution ($0, <$1K, $1-10K, etc.)
- ✅ **`/api/calibration/volume-samples`** — Sample markets with $0 volume to distinguish NULL vs real zero
- ✅ **`/api/calibration/unchanged-samples`** — Random samples of unchanged outcomes with snapshot ranges
- ✅ **`/api/calibration/snapshot-health`** — Zero-snapshot and price-stuck counts per source×category

**Results:** MCE **2.7pp** (target ≤3.0pp ✓), ECE **2.4pp**, **69K outcomes**. Per-source: Odds API 1.3pp, Kalshi 4.4pp MCE / 3.5pp ECE, Polymarket 4.1pp MCE / 4.3pp ECE. All 10 buckets within 5pp. Polymarket price history backfill now running automatically — will continue improving as historical prices fill in.

**Files:** `backend/app/routes/calibration.py`, `backend/app/tasks/backfill_winners.py`, `backend/app/routes/admin.py`, `backend/app/tasks/__init__.py`, `frontend/app/calibration/page.tsx`, `frontend/lib/api.ts`

## May 13, 2026 — Category Page Polish + Infrastructure + Cleanup

### Native Category Page Polish (NATIVE-DESIGN complete — ALL 5 pages)
- ✅ **Economics page iOS polish** — Visual card design matching Politics/Entertainment style.
- ✅ **Entertainment page iOS polish** — Visual card design with richer hierarchy and styled market cards.
- ✅ **Weather page iOS polish** — Temperature colors, probability bars, bracket collapse for cleaner city forecast display.
- ✅ **Politics page iOS polish** — Cards, bars, map, badges refined for native visual quality.
- ✅ **Preferences page iOS polish** — All 5 NATIVE-DESIGN pages now complete (Politics, Entertainment, Weather, Economics, Preferences).

### Game-Markets & Series Markets
- ✅ **Game-markets fix: removed status/category filters** — Linked Kalshi markets were hidden by `status` and `llm_sport_category` filters on the game-markets query. Removed both filters from the linked query path. Overtime, half winners, player props, points leaders now show on event detail pages.
- ✅ **Series markets: dedicated array on event detail** — Series markets (Series Winner, Series Exact Score, Series Spread, Series Total Games) now loaded as a dedicated `series_markets` array via display-time team name query. New `display_category="series"` classification. Backend + web + iOS rendering shipped.

### Bug Admin Analytics
- ✅ **Burndown chart + summary stats** — SVG burndown chart on admin bug reports page showing open vs closed bugs over time, plus summary stats (total, open, closed, avg resolution time).

### Testing & Quality
- ✅ **124 new contract tests** — Playoffs, league futures, related futures, team progression test coverage. Integration test suite total now ~335 tests.
- ✅ **Gotchas #58-62 added** — Feed normalization, staleness threshold, web pin sync, beat schedule test allowlist, Gmail OAuth refresh tokens.

### Bug Fixes & Verifications
- ✅ **BR-PIN: Web pin sync fixed** — Pin sync was localStorage-only on web. Now syncs events + futures pins to server for cross-device persistence.
- ✅ **BR23: Weather city cards clickable** — City forecast cards now link to probability timeline charts (`FuturesDetailView` on iOS, `/futures/{marketId}` on web). Backend exposes `marketId` per city.
- ✅ **BR21: Futures browser images + emoji** — Added image thumbnails and category emoji to FuturesListView rows. Navigation uses shared `RouteDestination`.
- ✅ **BR22: Weather city search** — City search/filter added to both web and iOS weather pages.
- ✅ **BR1-2: Source attribution verified clean** — The v2 rewrite (`sourcesToggle`) shows a single collapsible "Individual Sportsbooks" dropdown. No duplication.
- ✅ **0f-13h: Award headshots verified** — Both `AwardCard` and `AwardCompactRow` in `RelatedFutures.tsx` already use `PlayerHeadshot`.
- ✅ **MS-14: EPL/UFC/Tennis verified resolved** — EPL grid loads correctly. UFC and Tennis removed from nav (no league configs). No dead-end paths remain.
- ✅ **P5b: Trending searches verified shipped** — Redis `ZINCRBY` tracking, `GET /api/search/trending`, web chips, iOS chips with fallback all working.

### iOS League Markets (0s Phase 4)
- ✅ **League market sections on iOS** — `LeagueGridView` now fetches league markets in parallel and renders Playoff Series, Awards, Props, Season Stats, and More Markets sections below the championship grid. Uses slug-to-sport-key mapping for all 14 leagues.

### Email & Notification Infrastructure
- ✅ **D-8: Daily digest email** — Celery beat scheduled at 8am ET. Top movers + resolving-soon markets. Gmail API integration.
- ✅ **D-6: Push notification foundation** — iOS token capture + backend endpoint for device token registration. Actual push sending not yet implemented.
- ✅ **Bug notification system** — Gmail API sends "your bug was fixed" emails with opt-in checkbox on rage shake form. Includes dad jokes.
- ✅ **Email compliance backlog item** — Added CAN-SPAM prerequisites: opt-in model, unsubscribe links, preference management, provider migration path.

### Social Features
- ✅ **D-9: Friend challenges backend scaffold** — New table, model, and 3 API endpoints for challenge creation/acceptance/resolution.

### Golf & Charts
- ✅ **Item 17: Golf chart redesign (iOS)** — Round markers R1-R4, time range picker, tournament-aware chart domains.

### macOS
- ✅ **MAC-9: Share verified cross-platform** — ShareLink works across iOS/macOS. MyStuffView context menus improved (share, copy prob, new window).

### Testing & CI
- ✅ **52 contract tests for category page APIs** — Weather, politics, entertainment, economics API shape validation. Integration suite: 158 → 210 tests.
- ✅ **124 additional contract tests** — Playoffs, league futures, related futures, team progression. Integration suite: 210 → ~335 tests.
- ✅ **CI fix: daily-digest in beat schedule test** — Added `daily-digest` to expected Celery beat schedule entries in `test_tasks_wiring.py`.

### Cleanup
- ✅ **Dead eiRankings route removed** — Was navigating to `EmptyView`. Cleaned up.
- ✅ **About page stats updated** — "90K+" → "130K+" markets tracked (iOS).

## May 12, 2026 — Bug Fixes + Web Nav Redesign

### Bug Reports #25-30 (all fixed)
- ✅ **BR25: Stale binary probabilities** — lowered feed staleness threshold from 97% to 95% leader probability.
- ✅ **BR26: Lowercase league title** — `LeagueGridView` fallback uses `.uppercased()` instead of `.capitalized`.
- ✅ **BR27: Probabilities sum >100%** — feed normalizes independent binary market probabilities when sum exceeds 105%.
- ✅ **BR28: "2 sources" but only one shown** — feed response now includes `sources` array; card shows "KALSHI + POLYMARKET".
- ✅ **BR29: Guess cards on closed events** — iOS guess slot skips completed/closed events and futures with leader ≥95%.
- ✅ **BR30: Stale Met Gala card** — added 14-day filter for markets with NULL resolution_date and zero movement.

### Web Navigation Redesign
- ✅ **Discover is now the default landing page** — bainluck.com loads Discover feed. Sports feed moved to `/sports`.
- ✅ **Desktop nav reordered** — Discover | Sports | Browse (dropdown) | My Stuff. Browse dropdown contains Politics, Entertainment, Economics, Weather.
- ✅ **Mobile bottom nav reordered** — Discover | Sports | Search | My Stuff.
- ✅ **About moved to user menu** — accessible from profile dropdown (both signed-in and signed-out states).
- ✅ **Footer removed** — all links now reachable via Browse dropdown and user menu.

### Web About Page
- ✅ **Markets tracked updated** — "90K+" → "130K+" (current count from calibration).
- ✅ **Calibration link improved** — added "View calibration report →" CTA with arrow icon. Outcome count updated to 474K.

## May 11, 2026 — Prediction Market Calibration Analysis

### Calibration Pipeline + Static Report
- ✅ **Calibration analysis endpoint** (`GET /api/admin/calibration-data`) — pre-aggregated calibration buckets across 3 sources (Kalshi, Polymarket, Odds API). 195K resolved outcomes.
- ✅ **Odds API ground-truth integration** — completed events with opening probabilities and final scores produce calibration data points with known winners (no inference needed). 13,806 outcomes from 6,903 games.
- ✅ **Virtual market reconstruction** — Polymarket multi-outcome events (e.g., "Who wins the presidency?" with 10 candidate sub-markets) are reconstructed into single multi-outcome markets via `group_id`, structurally matching how Kalshi stores championship markets.
- ✅ **Inverted field price correction** — Kalshi markets with 10+ outcomes where `opening_probability > 0.50` are detected as inverted "No" prices and flipped.
- ✅ **Correlated threshold dedup** — player prop markets ("HR 1+, 2+, 3+") collapsed to one calibration data point per market (closest to 50%).
- ✅ **Clean resolution filter** — only includes markets where 80%+ of outcomes resolved to near-0 or near-1.
- ✅ **`is_winner` backfill task** (`backfill_winners`) — sets `is_winner` from `current_probability` on cleanly-resolved markets. 52K of 131K markets backfilled on first run. Scheduled every 6h.
- ✅ **Backfill status endpoint** (`GET /api/admin/backfill-winners/status`) — shows backfill progress per source.
- ✅ **Static HTML report** with SVG charts (no JS dependencies), external studies section, methodology & limitations.
- ✅ **Report builder script** (`backend/scripts/build_calibration_report_svg.py`) — generates the report from endpoint data.

**Results:** MCE **4.8pp**, Brier **0.1745** (30% better than random). 7 of 10 probability buckets within 5pp of perfect calibration. 181K resolved outcomes across 3 sources.

### Data Quality Fixes (same day)
- ✅ **Winner flag inversion bug fixed** — multi-outcome market inversion was flipping winner detection backwards, causing golf 0-10% bucket to show 44.6% actual (should be ~1%). Removed broken inversion; unrealistic opening probabilities (>50% in 20+ outcome fields) now excluded instead.
- ✅ **event_id fallback grouping** — for Polymarket sub-markets without `group_id`, `event_id` is now used as fallback for virtual market reconstruction. Fixes football and other game-level sub-markets.
- ✅ **Default-price filter** — Kalshi golf markets with 80 outcomes all at `opening_probability = 0.97` (no real trading) are detected (50%+ of outcomes sharing same price) and excluded. Golf MCE improved from 20pp to 8.4pp.
- ✅ **Admin proxy route** (`/api/admin-proxy`) for browser-accessible backfill triggers and status checks.

**Files:** `backend/app/tasks/backfill_winners.py`, `backend/app/routes/admin.py` (calibration-data + backfill-winners endpoints), `backend/scripts/build_calibration_report_svg.py`

## May 11, 2026 — TestFlight Launch + iOS Polish

### TestFlight Readiness (14 fixes)
- ✅ **Swipe-to-navigate bug fixed** — Discover cards no longer accidentally navigate when swiping. Replaced `NavigationLink` with programmatic navigation via `NavigationPath`.
- ✅ **Idle timer disabled app-wide** removed — was draining battery on every foreground.
- ✅ **Discover error + loading states** — empty catch block replaced with proper error UI and loading spinner.
- ✅ **Guess card error handling** — `onGuessCompleted` now always fires; API failures don't block the UI.
- ✅ **Route consistency** — extracted shared `RouteDestination` view. Eliminated `Text("Team")`, `Text("About")` placeholder views across all tabs.
- ✅ **iPad Discover NavigationStack** — moved NavigationStack inside DiscoverView so it works on both iPhone and iPad.
- ✅ **print() → os.Logger** in BugReportView screenshot capture.
- ✅ **Watch app force unwraps** replaced with safe `guard let` pattern.
- ✅ **Entitlements cleanup** — removed duplicate `aps-environment` key.
- ✅ **macOS scene modifier chain fixed** — `.defaultSize` and `.commands` were in disconnected `#if os(macOS)` block.
- ✅ **Privacy manifest** (`PrivacyInfo.xcprivacy`) created — declares UserDefaults usage, no tracking.
- ✅ **Privacy policy page** at `bainluck.com/privacy` + in-app link from AboutView.
- ✅ **Economics page crash fixed** — removed `rateCuts` field (backend/iOS type mismatch, field unused).
- ✅ **Xcode warnings cleaned** — removed unused `isSoccer`, `awayShort` variables.

### Native UX Improvements
- ✅ **Discover tab is now default + leftmost** — app opens to Discover, not Sports.
- ✅ **Sticky category chips** — Discover filter chips pinned to top while scrolling.
- ✅ **Swipe hint** — inline "Swipe cards to dismiss" banner shown once for new users, auto-dismisses on first swipe.
- ✅ **Guess cards swipeable** — Higher/Lower cards now wrapped in SwipeToDismiss for consistent gesture behavior.
- ✅ **4-card welcome onboarding** — replaces old 5-step preferences wizard for first launch. Cards: probability explainer, calibration accuracy, gesture tutorial, sign-in value prop.
- ✅ **Sign-in page redesigned** — replaced generic icon+buttons with 4-perk value proposition (team following, personalized Discover, streaks, prediction history).
- ✅ **Prediction stats in My Stuff** — accuracy %, total predictions, current streak, best streak shown at top of team feed. Taps through to full stats view.
- ✅ **Search keyboard no longer auto-focuses** — removed aggressive keyboard pop-up on tab switch.
- ✅ **Browse tab (was Leagues)** — added Prediction Markets section (Politics, Entertainment, Economics, Weather) with colored icons. League rows use SF Symbols instead of emoji.
- ✅ **Sports tab pills → league grids** — NBA/NFL/MLB/NHL chips navigate to championship grid pages. Politics/Entertainment/Economics/Weather chips navigate to rich dedicated views. Removed chips for sports without dedicated pages (Tennis, MMA, Crypto).

## May 11, 2026 — Matching Quality + StatPal Playoff Fix

### StatPal Playoff Parser Fix (Critical)
- ✅ **StatPal playoff games were silently dropped** — `_extract_match_items()` only read `tournament.match` (regular season). Playoff games live in `tournament.week` as `[{"stage": "Play Offs", "match": [...]}]`. 16-line parser fix immediately surfaced CLE-DET Game 5 and all other NBA/NHL playoff fixtures.
- ✅ **StatPal period data now captured** — `raw_status` preserved on `StatPalFixture` (e.g., "Q3", "1H", "HT"). Written to `Event.period` in livescores sync. Previously normalized to "live" and discarded.
- ✅ **Quarter-level scores parsed** — `q1`/`q2`/`q3`/`q4`/`ot` scores from StatPal now available on fixtures.

### Link Rate Denominator + Matching Fixes
- ✅ **Link-rate denominator fixed** — Removed `event_id IS NOT NULL` clause that pulled season futures into the game-market denominator. Reverted series tickers from game-level map. Added guardrail test: no overlap between game and futures ticker maps.
- ✅ **NHL team abbreviations fixed** — `tb_nhl` → "Lightning" (was mapping to NFL Buccaneers), `uta_nhl` → "Mammoth" (was "Utah Hockey"). ~285 unlinked NHL spread/total/prop markets should now match.
- ✅ **Tier 1 gap analysis endpoint** — `GET /admin/prediction-markets/tier1-gaps` diagnoses every unlinked Tier 1 game market with specific failure reason.
- ✅ **Event creation lead-time audit endpoint** — `GET /admin/events/creation-lead-time` measures how far in advance events are created vs their commence_time.

### Event Dedup Fix
- ✅ **Merge task handles both-have-data duplicates** — Previously skipped when both events had external_id + snapshots (e.g., OKC-LAL from two Odds API regions showing 94% vs 80%). Now merges: reassigns all 8 FK tables, deletes orphan.
- ✅ **Merge task batched + committed per-merge** — Limited to 200 pairs per run (was unbounded, timing out on 43K backlog). Per-merge commit so work survives timeouts. 43K backlog drains at ~200/run.

### Tier 1 Coverage Monitoring
- ✅ **Hourly monitoring task** — `check_tier1_coverage` finds unlinked Kalshi game tickers within 36h and logs WARNING. Catches cases where Kalshi has markets but no event exists.
- ✅ **StatPal livescores event creation** — Schedule sync now creates events from live StatPal fixtures that don't have matching events. Catches playoff games that slip through.

### iOS Bug Fixes (Bug Reports #18-24)
- ✅ **Bug #19: Award futures grouped by team** — Players from both teams were mixed in one list. Now grouped with colored team headers.
- ✅ **Bug #20: Internal taxonomy tags hidden** — "National Interest", "Incredible", "Playoff Race" tags removed from iOS event detail UI. Tags still used functionally for series detection.
- ✅ **Bug #24: Daily Challenge copy improved** — "Make 5 predictions" → "Tap Higher or Lower on 5 cards" for first-time user clarity.

### Other Improvements
- ✅ **macOS context menus** — Copy Link + Share added to Feed, Discover, and My Stuff context menus.
- ✅ **Trending searches on iOS** — Search view now fetches trending queries from API instead of hardcoded chips.
- ✅ **macOS live title bar** — Window title shows top live game score, polling every 30s.
- ✅ **Swipe overlay visuals** — Green checkmark (right) and red X (left) on Discover card swipe.

## May 8, 2026 — Rage Shake Marathon (14/14 bugs resolved)

### Rage Shake Triage + Fixes (Sessions 6-7)

All 16 rage shake bug reports triaged, deduplicated into 14 new items. All 14 resolved in one night across two parallel Claude sessions.

**P1 fixes:**
- ✅ **RS-1: iPad sidebar navigation stuck** — Quick Links used `NavigationLink(value:)` which pushed onto the sidebar's NavigationStack, conflicting with tab-based `List(selection:)`. Converted to tagged `AppTab` cases with detail pane rendering. Added 6 new AppTab enum values.
- ✅ **RS-2: Weather API 500** — Missing `timedelta` import in `routes/weather.py` caused `NameError` on all 6 weather endpoints.
- ✅ **RS-3: iOS Additional Markets broken** — 2-column grid → single-column, lineLimit 1→2, resolved 100%/0% outcomes hidden for completed games.

**P2 fixes:**
- ✅ **RS-4: False offline + Preferences 401** — `NWPathMonitor` never started (always "unsatisfied"). Fixed with async continuation. Preferences endpoint changed to `get_optional_user` with default response for anonymous.
- ✅ **RS-5: iPad sign-in failure** — `connectedScenes.first` returns wrong scene on iPad Stage Manager. Now prefers foreground-active scene + key window. Error messages distinguish network/server/auth failures.
- ✅ **RS-6: Stale markets in Discover** — Met Gala market showing 2 days post-event. Added 4th staleness filter: `commence_time` past + no 24h movement → suppressed.
- ✅ **RS-7: Game state on Discover cards** — iOS guess + event cards now show "F 9-2" / "LIVE 8th" with scores. Red color for live status.
- ✅ **RS-8: Discover scroll blocked** — `SwipeToDismiss` DragGesture ate vertical scrolls. Changed to `simultaneousGesture` with horizontal-only activation.
- ✅ **RS-9: Final game display issues** — Period markers 8pt→10pt bold. Stale 50% Polymarket readings filtered. Chart anomaly fixed.
- ✅ **RS-10: Search suggests non-sport** — Category suggestions navigate to dedicated views instead of dead-end searches.
- ✅ **RS-11: Baseball inning markets** — "First Inning Run"/"First 5 Innings" reclassified from `game_prop` to period markets.
- ✅ **RS-12: Market map zero label** — Frontend "Tie"→"0" on margin maps. iOS added "0" text at zero line.
- ✅ **RS-13: Redundant odds on final** — Finished game hero shows "Team Wins" with team color instead of pre-game probability.
- ✅ **RS-14: Excessive whitespace** — Section spacing 16pt→12pt.

### Bug Report Admin Fixes
- ✅ **"Mark as Added to Backlog" button** — Backend `_VALID_STATUSES` didn't include "actioned"/"dismissed". Silent 400 error.
- ✅ **New tab UX** — Clicking a "new" bug no longer makes it vanish. Optimistic local state update.

### Discover Quality Debug Tool
- ✅ **Market trace API** — `GET /admin/discover-quality/trace/{market_id}` explains eligibility, pool membership, staleness filters, quality score, and suggested fixes.
- ✅ **Admin UI** — Frontend trace panel in `/admin/discover-quality` for per-market debugging.
- ✅ **Missing ground truth trace** — Shows why Kalshi/Polymarket email-featured markets don't appear in Discover.
- ✅ **Feed timing diagnostics** — `/api/feed` now emits `X-Feed-Elapsed-Ms`, and admin debug responses show per-stage timings for personalization, events, golf, futures, ranking, and debug tracing.
- ✅ **Discover feed latency pass** — Futures-only feed path no longer scores golf tournaments; futures candidate pools have stage timing; source-count queries are scoped to candidates; feed-specific futures indexes were added; futures ORM hydration now loads only feed-used columns. Production futures-only header observed around **770ms** with quality metrics unchanged.
- ✅ **Ground-truth recall pass** — Major NBA Finals path markets get a targeted sports-postseason candidate lane and score boost, while conference-final path markets stay below championship-level weight. Ground-truth matching now treats "win Finals" and "advance to Finals" variants as the same story, and oil ladders share a story key with sibling WTI oil cards. Production audit moved actionable missing buckets to zero: only game-market noise and sibling stories remain.
- ✅ **Discover shareability pass** — Discover cards now share stable UTM-tagged detail URLs with card-specific share text, clipboard copied state, GA4 `share` events, dynamic Open Graph/Twitter metadata, generated probability-card preview images, shared-link landing CTAs, and `shared_link_open` analytics for event and futures detail pages.
- ✅ **Discover interaction instrumentation** — Discover cards now emit typed impression/action analytics for impressions, detail clicks, dismisses, likes/unlikes, shares, and grouped-card expands. The frontend also keeps an opportunistic local category-interest profile to support the next personalization pass without changing ranking yet.
- ✅ **Local Discover personalization overlay** — The web Discover feed now reads the local interaction profile and applies a bounded client-side re-rank only within five-card windows after the first three cards. It modestly boosts clicked/liked/shared categories, demotes dismissed categories, refreshes after explicit actions, and exposes `data-personalization-trace` for debugging without changing backend feed scoring.
- ✅ **Native Discover first design pass** — iOS/macOS Discover now uses the same game cadence as web for Higher/Lower cards (every fifth item instead of every second item) and upgrades native event cards with clearer status, team identity, larger probabilities, team-color probability bars, scores, context copy, and card elevation.
- ✅ **Native Discover futures/share pass** — Native futures cards now use a stronger story-card layout with taller media/gradient heroes, larger leading probabilities, category/trending chips, clearer outcome bars, source-count pills, and card elevation. Native Discover context-menu share/copy links now use the same tracked Discover UTM URL shape as web.
- ✅ **Native Discover Higher/Lower redesign** — Native futures and event guess cards now use a clearer game-card layout: stronger "What are the odds?" header, larger threshold prompt panel, more tappable Higher/Lower controls, bigger result state, share actions on both card types, streak copy, and less cramped next/detail actions.
- ✅ **Native Discover personalization overlay** — iOS/macOS Discover now stores a local category tuning profile in `UserDefaults`, records detail opens, dismisses, and copied share links, applies the same bounded five-card-window re-rank as web after the first three cards, and adds a toolbar menu showing top local affinities with a reset action.
- ✅ **Native Discover analytics parity** — iOS/macOS Discover now emits Firebase Analytics events for card impressions, opens, dismisses, copied share links, category filter taps, and local tuning resets, tagged with native surface/category/rank metadata so personalization and design quality can be measured alongside web.
- ✅ **First-party Discover engagement capture** — Web and native now send Discover impressions/actions to `/api/feed/interactions`, stored in an append-only `discover_interactions` table. Admins can inspect `/api/admin/discover-engagement` for open/dismiss/share rates by surface, category, and item type.
- ✅ **Discover engagement admin panel** — `/admin/discover-quality` now includes first-party engagement totals, open/dismiss/share rates, category/surface opportunity lists, and top actioned cards alongside feed quality, timing, hook coverage, and trace diagnostics.
- ✅ **Engagement-driven ranking opportunities** — `/api/admin/discover-engagement` now returns promote/investigate/downrank recommendations from first-party open, dismiss, share, and impression rates. The Discover quality admin page surfaces these as candidate ranking/design actions.
- ✅ **Server-side Discover category personalization** — Authenticated feed scoring now derives tiny bounded category boosts/penalties from the user's recent first-party Discover opens, shares, likes, expands, and dismisses. This augments existing favorites/pins/sport-affinity personalization while preserving quality caps and anonymous local tuning fallback.
- ✅ **Discover context snippet fallback + swipe guard** — Web grouped/futures/event cards now render context from `hook_description → reason → headline`, so deterministic explanations appear even when LLM hooks are absent. Mobile web swipe-to-dismiss now suppresses the follow-up link click that could accidentally open event/futures details. Native event/futures cards also use feed `reason/headline` as context fallback.
- ✅ **Discover snippet and fun-market pass** — Web cards now prefer concise deterministic headlines when hooks are absent, truncate long hook snippets behind instant `See more`, and track `context_expand` as a weak interest signal. The feed audit now reports snippet quality issues and a stricter `fun-market-presence@10`, while the first-page mixer pulls one real culture/weird/big-name card into the top 10 when strong inventory exists.
- ✅ **Discover short context summaries** — Feed responses now include a top-level `context_summary` for concise visible card copy while preserving full `hook_description` text for instant `See more` expansion. This moves snippet quality from a UI-only truncation into the ranking/audit contract.
- ✅ **Today’s Challenge web CTA** — The passive progress card now has an explicit `Play next` action that scrolls to the next inline Higher/Lower card and records a `challenge_start` analytics event.
- ✅ **Today’s Challenge focused web flow** — Web Discover now opens Today’s Challenge as a focused modal, presents one Higher/Lower question at a time, advances inside the modal via explicit Next/Finish actions, shows set progress/completion, and records first-party `challenge_start` / `challenge_complete` engagement for admin rollups.
- ✅ **Discover engagement diagnostics v2** — `/api/admin/discover-engagement` and `/admin/discover-quality` now expose context expansion counts/rates plus Today’s Challenge start/completion counts/rates, making snippet curiosity and challenge funnel health inspectable from the admin viewer.
- ✅ **Native Discover challenge/context parity** — iOS/macOS Discover now decodes `context_summary`, shows concise expandable snippets with native `context_expand/context_collapse` events, and opens Today's Challenge as a focused sheet with explicit Next/Finish progression plus `challenge_start` / `challenge_complete` tracking.
- ✅ **Discover personalization trace** — Authenticated feed items now carry a compact `personalization_trace` with base score, final score, multiplier, score delta, category-affinity delta, bounds status, and reasons. `/admin/discover-quality` forwards the signed-in admin token for debug fetches and renders these traces when present so personalization effects are inspectable per card.
- ✅ **Discover personalization admin rollups** — `/admin/discover-quality` now summarizes authenticated personalization traces with boosted/suppressed counts, average multipliers, category effects, top reasons, and filters for boosted, suppressed, neutral, or missing-trace cards.
- ✅ **Discover swipe feedback ranking pass** — Web and native now treat right swipe as `like` / "more like this" and left swipe as `unlike` / "less like this" instead of hard dismissing. Backend personalization reacts faster with bounded category plus feature/entity/archetype affinities for both signed-in and anonymous session users, while onboarding and inline hints explain the gestures.
- ✅ **Cheap LLM Discover intelligence pass** — Added async/cached `discover_llm` metadata enrichment for feed-shaped futures only: topic/subtopic/entities/archetype/audience scope/salience/junk flags/comparison axes. Ranking consumes the cached metadata with bounded deterministic nudges and swipe feature tokens, never live LLM calls. Daily jobs also generate cached comparison-game pair candidates and LLM-proposed admin review rows from top-50 grading plus Polymarket email-highlight misses.
- ✅ **Polymarket email editorial audit signal** — `audit_feed_quality.py` can now ingest the Polymarket email-highlight sheet from a CSV path or published CSV URL, dedupe/filter recent high-interest rows, and report `email-hit@20` / `email-hit@50` plus email hits/misses as an evaluative Discover signal.

### Test Expansion + Improvements
- ✅ **33 seeded-data contract tests** — Feed scoring (16) + event detail (17). Suite: 110→158 tests.
- ✅ **Player award headshots (0f-4d)** — Verified already implemented (all-rosters expansion).
- ✅ **Discover first-page variety** — Improved mixing metrics and archetype caps.

## May 8, 2026 (Parallel Session 2)

### Bug Fixes + Test Expansion
- ✅ **Weather API 500 fixed (RS-2)** — Missing `timedelta` import in `routes/weather.py` caused `NameError` on every weather endpoint call. All 6 weather endpoints were completely broken.
- ✅ **iOS search category navigation (RS-10)** — Politics, Weather, Economics, Entertainment suggestions in search now navigate to their dedicated category views instead of triggering dead-end searches. Added "Categories" section to search empty state.
- ✅ **iOS false offline detection (RS-4)** — `currentNetworkType()` in BugReportView never started the `NWPathMonitor`, so `currentPath` always returned "unsatisfied" → all bug reports showed `network: offline`. Fixed with async continuation + `pathUpdateHandler`.
- ✅ **33 seeded-data contract tests** — Feed scoring/ordering/shape (16 tests) + event detail/game-markets/related-futures/history (17 tests). Integration test suite: 110 → 158 tests.
- ✅ **Player award headshots (0f-4d)** — Verified already implemented at `events.py:3496-3515` (all-rosters expansion for the sport). Backlog updated.

## May 7-8, 2026

### Discover Feed Ranking Breakthrough
- ✅ **Boring/repetitive market suppression** — Added `feed_market_quality` classifier and scoring caps for narrow commodity/finance ladders, dated buckets, social-count filler, music metric spam, and low-quality repeated families. Production audit: `boring-rate@20=0/20`, `ladder/bucket-rate@20=0/20`, `duplicate-family-rate@20=0/20`.
- ✅ **Ground-truth-informed candidate widening** — Feed candidate pools now include non-sports volume, movement, enriched markets, and soon-resolving markets so good Kalshi/Polymarket/email-style stories can enter scoring instead of being crowded out by stale sports or finance ladders.
- ✅ **Story-family diversity caps** — Top feed avoids repeated versions of the same story family after scoring. Exact families and broad story families are capped before response serialization.
- ✅ **Compelling-topic boosts** — Health outbreak, AI/tech, geopolitics, elections, Fed/economics, entertainment, sports personnel, and other public-interest markets get priority over mechanically active but boring markets.
- ✅ **Deterministic Discover explanations** — Futures cards now generate specific headlines from existing outcome data: named movers, opening-probability surprises, leader changes, and source disagreement. This moved production `explanation-coverage@20` from **4/20 → 20/20** without relying on OpenAI hook generation.
- ✅ **Curated first-page mixer** — Discover mode now applies first-page category caps after scoring so politics/geopolitics/economics cannot swallow the whole opening scroll. The mixer reorders, but does not drop cards or mutate scores.
- ✅ **Archetype/story mixing** — First-page mixer now also caps editorial archetypes and story families, with a required-texture pass that can pull strong tech/culture/weather/sports/weird cards into the first page when available.
- ✅ **Positive quality eval metrics** — Feed audit now reports positive archetype coverage (`world_event`, `tech_frontier`, `macro_signal`, `culture_moment`, `health_weather_risk`, `sports_story`), strict variety targets, category spread/max concentration, and archetype distribution.
- ✅ **Bounded hook enrichment** — Reversed unsafe backlog-scale hook behavior. `enrich_market_hooks` now targets only feed-shaped candidates, runs `limit=100` every 6h, and manual admin trigger is capped at 250. No more plan to spend API calls on ~56K open markets.
- ✅ **Discover quality audit** — `backend/scripts/audit_feed_quality.py` reports precision metrics: boring rate, ladder/bucket rate, duplicate family rate, explanation coverage, ground-truth hit rate, category distribution, and top-card debug reasons.
- Backend: `routes/feed.py`, `utils/feed_market_quality.py`, `utils/feed_reasons.py`, `tasks/enrich_markets.py`, `tasks/__init__.py`, `routes/admin.py`, `scripts/audit_feed_quality.py`
- Tests: `test_feed_market_quality.py`, `test_feed_scoring.py`, `test_futures_highlights.py`, `test_feed_reasons.py`

## May 7, 2026

### Health Check + Security Hardening + CI
- ✅ **DataGolf live fix** — 3,557 consecutive failures since Apr 22 (UniqueViolation). Fixed: check for existing markets before creating, reopen closed ones.
- ✅ **Championship grid performance** — Endpoints were timing out. Fixed: statement_timeout, N+1 query collapse (150+ → 1), resolved market filter, snapshot LIMIT.
- ✅ **MLB prediction market matching** — 22% → climbing. Root cause: Kalshi abbreviations ("A's", "Chicago WS") failing ILIKE. Fixed: prefer ticker-derived team names, added ATH/WSH_MLB to abbreviation map.
- ✅ **Denominator pollution audit** — All admin metrics fixed so 100% is achievable: link rate uses open-only, matching coverage filters to sports with PM markets, overall_health only critical for essential tasks, unclassified_rate sports-only.
- ✅ **Tier 1 compliance endpoint** — `GET /api/admin/prediction-markets/tier1-compliance`. Every MLB/NBA/NHL/NFL event must have all 5 sources. Per-event gap listing. Golf section for PGA tournaments.
- ✅ **Security hardening (Codex review)** — Auth on 8 admin write endpoints, sports sync auth, server-side prediction verification, bug report validation, frontend secret gates.
- ✅ **Performance** — Prediction stats SQL aggregation (was loading all rows), event history 3K cap + 1hr cache for completed games.
- ✅ **CI: frontend build** — `npm run build` in GitHub Actions catches ESLint + TS errors before Vercel deploy.
- ✅ **CI: alembic safety** — Tests for single head, migration count floor, revision chain integrity.
- ✅ **62 TypeScript errors fixed** — Unblocked Vercel deploys (20+ failed builds).
- ✅ **Vercel ESLint fix** — Hooks-after-early-return in admin pages.
- ✅ **NHL StatPal unicode fix** — "Montréal" now matches "Montreal" via diacritics stripping.

### iOS Parity: Politics + Entertainment Native Rewrites
- ✅ **PoliticsView.swift** (410 lines) — Bar-race hero with R/D/I party badges and 7d change chips, chamber control cards, senate state map grid (11-col geographic layout), cross-source spotlight cards, themed market card grids
- ✅ **EntertainmentView.swift** (450 lines) — Trending hero cards with kind-specific bodies, Spotify Race horse-race (outcomes as contenders), music/movies/TV sub-sections, cultural moments feed with yes/no bars, tech & culture section
- ✅ **CategoryModels.swift** — Full decode support for new API shapes: PoliticsCandidate with party/dual-source/history, ChamberControl, CrossSourceMatch, EntMarketRow with kind/volume/image/hook, EntThresholdGroup

### Entertainment Fixes — Spotify, Heatmaps, TMDB
- ✅ **Spotify Race fixed** — Shows outcomes within a single market as horse-race contenders (not separate markets as rows)
- ✅ **RT heatmap** — Fed-style grid component, grouping regex fixed for actual Kalshi format
- ✅ **Billboard heatmap** — Same grouping logic, renders when threshold groups exist
- ✅ **TMDB poster enrichment** — `useTMDBPoster` hook auto-fetches movie posters for rt/boxoffice cards
- ✅ **Kind classification tightened** — Removed greedy `kxrt` prefix, Spotify kind limited to chart-race patterns
- ✅ **Artist streaming direction** — Parses ↑/↓ from market question, shows colored indicators

### Presidential Hero Fix — French Election Bug
- ✅ **Non-US election filter** — `_is_headline_market` requires US-specific keywords, excludes French/UK/Canadian/etc. markets
- ✅ **VP market exclusion** — "Democratic VP nominee" no longer matches as presidential headline
- ✅ **Resolved chamber control filter** — Skip control markets where either side >97%

### Entertainment Page v1 Design — Full Rewrite
- ✅ **Editorial trending hero** — Lead card (1.4fr, 2 rows) + 4 smaller cards with kind-specific card bodies (Spotify leader+runner-up, RT threshold+histogram, reality binary split, multi-outcome lists, Eurovision flags)
- ✅ **Music section (tabbed)** — Spotify Race horse-race rows with cover tiles + delta chips | Billboard market list | Album drops 3-col grid with histograms | Artist streaming compact grid
- ✅ **Movies & TV section (tabbed)** — Rotten Tomatoes market list | Box Office histogram cards with cover tiles | Reality TV cards with binary split bars and multi-outcome lists
- ✅ **Cultural moments masonry feed** — 3-column CSS masonry layout with moment cards: tag chips, headlines, editorial hooks, yes/no bars or multi-outcome lists
- ✅ **Tech & Culture sticky sidebar** — Compact market cards for social media, tech culture, and platform bets. Binary yes/no bars and multi-outcome lists
- ✅ **Cover tiles** — Gradient + initials with optional image_url overlay (TMDB-ready). Deterministic color palette from title hash
- ✅ **Filter chips** — All / Music / Movies / TV / Internet / Live Events with section visibility control
- ✅ **Enriched backend** — Kind classification (spotify/billboard/boxoffice/rt/reality/eurovision/multi/binary), trending scoring with kind diversity, threshold market grouping, volume/delta/resolution/hook/image fields
- Backend: `routes/entertainment.py` — enriched market rows, kind classification, themed sections, trending builder
- Frontend: `app/entertainment/page.tsx` (1000+ lines), `entertainment.module.css`, updated types in `lib/api.ts`
- Design source: Claude Design `entertainment-and-culture` prototype (Entertainment.html)

### Politics Page v1 Design — Full Rewrite
- ✅ **Presidential bar-race hero** — Ranked candidate table with party badges (R/D/I auto-detected from ~60 known names), dual Kalshi/Polymarket bars when both sources available, source toggle (Merged/Kalshi/Poly)
- ✅ **Evolution chart** — SVG multi-line chart showing top 6 presidential candidates over time. Uses real FuturesOddsSnapshot data (30d, downsampled to 50pts). 7d/30d/All range toggle. Hero variant toggle switches between Rankings and Trends views
- ✅ **Sparklines** — Per-candidate 7d trend lines from historical snapshot data, color-coded green/red by direction
- ✅ **Movement chips** — ↑/↓ 7d change per candidate, computed from FuturesOddsSnapshot history
- ✅ **Senate state map** — 11-column geographic grid (all 50 states) colored by Dem win probability (red→gray→blue). State extracted from Kalshi kxsenate tickers + market name parsing. Hover for detail
- ✅ **Chamber control cards** — Senate + House R% vs D% with binary bars, detected from control markets
- ✅ **Cross-source spotlight** — Markets where Kalshi and Polymarket disagree, ranked by delta. Shows side-by-side probabilities with disagreement badges (>5pp flagged)
- ✅ **Category-themed market cards** — Colored top borders per theme (blue=presidential, purple=congressional, green=gubernatorial, amber=policy, red=SCOTUS, sky=international). Binary (yes/no bar) and multi-outcome (leader + runners-up) variants
- ✅ **Sub-theme nav** — Sticky chip rail with per-section market counts, smooth-scroll jump links
- ✅ **Source badges** — Kalshi (green), Polymarket (blue), Both (gradient)
- ✅ **CSS module** — `politics.module.css` with full design system tokens, responsive mobile layout
- Backend: `routes/politics.py` — dual-source merge, party detection, history query, senate map builder, chamber control, cross-source matching
- Frontend: `app/politics/page.tsx` (1100+ lines), `politics.module.css`, updated types in `lib/api.ts`
- Design source: `docs/designs/politics-v1/project/lib/` (Claude Design prototypes)

## May 6, 2026

### New Category Pages: Politics + Entertainment
- ✅ **`/politics`** — Initial politics dashboard (superseded by May 7 v1 redesign above)
- ✅ **`/entertainment`** — Entertainment and culture prediction markets dashboard (Oscars, box office, awards, pop culture). Same quality filters as politics.
- Backend: `routes/politics.py`, `routes/entertainment.py` with filtered market queries
- Frontend: `app/politics/page.tsx`, `app/entertainment/page.tsx` with category-specific styling
- Both pages follow same pattern: filtered API response, themed hero, quality-checked markets

### Infrastructure & Observability
- ✅ **Sentry PendingRollbackError filtering** — Filtered from Sentry to preserve 5K/mo free quota (resets May 20). Prevents noise from transient DB conflicts.
- ✅ **404 sport key caching** — Cache unknown sport keys in Redis for 24h. Saves ~37K wasted Odds API calls/day from malformed sport key lookups.
- ✅ **DataGolf UniqueViolation fix** — 3,557 consecutive failures since April 22 resolved. Postgres advisory lock prevents duplicate tournament insertions.
- ✅ **Championship grid timeouts fixed** — N+1 query elimination, statement_timeout increase to 30s, resolved market filtering. Grid loads reliably now.
- ✅ **Hook enrichment boost** — 500 markets/batch hourly (was 200 every 2h). Prioritizes missing hooks over regenerations. Cost ~$1/day.
- ✅ **Hook coverage endpoint** — `/api/admin/hook-coverage` shows tier breakdown, missing hook count, batch limits. Diagnostic tool for enrichment pipeline.
- ✅ **Request observability** — Request ID middleware + duration logging for every API request. Structured logs show `request_id` and `duration_ms`.
- ✅ **Aggregation quality monitoring task** — Daily check of source diversity across live events. Logs warning when >20% are single-source.
- ✅ **Source ingestion metrics** — Structured logging for Kalshi + Polymarket polling with markets_found, markets_matched, markets_classified counts.

### Data Quality (0f Items)
- ✅ **0f-2: Futures detail garbage outcomes** — Filter "player A/AB/L" garbage names from futures detail page. Polymarket Cy Young now clean.
- ✅ **0f-9: PM probabilities resolve on completion** — `transition_event_statuses` writes 1.0/0.0 to kalshi/polymarket win_probability_sources when game completes.
- ✅ **0f-10b: Cross-source player prop dedup** — Server-side merge of same player+stat+threshold from multiple sources. Added `source_count` field.
- ✅ **0f-12: Monotonicity enforcement** — Game totals and period totals (half/quarter) drop violating points where P(Over X+1) > P(Over X).
- ✅ **0f-4c: Opening player prop probabilities** — `opening_over_probability` field added to player props for pre-game comparison. Backend shipped.
- ✅ **0f-4: Event detail verified clean** — Live Yankees vs Red Sox audit confirms all market types showing.
- ✅ **0f-3d-1: Sport validation in matching** — Ticker-derived sport prefix now hard-rejects cross-sport matches. KXNBA can't match baseball_mlb events.
- ✅ **1d: Non-NHL hockey markets** — KHL/AHL/DEL/PWHL markets now detected and filtered from link rate denominator. Hockey link rate adjusted accordingly.
- ✅ **1f: Kalshi team aliases** — Verified not needed. MLB (30 teams, 0 cells missing Kalshi), NHL (32 teams, 0 cells missing).

### iOS/macOS Fixes (15+ items)
- ✅ **iOS-12: Score diff chart fallback** — When ESPN history has null scores, fallback to win_prob_history game_state data for score differential chart.
- ✅ **iOS-GD3: Win prob chart clipping** — Charts now clip at game end time (last data point + 5min buffer) instead of extending with stale post-game data.
- ✅ **iOS-5: Native Weather + Economics** — New WeatherView.swift and EconomicsView.swift matching web pages. Full API integration with themed styling.
- ✅ **MAC-4: Toolbar refresh button** — Native toolbar refresh button with countdown ring for scheduled games. Replaces menu-only refresh.
- ✅ **MAC-7: Hover states** — Feed cards show hover background on macOS. Subtle visual feedback for mouse users.
- ✅ **MAC-8: Right-click context menus** — All card types support context menu: Open, Pin, Share, Copy Link.
- ✅ **SN-5: Cmd+K shortcut** — Navigate menu Cmd+K shortcut focuses search bar on macOS.
- ✅ **iOS-GD1, GD2, GD4, GD5, GD6, GD7, GD8, GD9, GD10, GD11, GD13, GD14** — 12 event detail polish items from iOS game detail audit.

### Web Frontend
- ✅ **0f-13g: Player props default to Points** — Player prop cards default to Points category with per-card expand/collapse for other stats.
- ✅ **0f-13h + 0f-4e: Eager headshot loading** — Player award headshots and player prop headshots use eager loading with `loading="eager"` to prevent 60s delay.
- ✅ **0t-2 + 0t-3: Chart alignment** — Chart domains use shared ticks, period markers aligned, x-axis labels match between win prob and score diff.
- ✅ **BR3-1: Market map zero labeling** — MarketMap always renders positioned "0" label at actual zero point when offset from center.
- ✅ **SEARCH-P1d: Widen search dropdown** — Both typeahead and recent search dropdowns now `min-w-[480px]` on sm+ to prevent truncation.
- ✅ **Trending searches** — Redis tracking of search queries with zero-state chips showing top searches. Weighted by recency.
- ✅ **D-3a: Volume-weighted feed scoring** — Added volume_24h, volume_7d_avg, velocity scoring (3x avg = +12, 1.5x = +5), surprise factor (+15 for >=20pp moves).
- ✅ **D-10: Resolution notifications** — Wired `/api/predictions/resolutions` to Discover page. Shows up to 3 resolved prediction cards at top.

### Discover Feed Polish (VP-of-Design Pass)
- ✅ **Guess density 50% → 20%** — Every 5th card instead of every 2nd. Content-first feed.
- ✅ **Today's Challenge UX** — Removed confusing inline expansion + auto-scroll. Now passive progress tracker that counts feed guesses.
- ✅ **Source badges removed** — KALSHI/POLYMARKET labels meant nothing to casual users.
- ✅ **Movement badge threshold** — Suppressed <2% moves (noise, not signal).
- ✅ **"Show all N outcomes"** — Shows "Show more" when N > 10 (less intimidating).
- ✅ **Redundant resolution dates** — Suppressed "Resolves May 14" when outcomes are already date-named.
- ✅ **Imageless card treatment** — Shorter hero (h-32) with category emoji watermark for visual character.

### Mixed Bag — 6 Items Shipped (Discover, Search, Frontend, Matching)

**Frontend Fixes:**
- ✅ **MS-May4-3: Tennis futures infinite loading spinner** — Skip SWR fetch for invalid/NaN market IDs, show back navigation during loading/error states, improved error messages for 404s vs invalid IDs.
- ✅ **BR3-1: Market map zero labeling** — MarketMap now renders a positioned "0" label at the actual zero position when offset from center (where "Tie" sits).
- ✅ **SEARCH P1d: Widen search dropdown** — Both typeahead and recent search dropdowns widened to `min-w-[480px]` on sm+ breakpoints to prevent futures name truncation.

**Feed & Scoring:**
- ✅ **D-3a: Volume-weighted feed scoring** — Added `volume_24h` + `volume_7d_avg` to `compute_base_score`, volume velocity scoring (3x avg = spike +12, 1.5x = uptick +5), surprise factor (|current - opening| >= 20% = +15, >= 10% = +8) to both event and futures highlight scoring.
- ✅ **D-10: Resolution notifications** — Wired existing `/api/predictions/resolutions` endpoint to Discover page via SWR. Renders up to 3 ResolutionCards at top of feed showing resolved predictions.

**Matching Quality:**
- ✅ **0f-3d Issue 1: Sport validation in matching** — Ticker-derived sport prefix now hard-rejects cross-sport matches in `_score_candidates()`. KXNBA tickers can no longer link to baseball_mlb events due to city name collisions (Boston, New York).

**Investigated (no fix needed):**
- **0t-bonus: Soccer EFL/League 2 53-minute late start** — Not a timezone bug. Full commence_time chain is UTC throughout. 53-minute gap is late odds publication for lower-tier English football, not a code issue.

## May 5, 2026

### Backlog Blitz — 14 Items Shipped

Systematic pass through the backlog, clearing quick wins then medium-effort items.

**Bug Report Fixes (from Rage Shake #2):**
- ✅ **Score Diff period markers** (Bug #2): `.ultraThinMaterial` rendered as opaque black boxes inside Chart annotations on some iOS versions. Replaced with `Color.cardBackground.opacity(0.9)`.
- ✅ **Admin auto-review removed**: Clicking a bug report no longer auto-transitions to "reviewed" — status must be changed manually.
- ✅ **Submit error handling**: Shows error message + allows retry when offline, instead of greying out the button permanently.

**Event Detail (iOS):**
- ✅ **BR1-1**: Completed game hero showed opening odds as giant numbers AND as "Opened X% – Y%" caption (same data twice). Caption changed to "Pre-Game Odds" label.
- ✅ **iOS-GD6**: "BainLuck / Sportsbooks" redundant legend row removed. "Sources" dropdown renamed to "Individual Sportsbooks."
- ✅ **iOS-GD4**: Chart legend "Bain Luck Model" renamed to "Statistical Model" to distinguish from "Bain Luck" aggregate line.
- ✅ **iOS-GD2**: Team records (10-16-2) reduced to size 9 + quaternary opacity to visually separate from scores.
- ✅ **iOS-GD11**: Award probability bars — inline 30px capsule bars next to each percentage in the Awards section.
- ✅ **iOS-GD14**: Game Info footer uses absolute date ("May 4 at 7:00 PM") instead of RelativeTimeText ("Today") for scheduled games.
- ✅ **iOS-GD10**: LLM-generated prose summary removed from Season Futures section — card sections below already show the same info visually.
- ✅ **iOS-GD7**: Chart x-axis ticks use stride-based intervals (15/30/60 min) instead of `.automatic` which rounded to "nice" hours and could skip past game start.
- ✅ **iOS-GD13**: "Team to make postseason" now routes to Championship Path bucket instead of duplicating in Season Outlook. Added "postseason" and "make.*playoffs" to `divisionPlayoffPattern`.

**Data Accuracy:**
- ✅ **MS-May4-2**: Soccer/EPL charts extended 50-60 min past game end because `GAME_END_SOURCES` only included US sources (ESPN, MLB). Added sport-specific duration fallback: soccer 110min, tennis 180min, cricket 240min from `commence_time`.
- ✅ **MS-May4-5**: NBA/NHL grids missing Make Playoffs + Win Division columns. Root cause: grid query filtered `status IN ("open", "closed")`, excluding resolved markets. During active playoffs, early-stage markets are resolved. Fixed to include `"resolved"`.
- ✅ **MS-May4-1**: MLB runs map monotonicity violation (41% → 75%). Cross-source merge (Kalshi + Polymarket) produced non-monotonic over_probabilities. Added dedup-by-threshold (keep highest-volume source) + monotonicity enforcement on the total map.

**Rage Shake Polish:**
- ✅ **macOS paste**: Fixed clipboard reading to handle PNG/TIFF data types (Cmd+Ctrl+Shift+4 copies to clipboard as PNG, not file URL).
- ✅ **macOS Report a Bug**: Menu item was greyed out because `NotificationCenter.post` in `CommandMenu` doesn't enable SwiftUI buttons. Changed to `navCoordinator.showBugReport` state binding.
- ✅ **macOS screenshot**: Gave up on programmatic capture (SwiftUI's Metal rendering can't be captured via AppKit APIs). Shows paste prompt instead.
- ✅ **SwiftUI warning**: Fixed "Publishing changes from within view updates" in MainTabView tab selection binding.

**Other:**
- ✅ **Bug reports dashboard v2**: Stats section (total/new/resolved/avg response time), severity badges (P0-P3), leaderboard, triage progress bar.
- ✅ **macOS build fixes**: Replaced deprecated `CGWindowListCreateImage`, fixed `systemGray6` → `Color.cardBackground`, added missing `.about` Route case to all switch statements.

### Still Open (needs investigation)

- **iOS-GD3**: Post-game win prob drifts to 50% — needs DB query to find wrong linked market
- **iOS-GD5**: Chart indicators cluttered — design decision needed
- **iOS-GD9**: Championship Path shows wrong league rows — backend team-progression logic
- **BR1-2**: Source attribution design — need to decide on display approach
- **BR1-3**: 5 Polymarket NBA markets at 0% link rate — matching investigation
- **MS-May4-4**: EPL league page data contamination — filtering issue
- **MS-May4-3**: Tennis futures infinite spinner — can't reproduce

## May 3, 2026

- ✅ **Rage Shake bug reporting (full stack)**: Shake iOS device (or Cmd+Shift+B on macOS) to report bugs. Captures screenshot with PencilKit finger/pencil markup overlay, text description, and automatic app state (current tab, app version, device model, OS version, user ID, session ID, live game count, timestamp). Backend: `POST /api/feedback/bug-report` stores base64 screenshot + JSONB state in `bug_reports` table. Admin: `GET/PATCH /api/admin/bug-reports` for inbox management. Frontend dashboard at `/admin/bug-reports` with split-pane layout, decoded screenshot viewer, status toggles (New/Reviewed/Actioned/Dismissed), app state metadata. Works for all users (auth + anonymous). 12 files, 649 lines.
- ✅ **Polymarket-style hook descriptions**: Upgraded LLM hook generation from 120-char generic sentences to 250-char contextual, newsy blurbs. Prompt now includes opening probability, all top 5 outcomes, volume signal, and "why this matters" framing with Polymarket email-style few-shot examples. Smart re-generation: tracks `hook_generated_at` + leader at generation time, skips recent hooks unless leader changed or probability moved >15pp. `max_tokens` 60→150.
- ✅ **Polymarket email blurb pipeline**: Google Apps Script extracts editorial blurbs from Polymarket's daily marketing emails (Gmail tag already set up). Parses market titles + context paragraphs from HTML. Blurbs stored as few-shot training examples for the hook generation prompt.
- ✅ **Completed game hero fix**: iOS event detail shows opening odds ("Opened 45% – 55%") for finished games instead of misleading near-final 2%/98%. Falls back to "Final" when opening odds unavailable.
- ✅ **Discover card compaction**: iOS event cards redesigned from vertical stack to compact horizontal layout — 28px logos, inline scores, ~40% shorter.
- ✅ **Onboarding team search fix**: Deduplication by school/franchise name (Harvard shows once, not 8 times). Preseason/foreign league filtering. Multi-sport expansion — schools show "N sports" with chevron, tap to pick individual sport teams.

## May 2, 2026

- ✅ **TeamNameLink (Phase B)**: Shared `TeamNameLink` component + `teamUrls.ts` utility (`slugify`, `buildTeamPageUrl`). Wired into EventCard, FeedCard, event detail hero, ChampionshipGrid, TournamentProgressionTable, and team page GameCard. Team names are clickable links to `/sport/[sport]/[league]/team/[slug]`. SearchBar refactored to use shared `buildTeamPageUrl`. 9 files, 160 lines.
- ✅ **Search Phase 4: Fuzzy matching**: `pg_trgm` extension + GIN trigram indexes on `teams.name`, `events.home_team_name`, `events.away_team_name`, `futures_markets.name`. Typeahead and full search fall back to trigram similarity (threshold 0.25) when ILIKE finds no results. Both endpoints return `did_you_mean` when fuzzy correction applied. Frontend shows "Showing results for X" banner. Migration `a7b8c9d0e1f2`.
- ✅ **Search Phase 5: UX polish**: Cmd+K / Ctrl+K global shortcut focuses desktop search bar (keyboard hint badge). Recent searches stored in localStorage (last 5), shown on focus before typing. Mobile search overlay replaces `/search` page navigation — full-screen with auto-focus, recent searches, typeahead results, Cancel button.
- ✅ **Chart bug fixes (0f-13a, 0f-13b)**: Chart no longer extends 30-45min past game end — clips at last ESPN data point + 5min buffer instead of stale `completed_at`. Both charts now use identical shared tick labels computed in parent via `sharedTicks` prop.
- ✅ **Half margin maps fix (0f-13c)**: `halfMarginMaps` was reading from `gameMarkets.spreads` (full-game only) instead of `gameMarkets.period_markets`. Both 1H and 2H margin maps now render.
- ✅ **Team page SEO**: JSON-LD `SportsTeam` structured data + dynamic `document.title` on team pages.
- ✅ **Search P5c: entity-grouped results page**: Results organized into Teams / Games / Futures & Markets sections with counts. Backend returns matched teams (name, slug, logo, record, sport_key). New TeamCard component links to team pages. Summary line with per-entity breakdown.
- ✅ **Polymarket game markets fix (0f-13i)**: Polymarket spreads, totals, and player props now surface on event detail pages for the first time. Root cause: Polymarket series events don't have per-game event_ids matching Odds API events, and sub-market names ("O/U 196.5") lack team names. Fix: game-markets endpoint finds Polymarket parents by team name, then pulls sub-markets via group_id — bypassing event_id linking. Also added +8 scoring bonus for Odds API events and Phase 1.5 re-linking priority for completed events.
- ✅ **iOS search parity (SN-1..4)**: Enriched TypeaheadSuggestion with team_id, team_slug, sport_key, eventId, status, commenceTime, marketTypeLabel. New TeamDetailView.swift — full team page with hero, championship path, games, futures. Teams section in search results with logos/records. "Did you mean" fuzzy correction in typeahead and results. Typeahead now navigates directly to team/event/futures pages with logos and status badges.
- ✅ **About page revamp (web + iOS)**: Complete rewrite of /about — hero with probability visual, 6 category cards (Sports through Entertainment), multi-source aggregation explainer, Discover feed intro, By the Numbers stats, collapsible Under the Hood section (semantic matching, aggregation, production engineering for portfolio visitors), philosophy + disclaimer. New iOS AboutView.swift with matching content, linked from My Stuff tab. TeamDetailView wired into MyStuffView navigation (was placeholder).
- ✅ **Health check + grid fixes (6 commits)**: Link rate denominator fixed to game-level markets only (was counting season futures in denominator — reported 62%, real rate 95.5%). League-level breakdown added. Golf grid noise filter changed from price floor/ceiling to volume-only. League classification made sport-aware (`detect_league()` now takes `sport_category` — fixes esports→PGA, cricket→EPL contamination). Grid staleness filter (7-day cutoff + Odds API stale zeroing). Golf grid tournament name matching now includes Kalshi ticker prefix with freshness check.
- ✅ **N+1 query fixes**: Eliminated ~260 queries/cycle across `poll_all_odds` (batch event pre-load, WPS from ORM object) and `poll_live_prediction_markets` (use batch-loaded `outcomes_by_market` instead of re-querying). ESPN sync fixes shipped by parallel thread.
- ✅ **iOS Discover parity (DN-1..DN-14, 19/19 items)**: Fixed broken prediction POST (was raw URLSession with no auth — predictions weren't tracked). New PredictionStatsView with accuracy, streaks, categories, badges. "Next question" auto-scroll. Daily Challenge card with progress ring (5/day goal, UserDefaults persistence). Events as guessable with team logos. Guess density every 2nd card. Dismiss persistence to UserDefaults. Swipe-to-dismiss with animation. Onboarding auto-trigger. Grouped market cards (accordion by name prefix). Animated probability counter (numericText transition). Resolution notification cards (new `/api/predictions/resolutions` endpoint). Share prediction via native share sheet. Movement badges + trending indicator. Cmd+K on macOS.
- ✅ **iOS Search parity (SN-1..SN-5)**: Team results with logos/records. Team page navigation (TeamDetailView). Enriched typeahead model (team_id, sport_key, status, logos). "Did you mean" fuzzy correction. Cmd+K macOS shortcut. Backend typeahead API enriched with team_slug, sport_key, logo_url, status fields.
- ✅ **Onboarding team search fix**: Deduplication by normalized team name (Harvard shows once, not 8 times). Preseason/foreign league filtering. Multi-sport expansion — schools show "N sports" with chevron, tap to pick Basketball/Football/Hockey individually. Backend groups by name, returns `sports[]` array with per-sport team IDs.
- ✅ **Completed game hero fix**: Shows opening odds only ("Opened 45% – 55%") instead of misleading near-final 2%/98%. Falls back to "Final" when opening odds unavailable.
- ✅ **Discover card density**: Event cards redesigned from vertical to compact horizontal layout — 28px logos, inline scores, ~40% shorter.

## May 1, 2026

- ✅ **Discover feed breakthrough**: Removed `% at %` SQL filter that was killing 10,300 non-sports markets (economics, politics, tech, entertainment). Changed pool sort from tier+resolution to volume. Added micro-bet penalty for <24h resolution markets. Scheduled LLM hook + image enrichment tasks 4x daily. Combined ground truth: 295 Kalshi + 4,680 Polymarket + 146 email = 5,121 labeled markets. Feed went from 0% non-sports to ~85% non-sports.

## April 30, 2026

- ✅ **Discover content mix fix**: Feed API `event_pct` param lets Discover request 15% events instead of the default 60%. Non-sports futures (politics 35, geopolitics 38, economics 34, tech 34 base scores) now dominate Discover instead of being crowded out by sports events. Sports feed unchanged.
- ✅ **Wild-ending boost for completed events**: `compute_base_score()` now reads `ei_metadata` for `comeback_factor` and `lead_changes`. Miracle comebacks (winner was ≤10%) get +30, big comebacks (≤20%) get +20, 4+ lead changes get +10. Wild games surface in Discover alongside interesting futures.
- ✅ **Crash prevention**: Startup smoke test (`test_startup.py`, 4 tests, <1s) verifies app imports, route modules, task modules, and utility modules. Procfile validates imports before Alembic runs — broken code no longer reaches the web dyno. Catches the exact crash class from April 30 (broken imports in predictions.py, og_image.py).
- ✅ **ESPN box scores fully working (3-bug chain)**: (1) `espn_id` wasn't persisting due to ORM/Core mixing — fixed by piggybacking onto the existing `win_probability_sources` Core SQL update. (2) `box_score_data` write silently failed — fixed via raw SQL text + ORM sync. (3) `box_score_data` was never in the event detail API response — added 5 lines to `GET /api/events/{id}`. Verified: HOU@BAL shows 28 players with real stats (hits, RBIs, runs, walks, batting average). Player props on completed games now show actual results instead of "0 so far". Accrues to both web and native.
- ✅ **Site crash fix**: `predictions.py` and `og_image.py` imported `from app.database` (doesn't exist) instead of `from app.services`. Web dyno crash-looped for ~15 min.
- ✅ **BAINLUCK-FY N+1 fix**: Removed redundant `select(Sport)` from inside the per-event loop in `odds_polling.py`. ~200-400 duplicate queries eliminated per poll cycle.
- ✅ **Manus sweep (9 modules)**: Projected final score hidden for completed games. Chart stale tails fixed (`completed_at` caps domain instead of extending). MLB grid score 36 diagnosed as source disagreement (Polymarket Make Playoffs prices uniformly stale ~25%).
- ✅ **Prediction Streaks & Stats**: `user_predictions` table tracks every Higher/Lower guess. `POST /api/predictions` records guesses (auth-aware: user_id when logged in, session_id when anonymous). `GET /api/predictions/detailed-stats` returns total, correct, accuracy, current/best streak, category breakdown, 14-day trend, badges (First Guess, Hot Start, On Fire, Unstoppable, Centurion, Sharp Eye), and recent 20 predictions. Stats page at `/discover/stats` with hero stats, badges, category accuracy bars, trend chart, and prediction history.
- ✅ **Shareable Prediction Cards**: `GET /api/og/prediction` renders HTML card with OG meta tags for social sharing. Shows correct/incorrect badge, actual probability, market name, Bain Luck branding. "Share result" button on revealed guess cards.
- ✅ **Daily Challenge Card**: Pinned at top of Discover feed — "Make 5 predictions today" with circular progress ring. Trophy badge on completion. Resets daily via localStorage.
- ✅ **Build Your Feed Onboarding**: First-time visitors see a modal with 12 category tiles to pick interests. Sets initial category filter. "Show me everything" option. Persists via localStorage.
- ✅ **Animated Probability Counter**: Probabilities count up from 0 on scroll into view. 800ms ease-out cubic via IntersectionObserver + requestAnimationFrame.
- ✅ **Resolution Card Component**: Purple "Market Resolved" card showing user's guess vs actual result. Ready for backend wiring (needs endpoint to find user's resolved predictions).
- ✅ **Discover Feed Enhancements (multi-day)**: Pexels API images for market cards (image_url on FuturesMarket), LLM hook descriptions via GPT-4o-mini (hook_description), category interleaving for diversity, staleness filtering (resolution_date past, ≥90% no movement), non-sports quota (20%), infinite scroll, category filter chips, trending badges, swipe gestures (mobile), market grouping (related markets collapsed into expandable cards), multi-column layout (1/2/3 cols responsive), time-context labels, movement indicators. Enrichment tasks run 2x daily via Celery beat.
- ✅ **Native Discover Tab**: DiscoverView.swift with category chips, adaptive grid, event/futures/guess cards. Added to iPhone tab bar + Mac sidebar. Guess cards POST to /api/predictions.

## April 29, 2026

- ✅ **Manus sweep fixes (9 modules, April 30)**: Projected final score hidden for completed games + negative values (was showing "3 – -1" from resolved spread/total markets). Chart stale tails fixed — `completed_at` now caps the domain instead of extending it (was adding 42-76 min of flat line). API outage during sweep was transient (dyno restart). NHL 0-0 scores were transient (API outage). 11/15 league page failures were transient. NBA grid missing division column is correct (playoff season, divisions resolved). Monotonicity, cross-game contamination, mobile rendering, and event matching all passed clean.
- ✅ **`/discover` — Social prediction market feed prototype**: New mobile-first scrollable feed at `/discover`. Cards show hero visuals (team logos on gradients for events, giant probability on category-colored gradients for futures), probability bars, trend indicators, LLM headlines, and social actions (Like + Share + Dismiss). Category-specific gradient backgrounds for non-sports content (purple economics, pink culture, cyan tech). Filters out resolved markets (≥95% leader) and stale events (>12h). Replaces Search in desktop nav; mobile gets 4 tabs (Feed | Discover | Search | My Stuff).
- ✅ **Parity Sweep #3 (Charts, Props, Awards, Markets, Grid)**: Chart whitespace fixed — uses last ESPN/odds data point instead of `completedAt` (was 43 min late). Margin map PRE-GAME fix (removed unsigned spread fallback). Player props default to Points only with "All stats" toggle. Awards redesigned as compact player-grouped rows. Win probability markets filtered from Other Markets. Championship Grid blank screen fixed (initial loading state).
- ✅ **Polymarket game-level market decomposition**: Non-neg_risk Polymarket game events (e.g., "Magic vs. Pistons" with 40 sub-markets) were stored as 1 FuturesMarket row with all sub-markets flattened into outcomes. Player props, spreads, and O/U from Polymarket were invisible to the game-markets endpoint. Fix: each sub-market now creates its own FuturesMarket row with condition_id as external_id, Over/Under outcomes, and inherited event_id. The game-markets endpoint can now classify and display Polymarket player props alongside Kalshi.
- ✅ **espn_id persistence fix**: `espn_id` was set via ORM attribute assignment but silently lost when mixed with Core SQL updates on `win_probability_sources`. All completed events had `espn_id=null`, preventing box score fetch. Fixed by using Core SQL update for `espn_id`.
- ✅ **Player props graceful fallback**: Completed games without `box_score_data` now show probabilities ("pre" mode) instead of broken "0 so far" with all "—" thresholds. Threshold dedup added for same-source duplicates.
- ✅ **Market Maps mobile fix**: Stack margin/total columns vertically on mobile (`grid-cols-1 sm:grid-cols-2`). Title 18→15px, tile values 15→14px with text-overflow ellipsis.
- ✅ **Native Parity Sweep #2 (Market Maps, Player Props, Championship Path, Awards, Charts)**: Side-by-side audit of PHI 113 - BOS 97 across web and macOS. **Market Maps**: fixed PRE-GAME data bug (unsigned `spread` → signed `homeSpread`), taller/more vibrant density rail, added 2nd half margin and total maps, broadened half-map filters. **Player Props**: 2-column stat layout within each card (STEALS+REBOUNDS side by side), matching web. **Championship Path**: rich team cards with logos, records, conference seeds, thicker bars, "✓ clinched" indicators. **Awards**: grouped by team in mini card grid (was flat mixed list), no cap on count (both web and native). **Charts**: reduced post-completion whitespace (120s→30s buffer), web Score Differential x-axis now matches Win Probability (font size, interval logic). **Hero**: divergence warnings now show specific team/source/gap wording, tier tag labels (tier:1→"Major"), EI tag support.
- ✅ **0f-7: Kalshi win probability spikes**: Root cause — Kalshi creates separate binary markets per team ("Celtics win?" and "76ers win?") for the same game. Both linked to same Event, causing oscillating writes to `win_probability_sources["kalshi"]`. Fix: deduplicate by `(event_id, source)` before writing snapshots — one market per event per source. 327 tests pass.
- ✅ **Mac app UX fixes**: Feed card click targets (`.contentShape(Rectangle())`), league pill grey box styling, content max width 900→1200 on macOS, Score Differential period label normalization (strips clock prefixes), Other Markets filtering (exclude spread/total/moneyline redundant with Market Maps), novelty market probability floor (5%).

## April 28, 2026

- ✅ **iOS/macOS Event Detail Parity Sweep**: Full parity with web event detail page. **Web removals**: Game Segments, Period Markets, and Blowout Warning removed (market maps replace period data). **iOS/macOS hero enrichments**: tag chips (importance/signal/stakes/narrative), trend indicator ("+5% since open"), projected final score, source divergence warnings (sportsbook spread + PM vs book), stakes context label. **5 new native components**: MarketMapView (density curves via Swift Charts for margin + total maps), BookmakerTableView (individual sportsbook odds with consensus row), SeriesProbabilityView (negative binomial model with win dots + probability bar), SpecialEventMarketsView (auto-categorized game props/novelty/MVP in 2-column grid), RelatedByTagView ("More Basketball" cross-content discovery). **Also**: re-enabled bookmaker table in chart section, added league page link to championship grid, added `tags` param to feed API. Model updates: StandingsContext.stakes, ESPNData.seriesHomeWins/awaySeriesWins, GameMarketsResponse.other/pace. 11 files changed, 1,047 insertions.
- ✅ **0s Phase 1: League page market sections**: New `GET /api/leagues/{sport_key}` endpoint returns all open futures for a league grouped by section (series, awards, playoff_props, season_stats, novelty). Frontend renders `LeagueMarketCard` components in a 3-column grid below the championship grid. Filters by `llm_sport_category` + Kalshi ticker prefix + market name patterns. Cross-source dedup via `canonical_market_key`. Skips championship/conference/division tiers (already on grid).
- ✅ **0f-8: Chart Y-axis mobile readability**: OddsChart Y-axis font 12→13px, fill darkened #6B7280→#4B5563, column width 42→44. X-axis font 11→12px.
- ✅ **0r-2: Golf dead category links**: TournamentCard default href changed from `/categories/golf/tournaments/{slug}` to `/sport/golf/{tour}/{slug}` with tour slug mapping (dp_world→dpworld, korn_ferry→kft).
- ✅ **FeedCard badge overflow fix**: Added `flex-wrap` to badge row + capped LIVE badge at 140px with truncation. Guards against period field containing date strings.
- ✅ **0p: Today's Games on league pages**: `/sport/[sport]/[league]` pages now show a "Today's Games" section above the championship grid. Fetches from the feed API filtered by sport key (e.g., `basketball_nba`), events only (no futures), limit 30. Sorted: live → scheduled → completed, with feed score as tiebreaker. Uses existing `FeedCard` component in a 2-column responsive grid. Section header adapts ("Live & Today's Games" vs "Today's Games"). Hidden when no events. Empty state suppressed when events exist but grid is absent.
- ✅ **MS-1: Small text audit**: Bumped sub-11px text to readable sizes across FeedCard (opened context, resolve dates, source counts, movement), ChampionshipGrid (records, probabilities, headers, legend, trend indicators 7→9px), OddsChart (team labels 9→11px), and event detail page.
- ✅ **MS-3: Team logo fallback**: Event detail team logos now fall back to ESPN CDN lookup when `team_data.logo_large` is missing, with `onError` handler showing initials if image fails to load.
- ✅ **MS-7: Grid scroll hint**: Championship grid changed from `overflow-hidden` to `overflow-x-auto` with right-edge gradient fade on mobile.
- ✅ **MS-8: Chart y-axis readability**: OddsChart vertical team labels bumped from 9px to 11px with wider label column.
- ✅ **PREQ-7: N+1 query audit (PREQ sprint complete — 12/12)**: Fixed all 5 top Sentry N+1 issues (4,350+ events). Root cause: Celery tasks doing per-item DB queries in hot loops. Three batch-loading fixes: (1) ESPN sync team cache eliminates 40-60 individual `SELECT teams` per poll, (2) live PM poll batch-loads all outcomes upfront instead of per-market queries, (3) odds polling snapshot cache eliminates per-bookmaker×event `SELECT odds_snapshots`. API routes were already correct.
- ✅ **Score Differential chart labels**: Replaced horizontal "± Team leading" labels with vertical rotated team abbreviation + logo on the left side, matching Win Probability chart's layout. Chart height h-40→h-48. Added `homeTeamAbbrev`/`awayTeamAbbrev` props.
- ✅ **Doc cleanup**: CLAUDE.md test count updated (3,331), L4 matching status updated to verified. completed-features.md date ordering fixed. MEMORY.md trimmed from 237→97 lines (was truncating). Backlog: added PREQ-7 + hockey monitoring items.

## April 27, 2026

- ✅ **Polymarket stale pricing fix**: Two-layer defense against misleading Polymarket prices during blowouts: (1) skip outcomes with zero trading activity (no lastTradePrice AND no bids), (2) use lastTradePrice instead of midpoint when bid/ask spread >15pp. Fixes "Polymarket has 76ers at 38% vs sportsbooks at 6%" divergence badge during 94-120 blowout.
- ✅ **Chart x-axis fix**: Shared time range syncs both Win Probability and Score Differential charts. "Since Start" now shows game time only (~2h), not 24h of pre-game data. Toggling one chart toggles both.
- ✅ **Period marker dedup**: "Q1" no longer appears 3 times. Start vs end of period distinguished: Q1 (start) vs /Q1 (end). Same labels on both charts.
- ✅ **MS-2: Cookie banner above nav**: Consent banner now sits above the mobile bottom tab bar instead of overlapping it.
- ✅ **MS-5: Rain dedup by city**: Monthly rain section deduplicates by city name (was showing NYC 8 times). Keeps latest resolution date per city.
- ✅ **MS-6: Tornado chronological sort**: Tornado markets sorted by resolution date instead of probability. Months now appear in order.
- ✅ **Game-markets linked query fix**: Removed ±18h time window from linked query that was filtering out game totals/spreads (Kalshi's commence_time is resolution date, not game date). Time window stays on fallback query only.

## April 26, 2026

- ✅ **iOS-GD3 fix: Post-final win prob drift**: Completed events now exclude Kalshi/Polymarket from aggregate probability — their stale ~50% prices were dragging resolved 100% sources toward 50%.
- ✅ **Linking 1a: Kalshi time window 48h→7d**: Source-specific matching windows. Kalshi gets 7 days (commence_time is resolution date, not game date). Expected +8-12% link rate for basketball and hockey.
- ✅ **iOS Game Detail triage**: 14 items added to backlog from BOS @ BAL review.
- ✅ **iOS-GD1: EI badge reverted** — Shows for all games (needs label, not hiding). Reverted after initially hiding for completed games.
- ✅ **iOS-GD2: Mute team records** — Reduced to 10pt tertiary text so records don't merge with scores
- ✅ **iOS-GD5: Clean chart period indicators** — Light gridlines (0.5pt) + small floating chips (8pt, ultraThinMaterial) replacing cramped alternating label strip
- ✅ **iOS-GD6: Remove dead sources row** — Removed non-functional "BainLuck — Sportsbooks Sources ⌄" below chart
- ✅ **iOS-GD7: Fix x-axis tick distribution** — Uses `desiredCount: 5` for cleaner spacing
- ✅ **iOS-GD8: Player prop headshots** — Already implemented via AsyncImage + backend all-roster lookup
- ✅ **iOS-GD14: State-aware Game Info footer** — Scheduled: "Today 9:05 AM", Live: "Started 9:05 AM", Final: "Final · Apr 25, 9:05 AM"

## April 25, 2026

- ✅ **PREQ-2: API client timeout**: 15s AbortController on all `apiFetch()` calls. Prevents infinite white-screen hangs.
- ✅ **PREQ-3: Cache-Control headers**: Feed 10s, playoffs/golf/weather/economics 60s, sports 120s, history 30s. Back-navigation now instant.
- ✅ **PREQ-4: Connection pool tuning**: pool_size 10→20, max_overflow 15→20. Prevents pool exhaustion under concurrent load.
- ✅ **PREQ-5: SWR interval tuning**: My Stuff 15s→60s, grouped feed 60s→120s. Reduces unnecessary API polling.
- ✅ **PREQ-6: Redis feed caching**: Anonymous feed requests cached in Redis with 15s TTL. Authenticated users bypass cache. Redis failures silently fall through to DB.
- ✅ **PREQ-8: Dynamic imports**: Already implemented — OddsChart, ScoreDifferentialChart, BookmakerTable all use `next/dynamic`. No additional work needed.
- ✅ **PREQ-9: Image optimization**: Investigated — all `<img>` tags are tiny team logos (12-44px) already sized correctly. Next.js `<Image>` adds overhead for images this small. No changes needed.
- ✅ **PREQ-10: Health endpoint**: `/health/ready` now checks Redis connectivity and reports last poll timestamps per source.
- ✅ **PREQ-11: Source degradation**: Feed endpoint wraps event/futures/golf scoring in try/except — partial feed returned on source failure instead of 500.
- ✅ **PREQ-12: Sentry cleanup**: `before_send` filter drops WorkerLost, TimeLimitExceeded, and transient Redis ConnectionError noise.

## April 24, 2026

- ✅ **Link rate dashboard fix**: Admin dashboard now shows open-market-only link rates instead of all-time (which included 50K+ resolved/closed markets in the denominator, making the metric useless). Backend already calculated both — frontend was just reading the wrong field.
- ✅ **Design system doc**: Added `docs/design-system.md` — comprehensive visual design reference extracted by Claude Design (colors, typography, motion, voice, component specs). Linked in CLAUDE.md.
- ✅ **Admin dashboard improvements**: (1) Unclassified markets now show regex-guessed category tags (game prop, esports, matchup, etc.). (2) "Copy backlog prompt" buttons on both Data Quality and Grid Health cards — generates a structured prompt with findings ready to paste into Claude Code. (3) Grid Health refresh now shows timestamp and pulses green while auditing.

## April 22, 2026 (Evening — iOS Parity Session)

**iOS Event Detail Overhaul (~30 commits):**
- ✅ Feed crash fixes: WinProbSource/ESPNData decode bare numbers, feed skips malformed items, grouped-feed route order fix
- ✅ Feed card polish: bigger live scores, movement arrows, glowing probability bar
- ✅ Chart timing: `completed_at` clipping on both OddsChart and ScoreDiffChart
- ✅ Period markers on win prob chart (from win_prob_history game_state data)
- ✅ Period markers on score diff chart
- ✅ ChampionshipPathView: new component calling /team-progression endpoint (Make Playoffs → Division → Conf → Championship with progress bars)
- ✅ PlayerPropsCardView: new component calling /game-markets endpoint (per-player cards with initials, stat categories, threshold ladders with probability bars)
- ✅ Hero cleanup: removed divergence badge, tags section, baseball "0:00" clock, refresh countdown
- ✅ LineMovement removed (dead code, -391 lines)
- ✅ Related futures crash fix (gamePeriod Int→String)
- ✅ Championship card filter (display_category, not just tier)
- ✅ Trade watch dedup by player name per team
- ✅ Game market labels include market context
- ✅ Awards limit increased to 12
- ✅ Clean error messages (no more raw HTML dumps)
- ✅ Auto-refresh preserves data on fetch failure (sections no longer vanish)
- ✅ Removed duplicate game props from Bigger Picture (PlayerPropsCardView is primary)
- ✅ Score diff x-axis alignment via shared forcedDomain from EventDetailView
- ✅ Feed limit 200→50 to prevent timeouts
- ✅ ESPN score=0 bug fix (score parsing used `if score:` which skips int(0))

**Chart Timing Quality (Backend + Web):**
- ✅ Prediction market snapshot bleed fix (smartEndTime excludes kalshi/polymarket/aggregate_line)
- ✅ `completed_at` column on Event model, populated from 4 authoritative sources
- ✅ Backfill: 592 historical events got completed_at
- ✅ Backend PM matching Phase 2 skips completed events
- ✅ Timing audit script + Manus prompt
- ✅ Results: NBA 4.32x→1.07x, MLB 3.31x→1.00x

**Web Fixes:**
- ✅ Search page: removed duplicate search bar, better category emoji and labels
- ✅ Category browser: formatCategoryName replaces underscores, handles acronyms

## April 22, 2026

**Event Detail Below-the-Fold Redesign (Steps 1-5 of 6):**
- ✅ TotalPointsSpectrum rewrite — projection bars (pre-game/current/pace/actual) + threshold probability ladder. Replaces broken 172-threshold color bar with overlapping labels.
- ✅ PlayerPropsDashboard — per-player stat cards with "ladder" (multi-threshold) and "line" (single O/U) shapes. Three game states (pre/live/done). Box score integration for live actuals. Team filter toggle. Cross-source badges. Replaces broken PlayerPropsGrid.
- ✅ GameSegments — 1st/2nd half cards with total points O/U bar + team-colored leader split bar. Renders period_markets data that was previously unused.
- ✅ Bigger Picture redesign — two-column team cards with championship path probability bars, player awards grid. Eliminates duplicate team records. Trade Watch moved below with "speculative" disclaimer.
- ✅ SpecialEventMarkets — auto-categorized "other" markets (Game Props, Novelty, MVP, Player Performance). Sport-agnostic rendering for Super Bowl / Masters / World Cup without hardcoding.
- Design source: `handoffs/Event Detail Below-the-Fold.html` (Claude Design prototype)

**Mystery Shopper Critical Fixes (M1-M4):**
- ✅ M1+M3: DataGolf markets now close when tournaments complete (3 layers: schedule scan, completion detection, stale market cleanup). Golf landing page filters completed tournaments by schedule_status. Leaderboard reports "completed" instead of "live" when done.
- ✅ M2: ErrorBoundary + 12s loading timeout on event detail page (prevents infinite mobile spinner)
- ✅ M4: Player props with over_probability >95% or <5% filtered (boring thresholds hidden)

**Event Detail Polish (live game review):**
- ✅ "Threshold probabilities" → "Projected combined scoring" (clearer label)
- ✅ Removed duplicate "52 props across 20 players" subtitle + PLAYERS/TOTAL PROPS summary cards
- ✅ Player prop cards now use team colors (were all gray due to broken team detection)
- ✅ Special event outcome dedup operator precedence fix (was preventing dedup from working)
- ✅ Hide old "Game Markets" / "Upcoming Games" section dividers when PlayerPropsDashboard handles data above
- ✅ Score Differential: period marker label overlap fix — increased spacing to 5%, capped at 12 labels, reduced font weight
- ✅ MLB headshot fallback: ILIKE search when exact team name match fails

**Sentry Error Budget Fix:**
- ✅ Quota warning was logged as CRITICAL (2,716 events/period) → downgraded to WARNING
- ✅ DataGolf market creation failures for non-PGA tours (1,209 events) → WARNING
- ✅ DataGolf tour-level errors for kft/opp (1,138 events) → WARNING
- ✅ Estimated savings: ~5,000 error events/month (entire free tier budget was being consumed in 2 days)

**Cross-Event Contamination Fix:**
- ✅ Game markets query now requires BOTH team names to match (was OR, letting "Minnesota vs New York M" leak onto NYY vs BOS)

**URL Architecture: /sport/[sport]/[league] as canonical pattern:**
- ✅ All user-facing links migrated from `/playoffs/*` to `/sport/[sport]/[league]` paths
- ✅ Footer, LeagueChips, TeamPlayoffCard, event detail Championship Grid link — all updated
- ✅ `/playoffs` pages preserved in codebase (not deleted, not linked to)

**Player Props + Special Events Polish:**
- ✅ Team filter fix: detection now checks all team name words (was only checking last word — "Sox" never matched "Boston")
- ✅ Unknown-team players show in Home/Away filter views (were disappearing)
- ✅ Special event outcome dedup: same-name outcomes from multiple Kalshi markets merged (6 rows → 3)

**Cross-Sport Contamination Fix:**
- ✅ Game markets endpoint now filters by `llm_sport_category` — MLB games no longer show NBA three-pointers, double-doubles, or MLS markets when city names overlap (Cleveland, Houston).
- ✅ Fixed `period_totals` → `period_markets` typo (was causing 500 on all game-markets requests)

**Doc Cleanup:**
- ✅ Backlog: removed ~50 lines shipped/duplicate content, promoted M1-M4 to Tier 1, added 0f design redesign item
- ✅ CLAUDE.md: test counts updated (3,315), project structure corrected
- ✅ PRD: test count updated, MoneyPuck references removed (stub deleted), DataGolf + StatPal added to services table, "fangraphs" → "mlb" source key fix
- ✅ 7 new tests for tournament completion detection (3,315 total)

**Chart Timing Quality (0t-1)** — charts were extending 3-11 hours past game end:
- ✅ Root cause: Kalshi/Polymarket `win_prob_snapshots` kept being written hours after game end by hourly PM matching task. `smartEndTime` picked them up and stretched charts.
- ✅ Frontend: `smartEndTime` now excludes kalshi, polymarket, and aggregate_line — only uses ESPN + stat_model as game-end signals
- ✅ Frontend: When `completed_at` is available from the API, uses it as the authoritative end boundary (no inference needed)
- ✅ Backend: PM matching Phase 2 no longer writes snapshots for completed/closed events
- ✅ Backend: New `completed_at` column on Event model — set from ESPN (post/final), Odds API (completed flag), StatPal (end_time), staleness detection
- ✅ Backend: History API returns `completed_at` and `commence_time` for frontend chart boundary
- ✅ Backend: Backfill endpoint populated 592 historical events (116 from ESPN, 476 from stat_model)
- ✅ Results: NBA duration 4.32x→1.07x, MLB 3.31x→1.00x, MaxGap 181m→2.3m, findings 113→63

**Event Timing Audit Tooling:**
- ✅ New script: `backend/scripts/audit_event_timing.py` — sweeps completed events, measures start/end offset, gaps, chart alignment, source coverage. Aggregates by sport and source coverage. Supports `--save`/`--compare`/`--json`.
- ✅ New Manus prompt: `Manus/prompts/chart_timing_audit.md` — visual spot-check of 8 completed events across sports
- ✅ Registered `chart_timing` module in `manus_health_suite.py`

## April 19-20, 2026

**Weather Page** (`/weather`) — new top-level page with 6 sections, all live data:
- ✅ Hero rotator (top 5 featured weather markets, auto-advancing)
- ✅ Global temperature map — 49 cities, collision-resolved pins, histogram distribution panel
- ✅ Cross-source comparison — 9 cities with both Kalshi + Polymarket data
- ✅ NYC 7-day rain forecast (Kalshi daily markets)
- ✅ Monthly rainfall for 10 US cities with 24h movement deltas
- ✅ Natural events tracker — hurricane season strip, earthquake/tornado market lists
- ✅ Climate dashboard — 2026/2030/2050 horizon columns
- ✅ Wild cards — rare event probabilities (supervolcano, solar storms, etc.)
- ✅ Continent outline SVGs on abstract world map
- ✅ Backend: 6 new API endpoints at `/api/weather/*` serving real data from 521 weather markets
- ✅ Frontend: SWR hooks with static fallback, responsive design, hover tooltips on histogram bars
- ✅ "Weather" nav link added to DesktopNav
- ✅ GA4 analytics: `weather` page type registered

**Polymarket Neg-Risk Probability Fix** — root cause of grid health failures:
- ✅ Polymarket poller now uses bid/ask midpoint fallback when `outcomePrices` is empty (neg-risk markets)
- ✅ All Polymarket championship/conference futures outcomes now have correct probabilities
- ✅ NBA grid health: 0 → 97/100
- ✅ NHL grid health: 97 → 100/100
- ✅ Overall grid health: 62 → ~95/100

**God Function Refactoring — 5 functions (Item 6):**
- ✅ `_score_events` (feed.py, 466→~300 lines) → `utils/feed_scoring.py` — `compute_base_score()`, `format_event_data()`, `TAG_BOOSTS`, 15 tests
- ✅ `_sync_espn_live_events` (espn_sync.py, 897 lines) → 5 module-level helpers: `_espn_names_match_any()`, `get_event_name_variations()`, `get_espn_name_variants()`, `espn_team_matches()`, 16 tests
- ✅ `get_playoff_grid` (playoffs.py, 862→~780 lines) → `utils/playoff_grid.py` — `normalize_column_sums()`, `compute_movers()`, `sort_teams_by_championship()`, `is_valid_grid_outcome()`, 25 tests
- ✅ `get_related_futures` (events.py, 783→~750 lines) → `utils/related_futures.py` — `dedup_by_merge_group()`, `build_futures_entry()`, 11 tests
- ✅ `_poll_all_odds` (odds_polling.py, 638 lines) → `utils/polling_config.py` — `determine_api_params()`, `compute_effective_interval()`, 15 tests
- Total: 82 new tests, 4 new utility modules, all 5 highest-priority god functions addressed

**Sentry Error Fixes (5 issues, ~3,386 events eliminated):**
- ✅ BAINLUCK-JK: Task pool exhaustion — added pool_size=3, max_overflow=5, pool_recycle=1800 to `base.py`
- ✅ BAINLUCK-JG: `Event.sport_key` → `Sport.key` join (2,038 events)
- ✅ BAINLUCK-JH: `_sql_update` UnboundLocalError — moved to top-level import (1,298 events)
- ✅ BAINLUCK-JT: `Event.espn_event_id` → `Event.espn_id` (27 events)
- ✅ TooManyConnections: WrestleMania code removed entirely

**WrestleMania Removal (-3,686 lines):**
- ✅ Deleted: task, routes, models, scoring util, Polymarket service, frontend page + 11 components
- ✅ Removed from beat schedule, route imports, main.py router mount
- ✅ Patterns archived to `docs/archive/wrestlemania-reference.md`
- ✅ DB tables + Alembic migration preserved

**Observability Tool Access:**
- ✅ Heroku CLI installed and authenticated — prod logs, DB queries, dyno status
- ✅ Sentry API token configured — programmatic issue triage via curl
- ✅ GitHub CLI installed and authenticated — CI status, workflow runs
- ✅ Session startup health check added to CLAUDE.md (Sentry + Heroku + CI scan)

**Admin Auth Security Fix:**
- ✅ `_check_admin_secret()` returned True when `ADMIN_SECRET` unset — now returns False

**WrestleMania Win Probability Fix:**
- ✅ Leaderboard was using stale seed probabilities instead of latest odds snapshots
- ✅ Added 99.9% cap (never show false 100%). Frontend: "0%" for truly-zero players

**Grid Health Fixes (6 matching improvements):**
- ✅ Championship probability normalization (NHL 53.2% → 100%)
- ✅ "Postseason" patterns added to all sport stage classifiers + league configs
- ✅ Kalshi ticker prefixes (KXNBA/KXNHL/KXMLB) for market discovery
- ✅ Stanley Cup qualifier pre-check (prevents championship misclassification)
- ✅ MLB division rule ordering (moved above pennant, removed overly broad catch-all)
- ✅ Playoff series matchup markets added to backlog (Item 5)

**API Client Base Class (Item 4):**
- ✅ `BaseAPIClient` in `services/base_api.py` — shared httpx.AsyncClient setup + close()
- ✅ Applied to 5 services: OddsAPI, Kalshi, DataGolf, MLB, StatPal
- ✅ ESPN (lazy init) and Polymarket (dual clients) left as-is — non-standard patterns

**Name Normalization Consolidation (Item 3):**
- ✅ 11 scattered normalization functions → 1 canonical module (`utils/name_normalization.py`)
- ✅ Added: `strip_diacritics()`, `normalize_team_name()`, `match_key()`, `clean_slug()`
- ✅ Replaced duplicates in 10 files: playoffs, golf, oscars, oscars_pool, march_madness, roster_sync, team_linking, datagolf_api, mlb_sync
- ✅ Net -20 lines (114 added, 134 removed). All 3,225 tests pass.

**Player Prop Headshots (R1):**
- ✅ MLB roster sync now stores rich dicts with headshot URLs (was plain name strings — only ESPN-synced sports had headshots)
- ✅ `mlb_api.get_team_roster()` returns player dicts with MLB Stats API headshot CDN URLs
- ✅ NBA/NHL/NFL headshots already worked (ESPN sync path). All 4 major sports now covered.
- Root cause: MLB used a separate sync path (MLB Stats API) that stored `["Mike Trout"]` instead of `[{"name": "Mike Trout", "headshot": "https://..."}]`. The `player_metadata` builder in `events.py` only matched dict entries.

**Grid Matching Fixes:**
- ✅ Play-in tournament markets excluded from grid (was contaminating conference column with "Eastern Conference Play-In" at 3.5% vs real conference champion at 42%)
- ✅ Audit disagreement threshold: 15pp→25pp critical, 15pp warning (genuine Kalshi vs Polymarket pricing differences no longer tank health score)

**Admin Dashboard Fixes:**
- ✅ Daily burn chart: bar heights now use official Odds API counter, task proportions scaled to match (no more retroactive shrinking)
- ✅ EOM quota forecast: excludes today's partial day, uses trailing 2 complete days
- ✅ Score fetching skipped for ESPN-mapped sports (NBA/NHL/MLB/NFL) when all events have ESPN match — saves ~60-70% of score API cost

**Game Prop → Event Linking (Item 1C)** — 12 commits, 1,784+ markets newly linked:
- ✅ Ticker-derived team names for game props ("WSH Capitals" → "Capitals" from ticker abbreviation map)
- ✅ `_expand_team_search_terms()` for ILIKE pattern expansion (mascot extraction + city abbreviation lookup)
- ✅ `_SPORT_ABBREV_SUFFIX` derived programmatically from all ~150 ticker prefixes (was 7 hardcoded)
- ✅ `_TICKER_DATE_RE` fixed for digit-containing prefixes (KXNBA2D, KXNBA3PT)
- ✅ `sport_id` propagation on all 5 linking paths via `_set_market_sport_fields()`
- ✅ `llm_sport_category` correction from ticker prefix on link + Phase 1.5 backfill (fixes MLB tagged "basketball")
- ✅ " - More Markets" Polymarket suffix stripping
- ✅ "Game N:" playoff series prefix stripping
- ✅ City abbreviation map (`_CITY_ABBREV_TO_NAME`, 65 entries)
- ✅ Phase 2 deadlock fix (per-market commit + rollback on deadlock detection)
- ✅ Matching frequency 4h → 1h, limit 200 → 500
- ✅ `POST /admin/prediction-markets/fix-sport-categories` — bulk category correction from ticker
- ✅ `GET /admin/prediction-markets/link-rate` — per-sport link rate health endpoint
- ✅ Admin dashboard: Game Market Link Rate card with per-source/per-sport progress bars
- ✅ 28 new tests (324 total prediction market matching, 3,149 total)

**Results:** Kalshi tennis 52% → 96%, hockey 27% → 52%, baseball 69% → 77%. Dashboard tracks all sports.

## April 17-19, 2026

**WrestleMania 42 prediction game** (`/wrestlemania`) — throwaway, remove after April 20:
- ✅ 13-match card, Polymarket live odds, $1M bankroll, leaderboard, LLM commentary, spoiler guard, inline admin

**Infrastructure & data quality:**
- ✅ Win prob snapshot dedup fix — inning/period change detection
- ✅ Golf: Monte-Carlo tennis "Masters" leak, Polymarket "Yes" labels, Augusta ghost tournament
- ✅ Player prop headshot name matching, Alembic multi-head fix
- ✅ Quota optimization: score API rate-limit, MLB US-only, AFL 10min floor
- ✅ Admin dashboard: Game State Indicators by Sport chart

**Testing (110 new tests):**
- ✅ Item 4: API contract tests (27 tests) + integration conftest
- ✅ Item 9: External API fixture tests — Kalshi, Odds API, ESPN, DataGolf (77 tests)

<details>
<summary>Shipped features (click to expand)</summary>

- ✅ Excitement Index (EI) feature complete and deployed (migrated from Pulse)
- ✅ Kalshi prediction market integration
- ✅ Futures UI improvements (sportsbooks, start times, categorization)
- ✅ LLM infrastructure (OpenAI GPT-4o-mini for smart categorization)
- ✅ EI Hall of Fame page (`/ei/hall-of-fame`, `/pulse` redirects)
- ✅ Pinned Events & Futures (localStorage-based tracking)
- ✅ Futures categorization hardened (0 uncategorized markets)
- ✅ EI distribution tuning (normalization constants, percentile scoring, component tooltips)
- ✅ ~~TV/Party mode v1~~ (shipped for Super Bowl LX, removed post-event)
- ✅ TV Mode v2 design + interactive prototype (cascaded density hierarchy, multi-source charts, EI breathing animation, ambient futures rotation, iOS v2 features documented)
- ✅ Sentry error tracking (FastAPI + Celery worker, controlled by SENTRY_DSN env var)
- ✅ Multi-source win probability infrastructure (generic `win_prob_snapshots` table, source config, N-source chart)
- ✅ Bain Luck statistical win probability model (nflfastR-inspired, NFL/NCAAF/NBA/NCAAB/WNCAAB/NHL)
- ✅ Win probability source detail page (`/events/[id]/models`) with methodology + attribution
- ✅ ESPN team name matching normalization (unicode/accent handling for college teams)
- ✅ Status-based probability display (opening odds for finished games, current odds for live, with stale bookmaker filtering)
- ✅ Stale bookmaker filter extracted to `app/utils/odds_filtering.py` with 14 regression tests (including commence_time sanity check)
- ✅ Opening odds now stores last pregame consensus (cross-bookmaker average, continuously updated while scheduled)
- ✅ Snapshot data retention Phase 1: lossless collapsing of consecutive identical rows across `odds_snapshots`, `win_prob_snapshots`, `futures_odds_snapshots` + write-time dedup for `win_prob_snapshots`. Phase 2: rewritten to pure SQL using PostgreSQL window functions (LAG, SUM, CTEs) for constant memory — fixes Heroku worker OOM (R14).
- ✅ Refactored `tasks.py` (2,970 lines) into `tasks/` package with 18+ modules: `__init__.py`, `config.py`, `base.py`, `snapshots.py`, `redis_state.py`, `odds_polling.py`, `excitement_index.py`, `pulse.py`, `futures.py`, `kalshi.py`, `espn_sync.py`, `sports.py`, `retention.py`, `roster_sync.py`, `team_linking.py`, `prediction_market_matching.py`, `matching_audit.py`, `team_identity_backfill.py`, `mlb_sync.py`, `statpal_sync.py`. All task names pinned with `name=` params for backward compatibility. Celery heartbeat + health endpoint added.
- ✅ Super Bowl dead code cleanup: removed `contest.py`, `superbowl.py`, `youtube_api.py`, `CommercialLeaderboard.tsx`, and related routes/types (~7K+ lines)
- ✅ Related futures Phases 1-3: team linking infrastructure (`FuturesOutcome.team_id` FK, `FuturesMarket.market_tier`, backfill task), `GET /api/events/{id}/related-futures` endpoint with hybrid matching (name ILIKE + team_id, triple sport filter), frontend "Bigger Picture" section with team colors/logos/probability bars
- ✅ SportsDataIO integration: API client, roster sync task (daily at 7:00 AM UTC), `Team.roster_players` JSONB column for player name matching in related futures. NBA 26/30, NHL 20/32 teams synced. **Later:** `sportsdata_api.py` deleted, roster sync migrated to ESPN + MLB Stats API.
- ✅ Test coverage for core algorithms: 1700+ backend (pytest items) + 117+ frontend = 1800+ total tests. Pure-function testing strategy covers EI (85+), Highlights (126, incl. Level 2 time-series, event importance), odds math (35+35), futures categorization (116), win probability (67), ESPN API parsing (63, incl. season type, injury/news parsing, team name match scoring), team linking (97), LLM classification (60), prediction market matching (291), odds polling helpers (27), win prob sources (24), task wiring (21), stale bookmaker filter (14), snapshot collapse (13), retention SQL (19), redis state (13), onboarding/preferences (31), MLB Stats API (33), matching audit (22), line movement (27). See `docs/test-coverage-analysis.md` for full analysis and prioritized improvement recommendations.
- ✅ Moved `_create_or_update_win_prob_snapshot` to `tasks/snapshots.py` shared module (was in `odds_polling.py`, imported by `espn_sync.py`)
- ✅ Polymarket integration Phase 1: API client (`polymarket_api.py`), polling task (`tasks/polymarket.py`) with streaming pagination + batched commits (50 events/batch), 160+ tag-to-category mapping with fallback to rules + league detection, outcome name extraction, page cap monitoring. 69 tests covering tag mapping, name extraction, API parsing.
- ✅ Auth & Personalization Phase 1 (shipped): Google Sign-In on Safari + Chrome via GIS + backend custom token fallback, backend auth middleware, pin sync, frontend auth context + sign-in UI.
- ✅ Auth & Personalization Phase 2 (shipped): 5-step onboarding flow (`/onboarding`) — location, follow teams, alma maters, sports+beyond (20 categories incl. politics/entertainment/crypto), rivals. Team search falls back to events table and auto-creates Team records for college teams. Inline favorites CRUD on preferences page. 31+ tests.
- ✅ Auth & Personalization Phase 3 (shipped): Personalized feed scoring with team multipliers (local 3.5×, alma_mater 2.5×, followed 2.0×), rival multipliers (live losses, blown leads), sport affinity weighting. Personalization badges ("Your team", "Local", "Alma mater", "Rival losing"). Unified interestingness feed combining events + futures on homepage.
- ✅ Unified feed: Homepage redesigned from separate sections (Highlights, Live, Upcoming) to ranked feed with visual sections (Live Now, Just Happened, Upcoming, Top Markets). Feed items include events and futures, with personalization overlay for authenticated users. Completed events surface with EI-based scoring boost.
- ✅ Prediction market → event matching: Two-pass strategy (targeted Kalshi ticker scan + general scan) links game-level Kalshi/Polymarket markets to Events for win probability trend lines. Live game price polling every 2 min via `poll_live_prediction_markets` (targeted — only fetches prices for linked live-event markets from Kalshi/Polymarket APIs). Ticker abbreviation parsing (`extract_teams_from_ticker`) for generic-named Kalshi markets. 223 tests covering ticker detection, abbreviation parsing, name building, false positive prevention, sport prefix mapping, ticker fallback, live poll wiring.
- ✅ ESPN matching resilience + wall-clock fallback: Multi-signal ESPN matching (ESPN ID → name → commence_time proximity) for both live and scheduled events. Wall-clock time estimation fallback for stat model when ESPN sync misses (common for college teams). Odds polling path relaxed to use fallback automatically. 16 new tests (67 total win probability tests).
- ✅ Task-level monitoring dashboard: `redis_state.py` metrics system tracks success/failure/duration/output per task in Redis. Dashboard at `GET /api/admin/celery/dashboard` with health classification. 7 key tasks instrumented via `_tracked_run()`.
- ✅ Polymarket price history backfill: `POST /api/admin/polymarket/backfill-history` fetches CLOB `/prices-history` for outcomes with sparse data, stores as `FuturesOddsSnapshot` rows. Resolves clob_token_ids via Gamma API event lookup.
- ✅ Ranking Level 2: Time-series aware scoring using `compute_time_series_metrics()` from odds_snapshots. Computes volatility (RMS), lead changes, recent momentum. Batch SQL query for live events. New labels: "Lead change", "Odds shifting fast", "Wild game". 21 new tests.
- ✅ MLB Stats API integration: Live baseball win probability from `statsapi.mlb.com` (no API key). Celery task polls every 2 min during live games. Source key `"mlb"` (formerly `"fangraphs"`, display name "MLB Model"). 33 tests.
- ✅ Divergence badge: Frontend detects when prediction market odds (Kalshi/Polymarket) diverge >5% from sportsbook consensus. Purple badge for >10% gap, blue for >5%.
- ✅ Non-sports tier promotion: Politics, Entertainment, Crypto promoted from tier 3 to tier 2 in frontend categorization.
- ✅ Safari auth 3-tier fallback: signInWithCredential (4s) → backend custom token + signInWithCustomToken (4s) → backend-only PyJWT session token. Prevents hanging on Safari ITP. Auth persistence switched to `browserLocalPersistence` (localStorage) from IndexedDB.
- ✅ Anonymous feed ranking overhaul: 4-tier league system (Tier 1 +20 pts, Tier 3 -5, Tier 4 -45 penalty), expanded to ~70 league entries, anonymous min_score raised to 30. Regular-season tennis/golf demoted to tier 4. Prevents minor league and obscure events from appearing.
- ✅ MoneyPuck stub removed: Was a placeholder source config entry for future NHL advanced stats — removed since no public API exists and it cluttered the source registry.
- ✅ Typeahead search: `SearchBar` component with 200ms debounce, keyboard navigation, integrated into layout header. Backend `GET /api/events/typeahead` endpoint. Mobile search icon + desktop inline bar.
- ✅ "Market Was Wrong" page: `GET /api/market-moves` endpoint + `/market-moves` frontend page showing post-game championship odds shifts.
- ✅ Kalshi ticker abbreviation parsing: `extract_teams_from_ticker()` parses team names from Kalshi game tickers (e.g., `KXNBAGAME-26FEB21DETCHI` → Pistons, Bulls). 100+ team abbreviations across NBA/NFL/NHL/MLB. Solves matching failure for generic-named markets like "Professional Basketball Game" when multiple games exist. 223 tests (up from 195).
- ✅ Onboarding UX fixes: sport labels on team search/chips, duplicate non-sports category fix, session token TTL 1hr→8hrs, same-name team clickability fix.
- ✅ Feed quality improvements: raised feed thresholds (event min_score 20, futures min_score 40, 60% diversity cap), non-sports tier promotion to tier 2 in frontend categorization.
- ✅ Prediction market mislink fixes: both-teams matching gate in `_score_candidates` prevents single-team fuzzy matches (e.g., "Pistons vs. Bulls" matching South Florida Bulls). Phase 1.5 stale link cleanup expanded to scan ALL linked markets (not just completed/closed). Polymarket matchup-named outcome fallback in `find_moneyline_outcome` (handles "Pistons vs. Bulls" as outcome name). 291 tests (up from 223).
- ✅ Sport category disambiguation for prediction market matching: `_score_candidates` uses `llm_sport_category` + `_SPORT_CATEGORY_TO_KEY_PREFIX` mapping for +5 scoring bonus. Prevents cross-sport mislinks.
- ✅ NFL roster sync fix: Phase 1 team sync builds `sd_abbrev → team_id` mapping used by Phase 2 roster sync, bridging ESPN/SportsDataIO abbreviation gap. ILIKE fallback for formatting diffs. MLB abbreviation map (30 teams) added to `SPORTSDATA_ABBREV_TO_NAME`.
- ✅ Stale bookmaker filter improvements: `filter_stale_bookmaker_snapshots` now uses `valid_until` (write-time dedup aware) via `_effective_time()`. Layer 2 recency filter for live events excludes bookmakers >10 min stale. 23 tests (14 existing + 9 new).
- ✅ Prediction market matching hardening: prop/spread outcome filter (`_is_prop_or_spread_outcome`) prevents O/U, spread, and player prop outcomes from being matched as moneyline. Orphaned `win_prob_snapshots` now deleted on unlink/re-link (Phase 1.5 + admin endpoint). NCAAB/NCAAF ticker fragment matching (`extract_ticker_fragments` + `_score_fragment_match`) disambiguates among multiple same-sport candidates. Time window tightened from ±6h to ±3h with ticker game date. 291 tests (up from 259).
- ✅ Related futures Phase 4 — LLM "Bigger Picture" summary: `generate_related_futures_summary()` in `llm.py` produces 2-3 sentence casual summary of championship/award implications using GPT-4o-mini. Cached in `LineMovementAnalysis` table with `analysis_type="related_futures"` (2h TTL, never expires for completed games). Frontend summary-first collapsed design in `RelatedFutures.tsx` with "See all N futures" toggle.
- ✅ Bigger Picture visual redesign (v3-v6): Tier-grouped layout with pattern-based `effectiveTier()` (6 tiers: championship hero → conference → award rows with ESPN headshots → division → game grid → stat prop cards with SVG gauges). PlayerHeadshot component (headshot URL → espn_id → Wikipedia → initials). Award dedup by player+award combo key across sources. NOT_CHAMPIONSHIP_PATTERNS (14 patterns) downgrades misclassified markets. Title Comparison prefers markets with "championship" in name. Backend `_is_stat_prop_market()` filter ensures game-specific stats (points, rebounds, double-doubles, etc.) only appear on correct event page via ±6h temporal proximity or event_id match. Frontend GameMarketsGrid team name verification catches cross-sport false positives.
- ✅ Oscars landing page: `/oscars` page with 24 award categories, cross-source odds aggregation (Polymarket + Kalshi), TMDB movie posters/headshots via Bearer token auth, ceremony countdown, gold-themed design. Backend `GET /api/oscars` with diacritics dedup, Kalshi 0.5 noise filter, probability normalization, boxing false positive filter, NegRisk trivia dedup.
- ✅ My Stuff / Preferences restructure: My Stuff (`/my-stuff`) rewritten from preferences editor to team-filtered feed (3 states: sign-in, onboarding, team feed via `my_teams_only` API param). Preferences editor moved to `/preferences`. Backend `my_teams_only` param on `/api/feed` with wider time windows (24h/7d), team filtering, no min score, no diversity enforcement. UserMenu "Preferences" links to `/preferences`.
- ✅ Event importance scoring + ESPN season type: `compute_highlight()` now reads `llm_importance` field with championship (+25), playoff (+15), exhibition (-20) weights. ESPN sync parses `season.type` (1=pre, 2=regular, 3=post) and writes to `llm_importance` for live + scheduled events (won't downgrade championship to playoff). Tennis Grand Slams and golf Majors promoted from tier 3 to tier 2. 17 new tests (126 highlights + 50 ESPN parsing).
- ✅ Roster sync SportsDataIO → ESPN migration: Deleted `sportsdata_api.py` (321 lines). `roster_sync.py` already uses ESPN + MLB Stats API. `SPORTSDATA_API_KEY` no longer needed.
- ✅ "Why Did the Line Move?" ESPN context enrichment: Added `get_event_context()` to `espn_api.py` (parses injuries + news from `/summary` endpoint). Enriched `build_llm_prompt()` with real injury reports, news headlines, and live game state (score/period/clock). 3-tier prompt system: (1) injuries/news available → explain causes using provided data, (2) game state only → describe score and odds factually without speculating, (3) no context → describe odds movement only. Prevents vague LLM hedging like "possibly due to key plays or scoring runs." Admin cache clear: `DELETE /api/admin/line-movement/cache/{event_id}`. 27 line movement tests + 8 ESPN parsing tests (85 total).
- ✅ Feed quality tightening: Regular-season tennis demoted from tier 3 to tier 4. Tier 3 penalty changed from 0 to -5. Tier 4 penalty increased from -15 to -45. Anonymous min_score raised from 25 to 30. ~70 league entries in LEAGUE_TIERS (up from 30+). Events without odds data skipped in feed.
- ✅ Personalized feed hard filters: "Nah" sports (0.0 affinity) hard-filtered — skipped entirely unless championship/playoff importance. "If it's wild" sports (0.1 affinity) require min_score 55 — live+close alone isn't enough.
- ✅ Homepage section redesign: "Starting Soon" and "More Games" merged into single "Upcoming" section. New "Just Happened" section for completed events (24h window) with EI-based scoring boost (+25 for EI ≥80, +15 for ≥60). Section order: Live Now → Just Happened → Upcoming → Top Markets.
- ✅ Finished event card redesign: Shows expected vs actual — opening odds probability bar (what was expected) + score with winner bolded (what happened) + date/time for freshness. No probability numbers on finished cards. Non-repetitive reason text: returns empty string for generic cases, only shows genuinely insightful context ("Won as 35% underdog", "Starting soon", line movement). Applies to all statuses — upcoming events no longer repeat odds in reason text, live events no longer repeat score.
- ✅ Bigger Picture v5-v6 redesign: Tier-grouped visual hierarchy with 6 tiers (championship → conference → awards → downgraded → game markets → stat props). Upcoming games grid, player stat gauges with headshots, tiered border styling. Title odds fix prevents "Make Playoffs" from displaying instead of championship odds.
- ✅ Feed endpoint performance optimization (8-16x improvement, 5-10s → 0.6-1.2s): Three changes in `feed.py`: (a) replaced 29 sequential per-category futures queries with single `ROW_NUMBER() OVER (PARTITION BY llm_sport_category)` query (~95% fewer DB round-trips), (b) parallelized personalization queries (favorites, preferences, pins) with `asyncio.gather()`, (c) cached canonical source counts with 5-min TTL. No product trade-offs — the per-category LIMIT 10 was already in place.
- ✅ Matching quality audits: Three daily LLM-based audits (canonical key dedup, prediction market→event links, related futures coverage) using GPT-4o-mini. Report-only Phase 1 — findings stored in `LineMovementAnalysis` with `pattern_category` and `suggested_rule` for systematic rule improvement. Pattern aggregation endpoint ranks recurring issues. 7 admin endpoints, 22 tests. ~$0.02/day cost.
- ✅ Canonical identity migration (4 phases): Phase 1: consolidated 10 sport key translation dicts from 7 files into `utils/sport_keys.py` with 7 accessor functions and backward-compatible re-exports. Phase 2: built `TeamIdentityService` with 5-step resolution cascade (source_id → source_name → fuzzy mapping → fuzzy teams → None), `team_identity_mapping` table, backfill task, 6 admin endpoints. Phase 3: StatPal schedule-first event creation with `statpal_fixture_id` primary lookup, `commence_time_source` tracking, nullable `Event.external_id`. Phase 4: integrated identity service into 6 consumer modules (espn_sync, statpal_sync, sports, roster_sync, prediction_market_matching, team_linking) as a supplement to existing fuzzy matching — tries indexed lookup first, falls back to existing logic, registers mapping on success.
- ✅ ESPN team logo matching fix: Replaced bidirectional substring matching in `_backfill_team_logos()` with token-overlap scoring (`_team_name_match_score()`, threshold `> 0.5`). Removed mascot-only names ("Buckeyes", "Bulldogs") from ESPN lookup dict. Guarded `espn_id` writes to exact/ID matches only. One-time cleanup task cleared 179 bad matches (637 checked, 458 valid). Admin endpoint `POST /api/admin/espn/cleanup-bad-matches`. 13 new tests.
- ✅ Event detail standings fix: StatPal returns `position` (team rank) as strings in `standings_data` JSONB. `_compute_standings_context()` compared these with `<=` against integers, crashing all event detail pages. Fixed with `int()` conversion + try/except. StatPal sync now stores numeric standings fields (draws, ties, points, goals, position) as `int` at write time.
- ✅ Line movement 3-tier prompt: Split `build_llm_prompt()` into 3 instruction tiers — injuries/news → explain causes, game state only → describe factually (no speculation), no context → describe movement only. Eliminates vague hedging ("possibly due to key plays or scoring runs"). Admin endpoint `DELETE /api/admin/line-movement/cache/{event_id}` clears stale cached explanations.
- ✅ Apple Sign-In: Firebase `signInWithPopup` with `OAuthProvider('apple.com')` — Firebase handles Apple OAuth through its own verified domain, no domain verification needed on `bainluck.com`. Backend `POST /api/auth/apple` endpoint with Apple JWKS verification, `GET /api/auth/status` dynamic provider list. Provider chooser dropdown (Google + Apple) in UserMenu and My Stuff sign-in prompt. Key gotchas solved: `browserPopupRedirectResolver` required in `initializeAuth` (Firebase v10), preload module to prevent popup blockers, read `currentUser` directly after popup for immediate state. 13 backend tests.
- ✅ Pulse → Excitement Index (EI) migration: Replaced proprietary Pulse metric (weighted components: heart rate, amplitude, arrhythmia, vitals, time weight, lead changes) with standard GEI formula: `EI_raw = (T_regulation / T_actual) × Σ|pᵢ - pᵢ₋₁|`. New algorithm in `utils/excitement_index.py` with multi-source 30s time bucket aggregation. DB columns renamed via Alembic (`raw_gei` → `raw_ei`, `gei_components` → `ei_metadata`, `gei_percentiles` → `ei_percentiles`). Frontend `EIBadge.tsx` replaces `PulseBadge.tsx`. Routes `/ei` and `/ei/hall-of-fame` with `/pulse` redirect. API serves both `"ei"` and `"pulse"` keys for backward compat. 80+ tests in `test_excitement_index.py`.
- ✅ Tiered discovery frequency: Per-sport Redis gating in `_discover_events()` based on `LEAGUE_TIERS` — tier 1 (NBA/NFL) every 15min, tier 2 (NCAAB/MMA) every 30min, tier 3 (Liga MX) every 2h, tier 4 (minor leagues) every 4h. Reuses `poll_all_odds` Redis pattern. Saves ~53% of discovery API calls (~1.9M billed requests/month). Mitigates Feb 2026 quota exhaustion.
- ✅ iOS App Phases 1-7 (Mar 2026): Native SwiftUI app — section-based feed, multi-source odds chart with period markers, event detail (chart, related futures, line movement, scoring plays), search, EI rankings, Apple + Google Sign-In, native onboarding, preferences, iPad-native sidebar layout, category pages, filter chips, swipe-to-pin, haptic feedback, Firebase Analytics, deep linking. 46 Swift files, 29 commits across 7 phases.
- ✅ Golf landing page: Bespoke category page at `/categories/golf` — cross-source tournament odds aggregation (Polymarket, Kalshi, Odds API), current event detection from odds movement, 24h biggest movers from snapshot history, sparkline charts, LPGA/TGL separation, non-golf false positive regex filter, StatPal PGA schedule enrichment. Post-launch fixes: `_clean_slug()` strips sponsor suffixes from tournament slugs, `_SIGNATURE_EVENTS` + `_tournament_importance()` for importance-aware current event tiebreaking (Majors > Signature > Other), upcoming events linked to `/events/{id}`, tournament name discoverability cues (chevrons, "View details").
- ✅ Category pages infrastructure: Generic `/categories/[slug]` route for sport/category-filtered feeds, golf bespoke design, iOS `SportCategoryView` navigable from filter chips.
- ✅ Odds chart redesign: Period markers at game boundaries (ESPN data, gap-filling for missed early periods), auto-zoom Y-axis (±5% padding instead of fixed 0-100%), smart start time (skips hours of flat pre-game data), team color labels, compact score diff below chart. Applied to both web (`OddsChart.tsx`) and iOS (`OddsChartView.swift`).
- ✅ EI calibration: Scaling constant iteratively tuned 8.0 → 4.0 → 2.5. Time normalization ratio capped at 2.0x. Added EI diagnosis endpoint (`/api/admin/ei/diagnosis`) with per-sport breakdown and snapshot distribution. Fixed infinite recalculate loop.
- ✅ Duplicate event handling: 3-layer defense-in-depth — debug logging in `_find_statpal_event_for_odds_api()`, broader `_find_existing_event_by_teams()` safety net in all 3 event creation paths, admin merge endpoint. Cleaned up 5,735 orphan events (54 StatPal-vs-Odds API + 5,681 StatPal-vs-StatPal duplicates). Merge endpoint explicitly clears FK references from 4 non-CASCADE tables before delete.
- ✅ Odds API quota monitoring: Passive `x-requests-remaining` header capture in `odds_api.py`, Redis storage with 25h TTL, daily-activity inference endpoint, admin quota dashboard.
- ✅ Graduated live scoring + championship stakes weighting: Replaced flat +30 live bonus with graduated scoring (35/30/20 based on game closeness). Championship stakes weighting gives multiplicative boost for teams with >10% title odds. Moves "Futures stake weighting" from Ideas Backlog to shipped.
- ✅ ESPN box scores + live stat prop tracking: Box score data parsed from ESPN summary endpoint, stored as `Event.box_score_data` JSONB. iOS event detail shows stat prop pace projections with semi-circular gauges.
- ✅ ESPN proactive commence_time correction: `_discover_events()` cross-references ESPN schedule at discovery time to correct Odds API time errors before they enter the database. Adds ESPN schedule lookup as a third time source alongside StatPal and Odds API.
- ✅ Search ranking improvements: Search results ranked by highlight score for relevance. LLM anti-speculation: 3-tier prompt instructions prevent vague hedging in line movement explanations when no injury/news context is available.
- ✅ Feed resilience: Aggregate probability fallback when bookmaker consensus unavailable. Resolved 100% futures filtered from display. "No odds yet" placeholder for events without data. My Stuff soonest-first sorting. Reserve team match filtering.
- ✅ Clock-prefix period parsing fix: `_parse_game_progress()` falsely detected overtime when `event.period` had clock prefix (e.g., `"6:55 - 1st Quarter"` → regex matched `6` from clock, `6 > 4 quarters` = overtime). Fix: strip clock prefix, word-boundary OT regex, specific period-number patterns. Same fix in `win_probability.py`.
- ✅ Architecture improvement plan: 5-phase comprehensive plan covering backend cleanup, design system foundation, win probability charts, futures grouping, and design component migration. See `docs/architecture-improvement-plan.md`.
- ✅ Backend cleanup Phase 1 (5-step refactoring): (a) `fangraphs` source key renamed to `mlb` across backend/frontend/iOS + DB migration, (b) dead code removed (`fangraphs_api.py`, `gei.py`, `tasks/pulse.py`), (c) MoneyPuck stub removed from source registry, (d) stat model verification confirmed for college games, (e) design system foundation: shadcn/ui + Framer Motion, CSS design tokens, team-color theming, EI/status animation utilities.
- ✅ Probability timeline endpoint + TournamentChart: `GET /api/futures/{market_id}/probability-timeline` returns time-bucketed probability history. `TournamentChart.tsx` SVG component with Top 5/10/All toggle, Field area fill, position-based 10-color palette, interactive crosshair tooltip. 20 tests.
- ✅ Series probability computation: `compute_series_win_prob()` in `utils/series_probability.py` — negative binomial distribution for best-of-N series. API endpoint. 37 tests.
- ✅ Discover email ground-truth diagnostics: Polymarket email-highlight audit loader accepts stable `Audit Export` headers and URL/path env vars, supports private Google Sheets via service-account auth, records raw/loaded row counts, latest email date, and stale status, and surfaces private-export HTTP errors in `/admin/discover-quality` instead of breaking debug. Admin now splits Polymarket email misses into a dedicated editorial audit panel with bucket counts, sheet scores, hooks, DB trace entry points, and recommended actions. Email hits remain audit-only and do not directly boost ranking.
- ✅ Discover aggregate feedback review loop: `/api/admin/discover-engagement` now emits a card-level human review queue segmented by web/native and signed-in/anonymous, with promote/downrank/investigate candidates based on dismiss/open/share/context-expand rates, average rank, category, archetype, and market family. `/admin/discover-quality` renders the queue for low-friction ranking review. Feed ranking now suppresses recently seen cards per user/session, respects longer-lived dismisses, tightens stale no-movement futures filtering, and downranks/caps regional US election primaries plus niche low-signal sports families. Native Discover tuning inspector is DEBUG-only so TestFlight users do not see category-score internals.
- ✅ TestFlight Discover feedback loop: `/api/admin/discover-engagement` now reports repeat-card rate, stale-impression rate, runtime Discover suppression config, top repeated/stale cards, recent human review decisions, and a persisted review-decision API/table. `/admin/discover-quality` renders launch-health metrics and one-click review decisions. Native Discover bypasses the short API cache for fresh suppression, and rage-shake bug reports include visible Discover cards, current card, and recent Discover interactions so screenshots are actionable.
- ✅ Discover launch-health hill-climb console: repeat rate and stale impression rate are now the primary admin scoreboard before broader TestFlight distribution. Top stale/repeated cards link to detail pages, human review decisions are idempotent, reviewed cards leave the queue, and promote/downrank decisions apply bounded feed score nudges instead of only logging review rows.
- ✅ Daily habit loop + friend challenge frontend: `/daily` now provides five curated Higher/Lower calls with progress, streak/local completion tracking, countdown, replay, prediction submission, and shareable text summary. `/challenge/[id]` now loads existing challenge codes, handles friend Higher/Lower acceptance, shows participants/results, and supports share/copy. Discover sports futures staleness also tightened to suppress 90%+ effectively resolved sports markets unless the leader had a real underdog/surprise journey; deterministic futures copy now uses probability points and better leader-aware snippets.
- ✅ Market grouping system: Source hierarchy recovery (canonical_market_key set during Kalshi/Polymarket polling) + threshold variant detection (regex-based numeric threshold extraction). Three frontend components (`CombinedMarketCard`, `ProgressionTable`, `ThresholdGrid`). Admin + API endpoints. 315 tests.
</details>

See `docs/PRD.md` for full roadmap.

---
