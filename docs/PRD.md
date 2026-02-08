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
- **Heart Rate (25%)**: Frequency of significant probability moves (≥2% threshold). Normalized: moves/min ÷ 0.6
- **Amplitude (30%)**: Magnitude of probability swings (RMS calculation). Normalized: RMS ÷ 0.15
- **Arrhythmia (15%)**: Unpredictability/variance of changes. Normalized: stdev ÷ 0.10
- **Vitals (30%)**: Average closeness to 50% across all snapshots (rewards games that stayed competitive throughout, not just games that ended close)
- **Lead Changes Bonus (0-20%)**: Each time probability crosses 50%

**Time Weight Enhancement:**
Late-game drama counts more. Uses exponential curve: `0.6 + 0.4 × (progress^1.5)`

**Percentile Scoring Layer:**
Raw scores are mapped to percentiles using completed/closed games as the reference set (`gei_percentiles` table). The percentile score is what users see. Falls back to raw score when percentiles are unavailable. Sport-specific percentiles are used when available, with global fallback.

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
- Minimum 10 odds snapshots to appear in Hall of Fame rankings (prevents low-data false positives)
- Sport-specific expected durations for time weighting
- Updates in real-time for live games, batch-processed for completed games
- After algorithm changes, force-recalculate via admin endpoint (scores are cached in `raw_gei`)

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

### Highlights Ranking Algorithm ✅ Implemented

Events are scored 0–100 by `backend/app/utils/highlights.py` using additive weights:

| Factor | Points | Notes |
|--------|--------|-------|
| Live | +30 | Requires `status="live"` AND `commence_time` passed |
| Close matchup (40–60%) | +25 | Pre-game: requires trend evidence (see below) |
| Very close (45–55%) | +10 | Bonus on top of close matchup |
| Favorite switched | +20 | Live/completed only |
| Major prob swing (≥15%) | +15 | From opening line |
| Major score swing (≥20%) | +10 | Projected total change from opening |
| Starting in <3h | +15 | |
| Starting in <1h | +10 | Bonus on top of 3h |
| Tier 1 league | +10 | NBA, NFL, MLB, NHL |
| Tier 2 league | +5 | NCAAB, NCAAF, MLS |
| Recent upset | +20 | Finished + favorite switched |
| Recently finished | +5 | Within 24h |

Events with score ≥30 appear in the Highlights section. Live close games and recent upsets always qualify regardless of score.

**Key design rule — pre-game trend evidence:**
Pre-game closeness (e.g., 51/49 across 13 books) could be aggregation noise, not a real story. Close-matchup points are only awarded for pre-game events when:
- The line **moved ≥5%** from opening (market is repricing)
- The opening was **not** close but the current odds are (line tightened)
- The game is **starting soon** (closeness becomes action-relevant)

**Labels** (shown on cards in the Highlights section):
| Label | Condition |
|-------|-----------|
| Recent upset | Finished + favorite switched |
| Upset brewing | Live + favorite switched |
| Coin flip | Live + very close (45–55%) |
| Close game | Live + close (40–60%) |
| Momentum shift | Live + major prob swing |
| Close matchup | Starting soon + close |
| Live | Live (no other flags) |
| Line moving | Pre-game + major prob swing (≥15%) |

### Ranking & Feed Evolution

The highlight scoring system is **v1 of a ranking algorithm** that will eventually power:
- **iOS feed tab**: A scrollable feed of the most interesting live and recently finished events
- **Search result ranking**: Results ordered by relevance and excitement, not just status
- **Widgets**: "Most Exciting Game Right Now" needs a single best answer
- **Notifications**: Deciding what's worth interrupting a user about

This is a long-term workstream. Each level builds on the previous one and should be validated before moving to the next.

#### Level 1: Snapshot scoring (current) ✅
`compute_highlight` compares current aggregated odds to opening odds. Simple additive weights. No access to odds history — just two points in time.

**What works:** Catches live upsets, close games, big pre-game line moves.
**What doesn't:** Can't distinguish noise from trends without the trend evidence heuristics. Can't detect momentum (accelerating movement vs one-time jump). All events of the same type score identically regardless of sport-specific context.

#### Level 2: Time-series aware scoring
Pass recent snapshot history into the ranking function. This enables:
- **Trend detection**: Is the line moving consistently in one direction, or oscillating? Consistent movement is a story; oscillation is noise.
- **Velocity/acceleration**: A line that moved 5% in the last 10 minutes is more interesting than one that moved 5% over 3 days.
- **Volatility scoring**: High-variance odds histories (lots of movement) are inherently more interesting than flat lines, even if the current state looks unremarkable.
- **Convergence/divergence**: Are bookmakers agreeing more or less over time? Divergence suggests genuine uncertainty.

**Data available today:** `odds_snapshots` has per-bookmaker, per-poll readings. `odds_aggregated` has period-based min/max/avg. `espn_snapshots` captures ESPN's model during live games. The time-series data exists — `compute_highlight` just doesn't use it yet.

**Data model work needed:** Consider pre-computing summary stats on the event row (e.g., `max_prob_swing_1h`, `snapshot_count_1h`, `odds_volatility`) to avoid querying snapshot tables on every ranking call. These could be updated by the polling tasks that already touch these events.

