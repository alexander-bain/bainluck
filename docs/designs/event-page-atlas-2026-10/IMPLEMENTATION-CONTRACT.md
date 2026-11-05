# Event-page implementation contract — current design

PILLARS: FORMATTING / DISCOVER / TRUTH.
SHIP: A casual fan watches a readable probability journey and relevant visual prop stories, then opens any interesting card without losing its meaning or their place.

This contract supersedes the static-feed and always-0–100% instructions in atlas-v6/COMPONENT-CONTRACT.md. Historical packages retain their evidence; they are not current behavioral instructions where they conflict with this contract. It consolidates Alex's later moving-feed, chart-height, full-size exploration, pre-event labeling, golf and DataGolf directions. It does not change the first six-part #9483 delivery scope or claim production delivery.

## 1. The anchor

Win probability is the first value a person sees. Put competitor names, actual score, current sport state and an admitted projected final together. Actuals use the sport's units; they are never drawn as probabilities. In a final event, show the confirmed result and pre-event expectation while keeping the probability journey inspectable. A result is not a traded 100% observation.

**Current anchor overrides (October 21–22):** [HEADLINE-PHASE-CONTRACT-20261021.md](../HEADLINE-PHASE-CONTRACT-20261021.md) specifies the direct headline comparisons: pregame chances and qualified projected final; live chances and projection compared with retained pregame values alongside actual score/state; final result and pregame chance reminder alongside actual final versus retained pregame projection. Required comparisons are visible in the headline; provenance belongs in the existing disclosure. Sport-specific expectation formats remain subject to their own admission contracts.

The later selected matchup chart is [one primary probability trajectory with explicit team meaning](../native-single-trajectory-adoption-20261021/NATIVE-ADOPTION-BRIEF.md), transferred from the accepted web chart. This supersedes this contract's earlier instruction to normally draw both competitor histories. Follow that brief's qualified two-sided versus home-only axis, stable primary identity, truthful adaptive range, named source disclosure and fallback rules. Independently supplied away and draw readings retain their own qualified meaning; never manufacture away=1-home without a proven complementary binary contract. Golf and other field charts remain separate designs. Break missing intervals, exclude settlement markers from the observed probability journey and add no decorative smoothing. This pointer changes no source admission, historical evidence or delivery scope; the frozen v473 adoption map is unchanged.

A normal phone plot needs useful vertical space: the inspected references use about 212–230pt, not a compressed sparkline above a crowded card. At small available heights or enlarged text, let the chart and content scroll, keep a compact score/chance anchor and provide Chart return. Do not shrink the graph merely to fit a whole prop below it. Wide layouts put the anchor beside independently scrollable cards.

Use verified quarters, innings, sets, maps, rounds or holes on the timeline. First-observed boundaries must be labeled as observed, not exact start times. Put supported scoring events in a small aligned rail; cluster overlapping marks and disclose them on selection. Never infer a game minute from scheduled kickoff or a goal time from a later score capture. Missing state is explicitly unavailable.

Settled field/prop histories follow the [result-mark disposition](../settled-history-result-mark-20261022/DESIGN-DISPOSITION.md): Won/Lost is a distinct result annotation, never a synthetic probability sample, a timed jump to0/100 or a scrub target. All settlement bases follow that rule. A leg without real observations gets no invented probability coordinate; an entirely unobserved history keeps its sparse state. Existing web/Native ownership and source-placement holds remain unchanged.

Inspecting history adds a dated readout; it does not replace the pre-event baseline, rewrite current actuals or settle a prop. Exact-point selection must refuse unavailable gaps. Keep source/clock/method explanations behind the info control; active uncertainty remains visible.

## 2. Moving visual stories

The intended product is a moving, context-sensitive stream of visual cards beneath stable chrome. Auto-advance and reranking are supported; a static-only feed is not the final design. Ten-second movement in the recorded replay is a demonstration setting, not a production timing mandate.

