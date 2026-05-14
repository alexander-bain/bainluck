# Bain Luck -- Product Requirements Document

## 1. Overview

**North star:** The most engaging way to explore what the world thinks will happen.

Bain Luck is a prediction market discovery platform that translates betting odds and prediction market prices into intuitive probabilities. Users see "60% vs 40%" instead of "-150 / +130" or "0.60 CLOB price." The product aggregates probabilities from sportsbooks (The Odds API), prediction markets (Kalshi, Polymarket), and proprietary models (ESPN, Bain Luck stat model, MLB Stats API, DataGolf) to present a unified view of any event's likelihood.

**What it covers:** Sports, politics, economics, entertainment, weather, technology, geopolitics, and culture -- anything with a tradeable probability.

**Target user:** Curious people who want probability-first context. They follow sports, politics, or current events casually. They enjoy prediction games as lightweight entertainment. They want to see "73% chance" without needing to understand American odds or order book mechanics.

**What Bain Luck is NOT:**
- A sportsbook or betting interface
- A pick-selling or tout product
- A trading platform for prediction markets
- A stats-heavy analytics tool for professional bettors
- A social network

The product displays information, not transactions. No gambling language, no calls to action to place bets, no volume or trade data shown to users.

**Current product surface (May 2026):**
- **Discover feed** (`/`) -- Social prediction feed with Higher/Lower games, daily challenges, prediction streaks, images, LLM hooks, and personalization
- **Sports feed** (`/sports`) -- Live, upcoming, and recently completed games with multi-source probability charts
- **Category pages** -- Dedicated dashboards for Politics, Entertainment, Economics, Weather, and Preferences
- **Event detail pages** -- Multi-source probability charts, market maps, player props, series markets, related futures
- **Championship grids** -- League-level probability tables for 14+ leagues
- **Calibration report** (`/calibration`) -- Public accuracy analysis across 151K+ resolved outcomes
- **iOS + macOS app** -- Native SwiftUI app distributed via TestFlight with full feature parity
- **Daily digest emails** -- Morning email with top movers and resolving-soon markets

**Live site:** https://bainluck.com (Discover is the default landing page) | Sports feed: https://bainluck.com/sports

### The 10-Second Success Moment

A new user should immediately think:

> "Oh, I had no idea -- that's only 23% likely?"

This applies equally to a championship game, a presidential election, a Federal Reserve rate decision, or a movie's Rotten Tomatoes score. The mental model is **probability discovery**, not gambling.

### Product Priorities (ranked)

1. **Discover feed** -- Social prediction market feed with Higher/Lower games, images, LLM hooks, category filtering, daily challenges, and prediction streaks
2. **Best aggregated event probabilities** -- Probability-first event detail pages with multi-source charts, market maps, player props, and championship path
3. **Cross-source comparison** -- Compare across ALL probability sources (sportsbooks, Kalshi, Polymarket, ESPN, stat models)
4. **Related futures** -- Season futures, awards, playoff path, series probability, and championship grids on every event page
5. **Team/league-level odds** -- Championship grids + league market sections (series, awards, props)
6. **Multi-platform** -- Full parity between web, iOS, and macOS (shared SwiftUI codebase)

---

## 2. Product Principles

1. **Visual > Numerical** -- Percentages and charts beat odds formats every time.
2. **Discovery-first** -- The feed surfaces what is interesting and surprising. Users should find things they did not know to look for.
3. **Probability-first** -- Every piece of data is anchored to a probability. Context explains why a probability matters, not what to do about it.
4. **Source-agnostic resilience** -- The system works when any single source goes dark. Multiple independent sources (sportsbooks, Kalshi, Polymarket, ESPN, stat models) prevent single-point-of-failure blind spots.
5. **No gambling language** -- We show what changed, not what to bet. Never show volume, trade counts, or liquidity metrics to users. Betting is contextual information, not the call to action.
6. **Cross-platform parity** -- Web, iOS, and macOS should each feel native. Shared SwiftUI codebase for Apple platforms. Feature set, analytics taxonomy, and design language are consistent everywhere.
7. **Respect attention** -- No spammy notifications. Silence is sometimes the correct UX. Auth is pull-based, never forced.
8. **Transparency** -- Public calibration report. Source attribution on every probability. Users can always see where a number comes from.

