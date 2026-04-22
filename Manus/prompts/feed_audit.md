# Module 4: Feed & Discovery Audit

## Goal

Audit the bainluck.com home feed and discovery surfaces from the perspective of a first-time user who is interested in sports but unfamiliar with betting. Evaluate data freshness, data quality, navigation, and overall UX.

## Context

Bain Luck (bainluck.com) shows win probabilities for sports events — "60% vs 40%" instead of traditional betting lines like "-150 / +130". The home feed is the primary discovery surface. It should show live, recent, and upcoming events with clear probabilities, team logos, and game state.

The site also has category pages for Weather (`/weather`) and Economics (`/economics`), plus sport-specific pages at `/sport/{sport}/{league}` and championship grids at `/playoffs/{league}`.

## Instructions

### Step 1: Home Feed Audit

Go to **bainluck.com**. Evaluate the home feed:

#### Data Freshness
- [ ] **No stale LIVE labels**: No events marked "LIVE" that are actually scheduled for the future
- [ ] **No stale LIVE labels (past)**: No events marked "LIVE" for games that ended hours ago
- [ ] **Dates are current**: Upcoming events show correct future dates (not past dates)
- [ ] **Featured markets current**: Any "featured" or "top" market shows a date that hasn't passed

#### Data Quality
- [ ] **No 100%/0% probabilities**: No event shows exactly 100% or 0% for an unresolved matchup
- [ ] **No suspicious daily changes**: No "daily change" indicators showing impossible values (e.g., -57.5%)
- [ ] **Probabilities are reasonable**: Win probabilities are between 5% and 95% for most upcoming events
- [ ] **Scores are correct**: For completed events, final scores look reasonable for the sport
- [ ] **Team names correct**: No misspelled team names or "TBD" placeholders

#### Navigation & UX
- [ ] **Sport filter pills work**: Click each sport filter pill — does it correctly filter the feed?
- [ ] **Feed sections make sense**: "Live Now", "Just Happened", "Upcoming" sections are correctly sorted
- [ ] **Momentum indicators sensible**: Any "Upset brewing", "Line moving" labels correspond to actual probability movement
- [ ] **Click-through works**: Click 3 different feed cards — does each lead to a working event detail page?
- [ ] **Back navigation works**: After clicking into an event, can you navigate back to the feed?

#### Visual Quality
- [ ] **Team logos present**: Every event card has team logos
- [ ] **Consistent styling**: All cards follow the same visual pattern (no broken/misaligned cards)
- [ ] **No overlapping elements**: Text, logos, and probability bars don't overlap
- [ ] **Light mode only**: No dark backgrounds, no dark mode elements

### Step 2: Category Pages Audit

Visit each of these category/specialty pages and do a quick health check:

#### Weather (`/weather`)
- [ ] **Page loads**: Content renders (not blank)
- [ ] **Featured market is current**: The featured market date is today or future
- [ ] **Map renders**: The global temperature map is visible
- [ ] **City data reasonable**: Temperature values make sense for the season (not 33F in LA in April)
- [ ] **No stale data**: Rainfall and temperature markets reference current or future dates

#### Economics (`/economics`)
- [ ] **Page loads**: Content renders
- [ ] **Fed rate chart renders**: The dot-plot/heatmap is visible
- [ ] **Markets current**: No markets referencing past dates as active/upcoming
- [ ] **Probabilities formatted**: All probabilities show % signs (not bare numbers like "30")
- [ ] **Distributions valid**: No probability distribution where buckets sum to >110%

#### Championship Grids (`/playoffs`)
- [ ] **NBA grid loads**: Teams, logos, probabilities visible
- [ ] **NHL grid loads**: Same checks
- [ ] **MLB grid loads**: Same checks
- [ ] **No golf grid issues**: Golf probabilities are not 100%/0% (known past bug)

### Step 3: Navigation Audit

Test the overall site navigation:
- [ ] **Top nav works**: All nav links lead to real pages
- [ ] **Sport hierarchy works**: `/sport/basketball/nba` loads a league page
- [ ] **No 404 pages**: Check at least 5 internal links — none return 404
- [ ] **Mobile nav works**: At 375px, the bottom tab bar navigates correctly

### Step 4: Mobile Smoke Test

Resize the browser to 375px width (iPhone SE) and check:
- [ ] **Feed renders**: Events are visible, not blank
- [ ] **Cards are tappable**: Feed cards respond to clicks
- [ ] **Bottom nav present**: Tab bar at the bottom is visible
- [ ] **No horizontal overflow**: No elements extend beyond the viewport causing horizontal scroll

### Step 5: Take Screenshots

Capture:
1. Home feed (desktop, full scroll)
2. Home feed (mobile 375px)
3. Weather page (desktop)
4. Economics page (desktop)
5. One championship grid (desktop)
6. Any page with a FAIL finding

### Step 6: Report

```markdown
# Feed & Discovery Audit Report
**Date:** [today's date]

## Summary
- Total checks: [count]
- PASS: [count]
- FAIL: [count]
- N/A: [count]
- Health Score: [X] / 100

## Home Feed
| Check | Result | Notes |
|-------|--------|-------|
| No stale LIVE labels | PASS/FAIL | ... |
| ... | ... | ... |

## Weather Page
| Check | Result | Notes |
|-------|--------|-------|

## Economics Page
| Check | Result | Notes |
|-------|--------|-------|

## Championship Grids
| Check | Result | Notes |
|-------|--------|-------|

## Navigation
| Check | Result | Notes |
|-------|--------|-------|

## Mobile
| Check | Result | Notes |
|-------|--------|-------|

## Critical Findings
1. [Description + screenshot]

## Warnings
1. [Description]

## What Works Well
- [Positive observations — things a first-time user would appreciate]

## Suggested Improvements
- [3-5 specific, actionable suggestions to improve discovery/UX]
  - Focus on: what would make a casual sports fan come back to this site?
```

## Scoring Rubric

- **CRITICAL** (-10): Feed blank/broken, events with 100%/0%, major navigation failure, mobile broken
- **WARNING** (-3): Stale dates, formatting issues, missing logos, confusing labels
- **INFO** (-1): Minor polish, could-be-better items
