# Module 11: Category Page Audit

## Goal

Deep audit of bainluck.com's non-sport category pages — **Politics**, **Entertainment**, **Economics**, and **Weather** — evaluating data quality, cross-source matching, classification accuracy, visual design, and overall UX. This module is designed to work for any category page, including new ones that may be added in the future.

## Context

Bain Luck (bainluck.com) aggregates prediction market data from **Kalshi** and **Polymarket** into themed category pages. Each page has:
- A **hero section** (trending or featured market cards)
- **Themed sub-sections** with markets organized by topic
- **Probability bars, sparklines, or heatmaps** depending on market type
- **Source attribution** (Kalshi/Polymarket badge on each card)
- **Cross-source matching** (same question on both platforms → merged into one card with both sources shown)

The category pages are at:
- **Politics**: `bainluck.com/politics`
- **Entertainment**: `bainluck.com/entertainment`
- **Economics**: `bainluck.com/economics`
- **Weather**: `bainluck.com/weather`

Markets come from two upstream sources:
- **Kalshi** (kalshi.com) — regulated US exchange. Markets identified by ticker prefix (e.g., `kxpresidential`, `kxrottentomatoes`, `kxfed`).
- **Polymarket** (polymarket.com) — crypto exchange. Markets identified by slug/question text.

## Instructions

### Step 1: Audit Each Category Page

For each of the 4 category pages, visit the page and evaluate these dimensions:

---

#### A. Data Freshness & Staleness

- [ ] **Page loads without error**: No 500, no blank content, no "Error" message
- [ ] **No past-event markets featured**: Hero/trending section doesn't show markets whose real-world event has already happened (e.g., a "Met Gala 2026" market after May 5)
- [ ] **Resolution dates are future**: Markets with visible resolution dates reference upcoming dates, not past ones
- [ ] **Movement data is current**: Markets showing "↑5%" or "Trending" indicators have actually moved recently (not weeks-old movement)
- [ ] **No "zombie" markets**: No markets that are effectively resolved (one outcome at 99%+) still showing as active/open

---

#### B. Cross-Source Matching

Visit both **kalshi.com** and **polymarket.com** and find 3-5 markets that exist on BOTH platforms for the same question. Then check bainluck:

