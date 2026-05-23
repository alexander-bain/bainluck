# Handoff: Weather Probability Page (`/weather`)

## Overview
A new top-level page at `bainluck.com/weather` that translates Kalshi + Polymarket weather prediction markets into a consumer-friendly, probability-first experience. It should feel like a beautiful weather app that happens to be powered by prediction markets — **not** a trading platform.

The page has six sections:

1. **Hero** — rotating "featured weather question of the day"
2. **Global Temperature Map** — 50-city world map, each pin shows tomorrow's high-temp probability distribution (11 Polymarket buckets or 6 Kalshi buckets)
3. **NYC Rain Forecast** — 7-day daily rain strip (Kalshi, NYC-only) + April monthly rainfall totals for 10 US cities
4. **Natural Events Tracker** — hurricane season monthly strip, earthquake threshold markets, tornado counts
5. **Climate Dashboard** — long-horizon markets grouped by resolution year (2026 / 2030 / 2050)
6. **Wild Cards** — rare dramatic events (supervolcano, Arctic ice, solar storm, etc.)

---

## About the Design Files

The files in this bundle are **design references created in HTML** — a high-fidelity prototype showing the intended look, layout, and behavior. It is **not** production code to copy directly.

Your task is to **recreate this design in the bainluck Next.js codebase** at `frontend/app/weather/page.tsx`, using the project's existing patterns: Tailwind CSS, SWR for data fetching, the design tokens in `frontend/app/globals.css` and `frontend/app/design-tokens.css`, and the component conventions used in `frontend/app/page.tsx` and `frontend/components/*`.

## Fidelity

**High-fidelity.** All colors, typography, spacing, and interactions in the HTML match the intended production design. Recreate the UI pixel-perfectly using the codebase's existing Tailwind tokens and conventions. Where the HTML uses inline styles with exact hex values, map them to the CSS custom properties already defined in `globals.css` (e.g., `var(--surface-card)`, `var(--text-primary)`, `var(--accent-brand)`).

---

## File & Route Plan

Create these files in the `frontend/` directory:

```
frontend/
├── app/
│   └── weather/
│       └── page.tsx                    # Main route (client component, "use client")
├── components/weather/
│   ├── WeatherHero.tsx                 # Section 1
│   ├── TemperatureMap.tsx              # Section 2 (parent)
│   ├── MapCanvas.tsx                   # Section 2 (pins + world plane)
│   ├── DistributionPanel.tsx           # Section 2 (histogram)
│   ├── RainForecast.tsx                # Section 3 (NYC 7-day + monthly)
│   ├── NaturalEvents.tsx               # Section 4 (parent)
│   ├── HurricaneTracker.tsx            # Section 4 (monthly strip card)
│   ├── EventList.tsx                   # Section 4 (generic list card)
│   ├── ClimateDashboard.tsx            # Section 5 (three horizon columns)
│   ├── WildCards.tsx                   # Section 6
│   ├── Sparkline.tsx                   # Shared primitive
│   ├── SourceBadge.tsx                 # Shared (Kalshi / Polymarket / cross-source)
│   ├── ProbabilityNumber.tsx           # Shared (large mono % display)
│   └── data.ts                         # Static hero config + city coordinates
└── lib/
    └── weatherApi.ts                   # SWR fetchers for weather markets
```

Add a nav link "Weather" to the top header (already shown in the mock). The page is a client component because the hero rotator, map hover/selection, and SWR hooks all require client-side state.

---

## Screens / Views

There is one screen (`/weather`), vertically composed of the six sections below. Max content width: **1280px**, centered, with `24px` horizontal padding on desktop.

### Global layout

- Page background: `var(--surface-deep)` → `#F5F5F7`
- Sticky translucent header at top (`rgba(255,255,255,0.76)` + `backdrop-filter: saturate(180%) blur(10px)`)
- Header contains brand mark (26×26 gradient rounded square), nav, market count (`521 active markets · Apr 20, 2026`), search pill
- Each section separated by `56px` top padding; sections have their own card-grid layouts
- Footer at bottom with disclaimer and timestamp

---

### Section 1 — Hero (`WeatherHero.tsx`)

