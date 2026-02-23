# TV Mode — Design Plan

## Overview
Full-screen second-screen experience for live games, elections, award shows, and ambient futures display. Browser-first (`/tv` route), with iOS-native v2 planned.

## Core Concept
- **Live mode**: Single event focus filling the screen. Swipe/auto-rotate between games. Auto-switches to highest-Pulse game.
- **Ambient mode**: Slow crossfade rotation through interesting futures (championships, elections, Oscars, crypto) when no live games or during breaks.

## Signature Element
The probability numbers **breathe** — a subtle scale/glow animation whose speed maps to the Pulse score. `beatMs(p) = Math.max(550, 2000 - p * 14.5)`. A Pulse-91 thriller visibly throbs faster than a Pulse-42 blowout. Only Bain Luck can do this because only Bain Luck has Pulse.

## Design Language
- **Dark void** (#09090b) — not gray, true darkness. Numbers float in space.
- **Team colors as the only palette** — everything else is white/gray on dark.
- **Glowing numbers** — text-shadow in team color. Numbers emit light, not sit on surfaces.
- **No UI chrome in display mode** — no borders, no cards. Just information.
- **Jumbotron typography** — readable from 10 feet on TV, arm's length on phone.

## Cascaded Density Hierarchy (v4)

The guiding principle: every screen shows as much information as possible. Bigger screens show MORE, not the same thing bigger. Opening TV mode is a deliberate action — every pixel should show useful data.

### Phone (390×780, portrait)
Gets what iPad used to have — Pulse ring, multi-source chart with gridlines, full context, related futures.
- Header: sport + LIVE badge + period/clock + broadcast
- Teams row: badge + name + record + score (28px)
- Breathing probability numbers (56px) + probability bar
- Multi-source chart with gridlines (flex-fills available space)
- Pulse ring (58px) inline next to context items (opened, line movement, divergence)
- Championship impact box
- Related futures (up to 3)

### iPad (900×600, landscape)
Gets what TV used to have — 3-column layout with other games panel.
- Header bar: sport, LIVE, teams/badges/records, score (24px), clock, broadcast
- Left panel: breathing probabilities (56px), probability bar, multi-source chart with gridlines
- Center-right sidebar (190px): Pulse ring (72px), context items (opened/line/divergence/context), championship impact, related futures
- Far-right panel (140px): other live games (clickable to switch), trending futures (top 2)

### TV / Monitor (1280×720, landscape)
Maximal — everything the other views have, plus exclusive data:
- **Enhanced header**: sport, LIVE, teams/badges/records (16px names), score (34px), **score-by-period table** (per-quarter/period breakdown with team colors), clock, broadcast
- **Left panel**: breathing probabilities (80px), probability bar, multi-source chart with gridlines (620×260), **source comparison strip** (current value + delta for each source side-by-side)
- **Center-right sidebar (240px)**: Pulse ring (100px), **Pulse component breakdown** (Heart Rate, Amplitude, Arrhythmia, Vitals as colored progress bars), context items, championship impact, related futures (all)
- **Far-right panel (200px)**: other live games with scores + **sparklines** (inline mini-charts), trending futures (top 4) with **probability bars for top 3 outcomes each**

## Data Shown Per Device

| Feature | Phone | iPad | TV/Monitor |
|---------|-------|------|------------|
| Breathing probability numbers | ✅ 56px | ✅ 56px | ✅ 80px |
| Multi-source chart (Odds, ESPN, Kalshi, Polymarket) | ✅ w/ gridlines | ✅ w/ gridlines | ✅ w/ gridlines |
| Score + teams + records | ✅ | ✅ | ✅ large |
| Probability bar | ✅ | ✅ | ✅ |
| Pulse ring | ✅ 58px inline | ✅ 72px sidebar | ✅ 100px sidebar |
| Context (opened, line, divergence) | ✅ | ✅ sidebar | ✅ sidebar |
| Championship impact | ✅ | ✅ sidebar | ✅ sidebar |
| Related futures | ✅ up to 3 | ✅ all | ✅ all |
| Other live games panel | — | ✅ 140px | ✅ 200px |
| Trending futures panel | — | ✅ top 2 | ✅ top 4 w/ bars |
| Score-by-period breakdown | — | — | ✅ header |
| Pulse component breakdown | — | — | ✅ (HR/Amp/Arr/Vit) |
| Source comparison strip | — | — | ✅ below chart |
| Sparklines in other games | — | — | ✅ |

## Ambient Futures Mode
- 8-second display per item, 1.2s fade-in animation
- Category label + emoji + market name
- Top 5 outcomes with probability bars
- Dot indicators for position in rotation
- Source badges (Polymarket, Kalshi, Odds API)
- Subtle background gradient shifts per category
- Responsive sizing: phone (340px max), tablet (460px), TV (560px)

## Smart Behaviors
- **Auto-switch**: When a game's Pulse spikes above 85, auto-switch to it with a brief notification flash.
- **Auto-ambient**: If no live games, automatically enter ambient futures mode.
- **No sleep**: Request `wakeLock` API to prevent screen dimming.
- **Keyboard shortcuts**: Arrow keys to cycle games, Space to toggle live/ambient, F for fullscreen.

---

## iOS v2 Features

### Lock Screen Live Activities
A persistent mini probability bar on the Lock Screen that updates without opening the app. Shows team colors, current probability split, and Pulse dot. Tapping opens the full app to that game. Perfect for "glance at my phone face-down on the table" during a game.

**Implementation**: ActivityKit framework. Push-token based updates from backend (or polling). Show home/away team abbreviated names, probability bar, score, Pulse dot color.

### Dynamic Island
When a tracked game is live, the Dynamic Island shows the Pulse score and a pulsing dot whose speed matches the game's excitement. The compact view shows just the dot + score. The expanded view shows both teams, probabilities, and a mini sparkline.

**Compact**: `💓 78  BOS 62`
**Expanded**: Full team names, probability bar, mini chart, score

### StandBy Mode
When the iPhone is horizontal on a MagSafe charger (StandBy mode in iOS 17+), show a simplified clock-style display. Giant glowing probability numbers in team colors on a true-black background. Optimized for always-on display (OLED-friendly: mostly black pixels).

**Layout**: Team abbr + giant number on each side, thin probability bar between, Pulse ring in the corner. Time shown small in the corner. Auto-cycles between pinned games.

### Apple Watch Complication
Just the number. "62" in Celtics green on a dark watch face. Tap to see a mini probability bar with both teams. Available as corner, circular, and rectangular complications.

**Corner**: Just the leading team's probability
**Circular**: Probability ring (like Activity rings but team-colored)
**Rectangular**: Both teams + probabilities + Pulse dot

### Widget Gallery
- **Small widget**: Single game — team colors, probability split, Pulse dot
- **Medium widget**: Two games side by side, or one game with sparkline
- **Large widget**: Top 3 most exciting live games by Pulse score

### Haptic Feedback
Subtle taptic pulse when watching a game in the app that matches the Pulse score rhythm. Optional — user can toggle in settings. Intensifies during lead changes (50% crossings).

### Siri Integration
- "Hey Siri, what are the odds for the Celtics game?" → probability + Pulse score
- "Hey Siri, what's the most exciting game right now?" → highest Pulse live game
- "Hey Siri, what are the Celtics' championship odds?" → current futures probability

---

## Implementation Plan (Browser v1)

### Phase 1: Route + Core Layout
1. Create `/tv` route in Next.js
2. Implement device detection (or manual toggle)
3. Build LiveView component (phone + tablet + TV layouts)
4. Wire up to real events API (`/api/events` with `status=live`)
5. Wire up to real history API (`/api/events/{id}/history`)
6. Auto-refresh: poll events every 30s, history every 60s

### Phase 2: Multi-Source + Context
1. Wire up multi-source win probability (`win_prob_snapshots` by source)
2. Add opening odds display (from event's `opening_odds` field)
3. Add line movement calculation (current vs opening)
4. Wire up related futures for championship implications
5. Add market divergence detection (prediction market vs sportsbook consensus)

### Phase 3: Ambient + Polish
1. Build AmbientView with futures rotation
2. Auto-switch between live and ambient based on game availability
3. Implement Pulse-based auto-focus (highest-Pulse game gets priority)
4. Add keyboard shortcuts (arrows, space, F)
5. Request wakeLock to prevent screen sleep
6. Add fullscreen toggle

### Phase 4: Smart Features
1. Game start notifications (flash when a pinned game goes live)
2. Pulse spike alerts (highlight when a game suddenly gets exciting)
3. Sound option (subtle heartbeat audio mapped to Pulse, off by default)
4. Multi-game split screen option for TV (2-up or 4-up grid)

---

## Prototype
Interactive React prototype at `tv-mode-prototype.jsx` with:
- Device switching (iPhone / iPad / TV) with accurate frame sizes
- Live mode with breathing probability numbers, multi-source charts, context sidebars
- Ambient futures rotation mode
- Interactive Pulse slider to preview animation speed changes
- Game switching via arrow controls or clicking other-games panel
- All mock data: 4 games (NBA, NFL, NBA, Election), 5 futures markets (NBA, Oscars, 2028 Election, Bitcoin, Super Bowl)
- New TV-exclusive components: PulseBreakdown, SourceStrip, PeriodScores, Sparkline