---

## 3. User Journeys

### Casual Discover browser
Opens bainluck.com. Scrolls the Discover feed. Sees a card: "Will the Fed cut rates in June? -- 62% Yes." Taps Higher or Lower to guess the next card's probability. Gets 4 right in a row -- streak badge appears. Taps a politics card to see the full probability breakdown across Kalshi and Polymarket. Shares a card with a friend via a stable UTM link.

### Live sports fan
Navigates to the Sports tab during an NBA playoff game. Opens the event detail page. Sees a multi-source probability chart with lines from sportsbooks (consensus of 5-15 books), ESPN's model, Kalshi, Polymarket, and the Bain Luck stat model. The Pulse badge reads 82 -- the game is a must-watch. Player prop cards show live stat lines next to their prop thresholds. Related futures below the chart show how this game affects each team's championship odds.

### News and politics follower
Clicks Browse > Politics. Sees the presidential election hero section with candidates merged across Kalshi and Polymarket. Below, a cross-source spotlight highlights markets where the two platforms disagree by more than 5 points. Scrolls to Senate control, cabinet nominations, and policy markets. Taps into a market detail page with a probability timeline chart and outcome breakdown.

### Returning prediction game player
Opens the iOS app. A daily challenge card appears: "Make 5 predictions today." Taps Higher or Lower on 5 cards. Finishes the challenge and sees their accuracy stats in My Stuff: 67% correct, 12-day streak, 143 total predictions. Category tuning in Preferences ensures more sports and fewer economics cards in tomorrow's feed.

---

## 4. Features

### Discover Feed (`/`)
The default landing page. A ranked stream of the most interesting predictions happening right now across all categories.

- **Higher/Lower game** -- Every 2nd card is a guessing slot. Users predict whether the next market's probability is higher or lower than the current one. Guess results tracked per session and per user.
- **Daily challenges** -- 5-question focused challenge with explicit Next/Finish progression and completion analytics.
- **Prediction streaks** -- Consecutive correct guesses tracked across sessions. Streak badge in My Stuff.
- **LLM hook descriptions** -- GPT-4o-mini-generated journalist-style blurbs explaining why a market matters. Bounded to feed-shaped candidates only (never the full 56K+ market backlog).
- **Deterministic explanations** -- First-page comprehension does not depend on LLM hooks. Headlines name the mover, leader, or source disagreement from existing outcome data.
- **Pexels images** -- Stock photos on cards for visual richness.
- **Market quality classifier** -- Suppresses narrow commodity ladders, repetitive dated buckets, social-count filler, weak explanation cards, and low-signal regional election markets. Boosts compelling public stories.
- **Category filtering** -- Chips for Sports, Politics, Entertainment, Economics, Weather, and more.
- **Personalization** -- Authenticated users get bounded category boosts/penalties from recent interactions, favorites, pins, sport affinities, and roster-player matching. Per-card `personalization_trace` diagnostics for admin debugging.
- **Seen-card suppression** -- Anonymous and signed-in users get session/user interaction history to reduce repeated cards across visits.
- **Shareability** -- Stable UTM share URLs, card-specific share copy, generated OG images, shared-link CTAs.
- **Admin quality dashboard** -- `/admin/discover-quality` with feed metrics, timing, hook coverage, engagement rates, editorial audit panel, and human review queue.

### Sports Feed (`/sports`)
Live, upcoming, and recently completed games across all tracked sports.

