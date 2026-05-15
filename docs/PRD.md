# Bain Luck -- Product Requirements Document

## 1. Vision & North Star

Bain Luck is a prediction market discovery platform that translates betting odds and prediction market prices into intuitive probabilities. Instead of "-150 / +130" or "0.60 CLOB price," users see "60% vs 40%." The product aggregates probabilities from sportsbooks, prediction markets (Kalshi, Polymarket), and proprietary models (ESPN, stat models, MLB Stats API, DataGolf) to present a unified view of any event's likelihood -- across sports, politics, economics, entertainment, weather, technology, geopolitics, and culture.

**North Star:** The most engaging way to explore what the world thinks will happen.

The product's success moment is immediate: a new user sees a card and thinks, "Oh, I had no idea -- that's only 23% likely?" This applies equally to a championship game, a presidential election, a Federal Reserve rate decision, or a movie's Rotten Tomatoes score. The mental model is **probability discovery**, not gambling.

**Live site:** https://bainluck.com | **Sports feed:** https://bainluck.com/sports

---

## 2. Target Users

**Primary audience:** Curious people who follow sports, politics, or current events casually and enjoy prediction games as lightweight entertainment. They want to see "73% chance" without needing to understand American odds or order book mechanics.

**What they want:**
- Quick, visual answers to "how likely is X?"
- Surprising discoveries they did not know to look for
- A fun way to test their intuition via prediction games
- Cross-source context: what do sportsbooks say vs. prediction markets vs. models?

**What they do NOT want:**
- Betting advice, picks, or trading signals
- Volume, liquidity, or order book data
- Dense statistical interfaces designed for professional bettors
- Forced sign-up or notifications

**Auth philosophy:** No required sign-in. The logged-out experience must feel complete. Auth exists to unlock favorites sync, cross-device preferences, prediction history, and personalized feed ranking. Auth is pull-based, never forced.

---

## 3. User Journeys

### First Visit: Discover Browser
Opens bainluck.com. Scrolls the Discover feed. Sees a card: "Will the Fed cut rates in June? -- 62% Yes." Taps Higher or Lower to guess the next card's probability. Gets 4 right in a row -- streak badge appears. Taps a politics card to see the full probability breakdown across Kalshi and Polymarket. Shares a card with a friend via a stable UTM link.

### Daily Return: Prediction Game Player
Opens the iOS app. A daily challenge card appears: "Make 5 predictions today." Taps Higher or Lower on 5 cards. Finishes the challenge and sees accuracy stats in My Stuff: 67% correct, 12-day streak, 143 total predictions. Category tuning in Preferences ensures more sports and fewer economics cards in tomorrow's feed.

### Live Sports Fan
Navigates to the Sports tab during an NBA playoff game. Opens the event detail page. Sees a multi-source probability chart with lines from sportsbook consensus, ESPN, Kalshi, Polymarket, and the stat model. Player prop cards show live stat lines next to prop thresholds. Related futures below the chart show how this game affects each team's championship odds.

### Category Explorer
Clicks Browse and opens Politics. Sees the presidential election hero section with candidates merged across Kalshi and Polymarket. Below, a cross-source spotlight highlights markets where the two platforms disagree by more than 5 points. Scrolls to Senate control, cabinet nominations, and policy markets. Taps into a market detail page with a probability timeline chart and outcome breakdown.

### Compete with Friends
Receives a challenge link from a friend. Opens the same 5 markets the friend predicted on. Makes Higher/Lower guesses. Sees head-to-head results: who was more accurate, which predictions diverged. Returns to the Discover feed to find new markets to challenge back.

---

## 4. Feature Map

### Discover Feed (`/`)
The default landing page. A ranked stream of the most interesting predictions happening right now across all categories.

- **Higher/Lower game** -- guessing slots every 2nd card. Users predict whether the next market's probability is higher or lower. Results tracked per session and per user.
- **Daily challenges** -- 5-question focused challenge with explicit Next/Finish progression, completion analytics, and streak tracking across sessions.
- **LLM hook descriptions** -- GPT-4o-mini-generated journalist-style blurbs explaining why a market matters. Bounded to feed-shaped candidates only.
- **Deterministic explanations** -- first-page comprehension does not depend on LLM hooks. Headlines name the mover, leader, or source disagreement from existing outcome data.
- **Pexels images** -- stock photos on cards for visual richness.
- **Market quality classifier** -- suppresses narrow commodity ladders, repetitive dated buckets, social-count filler. Boosts compelling public stories (politics, economics, AI/tech, entertainment, sports).
- **Category filtering** -- chips for Sports, Politics, Entertainment, Economics, Weather, and more.
- **Personalization** -- authenticated users get bounded category boosts from interactions, favorites, pins, sport affinities, and roster-player matching.
- **Seen-card suppression** -- session and user interaction history reduces repeated cards across visits.
- **Shareability** -- stable UTM share URLs, card-specific share copy, generated OG images.

### Sports Feed (`/sports`)
Live, upcoming, and recently completed games across all tracked sports.

