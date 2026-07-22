# Futures Market Detail Page — Design ↔ Implementation Reconciliation (L2-161)

Reconciles the Claude Design handoff (`project/Futures Detail.dc.html`) against
the shipped futures detail page (`frontend/app/futures/[id]/page.tsx` +
`components/FuturesHero.tsx`) and the standing rulings. **Rulings win.**

## The headline finding
The shipped page already implements ~90% of the design's *shippable* core
(resolved-aware hero, 7d/30d/All trend chart, resolution panel, "More in this
story" constellation, provenance mark, loading + sparse states, threshold-ladder
grouping). And the design's marquee "signature" — **per-source breakdown +
disagreement spread plot** (Section 04) — is squarely **blocked by the
blend-only ruling**, which the page already enforced (#883 removed the per-source
`SourceAggregationBlock`). So this queue is mostly *reconciliation* plus one
rulings-safe visual upgrade.

## Shipped this queue (rulings-safe)
- **Hero C — "ambient history"** (the design's explicitly-marked *ships* hero).
  The hero outcome's 7-day probability curve now sits *behind* the numeral as
  quiet texture (area fill at 7% + line at 50% opacity), on a fixed 0–1 domain
  (no auto-scale — matches the trend chart's fixed-axis principle). New
  `AmbientHistory` sub-component in `FuturesHero`, fed by a pure
  `buildAmbientPoints(historyOutcomes, heroOutcomeId)` helper. accent-brand — the
  single blended line, **never** a per-source overlay.
- **64px hero numeral** (up from 56px) with the `%` at 28px — the design's
  "loudest thing on the page," matching the feed card's numeral for continuity.
- **Movement delta in a tinted pill** — `↑ 11 pts` in an accent-live/15 pill;
  `↓` in accent-danger/15 (design detail #4), replacing plain colored text.
- All of the above is **opt-in** (`sparklinePoints`): the hero falls back to a
  plain numeral when no history is available, and every existing state (resolved
  winner + chip, yes/no bar, provenance mark, resolution date) is preserved.

## Already shipped before this queue (design goals already met)
- Resolved hero = winner name + Won/Resolved chip, **no live number** (settled-
  means-settled; the design's "Resolved" edge state).
- Full-life settled chart window + preselected outcomes (L2-156).
- 7d/30d/All trend chart on a fixed 0–100% axis (the design's history panel).
- Resolution panel, "Part of:" up-links, "More in this story" related rows.
- Provenance mark: 3-dot cluster + "Aggregated from N sources" (a *count*, not a
  comparison — blend-safe).
- Loading skeleton (`LoadingState`), sparse/limited-history honest empty states,
  threshold-ladder grouping (`thresholdGroups`).

## Divergences (rulings / data reality win)
1. **NO per-source breakdown expansion (Section 04 "Show ›").** The design
   expands the aggregation strip into Kalshi 67 / Poly 69 / Odds 68 / Stat 68
   rows. The **blend-only ruling** ("source divergence is a data bug to fix, not
   a feature to show") forbids this on the futures detail surface; #883 already
   removed it. Kept: the quiet provenance count only.
2. **NO "disagreement" spread plot / range escalation.** The design's
   >5-pt-spread variant (a number line with four source dots that "climbs under
   the hero") is the exact comparison surface the ruling supersedes. Not built.
3. **NO "they agree within 3 points" sub-line.** It states divergence; omitted.
4. **NO source-attribution ↗ outbound links.** The design makes per-source ↗
   the page's only outbound surface. With no per-source rows, there are none —
   and the page stays understand-never-transact with zero book links.
5. **Design tokens, not raw hex / Inter / JetBrains import.** The prototype hard-
   codes `#F5F5F7`, `#10B981`, Inter + JetBrains Mono. We use surface/text/accent
   tokens and the site's existing `font-mono`. The ambient line is accent-brand,
   not the prototype's emerald (emerald reads as "up"; the ambient is neutral).
6. **No device-chrome / masthead / annotation furniture.** The `.dc.html` is a
   spec canvas (phone bezels, pins, legends). Only the real hero/page content is
   implemented; the page lives inside the app's own layout.
7. **No odds formats anywhere** (the +9900 leak class) — enforced; probabilities
   only.

## State honesty
- Ambient layer renders only with ≥3 real history points; otherwise a plain
  numeral (no empty frame).
- Resolved markets never render the live numeral or the ambient layer.