- **Multi-source probability charts** -- OddsChart renders N sources dynamically: sportsbook consensus, ESPN, Bain Luck stat model, MLB Stats API, Kalshi, Polymarket, DataGolf. Color-coded and labeled.
- **Divergence badges** -- Purple (>10%) or blue (>5%) badge when prediction market odds differ from sportsbook consensus.
- **Pulse (Game Excitement Index)** -- Proprietary 1-100 excitement score based on probability movement patterns. Components: heart rate, amplitude, arrhythmia, vitals, lead changes. Percentile-scored against completed games. Hall of Fame at `/pulse/hall-of-fame`.
- **Player props** -- Kalshi and Polymarket player prop markets displayed as cards with live box score stat lines when available.
- **Market maps** -- Spread and total markets visualized as interactive maps for 1st half, 2nd half, and full game.
- **Related futures** -- Championship odds, MVP odds, and award futures relevant to teams playing in the current game, displayed in a "Bigger Picture" section.
- **Series markets** -- Playoff series winner, exact score, spread, and total games markets loaded at display time.
- **Championship grids** -- League-level probability tables for 14+ leagues with monotonicity enforcement and noise filtering.
- **League market sections** -- Playoff series, awards, props, season stats, and more markets below championship grids (web + iOS).

### Category Pages
Five native category pages, all polished on web and iOS, following a consistent pattern: backend route queries `FuturesMarket` by category + ticker prefixes, classifies into sub-themes, builds structured response.

- **Politics** (`/politics`) -- Presidential election hero merging candidates across Kalshi + Polymarket. Cross-source spotlight for platform disagreement. Senate, cabinet, policy markets.
- **Entertainment** (`/entertainment`) -- Rotten Tomatoes, box office, Spotify, reality TV, awards. TMDB client for movie poster lookup. Threshold market grouping for heatmap-ready display.
- **Economics** (`/economics`) -- Fed rate decisions, inflation, GDP, recession probability, S&P/Nasdaq targets.
- **Weather** (`/weather`) -- City forecasts, rain probabilities, climate events, featured markets. City search and clickable probability graphs.
- **Preferences** (`/preferences`) -- Interest selector (Love/Big/Wild/Nah) by category. Sport affinities, team following, account management.

### Calibration Analysis (`/calibration`)
Public accuracy report across 151K+ resolved outcomes from 3 sources. MCE 3.8pp, Brier 0.1745 (30% better than random). Virtual market reconstruction via `group_id`. `is_winner` backfill task runs every 6h. Per-source breakdown: Odds API 2.4pp, Polymarket 5.2pp, Kalshi 5.5pp.

### Prediction Game
Higher/Lower guessing integrated into the Discover feed. Prediction stats (accuracy %, total predictions, current streak, best streak) in My Stuff. Daily challenge cards. Friend challenge backend scaffold (table, model, 3 API endpoints) shipped; frontend UI not yet built.

### Cross-Platform
- **Web** (Next.js 14, Vercel) -- Desktop and mobile-responsive. Discover | Sports | Browse (dropdown) | My Stuff navigation.
- **iOS** (SwiftUI, TestFlight) -- Full feature parity. Discover | Sports | Browse | Search | My Stuff tabs. Apple Sign-In + Google Sign-In with Keychain token storage. Rage shake bug reporting. 4-card welcome onboarding for first launch.
- **macOS** (shared SwiftUI codebase) -- Menu bar live scores, Cmd+K search, context menus, keyboard navigation. Same SwiftUI views with `#if os(macOS)` conditionals.
- **Apple Watch** -- Prototype (guess game, live games). Physical deployment not yet verified.

### Authentication
No required sign-in -- the logged-out experience must feel complete. Auth exists to unlock: favorites sync, pin sync, cross-device preferences, prediction history, and personalized feed ranking. Auth is pull-based, not forced. Firebase Auth with Google + Apple Sign-In. Backend-session-token pattern: iOS/web sends raw OAuth credential to backend, backend verifies with identity provider, creates Firebase user, issues PyJWT session token (HS256, 30-day TTL). Safari ITP workaround via 3-tier auth fallback.

