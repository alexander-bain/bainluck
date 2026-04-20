# Claude Design Prompts for Bain Luck

## Setup (do this once)

1. Connect GitHub repo: `https://github.com/alexander-bain/bainluck`
2. Import these context files from the repo:
   - `docs/claude-design-context.md` — design system, product description, constraints
   - `docs/weather-market-inventory.md` — real market data (for weather prompt)
3. Optionally also import `frontend/app/globals.css` and `frontend/app/design-tokens.css` for exact color tokens

Then paste any prompt below. Each prompt is self-contained but references the imported context.

---

## Prompt 1: Weather Page

Design a weather probability page for bainluck.com. See the imported `weather-market-inventory.md` for the REAL market data — every example below is a real market that exists right now.

This site translates prediction market odds into simple probabilities. Light mode only, clean modern aesthetic (see imported context file). Data comes from Kalshi and Polymarket prediction markets — NOT weather.gov. There are currently 521 active weather markets.

**Section 1 — Hero: "What's the weather betting on?"**
A featured question that rotates daily. Real examples:
- "Will it rain in NYC tomorrow?" → 72% (Kalshi)
- "Will 2026 be the hottest year ever?" → 38% (Kalshi)
- "Category 4 hurricane hits the US this year?" → 36% (Polymarket)

**Section 2 — Global Temperature Map**
This is the core feature. Polymarket runs daily "Highest temperature in [City] on [Date]?" markets for 50 global cities, each with 11 outcome buckets (e.g., "68-69°F", "70-71°F"). Kalshi has the same for 20 US cities plus high AND low temps. Design a world map with city pins — tapping a city shows the probability distribution for tomorrow's high as a bar chart or histogram. Pin color = current predicted temp (blue→amber→red gradient). 11 cities have both Kalshi + Polymarket data (show cross-source badge). This is structured prediction data that lends itself beautifully to a map.

Real data for the map (April 20, 2026):
- NYC: 50-51°F most likely (33%), from Polymarket
- Los Angeles: 68-69°F most likely (37%), from Polymarket  
- Miami: 82-83°F most likely (42%), from Polymarket
- London: 13°C most likely (46%), from Polymarket
- Tokyo: 23°C most likely (40%), from Polymarket
- Lucknow: 41°C most likely (36%), from Polymarket — one of the hottest cities

**Section 3 — NYC Rain Forecast**
Kalshi runs "Will it rain in NYC on [Date]?" markets daily for ~1 week forward. This is the most relatable prediction market data on the planet. Show it as a simple 7-day strip:
- Mon: 72% ☔ | Tue: 66% 🌧️ | Wed: 34% ⛅ | Thu: 100% ☔ | Fri: 35% ⛅ | Sat: 100% ☔ | Sun: 74% 🌧️
Rain is currently NYC-only. Also show monthly rainfall totals for 10 US cities (e.g., "Rain in Denver in April?" → Above 1 inch: 34%).

**Section 4 — Natural Events Tracker**
Group these real markets into a dramatic section:

Hurricane Season:
- "Will a hurricane form by May 31?" → 21% (Polymarket)
- "Cat 4 hurricane hits US before 2027?" → 36% (Polymarket)
- "Major Atlantic hurricanes in 2026?" → Above 0: 80% (Kalshi)

Earthquakes:
- "Megaquake by June 30?" → 18% (Polymarket)
- "8.0 earthquake in California before 2027?" → 8% (Kalshi)
- "8.0 earthquake in Japan before 2030?" → 50% (Kalshi)
- "9.0+ earthquake before 2027?" → 10% (Polymarket)

Tornadoes:
- "How many tornadoes in the US in 2026?" → 1250+: 60% (Polymarket)

**Section 5 — Climate Dashboard**
Slow-changing, evergreen markets:
- "Will any month of 2026 be the hottest on record?" → 78% (Polymarket)
- "Will 2026 be the hottest year ever?" → 29-38% (Kalshi)
- "CO2 above 440 ppm before 2030?" → 88% (Kalshi)
- "World passes 2°C over pre-industrial before 2050?" → 78% (Kalshi)
- "US meets climate goals by 2030?" → 16% (Kalshi)
- "EU meets 2030 climate goals?" → 44% (Kalshi)

**Section 6 — Wild Cards**
Low-probability dramatic events:
- "Supervolcano before 2050?" → 21% (Kalshi)
- "Min Arctic sea ice <4M sq km this summer?" → 43% (Polymarket)
- "Major solar storm by April 30?" → 3% (Polymarket)

