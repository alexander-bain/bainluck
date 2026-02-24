# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

**Bain Luck** is a visual-first sports odds experience that translates betting markets into intuitive win probabilities. Users see "60% vs 40%" instead of "-150 / +130".

**North Star**: The cleanest odds visualization tool on the internet.

**Target User**: Casual sports fans watching games who want context, not betting advice. Second-screen experience.

**Live Site**: https://bainluck.com

---

## Tech Stack

| Component | Technology | Hosting |
|-----------|------------|---------|
| Backend API | FastAPI (Python 3.11+) | Heroku |
| Database | PostgreSQL | Heroku Postgres |
| Task Queue | Celery + Redis | Heroku Redis |
| Frontend | Next.js 14 (React) | Vercel |
| iOS App | SwiftUI | Planned |

**Key External Services:**
- **The Odds API** (the-odds-api.com) - Sports odds data (~$119/mo)
- **Kalshi** (kalshi.com) - Prediction market data (futures with timing info, free)
- **Polymarket** (polymarket.com) - Prediction market data (sports + politics/entertainment/crypto, free, no API key)
- **SportsDataIO** (sportsdata.io) - **Removed.** Roster sync migrated to ESPN + MLB Stats API. `sportsdata_api.py` deleted.
- **MySportsFeeds** (mysportsfeeds.com) - Injuries, lineup changes, transactions, game context (pending personal account approval). Key enabler for "Why Did the Line Move?" feature. Affordable alternative to SportsDataIO for structured sports data with timestamps.
- **MLB Stats API** (statsapi.mlb.com) - Live baseball win probability, schedules, play-by-play (free, no API key)
- **ESPN** (undocumented API) - Team colors, logos, live game data, win probability, rosters, injuries, news (free, unreliable)
- **TMDB** (themoviedb.org) - Movie posters, headshots, trailers for Oscars page (free tier, no API key needed for read — uses Read Access Token as Bearer auth)
- **OpenAI** (platform.openai.com) - GPT-4o-mini for LLM classification (~$5/mo)
- **Google Analytics 4** - User analytics (free)
- **Firebase Auth** - Google Sign-In (Apple planned), user accounts and personalization (free tier)

---

## Project Structure

```
bainluck/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── models/models.py     # SQLAlchemy models
│   │   ├── routes/
│   │   │   ├── events.py        # Main events API (incl. typeahead search)
│   │   │   ├── admin.py         # Admin/debug endpoints
│   │   │   ├── auth.py          # Auth endpoints (Google sign-in, profile)
│   │   │   ├── sports.py        # Sports listing
│   │   │   ├── futures.py       # Championship odds
│   │   │   ├── feed.py          # Unified feed endpoint (events + futures ranked)
│   │   │   ├── oscars.py        # Oscars landing page (cross-source odds aggregation)
│   │   │   ├── market_moves.py  # "Market Was Wrong" endpoint
│   │   │   ├── user.py          # User data endpoints (pins, teams, onboarding, preferences)
│   │   │   └── health.py        # Health check endpoint
│   │   ├── services/
│   │   │   ├── odds_api.py      # The Odds API client
│   │   │   ├── kalshi_api.py    # Kalshi prediction market client
│   │   │   ├── espn_api.py      # ESPN API client (teams, scores, injuries, news)
│   │   │   ├── mlb_api.py       # MLB Stats API client
│   │   │   ├── firebase_auth.py # Firebase Admin SDK
│   │   │   ├── llm.py           # OpenAI GPT-4o-mini integration
│   │   │   └── database.py      # DB connection
│   │   ├── config/
│   │   │   └── win_prob_sources.py # Win probability source registry
│   │   ├── dependencies/
│   │   │   └── auth.py          # FastAPI auth dependencies
│   │   ├── tasks/               # Celery tasks (modular package, 15 modules)
│   │   │   ├── __init__.py      # Celery app, task definitions, beat schedule
│   │   │   ├── config.py        # Shared constants (intervals, sport mapping)
│   │   │   ├── base.py          # DB session helpers, run_async()
│   │   │   ├── snapshots.py     # Shared snapshot write-time dedup helpers
│   │   │   ├── redis_state.py   # Adaptive polling state, heartbeat
│   │   │   ├── odds_polling.py  # Odds polling, snapshot dedup, opening odds
│   │   │   ├── pulse.py         # Pulse/GEI computation
│   │   │   ├── futures.py       # Futures polling from The Odds API
│   │   │   ├── kalshi.py        # Kalshi prediction market polling
│   │   │   ├── espn_sync.py     # ESPN live sync, team enrichment
│   │   │   ├── sports.py        # Sport sync, event discovery
│   │   │   ├── retention.py     # Snapshot collapse/retention
│   │   │   ├── roster_sync.py   # SportsDataIO roster sync
│   │   │   ├── team_linking.py  # Futures outcome → team linking
│   │   │   ├── prediction_market_matching.py  # Link game markets → events
│   │   │   └── mlb_sync.py     # MLB Stats API win probability sync
│   │   └── utils/
│   │       ├── odds_math.py     # Probability conversions
│   │       ├── pulse.py         # Game excitement algorithm
│   │       ├── highlights.py    # Event ranking (Level 1 + Level 2)
│   │       ├── futures_highlights.py # Futures market ranking
│   │       ├── win_probability.py # Statistical win prob model
│   │       ├── odds_filtering.py  # Stale bookmaker filter
│   │       ├── line_movement.py # Line movement detection + LLM prompt building
│   │       ├── futures_categorization.py # Rules + LLM categorization
│   │       ├── team_linking.py  # Team name matching utilities
│   │       └── prediction_market_matching.py  # Game-level market detection + matching
│   ├── alembic/                 # Database migrations
│   └── requirements.txt
├── frontend/
│   ├── app/                     # Next.js app router pages
│   │   ├── onboarding/page.tsx  # 5-step onboarding flow
│   │   ├── oscars/page.tsx      # Oscars landing page (TMDB enriched)
│   │   ├── my-stuff/page.tsx    # "My Teams" — team-filtered feed (3 states: sign-in, onboarding, feed)
│   │   ├── preferences/page.tsx # Settings editor (teams, interests, pinned, account)
│   │   ├── search/page.tsx      # Search results page
│   │   └── market-moves/page.tsx # "Market Was Wrong" page
│   ├── components/              # React components
│   │   ├── SearchBar.tsx        # Typeahead search with keyboard nav
│   │   └── OnboardingBanner.tsx # CTA banner for unonboarded users
│   ├── lib/
│   │   ├── api.ts              # API client
│   │   ├── types.ts            # TypeScript interfaces
│   │   ├── tmdb.ts             # TMDB API client (movie posters, headshots, trailers)
│   │   ├── oscarsData.ts       # Static Oscars ceremony data (order, categories, emoji)
│   │   └── sportCategories.ts  # Sport grouping logic
│   └── hooks/                   # Custom React hooks
├── docs/PRD.md                  # Full product requirements
└── tools/mcp-api-proxy/         # MCP proxy for API access
```

---

## Key URLs

| Environment | URL |
|-------------|-----|
| Production Frontend | https://bainluck.com |
| Production API | https://api.bainluck.com |
| API Docs | https://api.bainluck.com/docs |
| Vercel Dashboard | Vercel (auto-deploys from master) |
| Heroku Dashboard | Heroku (auto-deploys from master) |

**Heroku App Name:** `bainluck` (for CLI commands like `heroku logs -a bainluck`)

---

## Critical Files

| File | Purpose |
|------|---------|
| `backend/app/tasks/` | Celery tasks package: odds polling, Pulse, ESPN sync, retention |
| `backend/app/utils/highlights.py` | Highlight scoring, flags, and labels |
| `backend/app/utils/pulse.py` | Pulse (excitement metric) algorithm |
| `backend/app/routes/events.py` | Main API - events, search, history, pulse-rankings |
| `backend/app/services/llm.py` | OpenAI GPT-4o-mini integration for classification |
| `backend/app/services/espn_api.py` | ESPN API client for team/event enrichment |
| `backend/app/utils/futures_categorization.py` | Hybrid rules + LLM categorization |
| `frontend/components/EventCard.tsx` | Event display component (includes pin button) |
| `frontend/components/FuturesCard.tsx` | Futures market display component (includes pin button) |
| `frontend/components/PulseBadge.tsx` | Pulse score badge with tooltip |
| `frontend/hooks/usePinnedEvents.ts` | Hook for managing pinned events (localStorage) |
| `frontend/hooks/usePinnedFutures.ts` | Hook for managing pinned futures (localStorage) |
| `frontend/app/pulse/hall-of-fame/page.tsx` | Top 25 highest/lowest Pulse games |
| `backend/app/services/firebase_auth.py` | Firebase Admin SDK init and token verification |
| `backend/app/dependencies/auth.py` | `get_current_user` / `get_optional_user` FastAPI deps |
| `backend/app/routes/auth.py` | Auth endpoints (Google sign-in, profile) |
| `backend/app/routes/user.py` | User data endpoints (pins, team search, onboarding, preferences) |
| `frontend/app/onboarding/page.tsx` | 5-step onboarding flow (location, follow, alma maters, sports+beyond, rivals) |
| `frontend/components/OnboardingBanner.tsx` | CTA banner for authenticated users who haven't onboarded |
| `backend/app/routes/feed.py` | Unified feed endpoint (events + futures, personalized, my_teams_only filter) |
| `backend/app/routes/market_moves.py` | "Market Was Wrong" — post-game market shifts |
| `backend/app/routes/oscars.py` | Oscars landing page — cross-source odds aggregation |
| `frontend/app/oscars/page.tsx` | Oscars frontend — TMDB-enriched award categories |
| `frontend/lib/tmdb.ts` | TMDB API client (movie posters, headshots, trailers) |
| `backend/app/utils/prediction_market_matching.py` | Game-level market detection, ticker parsing, team matching |
| `backend/app/tasks/prediction_market_matching.py` | Prediction market → event linking + snapshot writing |
| `frontend/components/SearchBar.tsx` | Typeahead search with 200ms debounce and keyboard nav |
| `frontend/app/market-moves/page.tsx` | "Market Was Wrong" page — post-game odds shifts |
| `frontend/app/search/page.tsx` | Search results page |
| `frontend/lib/firebase.ts` | Firebase config, sign-in/sign-out functions |
| `frontend/hooks/useAuth.ts` | Auth state hook |
| `frontend/components/AuthProvider.tsx` | Auth context provider |
| `docs/auth-personalization-plan.md` | Full auth + personalization implementation plan |
| `docs/tv-mode-plan.md` | TV Mode design plan (layouts, iOS v2 features, implementation phases) |
| `tv-mode-prototype.jsx` | Interactive TV Mode prototype (React, device switching, all layouts) |
| `docs/PRD.md` | Full product requirements and roadmap |

---

## Development Workflow

Development happens primarily through **Claude Code on the web** (GitHub-based). There is no local dev environment.

- **Backend** and **frontend** auto-deploy from `master` via Heroku and Vercel respectively
- **Database migrations**: Create with `alembic revision --autogenerate -m "description"`, applied automatically on Heroku release (`alembic upgrade head`)
- **Testing changes**: Push to master and verify on production, or use Heroku/Vercel preview deployments
- **Session start hook**: `.claude/hooks.json` auto-installs backend (`pip`) and frontend (`npm`) dependencies when a new Claude Code web session starts. Tests should work immediately without manual setup.
- **Running tests**:
  - Backend: `cd backend && python -m pytest tests/ -v` (requires `sqlalchemy`, `asyncpg`, `pydantic`, `openai`, `httpx`)
  - Frontend: `cd frontend && npx jest` (requires `jest`, `ts-jest`, `@types/jest` — already in devDependencies)
  - Backend tests cover (1591+ pytest items across 20 files): Pulse algorithm, Highlights scoring (incl. Level 2 time-series metrics, event importance), odds math, futures categorization rules, LLM classification (mocked), win probability model, team linking, stale bookmaker filtering, snapshot collapse (pure-function + SQL simulation), task wiring, odds polling helpers, ESPN API parsing (both endpoint formats, season type, injury/news parsing), redis state hashing, win prob source config, onboarding (metro aliases, sport affinity expansion/compression, reverse mapping), prediction market matching (291 tests: ticker detection, ticker abbreviation parsing, ticker fragment matching, name building, false positives, sport prefix mapping, ticker fallback, live poll wiring, matchup-name outcome fallback, prop/spread outcome filtering), retention SQL (19 tests: CTE logic simulation, table config, NULL handling), MLB Stats API (33 tests: team matching, schedule parsing, win probability), stale bookmaker filter (23 tests: valid_until dedup, recency filter), line movement (26 tests: detection thresholds, direction classification, prompt building with injuries/news/game context). See `docs/test-coverage-analysis.md` for full breakdown.
  - Frontend tests cover (117+ tests across 4 files): sportCategories (prefix matching, futures categorization, athlete disambiguation), pinned storage logic, EventCard, API client