### Rage Shake Bug Reporting
Shake phone or Cmd+Shift+F (macOS) to capture a screenshot + app state (page, device, network, user, visible Discover cards). Submitted to `POST /api/feedback/bug-report`. Admin page at `/admin/bug-reports` with auto-diagnosis (severity P0-P3, root cause, Claude Code prompt). Status flow: new, reviewed, actioned, dismissed. Burndown chart + resolution time tracking.

### Sports Coverage
Blacklist approach -- all sports from The Odds API are included except those explicitly excluded (most minor soccer leagues, cricket, rugby, AFL). Kalshi and Polymarket markets are ingested across all non-crypto categories. The system automatically picks up new sports added by The Odds API without code changes. 14+ leagues with championship grids. Sport-tier polling: Tier 1 (NBA/NHL/MLB/NFL/NCAAB), Tier 2 (WNBA/EPL/MLS/UCL/MMA/NCAAF), Tier 3 (everything else).

---

## 5. Architecture Summary

### Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+), 3,500+ tests | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis (dual workers: realtime + background) | Heroku Redis |
| Web Frontend | Next.js 14 (React) | Vercel |
| iOS/macOS App | SwiftUI (shared codebase, 89 Swift files) | TestFlight |
| Auth | Firebase Auth (Google + Apple Sign-In) | Google Cloud |
| Analytics | GA4 + Firebase Analytics | Google |
| LLM | OpenAI GPT-4o-mini (~$10/mo) | OpenAI |
| Error Tracking | Sentry | Sentry Cloud |

### Key Subsystems

**Event Registry** (`services/event_registry.py`) -- Unified `find_or_create_event()` with 4-step cascade: exact source ID, cross-source ID, structured match (sport + time +/- 4h + teams), create. All 5 source tasks wired. ESPN is a first-class source.

**Probability Aggregation** (`utils/aggregation.py`) -- `compute_aggregate_probability()` reads from `Event.win_probability_sources` JSONB. Source weights: betting 3.0, ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8. All sources write via select+update pattern (not ORM attribute assignment, which silently fails for JSONB).

**Prediction Market Matching** (`tasks/prediction_market_matching.py`) -- Hourly task links Kalshi/Polymarket game markets to events. Three-phase: Link (Pass 1 ticker scan + Pass 2 general scan), Re-validate (Phase 1.5), Snapshot writing (Phase 2). Per-market commit to avoid deadlocks. Current overall Kalshi open link rate: 93.9%.

**Quota Guard** (`tasks/redis_state.py`) -- The Odds API quota (5M/month) circuit breaker. >50K remaining: normal. 20K-50K: LIVE_ONLY. <20K: FULL_STOP. Sport-tier polling: Tier 1 (NBA/NHL/MLB/NFL/NCAAB) at 32s, Tier 2 at 64s, Tier 3 at 128s.

**Feed Ranking** (`routes/feed.py`, `utils/feed_market_quality.py`) -- Multiple candidate pools (sports, non-sports volume, movement, enriched, soon-resolving). Quality classifier + category/archetype/story mixer. Deterministic explanations first-class. LLM hook enrichment bounded.

**Four-Layer Matching Audit** (`scripts/audit_event_matching.py`) -- L1: Event Existence, L2: Market-to-Event Linking, L3: Futures Surfacing, L4: Market Completeness. All 4 layers at 100% (April 24, 2026).

### External Services

| Service | Purpose | Cost |
|---------|---------|------|
| The Odds API | Sports odds (moneylines, spreads, totals, futures) | ~$119/mo |
| Kalshi | Prediction markets (sports, politics, economics, entertainment, weather) | Free |
| Polymarket | Prediction markets (sports, politics, entertainment) | Free |
| ESPN | Team colors, logos, live game data, win probability, rosters | Free |
| MLB Stats API | Live baseball win probability | Free |
| StatPal | Schedules, rosters, injuries, play-by-play | ~$99/mo |
| DataGolf | Golf predictions, live in-play probabilities | ~$30/mo |
| TMDB | Movie/TV metadata, posters | Free |
| Pexels | Stock photos for Discover feed cards | Free |
| OpenAI | GPT-4o-mini for classification + hook descriptions | ~$10/mo |

