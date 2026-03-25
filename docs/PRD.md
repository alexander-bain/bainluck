# Bain Luck - Product Requirements Document

## Executive Summary

Bain Luck is a visual-first sports odds experience that translates betting markets into intuitive, real-time representations of how a game is expected to unfold—before and during play.

The product is designed primarily as a **second screen for casual sports fans**: people watching a game who want immediate, understandable context for what just happened and why it mattered, without having to interpret betting lines or think like gamblers.

Bain Luck is not a sportsbook, not a pick-selling tool, and not a stats-heavy analytics platform. It is the cleanest, fastest way to visualize expectation shifts in live sports.

**Expanding vision:** Bain Luck aggregates probabilities from sportsbooks (The Odds API), prediction markets (Kalshi, Polymarket), proprietary models (ESPN, Bain Luck stat model), and more — aspiring to be the **easiest place to see the probability of anything happening, computed any way possible**. Non-sports prediction markets (politics, entertainment, crypto) extend this into a broader "probability of everything" experience.

---

## Vision & North Star

### Vision
Make betting odds understandable to non-bettors by turning them into clean, live, visual signals about game expectations.

### North Star Statement
**Bain Luck is the cleanest odds visualization tool on the internet.**

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

Bain Luck will **not** become:
- A sportsbook or betting interface
- A pick-selling or tout product
- A social network
- A news or commentary site
- A heavy statistical modeling platform

These exclusions are intentional and protect product clarity.

---

## Core User Experience

### The Second-Screen Experience

Bain Luck is designed to be open during live play, but only active when meaningful.

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
When a large shift occurs, Bain Luck may surface:
- "That TD increased win probability by +14%"
- "This injury moved the line significantly"

No narration. No hype. Just facts.

### Probability Display by Game Status

Different game statuses show different probability data to users:

| Status | Primary Display | Secondary Display |
|--------|----------------|-------------------|
| Scheduled | Current betting consensus (`current_odds`) | — |
| Live | Current live odds (large) | "Opened X/Y" reference from `opening_odds` (small) |
| Completed/Closed | Opening odds probability bar (what was expected) | Score with winner bolded (what happened) + date/time for freshness |

**Opening odds** are the last pregame consensus — updated with the cross-bookmaker average on every poll while the event is scheduled, then frozen when the game starts.

**Completed event cards** show a visual "Expected vs. Actual" pattern: the probability bar renders opening odds (what the market expected), while the score area shows the result with the winning team bolded. A date/time stamp in the corner communicates freshness. The reason text area only adds context when genuinely insightful (e.g., "Won as 35% underdog" for upsets), avoiding repetition of information already visible on the card.

**Live event cards** show current odds in the probability bar with an "Opened X/Y" reference line. Reason text like "Virtually even" or "Underdog leading" appears only when it adds context beyond what the card UI communicates.

**Upcoming event cards** show current betting consensus. Reason text avoids repeating the odds (already visible); only adds timing ("Starting soon") or noteworthy context ("Starting soon — close matchup").

**Stale bookmaker filtering**: For non-scheduled events, bookmakers whose last distinct odds value was captured before `commence_time` are excluded from aggregation. This prevents stale pre-game lines from distorting live probabilities.

**Frontend cross-check** (event detail page only): Compares `current_odds` against the history endpoint's latest time-bucketed consensus. If they diverge >5% for live games, trusts history.

---

## Architecture

### System Design

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   The Odds API  │────▶│                 │────▶│   PostgreSQL    │
│   (External)    │     │  Celery + Redis │     │ (Heroku Postgres)│
└─────────────────┘     │  (Task Queue)   │     └────────┬────────┘
                        │                 │              │
┌─────────────────┐     │                 │              │
│     Kalshi      │────▶│                 │              │
│  (Pred Markets) │     │                 │              │
└─────────────────┘     │                 │              │
                        │                 │              │
┌─────────────────┐     │                 │              │
│   Polymarket    │────▶│                 │              │
│  (Pred Markets) │     │                 │              │
└─────────────────┘     │                 │              │
                        │                 │              │
┌─────────────────┐     │                 │              │
│      ESPN       │────▶│                 │              │
│ (Undocumented)  │     │                 │              │
└─────────────────┘     │                 │              │
                        │                 │              │
┌─────────────────┐     │                 │              │
│  MLB Stats API  │────▶│                 │              │
│  (Live Win Prob)│     └─────────────────┘              │
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
                                ▲                  ▲
                                └──────────────────┘
                                      Planned
```

### Tech Stack

| Component | Technology | Hosting | Rationale |
|-----------|------------|---------|-----------|
| Backend API | FastAPI (Python 3.11+) | Heroku | Modern, fast, great typing support |
| Database | PostgreSQL | Heroku Postgres | Managed, auto-backups |
| Task Queue | Celery + Redis | Heroku Redis | Scheduled odds polling, background tasks |
| Web Frontend | Next.js 14 (React) | Vercel | SSR for shareable links, great DX |
| iOS App | SwiftUI | Active (TestFlight) | Modern Apple development |
| Auth | Firebase Auth | Google Cloud | Google + Apple sign-in (shipped) |
| Analytics | Google Analytics 4 | Google | Cross-platform tracking, User-ID support |
| LLM Integration | OpenAI GPT-4o-mini | OpenAI | Classification, categorization (~$5/mo) |

### External Services

| Service | Purpose | Cost |
|---------|---------|------|
| **The Odds API** | Sports odds data (moneylines, spreads, totals, futures) | ~$119/mo |
| **Kalshi** | Prediction market data (futures with timing info) | Free |
| **Polymarket** | Prediction market data (sports + politics/entertainment/crypto) | Free (no API key) |
| **ESPN** | Team colors, logos, live game data, win probability, rosters | Free (undocumented) |
| **MLB Stats API** | Live baseball win probability, schedules | Free (no API key) |
| **TMDB** | Movie posters, headshots, trailers for Oscars page | Free tier |
| **OpenAI** | GPT-4o-mini for LLM classification | ~$5/mo |
| **Firebase Auth** | Google Sign-In, user accounts | Free tier |
| **Sentry** | Error tracking + performance monitoring | Free tier |
| **Google Analytics 4** | User analytics | Free |

---

## Data Model

### Core Tables

```sql
-- Sports we track
CREATE TABLE sports (
    id SERIAL PRIMARY KEY,
    key VARCHAR(50) UNIQUE NOT NULL,   -- e.g., 'basketball_nba'
    name VARCHAR(100) NOT NULL,         -- e.g., 'NBA'
    "group" VARCHAR(50),               -- e.g., 'Basketball'
    active BOOLEAN DEFAULT true
);

-- Teams/Players (enriched by ESPN + MLB Stats API)
CREATE TABLE teams (
    id SERIAL PRIMARY KEY,
    sport_id INTEGER REFERENCES sports(id),
    external_id VARCHAR(100),           -- ID from odds API
    name VARCHAR(200) NOT NULL,
    abbreviation VARCHAR(10),
    logo_url TEXT,

    -- ESPN enrichment
    espn_id VARCHAR(50),
    primary_color VARCHAR(7),           -- Hex color e.g. '#552583'
    secondary_color VARCHAR(7),
    logo_url_small VARCHAR(512),
    logo_url_large VARCHAR(512),
    alternate_names JSONB,              -- ["Lakers", "LA Lakers"]
    current_record VARCHAR(20),         -- "34-18"
    location VARCHAR(100),              -- ESPN location (city/region/school)

    -- ESPN + MLB Stats API enrichment
    roster_players JSONB,               -- ["Jayson Tatum", "Jaylen Brown", ...]

    -- StatPal enrichment
    statpal_team_id VARCHAR(100)        -- StatPal's team identifier (indexed)
);

-- Individual games/matches
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    sport_id INTEGER REFERENCES sports(id),
    external_id VARCHAR(100) UNIQUE,    -- NULL for StatPal-created events until Odds API attaches
    home_team_id INTEGER REFERENCES teams(id),
    away_team_id INTEGER REFERENCES teams(id),

    -- For quick lookups before team records exist
    home_team_name VARCHAR(200),
    away_team_name VARCHAR(200),

    commence_time TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'scheduled',  -- scheduled, live, completed, closed

    home_score INTEGER,
    away_score INTEGER,

    -- Opening odds (last pre-game consensus, frozen at game start)
    opening_home_probability DECIMAL(5,4),
    opening_away_probability DECIMAL(5,4),
    opening_home_spread DECIMAL(4,1),
    opening_over_under DECIMAL(5,1),
    opening_favorite VARCHAR(10),        -- 'home', 'away', 'even'

    -- Pulse (Game Excitement Index)
    raw_gei DECIMAL(6,4),               -- Score/100 (e.g., 0.75 = score 75)
    gei_components TEXT,                 -- JSON of component breakdown
    gei_computed_at TIMESTAMP WITH TIME ZONE,

    -- LLM metadata enrichment
    llm_gender VARCHAR(20),             -- men/women/mixed/unknown
    llm_level VARCHAR(20),              -- professional/college/amateur/youth
    llm_league VARCHAR(50),             -- NFL/NCAAF/NBA/etc.
    llm_importance VARCHAR(30),         -- playoff/championship/regular_season

    -- Normalized team names for better matching
    home_team_normalized VARCHAR(200),
    away_team_normalized VARCHAR(200),
    home_team_alt_names JSONB,          -- ["Lakers", "LA Lakers", etc.]
    away_team_alt_names JSONB,

    -- ESPN enrichment
    espn_id VARCHAR(50),
    venue_id INTEGER REFERENCES venues(id),
    broadcast_info VARCHAR(255),         -- "ESPN, ESPN+"
    game_clock VARCHAR(20),             -- "4:32"
    period VARCHAR(100),                -- "Q4", "2nd Half", "OT"
    espn_win_prob_home DECIMAL(5,4),    -- ESPN's model
    win_probability_sources JSONB,       -- {"espn": 0.65, "betting": 0.60}

    -- StatPal enrichment (schedule-first architecture)
    statpal_fixture_id VARCHAR(100),    -- StatPal fixture ID (indexed, primary lookup key)
    statpal_end_time TIMESTAMP WITH TIME ZONE,  -- Expected game end time
    commence_time_source VARCHAR(20),   -- 'odds_api', 'espn', 'statpal' (StatPal wins)

    created_at TIMESTAMP DEFAULT NOW()
);

-- Raw odds snapshots (with lossless deduplication)
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

    -- Calculated fields (denormalized for query speed)
    home_win_probability DECIMAL(5,4),
    away_win_probability DECIMAL(5,4),
    projected_home_score DECIMAL(5,1),
    projected_away_score DECIMAL(5,1),

    -- Deduplication fields (lossless collapsing)
    reading_count INTEGER DEFAULT 1,    -- How many polls saw this exact value
    valid_until TIMESTAMP WITH TIME ZONE -- Last time this value was confirmed
);

-- Aggregated odds (permanent storage, time-bucketed)
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

    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(event_id, period_start)
);