**Layout:** Two-column grid, `1.4fr 1fr`, `gap: 28px`.

**Left column:**
- "Live markets" pill (emerald, 11px) + "Updated N minutes ago" muted text
- Headline: `"What's the weather betting on today?"` — 52px, weight 600, letter-spacing `-0.028em`, line-height 1.02. The phrase "betting on" is colored `#10B981` (`--accent-brand`).
- Subtitle: 17px, `var(--text-secondary)`, max-width 580px
- Rotator dots: clickable pills, the active one elongates to 28×6px `#10B981`, inactive dots are 10×6px `#D1D5DB`. Shows `idx+1/total`.

**Right column (featured card):**
- White bg, 18px radius, 1px border, 28px padding, min-height 260px
- 4px colored top bar matching `probColor(prob)` — green ≥65%, amber 35–64%, red <35%
- Row: `"Featured · <tag>"` micro uppercase + `<SourceBadge>`
- Question — 24px, weight 600
- Footer row: big probability (64px mono, colored) + likely/toss-up/unlikely pill, then sparkline (120×36) + resolution date

**Rotation:** `setInterval` every **5.5s**, cycles through 5 featured markets. Clicking a dot resets to that index.

**Featured markets (hard-coded array):**
```ts
[
  { q: "Will it rain in NYC tomorrow?",             prob: 72, src: "kalshi",     tag: "Daily rain",  closes: "Tue, Apr 21" },
  { q: "Will 2026 be the hottest year ever?",       prob: 38, src: "kalshi",     tag: "Climate",     closes: "Thu, Dec 31" },
  { q: "Cat 4 hurricane hits the US before 2027?",  prob: 36, src: "polymarket", tag: "Hurricane",   closes: "Thu, Dec 31" },
  { q: "Will any month of 2026 be hottest on record?", prob: 78, src: "polymarket", tag: "Climate",  closes: "Thu, Dec 31" },
  { q: "Megaquake before June 30?",                 prob: 18, src: "polymarket", tag: "Seismic",     closes: "Tue, Jun 30" },
]
```

In production, swap this for a small API that returns the top 5 featured markets (by volume or curation).

---

### Section 2 — Global Temperature Map (`TemperatureMap.tsx`)

**Purpose:** Let users tap any of ~50 global cities to see tomorrow's high-temperature **probability distribution** — a histogram across 11 Polymarket outcome buckets (or 6 for Kalshi-only cities).

**Layout:** Two-column grid, `1.55fr 1fr`, gap 14px. Left = map card, right = distribution panel.

#### MapCanvas (`MapCanvas.tsx`)

Card: white, 16px radius, 1px border.

**Toolbar** (14×18px padding, bottom border): temp-gradient legend on the left (`-5°C → 40°C` bar 160×8px), `"HIGH · APR 20, 2026"` mono meta on the right.

**Map plane:**
- `aspect-ratio: 2/1`, min-height 360px
- Subtle 24×24px dotted grid pattern via inline SVG `<pattern>` with `#E5E7EB` dots
- Dashed latitude lines at y=200, 400, 600, 800; longitude lines at x=500, 1000, 1500; equator stronger (dasharray `6 8`)
- Region labels ultra-muted (`#D1D5DB`): "AMERICAS", "EUROPE / AFRICA", "ASIA / OCEANIA"
- Cities positioned by `x,y` percentages (see `data.ts` — these are **not** true lat/long; just visually placed)

**Pins** (30 cities):
- `<button>` absolutely positioned at `left: x%, top: y%`
- Size: 22px default, 30px on hover, 34px when selected
- Color: `tempColorC(modeTempInCelsius)` — gradient from deep blue (`#2563EB` at -10°C) through sky, neutral slate, amber (`#F59E0B` at 22°C), red (`#EF4444` at 32°C), to crimson (`#9F1239` at 45°C)
- Shadow when active: `0 0 0 3px #fff, 0 0 0 5px {color}, 0 8px 20px -6px {color}aa`
- Cross-source cities get a tiny 10px white bubble top-right, half-green/half-blue, indicating both Kalshi + Polymarket coverage

