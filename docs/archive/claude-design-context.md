# Bain Luck — Design Context for Claude Design

Import this file into Claude Design before running any prompt. It gives Claude Design everything it needs about the product, design system, and constraints.

GitHub repo: https://github.com/alexander-bain/bainluck

---

## What Bain Luck Is

Bain Luck (bainluck.com) is a visual-first sports odds experience that translates betting markets into intuitive win probabilities. Users see "60% vs 40%" instead of "-150 / +130". The target user is a casual sports fan watching a game who wants context, not betting advice.

**North Star**: The cleanest odds visualization tool on the internet.

**NEVER show**: American odds (+425, -150), gambling language, trade volumes, sportsbook branding, or dark mode. This is NOT a sportsbook.

**ALWAYS show**: Probabilities (0-100%), source attribution, clean data visualization.

## Tech Stack

- **Frontend**: Next.js 14, React, Tailwind CSS, Recharts for charts
- **Backend**: FastAPI (Python), PostgreSQL, Celery + Redis
- **Data Sources**: The Odds API (sportsbooks), Kalshi (prediction markets), Polymarket (prediction markets), ESPN (scores/game state), DataGolf (golf), MLB Stats API, StatPal (schedules/injuries)

## Design System

### Color Tokens (from globals.css)

Light mode ONLY. Never use dark backgrounds.

| Token | Value | Use |
|-------|-------|-----|
| `--surface-deep` | `#F5F5F7` | Page background (light gray) |
| `--surface-card` | `#FFFFFF` | Card backgrounds (white) |
| `--surface-elevated` | `#F0F0F2` | Slightly raised surfaces |
| `--surface-border` | `#E5E7EB` | Card borders, dividers |
| `--text-primary` | `#111827` | Main text (near-black) |
| `--text-secondary` | `#6B7280` | Supporting text (gray) |
| `--text-muted` | `#9CA3AF` | Least important text (light gray) |
| `--accent-live` | `#22C55E` | Live game indicators (green) |
| `--accent-brand` | `#10B981` | Brand accent (emerald) |
| `--accent-futures` | `#8B5CF6` | Futures/prediction markets (purple) |
| `--accent-warning` | `#F59E0B` | Warnings (amber) |
| `--accent-danger` | `#EF4444` | Errors, negative changes (red) |

### Typography

- **Sans**: Inter (primary body text)
- **Mono**: JetBrains Mono (numbers, probabilities, odds)
- Probabilities and numbers should always use the monospace font

### Source Colors (for multi-source charts)

| Source | Color | Hex |
|--------|-------|-----|
| Betting consensus | Slate | `#F8FAFC` |
| ESPN | Orange | `#F97316` |
| Stat model | Purple | `#A855F7` |
| Kalshi | Green | `#22C55E` |
| Polymarket | Blue | `#3B82F6` |
| MLB API | Teal | `#0D9488` |

### Chart Style (Gold Standard)

DataGolf's probability evolution plot is the design reference: thin colored lines on white background with clean gridlines. Apply this aesthetic to all probability charts.

## Existing Pages (reference for consistency)

| Page | URL | Purpose |
|------|-----|---------|
| Feed (home) | bainluck.com | Ranked list of games with probability cards |
| Event detail | bainluck.com/event/[id] | Single game deep-dive: win prob chart, markets, futures |
| Sport hierarchy | bainluck.com/sport/[sport]/[league] | League-level view (e.g., NBA standings grid) |
| Golf | bainluck.com/categories/golf | Tournament cards, leaderboards |
| Playoffs | bainluck.com/playoffs | Championship probability grids |
| Admin | bainluck.com/admin | Operations dashboard (quota, coverage, worker health) |

## Key Frontend Files (import from GitHub for reference)

- `frontend/app/globals.css` — Design system tokens
- `frontend/app/design-tokens.css` — Extended tokens (status, EI, source colors)
- `frontend/app/page.tsx` — Homepage/feed layout
- `frontend/components/FeedCard.tsx` — Event card component
- `frontend/components/EventCard.tsx` — Detailed event card
- `frontend/app/event/[id]/page.tsx` — Event detail page

## Product Expansion: Non-Sports Categories

Bain Luck is expanding beyond sports into prediction markets for ANY topic. Kalshi and Polymarket cover weather, politics, entertainment, finance, and world events. The backend already ingests from both.

Each non-sports category page should:
1. Use the same design system as the sports pages
2. Show probabilities as the hero element (large, monospace, prominent)
3. Include sparkline trend charts showing probability movement over time
4. Show source badges (Kalshi, Polymarket, or both)
5. Feel informational and clean — like a weather app, not a trading platform
6. Include a plain-English question for each market ("Will X happen?" → 73%)
7. Mobile-first responsive layout

## Card Component Pattern

Every prediction market (sports or non-sports) should render as a consistent card:
- White background (`--surface-card`)
- Thin border (`--surface-border`)
- Plain-English question as the title
- Large probability number in monospace font
- Small sparkline showing recent trend
- Source badge (Kalshi/Polymarket/Odds API)
- Category tag
- Resolution timeframe
- Optional contextual image (team logo, movie poster, weather icon, candidate photo)
