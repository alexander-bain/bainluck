# Bain Luck Design System

> **Source**: Extracted by Claude Design (April 2026) from `frontend/` codebase + user brief.
> **Canonical tokens**: `frontend/app/globals.css`, `frontend/app/design-tokens.css`, `frontend/tailwind.config.ts`.
> **Usage**: Reference this doc when writing Claude Design prompts or implementing new UI in Claude Code.

---

## How to Use This With Claude Design

When starting a new Claude Design project:
1. Select the "Bain Luck Design System" in the Design System dropdown
2. Describe what you want to design (e.g., "redesign the tournament detail page")
3. Claude Design will follow these rules automatically
4. When you're happy with the visual, bring the screenshot or handoff bundle to Claude Code CLI for production implementation

When asking Claude Code to write a Claude Design prompt:
- Reference this doc — Claude Code will extract the relevant constraints for the feature you're designing
- Claude Code knows your actual component library, API shapes, and data models, so it can write prompts that are grounded in what's actually buildable

---

Bain Luck is a **visual-first sports odds experience**. It translates betting markets — spreads, moneylines, totals — into intuitive **win probabilities** so users see "60% vs 40%" instead of "-150 / +130." Casual fans get the gist at a glance; power users get a Bloomberg-terminal level of density on top.

The aesthetic is **clean, data-dense, editorial** — Bloomberg Terminal meets ESPN, but inviting. White card surfaces on a light-gray field. **Light mode only, always.** No gambling imagery, no neon, no dark "sharp" chrome.

---

## CONTENT FUNDAMENTALS

Bain Luck copy is **quiet, declarative, and trusting the numbers**. The data is loud; the words are not.

**Voice**
- **Third-person observational.** "Lakers open as favorites." Not "You should bet…" The product doesn't advise — it surfaces probability.
- **Never anthropomorphizes the user** ("You'd love this market!"). Brief second-person only in toasts and empty states ("Check back soon — we surface the best stuff automatically").
- **No betting-industry argot.** Never "juice," "vig," "chalk," "sharp," "action." Say "probability," "favorite," "underdog," "market," "movement."
- **Confidence without hedging.** "Opened 55/45" > "It looks like this might have opened around 55/45."

**Source Attribution**
- Source attribution is always quiet — small tags/chips at the data row level, never in headlines, blurbs, or section copy. The product's voice is the aggregate, not the vendors. Individual market rows may show a source chip (Kalshi, Polymarket) for transparency.

**Tone & vibe**
- **Editorial and dry**, like a wire-service ticker. Closer to Bloomberg/FT than DraftKings.
- Occasional lightness in ambient UI — the logo is a 🍀 emoji, the category chips use sport emoji, toasts say things like "Showing more golf" — but never in body prose.

**Casing**
- **Sentence case for titles, headings, and buttons.** "My stuff", "Player props & progressions", "More like this".
- **UPPERCASE for micro-labels and status badges only.** `LIVE`, `FINAL`, `RESOLVED`, league tickers inside `.micro-xs` with `0.04em` tracking.
- Team and league names are **Title Case as rendered by the source** (ESPN / The Odds API) — we do not restyle them.

**Numbers & units**
- Probabilities always `%`, never decimals: `62%`, not `0.62`.
- Two-sided probabilities separated by `/`: `62% / 38%` or "Opened 55/45".
- Scores use JetBrains Mono, tabular figures, `-` separator: `108 - 102`.
- Movement deltas carry a sign and an arrow: `↑ 2.4%` in `--accent-live`, `↓ 1.1%` in `--accent-danger`.
- Time is relative where useful ("Today 7:30 PM", "Tomorrow 1:05 PM", "Resolves Thu"), absolute otherwise.

**Emoji**
- Used **as category markers, not decoration**: 🏀 NBA, 🏈 NFL, ⚾ MLB, ⛳ Golf, 🍀 brand logo, 📌 pinned, 🎯 player-props header.
- Never inside body copy or paragraph prose. Never to convey emotion.

**Examples from the codebase**
- Empty feed: *"Nothing interesting right now"* / subhead *"Check back soon — we surface the best stuff automatically"*
- Thumb-down toast: *"Showing less golf"*
- Reason badge: *"Upset watch"*, *"Close game"*, *"Line moved 4 pts"*, *"Starting soon"*
- Footer meter: *"42 events · 18 futures markets · Personalized"*
- Resolved futures: *"Denver Nuggets: 18% → Won"* (lowercase verb — factual, not celebratory)

---

## VISUAL FOUNDATIONS

