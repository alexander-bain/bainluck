# OddsTracker - Product Requirements Document

## Executive Summary

OddsTracker is a visual-first sports odds experience that translates betting markets into intuitive, real-time representations of how a game is expected to unfold—before and during play.

The product is designed primarily as a **second screen for casual sports fans**: people watching a game who want immediate, understandable context for what just happened and why it mattered, without having to interpret betting lines or think like gamblers.

OddsTracker is not a sportsbook, not a pick-selling tool, and not a stats-heavy analytics platform. It is the cleanest, fastest way to visualize expectation shifts in live sports.

---

## Vision & North Star

### Vision
Make betting odds understandable to non-bettors by turning them into clean, live, visual signals about game expectations.

### North Star Statement
**OddsTracker is the cleanest odds visualization tool on the internet.**

### North Star Metric
**Time-to-understanding**: How quickly a user can understand what changed in a game and how much it mattered.

Proxy metrics: time on event view, repeat usage during live games, chart interactions.

### The 10-Second Success Moment
A new user should immediately think:

> "Oh—this shows me how much that play actually changed the game."

This applies equally to a touchdown, a red card, a key injury announcement, or a momentum swing late in a close game. The mental model is **expectation shift**, not gambling.

---

## Target Users

### Primary User (v1 Focus)
**Casual sports fans who don't bet much (or at all).**

They:
- Watch games live
- Hear commentators reference odds or "win probability"
- Want context, not picks
- Are curious but not mathematically inclined
- Are often watching on TV with a phone in hand

### Secondary Users
- Fantasy sports players tracking matchup likelihoods
- Casual bettors seeking quick probability insights
- Users interested in prediction markets (politics, entertainment, events)

### Explicitly Deprioritized (for now)
- Professional bettors
- Arbitrage / line-shopping users
- Heavy fantasy analytics users

These users may still find value, but the product will not optimize for them in early versions.

---

## Product Principles

1. **Visual > Numerical** — Percentages and charts beat odds formats every time.
2. **Explain Movement, Not Advice** — We show what changed, not what to bet.
3. **Second-Screen Native** — The product assumes the user is watching the game elsewhere.
4. **Respect Attention** — No spammy notifications. Silence is sometimes the correct UX.
5. **Responsible by Design** — Betting is contextual information, not the call to action.

---

## What This Product Is Not (Non-Goals)

OddsTracker will **not** become:
- A sportsbook or betting interface
- A pick-selling or tout product
- A social network
- A news or commentary site
- A heavy statistical modeling platform

These exclusions are intentional and protect product clarity.

---

## Core User Experience

### The Second-Screen Experience

OddsTracker is designed to be open during live play, but only active when meaningful.

#### Live Update Philosophy
- Odds update when markets move meaningfully
- No "fake" updates during blowouts or dead time
- Users are told why updates pause

#### UX States (Explicit)

| State | Display |
|-------|---------|
| Live & Updating | "Live: Updating every ~60 seconds" |
| Paused (No Movement) | "No significant changes—game is currently a blowout" |
| Paused (Market Halted) | "Markets paused during review / injury / timeout" |
| Upcoming Update | "Next update expected after current drive / possession" |

This removes confusion and builds trust.

#### Automatic Context (Lightweight)
When a large shift occurs, OddsTracker may surface:
- "That TD increased win probability by +14%"
- "This injury moved the line significantly"

No narration. No hype. Just facts.

---

## Architecture

### System Design

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   The Odds API  │────▶│  Data Pipeline  │────▶│   PostgreSQL    │
│   (External)    │     │  (Poll/Store)   │     │   (AWS RDS)     │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
┌─────────────────┐                                      │
│     Kalshi      │──────────────────────────────────────┤
│   (Future)      │                                      │
└─────────────────┘                                      │
                        ┌─────────────────┐              │
                        │   REST API      │◀─────────────┘
                        │   (FastAPI)     │
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
      ┌───────────┐      ┌───────────┐      ┌───────────┐
      │  Web App  │      │  iOS App  │      │  Widgets  │
      │  (Next.js)│      │ (SwiftUI) │      │   (iOS)   │
      └───────────┘      └───────────┘      └───────────┘
```

### Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Backend API | FastAPI (Python) | Modern, fast, great typing support |
| Database | PostgreSQL (AWS RDS) | Existing infrastructure |
| Task Queue | Celery + Redis | Scheduled odds polling |
| Web Frontend | Next.js (React) | SSR for shareable links, great DX |
| iOS App | SwiftUI | Modern Apple development |
| Auth | Firebase Auth | Easy Google/Apple sign-in |
| Analytics | Google Analytics 4 | Cross-platform tracking, User-ID support |
| LLM Integration | Claude API | Context generation for odds movements |

---

## Data Model

### Core Tables

```sql
-- Sports we track
CREATE TABLE sports (
    id SERIAL PRIMARY KEY,
    key VARCHAR(50) UNIQUE NOT NULL,  -- e.g., 'basketball_nba'
    name VARCHAR(100) NOT NULL,        -- e.g., 'NBA'
    active BOOLEAN DEFAULT true
);

