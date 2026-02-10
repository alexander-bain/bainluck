# CLAUDE.md - Project Guidelines for Claude Code

## Project Overview

**OddsTracker** is a visual-first sports odds experience that translates betting markets into intuitive win probabilities. Users see "60% vs 40%" instead of "-150 / +130".

**North Star**: The cleanest odds visualization tool on the internet.

**Target User**: Casual sports fans watching games who want context, not betting advice. Second-screen experience.

**Live Site**: https://odds.alexbain.com

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
- **The Odds API** (the-odds-api.com) - Sports odds data
- **Kalshi** (kalshi.com) - Prediction market data (futures with timing info)
- **ESPN** (undocumented API) - Team colors, logos, live game data, win probability
- **OpenAI** (platform.openai.com) - GPT-4o-mini for LLM classification
- **Google Analytics 4** - User analytics
- **Firebase Auth** - Planned for user accounts

---

## Project Structure

```
odds-tracker/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── models/models.py     # SQLAlchemy models
│   │   ├── routes/
│   │   │   ├── events.py        # Main events API
│   │   │   ├── admin.py         # Admin/debug endpoints
│   │   │   ├── sports.py        # Sports listing
│   │   │   └── futures.py       # Championship odds
│   │   ├── services/
│   │   │   ├── odds_api.py      # The Odds API client
│   │   │   ├── kalshi_api.py    # Kalshi prediction market client
│   │   │   └── database.py      # DB connection
│   │   ├── tasks.py             # Celery tasks (polling, Pulse calc)
│   │   └── utils/
│   │       ├── odds_math.py     # Probability conversions
│   │       ├── pulse.py         # Game excitement algorithm
│   │       └── highlights.py    # Event ranking
│   ├── alembic/                 # Database migrations
│   └── requirements.txt
├── frontend/
│   ├── app/                     # Next.js app router pages
│   ├── components/              # React components
│   ├── lib/
│   │   ├── api.ts              # API client
│   │   ├── types.ts            # TypeScript interfaces
│   │   └── sportCategories.ts  # Sport grouping logic
│   └── hooks/                   # Custom React hooks
├── docs/PRD.md                  # Full product requirements
└── tools/mcp-api-proxy/         # MCP proxy for API access
```

---

## Key URLs

| Environment | URL |
|-------------|-----|
| Production Frontend | https://odds.alexbain.com |
| Production API | https://what-are-the-odds-0283511a7d93.herokuapp.com |
| API Docs | https://what-are-the-odds-0283511a7d93.herokuapp.com/docs |
| Vercel Dashboard | Vercel (auto-deploys from master) |
| Heroku Dashboard | Heroku (auto-deploys from master) |

**Heroku App Name:** `what-are-the-odds` (for CLI commands like `heroku logs -a what-are-the-odds`)

---

## Critical Files

| File | Purpose |
|------|---------|
| `backend/app/tasks.py` | Celery tasks: odds polling, Pulse calculation, event discovery |
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
| `docs/PRD.md` | Full product requirements and roadmap |

---

## Development Workflow

Development happens primarily through **Claude Code on the web** (GitHub-based). There is no local dev environment.

- **Backend** and **frontend** auto-deploy from `master` via Heroku and Vercel respectively
- **Database migrations**: Create with `alembic revision --autogenerate -m "description"`, applied automatically on Heroku release (`alembic upgrade head`)
- **Testing changes**: Push to master and verify on production, or use Heroku/Vercel preview deployments
- **Running tests**:
  - Backend: `cd backend && python -m pytest tests/ -v` (requires `sqlalchemy`, `asyncpg`, `pydantic`, `openai`, `httpx`)
  - Frontend: `cd frontend && npx jest` (requires `jest`, `ts-jest`, `@types/jest` — already in devDependencies)
  - Backend tests cover: Pulse algorithm, Highlights scoring, odds math, futures categorization rules, LLM classification (mocked), stale bookmaker filtering
  - Frontend tests cover: sportCategories (prefix matching, futures categorization, athlete disambiguation), pinned storage logic

### Querying the Production API