**City labels** — **only visible for selected + hovered pins.** Do NOT render labels for idle pins; that clusters badly in Americas/Europe. Label is a small white pill with `0 2px 8px rgba(17,24,39,0.1)` shadow, showing `City 22°` (mono degree).

**Map footer:** `"30 cities shown · tap a pin for distribution"` + `"11 cross-source"` (mono).

#### DistributionPanel (`DistributionPanel.tsx`)

White card, 16px radius, 22px padding, min-height 460px.

- Region kicker (uppercase muted) + city name (24px, weight 600)
- Top-right: `<SourceBadge>` or `<CrossSourceBadge>` if the city has both sources
- Sub-line: `"Tomorrow's high temperature · Apr 20, 2026"`
- **Peak number display:** 64px mono value (e.g. `50`) + 28px `°F` (or `°C`) in same color, then a small block showing the peak bucket's probability (e.g. `33%`) + `"most likely bucket"`
- `"50-51 is the modal outcome"` caption

**Histogram:** 140px tall, bars for each bucket (11 for Polymarket, 6 for Kalshi). Peak bar is fully saturated temp color; others are `{color}33` (20% alpha). Peak label floats above with its percentage. X-axis labels are tiny mono (9px), minor rotation not needed.

**Footer:** `"Click any pin on the map · 11 outcome buckets (Polymarket)"` (or 6 for Kalshi).

**All city data** (coordinates, distributions) is in `data.ts`. In production, replace with an API that returns distributions keyed by city ID.

---

### Section 3 — NYC Rain Forecast (`RainForecast.tsx`)

**Layout:** Two-column grid, `1.6fr 1fr`, gap 14px.

#### Left card: NYC 7-day rain strip
- White card, 16px radius, 22px padding
- Header: `"NYC · 7-day rain probability"` (20px, 600) + sub `"Daily 'Will it rain?' markets from Kalshi. NYC-only."` + right-aligned Kalshi SourceBadge
- **Strip:** 7 equal-width tiles in a CSS grid (`grid-template-columns: repeat(7, 1fr), gap: 8px`). Each tile:
  - 1px border, 12px radius, centered text
  - First tile (today) has tinted bg `#F0F9FF` + border `#BAE6FD`
  - Day label (MON, TUE…), date (mono, muted), emoji (26px), then **big prob** (20px mono, colored)
  - 4px filled bar at bottom
  - Color: green if ≥65%, amber if 35–64%, light slate `#CBD5E1` if <35%
- Footer: dashed top-border, `"Resolves daily at midnight ET · 0.01" threshold"` + date range

**Data array:**
```ts
[
  { day: "Mon", date: "Apr 20", prob: 72, icon: "🌧️" },
  { day: "Tue", date: "Apr 21", prob: 66, icon: "🌧️" },
  { day: "Wed", date: "Apr 22", prob: 34, icon: "⛅" },
  { day: "Thu", date: "Apr 23", prob: 100, icon: "☔" },
  { day: "Fri", date: "Apr 24", prob: 35, icon: "⛅" },
  { day: "Sat", date: "Apr 25", prob: 100, icon: "☔" },
  { day: "Sun", date: "Apr 26", prob: 74, icon: "🌧️" },
]
```

#### Right card: April rainfall
- Title `"April rainfall"` + Kalshi badge
- Sub: `'"Above 1 inch this month" — 10 cities.'`
- 10 rows, each: `110px city name | 1fr bar (7px tall, 999 radius) | 42px right-aligned % (colored mono)`
- Cities in order (with probs): NYC 92, Seattle 85, Miami 74, Houston 62, Chicago 58, Austin 51, SF 42, Dallas 38, Denver 34, LA 10

---

### Section 4 — Natural Events (`NaturalEvents.tsx`)

**Layout:** Three-column grid, `1.4fr 1fr 1fr`, gap 14px.