Rank existing, validated card families using available event context. The v102/v105 replays use explicit editorial rules; neither is connected AI ranking. Production ranking must use the existing async/cached ranking and enrichment path. A language model must not invent source facts, probabilities, causal claims or new composite odds. Novel generated prop combinations remain v2 under #10353–#10357.

Hold card order and automatic advancement during touch, focus, scrolling, inspection, details or full-size reading. Keep the selected original and the facts being read stable and dated; independently qualified score/chance in compact chrome may update. Queue pending priorities until the person returns and explicitly resumes. Hidden/background and reduced-motion states disable automatic advancement. Reduced motion retains manual navigation and all content.

The probability anchor stays visually stable while cards advance. A new rank cannot silently replace a selected golfer, threshold, outcome or expanded card. No giant table or mandatory search precedes the curated visuals. All props remains a secondary, complete route with categories, optional search and bounded windows.

## 3. Full-size reading

Every admitted story needs an expansion route when a phone cannot show it comfortably. Use a near-full-height reader with compact match/chance context, a neighboring-card peek, named card/count and left/right swipe plus accessible buttons. Single-card readers omit meaningless paging cues. Each card scrolls vertically independently; charts keep useful size. On iPad/Mac expansion is optional.

The page model owns exact selected outcome, card, period and history-inspection state. Compact and expanded instances share it. Details returns to the same selected card; closing returns to the previous feed position. Opening or closing never silently resumes movement. Remounting at another width must preserve the selection; model-only assertions do not prove device scroll/focus return.

## 4. Temporal and numeric language

| Evidence | Required meaning |
| --- | --- |
| Pre-event baseline | Explicit Pregame / Pre-match / Pre-race / Pre-event label, source basis and clock in details. Opening fallback is disclosed. First recorded is not automatically pre-event. |
| Qualified current chance | Only an eligible price can occupy a current chance slot. A timestamp alone is insufficient proof of eligibility. |
| Historical observation | Recorded, phase and timestamp remain explicit; this is not live now. |
| Actual | Score/stat/result with its own units and observation clock. No earlier actual is inferred from a later box score. |
| Projection | Valid paired source/clock/unit and lifetime. No mean, median, interval or expected score is invented from asynchronous thresholds. |
| Settlement | Won/Lost/Hit/Missed/void/pending/conflict comes from qualified result evidence; missing or conflicting remains unconfirmed. |
| Unreliable current reading | Keep the prop. Say No recent probability update and withhold its headline probability mark; retain the last recorded probability and its timestamp in details. |

