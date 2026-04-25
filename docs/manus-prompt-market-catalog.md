# Manus Prompt: Sports Prediction Market Ground Truth Catalog

## Goal

Catalog every open sports prediction market on Kalshi and Polymarket. For each market, classify where it belongs in a sports website hierarchy. The output will be used to measure and improve how well our site (bainluck.com) routes prediction market data to the right pages.

## Our site hierarchy

Our site organizes sports data into 4 levels:

```
[sport]    → /sport/basketball         (sport hub: all leagues in this sport)
[league]   → /sport/basketball/nba     (league page: standings, grid, games, futures)  
[team]     → /sport/basketball/nba/celtics  (team page: schedule, props, futures)
[player]   → /sport/basketball/nba/celtics/jayson-tatum  (player page: props, awards)
```

Additionally, we have these surfaces where markets can appear:

| Surface | URL pattern | What shows here |
|---------|------------|-----------------|
| **Championship grid** | `/playoffs/nba` | Teams as rows, championship stages as columns (make playoffs → division → conference → championship). Each cell = probability. |
| **Event detail** | `/events/{id}` | Individual game page. Shows: win probability, player props, game props (spread, total), related futures (series odds, championship odds for both teams). |
| **League page** | `/sport/basketball/nba` | Standings, upcoming games, league-level futures (MVP, ROY, win totals). |
| **Category page** | `/categories/golf` or `/economics` | Non-team-sport or non-sport markets organized by theme. |

## What to catalog

### Step 1: Kalshi Sports Markets

Go to **kalshi.com**. Navigate to their sports section. For each sport (NBA, NHL, MLB, NFL, WNBA, NCAAB, NCAAF, MMA/UFC, Soccer, Tennis, Golf, Boxing), find ALL open markets.

For each market, record:

| Field | Description | Example |
|-------|-------------|---------|
| `source` | Always "kalshi" | kalshi |
| `market_name` | Exact market title | "Lakers to win 2026 NBA Championship" |
| `market_url` | Full URL | https://kalshi.com/markets/kxnba... |
| `ticker` | Kalshi event ticker (visible in URL or market page) | KXNBA-26CHAMPION |
| `sport` | Sport category | basketball |
| `league` | Specific league | nba |
| `num_outcomes` | Number of outcomes/brackets | 30 |
| `market_type` | See classification below | championship |
| `hierarchy_level` | Where it belongs: sport / league / team / player / event | league |
| `surface` | Which page it should appear on | championship_grid |
| `grid_column` | If grid, which column? | Championship |
| `team` | If team-specific, which team? | Lakers |
| `player` | If player-specific, which player? | LeBron James |
| `notes` | Anything unusual about this market | "Has 30 team outcomes" |

### Step 2: Polymarket Sports Markets

Go to **polymarket.com**. Navigate to Sports. Do the same catalog for all sports markets. Polymarket doesn't have tickers, but record the market slug/URL and condition ID if visible.

### Step 3: Kalshi Economics Markets (bonus)

Since we also have an economics page, catalog Kalshi's economics/finance markets using the same format. These would go to `hierarchy_level: category` and `surface: economics_page`.

## Market type classification

Use these categories:

| Type | Description | Example |
|------|-------------|---------|
| `championship` | Who wins the title | "NBA Championship winner" |
| `conference` | Conference/league winner | "Eastern Conference winner" |
| `division` | Division winner | "Atlantic Division winner" |
| `make_playoffs` | Will team make playoffs | "Will Lakers make playoffs?" |
| `series` | Playoff series winner | "Celtics vs Cavaliers series" |
| `win_total` | Season win total O/U | "Lakers over 48.5 wins" |
| `exact_wins` | Exact season win count | "Lakers exactly 50 wins" |
| `award` | Individual award | "MVP", "ROY", "DPOY" |
| `game_moneyline` | Who wins a specific game | "Lakers vs Celtics" |
| `game_spread` | Point spread | "Lakers -3.5" |
| `game_total` | Over/under total | "O/U 220.5" |
| `game_half` | Half/quarter winner | "1st half winner" |
| `player_points` | Player points prop | "LeBron over 25.5 points" |
| `player_rebounds` | Player rebounds prop | "LeBron over 8.5 rebounds" |
| `player_assists` | Player assists prop | "LeBron over 7.5 assists" |
| `player_combo` | Combined stat prop | "LeBron PRA over 40.5" |
| `player_other` | Other player prop | "First basket scorer" |
| `tournament_winner` | Golf/tennis tournament winner | "Masters winner" |
| `tournament_prop` | Tournament prop | "Top 5 finish at Masters" |
| `fight_winner` | MMA/boxing fight winner | "Oliveira vs Holloway" |
| `fight_prop` | Method of victory, rounds | "Goes the distance" |
| `other` | Doesn't fit above | "How many home runs in 2026?" |

## Surface mapping rules

Use these rules to determine where each market should appear:

- **championship, conference, division, make_playoffs** → `championship_grid` (columns in the grid)
- **series** → `championship_grid` (dynamic "Current Round" column) AND `event_detail` (on games in that series)
- **win_total, exact_wins** → `league_page` (as a section) AND optionally `championship_grid` (as a column)
- **award** → `league_page` (awards section)
- **game_moneyline, game_spread, game_total, game_half** → `event_detail` (on the specific game page)
- **player_*** → `event_detail` (player props section on game page) AND `team_page` AND `player_page`
- **tournament_winner, tournament_prop** → `category_page` (golf, tennis)
- **fight_winner, fight_prop** → `event_detail` (on the fight card page)

## Output format

Produce a CSV file with all the fields listed above. One row per market. Group by sport, then by market_type within each sport.

At the end, include a summary section:

```
## Summary

### By Sport
NBA: X markets (Y Kalshi, Z Polymarket)
NHL: ...

### By Market Type
championship: X markets
conference: X markets
...

### By Surface
championship_grid: X markets
event_detail: X markets
league_page: X markets
...

### Cross-source pairs (same question on both Kalshi and Polymarket)
- NBA Championship: Kalshi KXNBA-26CHAMPION + Polymarket {slug}
- US Recession: Kalshi KXRECESSION + Polymarket {slug}
- ...
```

## Important notes

- **Be thorough.** Don't just grab the first page of markets. Click through all subcategories, scroll to load more, check tabs like "Props", "Futures", "Games". Kalshi often has hundreds of markets per sport across different event tickers.
- **Record the ticker/URL.** We need to match these back to our database. The ticker prefix (like `KXNBA`, `KXNFLGAME`, `KXNBAPTS`) is the most important field for Kalshi.
- **Note market status.** Only catalog OPEN markets (not resolved/settled). But note if a market just resolved recently — it tells us what types of markets to expect.
- **For game-level markets**, you don't need to catalog every single game. Instead, note the patterns: "Kalshi has KXNBAGAME, KXNBASPREAD, KXNBATOTAL, KXNBAPTS, KXNBAAST, KXNBAREB for every NBA game" — then give 2-3 examples with full details.
- **Cross-source pairing is a bonus.** If you notice the same question on both Kalshi and Polymarket, note it. But don't spend too long on this — it's easier to do programmatically after.