#### Column 1 — `HurricaneTracker.tsx`
- Header: red "HURRICANE SEASON · 2026" kicker with a red dot + `"Atlantic season tracker"` (20px, 600)
- Top-right stat: large prob `80%` (green, 32px) + caption `"≥1 major hurricane in 2026"`
- **Monthly bars:** 7 bars for May–Nov, 120px tall container. Gradient `linear-gradient(180deg, #EF4444 0%, #F87171 100%)`. Opacity scales with probability (`0.28 + p/100 * 0.72`). Peak months (≥70%) get bold `#B91C1C` prob label; others muted.
- Monthly probs: `May:21, Jun:34, Jul:58, Aug:78, Sep:88, Oct:60, Nov:24`
- Below: first 4 hurricane markets as list rows (`grid 1fr auto auto`): question + source badge, 72×5px bar, 14px mono %

#### Column 2 — `EventList` "Seismic activity"
- Icon chip (28×28px, 8px radius, `#7C3AED14` bg, `#7C3AED` glyph "⊙")
- Generic list with dividers: question + source badge + resolution date, right-aligned 18px mono % + 56×4px bar

Rows:
```ts
[
  { q: "Megaquake before June 30",                 prob: 18, src: "polymarket", closes: "Tue, Jun 30" },
  { q: "Another 7.0+ earthquake by Apr 30",        prob: 37, src: "polymarket", closes: "Thu, Apr 30" },
  { q: "9.0+ earthquake before 2027",              prob: 10, src: "polymarket", closes: "Thu, Dec 31" },
  { q: "8.0 earthquake in California before 2027", prob:  8, src: "kalshi",     closes: "Thu, Dec 31" },
  { q: "8.0 earthquake in California before 2028", prob: 13, src: "kalshi",     closes: "Fri, Dec 31" },
  { q: "8.0 earthquake in Japan before 2030",      prob: 50, src: "kalshi",     closes: "2029-12-31" },
  { q: "Zero 6.5+ quakes this week",               prob: 48, src: "polymarket", closes: "Sun, Apr 26" },
]
```

#### Column 3 — `EventList` "Tornadoes"
- Amber icon chip (`#F59E0B`), glyph "⟳"
- Rows: `">170 tornadoes in April" 32% Polymarket · Thu, Apr 30`, `"1250+ US tornadoes in 2026" 60% Polymarket · Thu, Dec 31`

---

### Section 5 — Climate Dashboard (`ClimateDashboard.tsx`)

**Layout:** Three equal-width columns, gap 14px. Each column is a card grouping markets by resolution horizon.

Each column has a big mono horizon label (32px, `2026` / `2030` / `2050`) + uppercase kicker ("This year" / "End of decade" / "Mid-century").

Market row format: question (13px, weight 500, pretty wrap) → bar + big colored % → SourceBadge.

**Items:**
```ts
// 2026 — This year
{ q: "Any month of 2026 is hottest on record", prob: 78, src: "polymarket" },
{ q: "2026 is the hottest year ever",          prob: 38, src: "kalshi"     },

// 2030 — End of decade
{ q: "CO₂ concentration above 440 ppm before 2030", prob: 88, src: "kalshi" },
{ q: "US meets climate goals by 2030",              prob: 16, src: "kalshi" },
{ q: "EU meets 2030 climate goals",                 prob: 44, src: "kalshi" },
{ q: "India meets its 2030 climate goals",          prob: 66, src: "kalshi" },
{ q: "EV market share above 10% in 2030",           prob: 87, src: "kalshi" },

// 2050 — Mid-century
{ q: "World passes 2°C over pre-industrial by 2050", prob: 78, src: "kalshi" },
```

---

### Section 6 — Wild Cards (`WildCards.tsx`)

Auto-fit grid, `minmax(220px, 1fr)`, gap 14px. Each card 14px radius, 20px padding, min-height 180px, `card-hover` (translateY -1px + soft shadow).

Layout per card: tag (micro uppercase muted) → question (15px, weight 500) → big prob (42px) + sparkline (80×24) → footer row with SourceBadge + `"Likely"/"Toss-up"/"Unlikely"` pill.

