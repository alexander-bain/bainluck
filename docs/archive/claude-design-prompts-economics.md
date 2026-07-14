# Claude Design Prompt: Economics Dashboard Page

## Context

Bain Luck (bainluck.com) is a visual-first sports odds experience that translates betting markets into intuitive win probabilities. We're expanding beyond sports into non-sports prediction markets. We just shipped a weather page and now want to build an economics dashboard — think "Bloomberg terminal for normies" using prediction market data from Kalshi and Polymarket.

**Design system:** Light mode only. Clean, minimal, lots of white space. Design tokens in `globals.css`: `bg-surface-card` for cards, `text-text-primary` / `text-text-secondary` / `text-text-muted` for text hierarchy, `border-surface-border` for borders, `text-accent-brand` for emphasis. See existing pages at bainluck.com for the visual language.

**Reference:** See bainluck.com/categories/weather for the weather page we just shipped — the economics page should follow a similar pattern but with sub-themes appropriate to economic data.

## Page Purpose

A single page at `/categories/economics` that aggregates economic prediction markets from Kalshi and Polymarket into a consumable dashboard. Users should be able to glance at the page and immediately understand: What do markets think about inflation? Is a rate cut coming? How likely is a recession?

## Sub-theme Sections

The page should be organized into these sections, each with its own visual treatment. Every section pulls from real prediction market data — these are actual Kalshi and Polymarket markets.

### 1. Hero / Dashboard Summary
A top-level "at a glance" row of 4-6 key economic indicators, each showing the market-implied probability or value. Think: the numbers a finance person checks every morning.
- **Fed rate direction** — "64% chance of June rate cut" (from Kalshi `kxfedfunds*` markets)
- **Recession probability** — "23% chance of recession in 2026" (from Kalshi `kxrecession*` + Polymarket)
- **Inflation trajectory** — "72% chance CPI stays below 3%" (from Kalshi `kxcpi*` + Polymarket)
- **Unemployment** — "Markets say 4.1%" (from Kalshi `kxunemployment*`)
- **Gas prices** — "$3.42 most likely" (from Kalshi `kxgasprice*`)
- **S&P 500 direction** — "Today: 58% up" (from Polymarket daily market)

### 2. Federal Reserve & Interest Rates
The most actively traded economic markets. Rich trend data.

**Markets available:**
- Kalshi: Fed funds rate per meeting (Jan, Mar, May, Jun, Jul, Sep, Nov, Dec 2026) — each has 5-8 rate bracket outcomes
- Kalshi: Number of rate cuts in 2026 (brackets: 0, 1, 2, 3, 4+)
- Kalshi: Number of rate hikes in 2026
- Polymarket: ECB rate decisions by meeting date
- Kalshi: What will Powell say during press conference (sentiment market)

**Design ideas:** Timeline visualization showing the market-implied rate path across 2026. Each FOMC meeting date as a node, with the probability distribution of rate outcomes. Think "dot plot but from markets, not the Fed."

### 3. Inflation & Consumer Prices
Monthly data release cadence creates natural urgency.