- **Multi-source probability charts** -- renders all available sources dynamically: sportsbook consensus, ESPN, stat model, MLB Stats API, Kalshi, Polymarket, DataGolf. Color-coded and labeled.
- **Excitement Index (EI)** -- 1-100 score based on the standard Game Excitement Index formula. Components: probability distance traveled, lead changes, comeback factor. Hall of Fame at `/ei/hall-of-fame`.
- **Divergence badges** -- visual indicator when prediction market odds differ from sportsbook consensus by 5+ or 10+ points.
- **Player props** -- Kalshi and Polymarket player prop markets displayed as cards with live box score stat lines.
- **Market maps** -- spread and total markets visualized as interactive maps for 1st half, 2nd half, and full game.
- **Related futures** -- championship odds, MVP odds, and award futures for teams in the current game.
- **Series markets** -- playoff series winner, exact score, spread, and total games markets.
- **Championship grids** -- league-level probability tables for 14+ leagues with monotonicity enforcement and noise filtering.
- **League market sections** -- playoff series, awards, props, season stats below championship grids.

### Event Detail Pages (`/sport/[sport]/[league]/[event]`)
The deep-dive view for any individual event.

- Multi-source probability chart with all available sources rendered dynamically
- Market map (spread and total visualization)
- Player props with live stat lines
- Game markets from Kalshi and Polymarket linked via semantic matching
- Related futures ("Bigger Picture" section) showing championship/award implications
- Series context for playoff games
- Source attribution on every probability

### Category Pages
Five native category dashboards, all polished on web and iOS.

- **Politics** (`/politics`) -- presidential election hero merging candidates across Kalshi + Polymarket. Cross-source spotlight for platform disagreement. Senate, cabinet, policy markets.
- **Entertainment** (`/entertainment`) -- Rotten Tomatoes, box office, Spotify, reality TV, awards. TMDB movie poster integration. Threshold market grouping for heatmap display.
- **Economics** (`/economics`) -- Fed rate decisions, inflation, GDP, recession probability, S&P/Nasdaq targets.
- **Weather** (`/weather`) -- city forecasts, rain probabilities, climate events, featured markets.
- **Preferences** (`/preferences`) -- interest selector (Love/Big/Wild/Nah) by category, sport affinities, team following, account management.

### Games & Social
- **Higher/Lower prediction game** -- integrated into Discover feed. Accuracy %, total predictions, current streak, best streak tracked in My Stuff.
- **Daily challenge** -- 5 predictions per day with streak mechanics.
- **Friend challenges** -- backend scaffold shipped (table, model, 3 API endpoints). Challenge a friend to predict on the same set of markets, compare accuracy.
- **Prediction stats** (`/discover/stats`) -- personal accuracy dashboard.

### Calibration Report (`/calibration`)
Public accuracy analysis. MCE 2.7pp across 195K+ resolved outcomes from 3 sources (Kalshi, Polymarket, Odds API). Virtual market reconstruction via `group_id`. Per-source breakdown. "Does Trading Activity Matter?" analysis section. Brier score 30% better than random baseline.

### Platform Coverage
- **Web** (Next.js 14, Vercel) -- desktop and mobile-responsive. Discover | Sports | Browse | My Stuff navigation.
- **iOS** (SwiftUI, TestFlight) -- full feature parity. Discover | Sports | Browse | Search | My Stuff tabs. Apple Sign-In + Google Sign-In with Keychain token storage. Rage shake bug reporting. 4-card welcome onboarding.
- **macOS** (shared SwiftUI codebase) -- menu bar live scores, Cmd+K search, context menus, keyboard navigation. Same views with `#if os(macOS)` conditionals.
- **Daily digest emails** -- morning email with top movers and resolving-soon markets.
- **Rage shake bug reporting** -- shake phone or Cmd+Shift+F to capture screenshot + app state, submitted to admin dashboard with auto-diagnosis (severity, root cause, Claude Code prompt).

---

## 5. Data Architecture

Full technical detail lives in `docs/architecture-reference.md`. This section covers the high-level design.

### Data Sources

| Source | What It Provides | Cost |
|--------|-----------------|------|
| The Odds API | Sports odds: moneylines, spreads, totals, futures (5-15 books) | ~$119/mo |
| Kalshi | Prediction markets: sports, politics, economics, entertainment, weather | Free |
| Polymarket | Prediction markets: sports, politics, entertainment | Free |
| ESPN | Team colors, logos, live game data, win probability, rosters | Free |
| StatPal | Schedules, rosters, injuries, play-by-play | ~$99/mo |
| DataGolf | Golf predictions, live in-play probabilities, leaderboards | ~$30/mo |
| MLB Stats API | Live baseball win probability | Free |
| TMDB | Movie/TV metadata, posters | Free |
| Pexels | Stock photos for Discover feed cards | Free |
| OpenAI | GPT-4o-mini for LLM classification + hook descriptions | ~$10/mo |

### Core Subsystems

