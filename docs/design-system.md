# Bain Luck Design System

> **Source**: Extracted by Claude Design (April 2026) from `frontend/` codebase + user brief. Settled-state, concept-page, threshold-group, end-of-feed, and cockpit sections added 2026-07-14 from the shipped implementation. Refreshed 2026-07-31 through Queue 289 / L2-220 (dollar-volume ruling, nothing-beats-unhelpful, fail-closed cards, progressive first card, native chart axis parity).
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

### Threshold Grid (threshold-group component)
`components/ThresholdGrid.tsx` — one card per threshold variant of the same question ("Bitcoin > $80K / $90K / $100K"; "RT score ≥ N"), sorted by `threshold_value`. Responsive `grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2`, framer-motion stagger. Each cell (`rounded-lg border p-3` on `--surface-card`): an "Under/Over" label, the mono formatted threshold (`$80K`, `1.5M`), a large mono percentage color-graded by probability, and a mini bar. The `highlightedValue` cell gets an `accent-brand` ring + `bg-accent-brand/5`. Source names removed (blend-only). Companion: `ThresholdSparkline.tsx`; the playoff-progression analog is `ProgressionLadder.tsx` (status dots: green achieved / red eliminated / muted pending). Backend grouping is `_group_threshold_markets()` on the category routes.

