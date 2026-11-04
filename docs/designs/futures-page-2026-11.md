# Futures page — November 2026 · Iteration 2

**FORMATTING / TRUTH. Ship:** Event Details and futures read as one product. Branch `design/futures-page-proto`; six production captures under `/kernels-preview/futures/[id]`. [Preview and comparisons](futures-page-2026-11/iteration-2/README.md). Captured Nov 3, **6:33 PM PT**; dated snapshots. No production route, API, stream, Midterms or round-up changes; no PR to master.

**Reuse decides the design.** The references are `live-game-detail-v2.html`, shipped `app/events/[id]/page.tsx`, and `EventDetailView.swift`. Gone: the standalone oversized numeral, desktop sidebar and top review panel. Adopted: paired identity hero, native typography, 12px card rhythm, chart card and below-chart rail. The actual shipped app width governs desktop; the HTML’s 680px canvas is a demonstration width.

| Futures block | Actual web component / composition | Actual SwiftUI mapping |
|---|---|---|
| Frame, back link, status/date | Game page’s inline `space-y-3`, hero frame and meta strip | `EventDetailView.contentView`, `heroSection(_:)`, `heroStatusBadge(_:)` |
| Duel answer / 56px identities | `EventHeroProbabilityPair`; game hero’s identity boxes | `heroSection(_:)`, `heroValue(away:)`, `nflPairedSide`, `nflPairedCenter` |
| Winner / final outcomes | `SettledOutcomeHero`, `SettledMark`, `outcomeRowVerdict` | Final branches of `heroSection(_:)` / `nflPairedSide` |
| Field / participation band | Actual `EventLeaderboard`, three / six rows plus disclosure | New adapter using `EvolutionLeaderboardHeader` / `EvolutionLeaderboardRow` in `EvolutionChartView.swift` |
| Quantity strip | New body following `FinishPositionLadder` / `PlacementGrid` grammar | New adapter following `EventDetailView.nbaLadders` and `LadderCardView` |
| Chart card / controls | Game card frame, `ChartRangeChips`, `ChartFullscreenDialog`; actual `FuturesChart` from event `WinnerEvolutionChart` / `SettledPathChart` | `chartHeaderBar(_:)`; actual `OddsChartView` in `contentView`, its `selectedRange` binding; futures-data adapter |
| Age / quiet ⓘ | Actual `PriceAgeMark`; reserved source marks, no sheet | `PriceAgeMarkView`; future disclosure maps to `probabilityDetails` / `FreshnessRevealView` |
| Bigger Picture | Actual `MatchupsRail`, opt-in market links; below-chart rail/grid | Actual `RelatedFuturesView` called from `contentView`; related-data adapter |

**New shape bodies.** Field shares remain full-field shares: top three and **21 more**. Participation bars stay independent. Quantity thresholds ascend. One leg never acquires a No. Non-duel heroes use population/period context opposite the leader. Initials occupy native identity boxes where participant artwork is absent. Bottom review controls label state studies; assumed grades never enter history. Native mappings identify existing primitives and required adapters; no native build is claimed.

**Number contract.** Blend only; attribution-only venue names; whole numbers; no gambling formats. Raw chart segments, fixed **0–100** domain, real gaps/results. Game `OddsChart` auto-scales; the shared event-composition `FuturesChart` honors this brief inside the same card. A default-off fit option keeps the entire timeline and requested height at 390px; other callers retain their geometry. Probabilities, results, counts and tooltips reserve ⓘ for #11920; dates/ticks/control labels remain labels. No source sheet or live EKG on frozen captures.

| Capture | Boundary the design preserves |
|---|---|
| 109085 · Kansas Senate | Existing registered-twin container supplies the blend by outcome ID. History is single-venue, explicitly attributed; blended history is missing. |
| 108629 · closest Governor race | All 24 legs retained; expanding never normalizes the displayed shares. |
| 65536371 · Denver snow | Six thresholds, five isolated readings: honest empty chart. Served 4/6-inch chances remain 60/64%. Structured threshold bounds are absent. |
| 227 · CFP qualifiers | Stored `field` + `mutually_exclusive:false` selects an independent band; classification unchanged. Dedicated participation relation absent. |
| 109918 · one leg | Resolved, `ungradeable_result`: “Result unavailable,” historical 58%, no asserted loss. Open/settled versions are labelled studies. |
| 108645 · Georgia Governor | `api_settlement`: Keisha Lance Bottoms won; Rick Jackson lost. Grade time Nov 3, **6:27 PM PT**, found from grades; absent from detail, retained separately in capture. |

The settled hero’s legacy authority type lists only score/tournament. The preview bridge retains runtime `market` provenance; a production port needs an honest type extension. No API field was added.

**Taste calls.** Old **A–D retired**: event hierarchy, independent semantics, settled language and below-chart placement settle them.

- **E — non-duel opposite slot:** population/period context (**recommend; shown**) or an empty slot. Context gives the paired composition meaning without implying another probability.
- **F — missing history:** event-sized chart frame with an explicit empty state (**recommend; shown**) or a compact notice. The frame preserves the same reading sequence through a data gap.

Evidence: real recent event left, hosted futures right; **390px and 1280px per half**, all six plus both one-leg studies.
