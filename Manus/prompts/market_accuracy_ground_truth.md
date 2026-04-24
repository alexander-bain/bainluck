# Market Accuracy Ground Truth — Monotonicity & Cross-Game Validation

## Goal

Verify that bainluck.com event detail pages show the **correct** markets for each game — no markets from other games leaking in, no stale data, and probabilities that are monotonically decreasing for totals/props.

This is a focused audit on data accuracy, not market discovery (that's covered by `event_matching_ground_truth.md`).

## Instructions

### Step 1: Pick 4 events to audit

Visit **bainluck.com/feed** and pick 4 events:
1. An **NBA playoff game** (tonight or most recent completed)
2. An **MLB game** (tonight or most recent completed)
3. A **second NBA or NHL game** from a different series/matchup
4. A **completed game** from today or yesterday (any sport)

For each, note:
- The bainluck event URL (e.g., `bainluck.com/events/14595395`)
- Teams playing
- Sport
- Status (scheduled / live / completed)

### Step 2: For each event — Audit the Projected Scoring section

On the bainluck event page, scroll to **"Projected scoring"** and **"Projected combined scoring"**:

1. Record every threshold and its probability (e.g., "200.5+ 84%, 203.5+ 77%, ...")
2. **Check monotonicity**: Does each row have a LOWER probability than the row above it? If any row has a HIGHER probability than the row above, flag it as a violation.
3. If there IS a violation, note:
   - Which threshold(s) violate
   - The probability values

### Step 3: For each event — Audit the Spread section

Scroll to the **"Spread"** section:

1. Are the outcomes grouped by period (Full Game / First Half / Second Half)?
2. Within each group, are they sorted by probability?
3. Are there any outcomes that look like they belong to a **different game**? Signs:
   - A threshold much higher/lower than the others in its group
   - A probability that breaks the pattern (suddenly jumps up)
   - An outcome that mentions a date or game number different from this event

### Step 4: For each event — Audit the Period Markets section

Scroll to **"Period Markets"**:

1. Record the market names and number of outcomes per market
2. Check monotonicity within each market (same as Step 2)
3. Flag any outcomes that appear to be from a different game

### Step 5: Cross-reference with Kalshi

For the 2 NBA/NHL events, go to **kalshi.com** and find the same game:

1. Navigate to the game page on Kalshi
2. Click on "First Half" or "1H Total" tab
3. Record the thresholds and their current yes/no prices
4. Compare against what bainluck shows:
   - Does bainluck show the **same number of thresholds**?
   - Do the probabilities **roughly match**? (Within 5% is fine, Kalshi prices change)
   - Does bainluck show any thresholds that **don't exist on Kalshi** for this game? (These are likely from a previous game in the series)

### Step 6: Check for cross-game contamination

For the NBA playoff event specifically:

1. On Kalshi, check if there are **multiple events** for the same matchup (Game 1, Game 2, Game 3, etc.) — they'll have different dates in the ticker (e.g., `KXNBA1HTOTAL-26APR19PHIBOS` vs `KXNBA1HTOTAL-26APR24BOSPHI`)
2. Record how many game-specific events exist for this matchup on Kalshi
3. On bainluck, does the event page show outcomes ONLY from today's game, or are there outcomes that look like they're from a previous game?

### Step 7: Output

Produce a JSON code block with this structure:

```json
{
  "captured_at": "2026-04-24T20:00:00Z",
  "date": "2026-04-24",
  "events_audited": [
    {
      "bainluck_url": "/events/14595395",
      "sport": "basketball_nba",
      "teams": "76ers vs Celtics",
      "status": "scheduled",
      "projected_scoring": {
        "thresholds": [
          {"threshold": 200.5, "probability_pct": 84},
          {"threshold": 203.5, "probability_pct": 77}
        ],
        "monotonic": true,
        "violations": []
      },
      "spread_section": {
        "groups": ["Full Game", "First Half", "Second Half"],
        "total_outcomes": 30,
        "suspected_wrong_game_outcomes": [],
        "grouped_correctly": true
      },
      "period_markets": {
        "markets": [
          {
            "name": "First Half Total",
            "outcomes": 9,
            "monotonic": false,
            "violations": [
              {"threshold": 121.5, "probability_pct": 58, "previous_threshold": 118.5, "previous_pct": 25}
            ]
          }
        ]
      },
      "kalshi_cross_reference": {
        "1h_total_thresholds_on_kalshi": 9,
        "1h_total_thresholds_on_bainluck": 9,
        "match": true,
        "extra_on_bainluck": [],
        "notes": "All thresholds match. Probabilities within 3% of Kalshi."
      },
      "cross_game_contamination": {
        "kalshi_events_for_matchup": 3,
        "kalshi_event_tickers": ["KXNBA1HTOTAL-26APR19PHIBOS", "KXNBA1HTOTAL-26APR21PHIBOS", "KXNBA1HTOTAL-26APR24BOSPHI"],
        "bainluck_shows_only_current_game": true,
        "contamination_found": false
      }
    }
  ],
  "summary": {
    "total_events": 4,
    "monotonicity_violations": 1,
    "cross_game_contamination": 0,
    "wrong_game_outcomes": 0,
    "overall_accuracy": "3/4 events clean, 1 has 1H total monotonicity issue"
  }
}
```

### Important Notes

- **Do NOT take screenshots** — structured data only
- **Monotonicity is key**: P(over 200.5) >= P(over 203.5) >= P(over 206.5). Any increase is a violation.
- **Cross-game contamination** is the #1 thing we're looking for — outcomes from Game 1/2 showing on Game 3's page
- **Compare threshold COUNTS** between Kalshi and bainluck — if bainluck shows more thresholds than Kalshi has for today's game, those extra ones are likely from a previous game
- Focus on playoff games (NBA, NHL) where multiple games in a series create the most contamination risk
- If a game is completed, the prices may show final settlement values (0% or 100%) — that's expected, not a bug

## Scoring

- **CRITICAL**: Cross-game contamination found (outcomes from wrong game)
- **CRITICAL**: Monotonicity violation in Projected Combined Scoring (main totals)
- **WARNING**: Monotonicity violation in Period Markets (less visible)
- **INFO**: Minor probability differences between Kalshi and bainluck (<5%)
