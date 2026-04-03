# Prompt 4: Futures Grouping System

**Terminal:** 4 (run AFTER Prompt 1 completes — depends on group_id schema)
**Estimated time:** 4-5 hours
**Risk level:** Low-Medium (mostly new code, but touches ingestion tasks)
**Depends on:** Prompt 1 Step 4 (group_id column must exist)

---

## Copy this entire prompt into Claude Code CLI:

```
I need you to build an intelligent futures grouping system that links related markets together. Read docs/architecture-improvement-plan.md first for full context.

PREREQUISITE: The group_id, group_type, and group_position columns must already exist on FuturesMarket (added in Prompt 1 Step 4). Verify:
  grep "group_id" backend/app/models/models.py

If the columns don't exist yet, stop and tell me.

## Step 1: Recover Polymarket NegRisk hierarchy

Read backend/app/tasks/polymarket.py to understand how Polymarket events are ingested.

Polymarket's API returns an event structure where one "event" contains multiple "markets" (binary outcomes). For NegRisk events, these markets are mutually exclusive alternatives (e.g., "Temperature 70-79°F" vs "Temperature 80°F+").

Currently, each market becomes a separate FuturesMarket row, losing the parent event relationship.

Fix: In the ingestion loop where FuturesMarket rows are created/updated:
1. If the Polymarket event has neg_risk=True OR contains more than 1 market, set:
   - group_id = f"polymarket:{polymarket_event_id}"
   - group_type = "negrisk" if neg_risk else "polymarket_event"
   - group_position = index of the market within the event (0, 1, 2, ...)
2. Store the Polymarket event_id in market_metadata JSONB field (if not already there)

Also read the Polymarket event title — if the event itself has a descriptive title (like "What will the high temperature be in SF?"), store it in market_metadata as "event_title" so we can display it as the group header.

Write tests in backend/tests/test_futures_grouping.py for this logic.

Run: cd backend && python -m pytest tests/ -v

## Step 2: Recover Kalshi event hierarchy

Read backend/app/tasks/kalshi.py to understand how Kalshi events are ingested.

Kalshi has an event-market hierarchy where each event (series) contains multiple markets. The event ticker links them. For example:
- Event ticker: "KXNBAGAME-26FEB21DETCHI"
- Market tickers: "KXNBAGAME-26FEB21DETCHI-M1", "KXNBAGAME-26FEB21DETCHI-M2", etc.

Read backend/app/routes/futures.py for the existing _extract_kalshi_suffix() helper — this function already parses Kalshi tickers to group related markets.

Fix: In the Kalshi ingestion loop:
1. Extract the event ticker from each market's data
2. Set group_id = f"kalshi:{event_ticker}"
3. Set group_type = "kalshi_event"
4. If the Kalshi event has a descriptive title, store as market_metadata["event_title"]

Add to existing tests.

Run: cd backend && python -m pytest tests/ -v

## Step 3: Create canonical key grouping

For markets from different sources (Odds API, Kalshi, Polymarket) that share the same canonical_market_key, create a group.

Create backend/app/utils/market_grouping.py:

```python
"""Market grouping utilities.

Groups related futures markets by:
1. Source hierarchy (Polymarket NegRisk, Kalshi events) — set during ingestion
2. Canonical key (cross-source same market) — computed here
3. Threshold variants (sequential numeric ranges) — computed here
4. Tournament progression (sport stages) — already exists in tournament_stages.py
"""

def compute_canonical_groups(session) -> dict:
    """Find markets sharing a canonical_market_key and set group_id.

    Returns: {canonical_key: [market_ids]}
    """
    pass

def detect_threshold_groups(markets: list) -> list:
    """Detect markets that differ only by numeric threshold.

    Strategy:
    1. Extract numeric values from outcome names
    2. Group outcomes by non-numeric name parts
    3. If group has 3+ outcomes with sequential/overlapping numbers, it's a threshold group

    Examples that should group:
    - "Under 50°F", "50-59°F", "60-69°F", "70-79°F", "80°F+" → temperature range
    - "0-24 points", "25-34 points", "35-44 points", "45+ points" → stat line
    - "Round 1", "Round 2", "Round 3", "Round 4+" → tournament round
    """
    pass