Use `curl` against the production API to inspect data:
```bash
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/events?sport=americanfootball_nfl"
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/events/search?q=celtics"
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/pulse/status"
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

### Frontend (Vercel Environment Variables)
- `NEXT_PUBLIC_API_URL` = `https://what-are-the-odds-0283511a7d93.herokuapp.com`
- `NEXT_PUBLIC_GA_MEASUREMENT_ID` - Google Analytics

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
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/pulse/recalculate?secret=any&limit=500"
# Then verify with distributions endpoint:
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/pulse/distributions"
```

**Hall of Fame filtering:** The `pulse-rankings` endpoint requires 20+ distinct minute-level time buckets (not raw snapshot rows, since each poll captures 5-11 bookmakers). Completed events with `data_quality == "minimal"` (< 10 aggregated time buckets) never get a stored Pulse score, providing a second layer of filtering.

### Highlights (Event Ranking)
Scores events 0–100 to decide what appears in the homepage Highlights section. Events need ≥30 points. This is **Level 1 (snapshot scoring)** of a multi-level ranking system — see "Ranking & Feed Evolution" in `docs/PRD.md` for the full roadmap toward the iOS feed tab.

**Key design rule:** Pre-game closeness (e.g., 51/49) doesn't award points unless there's trend evidence — the line moved ≥5% from opening, tightened from lopsided to close, or the game is starting soon. This prevents aggregation noise from surfacing uninteresting events.

**Labels:** "Upset brewing" and "Close game" are live-only. "Line moving" requires ≥15% swing from opening. "Close matchup" requires starting soon.

**Current limitation:** `compute_highlight` only sees current odds vs opening odds (two points in time). It doesn't query `odds_snapshots` or `odds_aggregated` for time-series data. Level 2 will add this — the snapshot data already exists in the DB.

**Files:** `backend/app/utils/highlights.py`, `frontend/app/page.tsx` (Highlights section rendering)

### Odds Polling
- Live games: Every 30 seconds
- Upcoming games: Every 2-5 minutes based on proximity
- Event discovery: Every 15 minutes (finds new games)

**Key task:** `poll_all_odds` in `backend/app/tasks.py`

### Probability Display by Game Status
Different game statuses show different probability data to users:
- **Scheduled**: Current betting consensus (`current_odds`)
- **Live**: Current live odds (big) + "Opened X/Y" reference from `opening_odds` (small)
- **Completed/Closed**: Opening odds (pre-game consensus) + Pulse excitement score

**Opening odds** are the last pregame consensus — `_maybe_set_opening_odds` in `tasks.py` updates them with the cross-bookmaker average on every poll while the event is scheduled, then freezes when the game starts. Stored on the `Event` model.

**Stale bookmaker filtering**: `filter_stale_bookmaker_snapshots()` in `app/utils/odds_filtering.py` excludes bookmakers whose last distinct odds value was captured before `commence_time`. Runs for ALL non-scheduled statuses (live, completed, closed). Has 14 regression tests in `tests/test_stale_bookmaker_filter.py`.

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
- `backend/app/tasks.py` - `poll_kalshi_markets` task (runs hourly at :45)

**Category Filter (IMPORTANT):**
Kalshi has thousands of markets (politics, economics, etc.) but we only want sports.
To stay within rate limits, we filter to specific categories.

**To change which categories are fetched**, edit this line in `backend/app/tasks.py` around line 1948:
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
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/kalshi/poll?secret=any"
# Response: {"status": "queued", "task_id": "abc123...", "message": "..."}

# Check task status (use task_id from above)
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/kalshi/task/abc123?secret=any"
# Response: {"task_id": "abc123", "state": "SUCCESS", "result": {...}}
```

**Note:** Polling runs as a background Celery task to avoid Heroku's 30-second HTTP timeout.

**Data Model:**
- Kalshi events → `futures_markets` table (source="kalshi")
- Kalshi markets → `futures_outcomes` table
- Stores bid/ask spreads: `yes_bid`, `yes_ask`, `last_price`
- Populates `commence_time` (event start) and `resolution_date` (market close)

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

**Supported categories (22):**
football, basketball, baseball, hockey, golf, tennis, soccer, mma, motorsports, boxing, cricket, rugby, aussierules, horse_racing, olympics, esports, entertainment, politics, lacrosse, chess, poker, other

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
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/futures/categorization-status"

# Trigger LLM categorization (requires OPENAI_API_KEY)
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/futures/categorize?secret=xxx&limit=50"

# Dry run (preview without saving)
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/futures/categorize?secret=xxx&dry_run=true"

# View uncategorized markets (diagnostic)
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/futures/uncategorized"

# Force-categorize all remaining via LLM
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/futures/force-categorize?secret=xxx&limit=100"
```

**Debug endpoints:**
```bash
# See futures count by source (odds_api vs kalshi)
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/futures/debug/sources"

