# Module 2: Sport & League Page Audit

## Goal

Audit every sport and league page on bainluck.com for data completeness, navigation integrity, and UX quality.

## Context

Bain Luck organizes sports into a hierarchy:
- **Sport hub**: `/sport/basketball` — all leagues for this sport
- **League page**: `/sport/basketball/nba` — standings, games, futures, grid link
- **Category page**: `/categories/golf` — for individual sports without teams

Each league page should show: upcoming/live/completed games, standings or rankings, links to the championship grid, league-level futures (MVP, ROY, win totals), and navigation to individual events.

## Instructions

### Step 1: Discover All Pages

Start at **bainluck.com** and use the navigation to find all sport/league pages. Check these known routes:

**Team sports:**
- `/sport/basketball/nba`
- `/sport/basketball/wnba`
- `/sport/hockey/nhl`
- `/sport/baseball/mlb`
- `/sport/football/nfl`
- `/sport/football/ncaaf`
- `/sport/basketball/ncaab`
- `/sport/soccer/epl`
- `/sport/soccer/mls`
- `/sport/soccer/ucl`
- `/sport/mma/ufc`

**Individual sports:**
- `/categories/golf`
- `/categories/tennis`

Note which pages exist (200 OK) and which return 404 or redirect.

### Step 2: Audit Each Page

For each page that loads, evaluate:

#### Content Completeness
- [ ] **Page loads without error**: No 404, 500, or blank page
- [ ] **League name and logo**: Correct league branding displayed
- [ ] **Season info**: Current season/year shown (not stale)
- [ ] **Upcoming games**: List of upcoming games with dates and teams
- [ ] **Live games**: Currently live games highlighted (if any)
- [ ] **Completed games**: Recent results visible
- [ ] **Championship grid link**: Link to `/playoffs/{league}` exists and works
- [ ] **Standings/rankings**: Some form of standings, if applicable for this league

#### Futures & Markets
- [ ] **Championship futures**: League champion odds shown (if available)
- [ ] **Award futures**: MVP, ROY, DPOY, etc. shown (if available for this sport)
- [ ] **Win totals**: Season win totals shown (if available)
- [ ] **Market source attribution**: Sources (Kalshi, Polymarket, sportsbooks) are indicated

#### Navigation
- [ ] **Breadcrumb correct**: Shows correct hierarchy (e.g., Basketball > NBA)
- [ ] **Event click-through**: Clicking a game leads to the correct event detail page
- [ ] **Back to sport hub**: Can navigate up to the sport hub page
- [ ] **Grid click-through**: Championship grid link leads to populated grid

#### Data Quality
- [ ] **No stale LIVE labels**: No games marked LIVE that are in the future
- [ ] **Correct sport**: All games shown belong to this league (no cross-sport contamination)
- [ ] **Reasonable probabilities**: Win probabilities are between 1-99% for unresolved matchups
- [ ] **Team names correct**: No misspellings, abbreviations are standard

#### Mobile (375px)
- [ ] **Page renders**: Content is visible on mobile
- [ ] **Games list readable**: Game cards/rows are not cut off
- [ ] **Navigation works**: Can navigate to events from mobile

### Step 3: Screenshots

For each league page:
1. Desktop screenshot (above-the-fold)
2. Mobile screenshot (375px) if the page has unique mobile issues

### Step 4: Report

```markdown
# Sport & League Page Audit Report
**Date:** [today's date]

## Page Inventory
| Route | Status | Sport | League |
|-------|--------|-------|--------|
| /sport/basketball/nba | 200 OK | Basketball | NBA |
| /sport/hockey/nhl | 200 OK | Hockey | NHL |
| /categories/tennis | 404 | Tennis | — |
| ... | ... | ... | ... |

## Per-Page Results

### /sport/basketball/nba
| Check | Result | Notes |
|-------|--------|-------|
| ... | ... | ... |

[Repeat for each page]

## Summary
- Pages found: [count]
- Pages with issues: [count]
- Health Score: [X] / 100

## Critical Findings
1. [Description]

## Warnings
1. [Description]

## Missing Pages (expected but not found)
- [List any sport/league combos that should exist but don't]

## Suggested Improvements
- [3 specific improvements for league pages]
```