**Markets available:**
- Kalshi: Monthly CPI brackets (above/below 2.5%, 3.0%, 3.5%, etc.) — one market per month
- Kalshi: PCE (Fed's preferred measure) readings
- Kalshi: Argentina monthly inflation (international comparison)
- Polymarket: Inflation above/below thresholds for 2026
- Kalshi: Consumer sentiment / confidence levels

**Design ideas:** Calendar-style layout where each upcoming CPI release date has a probability gauge. Show how market expectations shifted over time as data came in.

### 4. Jobs & Employment
Monthly reports, frequent revisions, politically charged.

**Markets available:**
- Kalshi: Unemployment rate brackets (quarterly readings)
- Kalshi: Weekly initial jobless claims (above/below thresholds)
- Kalshi: Nonfarm payroll direction
- Kalshi: Nonfarm productivity YoY
- Polymarket: Jobs report outcomes

### 5. GDP & Recession
The big macro question.

**Markets available:**
- Kalshi: Quarterly GDP growth brackets (Q1, Q2, Q3, Q4 2026)
- Kalshi: Will there be a recession in 2026? (Y/N)
- Kalshi: Consecutive negative GDP quarters?
- Polymarket: Recession timing markets
- Polymarket: GDP growth thresholds

**Design ideas:** A single bold "Recession Probability" gauge as the hero, with quarterly GDP expectations as supporting detail.

### 6. Markets & Indices
Daily/weekly resolution — highest velocity markets.

**Markets available:**
- Kalshi: Nasdaq-100 daily close price brackets (5-8 brackets per day)
- Kalshi: Nasdaq-100 weekly range
- Kalshi: S&P 500 daily/weekly targets
- Kalshi: VIX level brackets
- Polymarket: Nasdaq daily up/down
- Polymarket: Individual stock daily up/down (Meta, Apple, Tesla, etc.)
- Polymarket: Weekly range targets (QQQ, SPY)

**Design ideas:** These resolve daily, so show today's market expectation prominently with a simple up/down/range visualization. Archive yesterday's results.

### 7. Energy & Commodities
Gas prices are universally understood economic indicators.

**Markets available:**
- Kalshi: US national gas price — how high/low will it go in 2026? (brackets)
- Kalshi: California gas prices (separate brackets)
- Kalshi: WTI crude oil daily price brackets
- Kalshi: Brent crude oil daily price brackets
- Polymarket: Oil price thresholds

### 8. Housing & Mortgages
Directly impacts consumer decisions.

**Markets available:**
- Kalshi: 30-year mortgage rate — how high/low in 2026? (brackets)
- Polymarket: Will 30-year mortgage rate hit [X]% in 2026?
- Kalshi: Case-Shiller home price direction

### 9. Trade & Tariffs
Current events driven — tariff policy is the economic story of 2026.

**Markets available:**
- Kalshi: Tariff-related policy outcomes
- Kalshi: Trade war escalation/de-escalation markets
- Polymarket: Specific tariff policy markets
- Both: Impact on specific sectors/countries

### 10. Government & Fiscal
Debt ceiling, shutdowns, spending.

**Markets available:**
- Kalshi: Government shutdown probability + duration
- Kalshi: Will the debt ceiling be abolished?
- Polymarket: Shutdown probability
- Polymarket: DOGE savings milestones

## Design Directions to Explore

I'd love to see 2-3 different approaches to the overall page structure:

**Direction A: News Dashboard** — Like a financial news homepage. Grid of cards, each sub-theme is a card cluster. Dense, scannable, information-rich. Hero stats across the top.

**Direction B: Story Flow** — Vertical scroll, each sub-theme is a full-width section with a narrative arc. "Here's what markets think about the economy right now" told as a story with supporting data.

**Direction C: Interactive Terminal** — Darker aesthetic (our only exception to light mode?), dense data tables with sparklines, customizable layout. For the finance-interested power user.

## Important Notes

- **NEVER show American odds** (+425, -150, etc.). Only show probabilities and percentages. This is the core product philosophy.
- All data comes from Kalshi and Polymarket prediction markets — show source attribution clearly.
- Markets resolve on different timescales: daily (stocks), monthly (CPI), quarterly (GDP), annual (recession). The design needs to handle this gracefully.
- New markets appear and old ones resolve constantly. The design should accommodate variable density per section without looking empty or overloaded.
- Cross-source aggregation is a key value prop — when both Kalshi and Polymarket have the same market, show the merged probability with source breakdown available on click/hover.
- Mobile-first: many users will check this on their phone during their commute.
- The weather page at bainluck.com/categories/weather is the closest reference — similar structure, different content.

## Deliverable

Wireframes or mockups for the economics dashboard page showing:
1. Overall page layout with sub-theme sections
2. Hero/summary section with key economic indicators
3. Detail treatment for at least 2 sub-themes (suggest Fed rates + Inflation since they have the richest data)
4. Mobile layout
5. How resolved markets are handled (e.g., yesterday's CPI reading)
6. How the page looks when a sub-theme has few active markets vs many