### Win Probability Sources (7)

| Source | Type | Sports | Display |
|--------|------|--------|---------|
| Betting Odds | Market (The Odds API) | All | Dark solid line (consensus of 5-15 books) |
| ESPN | Model (undocumented API) | NBA, NCAAB, NFL, NCAAF, NHL, MLB | Orange dashed line |
| Bain Luck Model | Statistical (nflfastR methodology) | NFL, NCAAF, NBA, NCAAB, WNCAAB, NHL | Purple dashed line |
| MLB Stats API | Model (official MLB API) | MLB | Teal line |
| Kalshi | Market (prediction market) | All sports | Green line |
| Polymarket | Market (prediction market) | All sports | Blue line |
| DataGolf | Model (DataGolf API) | Golf | DataGolf line |

The OddsChart renders all available sources dynamically -- no frontend changes needed when a new source is added.

### Data Flow

1. **Ingest**: Celery tasks poll external APIs on schedules (32s-128s for live sports, hourly for futures, 2min for live prediction markets). Event Registry deduplicates and merges.
2. **Aggregate**: `compute_aggregate_probability()` blends all available sources with configurable weights. Written to `Event.win_probability_sources` JSONB.
3. **Rank**: Feed ranking scores events and markets across multiple candidate pools, applies quality filters and diversity constraints.
4. **Serve**: FastAPI endpoints serve ranked feeds, event details, category pages. Results cached where appropriate.
5. **Display**: Next.js (web) and SwiftUI (native) render probability-first UI with charts, cards, and interactive elements.

### Deployment

Both platforms auto-deploy from GitHub on push to `master`. Backend deploys to Heroku (~15s). Frontend deploys to Vercel. CI runs backend pytest + frontend `npm run build` on every push. Alembic migrations run during Heroku release phase.

For deep architectural detail, see `docs/architecture-reference.md`.

---

## 6. Data Model

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `events` | Games with teams, scores, probability sources | `win_probability_sources` (JSONB), `status`, `espn_id`, `statpal_fixture_id` |
| `odds_snapshots` | Historical odds per bookmaker | Write-time dedup, `reading_count`, `valid_until` |
| `win_prob_snapshots` | Multi-source win probability history | `source` (espn, stat_model, kalshi, polymarket, mlb, betting) |
| `futures_markets` | Championship/award/prop markets from all sources | `market_tier` (1-5), `event_id` (nullable FK), `llm_sport_category`, `image_url`, `hook_description`, `group_id` |
| `futures_outcomes` | Individual outcomes within markets | `current_probability`, `is_winner`, `team_id`, `calibration_probability` |
| `teams` | Team data with ESPN enrichment | `primary_color`, `logo_url`, `roster_players` (JSONB), `alternate_names` (JSONB) |
| `team_identity_mapping` | Cross-source team identity index | `source`, `source_id`, `source_name`, `sport_key` |
| `users` | Firebase Auth users | `firebase_uid`, `email`, `display_name` |
| `user_predictions` | Higher/Lower guesses | `session_id`, `user_id`, `market_id`, `guess`, `correct` |
| `user_seen_markets` | Tracks which markets a user/session has been shown | Dedup in feed |
| `discover_interactions` | First-party engagement data | Impressions, opens, dismisses, likes, shares, expands |

---

## 7. Metrics

### North Star
**Daily active users engaging with predictions** -- users who make at least one Higher/Lower guess, open a market detail page, or complete a daily challenge.

### Proxy Metrics
- **Higher/Lower guess rate** -- guesses per session (target: 3+)
- **Daily challenge completion rate** -- % of users who finish the 5-question challenge
- **Prediction streak retention** -- users maintaining active streaks across sessions
- **Feed card CTR** -- open rate on Discover cards
- **Share rate** -- cards shared per session
- **Weekly return rate** -- % of users who return within 7 days

