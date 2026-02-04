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
└── docker-compose.yml           # Local dev environment
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

## Development Commands

```bash
# Backend (local)
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (local)
cd frontend
npm install
npm run dev

# Database migrations
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head

# Run Celery worker (local)
cd backend
celery -A app.tasks worker --loglevel=info

# Run Celery beat (scheduled tasks)
celery -A app.tasks beat --loglevel=info
```

---

## Environment Variables

### Backend (.env)
```
ODDS_API_KEY=xxx          # From the-odds-api.com
KALSHI_API_KEY=xxx        # From kalshi.com (optional - enables Kalshi polling)
OPENAI_API_KEY=xxx        # From platform.openai.com (optional - enables LLM categorization)
DATABASE_URL=xxx          # PostgreSQL connection string
REDIS_URL=xxx             # Redis for Celery
ADMIN_SECRET=xxx          # Optional: protect admin endpoints
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=https://what-are-the-odds-0283511a7d93.herokuapp.com
NEXT_PUBLIC_GA_MEASUREMENT_ID=xxx  # Google Analytics
```

---

## Key Features

### Pulse (Game Excitement Metric)
Proprietary 1-100 score measuring how exciting a game is based on probability swings.

**Components:**
- Heart Rate (25%): Frequency of odds movements
- Amplitude (30%): Size of probability swings
- Vitals (30%): How close the matchup is
- Lead Changes: Bonus for favorite flipping

**Files:** `backend/app/utils/pulse.py`, `frontend/components/PulseBadge.tsx`

**Admin Endpoints:**
- `GET /api/admin/pulse/status` - Check calculation status
- `POST /api/admin/pulse/recalculate?secret=xxx&limit=100` - Trigger batch recalc

### Highlights (Event Ranking)
Scores events 0–100 to decide what appears in the homepage Highlights section. Events need ≥30 points.

**Key design rule:** Pre-game closeness (e.g., 51/49) doesn't award points unless there's trend evidence — the line moved ≥5% from opening, tightened from lopsided to close, or the game is starting soon. This prevents aggregation noise from surfacing uninteresting events.

**Labels:** "Upset brewing" and "Close game" are live-only. "Line moving" requires ≥15% swing from opening. "Close matchup" requires starting soon.

**Files:** `backend/app/utils/highlights.py`, `frontend/app/page.tsx` (Highlights section rendering)

### Odds Polling
- Live games: Every 30 seconds
- Upcoming games: Every 2-5 minutes based on proximity
- Event discovery: Every 15 minutes (finds new games)

**Key task:** `poll_all_odds` in `backend/app/tasks.py`

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

**Files:**
- `frontend/hooks/usePinnedEvents.ts` - Event pinning hook
- `frontend/hooks/usePinnedFutures.ts` - Futures pinning hook
- `frontend/lib/api.ts` - `fetchEventsByIds()`, `fetchFuturesByIds()` for loading pinned items

**UI Locations:**
- Pin button on EventCard (top-left, visible on hover)
- Pin button on FuturesCard (top-left, visible on hover)
- Pin button on event detail page (hero section)
- Pin button on futures detail page (hero section)
- "📌 Pinned" section on homepage (above Highlights)
- "📌 Pinned Futures" section on homepage (below Pinned events)

**Future Enhancement:**
When Firebase Auth is implemented, migrate to database storage:
```sql
CREATE TABLE pinned_items (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    item_type VARCHAR(20) NOT NULL,  -- 'event' or 'futures'
    item_id INTEGER NOT NULL,
    pinned_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, item_type, item_id)
);
```

---

## API Patterns

### Response Format
```python
# Probabilities as decimals (0.0-1.0)
{"home_probability": 0.65, "away_probability": 0.35}

# Timestamps in ISO 8601
{"commence_time": "2026-02-03T19:00:00+00:00"}

# Pulse included when available
{"pulse": {"score": 75, "status": "strong", "emoji": "💓", "label": "Exciting"}}
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

1. ✅ Pulse feature complete and deployed
2. ✅ Kalshi prediction market integration
3. ✅ Futures UI improvements (sportsbooks, start times, categorization)
4. ✅ LLM infrastructure (OpenAI GPT-4o-mini for smart categorization)
5. ✅ Pulse Hall of Fame page
6. ✅ Pinned Events & Futures (localStorage-based tracking)
7. ✅ Futures categorization hardened (0 uncategorized markets)
8. 🔄 Monitoring and reliability improvements
9. 📋 Next: Pass Kalshi event category as sport_key for better disambiguation
10. 📋 Next: Firebase Auth for user accounts
11. 📋 Next: Migrate pinned items to database (after auth)
12. 📋 Next: LLM-powered odds movement explanations

**LLM categorization is robust** — `classify()` always returns a result, with expanded pattern matching (90+ rules) and LLM response normalization covering edge cases. See `backend/app/services/llm.py`.

See `docs/PRD.md` for full roadmap.

---

## Gotchas & Tips

1. **Alembic multiple heads**: If you see this error, check `down_revision` in migration files - they should form a single chain.

2. **Admin endpoints require mounting**: New routers must be added to both `main.py` AND `routes/__init__.py`.

3. **Pulse requires 3+ snapshots**: Events with fewer odds updates won't have Pulse calculated.

4. **Frontend types must match backend**: Keep `frontend/lib/types.ts` in sync with API responses.

5. **CORS**: Production domains are whitelisted in `backend/app/main.py`.

---

## Quick Reference

| What | Where |
|------|-------|
| API docs | `/docs` on backend URL |
| Pulse explainer | https://odds.alexbain.com/pulse |
| Search | https://odds.alexbain.com/search?q=celtics |
| PRD | `docs/PRD.md` |
| Debug endpoints | `/api/events/debug/*` |
| Admin endpoints | `/api/admin/*` |