### Querying the Production API

Use `curl` against the production API to inspect data:
```bash
curl "https://api.bainluck.com/api/events?sport=americanfootball_nfl"
curl "https://api.bainluck.com/api/events/search?q=celtics"
curl "https://api.bainluck.com/api/admin/pulse/status"
```

**Note:** When running in Claude Code's web sandbox, direct HTTP requests to the production API may be blocked by egress restrictions. The MCP proxy at `tools/mcp-api-proxy/` is designed for local Claude Code CLI usage only.

---

## Environment Variables

Backend and frontend environment variables are configured in **Heroku** and **Vercel** respectively (not local `.env` files).

### Backend (Heroku Config Vars)
- `ODDS_API_KEY` - From the-odds-api.com
- `KALSHI_API_KEY` - From kalshi.com (optional - enables Kalshi polling)
- `OPENAI_API_KEY` - From platform.openai.com (optional - enables LLM categorization)
- `DATABASE_URL` - PostgreSQL connection string (managed by Heroku Postgres)
- `REDIS_URL` - Redis for Celery (managed by Heroku Redis)
- `ADMIN_SECRET` - Optional: protect admin endpoints
- `SENTRY_DSN` - From sentry.io (optional - enables error tracking + performance monitoring)
- `SENTRY_ENVIRONMENT` - Defaults to "production" if unset
- `SPORTSDATA_API_KEY` - **Removed** — no longer needed (roster sync uses ESPN + MLB Stats API)
- `MYSPORTSFEEDS_API_KEY` - From mysportsfeeds.com (optional — enables structured injury/lineup data for "Why Did the Line Move?", pending account approval)
- `FIREBASE_PROJECT_ID` - Firebase project ID (optional - enables auth)
- `FIREBASE_SERVICE_ACCOUNT_JSON` - Full service account JSON string (optional - for admin operations)

### Frontend (Vercel Environment Variables)
- `NEXT_PUBLIC_API_URL` = `https://api.bainluck.com`
- `NEXT_PUBLIC_FIREBASE_API_KEY` - Firebase web API key (optional - enables auth UI)
- `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` - Firebase auth domain (e.g., `project-id.firebaseapp.com`)
- `NEXT_PUBLIC_FIREBASE_PROJECT_ID` - Firebase project ID
- `NEXT_PUBLIC_GA_MEASUREMENT_ID` - Google Analytics
- `NEXT_PUBLIC_TMDB_API_KEY` - TMDB Read Access Token (v4 Bearer auth, used for Oscars page movie posters/headshots)

---

## Key Features

### Pulse (Game Excitement Metric)
Proprietary 1-100 score measuring how exciting a game is based on probability swings.

**Two-layer scoring:**
1. **Raw score**: Deterministic calculation from odds movement data (stored as `raw_gei` on events)
2. **Percentile score**: Raw score mapped to percentiles using completed/closed games as reference set. This is the score shown to users. Falls back to raw score if percentiles unavailable.

**Components (weighted):**
- Heart Rate (25%): Frequency of significant moves (≥2% threshold). Normalized: moves/min ÷ 0.6
- Amplitude (30%): RMS magnitude of probability swings. Normalized: RMS ÷ 0.15
- Arrhythmia (15%): Unpredictability (stdev of deltas). Normalized: stdev ÷ 0.10
- Vitals (30%): Average closeness to 50% across all snapshots (rewards games that stayed competitive throughout, not just those that ended close)
- Lead Changes: Bonus for 50% crossings (5 pts each, max 20 pts)
- Time Weight: Late-game multiplier `0.6 + 0.4 × (progress^1.5)`

**Normalization tuning history:**
The normalization ceilings were tuned iteratively using `GET /api/admin/pulse/distributions` to analyze score distributions across completed games. Key issue was Heart Rate saturating at 100% for 26% of games (ceiling too low at 0.3), then compressing below 38% (ceiling too high at 1.5). Final ceiling of 0.6 was derived from observed max rate of ~0.57 moves/min.

**Multi-bookmaker aggregation:** Raw odds snapshots come from multiple bookmakers (5-11 per event). Before Pulse calculation, snapshots are aggregated into 60-second time buckets using median probability (`_aggregate_snapshots` in `pulse.py`). This prevents bookmaker disagreements from being counted as odds movements. Without aggregation, even an unremarkable game can score 100 due to phantom lead changes and inflated movement metrics.

**Scaling:** Raw Pulse score is divided by 1.0 and mapped to 1-100. The theoretical max raw score is ~1.2 (all components maxed + lead change bonus), which clamps to 100. A typical close game scores 60-75; scoring 100 requires exceptional movement across all dimensions.

**Files:** `backend/app/utils/pulse.py`, `frontend/components/PulseBadge.tsx`

**Admin Endpoints:**
- `GET /api/admin/pulse/status` - Check calculation status
- `GET /api/admin/pulse/distributions` - Score and component distribution analysis (histograms, saturation, statistics)
- `POST /api/admin/pulse/recalculate?secret=xxx&limit=100` - Trigger batch recalc (completed + closed events)

**After algorithm changes:** You must force-recalculate stored scores since `raw_gei` values are computed once and cached:
```bash
curl -X POST "https://api.bainluck.com/api/admin/pulse/recalculate?secret=any&limit=500"
# Then verify with distributions endpoint:
curl "https://api.bainluck.com/api/admin/pulse/distributions"
```

**Hall of Fame filtering:** The `pulse-rankings` endpoint requires 20+ distinct minute-level time buckets (not raw snapshot rows, since each poll captures 5-11 bookmakers). Completed events with `data_quality == "minimal"` (< 10 aggregated time buckets) never get a stored Pulse score, providing a second layer of filtering.

### Highlights (Event Ranking)
Scores events 0–100 to decide what appears in the homepage Highlights section. Events need ≥30 points. This is **Level 1 (snapshot scoring)** of a multi-level ranking system — see "Ranking & Feed Evolution" in `docs/PRD.md` for the full roadmap toward the iOS feed tab.

**Key design rule:** Pre-game closeness (e.g., 51/49) doesn't award points unless there's trend evidence — the line moved ≥5% from opening, tightened from lopsided to close, or the game is starting soon. This prevents aggregation noise from surfacing uninteresting events.

**Labels:** "Upset brewing" and "Close game" are live-only. "Line moving" requires ≥15% swing from opening. "Close matchup" requires starting soon. "Championship game" and "Playoff game" show for pre-game events with matching `llm_importance`.

**Two-level scoring:**
- **Level 1** (always): Opening odds vs current (two points in time). Flags: live, close, upset, starting soon, line movement.
- **Level 2** (when snapshots available): Time-series analysis from `odds_snapshots`. Computes `TimeSeriesMetrics` (volatility RMS, lead changes, recent momentum). Only for live events with 3+ aggregated time buckets. Batch SQL query in the feed endpoint keeps it fast.

**League tier system (critical for anonymous feed quality):**
4-tier system that ensures major leagues dominate the anonymous feed:
- **Tier 1** (+20 pts): NBA, NFL, MLB, NHL, EPL, La Liga, Champions League
- **Tier 2** (+10 pts): NCAAF, NCAAB, WNBA, MLS, Bundesliga, Serie A, Ligue 1, MMA, tennis Grand Slams, golf Majors
- **Tier 3** (0 pts): Liga MX, Brazilian Serie A, boxing
- **Tier 4** (-15 pts): Everything not in the map (minor leagues, obscure international)

**Event importance scoring:**
The `llm_importance` field on events (populated by ESPN `season.type` and LLM text classification) feeds into `compute_highlight()`:
- **Championship** (+25 pts): Championship/final games — always surfaces
- **Playoff** (+15 pts): Postseason/playoff games — significant boost
- **Exhibition** (-20 pts): Preseason/all-star — deprioritized
- **Regular season** / **None**: No change (backward compatible)

A playoff NFL game scores 30 (live) + 20 (tier 1) + 15 (playoff) = **65** base. A preseason NBA game scores 30 + 20 + (-20) = **30** base. A far-future playoff NBA game scores 20 (tier 1) + 15 (playoff) = **35** even without any odds signals.

**Files:** `backend/app/utils/highlights.py`, `backend/app/utils/futures_highlights.py`, `frontend/app/page.tsx` (feed rendering)

### Odds Polling
- Live games: Every 30 seconds
- Upcoming games: Every 2-5 minutes based on proximity
- Event discovery: Every 15 minutes (finds new games)

**Key task:** `poll_all_odds` in `backend/app/tasks/odds_polling.py`

### Probability Display by Game Status
Different game statuses show different probability data to users:
- **Scheduled**: Current betting consensus (`current_odds`)
- **Live**: Current live odds (big) + "Opened X/Y" reference from `opening_odds` (small)
- **Completed/Closed**: Opening odds (pre-game consensus) + Pulse excitement score

**Opening odds** are the last pregame consensus — `_maybe_set_opening_odds` in `tasks/odds_polling.py` updates them with the cross-bookmaker average on every poll while the event is scheduled, then freezes when the game starts. Stored on the `Event` model.

**Stale bookmaker filtering**: `filter_stale_bookmaker_snapshots()` in `app/utils/odds_filtering.py` uses `_effective_time()` which prefers `valid_until` over `captured_at` (correctly handles write-time dedup). Two-layer filtering: (1) exclude bookmakers not confirmed since `commence_time`, (2) for live events, exclude bookmakers >10 min older than the freshest bookmaker. Runs for ALL non-scheduled statuses (live, completed, closed). Has 23 regression tests in `tests/test_stale_bookmaker_filter.py`.

**Frontend cross-check** (event detail page only): Compares `current_odds` against the history endpoint's latest time-bucketed consensus. If they diverge >5% for live games, trusts history. This catches cases where the backend filter doesn't fully solve the stale bookmaker problem.

**Surfaces**: EventCard (homepage) and event detail page both implement the status-based pattern. TV mode still uses raw `current_odds` (not yet updated).

**Files:** `backend/app/utils/odds_filtering.py`, `frontend/app/events/[id]/page.tsx`, `frontend/components/EventCard.tsx`

### Search
- Endpoint: `GET /api/events/search?q=celtics`
- Searches both events (by team name) and futures markets (by market name)
- Trigram indexes for fast ILIKE matching on `events.home_team_name`, `events.away_team_name`, and `futures_markets.name`
- Events ordered: Live → Upcoming → Completed
- Returns `results` (events) and `futures` (markets) arrays

### Kalshi Integration
Kalshi is a prediction market that provides structured event data including timing (when events start/end).

**Why Kalshi?** The Odds API doesn't provide `commence_time` for futures markets. Kalshi does, so futures from Kalshi will have proper start dates displayed.

**Files:**
- `backend/app/services/kalshi_api.py` - API client
- `backend/app/tasks/kalshi.py` - `poll_kalshi_markets` task (runs hourly at :45)

**Category Filter (IMPORTANT):**
Kalshi has thousands of markets (politics, economics, etc.) but we only want sports.
To stay within rate limits, we filter to specific categories.

**To change which categories are fetched**, edit this line in `backend/app/tasks/kalshi.py`:
```python
sports_categories = ["Sports", "Golf", "Football", "Basketball", "Baseball", "Hockey", "Tennis"]
```

**Rate Limiting:**
- Kalshi has strict rate limits (~10 req/sec)
- We add 0.5s delay between paginated requests
- Limited to 10 pages max per poll
- If you see 429 errors, wait a minute and try again

**Admin Endpoints:**
```bash
# Trigger a poll (queues background task, returns task_id)
curl -X POST "https://api.bainluck.com/api/admin/kalshi/poll?secret=any"
# Response: {"status": "queued", "task_id": "abc123...", "message": "..."}

# Check task status (use task_id from above)
curl "https://api.bainluck.com/api/admin/kalshi/task/abc123?secret=any"
# Response: {"task_id": "abc123", "state": "SUCCESS", "result": {...}}
```

**Note:** Polling runs as a background Celery task to avoid Heroku's 30-second HTTP timeout.

**Data Model:**
- Kalshi events → `futures_markets` table (source="kalshi")
- Kalshi markets → `futures_outcomes` table
- Stores bid/ask spreads: `yes_bid`, `yes_ask`, `last_price`
- Populates `commence_time` (event start) and `resolution_date` (market close)

### Polymarket Integration
Polymarket is the world's largest prediction market (~$9B valuation). Unlike Kalshi, it requires **no API key** for read access and has significantly better rate limits and sports coverage.

**Why Polymarket?** Three strategic reasons:
1. **More sports markets** — 3,294+ active sports markets with NHL and UFC partnerships, extensive soccer coverage (EPL, La Liga, UCL, Bundesliga, Serie A, MLS, etc.)
2. **Wildcard categories** — Politics, entertainment, crypto, weather, and geopolitics markets that expand Bain Luck beyond sports into "probability of anything"
3. **Built-in historical data** — `/prices-history` endpoint provides time-series data (configurable granularity) without requiring us to poll and store every snapshot

