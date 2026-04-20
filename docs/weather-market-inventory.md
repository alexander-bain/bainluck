# Weather Market Inventory — Real Data (April 19, 2026)

Import this file into Claude Design alongside `docs/claude-design-context.md` when designing the weather page. Everything in this doc is REAL — these markets exist right now.

---

## Summary

**521 active weather markets** across Kalshi (397) and Polymarket (124). Markets refresh daily with a ~1 week forward window for temperatures, plus longer-horizon seasonal and climate markets.

---

## Market Categories

### 1. Daily Temperature — High & Low (420 markets, ~80% of total)

**Polymarket** runs "Highest temperature in [City] on [Date]?" for **50 global cities**, each with 11 outcome buckets (e.g., "68-69°F", "70-71°F", "72°F or higher"). New markets created daily, resolving next-day. ~5 days forward.

**Kalshi** runs both "Highest temperature" and "Lowest temperature" for **20 US cities**, each with 6 outcome buckets. Same daily cadence. Also runs **NYC hourly temperature** markets every 4 hours (unique).

#### Polymarket Cities (50)
Amsterdam, Ankara, Atlanta, Austin, Beijing, Buenos Aires, Busan, Cape Town, Chengdu, Chicago, Chongqing, Dallas, Denver, Guangzhou, Helsinki, Hong Kong, Houston, Istanbul, Jakarta, Jeddah, Karachi, Kuala Lumpur, Lagos, London, Los Angeles, Lucknow, Madrid, Manila, Mexico City, Miami, Milan, Moscow, Munich, NYC, Panama City, Paris, San Francisco, São Paulo, Seattle, Seoul, Shanghai, Shenzhen, Singapore, Taipei, Tel Aviv, Tokyo, Toronto, Warsaw, Wellington, Wuhan

#### Kalshi US Cities (20)
Atlanta, Austin, Boston, Chicago, Dallas, Denver, Houston, LA, Las Vegas, Miami, Minneapolis, New Orleans, NYC, Oklahoma City, Philadelphia, Phoenix, San Antonio, San Francisco, Seattle, Washington DC

#### Overlap Cities (both sources)
Atlanta, Austin, Chicago, Dallas, Denver, Houston, LA/Los Angeles, Miami, NYC, San Francisco, Seattle

**Design implication**: Temperature markets are structured prediction data — each is a probability distribution across temperature buckets. This lends itself to a **map view** with city pins, where tapping a city shows the probability distribution for tomorrow's high. The global Polymarket coverage makes a world map compelling. The overlap cities could show cross-source comparison.

---

### 2. Rain & Precipitation (19 markets)

**Daily rain yes/no** (Kalshi, NYC only):
- "Will it rain in NYC on Apr 14?" → 72% Yes
- "Will it rain in NYC on Apr 15?" → 66% Yes
- ... through Apr 20 (1 week forward)

**Monthly rainfall totals** (Kalshi, 10 US cities):
- "Rain in NYC in Apr 2026?" → Above 1 inch: 92%
- "Rain in Denver in Apr 2026?" → Above 1 inch: 34%
- "Rain in Los Angeles in Apr 2026?" → Above 1 inch: 10%
- Also: Austin, Chicago, Dallas, Houston, Miami, San Francisco, Seattle

**Monthly precipitation** (Polymarket, 3 cities):
- "Precipitation in London in April?" → <20mm: 85%
- "Precipitation in NYC in April?" → <2": 62%
- "Precipitation in Seattle in April?" → 2.5-3": 44%

**Design implication**: The NYC daily rain markets are the most relatable weather prediction on the platform — "72% chance of rain tomorrow." Simple, useful, shareable. Monthly rainfall totals are a secondary view. Limited to NYC for daily, 10 US cities for monthly.

---

### 3. Hurricane Season (6 markets)

- "Will a hurricane form by May 31?" → 21% Yes (Polymarket)
- "Will a hurricane make landfall in the US by May 31?" → 8% Yes (Polymarket)
- "Will any Category 4 hurricane make landfall in the US before 2027?" → 36% Yes (Polymarket)
- "Will any Category 5 hurricane make landfall in the US before 2027?" → 15% Yes (Polymarket)
- "Number of tropical storms in 2026?" → Above 10: 78% (Kalshi)
- "How many Atlantic hurricanes will there be in 2026?" → Above 4: 82% (Kalshi)
- "How many major Atlantic hurricanes will there be in 2026?" → Above 0: 80% (Kalshi)

**Design implication**: Perfect for a "Hurricane Season Tracker" section — a timeline from now through December with probability milestones. Seasonal content that gets dramatically more interesting June–November.

---

### 4. Earthquakes (11 markets)

**Weekly counts**:
- "How many 6.5+ earthquakes Apr 20-26?" → 0: 48% (Polymarket)
- "How many 5.5+ earthquakes Apr 20-26?" → >9: 40% (Polymarket)

