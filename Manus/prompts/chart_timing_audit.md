# Module: Chart Timing & Boundary Audit

## Goal

Audit chart timing quality on completed event detail pages. Verify that win probability and score differential charts start at game time, end cleanly near game end, have no unexplained gaps, and align with each other.

## Context

Bain Luck (bainluck.com) shows two time-series charts on each event detail page:

1. **Win Probability Chart** (top): Shows probability of each team winning over time, from multiple sources (sportsbooks, ESPN, statistical models, prediction markets). Each source is a colored line.

2. **Score Differential Chart** (below): Shows the score gap over time. Uses actual score data from ESPN and sportsbook score feeds.

Both charts should:
- **Start** at approximately the real game start time (tip-off, puck drop, first pitch)
- **End** within ~5 minutes of the real game end — NOT trailing off with stale bookmaker data
- Have **no large gaps** (>5 minutes) in the middle where no data points exist
- Have the **same x-axis range** as each other (they should be aligned)
- Show **game state indicators** (vertical lines at period/quarter/inning boundaries)

### What "bad" looks like
- Chart extending 15-30 minutes past the game end with a flat line (stale bookmaker data)
- Chart starting 30+ minutes after the game actually began
- A sudden jump in the x-axis (e.g., timestamps skipping from 8:15 to 8:45)
- Win prob chart showing data until 10:30 PM but score chart ending at 10:15 PM
- No period/quarter/inning markers on a completed game that should have them

## Instructions

### Step 1: Select Events

Go to **bainluck.com** and browse the home feed. Select **8 completed events** to audit:
- 2 **NBA** games (basketball)
- 2 **NHL** games (hockey)
- 2 **MLB** games (baseball)
- 2 from **any other sport** with completed events (soccer, MMA, golf, etc.)

If a sport doesn't have 2 completed events, substitute from another sport. Try to maximize sport diversity.

For each event, note the event ID from the URL (`/events/{id}`) and the matchup name.

### Step 2: Research Real Game Times

For each of the 8 events, look up the **actual start and end time** from a reliable source (ESPN.com, Google Sports, or the official league site). Note:
- **Scheduled start time** (e.g., "7:00 PM ET")
- **Actual start time** if different (games often start a few minutes late)
- **End time** (when the final whistle/buzzer/out occurred)
- **Total duration** (e.g., "2h 47m")

### Step 3: Audit Each Event

Visit each event's detail page (`bainluck.com/events/{id}`) and evaluate:

| # | Check | PASS/FAIL | Notes |
|---|-------|-----------|-------|
| 1 | **Start timing**: Win prob chart starts within 10 min of real game start | | Note the chart's leftmost time vs real start |
| 2 | **End timing**: Win prob chart ends within 10 min of real game end | | Note if there's a stale flat tail |
| 3 | **No stale tail**: Chart doesn't show a long flat line after the game ended | | Stale data = flat probability at the end |
| 4 | **Score chart start**: Score diff chart starts at approximately the same time as win prob chart | | |
| 5 | **Score chart end**: Score diff chart ends at approximately the same time as win prob chart | | |
| 6 | **X-axis continuity**: No jumps or gaps >5 min visible in the time axis | | Look for sudden spacing changes |
| 7 | **Game state markers**: Period/quarter/inning lines visible on charts | | Count how many markers visible |
| 8 | **Marker placement**: Game state markers appear at approximately correct times | | Cross-reference with real game timeline |
| 9 | **Duration reasonable**: Total chart span matches expected game duration (±30 min) | | |
| 10 | **Final state**: Chart shows definitive outcome (clear winner) at the end | | Should converge to ~100%/0% |

### Step 4: Take Screenshots

For each event page, take a **desktop screenshot** that captures:
1. Both the win probability chart and score differential chart in one image
2. The time axis labels clearly visible

If the charts are too tall to capture together, take two screenshots (one per chart).

### Step 5: Cross-Sport Comparison

After auditing all 8 events, answer:
1. Which sport has the **best** chart timing quality? Why?
2. Which sport has the **worst**? What's the common issue?
3. Do events with more source lines (e.g., 4 sources vs 1) have better timing?
4. How many events had **no game state markers** at all?

### Step 6: Report

Produce a report in this exact format:

```markdown
# Chart Timing & Boundary Audit Report
**Date:** [today's date]
**Events audited:** 8

## Summary
- Total checks: [count]
- PASS: [count]
- FAIL: [count]
- Timing Health Score: [100 - (10 * critical_fails) - (3 * warning_fails)] / 100

## Per-Event Results

### Event 1: [Matchup] (ID: [id], Sport: [sport])
**Real game time:** [start] — [end] ([duration])
**Chart start:** [leftmost chart time]
**Chart end:** [rightmost chart time]
**Start offset:** [chart start - real start, in minutes]
**End offset:** [chart end - real end, in minutes]
**Sources visible:** [count and names]

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 1 | Start timing | PASS/FAIL | ... |
| ... | ... | ... | ... |

[Screenshot]

[Repeat for all 8 events]

## Cross-Sport Comparison
| Sport | Events | Avg Start Offset | Avg End Offset | Markers Present | Overall |
|-------|--------|-----------------|----------------|-----------------|---------|
| NBA | 2 | ... | ... | ... | Good/Fair/Poor |
| ... | ... | ... | ... | ... | ... |

## Key Findings
1. [Most impactful finding]
2. [Second most impactful]
3. [Third]

## Worst Offenders
[List the 2-3 events with the worst timing quality and describe specifically what's wrong]

## Positive Observations
[What works well]

## Suggested Fixes (prioritized)
1. [Highest-impact fix]
2. [Second fix]
3. [Third fix]
```

## Scoring Rubric

- **CRITICAL FAIL** (-10 points): Chart extends >20 min past game end, chart doesn't render, >15 min gap in data
- **WARNING FAIL** (-3 points): Chart extends 10-20 min past game end, 5-15 min gap, missing game state markers, chart domain mismatch between win prob and score charts
- **INFO** (-1 point): Minor timing offset (5-10 min), fewer markers than expected

Start health score at 100 and deduct per the rubric.