# See sport linking for futures
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/futures/debug/sport-mapping"
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
oddsTracker_pinnedEvents    // Array of event IDs
oddsTracker_pinnedFutures   // Array of futures market IDs
```

### ESPN Integration
ESPN's undocumented API provides team data (colors, logos) and live game info (clock, period, win probability).

**Data Enrichment:**
- **Teams**: ESPN ID, primary/secondary colors, logos (small/large), alternate names, current record
- **Events**: ESPN ID, venue, broadcast info, game clock, period, ESPN win probability
- **Venues**: Name, city, state, country, capacity

**Automatic Sync (Celery task `sync_espn_live_events`):**
- Runs every 60 seconds
- Auto-creates Team records with colors, logos, and alternate names from ESPN scoreboard data
- Updates live events with game clock, period, broadcast info, and win probability
- Also pre-populates team data for scheduled events (so colors/logos appear before games go live)
- ESPN win probability is **only available during live games** — cannot be backfilled after a game ends
- Team colors/logos persist in the `teams` table and apply to all events (past and present) via name lookup
- Mapped sports: NBA, NCAAB, WNCAAB, NFL, NCAAF, NHL, MLB, MLS, EPL (see `ESPN_SPORT_MAPPING` in tasks.py)

**Files:**
- ESPN client: `backend/app/services/espn_api.py`
- Celery sync task: `backend/app/tasks.py` (`sync_espn_live_events` / `_sync_espn_live_events`)
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
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/espn/sync-teams?secret=xxx&sport_key=basketball_nba"

# Check team sync status
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/espn/teams-status"

# Sync live event data (clock, period, win prob)
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/espn/sync-live-events?secret=xxx&sport_key=basketball_nba"

# Test team name matching
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/espn/match-teams?secret=xxx&our_team_name=Lakers&sport_key=basketball_nba"

# Fix incorrect commence_time values using ESPN as source of truth
# (backfills completed events — the live sync task handles new ones automatically)
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/espn/fix-commence-times?secret=any&limit=500"
# Check task status:
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/espn/task/{task_id}?secret=any"
```

### Snapshot Data Retention
Consecutive identical snapshot rows are collapsed into single rows with `captured_at` (first seen) and `valid_until` (last confirmed) timestamps. Lossless — original time series is fully reconstructable.

**Tables covered:** `odds_snapshots`, `win_prob_snapshots`, `futures_odds_snapshots`

**Write-time dedup:** `odds_snapshots` and `futures_odds_snapshots` had this since Jan 2026. `win_prob_snapshots` gained it in Feb 2026. Checks last row per (event, bookmaker/source) before inserting; bumps `reading_count` if value unchanged.

**Retroactive collapse:** Celery task `collapse_snapshots` processes one table per invocation. Runs daily via beat schedule (6:30/6:35/6:40 UTC for odds/winprob/futures respectively).

**Admin endpoints:**
```bash
# Trigger collapse for one table (table: odds, winprob, futures)
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/snapshots/collapse?secret=any&table=odds&limit=500"

# Check task status
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/snapshots/task/{task_id}?secret=any"

# View current row counts
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/snapshots/stats?secret=any"
```

**Files:** `backend/app/tasks.py` (`collapse_snapshots`, `_collapse_snapshots_impl`, `_collapse_table_for_partition`), `backend/app/routes/admin.py` (snapshot endpoints), `backend/tests/test_snapshot_collapse.py` (13 tests)

### Multi-Source Win Probability
The chart can display win probabilities from multiple independent sources, each as a labeled line with its own color and dash pattern.

**Architecture:**
- **Source registry**: `backend/app/config/win_prob_sources.py` — Python dict (not DB table) defining display_name, color, dash_pattern, methodology, attribution for each source
- **Generic storage**: `win_prob_snapshots` table with `source` column (replaces ESPN-specific storage for new sources)
- **OddsTracker Model**: nflfastR-inspired statistical model in `backend/app/utils/win_probability.py`. Uses normal distribution: score diff + time remaining + pregame spread. Sport-specific params: NFL base_std=13.45, NBA/NCAAB=12.0, NHL=2.5
- **Dual compute paths**: Stat model computes in both ESPN sync (every 60s) AND odds polling (every 30-60s) for redundancy
- **Frontend**: OddsChart.tsx renders N sources dynamically; legend labels link to `/events/[id]/models` detail page

**Current sources (3):**
- **Betting Odds** (market, solid dark line) — consensus from 5-15 sportsbooks via The Odds API
- **ESPN** (model, orange dashed) — ESPN's proprietary predictor, only available during live games
- **OddsTracker Model** (model, purple dashed) — our statistical model, attribution to nflfastR/PFR methodology

**Supported sports for stat model:** NFL, NCAAF, NBA, NCAAB, WNCAAB, NHL

**Adding a new source:** Add entry to `WIN_PROB_SOURCES` dict in `win_prob_sources.py`, write snapshots to `win_prob_snapshots` with the source key, and the chart/API pick it up automatically.