### Palette
- **Page field** `#F5F5F7` (`--surface-deep`) — never pure white. Every screen sits on this.
- **Cards** `#FFFFFF` (`--surface-card`) with `1px` `#E5E7EB` border and the soft `0 1px 3px rgba(0,0,0,0.08)` shadow.
- **Hover surface** `#F0F0F2` — cards warm up by ~3% on hover, borders fade into the elevated tone.
- **Text** `#111827` primary / `#6B7280` secondary / `#9CA3AF` muted. This trio does 95% of the typographic hierarchy.
- **Semantic accents** — `#22C55E` live, `#10B981` brand/emerald, `#8B5CF6` futures/purple, `#F59E0B` warning/highlight, `#EF4444` danger. Each is used at **full saturation for text**, at `/15` or `/10` opacity for tinted chip backgrounds.
- **Team colors are dynamic** — loaded from ESPN via `team.primary_color`, applied as CSS custom properties (`--team-home-primary`, `--team-away-primary`). `teamColorStyle(home, away)` maps hex to `"R G B"` tuples so Tailwind's `rgb(var(...))` syntax works.
- **EI severity ramp** — red (incredible/must-watch) → orange (exciting) → yellow (competitive) → gray (quiet/flat). Distinct from the semantic accents.
- **No gradients on cards or backgrounds.** One exception: the "gold-shimmer" marquee background used on Oscars-frontrunner cards (an animated linear-gradient sweep). Live-brand pulsing uses `--shadow-glow` (a 20px emerald halo at 15% alpha) — not a fill.

### Typography
- **Inter** for everything that isn't a probability or score. Weights 400 / 500 / 600 / 700.
- **JetBrains Mono** for probabilities (36/28/20/16 px, bold, tight tracking) **and** scores. This is non-negotiable — the mono numerals are the scoreboard cue.
- **Probability numerals** carry `font-variant-numeric: tabular-nums` so "62%" and "38%" line up column-wise. Tracking steps from `-0.01em` → `-0.03em` as size grows; the hero `36px` probability is almost-condensed.
- **Scale** — `display 48 · title-1 28 · title-2 22 · title-3 18 · body 16 · caption 14 · micro 12 · micro-xs 10`. Micro-xs is always UPPERCASE with `0.04em` tracking.
- **Line-height** tightens as size grows: `1.5` for body, `1.3` for title-3, `1.1` for display.

### Spacing & rhythm
- **4 px baseline.** Cards are `p-3` (12 px) or `p-4` (16 px); section gaps are `gap-3` (12 px) between cards, `mb-3` (12 px) between a section header and its grid.
- **Auto-fill grid** `repeat(auto-fill, minmax(min(100%, 320px), 1fr))` — cards always reach `320px` wide, never wider than needed, always single-column on mobile.
- **Content max-width 1200 px**, centered. The shell is always `max-w-content mx-auto px-3 md:px-6`.

### Backgrounds & imagery
- **Plain `#F5F5F7` field.** No textures, no patterns, no hand-drawn illustrations, no full-bleed hero photos.
- **Team logos** are the only recurring imagery — rendered at 20 px inline, 24 px in card headers, via ESPN's CDN (`a.espncdn.com`). Fallback is a colored initials chip using `team.primary_color`.
- **Flags** (15 px × 20 px) replace team logos for international soccer sports.
- **Entity images** (wikipedia thumbnail, 14–20 px) for non-sports futures (politics, economics, entertainment).
- No stock photography. No generative imagery. When data isn't available, show a sized skeleton or initials chip — never a placeholder image.

### Corners
- **10 px** (`--radius-card`) for every card. This is the signature radius.
- **Pill** (`9999px`) for: league chips, LIVE badge, FINAL badge, thumbs buttons' hover rounding, probability-bar segments.
- **6 px** for small inline chips (EI score, source count, reason badges).

### Borders
- Cards: `1px solid #E5E7EB` (`--surface-border`). That's it — no ring, no 2px stroke.
- Futures cards add a **2 px colored top-border** by category (blue for politics, yellow for entertainment, emerald for economics, cyan for tech, purple-40 otherwise). This is the one place a non-neutral border appears.
- Live events add a `ring-1 ring-accent-live/20` — a subtle green halo around the card border, not a fill.

### Shadows
- **Resting card** — `0 1px 3px rgba(0,0,0,0.08), 0 0 0 1px rgba(0,0,0,0.04)`. Layered: a soft drop + a hairline ring.
- **Hover card** — `0 4px 16px rgba(0,0,0,0.10), 0 0 0 1px rgba(0,0,0,0.06)`. Lift + warmer ring.
- **Glow** (`--shadow-glow`) — `0 0 20px rgba(16,185,129,0.15)`. Used sparingly for "live" emphasis.
- **Inner shadow** on probability-bar's favorite segment — `inset 0 1px 2px rgba(0,0,0,0.1)` — gives the scoreboard bar a tiny extruded feel.