The unavailable-current wording follows the current [#10868 design brief](https://github.com/alexander-bain/bainluck/issues/10868). It describes an unavailable or unreliable current chance, not every historically old observation. A retained pregame baseline that met its existing admission policy remains useful historical context under an explicit Pregame/Pre-match/Pre-event label and its own source clock in details; elapsed time after the game alone does not erase it or turn it into a live chance. This clarifies phase meaning without changing source eligibility or admitting an unqualified old quote. Actual sporting performance and qualified settlement remain independently visible when a current probability is unavailable.

Use the shared precision contract. Only exact 0 and 1 display as 0% and 100%; near-boundary values retain decimals/inequality labels. Missing/invalid values are unavailable, never zero. Hollow baseline / filled recorded markers and actual rules / outlined projection squares apply to comparative plots. Rings, tiles and fields must use direct temporal labels when glyph shape alone cannot carry that distinction.

One blended number per qualified semantic outcome is the production product. Independently timed provider examples in the archive are evidence studies, not authorization for a default source-disagreement dashboard. Do not normalize independent contracts merely to sum to 100%.

## 5. Finite rendering grammar

Choose by typed meaning, never title similarity alone. These are finite primitive families with composition rules; this is not proof that every venue combination has been observed.

| Primitive | Use when | Concrete browser implementation |
| --- | --- | --- |
| Quantity milestones | Same subject, unit, comparator, period and settlement; thresholds occupy true numeric positions | LivePlayerProfiles, PlayerMilestonePlot, TotalExpectationPlot |
| Discrete count rails | Overlapping 1+/2+/3+ counts; never slices of a 100% total | HockeyScoringCard, player profiles |
| Signed margin | Verified competitor orientation and scope | MarginExpectationVisual |
| Actual versus forecast | Compatible units and admitted projection | ProjectionJourneyCard, FinalTotalTrack |
| Single binary/named outcome | One supplied predicate; no invented opposite leg | SingleOutcomeVisual, BinaryProbabilityDial |
| Paired outcomes | Two exact supplied sides, independently qualified | PairedOutcomeVisual |
| Named field | Winner, scorer, method or category outcomes; unknown field mass stays unknown | FieldEventHeader, CatalogProbabilityCard, CombatOutcomeCards |
| Exact-score map | Explicit discrete coordinates and complete selected predicates | ExactScoreGridCard, TennisScoreOutcomeCard |
| Period/series path | Explicit set/map/round/series relation; no derived joint probability | AssociatedSeriesCard, TennisFinal, CombatDurationCard |
| Independent placement | Top-N/podium/cut/qualification; outcomes need not sum to 100% | PlacementFinal, RacingFinal, DataGolfOutlook |
| Complete original prop | Untyped/composite/interval/novel/conflicting meaning | CatalogProbabilityCard and exact original details; no guessed chart axis |

Specialized families take precedence over generic one-/two-row cards. Group only matching subject, unit, comparator, period, scope, settlement and compatible evidence basis. Keep source-market/outcome IDs alongside the semantic ID. A field placeholder is not a competing team. An explicit composite stays one supplied predicate; never multiply its legs.

All implementations above are in the retained browser source referenced by COMPONENT-MAP.json. Production adopters use their existing typed adapters and shared formatter, not the archive's fixture registries or specimen-specific parsers.

## 6. Golf

Golf uses a tournament probability journey, not a forced two-team scoreboard. Show a small, contextually selected cohort with stable golfer identity and a secondary chooser; the demonstrated policy is selected golfer plus two contenders. Do not replace the golfer while they inspect.

Use a clearly labeled zero-based adaptive y-axis so early low probabilities remain legible, with a full 0–100% option. Provide Before, round and tournament views. Compress long empty overnight intervals only with visible breaks; do not connect across unobserved gaps. Round markers need their own evidence, not assumed tee times. Point inspection uses exact captured timestamps and says Not recorded where that golfer has no observation. The v130 cutoff is specimen-specific, not a universal finish detector.

Use DataGolf-derived inputs for finish profiles, probability movement and useful comparisons, with their actual provenance/clock limitations. Do not copy its product or substitute model estimates for traded probabilities. Actual score, model probability, earlier expectation and settlement are independently labeled. Current references do not establish provider generation clocks, strokes-gained attribution or contemporaneous actual-score histories.

## 7. Complete access and native quality

Every original associated prop remains reachable even when its specialized visual is refused. Category filters and bounded windows must retain exact selection; absent/filtered/conflicting selections remain explicit. A renamed or reordered outcome must not inherit another outcome's probability or result. The source catalog count is outcome rows, not semantic props or distinct markets.

Use native SwiftUI/Charts/path/text and native interaction primitives. Reference renderers and AppKit harnesses are excluded from app targets. Normal/enlarged phone and wide layouts must be visually read; compilation, tests, HTTP success or screenshot existence alone do not establish readability. Browser, standalone native, integrated iOS and physical-device evidence are separate states.

## 8. Current scope and delivery

COMPONENT-MAP.json chooses the current browser/native packages. COVERAGE.md distinguishes demonstrated contexts from unverified combinations. Evidence files retain exact paths and hashes. The acceptance ledger is a status assessment, not a release waiver.

The first six-part #9483 milestone is unchanged: probability/score/state headline, routine-info disclosure, existing history inspection, admitted projection placement, existing visual props and complete original browsing. It does not wait for auto-scrolling, every sport, generated combinations or this consolidated handoff. UX owns source adoption, Native owns Apple/runtime/packaging, Integrator owns merge. This design chat owns isolated references only.