-- Teams/Players
CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    sport_id INTEGER REFERENCES sports(id),
    external_id VARCHAR(100),          -- ID from odds API
    name VARCHAR(200) NOT NULL,
    abbreviation VARCHAR(10),
    logo_url TEXT
);

-- Individual games/matches
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    sport_id INTEGER REFERENCES sports(id),
    external_id VARCHAR(100) UNIQUE,
    home_team_id INTEGER REFERENCES teams(id),
    away_team_id INTEGER REFERENCES teams(id),
    commence_time TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'scheduled',  -- scheduled, live, completed
    home_score INTEGER,
    away_score INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Raw odds snapshots (high frequency, pruned after aggregation)
CREATE TABLE odds_snapshots (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    bookmaker VARCHAR(50),

    -- Moneyline
    home_moneyline INTEGER,
    away_moneyline INTEGER,

    -- Spread
    home_spread DECIMAL(4,1),
    home_spread_odds INTEGER,
    away_spread_odds INTEGER,

    -- Totals
    over_under DECIMAL(5,1),
    over_odds INTEGER,
    under_odds INTEGER,

    -- Calculated fields
    home_win_probability DECIMAL(5,4),
    away_win_probability DECIMAL(5,4),
    projected_home_score DECIMAL(5,1),
    projected_away_score DECIMAL(5,1)
);

-- Aggregated odds (permanent storage)
CREATE TABLE odds_aggregated (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id),
    period_start TIMESTAMP WITH TIME ZONE,
    period_end TIMESTAMP WITH TIME ZONE,

    avg_home_win_prob DECIMAL(5,4),
    min_home_win_prob DECIMAL(5,4),
    max_home_win_prob DECIMAL(5,4),

    avg_projected_total DECIMAL(5,1),
    snapshot_count INTEGER,

    created_at TIMESTAMP DEFAULT NOW()
);

-- Users (optional auth)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    firebase_uid VARCHAR(128) UNIQUE,
    email VARCHAR(255),
    display_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- User favorites
CREATE TABLE user_favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    team_id INTEGER REFERENCES teams(id),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, team_id)
);