**Known issues (Feb 2026):**
- Stat model depends on `game_clock` and `period` from ESPN sync. If ESPN team name matching fails for an event, the stat model can't compute (no time remaining data). Name normalization helps but some college teams may still mismatch.
- Stat model can only compute during live games — it cannot be backfilled after a game ends (requires real-time clock/period/score data from ESPN sync).
- PFR is NOT viable as a live data source (no API, ToS blocks scraping, not real-time)

**Sport key aliasing:** The Odds API uses `americanfootball_nfl`/`americanfootball_ncaaf`/`icehockey_nhl` as sport keys, but the stat model's `SPORT_PARAMS` uses `football_nfl`/`football_ncaaf`/`hockey_nhl`. The `_normalize_sport_key()` function in `win_probability.py` handles this mapping. Basketball keys match natively. If you add a new sport, make sure to test with the actual database sport key.

**Files:** `backend/app/config/win_prob_sources.py`, `backend/app/utils/win_probability.py`, `backend/tests/test_win_probability.py` (39 tests), `frontend/components/OddsChart.tsx`, `frontend/app/events/[id]/models/page.tsx`

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
curl -X POST "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/admin/pulse/recalculate?secret=any&limit=500"
```

### Check Pulse status
```
https://what-are-the-odds-0283511a7d93.herokuapp.com/api/events/debug/pulse
```

### Debug an event
```
https://what-are-the-odds-0283511a7d93.herokuapp.com/api/events/{id}
https://what-are-the-odds-0283511a7d93.herokuapp.com/api/events/{id}/debug
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

1. 🔴 **Add test coverage for core algorithms** — `pulse.py` and `highlights.py` are pure functions that are easy to test and have caused the most rework. Target: 15+ test cases each. Backend has grown to 464 tests across `test_odds_math.py`, `test_pulse.py`, `test_highlights.py`, `test_futures_categorization.py`, `test_win_probability.py`, `test_stale_bookmaker_filter.py`, and `test_snapshot_collapse.py`. Zero frontend tests.
2. 🔴 **Refactor `tasks.py`** — At 3100+ lines, every change has a large blast radius. ESPN sync, odds polling, win probability computation, Pulse calculation, Kalshi polling, and snapshot collapsing should be separate modules. This is the root cause of most fix-commit cycles (missing imports, wrong variable names, status check gaps). Extract at minimum: `tasks/espn_sync.py`, `tasks/odds_poll.py`, `tasks/win_probability.py`.
3. 🟡 **Data retention policy — Phase 1 complete, Phase 2 pending** — Snapshot collapsing implemented: consecutive identical rows are merged into single rows with `captured_at`/`valid_until` spans (lossless). Write-time dedup added to `win_prob_snapshots`. Daily Celery beat tasks run at 6:30/6:35/6:40 UTC. Initial run deleted ~740K rows (19% of total). **Phase 2 opportunities:** pre-game snapshot thinning (keep 1/hour instead of every poll), aggregate completed games into `odds_aggregated` then delete raw rows, cap futures snapshot retention post-resolution. The `odds_aggregated` table exists in the schema but nothing writes to it yet.
4. 🟡 **Reduce stat model dependency on ESPN name matching** — The stat model can only compute when ESPN sync successfully matches a game (providing `game_clock` and `period`). For college sports with hundreds of teams, name mismatches are common. Options: match by ESPN ID instead of name, scrape ESPN scoreboard directly, or estimate time remaining from elapsed wall time as a fallback.
5. 🟡 **Monitoring and reliability improvements** — Poll health dashboard, improved error handling and retry logic.