-- Win probability history from multiple sources
CREATE TABLE win_prob_snapshots (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id),
    source VARCHAR(30) NOT NULL,        -- 'espn', 'stat_model', 'moneypuck', etc.
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    home_win_probability DECIMAL(5,4),
    away_win_probability DECIMAL(5,4),
    draw_probability DECIMAL(5,4),

    game_state JSONB,                   -- Source-specific state (clock, period, score)

    -- Deduplication
    reading_count INTEGER DEFAULT 1,
    valid_until TIMESTAMP WITH TIME ZONE
);

-- ESPN-specific snapshots (legacy, still populated)
CREATE TABLE espn_snapshots (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    home_win_probability DECIMAL(5,4),
    away_win_probability DECIMAL(5,4),

    home_score INTEGER,
    away_score INTEGER,
    game_clock VARCHAR(20),
    period VARCHAR(100)
);

-- Score history snapshots
CREATE TABLE score_snapshots (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(id),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    home_score INTEGER,
    away_score INTEGER
);

-- Venue/arena information from ESPN
CREATE TABLE venues (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(100),
    state VARCHAR(50),
    country VARCHAR(50),
    capacity INTEGER,
    espn_id VARCHAR(50)
);

-- Pulse percentile thresholds
CREATE TABLE gei_percentiles (
    id SERIAL PRIMARY KEY,
    scope VARCHAR(50) NOT NULL,         -- 'global', 'basketball_nba', etc.
    percentile INTEGER NOT NULL,        -- 1-100
    raw_gei_threshold DECIMAL(6,4),     -- Raw GEI value at this percentile
    sample_size INTEGER,                -- Number of events in this scope
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(scope, percentile)
);
```

### Futures Tables

```sql
-- A futures market (e.g., 'NBA Championship 2025-26')
CREATE TABLE futures_markets (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,        -- 'odds_api', 'kalshi', 'polymarket'
    external_id VARCHAR(200) NOT NULL,  -- sport_key or event_ticker
    sport_id INTEGER REFERENCES sports(id),

    name VARCHAR(300) NOT NULL,
    description TEXT,
    category VARCHAR(50) DEFAULT 'championship',  -- championship, mvp, division, prop
    llm_sport_category VARCHAR(50),     -- LLM-assigned sport category
    market_tier INTEGER,                -- 1=championship, 2=conference, 3=awards, 4=division, 5=props

    -- LLM metadata
    llm_gender VARCHAR(20),
    llm_level VARCHAR(20),
    llm_league VARCHAR(50),

    mutually_exclusive BOOLEAN DEFAULT true,
    commence_time TIMESTAMP WITH TIME ZONE,      -- When event/tournament begins
    resolution_date TIMESTAMP WITH TIME ZONE,    -- When market resolves
    status VARCHAR(20) DEFAULT 'open',           -- open, suspended, resolved

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(source, external_id)
);

-- A single outcome in a futures market (e.g., 'Los Angeles Lakers')
CREATE TABLE futures_outcomes (
    id SERIAL PRIMARY KEY,
    market_id INTEGER REFERENCES futures_markets(id),
    external_id VARCHAR(200),
    name VARCHAR(300) NOT NULL,
    team_id INTEGER REFERENCES teams(id),   -- For team-linking in related-futures

    -- Current consensus (denormalized)
    current_probability DECIMAL(7,6),
    current_american_odds INTEGER,
    current_yes_bid DECIMAL(5,4),            -- Kalshi bid/ask
    current_yes_ask DECIMAL(5,4),

    -- Opening odds
    opening_probability DECIMAL(7,6),
    opening_american_odds INTEGER,
    opening_captured_at TIMESTAMP WITH TIME ZONE,

    -- Movement tracking
    probability_change_24h DECIMAL(7,6),
    rank INTEGER,
    rank_change_24h INTEGER,

    is_winner BOOLEAN DEFAULT false,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(market_id, external_id)
);

-- Historical odds snapshot for a futures outcome
CREATE TABLE futures_odds_snapshots (
    id SERIAL PRIMARY KEY,
    outcome_id INTEGER REFERENCES futures_outcomes(id),
    bookmaker VARCHAR(50),

    probability DECIMAL(7,6),
    american_odds INTEGER,
    yes_bid DECIMAL(5,4),                    -- Kalshi
    yes_ask DECIMAL(5,4),                    -- Kalshi
    last_price DECIMAL(5,4),                 -- Kalshi

    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Deduplication
    reading_count INTEGER DEFAULT 1,
    valid_until TIMESTAMP WITH TIME ZONE
);
```

### User Tables

```sql
-- Users (optional auth for personalization)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    firebase_uid VARCHAR(128) UNIQUE,
    email VARCHAR(255),
    display_name VARCHAR(100),
    photo_url VARCHAR(512),
    created_at TIMESTAMP DEFAULT NOW()
);

-- User team relationships
CREATE TABLE user_favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    team_id INTEGER REFERENCES teams(id),
    relation_type VARCHAR(20) DEFAULT 'follow',  -- follow, local, alma_mater, rival
    source VARCHAR(20) DEFAULT 'manual',         -- manual, onboarding, inferred
    weight DECIMAL(3,2) DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, team_id)
);

-- User preferences from onboarding and settings
CREATE TABLE user_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) UNIQUE,
    home_location VARCHAR(100),
    sport_affinities JSONB DEFAULT '{}',
    onboarding_completed BOOLEAN DEFAULT false,
    onboarding_raw JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Server-side pin storage (replaces localStorage for authenticated users)
CREATE TABLE user_pins (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    pin_type VARCHAR(20) NOT NULL,       -- 'event' or 'future'
    target_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, pin_type, target_id)
);
```

### Identity Tables

```sql
-- Cross-source team identity index (canonical identity resolution)
CREATE TABLE team_identity_mapping (
    id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id) ON DELETE CASCADE,
    source VARCHAR(30) NOT NULL,        -- 'odds_api', 'espn', 'statpal', 'kalshi', 'polymarket', 'futures', 'mlb'
    source_id VARCHAR(200),             -- External ID from that source
    source_name VARCHAR(300),           -- Team name as used by that source
    source_abbreviation VARCHAR(20),    -- Abbreviation (e.g., 'BOS', 'LAL')
    sport_key VARCHAR(50),              -- Scoped by sport (e.g., 'basketball_nba')
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraints for upserts
    UNIQUE(source, source_id, sport_key) WHERE source_id IS NOT NULL,
    UNIQUE(source, source_name, sport_key) WHERE source_name IS NOT NULL
);
```

### Key Indexes

```sql
-- Odds snapshots
CREATE INDEX idx_odds_snapshots_event ON odds_snapshots(event_id);
CREATE INDEX idx_odds_snapshots_captured ON odds_snapshots(captured_at);

-- Events
CREATE INDEX idx_events_commence ON events(commence_time);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_events_espn ON events(espn_id);

-- Trigram indexes for fast ILIKE search
CREATE INDEX ix_events_home_team_name_trgm ON events USING gin (home_team_name gin_trgm_ops);
CREATE INDEX ix_events_away_team_name_trgm ON events USING gin (away_team_name gin_trgm_ops);

-- Composite index for filtering
CREATE INDEX ix_events_commence_status ON events (commence_time, status);

-- Teams
CREATE INDEX idx_teams_espn ON teams(espn_id);

-- Futures
CREATE INDEX idx_futures_source_external ON futures_markets(source, external_id);
CREATE INDEX idx_futures_outcomes_market ON futures_outcomes(market_id);
CREATE INDEX idx_futures_snapshots_outcome ON futures_odds_snapshots(outcome_id);

-- Win probability
CREATE INDEX idx_win_prob_event_source ON win_prob_snapshots(event_id, source);
CREATE INDEX idx_win_prob_captured ON win_prob_snapshots(captured_at);

-- Team identity
CREATE INDEX idx_team_identity_team ON team_identity_mapping(team_id);
CREATE INDEX idx_team_identity_source ON team_identity_mapping(source);
CREATE INDEX idx_team_identity_name ON team_identity_mapping(source_name);
CREATE INDEX idx_team_identity_sport ON team_identity_mapping(sport_key);

-- StatPal lookups
CREATE INDEX idx_events_statpal_fixture ON events(statpal_fixture_id);
CREATE INDEX idx_teams_statpal ON teams(statpal_team_id);
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

### Pulse (Game Excitement Metric) ✅ Implemented

Bain Luck's proprietary excitement metric measuring how "alive" a game is based on probability movement patterns.

**Two-layer scoring:**
1. **Raw score**: Deterministic calculation from odds movement data (stored as `raw_gei` on events)
2. **Percentile score**: Raw score mapped to percentiles using completed/closed games as reference set. This is the score shown to users. Falls back to raw score if percentiles unavailable.

**Components (weighted):**
- **Heart Rate (25%)**: Frequency of significant probability moves (>=2% threshold). Normalized: moves/min / 0.6
- **Amplitude (30%)**: Magnitude of probability swings (RMS calculation). Normalized: RMS / 0.15
- **Arrhythmia (15%)**: Unpredictability/variance of changes. Normalized: stdev / 0.10
- **Vitals (30%)**: Average closeness to 50% across all snapshots (rewards games that stayed competitive throughout, not just games that ended close)
- **Lead Changes Bonus (0-20%)**: Each time probability crosses 50% (5 pts each, max 20 pts)

**Time Weight Enhancement:**
Late-game drama counts more. Uses exponential curve: `0.6 + 0.4 * (progress^1.5)`

**Multi-bookmaker aggregation:** Raw odds snapshots come from multiple bookmakers (5-11 per event). Before Pulse calculation, snapshots are aggregated into 60-second time buckets using median probability. This prevents bookmaker disagreements from being counted as odds movements.

**Percentile Scoring Layer:**
Raw scores are mapped to percentiles using completed/closed games as the reference set (`gei_percentiles` table). The percentile score is what users see. Falls back to raw score when percentiles are unavailable. Sport-specific percentiles are used when available, with global fallback.

**Score Scale (1-100):**
| Score | Status | Label | Emoji |
|-------|--------|-------|-------|
| 81-100 | Racing | Must-Watch / Incredible | heart-anatomy |
| 61-80 | Strong | Exciting / Engaging | beating heart |
| 41-60 | Steady | Competitive / Steady | growing heart |
| 21-40 | Weak | One-Sided / Slow | stethoscope |
| 1-20 | Flatline | Skip It | chart declining |

**Implementation:** `backend/app/utils/pulse.py`

**Data Quality Gating:**
- Minimum 3 aggregated time buckets to calculate at all
- `data_quality == "minimal"` (3-9 buckets): live display only, no stored score
- `data_quality == "limited"` (10-29 buckets): stored score
- `data_quality == "good"` (30+): stored score
- Hall of Fame rankings require 20+ distinct minute-level time buckets

