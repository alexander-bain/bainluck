# Module 6: Championship Grid Deep Audit

## Goal

Audit every championship grid on bainluck.com cell-by-cell. Verify probabilities are reasonable, logos are present, data sources are shown, and values match live Kalshi/Polymarket data.

## Context

Championship grids show each team's probability of reaching successive playoff stages:
- **NBA/NHL**: Make Playoffs → Win Division → Win Conference → Win Championship
- **MLB**: Make Playoffs → Win Division → Win Pennant → Win World Series
- **Golf**: Different — shows tournament-by-tournament winner odds for majors

Each cell's probability comes from aggregating Kalshi, Polymarket, and/or sportsbook data. The grid is at `/playoffs/{league}`.

Key quality rules:
- Probabilities within each column should sum to approximately 100%
- Monotonicity: P(Make Playoffs) >= P(Win Division) >= P(Win Conference) >= P(Championship)
- No duplicate teams
- Each team should have a logo and correct name

## Instructions

### Step 1: Audit Each Grid

Visit each of these grids:
- `/playoffs/nba`
- `/playoffs/nhl`
- `/playoffs/mlb`
- `/playoffs/golf` (if it exists)

### Step 2: Per-Grid Checklist

For each grid:

#### Structure
- [ ] **Grid loads**: All rows and columns render
- [ ] **Column headers correct**: Headers match the expected playoff stages for this league
- [ ] **All teams present**: The expected number of teams appear (30 NBA, 32 NHL, 30 MLB)
- [ ] **No duplicate teams**: Each team appears exactly once
- [ ] **Teams sorted sensibly**: By championship probability, division, or alphabetically

#### Team Identity
- [ ] **Every team has a logo**: No missing/broken logo images
- [ ] **Team names correct**: Full, properly spelled team names
- [ ] **Team colors used**: Row or cell styling reflects team colors (if applicable)
- [ ] **Records shown**: Win-loss records displayed (if applicable)

#### Probability Quality
- [ ] **Column sums ~100%**: For each column, add up all team probabilities. Should be 95-105%.
  - Record actual sum for each column.
- [ ] **Monotonicity holds**: For each team, later-round probabilities are <= earlier-round probabilities
  - Note any violations (team X: 25% make playoffs but 30% win division)
- [ ] **No 0% championship contenders**: Teams with >20% make-playoffs shouldn't show 0% championship
- [ ] **No 100% values**: Unless a team has been mathematically eliminated or clinched
- [ ] **Reasonable ranges**: Championship favorites should be 5-25%, not 50%+

#### Source Verification (Spot Check)

Pick **5 teams** per grid. For each:
1. Visit **kalshi.com** and find that team's championship odds
2. Visit **polymarket.com** and find that team's championship odds (if available)
3. Compare against the probability shown on bainluck.com
4. The bainluck value should be within 5 percentage points of the source values

Record the comparison:
| Team | Bain Luck | Kalshi | Polymarket | Sportsbook | Delta |
|------|----------|--------|------------|------------|-------|

#### Interactivity
- [ ] **Team rows clickable**: Clicking a team navigates somewhere (team page or detail)
- [ ] **Hover/tooltip**: Hovering shows additional info (source breakdown)
- [ ] **Source indicators**: Can tell which sources contributed to each cell

#### Mobile (375px)
- [ ] **Grid scrollable**: Can horizontally scroll to see all columns
- [ ] **Team names visible**: Not truncated to unreadability
- [ ] **Probabilities readable**: Numbers aren't cut off or overlapping
- [ ] **Touch targets adequate**: Can tap team rows on mobile

### Step 3: Screenshots

For each grid:
1. Desktop full-width screenshot
2. Mobile (375px) screenshot
3. Close-up of any problem areas

### Step 4: Report

```markdown
# Championship Grid Audit Report
**Date:** [today's date]
**Grids audited:** [count]

## Summary
| Grid | Teams | Columns | Column Sum OK | Monotonicity OK | Source Match | Score |
|------|-------|---------|--------------|-----------------|-------------|-------|
| NBA | 30 | 4 | 4/4 | 28/30 | 4/5 | 85 |
| NHL | 32 | 4 | 4/4 | 32/32 | 5/5 | 95 |
| ... | ... | ... | ... | ... | ... | ... |

## Per-Grid Results

### NBA Grid (`/playoffs/nba`)

**Column Sums:**
| Column | Sum | Status |
|--------|-----|--------|
| Make Playoffs | 102.3% | OK |
| Win Division | 99.1% | OK |
| Win Conference | 101.5% | OK |
| Championship | 98.7% | OK |

**Monotonicity Violations:**
- [Team]: [detail]

**Source Spot Check:**
| Team | Bain Luck | Kalshi | Polymarket | Delta | Status |
|------|----------|--------|------------|-------|--------|
| Thunder | 28.5% | 27.0% | 29.1% | 1.5pp | OK |
| ... | ... | ... | ... | ... | ... |

**Other Findings:**
- [Any issues with logos, names, rendering]

[Repeat for each grid]

## Critical Findings
1. [Description]

## Warnings
1. [Description]

## Suggested Improvements
1. [Specific improvement]
2. [Specific improvement]
3. [Specific improvement]
```

## Scoring Rubric

- **CRITICAL** (-10): Column sums off by >15%, team missing entirely, grid blank
- **WARNING** (-3): Monotonicity violation, source delta >5pp, missing logo, mobile rendering issue
- **INFO** (-1): Minor visual issues, sort order preference
