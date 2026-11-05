# Event headline: expectations, movement, result

PILLARS: FORMATTING / TRUTH.
SHIP: A fan can read the chances and expected final before play, see how both have changed during play, and compare the actual result with the retained pregame expectation afterward.

This records the user’s October 21 headline requirement for the final event-page overhaul on web and native. It supplements web-projected-final-followthrough-20261019/DESIGN-BRIEF.md. It does not declare implementation complete or replace the existing chart assignment.

| Phase | Primary chance context | Primary score / expectation context |
| --- | --- | --- |
| Pregame | Prominent win chance for each competitor; retain draw where applicable. | Readable, named projected final in compatible sport units. No fabricated current 0–0. |
| Live | Prominent current win chance visibly compared with the retained pregame chance. | Actual score and game state remain prominent. Current projected final is directly comparable with the retained pregame projection, in the same team order and units. |
| Final | Winner/result plus a clear reminder of the pregame chance. Do not substitute a fabricated 100% market observation. | Actual final directly compared with the retained pregame projection, with explicit team association and scoring-period basis. |

## Selected hierarchy

These comparisons belong directly in the headline, not only inside Details, a chart scrub or a prop card. Keep current values visually primary; use compact, legible baseline context beside/beneath them. The chart remains the anchor with adequate plot height. Remove low-value provenance from the headline before compressing meaningful values. Phone may stack; larger screens can align the same quantities in columns. Avoid a sprawling table, color-only meanings, unexplained abbreviations and duplicate baseline labels.

Use actual retained game data for design and acceptance. Never invent a convenient before/after pair. The visible current and retained pregame levels must make movement understandable. Prefer a labelled before/current pair or retained baseline directly under the current value; a separate numeric delta is not required. If a numeric movement is printed, it is percentage-point change, not relative percent change, and must agree with the displayed levels. Preserve qualified home/away/draw semantics rather than manufacturing a complement.

## Baseline and availability

Compare the same event, competitor, quantity, units and scoring period. State the available baseline honestly: opening chance is not automatically latest-before-play chance. Current implemented forecast evidence is labelled “before scheduled start”; do not silently claim a proven actual kickoff cutoff. Show the baseline timing and source meaning in the existing disclosure when necessary, while keeping its phase label visible.

A pregame forecast cannot acquire a current label during play. An unavailable/unreliable current reading must be identified honestly; retained historical context can remain labelled. Do not reconstruct a pregame baseline from the final or last in-play forecast. Missing forecasts are omitted or clearly unavailable, never fabricated.

## All-sport obligation and delivery boundary

The hierarchy applies across sports. Score-pair projections require a qualified sport/format source. Combat, golf and other field events use meaningful sport-specific expectation/result quantities where a final score pair is inappropriate; that adaptation must still make pre-event versus current versus actual unmistakable. Unsupported omission remains incomplete coverage, not all-sports completion. NEXT-FORMAT-PROJECTION-READINESS-20261021.md preserves the present source limits.

This is an event headline requirement. It does not mandate placing every comparison in every compact feed card. Existing readable card/final-comparison work retains its accepted scope.

Build 77 is an available increment, not completion of this phase contract. The live-versus-pregame comparisons are not yet fully implemented/accepted. Existing UX chart work continues in its current scope/order; Native retains composition, Apple/runtime and packaging. Root should carry the remaining headline comparison delta within existing #9483/#11296 ownership at the next cleared boundary, without a duplicate source author or a new hold on qualified delivery.

Concrete implementation seams are maintained in [web comparison follow-through](headline-live-comparison-followthrough-20261021/DESIGN-IMPLEMENTATION-DELTA.md) and [native comparison handoff](headline-live-comparison-followthrough-20261021/NATIVE-CONSUMER-SEAM.md). The latter preserves the admitted current pair's typed period/unit, existing final-only resolver and native two-group headline layout. Current source/review/delivery evidence belongs in CURRENT-IMPLEMENTATION-REFERENCE.md; an implementation brief is not evidence that this contract has shipped.

## Acceptance

Use retained real pregame/live/final cases per admitted format to verify visible chance baselines and direction, team-aligned projection baselines and actual/game-state clarity. Check phone readability without sacrificing the chart, appropriate large text/accessibility meaning and larger-screen alignment. Source, rendered, served and installed acceptance remain distinct. No new capture or Apple run is requested by this contract alone.

## Actual Native consistency counterexample retained — October22

The current real Packers14780562 page shows a before-scheduled-start headline forecast Dallas28–Green Bay27 while its final story shows Cowboys26.5–Packers27.5 and says Packers won as projected. Both source paths may be independently admitted, but those opposite leaders cannot silently share an unqualified pregame expectation. This is a required consistency case for this contract: use the same qualified retained baseline for the ordinary comparison, or explicitly identify a deliberately different earlier historical basis. Preserve original history values, units, periods and team order. Exact pixels, prior owner input and immutable paths are retained in native-single-trajectory-adoption-20261021/real-page-normal-393-20261022/. This does not reopen paid source review of an unchanged live-comparison contribution or add a new author/release hold.