**Admin Endpoints:**
```bash
GET  /api/admin/pulse/status           # Check calculation status
GET  /api/admin/pulse/distributions    # Score and component distribution analysis
POST /api/admin/pulse/recalculate      # Trigger batch recalculation
```

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

Events are scored 0-100 by `backend/app/utils/highlights.py` using additive weights:

| Factor | Points | Notes |
|--------|--------|-------|
| Live | +30 | Requires `status="live"` AND `commence_time` passed |
| Close matchup (40-60%) | +25 | Pre-game: requires trend evidence (see below) |
| Very close (45-55%) | +10 | Bonus on top of close matchup |
| Favorite switched | +20 | Live/completed only |
| Major prob swing (>=15%) | +15 | From opening line |
| Major score swing (>=20%) | +10 | Projected total change from opening |
| Starting in <3h | +15 | |
| Starting in <1h | +10 | Bonus on top of 3h |
| Tier 1 league | +20 | NBA, NFL, MLB, NHL, EPL, La Liga, UCL |
| Tier 2 league | +10 | NCAAB, NCAAF, WNBA, MLS, Bundesliga, Serie A, MMA, tennis Grand Slams, golf Majors |
| Tier 3 league | -5 | Niche/regional (Liga MX, Brazilian Serie A, boxing) |
| Tier 4 league | -45 | Unknown/uncategorized, minor leagues, regular tennis |
| Championship game | +25 | `llm_importance == "championship"` |
| Playoff game | +15 | `llm_importance == "playoff"` |
| Exhibition game | -20 | `llm_importance == "exhibition"` (preseason, all-star) |
| Recent upset | +20 | Finished + favorite switched |
| Recently finished | +5 | Within 24h |
| Pulse boost (finished) | +10 | Completed events with Pulse score ≥60 |

Events need ≥30 points for the anonymous feed (≥25 for personalized). Live close games and recent upsets always qualify regardless of score.

**Key design rule — pre-game trend evidence:**
Pre-game closeness (e.g., 51/49 across 13 books) could be aggregation noise, not a real story. Close-matchup points are only awarded for pre-game events when:
- The line **moved >=5%** from opening (market is repricing)
- The opening was **not** close but the current odds are (line tightened)
- The game is **starting soon** (closeness becomes action-relevant)

**Labels** (shown on cards in the Highlights section):
| Label | Condition |
|-------|-----------|
| Recent upset | Finished + favorite switched |
| Upset brewing | Live + favorite switched |
| Coin flip | Live + very close (45-55%) |
| Close game | Live + close (40-60%) |
| Lead change | Live + Level 2 detected 50% crossing |
| Momentum shift | Live + major prob swing |
| Odds shifting fast | Live + high volatility (Level 2) |
| Wild game | Live + high variance (Level 2) |
| Close matchup | Starting soon + close |
| Live | Live (no other flags) |
| Line moving | Pre-game + major prob swing (>=15%) |
| Championship game | Pre-game + `llm_importance == "championship"` |
| Playoff game | Pre-game + `llm_importance == "playoff"` |

**Note:** Level 2 time-series scoring (shipped) queries recent `odds_snapshots` for volatility, lead changes, and momentum — see Level 2 section below.

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

#### Level 2: Time-series aware scoring ✅ Shipped
Pass recent snapshot history into the ranking function. This enables:
- **Trend detection**: Is the line moving consistently in one direction, or oscillating? Consistent movement is a story; oscillation is noise.
- **Velocity/acceleration**: A line that moved 5% in the last 10 minutes is more interesting than one that moved 5% over 3 days.
- **Volatility scoring**: High-variance odds histories (lots of movement) are inherently more interesting than flat lines, even if the current state looks unremarkable.
- **Convergence/divergence**: Are bookmakers agreeing more or less over time? Divergence suggests genuine uncertainty.

**Shipped February 2026:**
- [x] `compute_time_series_metrics()` in `utils/highlights.py` analyzes odds snapshots for volatility (RMS probability swings), lead changes (50% crossings), and recent momentum (trend over last hour)
- [x] New highlights labels: "Lead change" (+20 pts), "Odds shifting fast" (+15 pts volatility bonus), "Wild game" (high variance)
- [x] Live odds history queried on every highlight computation to capture full volatility picture
- [x] Component scores: volatility, lead changes, recent trend acceleration all feed into highlights ranking

**Implementation:** `backend/app/utils/highlights.py` with helper function `_compute_time_series_metrics(event_id, session)` that queries the last 24 hours of odds_snapshots, aggregates by time bucket, calculates RMS and momentum.

#### Level 3: Sport-specific and contextual scoring
Different sports have different baseline dynamics:
- A 51/49 NBA game is common; a 51/49 MLB game is rare and notable
- A 10-point swing in football means more in Q4 than Q1
- College basketball upsets are more frequent and exciting than NBA upsets

Also: game context from ESPN (quarter/period, time remaining, score margin) should influence ranking. A 52/48 game in the 4th quarter with 2 minutes left is wildly more interesting than 52/48 in the 1st quarter.

**Partially shipped (February 2026):**
- [x] Event importance wired into scoring: `llm_importance` (championship +25, playoff +15, exhibition -20) feeds into `compute_highlight()`. A playoff NFL game scores 65 base vs 50 regular season.
- [x] ESPN `season.type` parsing: sync task writes 1=exhibition, 2=regular_season, 3=playoff to `llm_importance` for both live and scheduled events. More reliable than LLM text classification.
- [x] Tennis Grand Slams and golf Majors promoted from tier 3 to tier 2.

