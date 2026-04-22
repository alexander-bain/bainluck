# Module 3: Market Completeness Audit

## Goal

Cross-reference the prediction markets currently available on Kalshi and Polymarket against what bainluck.com is actually displaying. Identify markets we're missing.

## Context

Bain Luck aggregates prediction market data from two sources:
- **Kalshi** (kalshi.com) — US-regulated exchange with sports, weather, economics markets
- **Polymarket** (polymarket.com) — Crypto-based exchange with sports and current events markets

Our site should surface every sports-related market from both platforms. Markets appear on different pages depending on their type:
- Championship/conference/division/playoffs → Championship Grid (`/playoffs/{league}`)
- Game moneyline/spread/total → Event Detail (`/events/{id}`)
- Player props → Event Detail (player props section)
- Awards (MVP, ROY) → League Page (`/sport/{sport}/{league}`)
- Win totals → League Page
- Tournament winner → Category Page (`/categories/golf`)

## Instructions

### Step 1: Inventory Kalshi Sports Markets

Go to **kalshi.com**. Navigate to their Sports section. For each sport category:

1. **Count total open markets** by sport
2. **Note market types available**: championship, game props, player props, awards, win totals, etc.
3. **Record any NEW market types** we might not support (e.g., new prop types, new sports, new competition formats)
4. **Note any ticker prefixes** you see (e.g., KXNBA, KXNFLGAME, KXNBAPTS)

Focus on these sports: NBA, NHL, MLB, NFL, WNBA, NCAAB, NCAAF, UFC/MMA, Soccer (EPL, MLS, UCL, Liga MX), Golf, Tennis, Boxing

### Step 2: Inventory Polymarket Sports Markets

Go to **polymarket.com**. Navigate to Sports.

1. **Count total open markets** by sport
2. **Note market types**: Usually championship, series, and some game props
3. **Look for unique markets** not on Kalshi (Polymarket sometimes has different props or sports)

### Step 3: Cross-Reference Against Bain Luck

For each sport with significant markets:

1. Visit the corresponding **bainluck.com** page (league page, grid, category page)
2. Count how many prediction market data points are visible
3. Compare against the counts from Steps 1-2
4. Note specific markets that exist on Kalshi/PM but do NOT appear on bainluck.com

Pay special attention to:
- **Game-level markets**: Are today's game props showing up on event detail pages?
- **Player props**: Pick 2-3 events and compare Kalshi player props vs. what bainluck shows
- **Championship grid**: Does the grid show both Kalshi AND Polymarket data?
- **New/obscure sports**: Does Kalshi have markets for sports we don't cover at all?

### Step 4: Identify Gaps

Categorize missing markets:

1. **CRITICAL GAPS**: Markets that exist and should clearly be on our site but aren't
   - e.g., NBA Championship on Kalshi exists but isn't in our grid
2. **COVERAGE GAPS**: Market types we support for some sports but not others
   - e.g., Player props show for NBA but not NHL
3. **NEW OPPORTUNITIES**: Market types or sports we don't support at all yet
   - e.g., Kalshi added tennis tournament markets we've never seen

### Step 5: Report

```markdown
# Market Completeness Audit Report
**Date:** [today's date]

## Market Inventory

### Kalshi
| Sport | Total Open Markets | Market Types Available | Key Tickers |
|-------|-------------------|----------------------|-------------|
| NBA | ~150 | championship, game, player props, awards | KXNBA, KXNBAGAME, KXNBAPTS |
| ... | ... | ... | ... |

### Polymarket
| Sport | Total Open Markets | Market Types Available |
|-------|-------------------|----------------------|
| NBA | ~20 | championship, series |
| ... | ... | ... |

## Coverage on Bain Luck

### Championship Grids
| League | Kalshi markets in grid | Kalshi markets NOT in grid | Polymarket in grid | Polymarket NOT in grid |
|--------|----------------------|--------------------------|-------------------|----------------------|
| NBA | X | Y | X | Y |
| ... | ... | ... | ... | ... |

### Event Detail (spot check: [event name])
| Market Type | Available on Kalshi | Shown on Bain Luck | Missing |
|-------------|-------------------|-------------------|---------|
| Player points | 8 players | 6 players | 2 missing |
| ... | ... | ... | ... |

### League Futures
| League | Awards on Kalshi | Awards on Bain Luck | Win Totals Kalshi | Win Totals BL |
|--------|-----------------|--------------------|-----------------|-|
| NBA | MVP, ROY, DPOY | MVP, ROY | 30 teams | 30 teams |
| ... | ... | ... | ... | ... |

## Critical Gaps (markets exist, should be shown, aren't)
1. [Specific market] on [source] — should appear on [page] — ticker: [X]
2. ...

## Coverage Gaps (partial support)
1. [Market type] supported for [sport A] but not [sport B]
2. ...

## New Opportunities (markets we don't support at all)
1. [Description] — [source] ticker: [X] — [estimated user interest: high/medium/low]
2. ...

## Summary
- Total markets on Kalshi: ~[X]
- Total markets on Polymarket: ~[X]  
- Markets surfaced on bainluck.com: ~[X]
- **Coverage rate**: [X]%
- Critical gaps: [count]
```
