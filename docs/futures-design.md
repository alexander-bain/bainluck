# Futures Markets Design

## Overview

This document outlines the design for supporting futures/outright markets from multiple sources (The Odds API, Kalshi) in OddsTracker.

## Event Types

### Current: Head-to-Head (H2H)
```
Team A (52%) vs Team B (48%)
├── Two contestants
├── Probabilities sum to ~100%
└── Sources: The Odds API (h2h markets)
```

### New: Outright/Futures
```
"Who will win the Super Bowl?"
├── Many contestants (2-50+)
├── Each has independent probability
├── Probabilities sum to ~100%
└── Sources: The Odds API (outrights), Kalshi (multi-outcome)
```

### New: Binary
```
"Will inflation exceed 3% in Q2?"
├── Yes (65%) / No (35%)
├── Essentially h2h with Yes/No as "teams"
└── Sources: Kalshi (most events)
```

## Data Model

### Option A: Unified Model (Recommended)

Extend the existing Event model with a type field and add an Outcome model:

```python
# models.py additions

class Event:
    # Existing fields...
    id: int
    external_id: str
    sport_id: int
    status: str  # scheduled, live, completed, closed
    commence_time: datetime

    # NEW: Event type
    event_type: str  # "h2h" | "outright" | "binary"

    # For h2h events (existing)
    home_team_name: str | None
    away_team_name: str | None
    home_score: int | None
    away_score: int | None

    # For outright/binary events (NEW)
    title: str | None  # "Super Bowl Winner", "Will BTC hit $100k?"
    description: str | None
    resolution_date: datetime | None  # When market resolves

    # Data source tracking (NEW)
    source: str  # "the_odds_api" | "kalshi"
    source_event_id: str | None  # Original ID from source


class Outcome:
    """Individual outcome/contestant in a futures market."""
    id: int
    event_id: int  # FK to Event

    name: str  # "Kansas City Chiefs", "Yes", "Patrick Mahomes"
    description: str | None

    # Current odds
    probability: Decimal | None  # 0.0-1.0
    american_odds: int | None  # +150, -200

    # Tracking
    source: str  # "the_odds_api" | "kalshi"
    captured_at: datetime

    # For ranking/display
    rank: int | None  # 1 = favorite
    is_winner: bool = False  # Set when resolved


class OutcomeSnapshot:
    """Historical odds for an outcome (like OddsSnapshot for h2h)."""
    id: int
    outcome_id: int  # FK to Outcome

    probability: Decimal
    american_odds: int | None

    captured_at: datetime
    valid_until: datetime | None
    reading_count: int = 1

    bookmaker: str | None  # For odds API sources
```

### Option B: Separate Futures Model

Keep Event for h2h only, create FuturesEvent for outrights:

```python
class FuturesEvent:
    id: int
    external_id: str
    source: str

    title: str
    description: str | None
    category: str  # "sports", "politics", "economics", "entertainment"
    subcategory: str | None  # "nfl", "presidential", "inflation"

    status: str
    resolution_date: datetime | None

    outcomes: List[FuturesOutcome]
```

**Recommendation:** Option A (Unified) is better because:
- Simpler queries and API responses
- Shared infrastructure (polling, caching, history)
- Easier to display mixed results
- Binary events map cleanly to h2h structure

## Source Integration

### The Odds API - Outrights

The Odds API returns outrights in a different format than h2h:

```json
// GET /v4/sports/{sport}/odds?markets=outrights
{
  "id": "a1b2c3d4",
  "sport_key": "americanfootball_nfl",
  "sport_title": "NFL",
  "commence_time": "2025-02-09T23:30:00Z",
  "home_team": null,  // No home/away for outrights
  "away_team": null,
  "bookmakers": [{
    "key": "draftkings",
    "markets": [{
      "key": "outrights",
      "outcomes": [
        {"name": "Kansas City Chiefs", "price": 450},
        {"name": "Philadelphia Eagles", "price": 600},
        {"name": "Buffalo Bills", "price": 700},
        // ... 29 more teams
      ]
    }]
  }]
}
```

**Mapping:**
- `event_type` = "outright"
- `title` = "{sport_title} Winner" or from API
- `source` = "the_odds_api"
- Create Outcome for each item in `outcomes[]`

### Kalshi API

Kalshi events are structured differently:

```json
// GET /trade-api/v2/markets
{
  "ticker": "INFL-25Q2-T3",
  "title": "Inflation above 3% in Q2 2025?",
  "subtitle": "Based on CPI data",
  "status": "active",
  "close_time": "2025-07-15T16:00:00Z",
  "yes_bid": 0.65,
  "yes_ask": 0.67,
  "no_bid": 0.33,
  "no_ask": 0.35,
  "category": "Economics",
  "result": null  // "yes" | "no" when resolved
}
```

**Mapping for Binary:**
- `event_type` = "binary"
- `title` = Kalshi's `title`
- `home_team_name` = "Yes"
- `away_team_name` = "No"
- Use existing h2h flow with probabilities from yes_bid/yes_ask

**Mapping for Multi-Outcome:**
Some Kalshi markets have multiple outcomes (e.g., "Which party wins?"):
- `event_type` = "outright"
- Create Outcome for each choice

## API Design

### Events Endpoint Changes

```
GET /api/events
  ?type=h2h|outright|binary|all (default: all)
  ?source=the_odds_api|kalshi|all (default: all)
  ?category=sports|politics|economics|all (default: all)
```