- [ ] **Matched markets show both sources**: Markets available on both Kalshi AND Polymarket show both source badges (not appearing as two separate cards)
- [ ] **Probabilities are comparable**: When both sources are shown, their probabilities are within a reasonable range (not 80% on one and 20% on the other, unless there's genuine disagreement)
- [ ] **No obvious duplicates**: The same question doesn't appear twice in different sections with different source badges
- [ ] **Source count accurate**: If a card shows "2 sources", verify both Kalshi and Polymarket actually have that market

*Document which markets you checked and whether matching worked.*

---

#### C. Classification Accuracy

- [ ] **Markets are in the right category**: No politics markets showing on entertainment, no economics markets on weather, etc.
- [ ] **Sub-theme classification correct**: Within each page, markets are in the right sub-section (e.g., on Politics: presidential markets in the Presidential section, not Congressional)
- [ ] **Kind/type labels correct**: If markets have type badges (e.g., "Spotify", "Rotten Tomatoes", "Fed Rate"), the badges match the actual market content
- [ ] **No greedy classification**: Markets that mention multiple topics (e.g., "Will Trump approve X economic policy?") are in the most relevant category, not a random one

*If you find a misclassified market, note its name, where it appears, and where it should appear.*

---

#### D. Data Quality & Probabilities

- [ ] **Probabilities show % signs**: All probability values have "%" suffix (not bare numbers like "30")
- [ ] **Multi-outcome markets sum reasonably**: For markets with 3+ outcomes, probabilities sum to approximately 100% (between 90% and 110%)
- [ ] **Binary markets are complementary**: Yes/No markets where both sides are shown should sum to ~100%
- [ ] **Threshold markets are monotonic**: For "Over X" threshold ladders (e.g., "Fed rate ≥ 4.25", "≥ 4.50", "≥ 4.75"), probabilities decrease as threshold increases
- [ ] **No negative probabilities**: No probability values < 0%
- [ ] **No >100% probabilities**: No probability values > 100%
- [ ] **Outcome names are readable**: No truncated labels, no raw ticker IDs, no garbled text

---

#### E. Hero / Trending Section

- [ ] **Hero section has content**: The top of the page shows featured/trending markets (not empty)
- [ ] **Hero markets are genuinely interesting**: Featured markets have significant trading volume, recent movement, or public interest — not obscure commodity ladders or dated buckets
- [ ] **Hero visual renders correctly**: Images/gradients/cards display properly (no broken images, no placeholder text)
- [ ] **Hero is diverse**: The hero section doesn't show 5 markets about the same narrow topic

---

#### F. Visual Design & Layout

- [ ] **Light mode only**: White/light backgrounds, no dark mode elements
- [ ] **Consistent card styling**: All market cards follow the same visual pattern
- [ ] **No overlapping text**: Labels, values, and badges don't overlap
- [ ] **Responsive on mobile (375px)**: Page renders correctly at mobile width without horizontal overflow
- [ ] **Section headers are clear**: Each sub-section has a visible title that explains what's in it
- [ ] **Sparklines/charts render**: Any inline charts or sparklines display correctly (not blank rectangles)
- [ ] **Heatmaps/grids readable**: If threshold groups are shown as heatmaps (e.g., RT scores, Fed rates), cells are readable and color-coded

---

#### G. Navigation & Interaction

- [ ] **Accessible from main nav**: The category page is reachable from the site's main navigation
- [ ] **Back navigation works**: After clicking into a market detail, you can navigate back to the category page
- [ ] **Filter/tab controls work**: If the page has filter chips or tab controls, they work and filter correctly
- [ ] **Click-through to detail**: Clicking a market card leads to a working detail page (not 404 or blank)

---

### Step 2: Cross-Reference Upstream Coverage

For each category, visit the upstream source sites and check what bainluck is MISSING:

#### Politics
Go to **kalshi.com** → Politics/Elections section. Find 5 active markets. Check if each appears on bainluck.com/politics.
Go to **polymarket.com** → search for "election", "president", "congress". Find 3 active markets. Check if each appears.

#### Entertainment
Go to **kalshi.com** → search for "Spotify", "Rotten Tomatoes", "box office", "Grammy", "Oscar", "Emmy". Find 5 active markets. Check bainluck.
Go to **polymarket.com** → search for "movie", "music", "awards", "streaming". Find 3 active markets. Check bainluck.

#### Economics
Go to **kalshi.com** → Economics section (Fed rate, GDP, CPI, unemployment, oil, S&P). Find 5 active markets. Check bainluck.
Go to **polymarket.com** → search for "recession", "GDP", "inflation", "Fed". Find 3 active markets. Check bainluck.

#### Weather
Go to **kalshi.com** → Weather section (temperature, hurricane, rainfall). Find 5 active markets. Check bainluck.
Go to **polymarket.com** → search for "weather", "temperature", "hurricane". Find 3 active markets. Check bainluck.

For each market found upstream but MISSING from bainluck, record:
- Market name
- Source (Kalshi/Polymarket)
- Market URL
- Whether it's a new market type we don't support, or one we should already have

---

### Step 3: Design Comparison (Desktop + Mobile)

Take screenshots of each category page at:
1. **Desktop (1440px)** — full page scroll
2. **Mobile (375px)** — full page scroll

For each, evaluate:
- Does the page feel like a **polished product** or a **data dump**?
- Is there a clear **visual hierarchy** (hero → sections → detail)?
- Would a **non-expert** understand what the numbers mean?
- Is it **scannable** — can you quickly find the most interesting thing?

---

### Step 4: Report

```markdown
# Category Page Audit Report
**Date:** [today's date]
**Auditor:** Manus AI

## Summary
| Page | Health Score | Critical | Warning | Info |
|------|-------------|----------|---------|------|
| Politics | X/100 | N | N | N |
| Entertainment | X/100 | N | N | N |
| Economics | X/100 | N | N | N |
| Weather | X/100 | N | N | N |

## Politics Page (/politics)

### Data Freshness
| Check | Result | Notes |
|-------|--------|-------|

### Cross-Source Matching
| Kalshi Market | Polymarket Market | Bainluck Shows | Matched? |
|--------------|-------------------|----------------|----------|

### Classification Accuracy
| Check | Result | Notes |
|-------|--------|-------|

### Data Quality
| Check | Result | Notes |
|-------|--------|-------|

### Missing Markets (Coverage Gaps)
| Market | Source | URL | Should We Have It? |
|--------|--------|-----|-------------------|

### Design Observations
- [What works well]
- [What could be improved]
- [Screenshot links]

[Repeat for Entertainment, Economics, Weather]

## Cross-Cutting Findings
1. [Issues that affect multiple category pages]
2. [Patterns worth addressing systematically]

## Top 5 Actionable Improvements
1. [Most impactful fix, with specific market/page/section reference]
2. ...
```

## Scoring Rubric

- **CRITICAL** (-10): Page broken/blank, markets in completely wrong category, probabilities obviously wrong
- **WARNING** (-3): Stale/resolved markets still featured, missing cross-source matching, classification errors
- **INFO** (-1): Minor polish, design suggestions, edge-case formatting
- Start at 100, subtract per finding. Floor at 0.

## Notes for Future Categories

This audit module is designed to work for any new category page added to bainluck.com. When a new category launches:
1. Add it to the list in Step 1
2. Add upstream source checks in Step 2
3. Run this module — no prompt changes needed beyond adding the new URL