**Data still needed:** Sport-specific baseline distributions (what's a "normal" amount of volatility for NFL vs NBA vs MLB). Could be a config table or derived from historical data. Game-phase weighting functions per sport.

#### Level 4: Personalized ranking
User favorites boost events featuring their teams. Recent viewing history could influence ranking (don't re-surface events they've already seen; boost sports they engage with).

**Data model:** `user_favorites` table exists with relation types (follow, local, alma_mater, rival). `user_preferences` has sport affinities. `user_pins` tracks explicit interest.

**Shipped (February 2026):**
- [x] Personalized feed scoring with team multipliers, rival detection, sport affinity weighting
- [x] `my_teams_only` filter on `/api/feed` for the "My Teams" page — shows only games/futures involving user's followed teams with wider time windows (24h recent, 7 days upcoming), no min score threshold, no diversity enforcement

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
GET  /api/sports                           # List supported sports
GET  /api/events                           # List upcoming events (with filters)
GET  /api/events/{id}                      # Event details with current odds
GET  /api/events/{id}/history              # Odds history for trending chart
GET  /api/events/{id}/related-futures      # Championship/MVP odds for teams in this game
GET  /api/events/{id}/line-movement        # Line movement analysis with LLM explanation
GET  /api/events/search?q=celtics          # Search events + futures by team/market name
GET  /api/events/typeahead?q=celtics       # Quick typeahead results (top 5 events + 3 futures)
GET  /api/events/pulse-rankings            # Top Pulse games (Hall of Fame)

# Feed
GET  /api/feed                             # Unified ranked feed (events + futures, personalized)
GET  /api/feed?my_teams_only=true          # Team-filtered feed (auth required, wider time windows)

# Futures
GET  /api/futures                          # List active futures markets
GET  /api/futures/{id}                     # Future details with all outcomes
GET  /api/futures/{id}/history             # Odds history for a future
GET  /api/futures/debug/sources            # Count by source (odds_api vs kalshi vs polymarket)
GET  /api/futures/debug/sport-mapping      # Sport linking diagnostics

# Other
GET  /api/oscars                           # Oscars landing page data
GET  /api/market-moves                     # Post-game championship odds shifts
```

### Authenticated Endpoints

```
# Auth
POST /api/auth/google                      # Exchange Firebase ID token
POST /api/auth/google-access-token         # Safari fallback (GIS access token → custom token)
GET  /api/auth/me                          # Current user profile

# User data
GET  /api/me/pins                          # Get user's pinned events/futures
POST /api/me/pins                          # Pin an event/future
DELETE /api/me/pins/{pin_type}/{target_id} # Unpin
GET  /api/me/teams/search?q=lakers         # Search teams for favorites
GET  /api/me/teams/by-location?q=Boston    # Location search with metro alias expansion
GET  /api/me/preferences                   # User preferences + favorites
POST /api/me/onboarding                    # Batch save onboarding data
POST /api/me/favorites                     # Add single favorite
DELETE /api/me/favorites/{team_id}         # Remove favorite
PUT  /api/me/preferences/sport-affinities  # Update sport affinities
```

### Admin Endpoints

```
# Odds polling
POST /api/admin/poll-odds                  # Trigger manual odds poll
POST /api/admin/discover-events            # Trigger event discovery

# Pulse
GET  /api/admin/pulse/status               # Calculation status
GET  /api/admin/pulse/distributions        # Score distribution analysis
POST /api/admin/pulse/recalculate          # Batch recalculation

# ESPN
POST /api/admin/espn/sync-teams            # Sync team colors/logos
GET  /api/admin/espn/teams-status          # Team sync status
POST /api/admin/espn/sync-live-events      # Sync live game data
POST /api/admin/espn/match-teams           # Test team name matching
POST /api/admin/espn/fix-commence-times    # Fix incorrect start times

# Futures categorization
GET  /api/admin/futures/categorization-status
POST /api/admin/futures/categorize         # Trigger LLM categorization
GET  /api/admin/futures/uncategorized      # View uncategorized markets
POST /api/admin/futures/force-categorize   # Force-categorize all remaining

# Kalshi
POST /api/admin/kalshi/poll                # Trigger Kalshi poll
GET  /api/admin/kalshi/task/{task_id}      # Check task status

# Polymarket
POST /api/admin/polymarket/poll            # Trigger Polymarket poll
POST /api/admin/polymarket/backfill-history # Backfill CLOB price history
GET  /api/admin/polymarket/task/{task_id}  # Check task status

# Prediction market matching
POST /api/admin/prediction-markets/match   # Trigger matching
GET  /api/admin/prediction-markets/status  # Linked vs unlinked counts
GET  /api/admin/prediction-markets/debug   # Debug matching funnel
POST /api/admin/prediction-markets/poll-live # Trigger live price poll
POST /api/admin/prediction-markets/link    # Manual link (fallback)

# Rosters (ESPN + MLB Stats API)
POST /api/admin/rosters/sync               # Trigger roster sync
GET  /api/admin/rosters/task/{task_id}     # Check task status

# MLB
POST /api/admin/mlb/sync                   # Trigger MLB win prob sync
GET  /api/admin/mlb/task/{task_id}         # Check task status

# Snapshot retention
POST /api/admin/snapshots/collapse         # Trigger snapshot collapsing
GET  /api/admin/snapshots/task/{task_id}   # Check task status
GET  /api/admin/snapshots/stats            # Current row counts

# Worker health
GET  /api/admin/celery/health              # Celery worker heartbeat status
GET  /api/admin/celery/dashboard           # Task-level success metrics dashboard
GET  /api/admin/celery/task-metrics/{name} # Per-task metrics detail
```

---

## Search

### Philosophy

Search is a core discovery mechanism that lets users find games, teams, and historical data quickly. The search experience should feel **instant, forgiving, and intelligent** — users shouldn't need to know exact team names or league structures.

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
- Also searches futures markets by market name
- Results ordered: Live -> Upcoming -> Completed
- Returns `results` (events) and `futures` (markets) arrays
- Sport disambiguation (shows which leagues matched)
- Paginated results with Previous/Next navigation
- Trigram indexes for fast ILIKE queries

**UI Components:**
- `SearchBar` component: typeahead with 200ms debounce, keyboard navigation (up/down arrows + Enter), compact mode for header
- Header integration: mobile search icon (links to `/search`), desktop inline search bar
- Full search results page at `/search?q=...`
- Sport filter pills when multiple leagues match

**Typeahead endpoint:** `GET /api/events/typeahead?q=celtics`
- Returns top 5 events + 3 futures instantly
- Used by `SearchBar` component for dropdown suggestions
- Lightweight endpoint for fast header-based search

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

#### Phase 2: Smart Query Parsing (Q3 2026)
Parse natural-language-like queries into structured filters:

| User Types | Parsed As |
|------------|-----------|
| "celtics nba" | team=celtics, sport=basketball_nba |
| "celtics 2024" | team=celtics, season=2024-25 |
| "celtics vs lakers" | team1=celtics, team2=lakers |
| "nfl week 10" | sport=nfl, week=10 |
| "march madness" | sport=basketball_ncaab, date=march |

#### Phase 3: Suggested Searches (Q3 2026)
Surface interesting queries users might want (trending, favorites-based, discover).

#### Phase 4: Natural Language Search (Q4 2026)
LLM-powered query understanding for complex requests using Claude API.

#### Phase 5: Saved Searches & Alerts (2027)
For authenticated users: save frequent searches, get notified when new results match.

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

### Phase 3: Reliability & Data Quality ✅ Complete
**Observable, resilient, and sustainable infrastructure.**

- [x] Event discovery task (polls ALL sports, not just those with existing events)
- [x] Stale data detection and auto-closing of stuck events
- [x] Per-sport polling intervals based on game proximity
- [x] **Sentry error tracking** — FastAPI backend + Celery worker. Controlled by `SENTRY_DSN` env var.
- [x] **Test coverage for core algorithms** — 1667+ total tests (1550+ backend pytest items across 20 files + 117+ frontend tests across 4 files). Covers: Pulse (85), Highlights (126 incl. Level 2 + event importance), odds math (70), futures categorization (116), win probability (67), team linking (97), LLM classification (60), prediction market matching (291), ESPN API parsing (50), stale bookmaker filter (23), snapshot collapse (13), retention SQL (19), redis state (13), onboarding/preferences (31), MLB Stats API (33), task wiring (21), odds polling helpers (27), win prob sources (24), line movement (26), futures highlights + feed reasons (36).
- [x] **Data retention Phase 1** — Lossless snapshot collapsing across `odds_snapshots`, `win_prob_snapshots`, `futures_odds_snapshots`. Write-time dedup prevents identical consecutive rows. Retroactive collapse runs daily via Celery beat schedule. Phase 2: Rewritten to pure SQL using PostgreSQL window functions (LAG, SUM, CTEs) for constant memory — zero rows loaded into Python. Fixes Heroku worker OOM (R14).
- [x] **Super Bowl one-off cleanup** — Removed ~7,000+ lines of dead code across ~15 files (contest.py, superbowl.py, youtube_api.py, CommercialLeaderboard.tsx, TV mode, etc.)
- [x] **Tasks package refactor** — Monolithic `tasks.py` (2,970 lines) refactored into `tasks/` package with 15 modules. All task names pinned for backward compatibility. Celery heartbeat + health endpoint added.
- [x] **Stale bookmaker filtering** — Extracted to `app/utils/odds_filtering.py` with 23 regression tests. Uses `valid_until` (write-time dedup aware) via `_effective_time()`. Layer 2 recency filter for live events excludes bookmakers >10 min stale.
- [x] **Worker memory (R14 OOM)** — Snapshot collapse rewritten to pure SQL (window functions + batch delete) for constant memory usage. Verified on production Feb 2026.
- [x] **Task correctness monitoring** — Task-level success metrics system: `record_task_success()`/`record_task_failure()` in `redis_state.py`. Dashboard at `GET /api/admin/celery/dashboard` with health classification. 7 key tasks instrumented.

### Phase 4: Pulse (Game Excitement Metric) ✅ Complete
**Proprietary excitement scoring for all games.**

Completed: February 2026

- [x] Implement Pulse calculation algorithm in backend (`backend/app/utils/pulse.py`)
- [x] Real-time Pulse updates for live games (every poll cycle)
- [x] Batch Pulse calculation for completed games (every 10 minutes)
- [x] PulseBadge component with tooltip showing component breakdown
- [x] Pulse displayed on all live, completed, and closed games
- [x] Explainer page at `/pulse` with full methodology
- [x] Admin endpoints for Pulse management
- [x] Debug endpoint for Pulse diagnostics
- [x] Percentile scoring layer (raw scores mapped to percentiles using completed games)
- [x] Distribution-tuned normalization constants
- [x] Hall of Fame page at `/pulse/hall-of-fame` (top 25 highest/lowest Pulse games)

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

**Storage:** localStorage for anonymous users, `user_pins` table for authenticated users. Pin migration from localStorage to server happens on first login via `usePinSync` hook.

### Phase 6: Authentication & Personalization
**User accounts for cross-device experience.**

#### Phase 6.1: Core Auth ✅ Complete (February 2026)
- [x] Firebase Auth integration (Google Sign-In)
- [x] Google Identity Services (GIS) OAuth popup flow
- [x] Safari compatibility via 3-tier auth fallback (shipped Feb 2026)
- [x] Backend auth middleware (`get_current_user` / `get_optional_user`)
- [x] User profile endpoints (`POST /api/auth/google`, `GET /api/auth/me`)
- [x] Server-side pin sync (`/api/me/pins` CRUD)
- [x] Frontend auth context + sign-in UI (UserMenu, AuthProvider)
- [x] Pin migration from localStorage to server on first login

**Auth Architecture (3-tier Safari fallback):**
- **Tier 1 (Chrome/Firefox)**: GIS `initTokenClient` (OAuth popup, 4s timeout) -> Firebase `signInWithCredential` (4s timeout)
- **Tier 2 (Safari, ITP fallback)**: If Tier 1 fails, send access token to `POST /api/auth/google-access-token` -> backend verifies with Google OAuth token endpoint -> creates Firebase custom token via Admin SDK -> frontend calls `signInWithCustomToken` (4s timeout)
- **Tier 3 (Last resort)**: If both fail, backend returns PyJWT session token that frontend stores in localStorage and sends as Authorization header
- **Auth persistence**: Switched from IndexedDB (browser-controlled) to localStorage (app-controlled) for more reliable persistence across tabs and app reloads
- Requires `FIREBASE_SERVICE_ACCOUNT_JSON` on backend for Safari support (enables token verification and custom token creation)

**Auth Philosophy:**
- No required sign-in — logged-out experience must feel complete
- Auth unlocks: Favorites sync, notifications, cross-device preferences, pin sync
- Auth is **pull-based, not forced**

#### Phase 6.2: Onboarding & Preferences ✅ Complete (February 2026)
- [x] 5-step onboarding flow (location → follow teams → alma maters → sports+beyond → rivals)
- [x] Preference storage in `user_preferences` table
- [x] Metro alias expansion (e.g., "New England" → Boston Celtics, Patriots, Bruins, Red Sox)
- [x] Team search with events table fallback for auto-creation of college teams
- [x] Settings editor at `/preferences` (teams, interests, pinned items, account)
- [x] Inline favorites CRUD (add/remove without revisiting onboarding)
- [x] Batch save endpoint saves location, favorites, sport affinities, onboarding state atomically
- [x] My Stuff (`/my-stuff`) restructured as team-filtered feed (was preferences editor)
- [x] `my_teams_only` API parameter on `/api/feed` with wider time windows, team filtering, no min score

#### Phase 6.3: Personalized Experience ✅ Complete (February 2026)
- [x] Personalized feed scoring with team multipliers (local 3.5×, alma_mater 2.5×, followed 2.0×)
- [x] Rival multipliers (live losses and blown leads boost rival games in feed)
- [x] Sport affinity weighting (user's sport preferences boost relevant events)
- [x] Personalization badges ("Your team", "Local", "Alma mater", "Rival losing")
- [x] Unified interestingness feed combining events + futures with personalization overlay
- [x] Non-sports categories in feed (Politics, Entertainment, Crypto, Economics, Tech, Weather, Geopolitics, Culture)
- [x] Non-sports tier promotion: Politics, Entertainment, Crypto moved from tier 3 to tier 2 in frontend categorization (increased weighting)

### Phase 7: LLM Integration & Metadata Enrichment ✅ Complete
**OpenAI-powered smart features and ESPN data integration.**

Completed: February 2026

- [x] OpenAI GPT-4o-mini integration (`backend/app/services/llm.py`)
- [x] Generic `classify()` utility for text classification
- [x] Hybrid futures categorization (90+ regex patterns + LLM fallback)
- [x] 23 sport categories supported
- [x] Zero uncategorized markets (LLM always returns a category)
- [x] LLM results cached in database (`llm_sport_category` column)
- [x] Admin endpoints for categorization management
- [x] LLM Metadata Enrichment: Gender, level, league, importance classification
- [x] ESPN API Integration: Team colors, logos, live game data, win probability
- [x] Venue data from ESPN
- [x] ESPN team name matching with unicode normalization

**Categorization Files:**
- Frontend patterns: `frontend/lib/sportCategories.ts`
- Backend patterns: `backend/app/utils/futures_categorization.py`
- LLM service: `backend/app/services/llm.py`

### Phase 8: ESPN Integration ✅ Complete
**Team enrichment and live game data from ESPN's undocumented API.**

Completed: February 2026

- [x] ESPN API client (`backend/app/services/espn_api.py`)
- [x] Automatic team sync (colors, logos, alternate names, records)
- [x] Live event sync every 60 seconds (game clock, period, broadcast, win prob)
- [x] Team name matching with unicode/accent normalization for college teams
- [x] Venue data (name, city, state, country, capacity)
- [x] Commence time correction (fixes wrong UTC times from The Odds API)
- [x] Auto-creates Team records from ESPN scoreboard data

**Mapped Sports:** NBA, NCAAB, WNCAAB, NFL, NCAAF, NHL, MLB, MLS, EPL

**Frontend Display:**
- Team logos and colors on EventCard and event detail page
- Team-colored probability bar
- Broadcast info badge
- ESPN win probability badge (live games only)
- ESPN trend line on OddsChart (orange dashed line)

### Phase 9: Futures Markets ✅ Complete
**Championship odds, MVP races, and outrights.**

Completed: February 2026

- [x] Database schema (`futures_markets`, `futures_outcomes`, `futures_odds_snapshots`)
- [x] Poll futures odds from The Odds API (hourly task)
- [x] Futures visualization with horizontal bar charts
- [x] Movement indicators (24h change, rank change)
- [x] Futures categories via hybrid categorization (rules + LLM)
- [x] Sport grouping on homepage
- [x] Futures detail pages with all outcomes
- [x] Search includes futures markets
- [x] Futures pinning support

### Phase 10: Kalshi Prediction Markets ✅ Complete
**Sports prediction markets with timing info.**

Completed: February 2026

- [x] Kalshi API integration (`backend/app/services/kalshi_api.py`)
- [x] Polling task with rate limiting (hourly at :45, in `tasks/kalshi.py`)
- [x] Stores bid/ask spreads and timing info
- [x] Categories: Sports, Golf, Football, Basketball, Baseball, Hockey, Tennis
- [x] Commence time and resolution date populated
- [x] LLM-based categorization for uncategorized markets

**Data Model:**
- Kalshi events -> `futures_markets` table (source="kalshi")
- Kalshi markets -> `futures_outcomes` table
- Stores: `yes_bid`, `yes_ask`, `last_price`

**To add more categories**, edit `sports_categories` in `backend/app/tasks/kalshi.py`:
```python
sports_categories = ["Sports", "Golf", "Football", "Basketball", "Baseball", "Hockey", "Tennis"]
```

### Phase 11: Multi-Source Win Probability ✅ Complete
**Multiple independent win probability sources on a single chart.**

Completed: February 2026

- [x] Generic `win_prob_snapshots` table with source column
- [x] Source registry in `backend/app/config/win_prob_sources.py` (Python dict, not DB)
- [x] Bain Luck statistical win probability model (nflfastR-inspired normal distribution)
- [x] OddsChart renders N sources dynamically with labeled, color-coded lines
- [x] `/events/[id]/models` detail page showing methodology + attribution
- [x] Dual compute paths: ESPN sync (60s) + odds polling (30-60s)

**Current Sources (7):**
| Source | Type | Sports | Notes |
|--------|------|--------|-------|
| Betting Odds | Market (The Odds API) | All | Sportsbook consensus (5-15 books) |
| ESPN | Model (undocumented API) | NBA, NCAAB, NFL, NCAAF, NHL, MLB | Only live games, orange dashed line on chart |
| Bain Luck Model | Model (nflfastR methodology) | NFL, NCAAF, NBA, NCAAB, WNCAAB, NHL | Statistical model with wall-clock fallback when ESPN clock unavailable |
| MLB Stats API | Model (Official MLB API) | MLB | Free, live baseball only, no API key, teal line |
| Kalshi | Market (Prediction market) | All sports | Game-level outcomes, green line |
| Polymarket | Market (Prediction market) | All sports | Game-level outcomes, blue line |
| MoneyPuck | Model (stub) | NHL | Stub configured, awaiting full integration |

**Bain Luck Model Details:**
- Normal distribution model: score diff + time remaining + pregame spread
- Sport-specific params: NFL base_std=13.45, NBA/NCAAB=12.0, NHL=2.5
- Prefers `game_clock` and `period` from ESPN sync, but falls back to wall-clock time estimation (`estimate_seconds_remaining_from_wall_clock()`) when ESPN data is unavailable (common for college teams)

**Architecture for adding a new source:**
1. Add entry to `WIN_PROB_SOURCES` dict in `win_prob_sources.py`
2. Write snapshots to `win_prob_snapshots` table with the source key
3. Chart and API pick it up automatically — no frontend changes needed

**Planned sources (stubs configured, awaiting implementation):**
| Source | Sport | Status | Notes |
|--------|-------|--------|-------|
| MoneyPuck | NHL | Stub configured | Free JSON API with live game WP |

### Phase 12: Related Futures ✅ Complete (Phases 1-3)
**Show championship odds, MVP odds, and award futures relevant to teams playing in a specific game.**

Completed: February 2026

- [x] Team linking infrastructure (`FuturesOutcome.team_id` FK, `FuturesMarket.market_tier`, backfill task)
- [x] `GET /api/events/{id}/related-futures` endpoint
- [x] Hybrid matching: name ILIKE (team names, short names, roster players) + team_id lookup
- [x] Triple sport filtering (external_id prefix, llm_sport_category, sport_id)
- [x] Frontend "Bigger Picture" section with team colors, logos, probability bars, tier icons

**Endpoint:** `GET /api/events/{id}/related-futures`

**Matching strategy (hybrid):**
1. **Name ILIKE** — Team names, short names (>=4 chars), alternate names, and roster player names matched against `FuturesOutcome.name`
2. **team_id lookup** — Supplementary matching via `FuturesOutcome.team_id`
3. Combined via OR for maximum recall

**Shipped phases:**
- Phase 4 ✅: LLM "Bigger Picture" summary — `generate_related_futures_summary()` in `llm.py` produces 2-3 sentence casual summary using GPT-4o-mini, cached in `LineMovementAnalysis` with 2h TTL. Frontend summary-first collapsed design with "See all N futures" toggle.

**Future phases:**
- Phase 5: Bidirectional linking — futures detail pages show relevant upcoming/recent events

### Phase 13: Roster Sync (ESPN + MLB Stats API) ✅ Complete

**Structured roster data for player matching in related futures.**

Completed: February 2026

Originally used SportsDataIO, fully migrated to ESPN + MLB Stats API (zero cost).

- [x] ESPN roster endpoint for NBA, NFL, NHL, NCAAB, NCAAF, WNBA, MLS, EPL
- [x] MLB Stats API for baseball rosters
- [x] Roster sync task (daily at 7:00 AM UTC, `tasks/roster_sync.py`)
- [x] `Team.roster_players` JSONB column for player name matching
- [x] Deduplicated, sorted player names (including ASCII variants)
- [x] SportsDataIO client (`sportsdata_api.py`) deleted — 321 lines of dead code removed

### Phase 14: Snapshot Data Retention ✅ Complete
**Lossless compression of consecutive identical snapshot rows.**

Completed: February 2026

- [x] Write-time dedup for `odds_snapshots` and `futures_odds_snapshots` (checks last row before inserting)
- [x] Write-time dedup for `win_prob_snapshots`
- [x] Retroactive collapse task (`collapse_snapshots`) processes one table per invocation
- [x] Runs daily via beat schedule (6:30/6:35/6:40 UTC for odds/winprob/futures)
- [x] Lossless — original time series fully reconstructable from `captured_at` + `valid_until` + `reading_count`

- [x] Rewrite collapse to pure SQL (window functions LAG/SUM + CTEs + batch delete) for constant memory — zero rows loaded into Python
- [x] Fixes Heroku worker OOM (R14) — verified on production Feb 2026

**Remaining Phase 2 opportunities (if OOM recurs):**
- [ ] Pre-game snapshot thinning (keep 1/hour instead of every poll)
- [ ] Aggregate completed games into `odds_aggregated` then delete raw rows
- [ ] Cap futures snapshot retention post-resolution

### Phase 15: Polymarket Integration & Additional Data Sources
**Expanding coverage beyond sportsbooks into prediction markets, and adding new probability sources.**

Target: Q2 2026

This phase moves Bain Luck toward the broader vision: **"The easiest place to see the probability of anything happening, computed any way possible."** Polymarket adds both deeper sports coverage and wildcard non-sports categories (politics, entertainment, crypto, weather) that make the feed more interesting and differentiated.

#### Phase 15a: Polymarket Integration ✅ Phase 1 Shipped

**Why Polymarket?**
- World's largest prediction market (~$9B valuation, $1.1B+ sports volume)
- **No API key required** for read-only access (unlike Kalshi)
- 3,294+ active sports markets with official NHL and UFC partnerships
- Built-in historical price data via `/prices-history` endpoint
- Generous rate limits (~1,000 calls/hour vs Kalshi's ~10 req/sec)
- Non-sports categories unlock "probability of anything" content for the feed

**API Architecture:**

Polymarket splits its API into four services. We only need two (both free, no auth):

| Service | Base URL | Purpose |
|---------|----------|---------|
| Gamma API | `https://gamma-api.polymarket.com` | Market discovery, metadata, tags, sports |
| CLOB API | `https://clob.polymarket.com` | Current prices, order book, price history |

Key Gamma endpoints:
- `GET /events` — List events (filterable by tag_id, series_id, active, closed, volume, liquidity, date range)
- `GET /sports` — Discover supported sports/leagues with series_id and tag_id metadata
- `GET /markets` — List individual markets
- `GET /tags` — Discover all categories/tags

Key CLOB endpoints:
- `GET /prices-history?market={token_id}&interval=max&fidelity=60` — Historical price time series
- `GET /midpoint?token_id=X` — Mid-market price
- `GET /price?token_id=X&side=buy` — Best bid/ask

**Data Model Mapping:**

| Polymarket | Bain Luck DB |
|------------|----------------|
| Event | `futures_markets` (source="polymarket") |
| Event.id | `futures_markets.external_id` |
| Event.title | `futures_markets.name` |
| Event.tags | Used for `llm_sport_category` / sport categorization |
| Event.startDate/endDate | `commence_time` / `resolution_date` |
| Market (per outcome) | `futures_outcomes` |
| Market.conditionId | `futures_outcomes.external_id` |
| Market.outcomePrices[0] | `futures_outcomes.current_probability` |
| Market.lastTradePrice | Snapshot `last_price` |
| CLOB bid/ask | `current_yes_bid` / `current_yes_ask` |
| Market.volume | For liquidity-based ranking |

NegRisk events (multi-outcome, e.g., "NBA Championship Winner") have one binary Yes/No market per team. Maps naturally to our FuturesOutcome model.

**Implementation checklist (Phase 1 — shipped Feb 2026):**
- [x] API client: `backend/app/services/polymarket_api.py` (Gamma + CLOB, no API key needed)
- [x] Polling task: `backend/app/tasks/polymarket.py` with streaming pagination (batched commits, 50 events/batch, page cap warning)
- [x] 160+ tag-to-category mapping with fallback to `futures_categorization.py` rules + league detection
- [x] Outcome name extraction from stringified JSON arrays
- [x] Admin endpoints: `POST /api/admin/polymarket/poll`, task status check
- [x] Task registration in `tasks/__init__.py` with `name="app.tasks.poll_polymarket"` wrapper
- [x] 69 tests covering tag mapping, name extraction, API parsing

**Phase 2 — Shipped (Feb 2026):**
- [x] Beat schedule `poll_polymarket` (auto-polling hourly at :15)
- [x] Price history backfill via CLOB `/prices-history` endpoint (`POST /api/admin/polymarket/backfill-history` fetches historical prices for outcomes with sparse data, stores as FuturesOddsSnapshot rows)
- [x] Live game price polling every 2 min via `poll_live_prediction_markets` (only fetches prices for markets linked to live events, to avoid rate limit burnout)
- [x] Non-sports category display in frontend (Politics, Entertainment, Crypto tiers in categorization logic)

**Parsing gotcha:** Gamma API returns `outcomes`, `outcomePrices`, and `clobTokenIds` as stringified JSON arrays (e.g., `"[\"Yes\", \"No\"]"`). Must use `json.loads()` to parse.

**Rate limit strategy:** ~1,000 calls/hour is generous. Unlike Kalshi (0.5s delay between pages), we can paginate freely. Still add modest delays (0.2s) between league-level fetches to be a good API citizen.

**Sports coverage (confirmed):**
| Sport | Coverage |
|-------|----------|
| NFL/CFB | Full (games, futures, props) |
| NBA/NCAAB | Full |
| NHL | Full (official partnership) |
| MLB | Full |
| UFC/MMA | Full (official partnership) |
| Soccer | Extensive (EPL, La Liga, UCL, Bundesliga, Serie A, MLS, etc.) |
| Golf (PGA) | Available |
| Tennis (ATP, WTA) | Available |

**Non-sports categories to enable:**
| Category | Examples | Feed Value |
|----------|---------|------------|
| Politics | Elections, approval ratings, policy | "Will X win the election?" — 73% |
| Entertainment | Oscars, box office, Nobel Prize | Fun wildcard content |
| Crypto | Bitcoin targets, ETF approvals | "BTC above $100K by June?" — 45% |
| Economy | Fed rate cuts, inflation, GDP | Macro context |
| Tech/AI | AI benchmarks, SpaceX | Forward-looking |
| Weather | Daily temperatures, disasters | Relatable probabilities |

**Legal note:** Polymarket's ToS prohibits US persons from *trading*, but the read-only API is globally accessible. Our integration only reads and displays probabilities — no trading functionality. The "(if legally viable)" caveat from the original roadmap is resolved: read-only display is unambiguously fine.

**Comparison to existing Kalshi integration:**
| Dimension | Kalshi (current) | Polymarket (current) |
|-----------|------------------|---------------------|
| Auth required | Yes (`KALSHI_API_KEY`) | None |
| Rate limits | Strict (~10 req/sec) | Generous (~1,000/hr) |
| Sports markets | Hundreds | 3,294+ |
| Price format | Cents (0-100), convert | Decimal (0.00-1.00) native |
| Historical prices | None (we must poll) | Built-in `/prices-history` |
| Non-sports content | Limited (we filter to sports) | Extensive |
| Liquidity | Lower | Highest in prediction markets |

#### Phase 15b: Additional Win Probability Sources

- [ ] MoneyPuck for NHL (free JSON API with live game win probability)
- [x] MLB Stats API for MLB ✅ Shipped — Live baseball win probability via `statsapi.mlb.com`, source key "fangraphs" (legacy name), display name "MLB Model", teal `#0d9488`

#### Phase 15c: Additional Data Sources

- [ ] International sportsbooks for broader odds coverage
- [ ] Real-time sports data (play-by-play) for richer context

#### Phase 15d: Prediction Market Game-Level Odds ✅ Fully Shipped

**Show Kalshi and Polymarket individual game outcomes as win probability sources alongside sportsbooks and models.**

Both Kalshi and Polymarket have moneyline-style game outcome markets ("Will the Lakers beat the Celtics?"). These represent a fundamentally different probability source — prediction market consensus vs. sportsbook consensus vs. statistical models. Showing them side-by-side on the event detail page is the ultimate expression of **"all possible win probabilities aggregated into one place."**

**Shipped (Feb 2026):**
- [x] Two-pass matching strategy: targeted Kalshi ticker scan (12 sport prefixes) + general scan for Polymarket and non-ticker Kalshi markets
- [x] Regex-based game-level detection, fuzzy team name matching, Kalshi ticker parsing
- [x] Sport+time fallback when names are generic (e.g., "Professional Basketball Game")
- [x] Dash matchup false positive prevention (rejects "English Premier League – 2nd Place" etc.)
- [x] Write matched game-level odds to `win_prob_snapshots` with source="polymarket" / source="kalshi"
- [x] Source registry entries in `win_prob_sources.py` (Kalshi: green `#22c55e`, Polymarket: blue `#3b82f6`)
- [x] Beat schedule: `match_prediction_markets` runs every 15 min, live polling every 2 min via `poll_live_prediction_markets` (only fetches prices for markets linked to live events)
- [x] Admin endpoints for status, debug funnel, and manual linking
- [x] 291 tests covering ticker detection, name building, false positives, sport prefix mapping, ticker abbreviation parsing, ticker fragment matching, live poll wiring, matchup-name outcome fallback, prop/spread outcome filtering
- [x] OddsChart already renders N sources dynamically — no frontend changes needed
- [x] **Divergence badge (shipped Feb 2026)**: Frontend detects when prediction market odds differ >5% from sportsbook consensus. Purple badge for >10% divergence, blue for >5%. Appears on event detail page next to odds chart.

**OddsChart Implementation:**
- Dynamically renders all configured sources with different colors and dash patterns
- Prediction market lines (Kalshi green, Polymarket blue) sit alongside sportsbook (dark solid), ESPN (orange dashed), and Bain Luck model (purple dashed) for full comparison

**Why this matters:**
Sportsbooks set lines to balance action (minimize risk). Prediction markets set prices based on collective belief (maximize accuracy). When they disagree, something interesting is happening — the divergence badge makes this obvious.

### Phase 16: Probability Comparisons ("Comparable Odds")
**Make win probabilities viscerally relatable by comparing them to real-world likelihoods.**

Target: TBD (Exploratory)

A user sees their team has a 15% chance of winning. Instead of just a number, a "Comparable Odds" box on the event detail page tells them: *"About as likely as rain on a summer day in Atlanta"* or *"About as likely as your neighbor owning a dog in Germany."*

**Why this works:**
- Probabilities are abstract; real-world analogies make them intuitive
- Fits the product's mission of making odds *understandable* to non-bettors
- Creates a delightful, shareable moment
- Reinforces the second-screen experience with conversation starters

**Requirements:**
- Massive comparison database (minimum 1,000 entries)
- Bucketed by probability range (5% bands)
- Diverse categories (weather, animals, geography, pop culture, science, etc.)
- Sourced and factual with citations
- Tone: Fun, surprising, educational — never condescending or gambling-adjacent

### Phase 17: Event Similarity Scores
**Find historical events that followed the most similar probability pattern — the "Baseball Reference" approach for odds.**

Target: TBD (Exploratory)

Inspired by [Baseball Reference's similarity scores](https://www.baseball-reference.com/about/similarity.shtml), this feature would show users which past games followed probability arcs most similar to the current or completed game.

**Similarity algorithm (proposed):**
- Probability curve shape (40%): DTW or resampled point-by-point comparison
- Final margin (15%): How close the final probabilities were
- Volatility pattern (20%): Similar number/size of swings
- Lead changes (15%): Similar number of favorite flips
- Sport match (10%): Same sport gets a bonus

**Phases:**
1. Post-game similarity only (batch computed after game ends)
2. Live similarity matching (compare partial curves during games)
3. Cross-sport similarity
4. User-facing "Find games like this" search feature

### Phase 18: Advanced LLM Features
**Intelligent explanations, search, and context generation.**

Target: 2027

- [ ] Odds movement explanations (detect significant swings, generate human-readable explanations)
- [ ] Smart search query understanding (LLM-parsed natural language queries)
- [ ] Excitement summaries (narrative summaries for high-Pulse games)
- [ ] Market description generation

**Principles:**
- Brief, factual, non-predictive
- Only surface for meaningful events
- No gambling advice or encouragement

### Phase 19: Team Insights (LLM-Powered Personalized Feed)
**Personalized insights about your favorite teams, synthesized by LLM from structured DB queries.**

Target: TBD (Requires Firebase Auth for favorites persistence)

During onboarding, users select favorite teams. The system runs structured queries (recent results, upcoming games, live games, championship odds, high-Pulse games), then uses GPT-4o-mini to synthesize the ~10 most interesting insights.

**Key Design Decision:** Pre-query structured data per team, then let the LLM synthesize and narrate. This is cheaper, faster, more reliable, and auditable than letting the LLM query the DB.

**Implementation Phases:**
1. Team picker UI + insights endpoint (web only)
2. Event detail page integration ("More about this team")
3. Notification triggers based on urgency field
4. iOS integration with native insights feed
5. Daily digest emails

### Phase 20: iOS App ✅ SHIPPED (Feb-Mar 2026)
**Native second-screen experience — shipped across 7 phases, 29 commits.**

- [x] SwiftUI app with near-feature-parity to web
- [x] Section-based feed (Live Now, Just Happened, Upcoming, Top Markets)
- [x] Multi-source odds chart with period markers, All/Since Start toggle, team colors
- [x] Event detail: probability bar, chart, related futures ("Bigger Picture"), line movement, scoring plays
- [x] Search with suggestions + EI Rankings (Hall of Fame)
- [x] Filter chips (sport categories, Starting Soon, Primetime/National TV)
- [x] Apple Sign-In + Google Sign-In with Keychain token storage
- [x] Native 5-step onboarding flow
- [x] Preferences page with app icon selection
- [x] iPad-native layout (sidebar navigation + max-width detail views)
- [x] Category detail pages navigable from filter chips
- [x] Swipe-to-pin on cards, compact pin buttons
- [x] Haptic feedback, live tab badge, skeleton loading states
- [x] Firebase Analytics (screen views, event interactions)
- [x] Deep linking support
- [ ] Share extension for quick sharing
- [ ] Background refresh
- [ ] Widgets (Lock Screen, Home Screen)
  - Current game win probability
  - Upcoming games for favorite teams
  - "Most Exciting Game Right Now"
- [ ] App Store submission

---

## Horizon — AI-Native Sports Intelligence

These are differentiated features that can't be built with odds data alone. They require sports data enrichment (rosters, injuries, standings, schedules from ESPN free API + MySportsFeeds) combined with AI interpretation. Ordered by estimated impact and feasibility.

1. ~~**"The Market Was Wrong"**~~ ✅ **Shipped** — `GET /api/market-moves` endpoint + `/market-moves` page. Shows post-game championship odds shifts. Next: v2 with AI narrative generation and personalization.

2. ~~**"Why Did the Line Move?"**~~ ✅ **Shipped** — Detection in `line_movement.py`, LLM explanation in `llm.py`, ESPN injuries/news context via `get_event_context()`, live game state (score/period/clock). Cached in `LineMovementAnalysis`. Frontend in `LineMovementExplainer.tsx`. 26 line movement tests + 8 ESPN parsing tests.

3. **"Your Team's Season at a Glance"** — Dashboard: championship odds trajectory, win/loss record overlaid on odds chart, key inflection points annotated.

4. **Injury Impact Score** — When a player is injured, show historical impact on team's odds.

5. **Game Context Card** — Rich pre-game card: standings implications, head-to-head record, streak info, playoff scenario impact.

6. **Overreaction Index** — Compare a team's current championship odds trajectory against historical base rates.

7. **Momentum Tracker** — Rolling 10-game odds trend visualization showing which teams the market is repricing.

8. **"What's Actually at Stake"** — For each game, show concrete implications: "Win and they're 2 games up in the division."

9. **Sharps vs Public** — If MySportsFeeds provides line movement + betting splits, surface when sharp money disagrees with public sentiment.

10. **Futures Postmortem** — At season end, show who "won" the futures market: early bettors on the champion, worst value bets, biggest surprises.

---

## Ideas Under Exploration

These ideas need design questions answered before planning. See `docs/planning-questions.md` for detailed question sets.

### Bespoke Category Landing Pages
~~Beautiful, over-invested landing pages for each major sport~~ **Golf page shipped** at `/categories/golf` (Mar 2026): cross-source tournament odds aggregation, current event detection, 24h movers, sparkline charts, LPGA/TGL separation. Generic `/categories/[slug]` infrastructure also built. Remaining: basketball, football, soccer, politics, entertainment, and other categories. The Oscars page was the prototype for this pattern.

### Golf Live Scores Integration
StatPal provides live scores for golf tournaments (leaderboard updates every 15s). Need to figure out how to USE this data on the golf category page and tournament detail pages — e.g., live leaderboard position overlaid on odds, real-time scoring updates during tournament rounds. The golf grid currently only shows pre-tournament odds; live scores could make it dynamic during events.

### "What Are the Odds?" Game
Probability guessing game: show users events/futures from the DB, they guess the probability, we score accuracy. Designed as a retention driver and viral acquisition vehicle. Many game mechanics to work out (scoring formula, difficulty modes, multiplayer, social sharing).

### Insight Arena (Admin LLM Training)
Admin-only feature: LLM generates event-level, category-level, and DB-wide insights. Two insights are surfaced at a time for A/B preference selection. Choices train the LLM (via prompt refinement, RLHF-style preference data, or few-shot examples) on what makes a good insight. Eventually graduates insights to user-facing surfaces.

---

## Sports Coverage

### Blacklist Approach

Bain Luck uses a **blacklist** rather than a whitelist for sports coverage:

- **Included**: All sports from The Odds API except those on the blacklist, plus all Kalshi and Polymarket markets (sports + non-sports categories)
- **Excluded**: Most soccer leagues (except MLS, EPL, La Liga, Bundesliga, Serie A, UCL, and other major leagues), Cricket, Rugby, AFL

This means the system automatically picks up new sports that The Odds API adds without requiring code changes.

### Sport Categories

Sports are grouped into categories for the UI based on their API key prefix:

| Category | Prefix(es) | Emoji |
|----------|------------|-------|
| Football | americanfootball_* | football |
| Basketball | basketball_* | basketball |
| Baseball | baseball_* | baseball |
| Hockey | icehockey_* | hockey |
| Soccer | soccer_usa_mls | soccer |
| MMA | mma_* | martial arts |
| Boxing | boxing_* | boxing |
| Golf | golf_* | golf |
| Tennis | tennis_* | tennis |
| Politics | politics_* | ballot |
| Esports | esports_* | controller |
| Motorsport | motorsport_*, racing_* | racing |
| Other | (any unmatched) | trophy |

Unknown sports automatically fall into the "Other" category.

### High Priority Sports

| Sport | API Key Pattern | Notes |
|-------|-----------------|-------|
| NFL | americanfootball_nfl | Primary focus |
| NBA | basketball_nba | Primary focus |
| MLB | baseball_mlb | Primary focus |
| NHL | icehockey_nhl | Primary focus |
| College Football | americanfootball_ncaaf | Strong user demand |
| College Basketball | basketball_ncaab, basketball_wncaab | March Madness priority |
| MLS | soccer_usa_mls | US soccer coverage |

---

## Configuration

### Polling Strategy

| Scenario | Interval |
|----------|----------|
| Live games | 30 seconds |
| Games starting in 0-2 hours | 60 seconds |
| Games starting in 2-6 hours | 2-5 minutes |
| Event discovery (all sports) | 15 minutes |
| Futures (The Odds API) | Hourly |
| Kalshi prediction markets | Hourly (at :45) |
| Polymarket prediction markets | Hourly (at :15) |
| Prediction market live game polling | Every 2 minutes |
| ESPN live sync | 60 seconds |
| Roster sync (ESPN + MLB Stats API) | Daily (7:00 AM UTC) |

### Data Retention

| Data Type | Strategy | Status |
|-----------|----------|--------|
| Raw odds snapshots | Lossless dedup (write-time + retroactive collapse) | ✅ Implemented |
| Win probability snapshots | Lossless dedup (write-time + retroactive collapse) | ✅ Implemented |
| Futures odds snapshots | Lossless dedup (write-time + retroactive collapse) | ✅ Implemented |
| Aggregated data | Indefinite | OK |
| Event metadata | Indefinite | OK |
| Futures history | Indefinite | OK |

**How lossless dedup works:**
- **Write-time**: Before inserting a new snapshot, check last row per (event, bookmaker/source). If value unchanged, bump `reading_count` and update `valid_until` instead of inserting.
- **Retroactive collapse**: Celery task `collapse_snapshots` merges consecutive identical rows into single rows with `captured_at` (first seen) and `valid_until` (last confirmed). Runs daily.
- **Lossless**: Original time series is fully reconstructable from the collapsed data.

**Remaining retention work (if needed):**
- [ ] Pre-game snapshot thinning (keep 1/hour instead of every poll)
- [ ] Aggregate completed games into `odds_aggregated`, then delete raw rows
- [ ] Cap futures snapshot retention post-resolution

---

## Authentication Philosophy

- **No required sign-in** — Logged-out experience must feel complete
- Auth exists to unlock: Favorites sync, pin sync, notification controls, cross-device preferences
- Auth is **pull-based, not forced**

**Current Implementation (Phase 1):**
- Google Sign-In via Google Identity Services (GIS)
- Safari compatibility via backend custom token exchange (bypasses ITP)
- Pin migration from localStorage to server on first login
- Requires `FIREBASE_SERVICE_ACCOUNT_JSON` for Safari support

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

Bain Luck displays information, not transactions.

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

## Development Priorities (March 2026)

### Active — Infrastructure & Reliability
These are the current focus. Resist the urge to build new features until these are addressed.

1. ✅ **Reduce stat model dependency on ESPN name matching** — Shipped. Three-pronged fix: multi-signal ESPN matching, wall-clock time estimation fallback, odds polling stat model path relaxed.
2. ✅ **Data retention / worker memory (R14 OOM)** — Shipped. Snapshot collapse rewritten to pure SQL. Phase 2 opportunities remain.
3. ✅ **Monitoring and reliability** — Shipped. Task-level success metrics system with dashboard.

### Shipped — Features

4. ✅ **Auth & Personalization** — All 3 phases shipped: Google Sign-In (Safari compatible), 5-step onboarding, personalized feed scoring with team/rival/sport multipliers.
5. ✅ **Ranking Level 2** — Time-series aware scoring with volatility, lead changes, momentum.
6. ✅ **Anonymous feed ranking overhaul** — 4-tier league system (~70 entries), event importance scoring (championship/playoff/exhibition), Pulse boost for finished events.
7. ✅ **MLB Stats API integration** — Live baseball win probability from official MLB API.
8. ✅ **Prediction market → event matching** — Two-pass strategy, 291 tests, ticker abbreviation parsing, both-teams gate, sport scoring, Polymarket CLOB backfill.
9. ✅ **Typeahead search** — SearchBar component with debounce, keyboard nav, layout header integration.
10. ✅ **"Market Was Wrong"** — Post-game championship odds shifts page.
11. ✅ **"Why Did the Line Move?"** — ESPN context enrichment (injuries, news, game state) + LLM explanation.
12. ✅ **Related futures Phase 4** — LLM "Bigger Picture" summary on related-futures endpoint.
13. ✅ **Oscars landing page** — 24 award categories, cross-source odds, TMDB enrichment.
14. ✅ **Event importance scoring** — ESPN season type parsing, championship/playoff/exhibition weights.
15. ✅ **Roster sync migration** — SportsDataIO deleted, ESPN + MLB Stats API is primary.
16. ✅ **Feed UX overhaul** — Sectioned feed (Live Now → Just Happened → Upcoming → Top Markets), non-repetitive reason text, finished event expected-vs-actual design.
17. ✅ **Divergence badge** — Prediction market vs sportsbook divergence detection (>5% threshold).
18. ✅ **Canonical identity migration** — Consolidated sport key translations (`sport_keys.py`), `TeamIdentityService` with 5-step resolution cascade, `team_identity_mapping` table, StatPal schedule-first event creation, 6 consumer modules integrated.

### Next — Features (in priority order)

19. ✅ **Apple Sign-In** — Firebase `signInWithPopup` with `OAuthProvider('apple.com')`. Provider chooser dropdown (Google + Apple). 13 backend tests. Remaining: Firebase support email, GA cross-platform.
20. ✅ **iOS App Phases 1-7** — Native SwiftUI app shipped: section-based feed, multi-source odds chart with period markers, event detail (chart, related futures, line movement, scoring plays), search, EI rankings, Apple + Google Sign-In, native onboarding, preferences, iPad sidebar layout, category pages, filter chips, swipe-to-pin, haptic feedback, Firebase Analytics, deep linking. 46 Swift files, 29 commits. Remaining: share extension, background refresh, widgets, App Store submission.
21. ✅ **Golf landing page** — Bespoke category page at `/categories/golf` with cross-source tournament odds aggregation, current event detection, 24h movers, sparkline charts. Generic `/categories/[slug]` infrastructure also built.
22. ✅ **Odds chart redesign** — Period markers, auto-zoom Y-axis, smart start time, team color labels, compact score diff. Applied to web + iOS.
23. ✅ **EI calibration** — Scaling constant tuned from 8.0 → 2.5, time normalization cap at 2.0x, diagnosis endpoint.
24. ✅ **Duplicate event handling** — 3-layer prevention + admin merge cleanup (5,735 orphans removed).
25. ✅ **Graduated live scoring + championship stakes** — Graduated live scoring (35/30/20 by closeness), championship odds multiplicative boost.
26. ✅ **ESPN box scores + live stat prop tracking** — Box score JSONB column, stat prop pace projections on iOS.
27. ✅ **Odds API quota monitoring** — Passive header capture, daily-activity inference, admin dashboard.
28. **Sport-specific EI normalization** — Different sports have different baseline volatility.
29. **Related futures Phase 5** — Bidirectional linking: futures detail pages show relevant events.
30. **Additional win prob sources** — MoneyPuck for NHL. Infrastructure ready (stub configured).

### Later (Q2-Q4 2026)
- iOS app: App Store submission, widgets, background refresh, share extension
- **TV Mode v2** — Fullscreen second-screen experience at `/tv`. Design complete, interactive prototype built. See `docs/tv-mode-plan.md`.
- Additional bespoke category pages (basketball, football, soccer, politics, entertainment)
- Advanced notification preferences
- "The Market Was Wrong" v2 — AI narrative generation + personalization
- Non-sports category display enhancements in frontend

### Exploring (No Timeline)
- Probability Comparisons ("Comparable Odds") — Phase 16
- Event Similarity Scores — Phase 17
- Team Insights (LLM-Powered Personalized Feed) — Phase 19
- AI-Native Sports Intelligence features — Horizon section

---

## Completed Features (March 2026)

<details>
<summary>All shipped features (click to expand)</summary>

- Pulse feature complete and deployed (algorithm, badges, tooltips, percentile scoring, Hall of Fame)
- Kalshi prediction market integration (polling, rate limiting, category filtering)
- Futures markets with smart categorization (90+ regex patterns, 23 categories, LLM fallback)
- LLM infrastructure (OpenAI GPT-4o-mini for classification, caching, admin endpoints)
- Pinned Events & Futures (localStorage + server-backed for authenticated users)
- Sentry error tracking (FastAPI + Celery worker)
- Multi-source win probability infrastructure (generic table, source registry, N-source chart)
- Bain Luck statistical win probability model (nflfastR-inspired, 6 sports)
- Win probability source detail page (`/events/[id]/models`)
- ESPN integration (team colors/logos, live game data, win probability, venues, alternate names, records)
- ESPN team name matching normalization (unicode/accent handling for college teams)
- ESPN commence_time correction (fixes wrong UTC times from The Odds API)
- Status-based probability display (opening odds for finished games, current odds for live)
- Stale bookmaker filter (`app/utils/odds_filtering.py`, 14 regression tests)
- Opening odds tracking (last pregame consensus, continuously updated while scheduled)
- Snapshot data retention (lossless collapsing + write-time dedup + pure SQL rewrite for constant memory)
- Tasks package refactor (monolithic `tasks.py` -> 14-module `tasks/` package)
- Super Bowl dead code cleanup (~7K+ lines removed)
- Related futures Phases 1-3 (team linking, endpoint, "Bigger Picture" UI)
- SportsDataIO integration (API client, roster sync) — later migrated to ESPN + MLB Stats API; `sportsdata_api.py` deleted
- Polymarket integration Phase 1 (API client, polling task, 160+ tag-to-category mapping, streaming pagination)
- Prediction market → event matching (two-pass strategy, 291 tests, ticker parsing, ticker abbreviation extraction, ticker fragment matching, sport+time fallback, both-teams gate, sport scoring, prop/spread filter)
- Firebase Auth Phase 1 (Google Sign-In, Safari fallback, pin sync, auth context)
- Auth & Personalization Phase 2 (5-step onboarding: location, follow, alma maters, sports+beyond, rivals)
- Auth & Personalization Phase 3 (personalized feed scoring, rival multipliers, unified interestingness feed)
- Unified feed (homepage redesigned to single "Right Now" feed ranked by interestingness)
- Team auto-creation from events (event discovery + search fallback auto-create Team records)
- Non-sports categories in onboarding (politics, entertainment, crypto, economics, tech, weather, geopolitics, culture)
- Ranking Level 2 (time-series aware scoring with volatility, lead changes, momentum)
- 4-tier league ranking system (30+ leagues mapped, 4-tier multiplier system)
- MLB Stats API integration (live baseball win probability, free API)
- Divergence badge for prediction market discrepancy detection (>5% threshold, purple/blue coloring)
- Safari 3-tier auth fallback (Firebase credential → custom token → PyJWT session token)
- Non-sports tier promotion (Politics, Entertainment, Crypto moved to tier 2)
- Polymarket Phase 2 (beat schedule, price history backfill, live game polling every 2 min)
- Celery heartbeat + health endpoint + task-level success metrics
- Google Analytics 4 integration
- Typeahead search (SearchBar component, debounce, keyboard nav, layout header integration, typeahead API endpoint)
- "Market Was Wrong" page (post-game championship odds shifts, market_moves.py endpoint)
- Kalshi ticker abbreviation parsing (extract_teams_from_ticker, 100+ abbreviations, solves generic-named market matching)
- Onboarding UX fixes (sport labels, duplicate category fix, session TTL 8hrs, same-name team clickability)
- Feed quality improvements (raised thresholds, diversity cap, non-sports tier promotion)
- Test coverage (1667+ total: 1550+ backend + 117+ frontend across 24+ test files)
- My Stuff / Preferences restructure: `/my-stuff` rewritten from preferences editor to team-filtered feed (3 states: sign-in prompt, onboarding prompt, team feed). Preferences editor moved to `/preferences`. Backend `my_teams_only` param on `/api/feed` with wider time windows (24h/7d), team filtering, no min score, no diversity enforcement. UserMenu "Preferences" links to `/preferences`.
- Oscars landing page: `/oscars` with 24 award categories, cross-source odds aggregation (Polymarket + Kalshi), TMDB movie posters/headshots, ceremony countdown, gold-themed design. Backend `GET /api/oscars` with diacritics dedup, Kalshi 0.5 noise filter, probability normalization.
- Event importance scoring + ESPN season type: `compute_highlight()` reads `llm_importance` with championship (+25), playoff (+15), exhibition (-20) weights. ESPN sync parses `season.type`. Tennis Grand Slams and golf Majors promoted to tier 2. 17 new tests.
- Roster sync SportsDataIO → ESPN migration: Deleted `sportsdata_api.py` (321 lines). `roster_sync.py` uses ESPN + MLB Stats API. `SPORTSDATA_API_KEY` no longer needed.
- "Why Did the Line Move?" ESPN context enrichment: `get_event_context()` in `espn_api.py` (injuries + news), enriched LLM prompt with real data + game state. 26 line movement tests + 8 ESPN parsing tests.
- Related futures Phase 4 — LLM "Bigger Picture" summary: GPT-4o-mini generates 2-3 sentence casual summary, cached in `LineMovementAnalysis` with 2h TTL. Frontend summary-first collapsed design.
- Feed UX overhaul: Sectioned feed (Live Now → Just Happened → Upcoming → Top Markets), non-repetitive reason text in `feed_reasons.py`, finished event expected-vs-actual design (opening odds bar + score with winner bolded + date/time), "Nah" hard filter, "If it's wild" higher bar (min_score 55).
- League tier expansion: ~70 league entries, Tier 3 (-5 pts), Tier 4 (-45 pts), regular tennis demoted to Tier 4, Pulse boost (+10) for finished events with high Pulse scores.
- Canonical identity migration: Consolidated 10 sport key translation dicts into `sport_keys.py` (7 accessor functions, zero codebase imports). Built `TeamIdentityService` with 5-step resolution cascade and `team_identity_mapping` table. StatPal schedule-first event creation (`statpal_fixture_id`, `commence_time_source`). Integrated into 6 consumer modules (espn_sync, statpal_sync, sports, roster_sync, prediction_market_matching, team_linking) as supplement to existing fuzzy matching. Backfill task for one-time population from ESPN IDs, team names, and Kalshi abbreviations. 6 admin endpoints.
- iOS App Phases 1-7 (Feb-Mar 2026): Native SwiftUI app — section-based feed, multi-source odds chart with period markers, event detail (chart, related futures, line movement, scoring plays), search, EI rankings, Apple + Google Sign-In, native onboarding, preferences, iPad-native sidebar layout, category pages, filter chips, swipe-to-pin, haptic feedback, Firebase Analytics, deep linking. 46 Swift files, 29 commits across 7 phases.
- Golf landing page (Mar 2026): Bespoke category page at `/categories/golf` — cross-source tournament odds aggregation, current event detection, 24h movers, sparkline charts, LPGA/TGL separation, non-golf false positive regex filter, StatPal PGA schedule enrichment. Generic `/categories/[slug]` infrastructure also built. 12 commits.
- Odds chart redesign (Feb-Mar 2026): Period markers at game boundaries (ESPN data, gap-filling), auto-zoom Y-axis (±5% padding), smart start time (skips flat pre-game data), team color labels, compact score diff below chart. Applied to both web (`OddsChart.tsx`) and iOS (`OddsChartView.swift`). 8 commits.
- EI calibration (Feb-Mar 2026): Scaling constant iteratively tuned 8.0 → 4.0 → 2.5. Time normalization ratio capped at 2.0x. Added diagnosis endpoint. Fixed infinite recalculate loop. 10 commits.
- Duplicate event handling (Mar 2026): 3-layer prevention — debug logging in StatPal matching, `_find_existing_event_by_teams()` safety net in all event creation paths, admin merge endpoint. Cleaned up 5,735 orphan events (54 StatPal-vs-Odds API + 5,681 StatPal-vs-StatPal duplicates). 10 commits.
- Graduated live scoring + championship stakes (Mar 2026): Replaced flat +30 live bonus with graduated scoring (35/30/20 by closeness). Championship stakes weighting gives multiplicative boost for teams with >10% title odds.
- ESPN box scores + live stat props (Mar 2026): Box score parsing from ESPN summary endpoint, stored as `Event.box_score_data` JSONB. iOS stat prop pace projections with semi-circular gauges.
- Odds API quota monitoring (Feb-Mar 2026): Passive header capture, Redis tracking, daily-activity inference, admin quota dashboard.
- ESPN proactive commence_time correction: Discovery cross-references ESPN schedule to correct Odds API time errors at insertion time.
- Search ranking improvements: Highlight score ranking for search results. LLM anti-speculation 3-tier prompt system.
- Feed resilience: Aggregate probability fallback, resolved futures filter, "No odds yet" placeholder, My Stuff soonest-first sorting, reserve team match filtering.
- Matching quality audits: Three daily LLM-based audits (canonical key dedup, prediction market→event links, related futures coverage). Pattern aggregation endpoint for systematic rule improvement. 22 tests. ~$0.02/day.
- Pulse → Excitement Index (EI) migration: Standard GEI formula replaces proprietary Pulse metric. 30s time bucket aggregation, regulation time normalization per sport. DB columns renamed. 80+ tests.
</details>

---

## Open Questions

1. **iOS widget strategy**: Which widgets provide most value? Lock screen vs home screen?

2. **LLM cost management**: How to balance explanation quality with API costs? (Current: ~$5/mo with caching)

3. **Futures update frequency**: Daily enough? Or should we poll more during playoffs/key events? (Currently hourly from The Odds API)

4. **Auth conversion**: What's the right moment to prompt for sign-in without being annoying? (Currently: only on explicit "Sign In" tap)

5. ~~**Stat model ESPN dependency**~~: Resolved — three-pronged fallback: ESPN ID → name → commence_time proximity, plus wall-clock time estimation when ESPN sync misses entirely.

These are product experiments, not blockers.

---

## Final Note

This product wins not by being smarter than users, but by being **clearer than everything else**.

If Bain Luck succeeds, users won't say:
> "This helped me bet."

They'll say:
> "I finally understood what was happening."
