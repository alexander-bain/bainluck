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
| `backend/app/utils/pulse.py` | Pulse (excitement metric) algorithm |
| `backend/app/routes/events.py` | Main API - events, search, history |
| `frontend/components/EventCard.tsx` | Event display component |
| `frontend/components/PulseBadge.tsx` | Pulse score badge with tooltip |
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

### Odds Polling
- Live games: Every 30 seconds
- Upcoming games: Every 2-5 minutes based on proximity
- Event discovery: Every 15 minutes (finds new games)

**Key task:** `poll_all_odds` in `backend/app/tasks.py`

### Search
- Endpoint: `GET /api/events/search?q=celtics`
- Trigram indexes for fast ILIKE matching
- Results ordered: Live → Upcoming → Completed

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
Futures markets are categorized using pattern matching in `frontend/lib/sportCategories.ts`.

**How it works:**
1. First tries prefix matching on sport key (e.g., `golf_masters` → Golf)
2. Falls back to regex patterns on market name (e.g., "College Football Playoff" → Football)
3. Handles baseball awards like "AL MVP", "NL Cy Young" → Baseball
4. Uses athlete name detection for ambiguous markets like "US Open"

**To add new patterns**, edit `SPORT_PATTERNS` in `sportCategories.ts`:
```typescript
const SPORT_PATTERNS: Array<{ pattern: RegExp; category: string }> = [
  { pattern: /\b(al|nl)\s+(mvp|cy.young|rookie)\b/i, category: "baseball" },
  { pattern: /\bcollege.football\b/i, category: "football" },
  // Add new patterns here...
];
```

**Debug endpoints:**
```bash
# See futures count by source (odds_api vs kalshi)
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/futures/debug/sources"

# See sport linking for futures
curl "https://what-are-the-odds-0283511a7d93.herokuapp.com/api/futures/debug/sport-mapping"
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
4. 🔄 Monitoring and reliability improvements
5. 📋 Next: Firebase Auth for user accounts
6. 📋 Next: Favorites and personalization

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