### Quality Metrics (current values, May 2026)
- **Calibration MCE**: 3.8pp across 151K resolved outcomes (target: <5pp)
- **Kalshi open link rate**: 93.9% (target: 100%)
- **Four-layer matching**: 100% on all 4 layers (Event Existence, Market-to-Event, Futures Surfacing, Market Completeness)
- **Grid accuracy**: 51/51 (100%)
- **Feed boring-rate@20**: 0/20
- **Feed explanation-coverage@20**: 20/20

---

## 8. Milestones

| When | What |
|------|------|
| **March 2026** | MVP: sports odds visualization, multi-source charts, ESPN integration, Kalshi + Polymarket integration, authentication, personalized feed, related futures |
| **Early April 2026** | Event Registry shipped (4-step cascade, all 5 source tasks). Market tier tagging (90K+ markets). Roster-based team_id linking. Championship grids for 14+ leagues. Golf product launch with DataGolf integration. |
| **Mid April 2026** | Four-layer matching audit system -- all 4 layers to 100%. macOS app launched. Weather page shipped (6 backend endpoints, 521 markets). Quota optimization (circuit breaker, sport-tier polling). |
| **Late April 2026** | Discover feed launched with Higher/Lower games, LLM hooks, Pexels images. Prediction game with streaks and daily challenges. Hook enrichment pipeline (GPT-4o-mini). |
| **Early May 2026** | Category pages shipped: Politics, Entertainment, Economics (web + iOS). Calibration pipeline: MCE 4.8pp across 181K outcomes. Bug report admin with rage shake pipeline. |
| **May 6-8** | 70+ commit marathon: performance, category pages, grid fixes, dead code cleanup. Navigation redesign (Discover as default). 14/14 rage shake bugs resolved. 335+ contract tests. |
| **May 11-13** | TestFlight launch (first external build). StatPal playoff parser fix. Native category page polish (all 5 pages). iOS league market sections. Calibration MCE improved to 3.8pp. Daily digest emails. Friend challenge scaffold. |

---

## 9. Roadmap

### Active Work
- **Semantic matching hill-climb** -- Kalshi sawtooth oscillation fix, double-header date matching, link rate toward 100%
- **Discover feed quality + personalization** -- Polymarket email ground-truth pipeline, entity-level personalization, aggregate feedback review queue
- **Calibration improvements** -- Kalshi API settlement backfill, football/hockey accuracy, nightly refresh task

### Next Up
- **GA4 console configuration** -- Custom dimensions, key events, audiences via Admin API or manual setup
- **Cross-source market matching for non-sport categories** -- Reduce duplicate cards across Kalshi and Polymarket on Entertainment, Economics, Weather pages
- **Push notifications** -- Foundation shipped (iOS token capture + backend endpoint), actual sending not implemented
- **Friend challenge UI** -- Backend scaffold exists, frontend not built

### Future
- **Semantic search** -- Embedding-based search with pgvector so users can ask "Will the Celtics repeat?"
- **Live game companion mode** -- Aggressive auto-refresh, screen-stays-awake, simplified layout
- **iOS widgets** -- Lock Screen, Home Screen, macOS Today view
- **App Store submission** -- After TestFlight validation
- **Email provider migration** -- Gmail API to SendGrid/Postmark/SES before scaling beyond single-user

Full backlog: `docs/backlog.md` (single source of truth).

---

## 10. Reference Docs

| Document | Purpose |
|----------|---------|
| `docs/architecture-reference.md` | Core system design: aggregation, resilience, charts, tasks, admin |
| `docs/feature-reference.md` | Detailed feature documentation |
| `docs/backlog.md` | All outstanding work items (single source of truth) |
| `docs/completed-features.md` | Shipped features log |
| `docs/gotchas-reference.md` | Extended gotchas (62 entries) |
| `docs/design-system.md` | Visual design system: colors, type, motion, voice, components |
| `docs/hill-climb-guide.md` | Matching accuracy hill-climb playbook |
| `docs/quality-audit.md` | Audit script usage, check catalog |