**Event Registry** -- unified `find_or_create_event()` with 4-step cascade: exact source ID, cross-source ID, structured match (sport + time + teams), create. All source tasks wired. Prevents duplicate events from different sources describing the same game.

**Probability Aggregation** -- `compute_aggregate_probability()` blends all available sources with configurable weights (betting 3.0, ESPN 1.5, stat_model 1.0, Kalshi/Polymarket/MLB 0.8). Source-agnostic resilience: the system works when any single source goes dark (validated during March 2026 Odds API quota exhaustion).

**Prediction Market Matching** -- hourly task links Kalshi/Polymarket game markets to events via semantic matching. Three-phase: Link (ticker scan + general scan), re-validate, snapshot writing. The #1 technical challenge in the product and the biggest leverage point.

**Market Grouping** -- markets sharing the same real-world question (e.g., 10 nominee sub-markets for "Who wins Best Picture?") share a `group_id`. Powers feed dedup, cross-source matching, calibration accuracy, and related-market grouping.

**Feed Ranking** -- multiple candidate pools (sports, non-sports volume, movement, enriched, soon-resolving), quality classifier, category/archetype/story mixer, deterministic explanations. LLM hook enrichment intentionally bounded.

**Quota Guard** -- The Odds API quota (5M/month) circuit breaker with three modes: Normal, LIVE_ONLY (20K-50K remaining), FULL_STOP (<20K remaining). Sport-tier polling at 32s/64s/128s intervals.

### Quality Measurement

**Four-Layer Matching Audit** measures semantic matching accuracy:
- L1: Event Existence -- every game exists with all sources
- L2: Market-to-Event -- game markets linked via event_id
- L3: Futures Surfacing -- season futures on event detail pages
- L4: Market Completeness -- every market type showing per game

All 4 layers at 100% (April 24, 2026). Grid accuracy: 51/51 (100%).

**Feed Quality Audit** measures Discover feed output:
- `boring-rate@20 = 0` (no boring cards in top 20)
- `ladder/bucket-rate@20 = 0` (no commodity ladders in top 20)
- `explanation-coverage@20 = 20/20` (every card has an explanation)

---

## 6. Metrics

### North Star Metric
**Daily active users engaging with predictions** -- users who make at least one Higher/Lower guess, open a market detail page, or complete a daily challenge.

### Engagement Metrics
- **Higher/Lower guess rate** -- guesses per session (target: 3+)
- **Daily challenge completion rate** -- % of users who finish the 5-question challenge
- **Prediction streak retention** -- users maintaining active streaks across sessions
- **Feed card CTR** -- open rate on Discover cards
- **Share rate** -- cards shared per session
- **Weekly return rate** -- % of users who return within 7 days

### Data Quality Metrics (current values, May 2026)
- **Calibration MCE**: 2.7pp across 195K+ resolved outcomes (target: <5pp)
- **Four-layer matching**: 100% on all 4 layers
- **Grid accuracy**: 51/51 (100%)
- **Feed boring-rate@20**: 0/20
- **Feed explanation-coverage@20**: 20/20

---

## 7. Product Principles

1. **Visual over numerical** -- percentages and charts beat odds formats every time.
2. **Discovery-first** -- the feed surfaces what is interesting and surprising. Users should find things they did not know to look for.
3. **Probability-first** -- every piece of data is anchored to a probability. Context explains why a probability matters, not what to do about it.
4. **Source-agnostic resilience** -- the system works when any single source goes dark. Multiple independent sources prevent single-point-of-failure blind spots.
5. **No gambling language** -- we show what changed, not what to bet. Never show volume, trade counts, or liquidity to users.
6. **Cross-platform parity** -- web, iOS, and macOS should each feel native.
7. **Transparency** -- public calibration report, source attribution on every probability.
8. **Respect attention** -- no spammy notifications, no forced auth.

---

## 8. Non-Goals

Bain Luck is **NOT**:

- **A sportsbook or betting interface** -- no wagering, no account balances, no deposit flows.
- **A trading platform** -- no order books, no positions, no portfolio tracking.
- **A pick-selling or tout service** -- no "best bets," no betting advice, no recommended wagers.
- **A stats-heavy analytics tool** -- not designed for professional bettors or quantitative traders.
- **A social network** -- predictions and challenges are social features, but the product is not a feed of user-generated content.

The product displays information, not transactions. No gambling language, no calls to action to place bets, no volume or trade data shown to users. Betting is contextual information for computing probabilities, not the call to action.

---

## 9. Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+), 3,500+ tests | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis (dual workers: realtime + background) | Heroku Redis |
| Web Frontend | Next.js 14 (React) | Vercel |
| iOS/macOS App | SwiftUI (shared codebase, 89 Swift files) | TestFlight |
| Auth | Firebase Auth (Google + Apple Sign-In) | Google Cloud |
| Analytics | GA4 + Firebase Analytics | Google |
| LLM | OpenAI GPT-4o-mini | OpenAI |
| Error Tracking | Sentry | Sentry Cloud |

Both platforms auto-deploy from GitHub on push to `master`. CI runs backend pytest + frontend `npm run build` on every push.

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