**API Architecture (4 services, only 2 needed):**
| Service | Base URL | Purpose | Auth |
|---------|----------|---------|------|
| **Gamma API** | `https://gamma-api.polymarket.com` | Market discovery, metadata, tags, sports | **None** |
| **CLOB API** | `https://clob.polymarket.com` | Prices, order book, price history | **None** (read) |
| Data API | `https://data-api.polymarket.com` | User positions (not needed) | Yes |
| WebSocket | `wss://ws-subscriptions-clob.polymarket.com` | Real-time updates (not needed for polling) | Varies |

**Key Gamma API endpoints:**
- `GET /events` — List events with filtering (tag_id, series_id, active, closed, volume, liquidity)
- `GET /sports` — Discover supported sports/leagues with series_id and tag_id metadata
- `GET /markets` — List markets with filtering
- `GET /tags` — Discover all categories

**Key CLOB API endpoints:**
- `GET /prices-history?market={token_id}&interval=max&fidelity=60` — Historical price time series
- `GET /midpoint?token_id=X` — Mid-market price
- `GET /price?token_id=X&side=buy` — Best bid/ask

**Rate Limits:** ~1,000 calls/hour (Cloudflare throttling, much more generous than Kalshi's ~10 req/sec)

**Data Model Mapping:**
| Polymarket | Bain Luck DB |
|------------|----------------|
| Event | `FuturesMarket` (source="polymarket") |
| Event.id | `FuturesMarket.external_id` |
| Event.title | `FuturesMarket.name` |
| Event.tags | Used for `llm_sport_category` / categorization |
| Market (per outcome) | `FuturesOutcome` |
| Market.conditionId | `FuturesOutcome.external_id` |
| Market.outcomePrices[0] | `FuturesOutcome.current_probability` |
| Market.lastTradePrice | Snapshot `last_price` |
| CLOB bid/ask | `current_yes_bid` / `current_yes_ask` |

**Parsing gotcha:** `outcomes`, `outcomePrices`, and `clobTokenIds` are returned as **stringified JSON arrays** (e.g., `"[\"Yes\", \"No\"]"`) and must be parsed with `json.loads()`.

**NegRisk events:** Multi-outcome events (e.g., "NBA Championship Winner") have one binary market per team, each with Yes/No shares. Maps naturally to our FuturesOutcome model (same as Kalshi multi-market events).

**Files:**
- `backend/app/services/polymarket_api.py` — API client (Gamma + CLOB, no API key needed)
- `backend/app/tasks/polymarket.py` — Polling task with streaming pagination (batched commits, page cap warning)
- `backend/tests/test_polymarket.py` — 69 tests (tag mapping, name extraction, API parsing)

**Polling architecture:** Events are fetched page-by-page (100 per page, 0.3s delay) and processed in batches of 50 to limit memory. Categorization uses a 160+ entry tag-to-category map with fallback to `futures_categorization.py` rules + league detection. Stats include `pages_fetched`, `unique_events_seen`, and `hit_page_cap` for monitoring.

**Admin endpoints:**
```bash
# Trigger a poll
curl -X POST "https://api.bainluck.com/api/admin/polymarket/poll?secret=any"

# Backfill price history (fetches CLOB /prices-history for outcomes with <24 snapshots)
curl -X POST "https://api.bainluck.com/api/admin/polymarket/backfill-history?secret=any&limit=50"

# Check task status
curl "https://api.bainluck.com/api/admin/polymarket/task/{task_id}?secret=any"
```

**Non-sports categories to enable:**
| Category | Examples |
|----------|---------|
| Politics | Elections, approval ratings, policy decisions |
| Entertainment | Oscars, box office, Nobel Prize, reality TV |
| Crypto | Bitcoin price targets, ETF approvals |
| Economy | Fed rate cuts, inflation, GDP |
| Tech/AI | AI benchmarks, SpaceX launches |
| Weather | Daily temperatures, natural disasters |

**Legal note:** Polymarket's ToS prohibits US persons from *trading*, but the read-only API is globally accessible. Our integration only displays probabilities — no trading functionality.

**Comparison to Kalshi:**
| Dimension | Kalshi | Polymarket |
|-----------|--------|------------|
| Auth | API key required | None (fully public) |
| Rate limits | Strict (~10 req/sec) | Generous (~1,000/hr) |
| Sports markets | Hundreds | 3,294+ |
| Price format | Cents (0-100) | Decimal (0.00-1.00) native |
| Historical prices | None (must poll) | Built-in `/prices-history` |
| Non-sports | Limited | Extensive (politics, crypto, weather, etc.) |
| Liquidity | Lower | Highest in market |

### Sport Categorization (Futures)
Futures markets are categorized using a hybrid approach: pattern matching rules + LLM fallback.

**How it works:**
1. Check `llm_sport_category` from database (cached LLM result)
2. Try prefix matching on sport key (e.g., `golf_masters` → Golf)
3. Try regex patterns on market name (e.g., "College Football Playoff" → Football)
4. Handle sport-specific awards (AL MVP → Baseball, Hart Trophy → Hockey, etc.)
5. Use athlete name detection for ambiguous markets like "US Open"
6. Fall back to LLM (GPT-4o-mini) for uncategorized markets
7. LLM always returns a category (never NULL) — defaults to "other"

**Supported categories (23):**
football, basketball, baseball, hockey, golf, tennis, soccer, mma, motorsports, boxing, cricket, rugby, aussierules, horse_racing, olympics, esports, entertainment, politics, lacrosse, chess, poker, darts, other

**Files:**
- Frontend patterns: `frontend/lib/sportCategories.ts`
- Backend patterns: `backend/app/utils/futures_categorization.py`
- LLM service: `backend/app/services/llm.py`

**To add new patterns**, edit `SPORT_PATTERNS` in `sportCategories.ts` or `futures_categorization.py`:
```python
# Backend
SPORT_PATTERNS = [
    (re.compile(r"\b(mlb|world.series)\b", re.I), "baseball"),
    (re.compile(r"\bcollege.football\b", re.I), "football"),
    # Add new patterns here...
]
```

**Important:** Pattern order matters — more specific patterns (e.g., `defensive.player.of.the.year` → football) should come before broader ones (e.g., `defensive.player` → basketball). The LLM handles everything patterns miss, so only add patterns for high-volume categories to save API costs.

**Known limitation:** Some Kalshi markets have ambiguous names like "MVP Winner?" without any sport context. These correctly categorize as "other" since there's no way to determine the sport. Improving Kalshi category pass-through would help here.

**Admin endpoints:**
```bash
# Check categorization status
curl "https://api.bainluck.com/api/admin/futures/categorization-status"

# Trigger LLM categorization (requires OPENAI_API_KEY)
curl -X POST "https://api.bainluck.com/api/admin/futures/categorize?secret=xxx&limit=50"

# Dry run (preview without saving)
curl -X POST "https://api.bainluck.com/api/admin/futures/categorize?secret=xxx&dry_run=true"

# View uncategorized markets (diagnostic)
curl "https://api.bainluck.com/api/admin/futures/uncategorized"

# Force-categorize all remaining via LLM
curl -X POST "https://api.bainluck.com/api/admin/futures/force-categorize?secret=xxx&limit=100"
```

**Debug endpoints:**
```bash
# See futures count by source (odds_api vs kalshi vs polymarket)
curl "https://api.bainluck.com/api/futures/debug/sources"

# See sport linking for futures
curl "https://api.bainluck.com/api/futures/debug/sport-mapping"
```

### Pinned Events & Futures
Users can pin events and futures markets they want to track closely. Pinned items appear in dedicated sections at the top of the homepage.

**Features:**
- Pin/unpin events and futures from any card or detail page
- Pinned sections appear above Highlights on homepage
- Maximum 6 pinned events + 6 pinned futures
- Works for events outside the 7-day window (e.g., Super Bowl weeks away)
- Cross-tab sync via localStorage storage events
- Separate limits for events vs futures

**Storage:**
Currently uses localStorage (no auth required). When Firebase Auth is added, this can be upgraded to database-backed storage for cross-device sync.

```javascript
// localStorage keys
bainluck_pinnedEvents    // Array of event IDs
bainluck_pinnedFutures   // Array of futures market IDs
```

### SportsDataIO Integration (Removed)
SportsDataIO previously provided roster data. **Fully replaced** by ESPN roster endpoints + MLB Stats API at zero cost. The `sportsdata_api.py` client has been deleted. `SPORTSDATA_API_KEY` is no longer needed.

**Roster Sync:** `backend/app/tasks/roster_sync.py` (`_sync_rosters`)
- Uses ESPN `/teams/{id}/roster` endpoint for NBA, NFL, NHL, NCAAB, NCAAF, WNBA, MLS, EPL
- Uses MLB Stats API for baseball
- Beat schedule: daily at 7:00 AM UTC (`sync-rosters-daily`)
- Stores deduplicated, sorted player name list on `Team.roster_players` JSONB column

**Admin endpoints:**
```bash
# Trigger roster sync (all sports or specific)
curl -X POST "https://api.bainluck.com/api/admin/rosters/sync?secret=any"
curl -X POST "https://api.bainluck.com/api/admin/rosters/sync?secret=any&sport_key=basketball_nba"

# Check task status
curl "https://api.bainluck.com/api/admin/rosters/task/{task_id}?secret=any"
```

### Related Futures (Event → Futures Linking)
Shows championship odds, MVP odds, award futures, upcoming game moneylines, and game-specific stat props relevant to teams playing in a specific game. The "Bigger Picture" section on event detail pages.

**Endpoint:** `GET /api/events/{id}/related-futures`

**Matching strategy (hybrid):**
1. **Name ILIKE** — Team names, short names (≥4 chars), alternate names, and roster player names matched against `FuturesOutcome.name`
2. **team_id lookup** — Supplementary matching via `FuturesOutcome.team_id` (populated by backfill task)
3. **Market name ILIKE** — Team names matched against `FuturesMarket.name` for game props where outcome names are generic ("Over 218.5")
4. Combined via OR for maximum recall

**Sport filtering (triple strategy via OR):**
- `FuturesMarket.external_id LIKE prefix%` (e.g., "basketball%")
- `FuturesMarket.llm_sport_category` matches mapped category
- `FuturesMarket.sport_id` matches compatible sport IDs

**Game-specific stat prop filtering (backend):**
Stat prop markets (e.g., "Boston at Golden State: Points") are tied to a single game. The backend filters these so they only appear on the correct event's detail page. Detection uses `_GAME_STAT_PROP_RE` (regex matching ": Points", ": Rebounds", ": Double Doubles", etc.). Matching uses `event_id` equality or ±6h temporal proximity on `commence_time`/`resolution_date`. Game moneylines (e.g., "Lakers vs Nuggets") are NOT filtered — they pass through as "Upcoming Games" context. Season-long markets (championship, MVP, awards) always show.

**Key helpers** (in `events.py`):
- `_SPORT_PREFIX_TO_LLM_CATEGORY` — Maps sport key prefixes to LLM categories
- `_GAME_STAT_PROP_RE` / `_GAME_MATCHUP_RE` — Module-level compiled regex for game-specific market detection
- `_is_stat_prop_market()` / `_stat_prop_matches_event()` — Per-request closures using event commence_time
- `_team_name_patterns()` — Builds ILIKE-safe patterns from team names
- `_escape_like()` — Escapes `%`, `_`, `\` for safe ILIKE patterns

**Frontend tier system (`effectiveTier()` in `RelatedFutures.tsx`):**
Pattern-based tier detection overrides backend `market_tier` when needed. Checked in priority order:
1. **Tier 6 (stat props)**: `STAT_PROP_PATTERNS` — ": Points", ": Rebounds", ": Double Doubles", etc. + "Team at Team: Stat" format. Displayed as Player Stats cards with semi-circular SVG gauges and headshots.
2. **Tier 5 (game markets)**: `GAME_MARKET_PATTERNS` — "vs.", "–", "Moneyline", "Game N". Displayed in dense 2-column Upcoming Games grid.
3. **Tier 3 (awards)**: `AWARD_PATTERNS` — 18 patterns including MVP, Golden Boot/Glove, Cy Young, Rookie, Player of Year, etc. Displayed as player-centric rows with headshots. Deduplicated by `normalizeName(outcome) + "::" + shortAwardLabel(market)`.
4. **Tier 4 (downgraded)**: `NOT_CHAMPIONSHIP_PATTERNS` — 14 patterns preventing non-championship markets from being hero cards (Win Totals, Make Playoffs, Seeding, Over/Under wins, Cover of NBA 2K, etc.)
5. **Tier 1-2 (backend)**: Trust backend `market_tier` for championship/conference if no pattern overrides.

**Title Comparison bar:** Uses `findBestChampionship()` which prefers markets with "championship" in the name over other tier-1 markets, preventing "Make Playoffs" (94%) from displaying instead of actual championship odds (2%).

**Cross-sport false positive prevention:** `GameMarketsGrid` verifies the market name contains the team name (or short name ≥4 chars) before displaying. Catches backend sport-filter leaks like hockey markets appearing on basketball event pages.

**Player headshots:** `PlayerHeadshot` component with priority chain: `matched_player.headshot` (direct ESPN URL from roster) → ESPN `espn_id` → Wikipedia → colored initials fallback. The `matched_player` metadata comes from `Team.roster_players` JSONB (populated by daily roster sync).

**LLM Summary:** `generate_related_futures_summary()` in `llm.py` generates a 2-3 sentence casual summary of championship/award implications using GPT-4o-mini. Cached in `LineMovementAnalysis` table with `analysis_type="related_futures"`. TTL: 2 hours for live/scheduled games, never expires for completed. Returned as `"summary": str | null` in the endpoint response. Gracefully degrades when `OPENAI_API_KEY` is not set.

**Files:**
- Backend endpoint: `backend/app/routes/events.py` (related-futures section + stat prop filtering + LLM summary caching)
- Frontend component: `frontend/components/RelatedFutures.tsx` (~1200 lines — tier detection, stat prop cards, award cards, game grid, headshots, dedup)
- LLM generation: `backend/app/services/llm.py` (`generate_related_futures_summary`)
- Team linking utility: `backend/app/utils/team_linking.py`
- Tests: `backend/tests/test_team_linking.py` (11 tests for helpers)

### ESPN Integration
ESPN's undocumented API provides team data (colors, logos) and live game info (clock, period, win probability).

**Data Enrichment:**
- **Teams**: ESPN ID, primary/secondary colors, logos (small/large), alternate names, current record
- **Events**: ESPN ID, venue, broadcast info, game clock, period, ESPN win probability, season type (→ `llm_importance`)
- **Venues**: Name, city, state, country, capacity

**Automatic Sync (Celery task `sync_espn_live_events`):**
- Runs every 60 seconds
- Auto-creates Team records with colors, logos, and alternate names from ESPN scoreboard data
- Updates live events with game clock, period, broadcast info, and win probability
- Also pre-populates team data for scheduled events (so colors/logos appear before games go live)
- Parses `season.type` (1=preseason, 2=regular, 3=postseason) and writes to `llm_importance` on both live and scheduled events (won't downgrade "championship" to "playoff")
- ESPN win probability is **only available during live games** — cannot be backfilled after a game ends
- Team colors/logos persist in the `teams` table and apply to all events (past and present) via name lookup
- Mapped sports: NBA, NCAAB, WNCAAB, NFL, NCAAF, NHL, MLB, MLS, EPL (see `ESPN_SPORT_MAPPING` in `tasks/config.py`)

**Files:**
- ESPN client: `backend/app/services/espn_api.py`
- Celery sync task: `backend/app/tasks/espn_sync.py` (`_sync_espn_live_events`)
- Team lookup in API: `backend/app/routes/events.py` (`_build_team_lookup`)
- Model columns on teams: `espn_id`, `primary_color`, `secondary_color`, `logo_url_small`, `logo_url_large`, `alternate_names`, `current_record`
- Model columns on events: `espn_id`, `venue_id`, `broadcast_info`, `game_clock`, `period`, `espn_win_prob_home`, `win_probability_sources`

**Frontend display:**
- Team logos and colors on EventCard and event detail page
- Team-colored probability bar
- Broadcast info badge
- ESPN win probability badge (live games only)
- ESPN trend line on OddsChart (orange dashed line)

**Admin endpoints:**
```bash
# Sync team data from ESPN (colors, logos)
curl -X POST "https://api.bainluck.com/api/admin/espn/sync-teams?secret=xxx&sport_key=basketball_nba"

# Check team sync status
curl "https://api.bainluck.com/api/admin/espn/teams-status"

# Sync live event data (clock, period, win prob)
curl -X POST "https://api.bainluck.com/api/admin/espn/sync-live-events?secret=xxx&sport_key=basketball_nba"

# Test team name matching
curl -X POST "https://api.bainluck.com/api/admin/espn/match-teams?secret=xxx&our_team_name=Lakers&sport_key=basketball_nba"

# Fix incorrect commence_time values using ESPN as source of truth
# (backfills completed events — the live sync task handles new ones automatically)
curl -X POST "https://api.bainluck.com/api/admin/espn/fix-commence-times?secret=any&limit=500"
# Check task status:
curl "https://api.bainluck.com/api/admin/espn/task/{task_id}?secret=any"
```

### Authentication & Personalization
Firebase Auth provides Google (and later Apple) Sign-In. The app works fully without login; auth unlocks personalization features.

**Architecture:**
- **Frontend**: Google Identity Services (GIS) OAuth popup → access token → Firebase `signInWithCredential` or backend custom token exchange
- **Backend**: `firebase-admin` verifies ID tokens → upserts user in `users` table → returns profile
- **Auth dependencies**: `get_current_user` (required auth) and `get_optional_user` (optional auth) FastAPI dependencies
- **Anonymous-first**: All existing endpoints work without auth. Personalization is an overlay, not a gate.
- **Pin sync**: Pins migrate from localStorage to `user_pins` table on first login. localStorage continues as fallback for anonymous users.

**Safari compatibility (critical — 3-tier auth fallback):**
Safari ITP blocks `identitytoolkit.googleapis.com`, breaking both `signInWithCredential` AND `signInWithCustomToken`. The solution is a 3-tier fallback with fast timeouts (4s) to prevent hanging:
1. **`signInWithCredential`** (4s timeout) — works on Chrome/Firefox
2. **Backend custom token → `signInWithCustomToken`** (4s timeout) — works when only credential auth is blocked
3. **Backend-only auth** — when Firebase client SDK is fully blocked, the backend issues a PyJWT session token (HS256, 1hr TTL) signed with `ADMIN_SECRET`. Frontend stores in localStorage and uses directly as Bearer token. Backend `verify_id_token()` accepts both Firebase ID tokens and backend session tokens.

**Auth persistence fix:** Firebase uses `initializeAuth` with explicit `browserLocalPersistence` (localStorage) instead of the default `indexedDBLocalPersistence`. Safari ITP aggressively clears IndexedDB for cross-origin resources, causing sign-out on hard refresh.

This requires `FIREBASE_SERVICE_ACCOUNT_JSON` and `ADMIN_SECRET` on the backend.

**Key files for Safari auth:**
- `frontend/lib/firebase.ts` — 3-tier sign-in with `withTimeout()`, `BackendAuthData` localStorage fallback
- `backend/app/services/firebase_auth.py` — `create_session_token()`, `verify_session_token()`, updated `verify_id_token()` to accept both Firebase and session tokens
- `backend/requirements.txt` — Added `PyJWT>=2.8.0`

**Key files:**
- `backend/app/services/firebase_auth.py` — Firebase Admin SDK init, token verification, `get_or_create_firebase_user`, `create_custom_token`
- `backend/app/dependencies/auth.py` — `get_current_user` / `get_optional_user` FastAPI dependencies
- `backend/app/routes/auth.py` — `POST /api/auth/google`, `POST /api/auth/google-access-token` (Safari fallback), `GET /api/auth/me`, profile management
- `backend/app/routes/user.py` — Pin CRUD (`/api/me/pins`), team search (`/api/me/teams/search`)
- `frontend/lib/firebase.ts` — Firebase app config, GIS OAuth flow, two-step sign-in with backend fallback
- `frontend/hooks/useAuth.ts` — Reactive auth state, token management
- `frontend/components/AuthProvider.tsx` — Auth context provider, wires token to API client
- `frontend/components/UserMenu.tsx` — Header sign-in button / user avatar dropdown (Preferences links to `/preferences`)
- `frontend/hooks/usePinSync.ts` — One-way localStorage → server pin migration on first login
- `frontend/app/my-stuff/page.tsx` — "My Teams" page: team-filtered feed (sign-in prompt → onboarding prompt → team feed)
- `frontend/app/preferences/page.tsx` — Settings editor (teams, interests, pinned items, account)
- `frontend/app/onboarding/page.tsx` — 5-step onboarding flow (location → follow → alma maters → sports+beyond → rivals)
- `frontend/components/OnboardingBanner.tsx` — Dismissable CTA banner for authenticated users without preferences

**Database tables:**
- `users` — Firebase UID, email, display name, photo URL
- `user_preferences` — Home location, sport affinities (JSONB), onboarding state, raw onboarding responses
- `user_favorites` — Team relationships with type (follow/local/alma_mater/rival), source, and weight
- `user_pins` — Server-side pin storage (events + futures)

**Environment variables:**
- Backend: `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON` (**required** for Safari sign-in — enables `create_custom_token` and `get_user_by_email`)
- Frontend: `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`

**City → Teams mapping:** ESPN's `location` field on team objects maps cities/regions/schools to teams. The `Team.location` column stores this. A static metro alias map (`METRO_ALIASES` in `user.py`, ~30 entries) groups brand names to metro areas ("New England" → "Boston", "Golden State" → "Bay Area").

**Onboarding flow (shipped):**
5-step single-page stepper at `/onboarding` — invitational (not forced), triggered by CTA banner on homepage for authenticated users who haven't completed onboarding.

Steps:
1. **"Where do you follow sports?"** — Location autocomplete → metro alias expansion → team chips (all selected by default, toggleable)
2. **"Any other favorite teams?"** — General team search, any location. Gets biggest feed boost (+0.5 follow bonus).
3. **"Any alma maters?"** — School autocomplete filtered to college sports (ncaa/wncaab keywords). Falls back to events table for teams without Team records (auto-creates them).
4. **"What do you care about?"** — Grid of sport cards + "Beyond Sports" section (Politics, Entertainment, Crypto, Economics, Tech, Weather, Geopolitics, Culture) with 4-level selector: "Love it" (1.0), "Playoffs only" (0.3), "If it's wild" (0.1), "Nah" (0.0)
5. **"Any rivals?"** — Team autocomplete, "teams you love to hate"

Endpoints:
- `POST /api/me/onboarding` — Batch save all onboarding data (deletes existing onboarding favorites, inserts new, expands sport affinities, sets `onboarding_completed=True`)
- `GET /api/me/preferences` — Returns preferences + favorites with team names/logos, compresses sport affinities to frontend keys
- `GET /api/me/teams/by-location?q=Boston` — Location search with metro alias expansion
- `GET /api/me/teams/search?q=Harvard` — Team search with events table fallback for auto-creation
- `POST /api/me/favorites` — Add single favorite (for inline editing on preferences page)
- `DELETE /api/me/favorites/{team_id}?relation_type=follow` — Remove favorite
- `PUT /api/me/preferences/sport-affinities` — Update sport affinities

**Sport affinity key mapping:** Frontend uses simple keys ("football", "basketball") that expand to backend sport_key format ("americanfootball_nfl", "americanfootball_ncaaf") via `SPORT_AFFINITY_MAPPING` in `user.py`. Non-sports categories (politics, entertainment, crypto, etc.) map to their category name directly. Compression takes the max weight when multiple backend keys map to the same frontend category. Round-trip tested: expand → compress returns original values.

**Full plan:** `docs/auth-personalization-plan.md`

**Page architecture (tabs + settings):**
| Tab/Page | URL | Purpose |
|----------|-----|---------|
| Feed | `/` | Personalized broad discovery feed (events + futures ranked by interestingness) |
| Search | `/search` | Typeahead search results |
| My Stuff | `/my-stuff` | **Team-only filtered feed** — shows only games/futures for user's followed teams |
| Preferences | `/preferences` | **Settings editor** — teams, interests, pinned items, account |

My Stuff has 3 render states:
1. **Not authenticated** → sign-in prompt (no API call)
2. **Authenticated, no teams** → onboarding prompt (links to `/onboarding`)
3. **Has teams** → calls `GET /api/feed?my_teams_only=true` with 15s refresh, wider time windows (24h recent, 7 days upcoming), no min score, no diversity enforcement

UserMenu dropdown "Preferences" links to `/preferences` (not `/my-stuff`). Bottom nav "My Stuff" links to `/my-stuff`.

### Snapshot Data Retention
Consecutive identical snapshot rows are collapsed into single rows with `captured_at` (first seen) and `valid_until` (last confirmed) timestamps. Lossless — original time series is fully reconstructable.

**Tables covered:** `odds_snapshots`, `win_prob_snapshots`, `futures_odds_snapshots`

**Write-time dedup:** `odds_snapshots` and `futures_odds_snapshots` had this since Jan 2026. `win_prob_snapshots` gained it in Feb 2026. Checks last row per (event, bookmaker/source) before inserting; bumps `reading_count` if value unchanged.

**Retroactive collapse:** Celery task `collapse_snapshots` processes one table per invocation. Runs daily via beat schedule (6:30/6:35/6:40 UTC for odds/winprob/futures respectively). Uses pure SQL with PostgreSQL window functions (LAG, SUM) and CTEs — zero rows loaded into Python, constant memory usage regardless of dataset size.

**Admin endpoints:**
```bash
# Trigger collapse for one table (table: odds, winprob, futures)
curl -X POST "https://api.bainluck.com/api/admin/snapshots/collapse?secret=any&table=odds&limit=500"

# Check task status
curl "https://api.bainluck.com/api/admin/snapshots/task/{task_id}?secret=any"

# View current row counts
curl "https://api.bainluck.com/api/admin/snapshots/stats?secret=any"
```

**Files:** `backend/app/tasks/retention.py` (`_collapse_snapshots_impl`, `_collapse_table_for_partition`), `backend/app/routes/admin.py` (snapshot endpoints), `backend/tests/test_snapshot_collapse.py` (13 tests)

### Multi-Source Win Probability
The chart can display win probabilities from multiple independent sources, each as a labeled line with its own color and dash pattern.

**Architecture:**
- **Source registry**: `backend/app/config/win_prob_sources.py` — Python dict (not DB table) defining display_name, color, dash_pattern, methodology, attribution for each source
- **Generic storage**: `win_prob_snapshots` table with `source` column (replaces ESPN-specific storage for new sources)
- **Bain Luck Model**: nflfastR-inspired statistical model in `backend/app/utils/win_probability.py`. Uses normal distribution: score diff + time remaining + pregame spread. Sport-specific params: NFL base_std=13.45, NBA/NCAAB=12.0, NHL=2.5
- **Dual compute paths**: Stat model computes in both ESPN sync (every 60s) AND odds polling (every 30-60s) for redundancy
- **Frontend**: OddsChart.tsx renders N sources dynamically; legend labels link to `/events/[id]/models` detail page

**Current sources (5+2 stubs):**
- **Betting Odds** (market, solid dark line) — consensus from 5-15 sportsbooks via The Odds API
- **ESPN** (model, orange dashed) — ESPN's proprietary predictor, only available during live games
- **Bain Luck Model** (model, purple dashed) — our statistical model, attribution to nflfastR/PFR methodology
- **Kalshi** (market, green `#22c55e`) — prediction market prices from game-level Kalshi markets
- **Polymarket** (market, blue `#3b82f6`) — prediction market prices from game-level Polymarket markets
- **MLB Model** (model, formerly "FanGraphs" key, teal `#0d9488`) — MLB Stats API live win probability (see MLB integration below)
- **MoneyPuck** (stub, cyan `#06b6d4`) — NHL advanced stats, stub only (no public API)

**Supported sports for stat model:** NFL, NCAAF, NBA, NCAAB, WNCAAB, NHL

**Adding a new source:** Add entry to `WIN_PROB_SOURCES` dict in `win_prob_sources.py`, write snapshots to `win_prob_snapshots` with the source key, and the chart/API pick it up automatically.

### MLB Stats API Integration
MLB's official Stats API (`statsapi.mlb.com`) provides live win probability data during baseball games — no API key required.

**Architecture:**
- **API client**: `backend/app/services/mlb_api.py` — `MLBAPIService` with game schedule, live game filtering, context metrics win probability, and play-by-play history
- **Sync task**: `backend/app/tasks/mlb_sync.py` — Celery task that polls live MLB games every 2 minutes, matches to our events, writes `win_prob_snapshots` with source `"fangraphs"` (legacy key)
- **Team matching**: `_name_matches()` uses suffix, mascot extraction, and containment matching (handles "Red Sox" vs "Boston Red Sox")
- **Source config**: `WIN_PROB_SOURCES["fangraphs"]` — display name "MLB Model", color teal `#0d9488`

**Key endpoints:**
- `GET /api/v1/schedule?sportId=1&date=YYYY-MM-DD` — Today's MLB games
- `GET /api/v1/game/{gamePk}/contextMetrics` — Live win probability (percentage, e.g., 65.3)
- `GET /api/v1/game/{gamePk}/winProbability` — Play-by-play win probability history

**Admin endpoints:**
```bash
curl -X POST "https://api.bainluck.com/api/admin/mlb/sync?secret=any"
curl "https://api.bainluck.com/api/admin/mlb/task/{task_id}?secret=any"
```

**Files:** `backend/app/services/mlb_api.py`, `backend/app/tasks/mlb_sync.py`, `backend/tests/test_mlb_api.py` (33 tests)

**ESPN matching resilience (Feb 2026):** The stat model prefers ESPN `game_clock` and `period` data but now has two fallback layers when ESPN name matching fails (common for college teams):
1. **Multi-signal ESPN matching**: ESPN ID first (set during scheduled pre-sync), then name matching, then commence_time proximity (±6h, exactly 1 candidate)
2. **Wall-clock time estimation**: `estimate_seconds_remaining_from_wall_clock()` maps elapsed wall time to game-clock time using sport-specific average durations. Less precise than ESPN clock data but sufficient for a reasonable win probability estimate.

**Known issues (Feb 2026):**
- Wall-clock estimation is approximate — it doesn't account for overtime, delays, or pace variation. ESPN clock data is always preferred when available.
- Stat model can only compute during live games — it cannot be backfilled after a game ends (requires real-time score data).
- PFR is NOT viable as a live data source (no API, ToS blocks scraping, not real-time)

**Sport key aliasing:** The Odds API uses `americanfootball_nfl`/`americanfootball_ncaaf`/`icehockey_nhl` as sport keys, but the stat model's `SPORT_PARAMS` uses `football_nfl`/`football_ncaaf`/`hockey_nhl`. The `_normalize_sport_key()` function in `win_probability.py` handles this mapping. Basketball keys match natively. If you add a new sport, make sure to test with the actual database sport key.

**Files:** `backend/app/config/win_prob_sources.py`, `backend/app/utils/win_probability.py`, `backend/tests/test_win_probability.py` (67 tests), `frontend/components/OddsChart.tsx`, `frontend/app/events/[id]/models/page.tsx`

### Prediction Market → Event Matching
Links Kalshi and Polymarket game-level markets (e.g., "NBA: Celtics at Warriors") to Event records so they appear as win probability trend lines on the OddsChart.

**Architecture:**
- **Detection**: `utils/prediction_market_matching.py` — regex-based game-level detection, fuzzy team name matching, Kalshi ticker parsing
- **Matching task**: `tasks/prediction_market_matching.py` — Celery task that links FuturesMarkets to Events and writes `win_prob_snapshots`
- **Source registry**: `win_prob_sources.py` already has Kalshi (green `#22c55e`) and Polymarket (blue `#3b82f6`) entries
- **Beat schedule**: `match_prediction_markets` runs every 15 min at `:05, :20, :35, :50`; `poll_live_prediction_markets` runs every 2 min (only fetches prices for markets linked to live events)

**Two-pass matching strategy (Phase 1):**
1. **Pass 1 — Targeted ticker scan**: Queries `FuturesMarket` by Kalshi game ticker patterns (`KXNBAGAME%`, `KXNFLGAME%`, etc.) with no limit. Uses `extract_matchup_with_ticker_fallback()` which tries name-based extraction first, then ticker abbreviation parsing, with `_find_event_by_sport_and_time()` as last resort when both fail.
2. **Pass 2 — Matchup-prioritized scan**: Two sub-queries to maximize game-level coverage: (a) markets with matchup name patterns (`% vs.%`, `% vs %`, `% – %`) get full scan budget (500), (b) remaining non-matchup markets get 20% budget (100) for edge cases. This prevents non-game markets (politics, crypto, weather — 13,000+ Polymarket markets) from crowding out game markets like "Celtics vs. Lakers". Result: 4x more game-level detections (392 vs 90) and 143 new links per run vs 0.

**Polymarket CLOB price history backfill:** When a Polymarket market is first linked to an event, the matching task automatically backfills `win_prob_snapshots` from Polymarket's `/prices-history` endpoint. This fills in the trend line from market creation (typically days before the game) rather than starting from the link timestamp. Uses fidelity=30 (30-minute intervals) for smooth chart rendering.

**Kalshi game ticker format**: `KXNBAGAME-26FEB19BOSGSW` = sport prefix + date + team abbreviations. Supported prefixes (12 sports): `kxnbagame`, `kxnflgame`, `kxnhlgame`, `kxmlbgame`, `kxncaabgame`, `kxncaafgame`, `kxwnbagame`, `kxmlsgame`, `kxsoccergame`, `kxufcfight`, `kxboxingfight`, `kxlolgame`.

**Ticker abbreviation parsing (Feb 2026):** `extract_teams_from_ticker()` parses team abbreviations directly from Kalshi tickers. Example: `KXNBAGAME-26FEB21DETCHI` → `("Pistons", "Bulls")`. This is the primary matching path for generic-named Kalshi markets like "Professional Basketball Game" which have no team names in the title. Maps 100+ abbreviations across NBA (30), NFL (~30), NHL (~32), MLB (~30) with sport-specific disambiguation suffixes. The extracted team names feed into `_find_matching_event()` for fuzzy matching against event team names. The combined function `extract_matchup_with_ticker_fallback()` is used across all 4 matching codepaths (Pass 1 link, Pass 2 link, Phase 2 snapshots, live polling snapshots).

**Sport+time fallback (last resort)**: When both name extraction and ticker abbreviation parsing fail, `get_sport_prefix_from_ticker()` maps the ticker to a sport_key prefix, then `_find_event_by_sport_and_time()` finds events within ±6 hours. Only links if exactly 1 event matches (avoids ambiguity). This fails when multiple games exist in the same sport on the same day — the ticker abbreviation parser above was built to solve this.

**Dash matchup false positive prevention**: The regex `Team A – Team B` pattern is validated by `_looks_like_team_name()` to reject false positives like "English Premier League – 2nd Place" or "The Masters - Winner".

**Both-teams matching gate**: `_score_candidates` requires BOTH `team_a` and `team_b` to fuzzy-match the event when both are available. Prevents "Thunder vs. Pistons" matching "Bulls vs. Pistons" and "Pistons vs. Bulls" matching "Georgia Southern vs South Florida Bulls".

**Sport category scoring**: `_score_candidates` adds a +5 bonus when the market's sport (from ticker prefix or `llm_sport_category` via `_SPORT_CATEGORY_TO_KEY_PREFIX`) matches the event's sport. Prevents cross-sport mislinks.

**Polymarket matchup-named outcome fallback**: `find_moneyline_outcome` handles Polymarket outcomes named with the full matchup (e.g., "Pistons vs. Bulls" instead of a single team name). Checks that both matchup teams appear in the outcome name and rejects outcomes with ":" (spreads/totals).

**Phase 1.5 stale link cleanup**: Scans ALL linked markets (not just completed/closed events) and verifies both teams match. Mislinked markets are re-linked to a better match or unlinked entirely.

**Admin endpoints:**
```bash
# Trigger matching
curl -X POST "https://api.bainluck.com/api/admin/prediction-markets/match?secret=any"

# Check status (linked vs unlinked counts)
curl "https://api.bainluck.com/api/admin/prediction-markets/status?secret=any"

# Debug funnel (where markets drop off)
curl "https://api.bainluck.com/api/admin/prediction-markets/debug?secret=any&sample_size=100"

# Trigger live price poll (normally runs every 2 min automatically)
curl -X POST "https://api.bainluck.com/api/admin/prediction-markets/poll-live?secret=any"

# Manual link (fallback when auto-matching fails)
curl -X POST "https://api.bainluck.com/api/admin/prediction-markets/link?secret=any&market_id=123&event_id=456"

# Backfill Polymarket win_prob_snapshots from CLOB price history
# (fills in trend line from market creation, not just current price)
curl -X POST "https://api.bainluck.com/api/admin/prediction-markets/backfill-history?secret=any&market_id=130740&event_id=5541994"
```

**Files:**
- `backend/app/utils/prediction_market_matching.py` — Detection regex, fuzzy matching, team mapping, ticker parsing, ticker abbreviation extraction, ticker fragment matching (NCAAB/NCAAF), prop/spread outcome filter, `_SPORT_CATEGORY_TO_KEY_PREFIX` mapping
- `backend/app/tasks/prediction_market_matching.py` — Celery task: two-pass link + snapshot phases, both-teams gate, sport scoring, orphaned snapshot cleanup on unlink/re-link, fragment-based disambiguation, matchup-prioritized scan (Pass 2a/2b), Polymarket CLOB price history backfill on first link
- `backend/tests/test_prediction_market_matching.py` — 291 tests (ticker detection, ticker abbreviation parsing, ticker fragment matching, name building, false positives, sport prefix mapping, ticker fallback, live poll wiring, matchup-name outcome fallback, prop/spread outcome filtering, integration)

### Team Auto-Creation from Events
The `_discover_events()` task (runs every 15 min) now batch-creates Team records for any teams found in events that don't yet have entries in the `teams` table. This ensures college teams (Harvard, Brown, Stanford, etc.) get Team records even without ESPN scoreboard matching. The `search_teams` endpoint also falls back to searching the events table and auto-creating Team records for matches.

### Oscars Landing Page
Visual-first landing page for the 98th Academy Awards (March 2, 2026) at `/oscars`. Aggregates prediction market odds from Polymarket and Kalshi, enriched with movie posters and headshots from TMDB.

**Backend:** `GET /api/oscars` — Queries all Oscar-related `FuturesMarket` records, groups by 24 award categories (regex-based extraction from market names), merges nominees across sources with diacritics-aware dedup, normalizes probabilities to sum to 100%, and orders by ceremony presentation.

**Key data quality handling:**
- **Kalshi 0.5 filtering**: Illiquid binary markets default to 50/50 — filtered out as noise
- **Diacritics dedup**: `_strip_diacritics()` using `unicodedata.normalize("NFD")` ensures Skarsgård = Skarsgard
- **Name normalization**: Strips "The " prefix, colon subtitles ("F1: The Movie" → "F1"), role/film info after " - " or " for "
- **"Tie" outcome filtering**: Removed from all categories
- **Boxing false positive filter**: `_is_oscars_market()` rejects markets with " vs " (e.g., "Oscar Duarte vs...")
- **NegRisk trivia dedup**: Skips trivia markets where all outcomes share the same name
- **Cap at 10 nominees** per category after probability normalization

**Frontend:** Gold-themed page with sections:
1. **Hero** — Countdown timer to ceremony, gold gradient background
2. **Best Picture Spotlight** — Horizontal poster row from TMDB, probabilities underneath
3. **Major Awards** (6 categories) — Headshots + probability bars with source breakdown
4. **Craft Awards** (17 categories) — Compact expandable rows
5. **Trivia** — Non-award markets ("most nominations at 99th Oscars")

**TMDB integration** (`frontend/lib/tmdb.ts`): Client-side only (TMDB has CORS headers). Uses Read Access Token (v4) as Bearer auth via `NEXT_PUBLIC_TMDB_API_KEY`. Progressive enrichment — odds render first, images load async via `Promise.allSettled`. localStorage cache with 24h TTL. Graceful fallback to colored initial circles if no token or fetch fails.

**Files:**
- Backend: `backend/app/routes/oscars.py`
- Frontend: `frontend/app/oscars/page.tsx`
- TMDB client: `frontend/lib/tmdb.ts`
- Static data: `frontend/lib/oscarsData.ts`
- Types: `OscarsResponse`, `OscarsCategory`, `OscarsNominee` in `frontend/lib/types.ts`

### TV Mode (Second-Screen Experience)
Fullscreen browser-first second-screen experience at `/tv` for live games, elections, award shows, and ambient futures display. Designed for phone, iPad, and TV/monitor with a cascaded density hierarchy — every screen shows as much data as possible, bigger screens show MORE.

**Signature element:** Probability numbers "breathe" — a CSS scale/glow animation whose speed maps to the Pulse score. `beatMs(p) = Math.max(550, 2000 - p * 14.5)`. A Pulse-91 thriller visibly throbs faster than a Pulse-42 blowout.

**Design language:** Dark void (#09090b), team colors as the only palette, glowing numbers via text-shadow, no UI chrome in display mode, jumbotron typography.

**Cascaded density hierarchy (v4):**

| Feature | Phone | iPad | TV/Monitor |
|---------|-------|------|------------|
| Breathing probability numbers | ✅ 56px | ✅ 56px | ✅ 80px |
| Multi-source chart (Odds, ESPN, Kalshi, Polymarket) | ✅ w/ gridlines | ✅ w/ gridlines | ✅ w/ gridlines |
| Score + teams + records | ✅ | ✅ | ✅ large |
| Probability bar | ✅ | ✅ | ✅ |
| Pulse ring | ✅ 58px inline | ✅ 72px sidebar | ✅ 100px sidebar |
| Context (opened, line, divergence) | ✅ | ✅ sidebar | ✅ sidebar |
| Championship impact | ✅ | ✅ sidebar | ✅ sidebar |
| Related futures | ✅ up to 3 | ✅ all | ✅ all |
| Other live games panel | — | ✅ 140px | ✅ 200px |
| Trending futures panel | — | ✅ top 2 | ✅ top 4 w/ bars |
| Score-by-period breakdown | — | — | ✅ header |
| Pulse component breakdown | — | — | ✅ (HR/Amp/Arr/Vit) |
| Source comparison strip | — | — | ✅ below chart |
| Sparklines in other games | — | — | ✅ |

**Two modes:**
- **Live mode**: Single event focus filling the screen. Navigate between games via arrows/swipe. Auto-switches to highest-Pulse game when spike >85.
- **Ambient mode**: 8-second rotation through interesting futures (championships, elections, crypto) with crossfade. Auto-activates when no live games.

**Smart behaviors:** Auto-switch on Pulse spikes, auto-ambient when no live games, `wakeLock` API to prevent screen dimming, keyboard shortcuts (arrows, space, F).

**Device frames:** Phone 390×780 (with notch), iPad 900×600, TV 1280×720. Scale-to-fit based on viewport width.

**iOS v2 features (documented, not built):** Lock Screen Live Activities (persistent probability bar), Dynamic Island (Pulse dot + score), StandBy mode (giant numbers on MagSafe charger), Apple Watch complications (probability ring), widget gallery (small/medium/large), haptic feedback mapped to Pulse rhythm, Siri integration ("What's the most exciting game right now?").

**Files:**
- Prototype: `tv-mode-prototype.jsx` (interactive React component with device switching, mode toggling, Pulse slider)
- Design plan: `docs/tv-mode-plan.md` (full spec including iOS v2 features, implementation phases)

**Implementation plan (4 phases):**
1. Route + core layout: `/tv` route, device detection, LiveView, wire to events/history APIs
2. Multi-source + context: win probability sources, opening odds, line movement, related futures, divergence
3. Ambient + polish: futures rotation, auto-switch, keyboard shortcuts, wakeLock, fullscreen
4. Smart features: game start notifications, Pulse spike alerts, optional heartbeat audio, multi-game split screen

---

## API Patterns

### Response Format
```python
# Probabilities as decimals (0.0-1.0)
{"home_probability": 0.65, "away_probability": 0.35}

# Timestamps in ISO 8601
{"commence_time": "2026-02-03T19:00:00+00:00"}

# Pulse included when available (score = percentile, raw_score = pre-percentile)
{"pulse": {"score": 75, "raw_score": 68, "status": "strong", "emoji": "💓", "label": "Exciting"}}
```

### Event Statuses
- `scheduled` - Not started
- `live` - In progress
- `completed` - Finished (confirmed by Scores API)
- `closed` - Finished (inferred from stale odds)

---

## Database Schema (Key Tables)

```sql
events          -- Games/matches with teams, scores, Pulse
odds_snapshots  -- Historical odds from each bookmaker
score_snapshots -- Score history during live games
sports          -- Supported sports/leagues
futures         -- Championship odds markets
gei_percentiles -- Pulse percentile thresholds
```

**Pulse fields on events:**
- `raw_gei` - Score/100 (e.g., 0.75 = score 75)
- `gei_components` - JSON of component breakdown
- `gei_computed_at` - When last calculated

---

## Common Tasks

### Add a new API endpoint
1. Add route in `backend/app/routes/`
2. If new router, register in `backend/app/main.py` and `backend/app/routes/__init__.py`

### Add a new frontend page
1. Create file in `frontend/app/[route]/page.tsx`
2. Next.js app router auto-registers it

### Run Pulse recalculation
```bash
curl -X POST "https://api.bainluck.com/api/admin/pulse/recalculate?secret=any&limit=500"
```

### Check Pulse status
```
https://api.bainluck.com/api/events/debug/pulse
```

### Debug an event
```
https://api.bainluck.com/api/events/{id}
https://api.bainluck.com/api/events/{id}/debug
```

---

## Code Style

- **Python**: Type hints, Black formatting, Ruff linting
- **TypeScript**: Strict mode, interfaces in `lib/types.ts`
- **Components**: Functional React with hooks
- **Commits**: Descriptive messages, reference session URLs

---

## Deployment

Both backend and frontend auto-deploy from `master` branch.

**Backend (Heroku):**
- Push to master triggers build
- Runs `alembic upgrade head` on release
- Procfile: `web: uvicorn app.main:app`

**Frontend (Vercel):**
- Push to master triggers build
- Auto-preview for PRs

---

## Current Priorities (February 2026)

### Active — Infrastructure & Reliability
These are the current focus. Resist the urge to build new features until these are addressed.

1. 🟢 **Reduce stat model dependency on ESPN name matching (shipped)** — Three-pronged fix: (a) multi-signal ESPN matching (ESPN ID → name → commence_time proximity) for both live and scheduled events, (b) wall-clock time estimation fallback when ESPN sync misses entirely, (c) odds polling stat model path relaxed to use wall-clock when game_clock unavailable. 67 tests covering wall-clock estimation + fallback integration. **Remaining:** verify on production with live college games to measure improvement in stat model coverage.
2. 🟡 **Data retention / worker memory** — Heroku worker was hitting R14 (Memory quota exceeded). **Phase 1 fix shipped:** snapshot collapse rewritten to pure SQL using PostgreSQL window functions (LAG, SUM) and CTEs — zero rows loaded into Python, constant memory usage. **Phase 2 opportunities (if OOM persists):** pre-game snapshot thinning (keep 1/hour instead of every poll), aggregate completed games into `odds_aggregated` then delete raw rows, cap futures snapshot retention post-resolution. The `odds_aggregated` table exists in the schema but nothing writes to it yet.
3. 🟢 **Monitoring and reliability improvements (shipped)** — Task-level success metrics system: `record_task_success()`/`record_task_failure()` in `redis_state.py` tracks duration, result summaries, consecutive failures, and 24h success/failure counts per task in Redis. Dashboard endpoint `GET /api/admin/celery/dashboard` shows all tracked tasks with health classification (healthy/degraded/critical). 7 key tasks instrumented via `_tracked_run()`: poll_odds, espn_sync, discover_events, poll_futures, poll_kalshi, poll_polymarket, prediction_market_match. Per-task detail: `GET /api/admin/celery/task-metrics/{name}`. **Remaining:** add alerting (e.g., Slack webhook when a task goes critical), add more tasks to tracking.

### Next — Features (in priority order)
4. 🟢 **Auth & Personalization Phase 1 (shipped)** — Google Sign-In working on Safari and Chrome via GIS + backend custom token fallback. Backend auth middleware, pin sync endpoints, frontend auth context + sign-in UI, preferences page placeholder. Still needs desktop Safari verification. See `docs/auth-personalization-plan.md` for full plan.
5. 🟢 **Auth & Personalization Phase 2 (shipped)** — 5-step onboarding flow (location → follow teams → alma maters → sports+beyond → rivals) with metro alias expansion, sport affinity key mapping, batch save endpoint, preferences display page, homepage CTA banner, inline favorites CRUD, non-sports categories (politics, entertainment, crypto, etc.). Team search falls back to events table and auto-creates Team records for college teams. See onboarding details in Auth & Personalization section above.
6. 🟢 **Auth & Personalization Phase 3 (shipped)** — Personalized feed scoring: team multipliers (local 3.5×, alma_mater 2.5×, followed 2.0×), rival multipliers (live losses, blown leads), sport affinity weighting, personalization badges ("Your team", "Local", "Alma mater", "Rival losing"), unified interestingness feed combining events + futures.
7. 🟢 **Ranking Level 2 (shipped)** — Time-series aware scoring using `compute_time_series_metrics()` from odds_snapshots. Computes volatility (RMS of consecutive deltas), lead changes (50% crossings), and recent momentum (30-min window). Batch SQL query for live events. New labels: "Lead change", "Odds shifting fast", "Wild game". 21 new tests.
8. 🟢 **Anonymous feed ranking overhaul (shipped)** — 4-tier league system: Tier 1 (+20 pts): NBA/NFL/MLB/NHL/EPL/La Liga/UCL. Tier 2 (+10): NCAAF/NCAAB/WNBA/MLS/Bundesliga/Serie A/MMA. Tier 3 (0): mid-tier international. Tier 4 (-15 penalty): everything else (minor leagues). Expanded from 7 to 30+ league entries. Anonymous min_score raised from 20 to 25. Prevents minor league hockey from dominating the feed.
9. 🟢 **MLB Stats API integration (shipped)** — Live baseball win probability from MLB's official API (`statsapi.mlb.com`). No API key needed. Celery task polls every 2 min during live games. Replaces FanGraphs stub. 33 tests.
10. 🟢 **Divergence badge (shipped)** — Frontend detects when prediction market odds (Kalshi/Polymarket) diverge >5% from sportsbook consensus. Purple badge for >10% gap, blue for >5%. On event detail page data freshness strip.
11. 🟢 **Non-sports tier promotion (shipped)** — Politics, Entertainment, Crypto promoted from tier 3 to tier 2 in `sportCategories.ts` frontend categorization.
12. 🟢 **Prediction market game-level odds (shipped)** — Two-pass matching (ticker scan + general scan), 291 tests, sport+time fallback, ticker abbreviation parsing for generic-named Kalshi markets, admin endpoints. Live polling every 2 min. Both-teams matching gate prevents mislinks (e.g., "Pistons vs. Bulls" matching South Florida Bulls). Sport category scoring bonus for disambiguation. Polymarket matchup-named outcome fallback for `find_moneyline_outcome`. Stale/mislink cleanup scans ALL linked markets (not just completed) and deletes orphaned `win_prob_snapshots`. Prop/spread outcome filter prevents O/U and spread outcomes from being matched as moneyline. NCAAB/NCAAF ticker fragment matching disambiguates among multiple same-sport candidates. LLM "Bigger Picture" summary on related-futures endpoint (GPT-4o-mini, cached in `LineMovementAnalysis`).
13. 🟢 **Typeahead search (shipped)** — `SearchBar` component with 200ms debounce, keyboard navigation (arrow keys + Enter), integrated into layout header. Backend `GET /api/events/typeahead?q=...` endpoint returns top 5 events + 3 futures. Mobile: search icon links to `/search` page. Desktop: inline search bar in header.
14. 🟢 **"Market Was Wrong" page (shipped)** — `GET /api/market-moves` endpoint surfaces post-game championship odds shifts. Frontend page at `/market-moves` shows which teams' futures moved most after game results. Backend uses `routes/market_moves.py`.
15. 🟢 **Onboarding UX fixes (shipped)** — Sport labels on all team search dropdowns/chips (shows "NBA", "NCAA Lacrosse" etc. to disambiguate), fixed duplicate non-sports in onboarding grid, increased session token TTL from 1hr to 8hrs to prevent expiry during onboarding, fixed same-name team clickability (dedup by ID not name).
16. 🟢 **Sport category disambiguation (shipped)** — `_score_candidates` uses `llm_sport_category` (already populated for both Kalshi and Polymarket) to add sport-match scoring bonus (+5) via `_SPORT_CATEGORY_TO_KEY_PREFIX` mapping. Prevents cross-sport mislinks.
17. 🟢 **Oscars landing page (shipped)** — `/oscars` page with 24 award categories, cross-source odds aggregation (Polymarket + Kalshi), TMDB movie posters/headshots, ceremony countdown, gold-themed design. Backend at `GET /api/oscars`. Diacritics-aware nominee dedup, Kalshi 0.5 noise filter, probability normalization. See Oscars Landing Page section above.
18. 🟢 **Event importance scoring + ESPN season type (shipped)** — `compute_highlight()` reads `llm_importance` with championship (+25), playoff (+15), exhibition (-20) weights. ESPN sync parses `season.type` and writes to `llm_importance`. Tennis Grand Slams and golf Majors promoted to tier 2. Playoff NFL scores 65 base (was 50), preseason NBA drops to 30 (was 50). 17 new tests.
19. 🟢 **Migrate roster sync from SportsDataIO to ESPN (shipped)** — `roster_sync.py` already uses ESPN + MLB Stats API as primary sources. Deleted `sportsdata_api.py` (321 lines of dead code). `SPORTSDATA_API_KEY` env var no longer needed.
20. 🟢 **"Why Did the Line Move?" v1 — ESPN context enrichment (shipped)** — The full pipeline was already deployed (detection in `line_movement.py`, LLM explanation in `llm.py`, caching in `LineMovementAnalysis`, endpoint at `GET /events/{id}/line-movement`, frontend in `LineMovementExplainer.tsx`). This phase adds **real data** to the LLM prompt: ESPN injury reports (`get_event_context()` in `espn_api.py`), news headlines, and live game state (score/period/clock). Prompt instructs LLM to only reference listed injuries — no fabrication. Response includes `context` metadata (injuries_count, news_count, has_game_state). 26 new line movement tests + 8 ESPN parsing tests (84 total in both files).
21. 📋 Apple Sign-In (after Google auth is working) — required by App Store policy if Google Sign-In is offered. Also: change Firebase support email to support@bainluck.com, link Firebase to Google Analytics for cross-platform reporting
22. 📋 Sport-specific Pulse normalization (different ceilings per sport)
23. 🟡 **TV Mode v2 (designed, prototype built)** — Fullscreen second-screen experience for live games, elections, award shows, and ambient futures. Browser-first (`/tv` route). Cascaded density hierarchy: Phone shows Pulse ring + multi-source chart + context + related futures. iPad shows 3-column layout (chart + context sidebar + other games). TV is maximal with score-by-period, Pulse component breakdown, source comparison strip, sparklines in other-game cards, expanded trending futures. Ambient mode auto-rotates through futures during downtime. Prototype at `tv-mode-prototype.jsx`, full design plan at `docs/tv-mode-plan.md`. iOS v2 features documented (Live Activities, Dynamic Island, StandBy, Apple Watch, widgets, haptics, Siri). See TV Mode section in Key Features below.
24. 🟢 **Stale bookmaker filter fix (shipped)** — `filter_stale_bookmaker_snapshots` now uses `valid_until` (write-time dedup aware) instead of only `captured_at`. Layer 2 recency filter for live events excludes bookmakers >10 min stale. 23 tests (14 existing + 9 new). Reduces `current_odds` divergence from history endpoint.
25. 🟢 **NFL roster sync fix (shipped)** — Phase 1 team sync builds `sd_abbrev → team_id` mapping that Phase 2 roster sync uses as primary lookup, bridging the ESPN/SportsDataIO abbreviation gap. Added ILIKE fallback for formatting diffs, MLB abbreviation map (30 teams). Should fix 2/32 → 32/32 NFL matching.
26. 🟢 **Related futures Phase 4 (shipped)** — LLM "Bigger Picture" summary on related-futures endpoint. GPT-4o-mini generates 2-3 sentence casual summary of championship/award implications. Cached in `LineMovementAnalysis` with 2h TTL (never expires for completed games). Frontend summary-first collapsed design with "See all N futures" toggle.
27. 🟢 **Bigger Picture visual redesign (shipped)** — Tier-grouped display with pattern-based `effectiveTier()` overriding backend `market_tier`. Championship hero cards, award rows with ESPN headshots (`PlayerHeadshot` component: headshot URL → espn_id → Wikipedia → initials), stat prop cards with semi-circular SVG gauges, dense 2-col upcoming games grid. Award dedup by player+award combo key. NOT_CHAMPIONSHIP_PATTERNS (14 patterns) prevents misclassified hero cards (Win Totals, Make Playoffs, Seeding, etc.). Title Comparison prefers "championship" in market name. Backend stat prop filter ensures game-specific stats only show on correct event page (±6h temporal proximity or event_id match). Frontend cross-sport false positive check on game grid (team name must appear in market name).
28. 📋 **Related futures Phase 5** — Bidirectional linking: futures detail pages show relevant upcoming/recent events
28. 📋 Non-sports category display in frontend (politics, entertainment, crypto tabs on homepage)
29. 🟡 **Database size & retention strategy (evaluating)** — The `odds_snapshots`, `futures_odds_snapshots`, and `win_prob_snapshots` tables grow ~10-20K net rows/day after write-time dedup. Current mitigation: lossless snapshot collapse (Phase 1 shipped — pure SQL, constant memory) reduces row count 50-90% for events >48h old. **No auto-deletion** — we want to preserve full history. Future options under evaluation: (a) pre-game snapshot thinning (keep 1/hour for >24h before game), (b) populate `odds_aggregated` table with 1-hour buckets for completed events then archive raw snapshots to cold storage, (c) tiered retention by event tier (Tier 1 full history, Tier 3-4 for 30 days), (d) futures cleanup for resolved markets after 6 months. The current collapse strategy buys 2-3 years of runway. Need to spend more time evaluating solutions — the priority is not losing data we might want later. See `backend/app/tasks/retention.py` for collapse implementation.

### Horizon — AI-Native Sports Intelligence (ESPN + MySportsFeeds + The Odds API + AI)
These are differentiated features that can't be built with odds data alone. They require sports data enrichment (rosters, injuries, standings, schedules from ESPN free API + MySportsFeeds) combined with AI interpretation. Ordered by estimated impact and feasibility.

1. 🟡 **"The Market Was Wrong" v2** — Basic version shipped (see priority #14). Next: add AI narrative generation ("After tonight's upset loss, the Celtics' title odds dropped from 8% to 5.5%"), deeper historical context, and personalization (show moves for your teams first).
2. 🟡 **"Why Did the Line Move?"** — Promoted to priority #19 in Next section. Core architecture: detect significant movements → correlate with ESPN injuries/news + MySportsFeeds structured data + live game context → LLM explanation. See priority #19 for details.
3. 📋 **"Your Team's Season at a Glance"** — Dashboard view: championship odds trajectory over the season, win/loss record overlaid on odds chart, key inflection points annotated. Needs: team favorites (auth), futures odds history, game results.
4. 📋 **Injury Impact Score** — When a player is injured, show historical impact on team's odds. "When Steph Curry has been out this season, Warriors odds shift -4.2% on average." Needs: MySportsFeeds injury data + odds snapshots correlation.
5. 📋 **Game Context Card** — Rich pre-game card: standings implications, head-to-head record, streak info, playoff scenario impact. "If the Celtics win tonight, they clinch the #1 seed." Needs: ESPN standings + schedule + AI reasoning.
6. 📋 **Overreaction Index** — Compare a team's current championship odds trajectory against historical base rates. "The Lions are +400 to win the Super Bowl. Only 3 teams with these regular season stats have ever won." Needs: historical odds data + AI analysis.
7. 📋 **Momentum Tracker** — Rolling 10-game odds trend visualization. Show which teams are on hot/cold streaks based on how the market is repricing them, not just W/L record. Needs: futures odds time series.
8. 📋 **"What's Actually at Stake"** — For each game, show concrete implications: "Win and they're 2 games up in the division. Lose and they drop to 4th." Needs: ESPN standings + schedule + playoff math.
9. 📋 **Sharps vs Public** — If MySportsFeeds provides line movement + betting splits, surface when sharp money disagrees with public sentiment. Differentiated from existing tools by visual-first presentation.
10. 📋 **Futures Postmortem** — At season end, show who "won" the futures market: early bettors on the champion, worst value bets, biggest surprises. Needs: full futures odds history + AI narrative generation.

### Completed
<details>
<summary>Shipped features (click to expand)</summary>

- ✅ Pulse feature complete and deployed
- ✅ Kalshi prediction market integration
- ✅ Futures UI improvements (sportsbooks, start times, categorization)
- ✅ LLM infrastructure (OpenAI GPT-4o-mini for smart categorization)
- ✅ Pulse Hall of Fame page
- ✅ Pinned Events & Futures (localStorage-based tracking)
- ✅ Futures categorization hardened (0 uncategorized markets)
- ✅ Pulse distribution tuning (normalization constants, percentile scoring, component tooltips)
- ✅ ~~TV/Party mode v1~~ (shipped for Super Bowl LX, removed post-event)
- ✅ TV Mode v2 design + interactive prototype (cascaded density hierarchy, multi-source charts, Pulse breathing animation, ambient futures rotation, iOS v2 features documented)
- ✅ Sentry error tracking (FastAPI + Celery worker, controlled by SENTRY_DSN env var)
- ✅ Multi-source win probability infrastructure (generic `win_prob_snapshots` table, source config, N-source chart)
- ✅ Bain Luck statistical win probability model (nflfastR-inspired, NFL/NCAAF/NBA/NCAAB/WNCAAB/NHL)
- ✅ Win probability source detail page (`/events/[id]/models`) with methodology + attribution
- ✅ ESPN team name matching normalization (unicode/accent handling for college teams)
- ✅ Status-based probability display (opening odds for finished games, current odds for live, with stale bookmaker filtering)
- ✅ Stale bookmaker filter extracted to `app/utils/odds_filtering.py` with 14 regression tests (including commence_time sanity check)
- ✅ Opening odds now stores last pregame consensus (cross-bookmaker average, continuously updated while scheduled)
- ✅ Snapshot data retention Phase 1: lossless collapsing of consecutive identical rows across `odds_snapshots`, `win_prob_snapshots`, `futures_odds_snapshots` + write-time dedup for `win_prob_snapshots`. Phase 2: rewritten to pure SQL using PostgreSQL window functions (LAG, SUM, CTEs) for constant memory — fixes Heroku worker OOM (R14).
- ✅ Refactored `tasks.py` (2,970 lines) into `tasks/` package with 14 modules: `__init__.py`, `config.py`, `base.py`, `snapshots.py`, `redis_state.py`, `odds_polling.py`, `pulse.py`, `futures.py`, `kalshi.py`, `espn_sync.py`, `sports.py`, `retention.py`, `roster_sync.py`, `team_linking.py`. All task names pinned with `name=` params for backward compatibility. Celery heartbeat + health endpoint added.
- ✅ Super Bowl dead code cleanup: removed `contest.py`, `superbowl.py`, `youtube_api.py`, `CommercialLeaderboard.tsx`, and related routes/types (~7K+ lines)
- ✅ Related futures Phases 1-3: team linking infrastructure (`FuturesOutcome.team_id` FK, `FuturesMarket.market_tier`, backfill task), `GET /api/events/{id}/related-futures` endpoint with hybrid matching (name ILIKE + team_id, triple sport filter), frontend "Bigger Picture" section with team colors/logos/probability bars
- ✅ SportsDataIO integration: API client, roster sync task (daily at 7:00 AM UTC), `Team.roster_players` JSONB column for player name matching in related futures. NBA 26/30, NHL 20/32 teams synced. **Later:** `sportsdata_api.py` deleted, roster sync migrated to ESPN + MLB Stats API.
- ✅ Test coverage for core algorithms: 1533+ backend (pytest items) + 117+ frontend = 1650+ total tests. Pure-function testing strategy covers Pulse (85), Highlights (126, incl. Level 2 time-series, event importance), odds math (35+35), futures categorization (116), win probability (67), ESPN API parsing (50, incl. season type), team linking (97), LLM classification (60), prediction market matching (291), odds polling helpers (27), win prob sources (24), task wiring (21), stale bookmaker filter (14), snapshot collapse (13), retention SQL (19), redis state (13), onboarding/preferences (31), MLB Stats API (33). See `docs/test-coverage-analysis.md` for full analysis and prioritized improvement recommendations.
- ✅ Moved `_create_or_update_win_prob_snapshot` to `tasks/snapshots.py` shared module (was in `odds_polling.py`, imported by `espn_sync.py`)
- ✅ Polymarket integration Phase 1: API client (`polymarket_api.py`), polling task (`tasks/polymarket.py`) with streaming pagination + batched commits (50 events/batch), 160+ tag-to-category mapping with fallback to rules + league detection, outcome name extraction, page cap monitoring. 69 tests covering tag mapping, name extraction, API parsing.
- ✅ Auth & Personalization Phase 1 (shipped): Google Sign-In on Safari + Chrome via GIS + backend custom token fallback, backend auth middleware, pin sync, frontend auth context + sign-in UI.
- ✅ Auth & Personalization Phase 2 (shipped): 5-step onboarding flow (`/onboarding`) — location, follow teams, alma maters, sports+beyond (20 categories incl. politics/entertainment/crypto), rivals. Team search falls back to events table and auto-creates Team records for college teams. Inline favorites CRUD on preferences page. 31+ tests.
- ✅ Auth & Personalization Phase 3 (shipped): Personalized feed scoring with team multipliers (local 3.5×, alma_mater 2.5×, followed 2.0×), rival multipliers (live losses, blown leads), sport affinity weighting. Personalization badges ("Your team", "Local", "Alma mater", "Rival losing"). Unified interestingness feed combining events + futures on homepage.
- ✅ Unified feed: Homepage redesigned from separate sections (Highlights, Live, Upcoming) to single "Right Now" feed ranked by interestingness score. Feed items include events and futures, with personalization overlay for authenticated users.
- ✅ Prediction market → event matching: Two-pass strategy (targeted Kalshi ticker scan + general scan) links game-level Kalshi/Polymarket markets to Events for win probability trend lines. Live game price polling every 2 min via `poll_live_prediction_markets` (targeted — only fetches prices for linked live-event markets from Kalshi/Polymarket APIs). Ticker abbreviation parsing (`extract_teams_from_ticker`) for generic-named Kalshi markets. 223 tests covering ticker detection, abbreviation parsing, name building, false positive prevention, sport prefix mapping, ticker fallback, live poll wiring.
- ✅ ESPN matching resilience + wall-clock fallback: Multi-signal ESPN matching (ESPN ID → name → commence_time proximity) for both live and scheduled events. Wall-clock time estimation fallback for stat model when ESPN sync misses (common for college teams). Odds polling path relaxed to use fallback automatically. 16 new tests (67 total win probability tests).
- ✅ Task-level monitoring dashboard: `redis_state.py` metrics system tracks success/failure/duration/output per task in Redis. Dashboard at `GET /api/admin/celery/dashboard` with health classification. 7 key tasks instrumented via `_tracked_run()`.
- ✅ Polymarket price history backfill: `POST /api/admin/polymarket/backfill-history` fetches CLOB `/prices-history` for outcomes with sparse data, stores as `FuturesOddsSnapshot` rows. Resolves clob_token_ids via Gamma API event lookup.
- ✅ Ranking Level 2: Time-series aware scoring using `compute_time_series_metrics()` from odds_snapshots. Computes volatility (RMS), lead changes, recent momentum. Batch SQL query for live events. New labels: "Lead change", "Odds shifting fast", "Wild game". 21 new tests.
- ✅ MLB Stats API integration: Live baseball win probability from `statsapi.mlb.com` (no API key). Celery task polls every 2 min during live games. Source key `"fangraphs"` (display name "MLB Model"). 33 tests.
- ✅ Divergence badge: Frontend detects when prediction market odds (Kalshi/Polymarket) diverge >5% from sportsbook consensus. Purple badge for >10% gap, blue for >5%.
- ✅ Non-sports tier promotion: Politics, Entertainment, Crypto promoted from tier 3 to tier 2 in frontend categorization.
- ✅ Safari auth 3-tier fallback: signInWithCredential (4s) → backend custom token + signInWithCustomToken (4s) → backend-only PyJWT session token. Prevents hanging on Safari ITP. Auth persistence switched to `browserLocalPersistence` (localStorage) from IndexedDB.
- ✅ Anonymous feed ranking overhaul: 4-tier league system (Tier 1 +20 pts, Tier 4 -15 penalty), expanded from 7 to 30+ league entries, anonymous min_score raised to 25. Prevents minor league games from dominating.
- ✅ MoneyPuck stub: Source config entry for future NHL advanced stats integration.
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
- ✅ "Why Did the Line Move?" ESPN context enrichment: Added `get_event_context()` to `espn_api.py` (parses injuries + news from `/summary` endpoint). Enriched `build_llm_prompt()` with real injury reports, news headlines, and live game state (score/period/clock). Prompt instructs LLM to only reference listed data. Response includes `context` metadata. 26 line movement tests + 8 ESPN parsing tests (84 total).
</details>

See `docs/PRD.md` for full roadmap.

---

## Development Process & Lessons Learned

### Fix-Commit Problem
~34% of early commits were bug fixes, often for issues that could have been caught before deploy. Root causes:
- Test suite now has 1667+ tests (1550+ backend + 117+ frontend) but initially had very few
- Direct deploy to production without staging verification
- Background task failures (Celery) — now mitigated by Sentry error tracking + heartbeat monitoring

**Rule of thumb:** Before shipping changes to `pulse.py`, `highlights.py`, or the `tasks/` modules, write or run tests first.

### Tasks Package Architecture
The former monolithic `tasks.py` was refactored into `backend/app/tasks/` (14 modules). Key architectural decisions:
- All task names pinned with `name="app.tasks.*"` — beat schedule uses string task names that must match
- `__init__.py` has thin task wrappers that call `run_async()` on async implementations from submodules
- `from app.tasks import celery_app` and other existing imports work via re-exports in `__init__.py`
- Cross-module imports: `sports.py` imports from `odds_polling.py`, `espn_sync.py` imports from `snapshots.py`
- Shared utilities: `snapshots.py` contains write-time dedup helpers used by both `odds_polling.py` and `espn_sync.py`
- Celery worker command `celery -A app.tasks worker` resolves to `tasks/__init__.py` automatically

### Super Bowl One-Offs (Removed)
All Super Bowl LX party features have been removed: commercial/ad leaderboard, prop contest system, AI commentary/roasting, trivia, YouTube API integration, TV/Party mode page, player props endpoint, confetti/ECG animations. Code was deleted across ~15 files totaling ~7,000+ lines.

### localStorage Debt
Pinned events/futures use localStorage for anonymous users and sync to `user_pins` table on first login (via `usePinSync` hook). The existing localStorage hooks (`usePinnedEvents`, `usePinnedFutures`) still work for anonymous users. A future phase will replace them with server-backed hooks that read/write via the API when authenticated. Avoid adding new localStorage-dependent features — use the `user_preferences` JSONB columns or `user_favorites` table instead.

### Session-End Feedback Prompt
At the end of long working sessions, run the feedback prompt (saved in `docs/feedback-prompt.md`) to get process feedback on priority alignment, prompting effectiveness, and blind spots.

---

## Gotchas & Tips

1. **Alembic multiple heads**: If you see this error, check `down_revision` in migration files - they should form a single chain.

2. **Alembic revision IDs must be ≤32 characters**: The `alembic_version.version_num` column is `VARCHAR(32)`. Longer revision IDs will cause `StringDataRightTruncation` errors during Heroku release. Use short descriptive names (e.g., `add_outcome_search_idx` not `add_futures_outcomes_search_index`).

3. **Alembic migrations use psycopg2, not asyncpg**: The `alembic/env.py` uses synchronous psycopg2 for migrations even though the app uses asyncpg at runtime. This is intentional — async engines don't work reliably in Heroku's release phase.

4. **Admin endpoints require mounting**: New routers must be added to both `main.py` AND `routes/__init__.py`.

5. **Pulse data quality gating**: `calculate_pulse()` returns `None` for < 3 aggregated time buckets. For completed events, Pulse is only stored when `data_quality` is `"limited"` (10-29 buckets) or `"good"` (30+). Events with `"minimal"` data (3-9 buckets) get no stored score. Hall of Fame rankings additionally require 20+ distinct minute-level time buckets. Note: live games still show Pulse with any data quality for real-time feedback.

6. **Frontend types must match backend**: Keep `frontend/lib/types.ts` in sync with API responses.

7. **CORS**: Production domains are whitelisted in `backend/app/main.py`.

8. **Pulse scores are cached**: Changing the algorithm in `pulse.py` does NOT retroactively update stored scores. You must run the force-recalculate endpoint afterward and verify with the distributions endpoint.

9. **Pulse percentiles use completed games only**: The `gei_percentiles` table is computed from completed/closed events with `raw_gei > 0`. Live games are excluded from the reference set to avoid skewing thresholds.

10. **Celery tasks MUST use async DB sessions**: The database module only provides async sessions — there is no `SessionLocal`. New tasks go in the appropriate `tasks/` submodule with an async implementation, and get a thin wrapper in `tasks/__init__.py`:
    ```python
    # In tasks/__init__.py:
    @celery_app.task(bind=True, name="app.tasks.my_task")
    def my_task(self):
        from app.tasks.my_module import _my_task_impl
        return run_async(_my_task_impl())

    # In tasks/my_module.py:
    async def _my_task_impl():
        async with get_task_session() as session:
            result = await session.execute(...)
    ```
    Never use `SessionLocal` or synchronous `session.execute()` — it will raise `ImportError` silently in the worker.

11. **ESPN scoreboard vs teams API format**: The scoreboard endpoint returns team logos as a single `"logo"` string, while the teams endpoint returns a `"logos"` array. The `_parse_team` method in `espn_api.py` handles both.

12. **Safari breaks Firebase Auth** — `signInWithPopup`, `signInWithRedirect`, and `signInWithCredential` all fail on Safari due to ITP. The working solution is GIS `initTokenClient` (opens OAuth popup, returns access token) → backend exchanges for custom Firebase token → `signInWithCustomToken`. Do NOT attempt to use Firebase's native Google sign-in methods on Safari. The backend fallback endpoint `POST /api/auth/google-access-token` handles this. Requires `FIREBASE_SERVICE_ACCOUNT_JSON` to be set.

13. **The Odds API commence_time can be wrong**: The Odds API occasionally returns game local times as if they were UTC (e.g., a 3:30 PM ET game as `15:30Z` instead of `20:30Z`). To prevent this: (a) odds polling upserts no longer overwrite `commence_time` after initial insert, and (b) the ESPN sync task corrects mismatches automatically. For bulk retroactive fixes, use `POST /api/admin/espn/fix-commence-times`. **Note:** Task modules use `logging.getLogger(__name__)`. Some older code still uses `print()` instead — migrate to logger when touching those sections.

---

## Quick Reference

| What | Where |
|------|-------|
| API docs | `/docs` on backend URL |
| Pulse explainer | https://bainluck.com/pulse |
| Pulse Hall of Fame | https://bainluck.com/pulse/hall-of-fame |
| Search | https://bainluck.com/search?q=celtics |
| Market Was Wrong | https://bainluck.com/market-moves |
| Oscars | https://bainluck.com/oscars |
| Onboarding | https://bainluck.com/onboarding |
| My Teams | https://bainluck.com/my-stuff |
| Preferences | https://bainluck.com/preferences |
| PRD | `docs/PRD.md` |
| Debug endpoints | `/api/events/debug/*` |
| Admin endpoints | `/api/admin/*` |