**Milestone/threshold**:
- "Megaquake by June 30?" → 18% (Polymarket)
- "Another 7.0+ earthquake by April 30?" → 37% (Polymarket)
- "9.0+ earthquake before 2027?" → 10% (Polymarket)
- "8.0 earthquake in California before 2027?" → 8% (Kalshi)
- "8.0 earthquake in California before 2028?" → 13% (Kalshi)
- "8.0 earthquake in Japan before 2030?" → 50% (Kalshi)

**Annual counts**:
- "How many 7.0+ earthquakes in 2026?" → 14-16: 28% (Polymarket)
- "How many 7.0+ earthquakes by June 30?" → 8+: 84% (Polymarket)

**Design implication**: Dramatic, attention-grabbing content. The California 8.0 and megaquake markets are the kind of "what are the odds?" content that drives shares. Great for a "Seismic Activity" card or section.

---

### 5. Tornadoes (3 markets)

- "Number of tornadoes in Apr 2026?" → Above 50: 100% (Kalshi, resolved)
- "How many Tornadoes in the US in April?" → 170-199: 32% (Polymarket)
- "How many Tornadoes in the US in 2026?" → 1250+: 60% (Polymarket)

**Design implication**: Seasonal — most relevant March–June. Could pair with a map showing tornado alley.

---

### 6. Climate & Records (10+ markets)

**Hottest on record**:
- "This Feb 2026 is the hottest February ever?" → 2% (Kalshi)
- "This Mar 2026 is the hottest March ever?" → 2% (Kalshi)
- "This Apr 2026 is the hottest April ever?" → 6% (Kalshi)
- "Will any month of 2026 be the hottest on record?" → 78% (Polymarket)
- "Will 2026 be the hottest year ever?" → 29-38% (Kalshi, two markets)

**Long-term climate**:
- "How bad will CO2 atmospheric concentration get before 2030?" → At least 440 ppm: 88% (Kalshi)
- "EV market share in 2030?" → Above 10%: 87% (Kalshi)
- "India meets its 2030 climate goals?" → 66% (Kalshi)
- "EU meets its 2030 climate goals?" → 44% (Kalshi)
- "US meets its climate goals?" → By 2030: 16% (Kalshi)
- "Will the world pass 2°C over pre-industrial levels before 2050?" → 78% (Kalshi)

**Design implication**: Evergreen content that changes slowly — perfect for a "Climate Dashboard" section. "78% chance 2026 has the hottest month ever" is a headline-worthy stat. Long-term markets (2030, 2050) create a compelling "future of the planet" tracker.

---

### 7. Other / Exotic (5 markets)

- "Min Arctic sea ice extent this summer?" → <4m sq km: 43% (Polymarket)
- "Major solar storm by April 30?" → 3% (Polymarket)
- "How many major Space Weather events this week?" → <2: 38% (Polymarket)
- "How many large volcano eruptions (VEI ≥4) in 2026?" → 0: 55% (Polymarket)
- "Will a supervolcano erupt before 2050?" → 21% (Kalshi)
- "Flu Hospitalization Rate Week 15, 2026?" → 85-90: 76% (Polymarket)

**Design implication**: The exotic/rare-event markets are engagement gold — "21% chance of a supervolcano before 2050" is the kind of content people screenshot and share. Could be a "Wild Cards" or "Long Shots" section.

---

## What Does NOT Exist (don't design for these)

- No wind speed markets
- No humidity markets
- No air quality / AQI markets
- No drought markets
- No wildfire markets (currently)
- No lightning/thunderstorm markets
- No UV index markets
- No specific storm tracking (no "Will Hurricane X hit Florida?")
- No ski/snow resort markets
- No pollen/allergy markets
- Rain is NYC-only for daily predictions (10 cities for monthly totals)
- No "will it be sunny?" markets

---

## Suggested Page Sections (grounded in real data)

1. **Hero**: "What are the odds?" — featured weather question of the day. Rotate between rain probability, earthquake threshold, climate record, hurricane milestone.

2. **City Weather Map**: Global map with 50+ city pins. Tap a city → see probability distribution for tomorrow's high temperature. Pin size = uncertainty (wide distributions = bigger pin). Color = temperature (blue=cold, red=hot). Cross-source badge for overlap cities.

3. **Rain Forecast**: NYC daily rain probability for the next week. Simple, relatable, shareable. "72% chance of rain tomorrow in NYC."

4. **Natural Events Tracker**: Hurricane season timeline, earthquake counts, tornado season. Seasonal content that gets dramatic during active seasons.

5. **Climate Dashboard**: Hottest year/month tracker, CO2 levels, climate goal compliance. Slow-changing, evergreen, shareable.

6. **Wild Cards**: Supervolcano, megaquake, solar storms, Arctic ice. Low-probability dramatic events. The "whoa" section.