Response includes event_type to help frontend render correctly:

```json
{
  "events": [
    {
      "id": 123,
      "event_type": "h2h",
      "home_team": "Lakers",
      "away_team": "Celtics",
      "current_odds": {...}
    },
    {
      "id": 456,
      "event_type": "outright",
      "title": "Super Bowl Winner",
      "outcomes": [
        {"name": "Chiefs", "probability": 0.22, "rank": 1},
        {"name": "Eagles", "probability": 0.15, "rank": 2},
        // Top 10 only in list view
      ],
      "total_outcomes": 32
    },
    {
      "id": 789,
      "event_type": "binary",
      "title": "Will BTC hit $100k by June?",
      "home_team": "Yes",
      "away_team": "No",
      "current_odds": {
        "home_probability": 0.45,
        "away_probability": 0.55
      }
    }
  ]
}
```

### New Endpoint: Outcome Details

```
GET /api/events/{event_id}/outcomes
  ?limit=50 (default: 10)
```

Returns all outcomes for an outright event with full history.

## Frontend Components

### FuturesCard Component

For outright events on the home page:

```
┌─────────────────────────────────────┐
│ 🏈 NFL          Super Bowl Winner   │
│                                     │
│  1. Chiefs           22%  ████████░░│
│  2. Eagles           15%  █████░░░░░│
│  3. Bills            12%  ████░░░░░░│
│  4. Lions            10%  ███░░░░░░░│
│  5. 49ers             8%  ██░░░░░░░░│
│                                     │
│  +27 more · Resolves Feb 9          │
└─────────────────────────────────────┘
```

### BinaryCard Component (or reuse EventCard)

Binary events can use existing EventCard with minor tweaks:

```
┌─────────────────────────────────────┐
│ 🗳️ Politics      Resolves Nov 5     │
│ Will Democrats win the presidency?  │
│                                     │
│  Yes                           62%  │
│  ████████████████████░░░░░░░░░░░░░░│
│  No                            38%  │
│                                     │
│  via Kalshi                         │
└─────────────────────────────────────┘
```

### FuturesDetail Page

Full page for viewing all outcomes:

```
Super Bowl LVIX Winner
Resolves: February 9, 2025 · 32 teams

┌──────────────────────────────────────────┐
│ Search teams...                     🔍   │
└──────────────────────────────────────────┘

│ Rank │ Team                  │ Prob  │ Trend │
│──────│───────────────────────│───────│───────│
│  1   │ Kansas City Chiefs    │  22%  │  ↑ 2% │
│  2   │ Philadelphia Eagles   │  15%  │  ↓ 1% │
│  3   │ Buffalo Bills         │  12%  │  ─    │
│  4   │ Detroit Lions         │  10%  │  ↑ 3% │
│  5   │ San Francisco 49ers   │   8%  │  ↓ 2% │
│ ...  │                       │       │       │

[Show probability trend chart for selected teams]
```

## Categories & Organization

### Sport Categories (The Odds API)
- Football: `americanfootball_nfl_super_bowl_winner`
- Basketball: `basketball_nba_championship_winner`
- Baseball: `baseball_mlb_world_series_winner`
- Golf: `golf_masters_tournament_winner`
- etc.

### Kalshi Categories
- Politics: Elections, legislation, appointments
- Economics: Inflation, Fed rates, GDP
- Entertainment: Awards, box office
- Science: Space launches, discoveries
- Weather: Temperature records, hurricanes
- Finance: Stock prices, crypto

### Frontend Category Display

```
Home Page Tabs:
[All] [Sports] [Politics] [Economics] [More ▼]

Or integrated with sport filter:
[🏆 All] [🏈 Football] [🏀 Basketball] [🗳️ Politics] [📈 Economics] [More ▼]
```

## Implementation Phases

### Phase 1: Data Model & Binary Events
1. Add `event_type`, `title`, `source` fields to Event
2. Map Kalshi binary events to existing h2h structure
3. Display with existing EventCard (minor tweaks)

### Phase 2: Outright Support
1. Create Outcome and OutcomeSnapshot models
2. Add polling for The Odds API outrights
3. Create FuturesCard component
4. Add /outcomes endpoint

### Phase 3: Kalshi Integration
1. Implement Kalshi API client
2. Add Kalshi poller
3. Support Kalshi multi-outcome markets
4. Add category filtering

### Phase 4: Enhanced Features
1. Outcome trend charts
2. Probability change alerts
3. "Watch" specific outcomes
4. Cross-source comparison

## Migration Path

1. **Database migration:**
   - Add `event_type` column (default "h2h")
   - Add `title`, `source`, `resolution_date` columns
   - Create Outcome table
   - Create OutcomeSnapshot table

2. **Backfill:**
   - Set all existing events to `event_type = "h2h"`
   - Set `source = "the_odds_api"`

3. **Frontend:**
   - EventCard checks `event_type` and renders accordingly
   - Add FuturesCard for outright events
   - Update home page to handle mixed event types

## Open Questions

1. **Polling frequency for futures?**
   - Futures change slowly, maybe poll every 30 min vs 30 sec for live

2. **How to handle outcome limit?**
   - Super Bowl has 32 teams, Masters has 100+ golfers
   - Show top 10 in list, full list on detail page?

3. **Kalshi API access?**
   - Need API key and understand rate limits
   - May need different polling strategy

4. **Category taxonomy?**
   - How to map The Odds API sports to Kalshi categories?
   - Unified category system or source-specific?