### Motion
- **Durations** ladder: `100 · 150 · 200 · 300 · 400 · 500 ms`. `--duration-prob (400ms)` is reserved for probability width transitions so numbers and bars change together.
- **Easing** is almost always `cubic-bezier(0.25, 0.1, 0.25, 1)` — "ease-out cubic". Framer Motion uses it as `[0.25, 0.1, 0.25, 1]`.
- **No bounces** in the main feed. Springs only appear on modals/tooltips (`scaleIn` preset, `stiffness 300 / damping 24`).
- **Stagger** — feed sections reveal children `0.05s` apart with `0.1s` parent delay, 8 px up-from-below.
- **Live pulse** — 2s infinite `opacity: 1 → 0.5 → 1`. The 6 px green dot next to "LIVE" uses it.

### Hover & press
- **Cards lift by `scale(1.005)`** — almost imperceptible; the shadow change carries most of the cue.
- **Text buttons** shift color, not background: muted → secondary, secondary → primary.
- **Icon buttons** (thumbs, pin) shift from `text-muted/30` → colored accent (`accent-live` thumb-up, `accent-danger` thumb-down, `accent-warning` pin active).
- **Pressed state** inherits the browser default plus the ring from `focus-visible:ring-1 ring-ring`. No explicit `:active` shrink.
- **Disabled** = `opacity 0.3–0.5`, `cursor-not-allowed`.

### Transparency & blur
- **Sticky header** uses `bg-surface-card/80 backdrop-blur-lg` — the one place blur appears. This keeps scrolling feeds visible behind the nav.
- **Bottom nav (mobile)** uses `bg-surface-card/95 backdrop-blur-lg`.
- **Tinted chip backgrounds** — `bg-accent-*/10` or `bg-accent-*/15`. Never `/50`+; the color stays as flavor, not as mass.
- No translucent cards. No frosted panels in body content.

### Layout rules & fixed elements
- **Header** — sticky top, full-bleed, `z-50`, 1 px bottom border. Height defined by `py-3` padding.
- **Bottom tab nav** (mobile only, hidden `md:` up) — fixed, `z-50`, safe-area padded. 3 tabs: Feed / Search / My Stuff.
- **Desktop tabs** sit between logo and search inside the header.
- **Pinned items** always render above the feed in a "📌 Pinned" section, max 6.
- **Toasts** fixed `bottom-24 md:bottom-8`, centered, auto-dismiss at 2s.

---

## ICONOGRAPHY

- **Primary icon system: `lucide-react`** (pinned in `frontend/package.json`). Thin, rounded, 2 px stroke. Use at `16 px` inline and `20–22 px` for nav.
- **Custom inline SVG icons** for the bottom-nav (`FeedIcon`, `SearchIcon`, `UserIcon`, `PinIcon`). All draw in the exact Lucide vocabulary — `stroke-linecap="round"`, `stroke-linejoin="round"`, stroke weight toggles between `1.5` (resting) and `2.5` (active).
- **Thumbs up/down** are hand-drawn 12 px SVGs inside `FeedCard.tsx`.
- **Pin** is a 14 px SVG with a filled and outline variant (active uses `fill="currentColor"`).
- **Emoji as icons** — used deliberately as category / sport markers (🏀🏈⚾🏒⚽⛳🏆⚡🍀🎯📌). They're part of the content layer, not the chrome.
- **Inline glyph markers** — `⚠` (upset), `⚖` (close game), `↕` (line moved), `🕐` (starting soon), `⚡` (lead change) — rendered as Unicode characters inside reason-badge pills with matching accent colors.
- **No custom icon font.** No FontAwesome. No proprietary sprite.

---

## SIGNATURE COMPONENTS

### Probability Bar
Two rounded segments with a **1.5px gap**, team-colored. Favorite side is full opacity, underdog is 40% opacity. Inner glow shadow on the favorite segment. Height: 4px (sm), 6px (md), 8px (lg). Animated width transitions via Framer Motion at 500ms ease-out cubic.

### Feed Card (Event)
Header row (live badge + EI + league + score) → team rows with logos + probabilities → probability bar → footer (reason badge + timestamp). Live events get a green ring halo. Completed events at 70% opacity.

### Feed Card (Futures)
2px colored top-border by category → league + source count → market name → top 4 outcome rows with mini progress bars → timestamp. Leader row gets amber rank badge and purple progress bar.

### Evolution Chart
Thin 1.5px lines, `#EEF0F3` horizontal grid only (no vertical grid), eliminated outcomes are dashed + gray at 55% opacity. Y-axis extends to zero. X-axis clearly labeled. Catmull-rom smoothing between data points.

### League Chips
Horizontal scrollable row, pill-shaped (`9999px` radius). Active chip: `bg-text-primary text-text-inverse`. Inactive: `bg-surface-elevated text-text-secondary`. Sport emoji prefix. No scrollbar visible.

---

## TECH STACK (for code generation context)

- Next.js 14 App Router, React, TypeScript strict mode
- Tailwind CSS with custom design tokens (see `tailwind.config.ts`)
- Framer Motion for animations
- Recharts for production data visualization
- shadcn/ui primitives (card, badge, button, tooltip)
- Lucide React for icons
- Inter + JetBrains Mono (loaded via `next/font/google`)
