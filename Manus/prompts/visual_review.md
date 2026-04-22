# Module 5: Visual Design Review

## Goal

Evaluate the visual design quality of bainluck.com's key pages. Identify polish issues, accessibility concerns, and suggest specific improvements. Compare against best-in-class sports data sites.

## Context

Bain Luck's design philosophy:
- **Light mode only** — white backgrounds, clean gridlines, no dark mode
- **Probability-first** — every number is a percentage, not a betting line
- **Casual sports fan target** — not for degenerate bettors, for people watching games who want context
- **Clean and uncluttered** — DataGolf's evolution plot is the gold standard for chart design

Design tokens (from CSS): `bg-surface-card`, `text-text-primary`, `text-text-secondary`, `text-text-muted`, `border-surface-border`, `text-accent-live`, `text-accent-brand`, `text-accent-danger`.

## Instructions

### Step 1: Screenshot Key Pages

Visit and screenshot (full page, desktop 1440px) each of these:
1. **Home feed** — bainluck.com
2. **Event detail** (live game) — click any live event
3. **Event detail** (upcoming game) — click any upcoming event
4. **Championship grid** — /playoffs/nba
5. **Golf category** — /categories/golf
6. **Weather** — /weather
7. **Economics** — /economics

Also capture mobile (375px) versions of pages 1, 2, and 4.

### Step 2: Evaluate Each Page

For each page, assess these dimensions (score 1-5 each):

#### Typography & Readability (1-5)
- Font sizes create clear hierarchy (headings > body > captions)
- Line lengths are comfortable (45-75 characters)
- Sufficient contrast between text and background
- Numbers are formatted consistently (commas, decimals, % signs)

#### Color & Branding (1-5)
- Consistent color palette across pages
- Team colors used effectively (not garish or clashing)
- Accent colors (live indicators, brand elements) are distinctive
- No dark backgrounds or dark mode leaks
- Color blind friendly (don't rely on red/green alone)

#### Layout & Spacing (1-5)
- Adequate whitespace between sections
- Cards/components have consistent padding
- No cramped or overly sparse areas
- Grid alignment is clean (items line up)
- Responsive: no horizontal overflow on any viewport

#### Chart Quality (1-5)
- Axis labels are readable and correctly positioned
- Legends are clear and don't overlap chart area
- Gridlines are subtle (thin, light gray)
- Data lines are distinguishable by color
- Tooltips/hovers work and show useful info
- Compare against DataGolf's chart style as the gold standard

#### Information Density (1-5)
- Right amount of info per screen (not overwhelming, not empty)
- Important data is prominent, secondary data is subtle
- Progressive disclosure works (can drill into details)
- No redundant information (same number shown twice)

#### Polish & Attention to Detail (1-5)
- Loading states are clean (skeleton screens, not spinners)
- Transitions/animations are smooth (if present)
- Icons and logos render crisply
- No broken images, missing assets, or placeholder text
- Consistent component styling (buttons, cards, tables all match)

### Step 3: Competitive Comparison

Briefly compare bainluck.com's design against:
- **ESPN** (espn.com game pages) — chart quality, game state presentation
- **FanDuel** (fanduel.com/research) — odds presentation, market organization
- **DataGolf** (datagolf.com) — chart design, data density

Note: We're not trying to copy these sites. We're identifying where they do something better that we should learn from.

### Step 4: Report

```markdown
# Visual Design Review Report
**Date:** [today's date]

## Page Scores

| Page | Typography | Color | Layout | Charts | Density | Polish | Average |
|------|-----------|-------|--------|--------|---------|--------|---------|
| Home feed | X/5 | X/5 | X/5 | — | X/5 | X/5 | X.X |
| Event (live) | X/5 | X/5 | X/5 | X/5 | X/5 | X/5 | X.X |
| ... | ... | ... | ... | ... | ... | ... | ... |
| **Overall** | | | | | | | **X.X** |

## Per-Page Analysis

### Home Feed
**Score: X.X / 5.0**
- Strengths: [what works well]
- Issues: [specific problems with screenshots]
- Improvements:
  1. [Specific, actionable suggestion]
  2. [Specific, actionable suggestion]
  3. [Specific, actionable suggestion]

[Repeat for each page]

## Competitive Comparison
| Dimension | Bain Luck | ESPN | FanDuel | DataGolf |
|-----------|----------|------|---------|----------|
| Chart quality | X/5 | X/5 | X/5 | X/5 |
| Data density | X/5 | X/5 | X/5 | X/5 |
| Overall polish | X/5 | X/5 | X/5 | X/5 |

Key takeaways from competitors:
1. [What they do better]
2. [What they do better]
3. [What we do better than them]

## Top 10 Design Improvements (Prioritized)
1. [Highest impact, lowest effort first]
2. ...
10. ...

## Accessibility Notes
- [Any contrast issues, missing alt text, keyboard navigation problems]

## Screenshots
[Attached for each page, desktop + mobile]
```