```

Implement both functions. The canonical_groups function should:
- Query FuturesMarket where canonical_market_key IS NOT NULL
- Group by canonical_market_key
- For groups with 2+ markets, set group_id = f"canonical:{canonical_market_key}"
- Set group_type = "canonical"

The threshold detection should:
- Extract numeric patterns from outcome names using regex
- Normalize the non-numeric parts (e.g., "Under ___°F" as a template)
- Group outcomes with the same template
- Only create a group if there are 3+ threshold variants
- Set group_id = f"threshold:{market_id}:{template_hash}"

Write comprehensive tests (at least 15 tests):
- Canonical key grouping with 2 sources → group created
- Canonical key grouping with 1 source → no group
- Temperature range detection → grouped
- Score range detection → grouped
- Non-numeric outcomes → not grouped
- Mixed numeric/non-numeric → only numeric grouped
- Edge case: "Round 1" vs "1st Round" (different format, same meaning)

Run: cd backend && python -m pytest tests/test_futures_grouping.py -v

## Step 4: Create grouping API endpoint

Add to backend/app/routes/futures.py:

GET /api/futures/groups/{group_id}
  - Returns all markets in the group with their outcomes
  - Includes group metadata (type, display title, total markets)

Response format:
{
  "group_id": "polymarket:12345",
  "group_type": "negrisk",
  "display_title": "What will the high temperature be in San Francisco?",
  "total_markets": 5,
  "markets": [
    {
      "market_id": 100,
      "name": "Under 50°F",
      "position": 0,
      "outcomes": [
        {"name": "Yes", "probability": 0.15},
        {"name": "No", "probability": 0.85}
      ]
    },
    ...
  ]
}

GET /api/futures/groups?type={negrisk|kalshi_event|canonical|threshold}&limit=20
  - List all groups of a given type
  - Returns group_id, type, display_title, market_count

Write tests for both endpoints.

## Step 5: Create frontend display components

Create three new components. Import design tokens and animations from the files created in Prompt 2.

### frontend/components/ThresholdGrid.tsx

Displays a horizontal grid of mutually exclusive options with probabilities.
For temperature ranges, score lines, etc.

```
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│  <50°F   │  50-59°  │  60-69°  │  70-79°  │   80°+   │
│   15%    │   28%    │   32%    │   20%    │    5%    │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

- Each cell shows outcome name + probability
- Cell background color intensity proportional to probability (higher = more vivid)
- Responsive: horizontal scroll on mobile if >4 items
- Highlight the most likely outcome
- Props: group data from the API endpoint

### frontend/components/ProgressionTable.tsx

Displays a table of participants across tournament stages.
This component consumes the existing GET /api/futures/{market_id}/progression endpoint.

```
Participant    | Make Cut | Top 20 | Top 10 | Win
─────────────────────────────────────────────────
Scheffler      |   92%    |  70%   |  45%   |  8%
McIlroy        |   88%    |  60%   |  35%   |  6%
```

- Rows = participants (sorted by win probability descending)
- Columns = tournament stages (from progression endpoint)
- Cell color intensity proportional to probability
- Limit to top 10 participants by default, expandable
- Props: progression data from the API

### frontend/components/CombinedMarketCard.tsx

Displays multiple related markets from the same event in one card.
For Kalshi game-level events with moneyline + spread + total.

```
┌─────────────────────────────────────────────┐
│  Pistons vs Celtics — Tonight 7:30 PM       │
│                                              │
│  Moneyline   Pistons 47%  │  Celtics 57%    │
│  Spread      +3.5   46%   │  -3.5    53%    │
│  Total       O 215.5 48%  │  U 215.5 52%    │
└─────────────────────────────────────────────┘
```

- Card header shows event title (from market_metadata.event_title)
- Each row is a market within the group
- Two-column layout: home/away or yes/no
- Props: group data from the API

All three components should:
- Use shadcn/ui Card as the container (if installed)
- Use design tokens for colors and spacing
- Use Framer Motion fadeIn for initial render
- Be responsive (stack vertically on mobile)
- Include TypeScript types for their props

Build the frontend: cd frontend && npm run build

## Step 6: Create admin backfill endpoint

Add to backend/app/routes/admin.py:

POST /api/admin/futures/groups/discover?secret=xxx
  - Runs all grouping algorithms:
    1. Canonical key grouping
    2. Threshold variant detection
  - Returns stats: { canonical_groups_created, threshold_groups_created, markets_updated }

This is for backfilling existing markets. New markets get group_id set during ingestion (Steps 1-2).

## Final verification

Run all backend tests: cd backend && python -m pytest tests/ -v
Run frontend build: cd frontend && npm run build

Report results.
Do NOT commit — I will review and commit manually.
```