**What does NOT exist (don't design for these):**
No wind speed, humidity, air quality, drought, wildfire, lightning, UV, ski conditions, or pollen markets. Rain daily forecasts are NYC-only. No specific storm tracking ("Will Hurricane X hit Florida?").

Card design: white (#FFFFFF) bg, thin border (#E5E7EB), question in plain English, probability in JetBrains Mono (large), sparkline trend, source badge (Kalshi green #22C55E or Polymarket blue #3B82F6), resolution date. Page bg: #F5F5F7. Text: #111827 / #6B7280 / #9CA3AF.

Make it feel like a beautiful weather app that happens to be powered by prediction markets, not a trading platform. Reference `frontend/app/page.tsx` in the connected GitHub repo for responsive patterns.

---

## Prompt 2: Entertainment Page

Design an entertainment predictions page for bainluck.com.

This site translates prediction market odds into probabilities. Light mode only, clean design (see imported context file for full design system). Data from Kalshi and Polymarket.

Sections:
1. Awards Season hero: Current/next major awards show (Oscars, Emmys, Grammys, Golden Globes) with top 5 nominees shown as a horizontal bar race chart — each bar shows nominee name, headshot, and win probability percentage. The probability number should be large and in monospace font.
2. Box Office predictions: "Will Wicked 2 gross $200M opening weekend?" → 42%. Show movie poster alongside the probability. Card grid, 2-3 per row on desktop.
3. TV & Streaming: Show renewal/cancellation probabilities ("Stranger Things renewed?" → 89%), reality TV outcomes. Clean card grid.
4. Music: Grammy predictions, album milestones, tour sellouts.

Each card: white background (#FFFFFF), thin border (#E5E7EB), question in plain English, large probability in JetBrains Mono, sparkline of probability trend (thin line on white, like DataGolf's evolution plot style), source badge (Kalshi or Polymarket), resolution timeframe.

Use rich media (movie posters, headshots, album art) as visual anchors. This page should feel like browsing an entertainment magazine that happens to show prediction data, not a sportsbook. Page bg: #F5F5F7. Brand accent: #10B981 emerald. Purple (#8B5CF6) for prediction market indicators.

The awards section should be a reusable component — same layout works for Oscars, Emmys, Grammys, just swap data.

Reference the existing site at bainluck.com and the connected GitHub repo for design patterns.

---

## Prompt 3: Politics Page

Design a politics probability page for bainluck.com.

CRITICAL: This must feel neutral, informational, and non-partisan — like a weather forecast for politics, not a political opinion site. NO red/blue party coloring anywhere.

This site translates prediction market odds into probabilities. Light mode only (see imported context). Data from Polymarket and Kalshi.

Sections:
1. Elections hero: Next major election with candidates shown side-by-side, each with a large probability percentage (JetBrains Mono font) and a trend line showing how odds moved over time (thin lines on white grid). Use candidate photos but neutral color palette — slate (#475569), charcoal (#374151), warm gray (#78716C). NO red or blue.
2. Policy Markets: "Will the Fed cut rates in June?" → 45%. Cards grouped by category (Economy, Foreign Policy, Regulation, Appointments). Each card: question, probability, sparkline, source badge.
3. Approval & Sentiment: Prediction markets on approval rating thresholds, shown as gauge-style indicators.
4. Congressional: Individual race probabilities if available, shown as a table or card grid.

Card design: white (#FFFFFF) background, thin border (#E5E7EB), question as title, probability as hero number. Page bg: #F5F5F7. Text: #111827 primary, #6B7280 secondary.

The page should feel like The Economist or FiveThirtyEight — serious, informational, data-driven. Show ALL sides with equal visual weight. Probability is the hero, not the candidates.

Reference the connected GitHub repo (alexander-bain/bainluck) for existing design patterns.

---

## Prompt 4: Finance & Crypto Page

Design a financial markets probability page for bainluck.com.

NOT a trading platform — this shows "what the crowd thinks will happen" in plain language. Light mode only (see imported context). Data from Kalshi.

Sections:
1. Hero dashboard: 3-4 featured questions as large stat cards — "S&P 500 above 6,000 by year-end?" → 58%, "Fed rate cut in June?" → 43%, "Bitcoin above $100K?" → 71%, "Recession in 2026?" → 22%. Each card: white bg, thin border, question, large monospace probability, small trend sparkline.
2. Interest Rates: Fed meeting timeline — horizontal timeline with FOMC dates as nodes, each showing stacked probability bars for cut/hold/hike.
3. Crypto: Top 5 crypto price threshold markets with probability trend charts (thin colored lines on white grid).
4. Economic Indicators: GDP, inflation, unemployment markets as a clean card grid.
5. Commodities: Oil, gold price threshold markets.

Typography: Inter for text, JetBrains Mono for all numbers. Colors: page bg #F5F5F7, cards white, text #111827/#6B7280/#9CA3AF. Green (#22C55E) for growth/up indicators, amber (#F59E0B) for flat, red (#EF4444) for contraction. Purple (#8B5CF6) for prediction market source badges.

Aesthetic: Think Bloomberg Terminal reimagined as a clean, light-mode weather app. Thin gridlines, monospace numbers, subtle color coding. No trading jargon — everything in plain English questions.

Reference the connected GitHub repo for existing component patterns.

---

## Prompt 5: World Events Page

Design a world events probability page for bainluck.com.

This site shows prediction market probabilities for geopolitical, scientific, and cultural events. Light mode only (see imported context). Data from Polymarket and Kalshi.

Sections:
1. "Big Questions" hero: 3-5 major questions with large probability displays and trend charts — e.g., "Ukraine ceasefire by 2026?" → 34%, "SpaceX crewed Mars mission by 2030?" → 8%, "AGI by 2030?" → 15%. Each with a thin-line probability trend chart.
2. Science & Tech: "SpaceX Starship orbital success?", "FDA approves [drug]?", "AGI by 2030?" — shown as a visual timeline of upcoming predicted events with probability bars.
3. Geopolitical: Trade deals, treaty outcomes, leadership changes — card grid with question/probability/trend.
4. Climate & Environment: Paris Agreement targets, temperature records, renewable energy milestones.

Card design: white (#FFFFFF) bg, thin border (#E5E7EB), question, probability in JetBrains Mono, sparkline, source badge (Polymarket blue #3B82F6 or Kalshi green #22C55E), one-line context note. Page bg: #F5F5F7.

Use a subtle globe or world map as a background element in the hero. Tone: The Economist — serious, informational, globally-minded. NO sensationalism, no alarming colors for geopolitical events.

Reference the connected GitHub repo for design system consistency.

---

## Prompt 6: Categories Hub Page

Design a categories hub page for bainluck.com — the "browse everything" entry point.

This site shows prediction market probabilities across sports, weather, politics, entertainment, finance, and world events. Light mode only (see imported context).

Layout:
1. "What are the odds?" hero with a large featured question from any category, showing question + probability + trend sparkline + category badge.
2. Category grid with REAL market counts: Politics (3,095 markets), Entertainment (1,087), Economics/Finance (1,023), Weather (521), Geopolitics (286), Tech (279), Sports (use total from existing sports data). Each card: category icon, name, exact active market count, one featured question with probability. White bg, thin border.
3. Trending: Top 10 most-active markets across ALL categories as a ranked list. Each row: rank, question, category tag pill, probability, 24h change arrow (green up / red down).
4. "Just Resolved": Recently answered questions showing "Market said 72% → Actually happened ✓" or "Market said 85% → Did NOT happen ✗". Calibration showcase.

Page bg: #F5F5F7. Cards: white. Text: #111827 → #6B7280 → #9CA3AF. Brand: #10B981 emerald. Each category card should hint at its domain (weather icon, globe, film reel, chart) while using consistent card design.

This is the front door — a first-time visitor should instantly understand what Bain Luck does.

Reference the connected GitHub repo (alexander-bain/bainluck) for existing page layouts and component patterns.

---

## Prompt 7: Shared Market Card Component

Design a reusable prediction market card component for bainluck.com that works across ALL categories. Light mode only (see imported context).

The card displays:
- Plain-English question ("Will it snow in NYC this week?")
- Hero probability number (73%) in JetBrains Mono, large and prominent
- Small sparkline chart (7-day probability trend, thin line on white)
- Source badge(s): Kalshi (green #22C55E bg), Polymarket (blue #3B82F6 bg), or both
- Category tag: small colored pill (Sports, Weather, Politics, etc.)
- Resolution timeframe: "Resolves in 3 days" or "Resolves June 2026"
- Optional contextual image: team logo, movie poster, weather icon, candidate photo

Card: white (#FFFFFF) bg, 1px border (#E5E7EB), 12px rounded corners, 16px padding. Probability is ALWAYS the visual hero — largest element.

Show 5 variants with REAL market data (these markets exist right now):
1. Weather: "Will it rain in NYC tomorrow?" → 72%, Kalshi, resolves tomorrow
2. Politics: "Virginia redistricting referendum passes?" → 86%, Polymarket, resolves Nov
3. Entertainment: "#1 Free App in US App Store tomorrow?" → ChatGPT: 84%, Polymarket, resolves tomorrow
4. Finance: "Meta closes above $660 on Monday?" → 86%, Polymarket, resolves Mon
5. Weather: "Cat 4 hurricane hits US before 2027?" → 36%, Polymarket, resolves Dec 31

All 5 must look like the same design system. Same dimensions, typography, spacing. Only category tag color and image differ.

Reference `frontend/components/FeedCard.tsx` in the connected GitHub repo for the existing card pattern.

---

## Recommended Order
1. **#7 (Shared Market Card)** — establish the design language first
2. **#6 (Categories Hub)** — the entry point
3. **#1 (Weather)** — most intuitive non-sports expansion
4. **#3 (Politics)** — biggest Polymarket vertical
5. **#2 (Entertainment)** — builds on existing Oscars work
6. **#4 (Finance)** — natural Kalshi content
7. **#5 (World Events)** — round out the vision