-- Futures/Outrights (championship odds, MVP, etc.)
CREATE TABLE futures (
    id SERIAL PRIMARY KEY,
    sport_id INTEGER REFERENCES sports(id),
    market_type VARCHAR(50) NOT NULL,      -- 'championship', 'mvp', 'division_winner', etc.
    name VARCHAR(200) NOT NULL,             -- 'NBA Championship 2025-26'
    season VARCHAR(20),                     -- '2025-26'
    status VARCHAR(20) DEFAULT 'active',    -- active, settled, cancelled
    settlement_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Futures outcomes (teams/players that can win)
CREATE TABLE futures_outcomes (
    id SERIAL PRIMARY KEY,
    future_id INTEGER REFERENCES futures(id),
    team_id INTEGER REFERENCES teams(id),   -- NULL for player props
    player_name VARCHAR(200),               -- For MVP, awards
    external_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Futures odds snapshots
CREATE TABLE futures_snapshots (
    id SERIAL PRIMARY KEY,
    outcome_id INTEGER REFERENCES futures_outcomes(id),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    bookmaker VARCHAR(50),
    odds INTEGER,                           -- American odds
    win_probability DECIMAL(5,4),
    valid_until TIMESTAMP WITH TIME ZONE
);

-- Prediction markets (Kalshi, etc.)
CREATE TABLE prediction_markets (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,            -- 'kalshi', 'polymarket', etc.
    external_id VARCHAR(100) UNIQUE,
    category VARCHAR(50),                   -- 'politics', 'entertainment', 'sports', 'economics'
    title VARCHAR(500) NOT NULL,
    description TEXT,
    end_date TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Prediction market snapshots
CREATE TABLE prediction_market_snapshots (
    id SERIAL PRIMARY KEY,
    market_id INTEGER REFERENCES prediction_markets(id),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    yes_price DECIMAL(5,4),                 -- 0.00-1.00
    no_price DECIMAL(5,4),
    volume INTEGER,
    open_interest INTEGER
);
```

### Indexes

```sql
CREATE INDEX idx_odds_snapshots_event ON odds_snapshots(event_id);
CREATE INDEX idx_odds_snapshots_captured ON odds_snapshots(captured_at);
CREATE INDEX idx_events_commence ON events(commence_time);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_futures_sport ON futures(sport_id);
CREATE INDEX idx_futures_snapshots_outcome ON futures_snapshots(outcome_id);
CREATE INDEX idx_prediction_markets_category ON prediction_markets(category);
```

---

## Core Algorithms

### Odds to Probability Conversion

American odds to implied probability:

```python
def american_to_probability(odds: int) -> float:
    """Convert American odds to implied probability."""
    if odds > 0:
        return 100 / (odds + 100)
    else:
        return abs(odds) / (abs(odds) + 100)

def remove_vig(home_prob: float, away_prob: float) -> tuple[float, float]:
    """Remove bookmaker's vig to get true probabilities."""
    total = home_prob + away_prob
    return home_prob / total, away_prob / total
```

### Projected Score Calculation

Using moneyline favorite and over/under:

```python
def project_scores(home_prob: float, over_under: float) -> tuple[float, float]:
    """
    Project final scores based on win probability and total.

    This is a simplified model. The favorite is expected to score
    proportionally more of the total based on their win probability.

    Note: Clearly labeled as illustrative in the UI, not a prediction.
    """
    # Adjust for the correlation between winning and scoring more
    # A team with 60% win prob doesn't score 60% of points
    # Use a dampened model
    home_share = 0.5 + (home_prob - 0.5) * 0.3

    home_score = over_under * home_share
    away_score = over_under * (1 - home_share)

    return round(home_score, 1), round(away_score, 1)
```

### Pulse (Game Excitement Metric)

OddsTracker's proprietary excitement metric measuring how "alive" a game is based on probability movement patterns.

**Components (weighted):**
- **Heart Rate (25%)**: Frequency of significant probability moves (≥2% threshold)
- **Amplitude (30%)**: Magnitude of probability swings (RMS calculation)
- **Arrhythmia (15%)**: Unpredictability/variance of changes
- **Vitals (30%)**: Current game competitiveness (closeness to 50/50)
- **Lead Changes Bonus (0-20%)**: Each time probability crosses 50%

**Time Weight Enhancement:**
Late-game drama counts more. Uses exponential curve: `0.6 + 0.4 × (progress^1.5)`

**Score Scale (1-100):**
| Score | Status | Label | Emoji |
|-------|--------|-------|-------|
| 81-100 | Racing | Must-Watch / Incredible | 🫀 |
| 61-80 | Strong | Exciting / Engaging | 💓 |
| 41-60 | Steady | Competitive / Steady | 💗 |
| 21-40 | Weak | One-Sided / Slow | 🩺 |
| 1-20 | Flatline | Skip It | 📉 |

**Implementation:** `backend/app/utils/pulse.py`

**Requirements:**
- Minimum 3 odds snapshots to calculate
- Sport-specific expected durations for time weighting
- Updates in real-time for live games, batch-processed for completed games

### Futures Pulse (Planned)

Adapt the Pulse concept to measure the drama of championship races over weeks/months.

**Proposed Components (weighted):**
- **Volatility (30%)**: Standard deviation of probability changes across all outcomes over time
- **Compression (25%)**: How close the top N contenders are (tight race = exciting)
- **Lead Changes (25%)**: Number of times the #1 favorite has changed
- **Momentum (20%)**: Recent rate of change for top contenders (surging teams)

**Key Differences from Event Pulse:**
| Event Pulse | Futures Pulse |
|-------------|---------------|
| Measures a single game (2-4 hours) | Measures a season (weeks/months) |
| Binary outcome (home vs away) | Multiple outcomes (10-30+ contenders) |
| Focuses on live swings | Focuses on trajectory over time |
| Time-weighted for late-game drama | Could weight for late-season/playoff drama |

**Questions to Resolve:**
- **Time window**: Should we measure all-time volatility or recent (30 days)?
- **Weighting**: Should recent changes count more than early-season changes?
- **Display**: Single score like events, or a richer "race status" display?
- **Threshold**: What's "exciting" for futures? Probably need different calibration than events.

### Highlights Ranking Algorithm (Planned)

```python
def calculate_highlight_score(event: Event, context: dict) -> float:
    """
    Calculate a composite score for surfacing events in highlights.

    Factors (weighted):
    - Closeness (40%): How close is the matchup?
    - Timing (25%): Is the game about to start or live?
    - Popularity (15%): Is this a major sport/league?
    - Movement (10%): Have odds moved significantly recently?
    - User relevance (10%): Does user follow these teams?

    Returns score 0-100 for ranking.
    """
    closeness = 1 - abs(event.home_prob - 0.5) * 2  # 0-1

    # Timing: live games > starting soon > later
    if event.status == 'live':
        timing = 1.0
    elif event.minutes_to_start < 60:
        timing = 0.8
    elif event.minutes_to_start < 180:
        timing = 0.5
    else:
        timing = 0.2

    # Popularity by league tier
    tier = context.get('sport_tier', 3)  # 1=major, 2=secondary, 3=other
    popularity = {1: 1.0, 2: 0.6, 3: 0.3}.get(tier, 0.3)

    # Recent odds movement (large swings are interesting)
    movement = min(context.get('prob_change_1h', 0) * 5, 1.0)

    # User relevance (if they follow these teams)
    user_relevance = 1.0 if context.get('user_favorite') else 0.3

    score = (
        closeness * 0.40 +
        timing * 0.25 +
        popularity * 0.15 +
        movement * 0.10 +
        user_relevance * 0.10
    )

    return round(score * 100, 1)
```

---

## API Endpoints

### Public Endpoints (No Auth)

```
GET  /api/sports                    # List supported sports
GET  /api/events                    # List upcoming events
GET  /api/events/{id}               # Event details with current odds
GET  /api/events/{id}/history       # Odds history for trending chart
GET  /api/share/{event_id}          # Shareable event view (web)

# Futures
GET  /api/futures                   # List active futures markets
GET  /api/futures/{id}              # Future details with current odds
GET  /api/futures/{id}/history      # Odds history for a future

# Prediction Markets (Kalshi, etc.)
GET  /api/predictions               # List active prediction markets
GET  /api/predictions/{id}          # Market details
GET  /api/predictions/{id}/history  # Price history
```

### Authenticated Endpoints

```
GET  /api/me                        # Current user profile
GET  /api/me/favorites              # User's favorite teams
POST /api/me/favorites              # Add favorite team
DELETE /api/me/favorites/{team_id}  # Remove favorite

POST /api/me/notifications          # Configure notification preferences
GET  /api/me/notifications          # Get notification settings
```

### Internal/Admin

```
POST /api/admin/poll-odds           # Trigger manual odds poll
POST /api/admin/aggregate           # Trigger aggregation job
POST /api/admin/discover-events     # Trigger event discovery for all sports
```

---

## Search

### Philosophy

Search is a core discovery mechanism that lets users find games, teams, and historical data quickly. The search experience should feel **instant, forgiving, and intelligent**—users shouldn't need to know exact team names or league structures.

### Current Implementation (v1) ✅

**Endpoint:** `GET /api/events/search?q=celtics`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `q` | required | Search query (min 2 chars) |
| `sport` | none | Filter by sport key |
| `page` | 1 | Page number |
| `per_page` | 25 | Results per page (max 100) |
| `days_back` | 30 | How far back to search |
| `include_upcoming` | true | Include scheduled games |

**Features:**
- Case-insensitive partial matching ("celt" finds "Boston Celtics")
- Searches both home and away team names
- Results ordered: Live → Upcoming → Completed
- Sport disambiguation (shows which leagues matched)
- Paginated results with Previous/Next navigation
- Trigram indexes for fast ILIKE queries

**UI Components:**
- Header search box with debounced dropdown (300ms)
- Full search results page at `/search?q=...`
- Sport filter pills when multiple leagues match

### Search Roadmap

#### Phase 1: Enhanced Filtering (Q2 2026)
Extend search with structured filters:

```
GET /api/events/search?q=celtics&sport=basketball_nba&season=2025-26&status=completed
```

| Filter | Examples |
|--------|----------|
| `sport` | `basketball_nba`, `americanfootball_nfl` |
| `league` | Alias for sport (user-friendly) |
| `season` | `2025-26`, `2024-25` |
| `status` | `live`, `scheduled`, `completed` |
| `date_from` | `2025-01-01` |
| `date_to` | `2025-12-31` |
| `team` | Exact team filter (after disambiguation) |

**UI: Filter chips**
```
[🏀 NBA ✕] [2025-26 Season ✕] [Completed only ✕]

Showing 47 results for "Celtics"
```

#### Phase 2: Smart Query Parsing (Q3 2026)
Parse natural-language-like queries into structured filters:

| User Types | Parsed As |
|------------|-----------|
| "celtics nba" | team=celtics, sport=basketball_nba |
| "celtics 2024" | team=celtics, season=2024-25 |
| "celtics vs lakers" | team1=celtics, team2=lakers |
| "nfl week 10" | sport=nfl, week=10 |
| "march madness" | sport=basketball_ncaab, date=march |

**Implementation:**
- Regex patterns for common formats
- Sport/league aliases ("nba" → "basketball_nba")
- Date parsing ("last week", "yesterday", "march")
- Team abbreviation mapping ("LAL" → "Los Angeles Lakers")

#### Phase 3: Suggested Searches (Q3 2026)
Surface interesting queries users might want:

**Contextual Suggestions:**
```
🔥 Trending
• "Super Bowl" (1.2M searches today)
• "Chiefs vs Eagles" (Live now)

⭐ Based on your favorites
• "Celtics recent games"
• "Patriots upcoming"

📊 Discover
• "Biggest upsets this week"
• "Closest games today"
• "Top 10 exciting NBA games"
```

**Pre-built Queries:**
- "Most exciting [sport] games this week"
- "Biggest probability swings today"
- "Close games right now"
- "Upsets in the last 7 days"

#### Phase 4: Natural Language Search (Q4 2026)
LLM-powered query understanding for complex requests:

| User Query | System Interprets |
|------------|-------------------|
| "top 5 most exciting celtics games from 2 years ago" | team=celtics, sort=gei desc, limit=5, date_range=2024 |
| "games where the underdog won last month" | status=completed, upset=true, days_back=30 |
| "close NBA games this weekend" | sport=nba, closeness>0.9, date=this_weekend |
| "when do the lakers play next" | team=lakers, status=scheduled, limit=1 |
| "patriots biggest comeback this season" | team=patriots, sort=comeback_margin, season=current |

**Architecture:**
```
User Query → LLM (Claude) → Structured Filters → Database Query → Results
                ↓
         "I interpreted your search as:
          Celtics games, sorted by excitement,
          from 2024 season, top 5"
```

**Implementation Notes:**
- Use Claude API to parse ambiguous queries
- Cache common query interpretations
- Show "interpreted as" explanation for transparency
- Fallback to basic search if LLM parsing fails
- Rate limit LLM calls (maybe only for logged-in users)

#### Phase 5: Saved Searches & Alerts (2027)
For authenticated users:

- Save frequent searches
- Get notified when new results match
- "Alert me when Celtics play a close game"
- Weekly digest of saved search results

### Search Quality Metrics

| Metric | Target |
|--------|--------|
| Zero-result rate | < 5% |
| Click-through rate | > 40% |
| Time to first click | < 3 seconds |
| Search refinement rate | < 20% (lower = better initial results) |

### Database Optimization

**Current indexes:**
```sql
-- Trigram indexes for fast ILIKE
CREATE INDEX ix_events_home_team_name_trgm ON events USING gin (home_team_name gin_trgm_ops);
CREATE INDEX ix_events_away_team_name_trgm ON events USING gin (away_team_name gin_trgm_ops);

-- Composite index for filtering
CREATE INDEX ix_events_commence_status ON events (commence_time, status);
```

**Future considerations:**
- Full-text search with `tsvector` for multi-field search
- Materialized view for "searchable events" with denormalized sport names
- Elasticsearch if query complexity grows significantly

### Search UX Principles

1. **Instant feedback** — Show results as user types (debounced)
2. **Forgive mistakes** — Fuzzy matching, typo tolerance
3. **Disambiguate clearly** — When "Celtics" matches multiple leagues, show all with clear labels
4. **Remember context** — Recent searches, personalized suggestions
5. **Fail gracefully** — No results? Suggest alternatives, don't dead-end

---

## Feature Phases & Roadmap

### Phase 1: MVP ✅ Complete
**Core visualization shipped to production.**

- [x] Project setup and CI/CD
- [x] Database schema and migrations
- [x] Odds API integration with adaptive polling
- [x] Live win probability (%)
- [x] Web-first, mobile-optimized UI
- [x] Auto-refresh (configurable: 32s live, 120s scheduled)
- [x] Odds movement chart (Probability Trend with time range filters)
- [x] Per-bookmaker probability breakdown (gray lines on charts, hover tooltips)
- [x] Sport/league filtering with category grouping
- [x] Sorting by closeness and game time

### Phase 2: Analytics & Observability ✅ Complete
**Comprehensive tracking for product insights.**

- [x] Google Analytics 4 integration with GA4 Measurement Protocol
- [x] Cross-platform User-ID support (for future iOS app)
- [x] GDPR-compliant Consent Mode v2
- [x] Event taxonomy: navigation, filters, interactions, engagement
- [x] Session engagement tracking (events viewed, charts used, filters applied)
- [x] Scroll depth and time-on-page tracking
- [x] Chart interaction analytics

### Phase 3: Reliability & Data Quality 🔄 In Progress
**Ensuring all sports are tracked properly.**

- [x] Event discovery task (polls ALL sports, not just those with existing events)
- [x] Stale data detection and auto-closing of stuck events
- [x] Per-sport polling intervals based on game proximity
- [ ] Improved error handling and retry logic
- [ ] Monitoring dashboard for poll health

### Phase 4: Pulse (Game Excitement Metric) ✅ Complete
**Proprietary excitement scoring for all games.**

Completed: February 2026

- [x] Implement Pulse calculation algorithm in backend (`backend/app/utils/pulse.py`)
- [x] Real-time Pulse updates for live games (every poll cycle)
- [x] Batch Pulse calculation for completed games (every 10 minutes)
- [x] PulseBadge component with tooltip showing component breakdown
- [x] Pulse displayed on all live, completed, and closed games
- [x] Explainer page at `/pulse` with full methodology
- [x] Admin endpoints for Pulse management (`/api/admin/pulse/status`, `/api/admin/pulse/recalculate`)
- [x] Debug endpoint for Pulse diagnostics (`/api/events/debug/pulse`)

### Phase 5: Authentication & Personalization
**User accounts for cross-device experience.**

Target: Q2 2026

- [ ] Firebase Auth integration (Google, Apple sign-in)
- [ ] Favorite teams (persisted to database)
- [ ] Personalized highlights based on favorites
- [ ] Cross-device sync of preferences
- [ ] Optional: Email notifications for favorite teams

**Auth Philosophy:**
- No required sign-in — logged-out experience must feel complete
- Auth unlocks: Favorites sync, notifications, cross-device
- Auth is **pull-based, not forced**

### Phase 6: LLM Integration 🔄 In Progress
**OpenAI-powered smart features.**

Infrastructure complete: February 2026

- [x] OpenAI GPT-4o-mini integration (`backend/app/services/llm.py`)
- [x] Generic `classify()` utility for text classification
- [x] Hybrid futures categorization (rules + LLM fallback)
- [x] LLM results cached in database (`llm_sport_category` column)
- [x] In-memory cache that skips `None` results (allows retries on failures)
- [x] Admin endpoints for triggering categorization
- [x] Expanded sport categories: lacrosse, chess, poker added
- [x] Improved LLM prompt with athlete/team examples and common response mappings
- [ ] Detect significant probability swings (>10% change)
- [ ] Generate brief explanations for odds movements
- [ ] Cache explanations to avoid redundant API calls
- [ ] Show explanations on event detail page and in highlights

**LLM Service Capabilities:**
```python
from app.services import llm

# General classification
result = llm.classify("Some text", ["option1", "option2", "option3"])

# Futures categorization (with caching)
category = llm.classify_futures_market_cached("2026 Masters Tournament Winner")
```

**Categorization Status (as of Feb 2026):**
- ~170 futures markets processed through hybrid categorization
- Pattern matching handles ~85% of markets (baseball awards, pro sports, leagues, etc.)
- LLM handles remaining edge cases (athlete names, ambiguous markets)
- ~67 markets may still need improved LLM prompt (unmerged PR with better prompt)

**Future LLM Use Cases:**
- Plain English explanations for odds movements
- Team name normalization across sources
- Smart search query understanding
- Market description generation

**Principles:**
- Brief, factual, non-predictive
- Only surface for meaningful events
- No gambling advice or encouragement

### Phase 7: iOS App
**Native second-screen experience.**

Target: Q3 2026

- [ ] SwiftUI app with feature parity to web
- [ ] Second-screen optimized UI (glanceable, minimal interaction)
- [ ] Native charts with smooth animations
- [ ] Favorites and personalized feed
- [ ] Share extension for quick sharing
- [ ] Background refresh
- [ ] Widgets (Lock Screen, Home Screen)
  - Current game win probability
  - Upcoming games for favorite teams
  - "Most Exciting Game Right Now"

### Phase 8: Futures Markets ✅ Complete
**Championship odds, MVP races, and outrights.**

Completed: February 2026

- [x] Database schema for futures (`futures_markets`, `futures_outcomes`, `futures_odds_snapshots`)
- [x] Poll futures odds from The Odds API (hourly task)
- [x] Futures visualization with horizontal bar charts
- [x] Movement indicators (24h change, rank change)
- [x] Futures categories via hybrid categorization (rules + LLM)
- [x] Sport grouping on homepage
- [x] Futures detail pages with all outcomes
- [x] Search includes futures markets
- [x] Pulse Hall of Fame page (`/pulse/hall-of-fame`)

**UI Features:**
- Grouped by sport category on homepage
- Top 5 outcomes shown in list view
- Full outcome list on detail page
- 24h probability change indicators

### Phase 9: Prediction Markets (Kalshi Integration) ✅ Complete
**Politics, entertainment, and event-based markets.**

Completed: February 2026

- [x] Kalshi API integration (`backend/app/services/kalshi_api.py`)
- [x] Polling task with rate limiting (hourly at :45)
- [x] Stores bid/ask spreads and timing info
- [x] Categories: Sports, Golf, Football, Basketball, Baseball, Hockey, Tennis
- [x] Commence time and resolution date populated
- [x] LLM-based categorization for uncategorized markets

**Data Model:**
- Kalshi events → `futures_markets` table (source="kalshi")
- Kalshi markets → `futures_outcomes` table
- Stores: `yes_bid`, `yes_ask`, `last_price`

**To add more categories** (e.g., Entertainment), edit `sports_categories` in `tasks.py`

### Phase 10: Additional Data Sources
**Expanding coverage and depth.**

Target: 2027

- [ ] Polymarket integration (if legally viable)
- [ ] PredictIt (if still operational)
- [ ] International sportsbooks for broader odds coverage
- [ ] Alternative odds sources for redundancy
- [ ] Real-time sports data (play-by-play) for richer context

---

## Recent Improvements (February 2026)

### Pulse - Game Excitement Metric ✅ NEW
- **Proprietary algorithm**: Measures game excitement based on probability movement patterns using a "vital signs" metaphor
- **Real-time updates**: Pulse calculated every poll cycle for live games
- **Component breakdown**: Momentum Swings, Drama Level, Competitiveness, Lead Changes
- **Visual badges**: Color-coded badges (🫀💓💗🩺📉) displayed on all games
- **Tooltip explanations**: Human-friendly descriptions of what makes each game exciting
- **Explainer page**: Full methodology at `/pulse`
- **Admin tools**: Status check and batch recalculation endpoints

### Analytics Implementation
- **Comprehensive GA4 tracking**: Full event taxonomy with clear hierarchy
- **Cross-platform ready**: User-ID support for future iOS app
- **Privacy compliant**: Consent Mode v2 with granular controls
- **Engagement metrics**: Scroll depth, time on page, chart interactions

### Backend Improvements
- **Event discovery task**: New `discover_events` Celery task that polls ALL active sports every 15 minutes, solving the chicken-and-egg problem where sports without existing events were never polled
- **Per-sport polling**: Intelligent polling intervals based on game proximity
- **Admin router**: New `/api/admin` endpoints for Pulse management and diagnostics

### UI/UX Polish
- **Removed user-facing staleness warnings**: "Needs Review" and "Stale" indicators now tracked internally for analytics but not shown to users
- **Improved error handling**: History loading errors now show actual error message with retry button
- **Cleaner live experience**: All live events show as LIVE without conditional warnings
- **Pulse badges everywhere**: All completed/closed games now show their Pulse score
- **Pulse Hall of Fame**: New page at `/pulse/hall-of-fame` showing top 25 highest and lowest Pulse games ever

### LLM Infrastructure ✅ NEW
- **OpenAI GPT-4o-mini integration**: Generic LLM service for classification tasks
- **Hybrid futures categorization**: Pattern matching rules (regex) + LLM fallback for edge cases
- **Improved LLM prompt**: Sports-aware prompt with athlete/team examples and common response mappings
- **Database caching**: LLM results stored in `llm_sport_category` column to avoid repeat API calls
- **In-memory cache**: Skips caching `None` results so failed classifications can be retried
- **Admin endpoints**: `/api/admin/futures/categorize` to trigger batch categorization with dry-run support
- **Cost-effective**: ~$0.001 per classification, results cached permanently
- **Expanded categories**: Lacrosse, chess, poker added to classification options

### Futures & Kalshi Integration ✅ NEW
- **Futures markets**: Championship odds, MVP races, division winners from The Odds API
- **Kalshi prediction markets**: Sports-related prediction markets with timing info
- **Smart categorization**: 170+ markets auto-categorized using hybrid rules + LLM
- **Pattern improvements**: Baseball awards (Manager, Comeback Player), pro sports, NWSL, Manchester United, Tewaaraton, WSOP, and more
- **Unified display**: Both sources appear together, grouped by sport category
- **Search integration**: Futures markets included in search results

### Bug Fixes
- **Upset Brewing fix**: Pre-game line movement no longer triggers "Upset Brewing" label for scheduled events
- **Favorite switched logic**: `favorite_switched` flag only set for live/completed games, not scheduled
- **Frontend upset filter**: Updated to use `is_upset` flag instead of raw `favorite_switched`
- **PulseBadge import**: Fixed default export import in Hall of Fame page

---

## Futures Market Design

### Data Model
Futures differ from game odds in several ways:
- **Many outcomes**: A championship has 30+ teams, not 2
- **Longer timeframes**: Season-long, not game-length
- **Slower updates**: Daily changes, not minute-by-minute

### Visualization Approach

**Championship Odds View:**
```
NBA Championship 2025-26

Boston Celtics     ████████████████████  18%  +450
Denver Nuggets     ███████████████       14%  +600
Milwaukee Bucks    ████████████          11%  +800
Phoenix Suns       ██████████            9%   +1000
...

[Show all 30 teams]

📈 Rising: OKC Thunder (+3% this week)
📉 Falling: LA Lakers (-2% this week)
```

**Historical View:**
- Line chart showing probability over time for top 5-10 teams
- Ability to select/deselect teams
- Key events annotated (trades, injuries, playoff clinching)

### Polling Strategy
- Poll futures once daily (overnight)
- Poll more frequently during key events (trade deadline, playoffs)
- Store all historical snapshots for trend analysis

---

## Prediction Markets Design (Kalshi)

### Data Model
Prediction markets are simpler than sports:
- **Binary outcomes**: Yes/No
- **Price = Probability**: A $0.65 "Yes" price = 65% implied probability
- **Volume matters**: Low-volume markets may be less reliable

### Visualization Approach

**Market Card:**
```
Will the Fed raise rates in March 2026?

YES  ████████████████████████  67%  ($0.67)
NO   ████████████              33%  ($0.33)

Volume: $1.2M | Ends: Mar 15, 2026

📈 Up 5% today
```

**Trend Chart:**
- Same style as probability trend charts
- Show price (0.00-1.00) over time
- Volume overlay option

### Categories
1. **Politics**: Elections, policy, geopolitical events
2. **Economics**: Fed rates, inflation, GDP
3. **Entertainment**: Awards, box office, TV
4. **Sports-Adjacent**: Season outcomes, records, milestones
5. **Science/Tech**: SpaceX launches, AI milestones

### Integration Notes
- Kalshi has well-documented API
- Rate limits and authentication required
- Some markets may have state restrictions

---

## Sports Coverage

### Blacklist Approach

OddsTracker uses a **blacklist** rather than a whitelist for sports coverage:

- **Included**: All sports from The Odds API except those on the blacklist
- **Excluded**: Soccer (all soccer_* leagues), Cricket, Rugby, AFL

This means the system automatically picks up new sports that The Odds API adds without requiring code changes.

### Why These Exclusions?

**Soccer**: Different market dynamics with draws, complex scoring, and the sheer volume would overwhelm the product focus.

**Cricket/Rugby/AFL**: Low US audience and different market structures.

### Sport Categories

Sports are grouped into categories for the UI based on their API key prefix:

| Category | Prefix(es) | Emoji |
|----------|------------|-------|
| Football | americanfootball_* | 🏈 |
| Basketball | basketball_* | 🏀 |
| Baseball | baseball_* | ⚾ |
| Hockey | icehockey_* | 🏒 |
| MMA | mma_* | 🥋 |
| Boxing | boxing_* | 🥊 |
| Golf | golf_* | ⛳ |
| Tennis | tennis_* | 🎾 |
| Politics | politics_* | 🗳️ |
| Esports | esports_* | 🎮 |
| Motorsport | motorsport_*, racing_* | 🏎️ |
| Other | (any unmatched) | 🏆 |

Unknown sports automatically fall into the "Other" category and are displayed with a trophy emoji.

### High Priority Sports

| Sport | API Key Pattern | Notes |
|-------|-----------------|-------|
| NFL | americanfootball_nfl | Primary focus |
| NBA | basketball_nba | Primary focus |
| MLB | baseball_mlb | Primary focus |
| NHL | icehockey_nhl | Primary focus |
| College Football | americanfootball_ncaaf | Strong user demand |
| College Basketball | basketball_ncaab, basketball_wncaab | March Madness priority |

---

## Configuration

### Polling Strategy

| Scenario | Interval |
|----------|----------|
| Live games | 32 seconds |
| Games starting in 0-2 hours | 60 seconds |
| Games starting in 2-6 hours | 2 minutes |
| Event discovery (all sports) | 15 minutes |
| Futures | Once daily |
| Prediction markets | Every 5 minutes |

### Data Retention

| Data Type | Retention |
|-----------|-----------|
| Raw snapshots | 7 days after event completion |
| Aggregated data | Indefinite |
| Event metadata | Indefinite |
| Futures history | Indefinite |
| Prediction market history | Indefinite |

---

## Authentication Philosophy

- **No required sign-in** — Logged-out experience must feel complete
- Auth exists to unlock: Favorites sync, Notification controls, Cross-device preferences
- Auth is **pull-based, not forced**

**Trigger Points (when to prompt for auth):**
- When user tries to add >3 favorite teams (localStorage limit)
- When user enables notifications
- When user explicitly taps "Sign In"

---

## Notifications Strategy

Notifications are high-risk and must earn their place.

### Initial Stance
- Off by default
- User-configured only
- Focused on major probability swings

### Examples
- "Win probability swung by 20%"
- "Late-game flip in close matchup"
- "Your team [Celtics] just took the lead"

**No constant pings. Silence is a feature.**

---

## Monetization (Future-Compatible, Not MVP)

### Long-Term Options
- Display ads (carefully placed, non-intrusive)
- Premium tier (e.g., ad-free, deeper history, advanced alerts)
- Affiliate partnerships (responsible, non-aggressive)

### Explicitly Excluded
- Selling picks
- Aggressive affiliate betting funnels
- Paywalling core functionality

Monetization must not distort trust or clarity.

---

## Legal & Compliance

- Neutral, compliant stance
- No state-specific betting actions
- No calls to action to place bets
- Clear labeling of prediction markets vs. sports betting

OddsTracker displays information, not transactions.

---

## Success Metrics

### Product Metrics
- % of sessions during live games
- Repeat opens during a single game
- Time spent on event view
- Highlights section engagement
- Futures page views

### Technical Metrics
- **Reliability**: 99.9% uptime for API
- **Freshness**: Odds updated within 2 minutes of source
- **Performance**: API response time < 200ms p95
- **Coverage**: % of sports with active event discovery

### Trust Metrics
- Low notification opt-out rates
- Low bounce rate during paused states
- Consent acceptance rate

---

## Open Questions

1. **Swing thresholds**: What threshold defines a "meaningful" probability swing worth surfacing? (Currently thinking 10% for LLM explanations)

2. **Futures update frequency**: Daily enough? Or should we poll more during playoffs/key events?

3. **Kalshi categories**: Which categories resonate most with our audience? Politics? Entertainment?

4. **iOS widget strategy**: Which widgets provide most value? Lock screen vs home screen?

5. **LLM cost management**: How to balance explanation quality with API costs?

6. **Auth conversion**: What's the right moment to prompt for sign-in without being annoying?

These are product experiments, not blockers.

---

## Development Priorities (Next 6 Months)

### Immediate (February 2026)
- ✅ Fix event discovery for NCAA basketball
- ✅ Pulse feature complete and deployed
- ✅ Kalshi prediction market integration
- ✅ Futures UI with hybrid categorization
- ✅ LLM infrastructure (OpenAI GPT-4o-mini)
- ✅ Pulse Hall of Fame page
- ✅ Upset Brewing bug fix
- 🔄 Merge remaining categorization PRs (improved patterns, LLM prompt, expanded categories)
- 🔄 Re-run categorize endpoint after merging to resolve remaining ~67 "other" markets
- Deploy analytics and observe user behavior
- Monitor polling health across all sports

### Near-term (March-April 2026)
- Register `sport`, `league`, `league_tier` as custom dimensions in GA4 Admin
- Add `"Entertainment"` to Kalshi sports_categories (2-line change in `tasks.py`)
- LLM-powered explanations for odds movements
- Begin Firebase Auth integration

### Mid-term (May-June 2026)
- Futures Pulse implementation (proposal documented in PRD, open questions to resolve)
- Favorites with cloud sync
- Begin iOS app development

### Later (Q3-Q4 2026)
- iOS app launch
- Smart search with LLM query understanding
- Natural language search

---

## Final Note

This product wins not by being smarter than users, but by being **clearer than everything else**.

If OddsTracker succeeds, users won't say:
> "This helped me bet."

They'll say:
> "I finally understood what was happening."