### End-of-Feed Card (graceful end state)
`components/discover/EndOfFeedCard.tsx` — replaces the abrupt silent stop when the Discover pool is exhausted or empty. `rounded-2xl bg-surface-card border` card: headline **"You're all caught up"**, sub-line "{count} markets explored — new markets open throughout the day, so check back soon.", a **"Refresh feed"** pill (`bg-accent-brand/10 text-accent-brand`, the web reload affordance — there's no pull-to-refresh), then an "Explore by category" row of `rounded-full bg-surface-elevated` links (Politics / Economics / Entertainment / Weather / Sports), each firing a `navigation_click` GA event.

---

## STANDING PRODUCT RULINGS (bind every surface)

Alex's standing rulings sit above the visual system — they decide *what* renders before this doc decides *how*. The full set with reasoning lives in `docs/PRODUCT-BRAIN.md`.

- **Probabilities only, never odds — and never dollar volume.** No American (−150/+130), decimal, or spread-style prices anywhere a user can see. Probability (`%`) is the only quantity format on any surface. Payloads may still carry `american_odds` for API consumers, but no rendered row prints it. Book/market-mechanics language ("bet", "payout", "juice", "odds") never appears in UI copy. Any odds string that reaches the screen is a P1 bug (the futures-detail `+9900` leak, L2-48). **Dollar volume as social proof is banned too** (ruling 2026-07-30): "$6.6M changed hands" framing violates the same thesis, whether in prose or a chart attribution line. The *word* "odds" in editorial copy is fine; it is price formats and dollar framing that are banned. The anti-gambling-enticement thesis is the product's reason to exist.
- **Nothing beats unhelpful.** Silence is better than filler. A commentary box that states the obvious, an empty chart frame, an unexplained chip — remove it rather than shipping it. Annotations are explainability-gated: name a real cause with confidence, or render nothing. Filler erodes trust faster than absence does.
- **The blend is the product.** One clean blended probability per question. Source names are quiet data-row chips at most, never in headlines, and per-source *lines* are forbidden on charts. Source divergence is a data-quality bug to fix upstream, not a feature to display. Three deliberate exceptions only: category-page cross-source spotlights, the playoffs "Sources" line, and My Stuff source dots.
- **Settled means settled** (see next section) and **no chart smoothing, ever** (fixed 0–100 axis; ugly movement is a data bug to fix, not a curve to sand down — see `chart-design-spec.md`).

---

## SETTLED-STATE LANGUAGE

One system-wide rule: **a finished thing shows its result, never a stale live affordance.** Implementation is per-surface but the grammar is shared — live percentages, movement pills, "Opened X/Y", trend arrows, and projected-finals are all gated behind `!isFinished` / `!resolved` and *replaced* by a result, not merely restyled.

**Badge grammar.** An uppercase pill, `text-[10px]/[11px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded`:
- **Won / HIT** → `bg-accent-live/15 text-accent-live` (a settled winner-field champion may use `bg-accent-brand/15 text-accent-brand`).
- **Final / Resolved / MISS** → neutral `bg-text-muted/15 text-text-secondary` or `bg-surface-elevated text-text-muted`.

**Event hero** (`app/events/[id]/page.tsx`, `components/event/EventLeaderboard.tsx`): the giant 48–52px probability block is replaced by the winner's short name + a **"Won"** chip; a tie shows **"Final · Tied"**. The winner team name is `font-semibold text-text-primary`, the loser `text-text-muted`. Never show "Final … Final" — the chart-card duplicate "Final" was deliberately removed (#190).

**Futures hero** (`components/FuturesHero.tsx`): `resolved` suppresses the big number and the movement pill; renders the winning outcome name + **"Won"** (or neutral **"Resolved"**). An upset gets one copy-only line: *"Markets gave this just {pct}%."* — factual, not celebratory.

**Feed cards**: list `EventFeedCard` shows a **"FINAL"** pill and hides the probability chips + bar; futures `FuturesFeedCard` shows **"RESOLVED"** + a green *"{winner}: {opening%} → Won"* line. Discover `EventCard` drops the win-prob strip for *"{winner} won"*. `formatFinishedDate` refuses to print a future date beside FINAL (gotcha #14 guard).

**Props, graded ("the script, graded")** (`components/PlayerPropsDashboard.tsx`): four states — `pre | live | done | settled`. A graded `StatBox` shows the actual stat colored by hit (team accent) vs miss (`#EF4444`), "of {line}", and a **"HIT"/"MISS"** pill; it prefers the authoritative server grade (`serverActual/serverHit`). Settled-but-ungradeable renders a muted **"Resolved · grading unavailable"** — never the misleading ~100%/0% pre bar (L2-112).

**Charts** (`OddsChart`, `components/event/SettledPathChart.tsx`): a completed chart shows the *full journey*. The domain ends at the real last-snapshot time, never the backend processing timestamp (gotcha #22/#46); the settled concept chart ("Path to resolution") is fixed 0–100, step-interpolated, no smoothing.

**Native parity** (`OddsChartView`, L2-216): the native event chart uses the **same single 0–100 axis** as web, defaulting to the blend-only line. The old mirrored ±50 delta rendering is gone — it was the main reason users fell back to Kalshi/ESPN during big games.

---

## LOADING & FAIL-CLOSED RENDERING

Speed and honesty are one system: what renders while data is in flight is a design decision, not an implementation detail.

**Progressive first card.** Web and native both render a bounded first page and paint the first card as soon as it is real, rather than blocking on a full payload (L2-207, L2-211, L2-217, #1480). Retries are classified — a timeout, an auth failure, and an empty result are visibly different states, never one generic spinner.

**Render-generation tokens.** Each render carries an immutable generation token so a late response from a superseded request can never paint over a newer one (L2-210 → L2-213). Response caches are principal-bound: a signed-out payload must never render for a signed-in principal.

**Fail closed on empty.** A predictive card that cannot lead with a real result is **suppressed, not rendered empty** (L2-215). An empty predictive shell reads as a broken app; absence reads as "nothing here yet." This is the loading-state corollary of *nothing beats unhelpful*.

**Last-good over nothing.** Where a cache exists, a stale-but-labeled last-good render beats an error state (L2-197, L2-214) — provided the staleness is stated truthfully in the UI, never silently.

---

## CONCEPT-PAGE PATTERNS

Event concepts (tournaments, fight cards, ceremonies, elections) render at `/event/<domain>/<slug>` (`app/event/[domain]/[slug]/page.tsx`) with section components in `components/event/`. The H1 is the *event*, not a market. Two `primary.kind` layouts: **`winner_field`** (golf/tennis/F1 leaderboard) and **`co_equal_list`** (UFC card, awards, elections).

**Slug / canonical / redirect rules.** Public URLs are colon-free (`/event/mma/ufc-319-...`), replacing the old `%3A`-encoded `event:domain:slug` form (L2-113). The page reconstructs the API key from the two decoded segments, injects a `<link rel="canonical">` to the pretty slug, and does a client 301-equivalent `router.replace(...)` when the backend returns a prettier self-resolving slug (combat = headliner + date). Live SWR refresh is 45s live / 5min for upcoming-within-24h.

**Header** (`EventHeader.tsx`): H1 `text-title-1`, a status chip (live `bg-accent-live/15`, settled neutral, upcoming `bg-accent-brand/10`), an optional **"Major"** chip (`bg-accent-futures/10`), a "Starts in N days" countdown, a "date · venue · location · N markets tracked" meta line, and an anchor-scroll pill nav.

**Bout / matchups grid** (`MatchupsRail.tsx`): mobile is a horizontal rail; **desktop is a responsive grid, not a horizontal scroll** — `flex gap-3 overflow-x-auto ... md:grid md:grid-cols-2 lg:grid-cols-3 md:gap-4 md:overflow-visible` (the L2-113 desktop fix). Each `MatchupCard` is `bg-surface-card rounded-card shadow-card border`, top-2 outcomes with a `FighterAvatar` + name + mono probability + `accent-brand` fill bar. Decided fights collapse into a dimmed `<details>` **"Completed (N)"** with a neutral **"Final"** chip. `FighterAvatar` uses cached Wikipedia headshots with an initials fallback.

**Fused / blended leaderboard** (`EventLeaderboard.tsx`): one row per competitor — rank (mono) · name · optional `#seed` chip · a **"Leader"** chip on rank-1 when live · `accent-brand` probability bar · optional `Sparkline` (real history only, hidden `<sm`) · 24h movement (▲ `text-accent-brand` / ▼ `text-accent-danger`) · big mono probability. The golf-live variant fuses tour data into the row: `Pos · Player · To-par · Thru · Δ · Win%`, sorted by score, with a `FreshnessChip` "as of" stamp; cut/WD/DQ players sink into a collapsed **"Missed cut (N)"** and show "—" for win%. The settled variant is a **"Final result"** heading + 🏆 champion + **"Won"**, with a collapsed **"Did not win (N)"** list (no stale percentages, L2-81). A live/upcoming winner-field also gets `RaceToTitleChart`; co-equal events use `TwoSidedTimeline`.

---

## COCKPIT (admin) TILE CONVENTIONS

The ops cockpit (`components/admin/AdminCockpit.tsx`, data from `GET /api/admin/cockpit`) is admin-only, but its status grammar is worth codifying because the sentinels reuse it.

**Status tokens** (`green | amber | red | unknown`):
- text — green `text-green-600`, amber `text-yellow-500`, red `text-accent-danger`, unknown `text-text-muted`.
- background — `bg-{green|yellow}-500/10 border-*/20`, red `bg-accent-danger/10 border-accent-danger/20`, unknown `bg-surface-card border-surface-border`.
- Flow-Sentinel dots — solid `bg-green-500` / `bg-yellow-500` / `bg-accent-danger`.

**Health tiles**: a 2/4-col grid of `rounded-xl border p-4` cards tinted by status; `text-micro uppercase tracking-wider` label + `text-2xl font-bold` value; the whole tile is a drill-in `<Link>`.

**Tracked badges** (the RED-honesty pass, L2-104) distinguish a *known* red from a fresh alarm:
- `tracked` → yellow linked pill `bg-yellow-500/10 text-yellow-600`, "{label} {value} — tracked #NNN".
- `artifact` → muted `bg-surface-elevated text-text-muted`, "… — {expected note}".
- `untracked` → the only four-alarm state: `bg-accent-danger/15 text-accent-danger ring-1 ring-accent-danger/40` with a bold `⚠` prefix.

**"Waiting on you"** and **quick-eval** blocks are `rounded-xl border border-surface-border bg-surface-card p-4`; empty state reads "Nothing waiting — you're clear." Accept/Reject/Skip buttons follow the accent grammar (green accept, `accent-danger` reject, muted skip).

> **Token debt to flag in reviews**: `ThresholdGrid`, `ProgressionLadder`, and the admin health helpers still use raw Tailwind heat colors (`text-green-400/amber-400/orange-400/red-400`, `text-green-600`) instead of `accent-*` tokens. The token system is not yet universal on threshold/admin surfaces.

---

## TECH STACK (for code generation context)

- Next.js 14 App Router, React, TypeScript strict mode
- Tailwind CSS with custom design tokens (see `tailwind.config.ts`)
- Framer Motion for animations
- Recharts for production data visualization
- shadcn/ui primitives (card, badge, button, tooltip)
- Lucide React for icons
- Inter + JetBrains Mono (loaded via `next/font/google`)
