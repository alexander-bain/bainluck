# Manus Site Sweep: Latency + UI Quality Audit (April 25, 2026)

## Context

Bain Luck (bainluck.com) just shipped a PREQ sprint — performance, reliability, efficiency, quality improvements. We need an independent audit to verify the improvements landed and find remaining issues.

## What to do

Visit every major page on bainluck.com as a **first-time mobile user (375px viewport)** AND as a **desktop user (1440px)**, measuring latency and noting UI issues.

### Part 1: Latency Audit

For each page below, measure and report:
- **Time to first content** (how long until something useful appears)
- **Time to interactive** (how long until you can scroll/click)
- **API response time** (check the `X-Response-Time` header in the Network tab for each API call — this is a new header we just added)
- **Cache behavior** (check `Cache-Control` headers — we just added these. Note which endpoints have them and which don't)

**Pages to test:**
1. Homepage feed (`bainluck.com`)
2. Event detail — click into a live or recent NBA/MLB game
3. NBA league page (`bainluck.com/sport/basketball/nba`)
4. MLB league page (`bainluck.com/sport/baseball/mlb`)
5. Golf page (`bainluck.com/categories/golf`)
6. Weather page (`bainluck.com/weather`)
7. Economics page (`bainluck.com/economics`)
8. Futures browser (`bainluck.com/futures`)
9. Championship grid (`bainluck.com/playoffs/nba`, `/playoffs/nhl`, `/playoffs/mlb`)
10. My Stuff page (`bainluck.com/my-stuff`) — note: requires sign-in, may show empty state

### Part 2: UI Quality Audit (Mobile — 375px viewport)

On each page, look for:
- **Readability issues** — text too small, too light, truncated, overlapping
- **Layout issues** — content cut off, horizontal scroll, elements overflowing
- **Chart issues** — axis labels too small, legends unreadable, data looks wrong
- **Touch targets** — buttons/links too small to tap accurately
- **Loading states** — spinners that last too long, content that pops in causing layout shift
- **Empty states** — pages that show nothing when they should show something
- **Data quality** — probabilities that don't make sense, wrong team names, stale data
- **Navigation** — can you easily get to every section? Is anything hidden or confusing?

### Part 3: UI Quality Audit (Desktop — 1440px)

Same checks as mobile, plus:
- **Whitespace** — too much? Too little? Content feels cramped or lost?
- **Card density** — feed cards too sparse or too packed?
- **Chart sizing** — charts appropriately sized for desktop viewport?
- **Header/nav** — everything fits in one row? No truncation?

### Part 4: Win Probability Chart Deep Dive

Go to a completed NBA playoff game (Celtics vs 76ers, April 24 is a good one if available). On the win probability chart:
- Are the **y-axis labels readable** on mobile?
- Does the **Kalshi line** show wild spikes (jumping from 80% to 5% and back)? If so, screenshot it.
- Is the **legend** clear enough to tell which line is which?
- Do the **period markers** (Q1, Q2, HT, Q3, Q4) look correct?
- Does the chart **extend past the game end**?

## How to report

For each finding, provide:
1. **Page URL**
2. **Screenshot** (annotated if possible)
3. **Severity**: CRITICAL (broken/unusable), HIGH (confusing/ugly), MEDIUM (suboptimal), LOW (nitpick)
4. **Category**: Latency, Layout, Data Quality, Readability, Navigation, Chart
5. **Description**: What you see and what you expected

## Expected findings

We recently shipped:
- Cache-Control headers on stable endpoints (feed, playoffs, golf, weather, economics)
- X-Response-Time header on every response
- SWR polling interval reductions (My Stuff 15s→60s, grouped feed 60s→120s)
- Redis feed caching for anonymous users (15s TTL)

We expect latency to be better than it was a week ago. We know about:
- Kalshi probability spikes on the win probability chart (investigating root cause)
- Y-axis labels being too small on mobile charts
- Some unclassified prediction markets in the data quality section

We want to know what ELSE you find that we haven't noticed yet.

## Format

Organize findings into two buckets:
1. **"Fix This" — issues that clearly need fixing** (data quality bugs, unreadable text, broken layouts)
2. **"Consider This" — subjective observations** (design preferences, information density, feature suggestions)

For the latency audit, provide a summary table of all measured times.