```ts
[
  { q: "Supervolcano erupts before 2050",          prob: 21, src: "kalshi",     tag: "Once-in-civilization" },
  { q: "Arctic sea ice <4M km² this summer",       prob: 43, src: "polymarket", tag: "Ice record" },
  { q: "Major solar storm before April 30",        prob:  3, src: "polymarket", tag: "Space weather" },
  { q: "Zero major space weather events this week",prob: 38, src: "polymarket", tag: "Space weather" },
  { q: "Zero VEI≥4 volcano eruptions in 2026",     prob: 55, src: "polymarket", tag: "Volcanic" },
]
```

---

## Shared Primitives

### `Sparkline`
Inline SVG, parameters `data: number[], color, width=96, height=28, stroke=1.5`. Draws a smooth path over normalized points with a gradient area fill (`color` at 18% → 0%), end-dot circle. Animates `stroke-dashoffset 400 → 0` over 1.2s (`spark-line` class).

### `SourceBadge`
Rounded pill (999px radius). Two variants:
- **Kalshi:** bg `#ECFDF5`, fg `#047857`, dot `#22C55E`
- **Polymarket:** bg `#EFF6FF`, fg `#1D4ED8`, dot `#3B82F6`

`<CrossSourceBadge />` — split-gradient background (50% green tint, 50% blue tint), two colored dots + `"CROSS-SOURCE"` label. Used on the 11 overlap cities in Section 2.

### `ProbabilityNumber`
Big mono number + smaller (~42% size) `%` sign. Color auto-resolved by `probColor(p)`:
- p ≥ 65 → `#22C55E` (likely — green)
- 35 ≤ p < 65 → `#F59E0B` (toss-up — amber)
- p < 35 → `#EF4444` (unlikely — red)

