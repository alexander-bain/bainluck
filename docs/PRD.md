# OddsTracker - Product Requirements Document

## Overview

OddsTracker is a sports betting odds visualization app that converts gambling odds into intuitive win probabilities, helping users understand the likelihood of outcomes without needing to interpret betting lines.

### Vision
Make sports betting odds accessible and understandable to everyone by translating complex betting lines into simple percentages and projected scores.

### Target Users
- Sports fans who want to understand game expectations
- Casual bettors seeking quick probability insights
- Fantasy sports players tracking matchup likelihoods

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

### Phase 1: MVP (Weeks 1-3)
- [x] Project setup and CI/CD
- [ ] Database schema and migrations
- [ ] Odds API integration
- [ ] Basic probability conversion
- [ ] Simple web UI showing live probabilities
- [ ] Historical odds chart per event

### Phase 2: Personalization (Weeks 4-5)
- [ ] Favorite teams (local storage first)
- [ ] Sorting options (alphabetical, by sport, by GEI)
- [ ] Firebase Auth integration
- [ ] Persist favorites to database

### Phase 3: Enhanced Features (Weeks 6-8)
- [ ] Projected final scores
- [ ] Game Excitement Index
- [ ] Tournament/championship tracking
- [ ] Shareable web links with app promo banner

### Phase 4: iOS App (Weeks 9-12)
- [ ] SwiftUI app shell
- [ ] API integration
- [ ] Favorites and sorting
- [ ] Share extension

### Phase 5: Advanced (Weeks 13+)
- [ ] Push notifications for probability swings
- [ ] iOS widgets
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

## Success Metrics

- **Reliability**: 99.9% uptime for API
- **Freshness**: Odds updated within 2 minutes of source
- **Performance**: API response time < 200ms p95
- **Engagement**: Daily active users, favorite teams per user

---

## Open Questions

1. **Auth trigger**: Which features require sign-in?
   - Favorites beyond X teams?
   - Notifications?
   - Historical data beyond 24 hours?

2. **Monetization**: Future consideration
   - Premium features?
   - Ad-supported free tier?

3. **Legal**: Sports betting display regulations by state?
