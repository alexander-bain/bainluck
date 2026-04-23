# Event Matching Ground Truth Sweep

## Goal

Capture a structured ground truth of today's sports events and their prediction markets from Kalshi and Polymarket. This data is used to measure and hill-climb our matching accuracy to 100%.

Three things to capture:
1. **Every game today** across Kalshi and Polymarket (Layer 1 ground truth)
2. **Every market for 3 selected games** — ALL tickers, not just moneyline (Layer 4 ground truth)
3. **What shows on bainluck.com** for those 3 games' event detail pages (Layer 3 ground truth)

## Instructions

### Step 1: Kalshi Game Sweep (Layer 1)

Go to **kalshi.com**. Navigate to the Sports section. For each sport with games today (MLB, NBA, NHL — skip offseason sports):

1. Find all game-level markets for today. These are typically listed under "Today's Games" or similar.
2. For each game, record:
   - The **event ticker** (e.g., `KXMLBGAME-26APR23NYYBOS`) — visible in the URL when you click on the game
   - The **teams** playing
   - The **sport** (MLB, NBA, NHL)
   - The **game time** (Eastern time)
   - The **share URL** (click "Share" on the market page, copy the link)

Focus on Tier 1 sports: MLB, NBA, NHL. Skip esports, soccer, tennis unless they have major events.

### Step 2: Polymarket Game Sweep (Layer 1)

Go to **polymarket.com**. Navigate to Sports.

1. Find all game-level markets for today
2. For each game, record:
   - The **market title** (e.g., "New York Yankees vs. Boston Red Sox")
   - The **condition ID** or **slug** from the URL
   - The **share URL**
   - The **sport**

### Step 3: Deep Audit — 3 Games (Layer 4)

Pick **3 games** from Step 1 — one from each sport if possible (1 MLB, 1 NBA, 1 NHL). For each:

#### On Kalshi:
Navigate to the game page. Record **EVERY market listed** for this game, not just moneyline. This includes:
- Moneyline / winner
- Spread (run line)
- Total (over/under)
- First 5 innings / first half
- Player props (hits, home runs, strikeouts, points, rebounds, assists, etc.)
- Team totals
- First inning run / first basket
- Series winner (if applicable)
- Any other markets listed

For each market, record:
- **Ticker** (from the URL, e.g., `KXMLBHIT-26APR23NYYBOS`)
- **Market name** (as displayed)
- **Number of outcomes** (e.g., 36 outcomes for a player prop with 18 batters × 2 sides)
- **Market type** (moneyline, spread, total, player_prop, first_half, etc.)

#### On Polymarket:
Do the same — find all markets related to this specific game and record each one.

#### On bainluck.com (Layer 3):
Visit the event detail page for this game on **bainluck.com** (search for the teams on the site).

Under the "Bigger Picture" or "Related Futures" section at the bottom, record what appears:
- Championship odds present? (World Series, NBA Championship, Stanley Cup)
- Conference/Pennant odds present? (AL/NL Champion, Eastern/Western Conference)
- Division odds present? (AL East, NFC West, etc.)
- Make Playoffs odds present?
- Player awards present? (MVP, Cy Young, ROY)
- Any wrong-sport markets? (e.g., basketball market on a baseball page)
- Any duplicate markets?

Also check the **Player Props** section:
- How many player prop cards are shown?
- Do players have headshot images or just initials?
- Are the team filter pills (e.g., SOX / YAN) working?

### Step 4: Output

Produce a single JSON code block with this exact structure. **This is the most important step — the JSON must be valid and complete.**

```json
{
  "captured_at": "2026-04-23T14:30:00Z",
  "date": "2026-04-23",
  "capture_method": "manus_sweep",
  "games_today": [
    {
      "sport": "baseball_mlb",
      "home_team": "Boston Red Sox",
      "away_team": "New York Yankees",
      "date": "2026-04-23",
      "time_et": "7:05 PM",
      "sources": {
        "kalshi": {
          "ticker": "KXMLBGAME-26APR23NYYBOS",
          "url": "https://kalshi.com/markets/..."
        },
        "polymarket": {
          "condition_id": "0x...",
          "url": "https://polymarket.com/event/..."
        }
      }
    }
  ],
  "deep_audits": [
    {
      "sport": "baseball_mlb",
      "home_team": "Boston Red Sox",
      "away_team": "New York Yankees",
      "bainluck_event_url": "/events/14523747",
      "kalshi_markets": [
        {
          "ticker": "KXMLBGAME-26APR23NYYBOS",
          "name": "Yankees vs Red Sox",
          "type": "moneyline",
          "outcomes": 2
        },
        {
          "ticker": "KXMLBHIT-26APR23NYYBOS",
          "name": "Yankees vs Red Sox: Hits",
          "type": "player_prop",
          "outcomes": 36
        }
      ],
      "polymarket_markets": [
        {
          "condition_id": "...",
          "name": "New York Yankees vs. Boston Red Sox",
          "url": "https://polymarket.com/event/...",
          "type": "moneyline"
        }
      ],
      "bainluck_event_detail": {
        "player_props_count": 97,
        "player_headshots": false,
        "team_filter_working": true,
        "related_futures": {
          "championship": true,
          "conference_or_pennant": true,
          "division": true,
          "make_playoffs": true,
          "awards": ["AL MVP - Aaron Judge 19%"],
          "wrong_sport_leaks": [],
          "wrong_gender_leaks": []
        }
      }
    }
  ]
}
```

### Important Notes

- **Do NOT take screenshots** — we only need the structured data. This saves credits.
- **Tickers are critical** — the event ticker (from the URL) is how we match markets in our database. Get every character right.
- **Every market matters** — for the 3 deep-audit games, list literally every market you see. A typical MLB game has 10-15 market types with hundreds of outcomes total.
- **JSON must be valid** — double-check quotes, commas, brackets before outputting.
- If a sport has no games today, skip it and note "no games today" in a comment.
- If Polymarket doesn't have a game, set its source to `null`.

## Scoring

This audit is scored on completeness:
- **CRITICAL**: Missing a game that exists on Kalshi/Polymarket
- **CRITICAL**: Missing a market type in the deep audit (e.g., skipping player props)
- **WARNING**: Missing a ticker or URL
- **INFO**: Minor formatting issues in JSON