Optional `forceColor` prop overrides (used by the hurricane tracker's green 80% stat).

---

## Interactions & Behavior

| Interaction | Behavior |
|---|---|
| Hero rotator auto-advance | 5500ms interval, wraps around. Pause on hover is NOT implemented in the mock — add it if desired. |
| Hero dot click | Jumps to that index, resets rotation. |
| Map pin hover | Grows pin to 30px, shows label pill beneath. |
| Map pin click | Sets selected city, distribution panel updates with new histogram. Selected pin is 34px with white ring + colored outer ring. |
| Map pin focus (keyboard) | Same as hover. Pins are `<button>`s — already focusable. |
| Card hover (wild cards, etc.) | `translateY(-1px)`, border `#D1D5DB`, soft shadow — 160ms transition. |
| Sparkline entry | Stroke-dashoffset animation, 1.2s ease-out. |
| Prob bars entry | `width: 0 → N%`, 900ms `cubic-bezier(0.2, 0.8, 0.2, 1)`. |
| Search pill | Cosmetic only in mock — wire to your existing search/command palette. |

All sections are static on load and use SWR revalidation intervals where live data is involved (temperature markets update hourly; rain markets daily; climate markets every 6 hours).

---

## State Management

Use **SWR** (already in the stack) for data fetching, mirroring `frontend/app/page.tsx`. Suggested hooks:

```ts
// frontend/lib/weatherApi.ts
export const fetchWeatherFeatured = () => api.get("/weather/featured").json();
export const fetchCityDistribution = (cityId) => api.get(`/weather/cities/${cityId}/distribution`).json();
export const fetchNycRain = () => api.get("/weather/nyc/rain").json();
export const fetchMonthlyRain = () => api.get("/weather/rain/monthly").json();
export const fetchNaturalEvents = () => api.get("/weather/events").json();
export const fetchClimate = () => api.get("/weather/climate").json();
export const fetchWildCards = () => api.get("/weather/wildcards").json();
```

**Client-local state:**
- `idx` (hero rotator index) — `useState` + `useEffect` interval
- `selectedCity` (map) — `useState`, default `"nyc"`
- `hoverCity` (map) — `useState`

**Initial implementation tip:** start with the hard-coded arrays from `data.ts` (ported from the HTML mock), then swap them for SWR hooks once the API endpoints exist.

---

## Responsive Behavior

Follow the breakpoints used in `frontend/app/page.tsx`:

- **≥ 1024px (desktop):** Full layout as spec'd. Hero 2-col, map 2-col, rain 2-col, events 3-col, climate 3-col.
- **768–1023px (tablet):** Hero stacks (title above card), map and rain still side-by-side but tighter, events collapse to 2+1 (hurricane tracker full-width row, earthquakes + tornadoes side-by-side below), climate stays 3-col, wild cards auto-fit.
- **< 768px (mobile):** Everything stacks. 7-day rain strip stays horizontal but use `overflow-x: auto` with scroll-snap. Map aspect ratio becomes `1/1` or `4/3`; histogram panel moves below the map.

Header search pill hides below 640px.

---

## Design Tokens (all already in `globals.css`)

### Colors
| Token | Hex | Usage |
|---|---|---|
| `--surface-deep` | `#F5F5F7` | Page background |
| `--surface-card` | `#FFFFFF` | Card backgrounds |
| `--surface-elevated` | `#F0F0F2` | Raised surfaces |
| `--surface-border` | `#E5E7EB` | Borders, dividers |
| `--text-primary` | `#111827` | Primary text |
| `--text-secondary` | `#6B7280` | Supporting text |
| `--text-muted` | `#9CA3AF` | Muted captions |
| `--accent-brand` | `#10B981` | Emerald — brand accents, kickers, highlight |
| `--accent-live` | `#22C55E` | Kalshi brand dot + "likely" probability |
| `--accent-warning` | `#F59E0B` | Toss-up probability, temperature amber |
| `--accent-danger` | `#EF4444` | Unlikely probability, storm category |

### Source-specific (add if not already present)
| Purpose | Bg | Fg | Dot |
|---|---|---|---|
| Kalshi pill | `#ECFDF5` | `#047857` | `#22C55E` |
| Polymarket pill | `#EFF6FF` | `#1D4ED8` | `#3B82F6` |

### Temperature gradient stops (for map pins)
```ts
[-10°C, rgb(37,99,235)]    // deep blue
[  5°C, rgb(56,189,248)]   // sky
[ 15°C, rgb(148,163,184)]  // neutral slate
[ 22°C, rgb(245,158,11)]   // amber
[ 32°C, rgb(239,68,68)]    // red
[ 45°C, rgb(159,18,57)]    // crimson
```
Linear interpolate between adjacent stops.

### Typography
- **Sans:** `Inter` — 400/500/600/700. Use for all body, labels, headings.
- **Mono:** `JetBrains Mono` — 400/500/600. Use for **every number** — probabilities, temps, dates, counts, range bounds. Enable `tabular-nums`.

Type scale used:
| Role | Size | Weight | Letter-spacing |
|---|---|---|---|
| H1 hero | 52px | 600 | -0.028em |
| H2 section | 28px | 600 | -0.02em |
| H3 card | 20–24px | 600 | -0.015em |
| Big prob (hero/panel) | 64px | 600 | -0.04em |
| Big prob (card) | 42px | 600 | -0.02em |
| Mono list prob | 18–20px | 600 | -0.02em |
| Body | 15–17px | 400–500 | 0 |
| Caption | 12–13px | 400 | 0 |
| Micro / kicker | 10.5–11px | 600 | 0.6–0.8px (uppercase) |

### Spacing, radii, shadows
- Card radii: `14px` (compact cards), `16px` (section cards)
- Card padding: `18–22px` inside, `28px` for hero featured card
- Section vertical gap: `56px`
- Max content width: `1280px`
- Card hover shadow: `0 1px 2px rgba(17,24,39,0.04), 0 8px 24px -12px rgba(17,24,39,0.08)`
- Selected pin shadow: `0 0 0 3px #fff, 0 0 0 5px {color}, 0 8px 20px -6px {color}aa`

---

## Data Contracts

All probabilities are integers 0–100. All sources are `"kalshi" | "polymarket"`.

```ts
type Source = "kalshi" | "polymarket";

type FeaturedMarket = {
  q: string; prob: number; src: Source; tag: string; closes: string;
};

type CityDistribution = {
  id: string; name: string; region: "Americas" | "Europe" | "Asia" | "Africa" | "Oceania";
  srcs: Source[];  // ["polymarket"] or ["polymarket","kalshi"] for overlap
  high: {
    unit: "C" | "F";
    mode: number;                                        // peak bucket center
    dist: Array<{ label: string; prob: number }>;        // 11 (Polymarket) or 6 (Kalshi) buckets
  };
  low?: { unit: "C" | "F"; mode: number; dist: Array<{ label: string; prob: number }> };
};

type RainDay = { day: string; date: string; prob: number; icon: string };
type MonthlyRain = { city: string; prob: number; src: Source };
type EventMarket = { q: string; prob: number; src: Source; closes: string };
type ClimateMarket = { q: string; prob: number; src: Source; scale: "2026" | "2030" | "2050" };
type WildCard = { q: string; prob: number; src: Source; tag: string };
```

The 50 Polymarket cities and 20 Kalshi US cities, plus the 11 overlap cities, are enumerated in `uploads/weather-market-inventory.md` (if not present, see the design context doc). Start with the ~30 cities in the HTML mock and expand.

---

## Animations & Easing (from `globals.css`)

Reuse these — they already exist:
- `--transition-fast: 150ms ease-in-out` — hover states
- `--transition-base: 200ms ease-out` — button states
- `--transition-probability: 400ms ease-out` — probability bar fills

Custom additions needed:
- Sparkline draw: `stroke-dashoffset` 400 → 0 over 1.2s `ease-out`
- Card entry: optional 400ms fade-up (`translateY(6px) → 0`, opacity 0 → 1)
- Histogram bars: 400ms ease on `height` when selection changes

---

## Accessibility

- All pins are `<button>`s with `aria-label="{City name}, {temp}°{unit}"`
- Rotator dots have `aria-label="Show featured {n}"`
- Respect `prefers-reduced-motion`: disable sparkline + bar-fill animations when set.
- Color is never the only cue — every probability number has a text label ("Likely / Toss-up / Unlikely") nearby.
- Target hit sizes: pins ≥ 22px, dots 10×6px but easily thumb-tappable because they have large invisible padding.

---

## Assets

- **No images or icons required.** All glyphs are either emoji (rain strip: 🌧️ ☔ ⛅) or inline SVG (search, plus, chevrons if you add them).
- **No hand-drawn map.** The world plane is an abstract dotted grid with latitude/longitude hashes and region captions — intentionally editorial, not cartographic. Do **not** substitute a real TopoJSON map without discussion; the mock is the direction.
- **Fonts** are already loaded via `next/font` in `frontend/app/layout.tsx`.

---

## Files in This Bundle

- `README.md` — this document
- `Weather.html` — the high-fidelity HTML prototype. Open it in a browser or in Claude Design to see the final intended result. All six sections, real market data, working hero rotator + map selection.

---

## Implementation Checklist

- [ ] Create `frontend/app/weather/page.tsx` as client component
- [ ] Add "Weather" nav link in main header
- [ ] Create `frontend/components/weather/` folder + extract each section into its own file
- [ ] Port static data arrays into `frontend/components/weather/data.ts`
- [ ] Implement shared primitives: `Sparkline`, `SourceBadge`, `CrossSourceBadge`, `ProbabilityNumber`
- [ ] Hero rotator with interval + dots
- [ ] Map with pins, hover/select, histogram panel
- [ ] NYC 7-day strip + monthly rain column
- [ ] Hurricane tracker + earthquake/tornado lists
- [ ] Climate 3-column layout
- [ ] Wild cards grid
- [ ] Mobile responsive audit at 375 / 768 / 1024 / 1280
- [ ] Swap static data for SWR hooks once API endpoints exist
- [ ] Accessibility pass (labels, reduced motion, keyboard nav)

---

## Questions or Unknowns

- **API shape:** backend endpoints for `/weather/*` don't exist yet. Define them alongside frontend work.
- **"Featured" rotation source:** currently hard-coded. Decide: editorial pick, highest-volume, highest-movement?
- **Cross-source UX:** when a city has both Kalshi + Polymarket distributions, should we show both stacked/overlaid, or pick one? The mock shows only the Polymarket distribution and a "cross-source" badge — the Kalshi version is implicitly available via another view.
- **NYC rain:** Kalshi currently offers daily rain for **NYC only**. If this expands to other cities, generalize the component to accept a city prop.
