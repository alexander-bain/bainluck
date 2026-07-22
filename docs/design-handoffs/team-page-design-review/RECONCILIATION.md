# Team Page v2 — Design ↔ Implementation Reconciliation (L2-162)

Item 0 of queue L2-162. This records how the Claude Design handoff
(`project/Team Page - Red Sox.dc.html`) was reconciled against the shipped v1.5
(L2-158) and the standing product rulings. **Rulings win** where they conflict
with the mockup.

## Shipped from the handoff
- **Team-color accent** — hero left-rail (already v1.5), plus season-journey line
  color, division-race highlight rail/row tint, championship-path bars + numbers.
- **Hero headline number** — the team's championship "price" (tier-1 prob) + 24h
  delta, right-aligned in the hero (new; the blend-is-the-product ruling).
- **Season journey** — one line, championship (or best available) prob over the
  season, via the consolidated `FuturesChart` (fixed 0–100% axis, straight
  segments = no smoothing). New `TeamSeasonJourney`.
- **Division race** — rivals × (Division / Playoffs / Champion), sortable,
  current team highlighted. New `TeamDivisionRace`, fed by the existing
  `/api/playoffs/{slug}` championship grid (no backend change).
- **Championship path progression** — Division → Conference → Championship
  connected with arrows, replacing v1.5's flat 3-card grid. New
  `TeamChampionshipPath`.
- **Section order** now matches the mockup: hero → today/next → recent results →
  season journey → division race → season futures.
- **Mobile-first** — cards stack; division grid scrolls horizontally in its card.

## Preserved from v1.5 (behavioral logic + GA hooks, unchanged)
- `usePageTracking` / `useScrollDepth` / `useEngagementTime`.
- Probability-first upcoming cards + LIVE-chip honesty (`isGameLive`).
- Result-first recent cards + doubleheader G1/G2 chips + settled-date guard.
- "we had them at X%" / upset flag stays gated on the backend pre-game field
  (still a backend gap — recent cards remain result-first until it lands).

## Divergences (rulings / data reality win)
1. **Raw hex palette → design tokens.** The mockup hard-codes `#F5F5F7`,
   `#111827`, etc. We use `surface`/`text`/`accent` tokens; the only inline
   colors are the team's own `primary_color` (legit dynamic data), exactly as
   v1.5 already did.
2. **No JetBrains Mono / Inter import.** We use the site's existing `font-mono`
   for tabular numerals rather than pulling Google Fonts.
3. **Season-journey annotations skipped.** The mockup shows hand-placed callouts
   ("7-game win streak", "Casas to IL"). No data source exists for these, so
   they are omitted rather than faked. The chart draws only real snapshot points
   (renders nothing below 2 points — no empty frame).
4. **Division-race columns are data-driven.** The mockup shows Division /
   Playoffs / World Series. We project Division / Playoffs / Champion from the
   grid's real cells (`division`, `make_playoffs`, `championship`) and drop any
   column no team has, rather than showing an always-3-column table.
5. **No duplicated app header.** The mockup includes a sticky top chrome bar; the
   team page already lives inside the global layout nav, so it is not re-added.
6. **No smoothing / no auto-scaled axis / no odds formats / no internal taxonomy
   chips** — all enforced (rank-in-league chips like "#4 of 30" are kept; those
   are public standings, not internal Tier/EI taxonomy).
7. **Championship path grouped into Season Futures.** The mockup nests the path
   under "Season futures"; we keep it as the first card there, with props/awards
   (tiers outside 1/2/4) as the sibling list — matching the mockup's
   "championship path + props separate" intent without duplicating markets.

## State honesty (sections hide rather than lie)
- Season journey: hidden unless ≥2 real history points exist.
- Division race: hidden unless the team is in the grid AND has ≥1 division peer.
- Hero headline: hidden when no championship-path probability is available.
