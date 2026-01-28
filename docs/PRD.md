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
      │  (React)  │      │ (SwiftUI) │      │   (iOS)   │
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

-- Tournaments/Championships
CREATE TABLE tournaments (
    id SERIAL PRIMARY KEY,
    sport_id INTEGER REFERENCES sports(id),
    name VARCHAR(200) NOT NULL,
    year INTEGER,
    status VARCHAR(20) DEFAULT 'active'
);

CREATE TABLE tournament_odds (
    id SERIAL PRIMARY KEY,
    tournament_id INTEGER REFERENCES tournaments(id),
    team_id INTEGER REFERENCES teams(id),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    odds INTEGER,
    win_probability DECIMAL(5,4)
);
```

### Indexes

```sql
CREATE INDEX idx_odds_snapshots_event ON odds_snapshots(event_id);
CREATE INDEX idx_odds_snapshots_captured ON odds_snapshots(captured_at);
CREATE INDEX idx_events_commence ON events(commence_time);
CREATE INDEX idx_events_status ON events(status);
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

### Game Excitement Index (GEI)

Based on Luke Benz's methodology:

```python
def calculate_gei(home_prob: float, over_under: float, sport: str) -> float:
    """
    Calculate Game Excitement Index.
    
    Higher when:
    - Game is close (probabilities near 50/50)
    - Expected to be high-scoring
    
    Reference: https://lukebenz.com/post/gei/
    
    Note: Experimental feature. Used as a sorting/discovery signal,
    not core to product identity.
    """
    # Closeness factor: peaks at 0.5, drops toward 0 or 1
    closeness = 1 - abs(home_prob - 0.5) * 2
    
    # Normalize over/under by sport average
    sport_avg_totals = {
        'basketball_nba': 220,
        'football_nfl': 45,
        'baseball_mlb': 8.5,
        'hockey_nhl': 6,
    }
    avg_total = sport_avg_totals.get(sport, 100)
    scoring_factor = over_under / avg_total
    
    # GEI formula (simplified)
    gei = closeness * 0.6 + scoring_factor * 0.4
    
    return round(gei * 100, 1)  # Scale to 0-100
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
```

---

## Feature Phases

### Phase 1: MVP ✅ Complete
**Core visualization shipped to production.**

- [x] Project setup and CI/CD
- [x] Database schema and migrations
- [x] Odds API integration
- [x] Live win probability (%)
- [x] Web-first, mobile-optimized UI
- [x] Auto-refresh (every 30 seconds)
- [ ] Odds movement chart (pre-game → now)
- [ ] Live update state indicators (pausing states, blowout detection)

### Phase 2: Personalization (In Progress)
- [x] Sorting by closeness (Closest Odds)
- [x] Sorting by game time
- [ ] Favorite teams (local storage first)
- [ ] Firebase Auth integration (pull-based, not forced)
- [ ] Persist favorites to database

### Phase 3: Context & Polish
- [ ] Projected final scores (clearly labeled as illustrative)
- [ ] Basic explanations for large probability swings
- [ ] Game Excitement Index (experimental, for sorting/discovery)
- [ ] Shareable web links with app promo banner
- [ ] Tournament/championship tracking

### Phase 4: iOS App
- [ ] SwiftUI app shell with parity to web
- [ ] Second-screen optimized UI
- [ ] Favorites and sorting
- [ ] Share extension
- [ ] Widgets (read-only)

### Phase 5: Advanced
- [ ] Push notifications for major probability swings
- [ ] LLM-powered swing summaries

---

## Supported Sports (Initial)

| Sport | API Key | Priority |
|-------|---------|----------|
| NFL | `americanfootball_nfl` | High |
| NBA | `basketball_nba` | High |
| MLB | `baseball_mlb` | High |
| NHL | `icehockey_nhl` | Medium |
| College Football | `americanfootball_ncaaf` | Medium |
| College Basketball | `basketball_ncaab` | Medium |
| Golf (Majors) | `golf_masters_winner` etc. | Low |
| Tennis (Majors) | `tennis_atp_*` | Low |

---

## Configuration

### Polling Strategy

| Scenario | Interval |
|----------|----------|
| No live games | Every 15 minutes |
| Games today | Every 5 minutes |
| Live games | Every 1 minute |

### Data Retention

| Data Type | Retention |
|-----------|-----------|
| Raw snapshots | 7 days after event completion |
| Aggregated data | Indefinite |
| Event metadata | Indefinite |

---

## Authentication Philosophy

- **No required sign-in** — Logged-out experience must feel complete
- Auth exists to unlock: Favorites, Notification controls, Future premium features
- Auth is **pull-based, not forced**

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

**No constant pings. Silence is a feature.**

---

## Monetization (Future-Compatible, Not MVP)

### Long-Term Options
- Display ads (carefully placed, non-intrusive)
- Premium tier (e.g., ad-free, deeper history, advanced alerts)

### Explicitly Excluded
- Selling picks
- Aggressive affiliate betting funnels

Monetization must not distort trust or clarity.

---

## Legal & Compliance

- Neutral, compliant stance
- No state-specific betting actions
- No calls to action to place bets

OddsTracker displays information, not transactions.

---

## Success Metrics

### Product Metrics
- % of sessions during live games
- Repeat opens during a single game
- Time spent on event view

### Technical Metrics
- **Reliability**: 99.9% uptime for API
- **Freshness**: Odds updated within 2 minutes of source
- **Performance**: API response time < 200ms p95

### Trust Metrics
- Low notification opt-out rates
- Low bounce rate during paused states

---

## Open Questions

1. **Swing thresholds**: What threshold defines a "meaningful" probability swing worth surfacing?

2. **Automatic context**: How much automatic explanation is helpful vs noisy?

3. **Auth trigger**: Which features require sign-in?
   - Favorites beyond X teams?
   - Notifications?
   - Historical data beyond 24 hours?

4. **Replay mode**: Should post-game replay mode exist to review how odds evolved?

5. **Legal**: Sports betting display regulations by state?

These are product experiments, not blockers.

---

## Final Note

This product wins not by being smarter than users, but by being **clearer than everything else**.

If OddsTracker succeeds, users won't say:
> "This helped me bet."

They'll say:
> "I finally understood what was happening."
