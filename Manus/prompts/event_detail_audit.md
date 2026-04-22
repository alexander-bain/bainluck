# Module 1: Event Detail Deep Audit

## Goal

Audit 6 specific event detail pages on bainluck.com for data completeness, visual rendering quality, and cross-page consistency. You are acting as a quality assurance tester who understands sports odds.

## Context

Bain Luck (bainluck.com) is a sports odds visualization site that shows win probabilities instead of traditional betting lines. Each event detail page (`/events/{id}`) should display:
- A **hero card** with the current aggregate win probability
- A **win probability chart** showing probability over time from multiple sources
- A **score differential chart** showing the score gap over time
- **Game state indicators** (quarter/period/inning boundaries) on both charts
- **Player props** (points, rebounds, assists, etc.) from Kalshi/Polymarket
- **Team props** (spread, total) from sportsbooks
- **Related Futures** (championship odds, series odds, awards for both teams)
- A **projected final score**

## Instructions

### Step 1: Select Events

Go to **bainluck.com** and browse the home feed. Select 6 events to audit:
- 2 **LIVE** events (games currently in progress, any sport)
- 2 **completed** events (finished today or yesterday)
- 2 **upcoming** events (scheduled for today or tomorrow)

Try to cover at least 3 different sports (e.g., NBA, NHL, MLB, Golf, Soccer).

For each event, note the event ID from the URL (`/events/{id}`) and the matchup name.

### Step 2: Audit Each Event

For each of the 6 events, visit the event detail page and evaluate every item on this checklist. Mark each as PASS, FAIL, or N/A.

#### Hero Section
- [ ] **Hero probability displayed**: A clear win probability is shown (e.g., "Lakers 62%")
- [ ] **Hero probability reasonable**: The probability is between 1% and 99% (unless game is final)
- [ ] **Team logos present**: Both team logos are visible (for team sports)
- [ ] **Team colors used**: Team-specific colors are applied to the probability bar
- [ ] **Game status correct**: Shows "LIVE", "FINAL", or scheduled time accurately
- [ ] **Score displayed** (if live/completed): Current or final score is visible

#### Win Probability Chart
- [ ] **Chart renders**: The chart is visible (not blank/loading)
- [ ] **Time axis correct**: X-axis starts at game start time and extends to current time (or game end)
- [ ] **Multiple sources shown**: At least 2 source lines are visible (e.g., "Bain Luck", "ESPN", "Kalshi")
- [ ] **Source count badge**: The source count indicator matches the number of lines on the chart
- [ ] **Legend readable**: Each source is labeled and distinguishable by color
- [ ] **Game state markers**: Period/quarter/half boundaries are marked on the chart (vertical lines or labels)
- [ ] **No flat lines at 50%**: Sources don't show a flat 50% line (indicates missing data being displayed as neutral)
- [ ] **Chart value matches hero**: The latest chart value approximately matches the hero probability

#### Score Differential Chart
- [ ] **Chart renders**: The chart is visible (not blank/loading)
- [ ] **Time axis aligned**: X-axis matches the win probability chart's time range
- [ ] **Score data present**: Line shows actual score differential changes
- [ ] **Game state markers**: Same period boundaries shown as in win probability chart

#### Player Props
- [ ] **Section visible**: Player props section exists on the page
- [ ] **Props displayed**: At least some player prop markets are shown (for team sports)
- [ ] **No duplicates**: No player appears twice with the same prop type
- [ ] **Reasonable values**: Prop lines are reasonable (e.g., points 15-40 for NBA, not 0 or 500)
- [ ] **Source attribution**: Each prop shows its source (Kalshi, Polymarket, sportsbook)

#### Team Props (Spread & Total)
- [ ] **Spread shown**: Point spread is displayed
- [ ] **Total shown**: Over/under total is displayed
- [ ] **Format correct**: Displayed as a number, not garbled (e.g., not "3 - -1")

#### Related Futures
- [ ] **Section loads**: Related Futures section is visible
- [ ] **Championship odds**: Both teams' championship odds are shown
- [ ] **No duplicate labels**: Each market appears once (not duplicated across sources)
- [ ] **Labels make sense**: Market names are clear to a casual fan
- [ ] **Probabilities reasonable**: No 0% or 100% values for unresolved markets

#### Mobile Rendering
- [ ] **Content loads at 375px**: Page renders content (no infinite spinner)
- [ ] **Charts visible**: Charts render on mobile viewport
- [ ] **Text readable**: No overlapping or truncated text

#### Cross-Page Consistency
- [ ] **Feed matches detail**: Go back to the feed — does the feed card show the same probability as the detail page hero?

### Step 3: Take Screenshots

For each event page, take:
1. A **desktop full-page screenshot** (or multiple scrolled captures)
2. A **mobile (375px) screenshot** of the hero + chart area

Attach all screenshots to your response.

### Step 4: Report

Produce a report in this exact format:

```markdown
# Event Detail Audit Report
**Date:** [today's date]
**Events audited:** 6

## Summary
- Total checks: [count]
- PASS: [count]
- FAIL: [count]  
- N/A: [count]
- Health Score: [100 - (10 * critical_fails) - (3 * warning_fails)] / 100

## Event 1: [Matchup] (ID: [id], Status: [LIVE/FINAL/UPCOMING])
| Check | Result | Notes |
|-------|--------|-------|
| Hero probability displayed | PASS/FAIL | ... |
| ... | ... | ... |

[Repeat for all 6 events]

## Critical Findings (action required)
1. [Description] — Event [id], screenshot attached

## Warnings
1. [Description] — Event [id]

## Positive Observations
- [Things that work particularly well]

## Suggested Improvements
- [3 specific, actionable suggestions for improving event detail pages]
```

## Scoring Rubric

- **CRITICAL FAIL** (-10 points): Chart doesn't render, mobile shows spinner, hero probability missing, cross-page mismatch >5pp
- **WARNING FAIL** (-3 points): Missing player props, missing game state markers, no source attribution, minor format issues
- **INFO** (-1 point): Minor visual polish issues, missing but non-essential elements

Start health score at 100 and deduct per the rubric.