### Next — Features (in priority order)
7. 📋 Ranking Level 2 — time-series aware scoring (use odds_snapshots in `compute_highlight`). Highest-leverage feature: directly improves the north star.
8. 📋 Add external win prob sources (MoneyPuck for NHL, FanGraphs for MLB) — infrastructure is ready, just needs API integration + source config entry
9. 📋 Pass Kalshi event category as sport_key for better disambiguation
10. 📋 Firebase Auth for user accounts
11. 📋 Migrate pinned items to database (after auth). **Note:** Stop adding new localStorage features until auth is in place — each one makes the migration harder.
12. 📋 LLM-powered odds movement explanations
13. 📋 Sport-specific Pulse normalization (different ceilings per sport)
14. 📋 TV/Party mode v2 — fullscreen second-screen display for watch parties. Previous version (Super Bowl LX) had: giant score + win probability, team-colored probability bar, win prob + score diff charts, Pulse ECG heartbeat, momentum indicator, lead change confetti, auto-scrolling player props carousel, AI commentary, trivia, contest leaderboard. All code was removed post-Super Bowl. Rebuild from scratch when prioritized — focus on big charts + clean visualization, skip the contest/trivia features.
15. 📋 Fix `current_odds` backend computation for started games — use time-bucketed aggregation (same as history endpoint) instead of per-bookmaker-latest, so all API consumers get correct data without frontend cross-checks

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
- ✅ ~~TV/Party mode~~ (shipped for Super Bowl LX, removed post-event — see future priority #14 for v2)
- ✅ Sentry error tracking (FastAPI + Celery worker, controlled by SENTRY_DSN env var)
- ✅ Multi-source win probability infrastructure (generic `win_prob_snapshots` table, source config, N-source chart)
- ✅ OddsTracker statistical win probability model (nflfastR-inspired, NFL/NCAAF/NBA/NCAAB/WNCAAB/NHL)
- ✅ Win probability source detail page (`/events/[id]/models`) with methodology + attribution
- ✅ ESPN team name matching normalization (unicode/accent handling for college teams)
- ✅ Status-based probability display (opening odds for finished games, current odds for live, with stale bookmaker filtering)
- ✅ Stale bookmaker filter extracted to `app/utils/odds_filtering.py` with 14 regression tests (including commence_time sanity check)
- ✅ Opening odds now stores last pregame consensus (cross-bookmaker average, continuously updated while scheduled)
- ✅ Snapshot data retention Phase 1: lossless collapsing of consecutive identical rows across `odds_snapshots`, `win_prob_snapshots`, `futures_odds_snapshots` + write-time dedup for `win_prob_snapshots`
</details>

See `docs/PRD.md` for full roadmap.

---

## Development Process & Lessons Learned

### Fix-Commit Problem
~34% of recent commits are bug fixes, often for issues that could have been caught before deploy. Root causes:
- No test suite beyond `test_odds_math.py` (240 lines)
- Direct deploy to production without staging verification
- Background task failures (Celery) — now mitigated by Sentry error tracking

**Rule of thumb:** Before shipping changes to `pulse.py`, `highlights.py`, or `tasks.py`, write or run tests first. These three files account for the majority of fix-commit cycles.

### God File: `tasks.py` (2,747 lines)
All Celery tasks live in a single file. This increases coupling and makes changes riskier. Not urgent to refactor, but be aware that every change to this file has a larger blast radius than it should.

### Super Bowl One-Offs (Removed)
All Super Bowl LX party features have been removed: commercial/ad leaderboard, prop contest system, AI commentary/roasting, trivia, YouTube API integration, TV/Party mode page, player props endpoint, confetti/ECG animations. Code was deleted across ~15 files totaling ~7,000+ lines.

### localStorage Debt
Pinned events/futures use localStorage. Every new localStorage feature increases the complexity of the eventual auth migration. Avoid adding new localStorage-dependent features until Firebase Auth is in place.

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

10. **Celery tasks MUST use async DB sessions**: The database module only provides async sessions — there is no `SessionLocal`. New Celery tasks must follow this pattern:
    ```python
    @celery_app.task(bind=True)
    def my_task(self):
        return run_async(_my_task_impl())

    async def _my_task_impl():
        async with get_task_session() as session:
            result = await session.execute(...)
    ```
    Never use `SessionLocal` or synchronous `session.execute()` — it will raise `ImportError` silently in the worker.

11. **ESPN scoreboard vs teams API format**: The scoreboard endpoint returns team logos as a single `"logo"` string, while the teams endpoint returns a `"logos"` array. The `_parse_team` method in `espn_api.py` handles both.

12. **The Odds API commence_time can be wrong**: The Odds API occasionally returns game local times as if they were UTC (e.g., a 3:30 PM ET game as `15:30Z` instead of `20:30Z`). To prevent this: (a) odds polling upserts no longer overwrite `commence_time` after initial insert, and (b) the ESPN sync task corrects mismatches automatically. For bulk retroactive fixes, use `POST /api/admin/espn/fix-commence-times`. **Note:** `tasks.py` now has `import logging` and `logger = logging.getLogger(__name__)` (added Feb 2026). Some older code in the file still uses `print()` instead.

---

## Quick Reference

| What | Where |
|------|-------|
| API docs | `/docs` on backend URL |
| Pulse explainer | https://odds.alexbain.com/pulse |
| Pulse Hall of Fame | https://odds.alexbain.com/pulse/hall-of-fame |
| Search | https://odds.alexbain.com/search?q=celtics |
| PRD | `docs/PRD.md` |
| Debug endpoints | `/api/events/debug/*` |
| Admin endpoints | `/api/admin/*` |