#### Level 3: Sport-specific and contextual scoring
Different sports have different baseline dynamics:
- A 51/49 NBA game is common; a 51/49 MLB game is rare and notable
- A 10-point swing in football means more in Q4 than Q1
- College basketball upsets are more frequent and exciting than NBA upsets

Also: game context from ESPN (quarter/period, time remaining, score margin) should influence ranking. A 52/48 game in the 4th quarter with 2 minutes left is wildly more interesting than 52/48 in the 1st quarter.

**Data available today:** `espn_snapshots` has `period`, `clock`, `home_score`, `away_score`. Events have `llm_importance` (playoff/regular_season). Sport tiers exist in highlights.py.

**Data model work needed:** Sport-specific baseline distributions (what's a "normal" amount of volatility for NFL vs NBA vs MLB). Could be a config table or derived from historical data. Game-phase weighting functions per sport.

#### Level 4: Personalized ranking
User favorites boost events featuring their teams. Recent viewing history could influence ranking (don't re-surface events they've already seen; boost sports they engage with).

**Data model planned:** `user_favorites` table is designed in the PRD schema. `pinned_items` migration is planned post-auth.

**Data model work needed:** A `user_event_interactions` table (or analytics-derived) to know what a user has already seen/engaged with. The ranking function needs a user context parameter, which means the API endpoint signatures change.

**Important constraint:** Logged-out experience must remain high quality. Personalization is additive, not required. The universal ranking must work well on its own.

#### Level 5: Learned ranking
Use engagement signals (from GA4 or a lightweight event log) as a feedback loop: did users click through to events the algorithm ranked highly? Did they spend time on event detail pages? Over time, this data can calibrate weights — or replace the hand-tuned additive model entirely.

This is the longest-term step and only makes sense once the product has meaningful traffic and the iOS app is live. Don't invest here prematurely.

#### Design principles across all levels
- **Transparency**: Users should always understand *why* something is highlighted (via labels). A black-box feed that surfaces events for opaque reasons undermines trust.
- **Stability**: Rankings shouldn't flicker. An event shouldn't jump in and out of the feed rapidly. Consider hysteresis (higher threshold to enter, lower to exit).
- **Graceful degradation**: If snapshot history is unavailable, fall back to snapshot scoring. If no user context, use universal ranking. Each level is an enhancement, not a dependency.
- **Shared infrastructure**: The iOS feed, web highlights, search ranking, and widget "best game" should all use the same underlying scoring function with different thresholds and filters — not separate implementations.

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
**Ensuring the system is observable, resilient, and sustainable.**

- [x] Event discovery task (polls ALL sports, not just those with existing events)
- [x] Stale data detection and auto-closing of stuck events
- [x] Per-sport polling intervals based on game proximity
- [ ] **Error tracking (Sentry)** — Add to FastAPI backend + Celery worker. Currently, background task failures (e.g., ESPN sync, Kalshi polling) go undetected until manually noticed. Free tier is sufficient.
- [ ] **Test coverage for core algorithms** — `pulse.py` and `highlights.py` are pure functions that have caused the most rework (6+ fix commits each). Target: 15+ test cases each covering edge cases (empty snapshots, single bookmaker, no lead changes, maximum lead changes). Only `test_odds_math.py` exists today.
- [ ] **Data retention policy** — Implement `odds_snapshots` pruning for completed events (keep aggregated data, prune raw snapshots after 7 days per PRD spec). Polling every 30s with 5-11 bookmakers generates massive row counts. Audit current Heroku Postgres usage.
- [ ] **Super Bowl one-off cleanup** — Remove dead code: `routes/superbowl.py`, `routes/contest.py`, `services/youtube_api.py`, `CommercialLeaderboard.tsx`, related Celery beat entries. These are event-specific features that won't serve future users.
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

### Phase 5: Pinned Events & Futures ✅ Complete
**Track important events without requiring authentication.**

Completed: February 2026

- [x] Pin/unpin events from cards and detail pages
- [x] Pin/unpin futures markets from cards and detail pages
- [x] Pinned sections on homepage (above Highlights)
- [x] Maximum 6 events + 6 futures pinned simultaneously
- [x] Works for events outside 7-day window (e.g., Super Bowl)
- [x] Cross-tab sync via localStorage
- [x] Search results support pinning

**Implementation:**
- localStorage-based (no auth required)
- `usePinnedEvents` and `usePinnedFutures` hooks
- `fetchEventsByIds` and `fetchFuturesByIds` for loading pinned items
- Subtle pin icon on cards (visible on hover, amber when pinned)

**Future Enhancement:** Migrate to database storage when Firebase Auth is implemented for cross-device sync.

### Phase 6: Authentication & Personalization
**User accounts for cross-device experience.**

Target: Q2 2026

- [ ] Firebase Auth integration (Google, Apple sign-in)
- [ ] Favorite teams (persisted to database)
- [ ] Migrate pinned items to database
- [ ] Personalized highlights based on favorites
- [ ] Cross-device sync of preferences
- [ ] Optional: Email notifications for favorite teams

**Auth Philosophy:**
- No required sign-in — logged-out experience must feel complete
- Auth unlocks: Favorites sync, notifications, cross-device, pinned items sync, Team Insights (Phase 15)
- Auth is **pull-based, not forced**

### Phase 7: LLM Integration & Metadata Enrichment ✅ Complete
**OpenAI-powered smart features and ESPN data integration.**

Infrastructure complete: February 2026

- [x] OpenAI GPT-4o-mini integration (`backend/app/services/llm.py`)
- [x] Generic `classify()` utility for text classification
- [x] Hybrid futures categorization (rules + LLM fallback)
- [x] LLM results cached in database (`llm_sport_category` column)
- [x] Admin endpoints for triggering categorization
- [x] **LLM Metadata Enrichment**: Gender, level, league, importance classification
- [x] **ESPN API Integration**: Team colors, logos, live game data, win probability
- [x] **Entity Resolution**: LLM-powered team name matching across data sources
- [x] **Venue Data**: Arena/stadium information from ESPN

**LLM Metadata Classifications:**
| Field | Values | Example |
|-------|--------|---------|
| `llm_gender` | men, women, mixed, unknown | WNBA → "women" |
| `llm_level` | professional, college, amateur, youth | NCAA → "college" |
| `llm_league` | NFL, NCAAF, NBA, WNBA, etc. | More granular than sport |
| `llm_importance` | championship, playoff, regular_season, exhibition | Super Bowl → "championship" |

**ESPN Integration:**
- Team enrichment: colors, logos, abbreviations, alternate names
- Event enrichment: game clock, period, broadcast info, venue
- Win probability: ESPN's statistical model (separate from betting odds)
- Entity resolution: LLM-assisted matching between our teams and ESPN teams

**Admin Endpoints:**
```bash
# LLM metadata enrichment
POST /api/admin/events/enrich-metadata?secret=xxx&limit=50
GET  /api/admin/events/metadata-status
POST /api/admin/futures/enrich-metadata?secret=xxx&limit=50
GET  /api/admin/futures/metadata-status

# ESPN integration
POST /api/admin/espn/sync-teams?secret=xxx&sport_key=basketball_nba
GET  /api/admin/espn/teams-status
POST /api/admin/espn/sync-live-events?secret=xxx&sport_key=basketball_nba
GET  /api/admin/espn/events-status
POST /api/admin/espn/match-teams?secret=xxx&our_team_name=Lakers&sport_key=basketball_nba
```

**LLM Service Capabilities:**
```python
from app.services import llm

# General classification (always returns a result when fallback is set)
result = llm.classify("Some text", ["option1", "option2", "option3"], fallback="option1")

# Futures categorization (always returns a category, never None)
category = llm.classify_futures_market("2026 Masters Tournament Winner")
# Returns: "golf" — LLM response normalization handles variants like "horse racing" → "horse_racing"

# Metadata enrichment
metadata = llm.enrich_event_metadata("Lakers", "Celtics", "basketball_nba")
# Returns: {"gender": "men", "level": "professional", "league": "NBA", "importance": "regular_season"}

# Team name matching (for entity resolution)
confidence = llm.match_team_names_cached("LA Lakers", "Los Angeles Lakers", "basketball")
# Returns: 0.95 (high confidence they're the same team)
```

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
- Hybrid approach: rules first, LLM fallback for edge cases

### Phase 8: iOS App
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

### Phase 9: Futures Markets ✅ Complete
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

### Phase 10: Prediction Markets (Kalshi Integration) ✅ Complete
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

### Phase 11: Additional Data Sources
**Expanding coverage and depth.**

Target: 2027

- [ ] Polymarket integration (if legally viable)
- [ ] PredictIt (if still operational)
- [ ] International sportsbooks for broader odds coverage
- [ ] Alternative odds sources for redundancy
- [ ] Real-time sports data (play-by-play) for richer context

### Phase 12: Probability Comparisons ("Comparable Odds")
**Make win probabilities viscerally relatable by comparing them to real-world likelihoods.**

Target: TBD (Exploratory)

A user sees their team has a 15% chance of winning. Instead of just a number, a "Comparable Odds" box on the event detail page tells them: *"About as likely as rain on a summer day in Atlanta"* or *"About as likely as your neighbor owning a dog in Germany."*

**Why this works:**
- Probabilities are abstract; real-world analogies make them intuitive
- Fits the product's mission of making odds *understandable* to non-bettors
- Creates a delightful, shareable moment ("Did you know your team's odds are the same as...")
- Reinforces the second-screen experience with conversation starters

**Requirements:**
- **Massive comparison database**: Minimum 1,000 entries to avoid repetition, ideally growing over time
- **Bucketed by probability range**: Group comparisons into bands (0-5%, 5-10%, 10-15%, ..., 95-100%) for easy lookup
- **Diverse categories**: Weather, animals, geography, pop culture, science, food, daily life, sports trivia, etc.
- **Sourced and factual**: Each comparison should be based on real statistics with a citation
- **Tone**: Fun, surprising, educational — never condescending or gambling-adjacent

**Data Model:**
```sql
CREATE TABLE probability_comparisons (
    id SERIAL PRIMARY KEY,
    probability_min DECIMAL(5,4) NOT NULL,  -- Lower bound (e.g., 0.10)
    probability_max DECIMAL(5,4) NOT NULL,  -- Upper bound (e.g., 0.15)
    comparison_text TEXT NOT NULL,           -- "Rain on a summer day in Atlanta"
    category VARCHAR(50),                   -- weather, animals, geography, science, etc.
    source TEXT,                             -- Citation/source for the statistic
    fun_factor INTEGER DEFAULT 5,           -- 1-10, for ranking/selection
    created_at TIMESTAMP DEFAULT NOW(),
    active BOOLEAN DEFAULT true
);

CREATE INDEX idx_prob_comparisons_range ON probability_comparisons(probability_min, probability_max);
CREATE INDEX idx_prob_comparisons_category ON probability_comparisons(category);
```

**Population strategy:**
- Seed with LLM-generated comparisons (GPT-4o or Claude), then manually verify sources
- Crowdsource additions over time (user submissions after auth)
- Periodic LLM batch jobs to generate new comparisons for underrepresented ranges
- Target distribution: ~50+ comparisons per 5% bucket to ensure variety

**Display (Event Detail Page):**
```
Comparable Odds
───────────────
Lakers have a 15% chance of winning.

🎲 That's about as likely as...
   "A coin landing heads 3 times in a row"

   [Show another] [📋 Share]
```

**Implementation considerations:**
- Random selection within the matching bucket (with optional category rotation)
- "Show another" button to cycle through comparisons without page reload
- Share button to generate a social card with the comparison
- API endpoint: `GET /api/comparisons?probability=0.15` returns a random match
- Cache aggressively — comparisons don't change often

**Open questions:**
- Should comparisons be localized (US-centric vs international)?
- Should users be able to submit their own comparisons?
- Should we show one comparison or a few? (One feels cleaner, aligns with product principles)
- How to handle the 45-55% range where most comparisons are boring? ("About as likely as a coin flip" gets old)

### Phase 13: Event Similarity Scores
**Find historical events that followed the most similar probability pattern — the "Baseball Reference" approach for odds.**

Target: TBD (Exploratory)

Inspired by [Baseball Reference's similarity scores](https://www.baseball-reference.com/about/similarity.shtml), this feature would show users which past games followed probability arcs most similar to the current or completed game. During a live game: *"This game is tracking most similarly to Lakers vs Celtics, March 2026 (Pulse: 87)."* After a game: *"Most similar games in our database."*

**Why this works:**
- Adds historical depth and context to every game
- Creates a "rabbit hole" effect — users explore past games they'd never have found
- Makes the growing historical database a visible, valuable asset
- Works especially well for high-drama games ("This is shaping up like THAT game")
- Bridges the second-screen experience with storytelling

**Similarity algorithm (proposed):**
```python
def calculate_similarity(event_a_history, event_b_history) -> float:
    """
    Compare two events' probability histories using multiple dimensions.

    Components (weighted):
    - Probability curve shape (40%): DTW or resampled point-by-point comparison
    - Final margin (15%): How close the final probabilities were
    - Volatility pattern (20%): Similar number/size of swings
    - Lead changes (15%): Similar number of favorite flips
    - Sport match (10%): Same sport gets a bonus

    Returns similarity score 0-100 (100 = identical pattern).
    """
```

**Key technical challenges:**
- **Time normalization**: Games have different lengths. Need to resample probability histories to a common timeline (e.g., 100 points representing 0-100% game progress)
- **Efficient comparison**: Comparing every pair is O(n²). Need smart indexing:
  - Pre-compute feature vectors (volatility, lead changes, max swing, final margin)
  - Use approximate nearest neighbor search on feature vectors
  - Only do expensive curve comparison on top candidates
- **Live matching**: During a game, compare the partial curve against completed games' equivalent partial curves

**Data requirements:**
- Minimum ~500 completed events with full probability histories to be useful
- More historical data = better matches
- Need to store normalized probability curves for fast comparison

**Data Model:**
```sql
-- Pre-computed similarity features for fast lookup
CREATE TABLE event_similarity_features (
    event_id INTEGER PRIMARY KEY REFERENCES events(id),
    sport_key VARCHAR(50),
    -- Normalized feature vector for approximate matching
    total_volatility DECIMAL(8,4),
    max_swing DECIMAL(5,4),
    lead_changes INTEGER,
    final_margin DECIMAL(5,4),
    pulse_score INTEGER,
    -- Resampled probability curve (100 points, 0-100% game progress)
    normalized_curve JSONB,  -- [0.55, 0.53, 0.58, ..., 0.72]
    computed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_similarity_sport ON event_similarity_features(sport_key);
CREATE INDEX idx_similarity_volatility ON event_similarity_features(total_volatility);
CREATE INDEX idx_similarity_pulse ON event_similarity_features(pulse_score);

-- Cached similarity results (top N similar for each event)
CREATE TABLE event_similarities (
    event_id INTEGER REFERENCES events(id),
    similar_event_id INTEGER REFERENCES events(id),
    similarity_score DECIMAL(5,2),  -- 0-100
    rank INTEGER,                   -- 1 = most similar
    computed_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (event_id, similar_event_id)
);
```

**Display (Event Detail Page):**
```
Similar Games
─────────────
This game's probability pattern most closely resembles:

1. 🏀 Lakers vs Celtics — Mar 12, 2026 (92% similar)
   Pulse: 87 | Final: 112-108 | 3 lead changes
   [View game →]

2. 🏀 Warriors vs Nuggets — Feb 28, 2026 (85% similar)
   Pulse: 74 | Final: 105-101 | 2 lead changes
   [View game →]

3. 🏈 Chiefs vs Bills — Jan 19, 2026 (78% similar)
   Pulse: 91 | Final: 28-24 | 4 lead changes
   [View game →]
```

**Live game display:**
```
Tracking Similar To...
──────────────────────
Through 3 quarters, this game is tracking most like:
🏀 Heat vs Bucks — Jan 15, 2026 (Pulse: 82)
That game ended with a 4-point margin after a late comeback.
```

**Phases:**
1. **v1**: Post-game similarity only (batch computed after game ends)
2. **v2**: Live similarity matching (compare partial curves during games)
3. **v3**: Cross-sport similarity ("This NFL game feels like THAT NBA game")
4. **v4**: User-facing "Find games like this" search feature

**Open questions:**
- Should similarity be computed only within the same sport, or cross-sport?
- How far back should the historical window go? (All-time vs last 2 seasons)
- Should we weight recent games higher in similarity results?
- What's the minimum number of odds snapshots needed for meaningful comparison?
- How to present similarity during live games without spoiling the referenced game's outcome?

### Phase 14: Advanced LLM Features
**Intelligent explanations, search, and context generation.**

Target: 2027

#### 11.1: Odds Movement Explanations
Generate brief, factual explanations for significant probability swings.

**Implementation:**
```python
def explain_odds_movement(event: Event, recent_snapshots: list) -> str:
    """
    Generate explanation for why odds moved.

    Example output:
    "Warriors win probability jumped from 55% to 72% in the last 10 minutes.
    This 17-point swing typically indicates a significant scoring run or
    key momentum shift."
    """
```

**Features:**
- Detect significant swings (>10% change in probability)
- Generate human-readable explanations
- Cache explanations to avoid redundant API calls
- Show on event detail page and in highlights
- Optional: correlate with score changes when available

**UI Integration:**
- Tooltip on probability swing indicators
- "What happened?" section on event detail page
- Highlight explanations in the Pulse card

#### 11.2: Smart Search Query Understanding
Parse natural language queries into structured filters using LLM.

**Examples:**
| User Query | Parsed As |
|------------|-----------|
| "celtics games last month" | team=celtics, days_back=30 |
| "close nba games today" | sport=nba, closeness>0.9, date=today |
| "biggest upsets this week" | upset=true, days_back=7, sort=upset_margin |
| "warriors vs lakers upcoming" | team1=warriors, team2=lakers, status=scheduled |

**Implementation:**
- Use Claude API (GPT-4o-mini) to parse ambiguous queries
- Show "interpreted as" explanation for transparency
- Cache common query interpretations
- Fallback to basic search if LLM parsing fails
- Rate limit LLM calls (maybe only for logged-in users)

#### 11.3: Excitement Summaries
Generate narrative summaries for high-Pulse games.

**Example Output:**
> "This game saw 4 lead changes in the final 10 minutes, with win probabilities
> swinging between 35% and 65%. The home team mounted a late comeback from a
> 12-point deficit, making this one of the most exciting regular season games
> of the week."

**Features:**
- Feed LLM the odds snapshots and score snapshots
- Generate human-readable narrative
- Include with disclaimer ("AI-generated summary")
- Show on completed game detail pages
- Feature in "Exciting Games This Week" section

#### 11.4: Multi-Source Probability Integration
Aggregate win probabilities from multiple statistical models. **Phase 1 shipped Feb 2026.**

**Shipped (Feb 2026):**
- Generic `win_prob_snapshots` table with source column (replaces ESPN-specific storage)
- Source registry in `backend/app/config/win_prob_sources.py` (Python dict, not DB)
- OddsTracker statistical win probability model (nflfastR-inspired normal distribution)
  - Supports: NFL, NCAAF, NBA, NCAAB, WNCAAB, NHL
  - Uses score diff + time remaining + pregame spread
- OddsChart renders N sources dynamically with labeled, color-coded lines
- `/events/[id]/models` detail page showing methodology + attribution for each source
- Dual compute paths: ESPN sync (60s) + odds polling (30-60s)
- ESPN team name matching with unicode normalization (handles college team names)

**Current sources (3):**
| Source | Type | Status | Sports |
|--------|------|--------|--------|
| Betting Odds | Market (The Odds API) | ✅ Live | All |
| ESPN | Model (undocumented API) | ✅ Live | NBA, NCAAB, NFL, NCAAF, NHL, MLB |
| OddsTracker Model | Model (nflfastR methodology) | ✅ Live | NFL, NCAAF, NBA, NCAAB, WNCAAB, NHL |

**Future sources to evaluate:**
| Source | Type | Viability | Notes |
|--------|------|-----------|-------|
| MoneyPuck | API | High (NHL) | Free JSON API with live game WP |
| FanGraphs | API | High (MLB) | Free JSON endpoints for live WP |
| Inpredictable | Web | Medium | College sports models, may need scraping |
| kenpom.com | Web | Medium | College basketball, paid subscription |
| FiveThirtyEight | Archive | Low | Shut down, historical Elo data only |
| Pro Football Reference | Web | ❌ Not viable | No API, ToS blocks scraping, not real-time |

**Architecture for adding a new source:**
1. Add entry to `WIN_PROB_SOURCES` dict in `win_prob_sources.py`
2. Write snapshots to `win_prob_snapshots` table with the source key
3. Chart and API pick it up automatically — no frontend changes needed

**Known limitations:**
- Stat model requires `game_clock` + `period` from ESPN sync. If ESPN name matching fails for an event, time remaining is unknown and the model can't compute.
- ESPN's win probability is only available during live games — cannot be backfilled.
- No pre-game win probability from models (only betting odds available pre-game).

See `docs/win-probability-sources-plan.md` for the full staged rollout plan.

#### 11.5: Historical Events Database
Build comprehensive database of past games with their probability histories.

**Scope:**
- All events tracked since OddsTracker launch (January 2026)
- Historical data from other sources where available
- Indexed for fast search and analysis

**Data Model:**
```sql
-- Enhanced historical storage
CREATE TABLE historical_events (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(100),
    sport_key VARCHAR(50),
    season VARCHAR(20),

    home_team VARCHAR(200),
    away_team VARCHAR(200),
    home_score INTEGER,
    away_score INTEGER,

    -- Probability history (compressed)
    probability_history JSONB,  -- [{time, home_prob, away_prob}, ...]

    -- Computed metrics
    pulse_score INTEGER,
    was_upset BOOLEAN,
    largest_swing DECIMAL(5,4),
    lead_changes INTEGER,

    -- Search indexes
    teams_search TSVECTOR,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_historical_events_sport_season ON historical_events(sport_key, season);
CREATE INDEX idx_historical_events_pulse ON historical_events(pulse_score DESC);
CREATE INDEX idx_historical_events_search ON historical_events USING gin(teams_search);
```

**Use Cases:**
- "Most exciting Lakers games ever"
- "Biggest upsets in NBA history"
- "Games similar to this one" (by probability pattern)
- Historical Pulse leaderboards by sport/season
- Training data for future ML models

**Data Sources:**
- Our own tracked events (primary, authoritative)
- ESPN historical games (supplementary)
- Sports Reference (research/validation)

### Phase 15: Team Insights (LLM-Powered Personalized Feed)
**Personalized insights about your favorite teams, synthesized by LLM from structured DB queries.**

Target: TBD (Exploratory — requires Firebase Auth for favorites persistence)

#### Concept
During onboarding (or anytime), users select their favorite teams. The system runs structured queries to gather recent data about those teams, then uses GPT-4o-mini to synthesize the ~10 most interesting insights. This creates a personalized "What you missed" or "What's coming up" experience.

**Example Insights:**
| Headline | Body | Type |
|----------|------|------|
| Lakers are live right now | LAL trailing Celtics 58-62 in Q3, 41% win probability | live |
| Patriots upset the Bills | Won 24-21 as +280 underdogs yesterday — Pulse score of 89 | result |
| Yankees' title odds surging | Championship probability jumped from 8% to 14% this week | futures |
| Lakers-Warriors Friday night | Opening line: LAL -3.5 (62% implied). First meeting since playoff elimination | upcoming |

#### Architecture

**Key Design Decision:** Don't let the LLM query the DB. Instead, pre-query structured data per team, then let the LLM synthesize and narrate. This is cheaper, faster, more reliable, and auditable.

```
Onboarding → Store favorites → Query DB per team → Build data packet → LLM narrates → 10 insights
```

#### Data Gathering (per team)

Five structured queries run for each favorite team:

```python
async def gather_team_data(team_id: int, db: AsyncSession) -> dict:
    """Gather all insight-worthy data for a team."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    # 1. Recent results (completed games, last 7 days)
    recent_results = await db.execute(
        select(Event)
        .where(or_(Event.home_team_id == team_id, Event.away_team_id == team_id))
        .where(Event.status.in_(["completed", "closed"]))
        .where(Event.commence_time >= week_ago)
        .order_by(Event.commence_time.desc())
        .limit(10)
    )

    # 2. Upcoming games (next 7 days)
    upcoming = await db.execute(
        select(Event)
        .where(or_(Event.home_team_id == team_id, Event.away_team_id == team_id))
        .where(Event.status == "scheduled")
        .where(Event.commence_time <= now + timedelta(days=7))
        .order_by(Event.commence_time.asc())
        .limit(5)
    )

    # 3. Live games right now
    live = await db.execute(
        select(Event)
        .where(or_(Event.home_team_id == team_id, Event.away_team_id == team_id))
        .where(Event.status == "live")
    )

    # 4. Championship/futures odds
    futures = await db.execute(
        select(FuturesMarket.name, FuturesOutcome.current_probability,
               FuturesOutcome.probability_change_24h)
        .join(FuturesOutcome, FuturesMarket.id == FuturesOutcome.market_id)
        .where(FuturesOutcome.team_id == team_id)
        .where(FuturesMarket.status == "open")
        .order_by(FuturesOutcome.current_probability.desc())
    )

    # 5. Most exciting recent games (by Pulse)
    pulse_games = await db.execute(
        select(Event)
        .where(or_(Event.home_team_id == team_id, Event.away_team_id == team_id))
        .where(Event.raw_gei.isnot(None))
        .where(Event.commence_time >= now - timedelta(days=14))
        .order_by(Event.raw_gei.desc())
        .limit(5)
    )

    return {
        "team": team_name,
        "recent_results": serialize_events(recent_results),
        "upcoming": serialize_events(upcoming),
        "live": serialize_events(live),
        "futures": serialize_futures(futures),
        "top_pulse_games": serialize_events(pulse_games),
    }
```

#### LLM Prompt

The data packet is fed to GPT-4o-mini with instructions to pick the most interesting items:

```python
prompt = """You are a sports analyst for a casual fan's second-screen experience.
Given the following data about a user's favorite teams, pick the 10 most
interesting, surprising, or actionable insights. Prioritize:

1. Live games happening RIGHT NOW (always #1 if any exist)
2. Upsets or close finishes in recent games (high Pulse scores)
3. Big line movements or shifting championship odds
4. Upcoming marquee matchups (rivalry, playoff implications)
5. Streaks, trends, or notable records

For each insight, return JSON:
{
  "insights": [
    {
      "headline": "Short punchy headline (≤10 words)",
      "body": "1-2 sentence explanation for a casual fan",
      "team": "Primary team this relates to",
      "type": "live|result|upcoming|futures|trend",
      "event_id": <id if applicable, null otherwise>,
      "urgency": "high|medium|low"
    }
  ]
}
"""
```

#### Use Cases

**1. Onboarding welcome screen:**
After selecting favorites, show "Here's what's happening with your teams" — creates immediate value and hooks the user.

**2. Event detail page enrichment:**
On a Lakers game page, show "More about the Lakers" section with relevant insights (recent record, futures odds, upcoming schedule).

**3. Notification triggers:**
The `urgency: "high"` field could drive push notifications. "Lakers are live and it's close" is worth an interrupt; "Lakers play Friday" is not.

**4. Daily digest email:**
For authenticated users, a morning email with personalized insights about their teams.

#### API Design

```
# Onboarding: pick teams
POST /api/me/favorites
Body: { "team_ids": [1, 5, 12] }

# Generate insights (authenticated)
GET /api/insights
Response: {
  "generated_at": "2026-02-06T12:00:00Z",
  "insights": [...],
  "teams": ["Lakers", "Patriots", "Yankees"]
}

# Team picker data
GET /api/teams?sport=basketball_nba
GET /api/teams/search?q=lakers
```

#### Cost & Performance

| Component | Cost/Latency |
|-----------|--------------|
| DB queries | ~5 queries × N teams, all indexed — <500ms total |
| LLM call | One GPT-4o-mini call, ~2-4K tokens — ~$0.001 |
| Caching | Redis TTL of 5-10 min per user — most requests hit cache |
| Total | 2-4 seconds first load, instant from cache |

#### Prerequisites

- **Firebase Auth**: Need user accounts to persist favorites
- **Team table populated**: Already done via ESPN sync
- **UserFavorite table**: Already exists in schema, ready to use
- **LLM service**: Already integrated (GPT-4o-mini in `services/llm.py`)

#### Implementation Phases

1. **v1**: Team picker UI + insights endpoint (web only)
2. **v2**: Event detail page integration ("More about this team")
3. **v3**: Notification triggers based on urgency field
4. **v4**: iOS integration with native insights feed
5. **v5**: Daily digest emails

#### Open Questions

- Should insights be cached per-team (sharable across users) or per-user (more personalized)?
- How many teams should users be able to follow? (Suggest 3-10)
- Should we show insights for teams the user doesn't follow if they're playing against favorites?
- How to handle the cold start problem for new users who haven't picked teams yet?

---

## Recent Improvements (February 2026)

### Pulse - Game Excitement Metric ✅ NEW
- **Proprietary algorithm**: Measures game excitement based on probability movement patterns using a "vital signs" metaphor
- **Real-time updates**: Pulse calculated every poll cycle for live games
- **Component breakdown**: Momentum Swings, Drama Level, Competitiveness, Lead Changes
- **Visual badges**: Color-coded badges (🫀💓💗🩺📉) displayed on all games
- **Tooltip explanations**: Human-friendly descriptions of what makes each game exciting, including component-level tooltips on event detail pages
- **Explainer page**: Full methodology at `/pulse`
- **Admin tools**: Status check, batch recalculation, and distribution analysis endpoints
- **Percentile scoring**: Raw scores mapped to percentiles using completed games as reference set, giving users a relative ranking
- **Distribution-tuned normalization**: Heart Rate (÷0.6), Amplitude (÷0.15), Arrhythmia (÷0.10) ceilings tuned from observed game data
- **Vitals uses game average**: Closeness to 50% averaged across all snapshots, not just final state
- **Hall of Fame quality filter**: Rankings require 10+ odds snapshots to prevent low-data false positives

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
- **Hybrid futures categorization**: 90+ regex patterns + LLM fallback for edge cases
- **22 sport categories**: football, basketball, baseball, hockey, golf, tennis, soccer, mma, motorsports, boxing, cricket, rugby, aussierules, horse_racing, olympics, esports, entertainment, politics, lacrosse, chess, poker, other
- **Zero uncategorized markets**: `classify()` always returns a category (never NULL), with LLM response normalization handling variant outputs like "horse racing" → horse_racing
- **Database caching**: LLM results stored in `llm_sport_category` column to avoid repeat API calls
- **Admin endpoints**: `/api/admin/futures/categorize`, `/uncategorized`, `/force-categorize`
- **Cost-effective**: ~$0.001 per classification, results cached permanently

### Futures & Kalshi Integration ✅ NEW
- **Futures markets**: Championship odds, MVP races, division winners from The Odds API
- **Kalshi prediction markets**: Sports-related prediction markets with timing info
- **Smart categorization**: All markets auto-categorized using hybrid rules (90+ patterns) + LLM fallback
- **Unified display**: Both sources appear together, grouped by sport category
- **Search integration**: Futures markets included in search results

### Pinned Events & Futures ✅ NEW
- **Track important events**: Pin events like the Super Bowl to track them closely
- **Pin futures markets**: Also pin championship races, MVP odds, etc.
- **Homepage sections**: "📌 Pinned" and "📌 Pinned Futures" appear above Highlights
- **Works anywhere**: Pin from cards, search results, or detail pages
- **No auth required**: localStorage-based, syncs across browser tabs
- **Smart fetching**: Pinned events outside the 7-day window are fetched separately
- **Limits**: Max 6 events + 6 futures to prevent UI clutter

### Bug Fixes
- **Upset Brewing fix**: Pre-game line movement no longer triggers "Upset brewing" label for scheduled events
- **Favorite switched logic**: Only set for live/completed games, not scheduled

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

| Data Type | Retention | Status |
|-----------|-----------|--------|
| Raw snapshots | 7 days after event completion | **NOT YET IMPLEMENTED** — snapshots accumulate indefinitely. Need a Celery task to prune `odds_snapshots` for completed events older than 7 days. |
| Aggregated data | Indefinite | OK |
| Event metadata | Indefinite | OK |
| Futures history | Indefinite | OK |
| Prediction market history | Indefinite | OK |

**Action needed:** Implement a scheduled Celery task to prune raw snapshots. At current polling rates (30s intervals, 5-11 bookmakers per event), a single NFL Sunday can generate 50,000+ snapshot rows. Without pruning, Heroku Postgres will hit row/storage limits.

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

### Completed (February 2026)
- ✅ Pulse (Game Excitement Metric) - live and completed
- ✅ Pulse Hall of Fame page
- ✅ Futures markets with smart categorization
- ✅ Kalshi prediction market integration
- ✅ LLM infrastructure (OpenAI GPT-4o-mini)
- ✅ Pinned events and futures (localStorage-based)
- ✅ Futures categorization hardened: 90+ regex patterns, 22 sport categories, LLM fallback always returns a result, 0 uncategorized markets

### Immediate — Infrastructure First (February-March 2026)
**Focus: Make the system observable and sustainable before building new features.**
- Add Sentry error tracking to FastAPI + Celery worker (prevents silent failures)
- Write test suites for `pulse.py` and `highlights.py` (reduces fix-commit cycle)
- Implement data retention policy for `odds_snapshots` (prevents DB growth issues)
- Clean up Super Bowl one-off code (dead routes, services, components, Celery tasks)
- Pass Kalshi event category through as sport_key for better disambiguation
- Deploy analytics and observe user behavior

### Near-term (March-April 2026)
- Ranking Level 2: time-series aware scoring (pre-compute summary stats from odds_snapshots, pass to `compute_highlight`). Highest-leverage feature for the north star.
- Firebase Auth integration
- Migrate pinned items to database for cross-device sync (avoid adding new localStorage features until this is done)
- Favorite teams with cloud sync

### Mid-term (May-June 2026)
- LLM-powered explanations for odds movements
- Ranking Level 3: sport-specific context and game-phase weighting
- Personalized highlights based on favorites (Ranking Level 4)
- Begin iOS app development (feed tab uses ranking infrastructure)

### Later (Q3-Q4 2026)
- iOS app launch with feed tab, search, and widgets — all powered by shared ranking function
- Widgets (Lock Screen, Home Screen) — "Most Exciting Game Right Now"
- Advanced notification preferences (ranking determines what's worth an interrupt)

### Exploring (No Timeline)
- **Probability Comparisons ("Comparable Odds")**: Massive database of real-world probability analogies (1,000+ entries) displayed on event detail pages to make win probabilities viscerally relatable — "Your team's 15% chance is about as likely as rain on a summer day in Atlanta" (Phase 12)
- **Event Similarity Scores**: Baseball Reference-style similarity matching that finds historical games with the most similar probability arcs — works during and after games, creates a "rabbit hole" into the historical database (Phase 13)
- **Team Insights (LLM-Powered Personalized Feed)**: Onboarding flow where users select favorite teams, then LLM synthesizes ~10 interesting insights from DB queries — recent results, upcoming games, championship odds shifts, high-Pulse games. Could power event detail page context and notification triggers (Phase 15)

---

## Final Note

This product wins not by being smarter than users, but by being **clearer than everything else**.

If OddsTracker succeeds, users won't say:
> "This helped me bet."

They'll say:
> "I finally understood what was happening."
