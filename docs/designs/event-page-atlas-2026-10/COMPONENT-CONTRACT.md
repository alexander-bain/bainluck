# Probability-first event pages — implementation contract

PILLARS: FORMATTING / TRUTH / DISCOVER.
SHIP: a casual fan sees who is likely to win, how the game compares with expectations, and the most useful prop stories; every associated question remains reachable.

This supersedes the original score-first brief and the rejected v3 numerical catalog. The approved visual reference is expectation-v4, with the explicit temporal grammar from temporal-v5. Atlas-v6 extends that direction. It is an isolated design reference, not deployed product source.

## Hierarchy and interaction

1. Win chances lead the headline. Team/contender names, actual score, valid paired projected final and the sport's game state belong together. On completion, show the winner/result and opening chance; never substitute the terminal trade for the result. A draw is an explicit outcome where the winner contract permits one. A field shows named leaders and reaches the full field; missing contenders do not become a made-up Other share.
2. The probability journey is a wide, quiet plot directly beneath/beside the headline. Direct team labels, consistent color identity, 0–100% scale, exact observation inspection, no decorative smoothing. Missing intervals stay broken. The retained capture uses a five-minute gap rule; production takes the evidence cadence from the history contract, not this prototype constant.
3. Curated groups explain expectations and their divergence. The first screenful is graphs, not a list of 1,000 prices. Preserve the card a person is reading while new data arrives. Update its marks without rearranging the page. A newly relevant group enters after interaction ends or an explicit refresh.
4. Stories / All props is the escape hatch. All props offers category chips, search, grouped questions and bounded pagination. Source rows are not counted as distinct semantic questions. A question's complete predicate, sides, unit, period and settlement basis remain in details.
5. A tap on a mark selects one question; a subsequent detail action opens its evidence. Keyboard and accessibility users get equivalent controls. Phone details are a native sheet; larger screens use a focus-trapped dialog or inspector. No Play updates button. Data updates automatically; nothing auto-scrolls by default.

## One visual grammar across different graphics

| Meaning | Mark | Label and axis |
| --- | --- | --- |
| Archived pregame probability | Hollow circle | Pregame chance; disclose opening fallback when applicable |
| Probability at a selected in-game timestamp | Solid team-colored circle | Recorded in game / explicit timestamp |
| Change in the same probability | Connector between the two circles | Delta in percentage points, same question and baseline |
| Actual achieved value | Thick vertical rule | Actual 72 yards / actual 190 points / final 1 home run; on the **units axis** |
| Projected final value | Outlined square | Projected final, unit, source/as-of; on the same units axis as actual |
| Resolved outcome | Check/cross plus result word | Won/Lost, Hit/Missed where appropriate; never hollow/filled probability semantics |
| Unsupported or unreliable current price | No current mark | **No recent price**; last captured value in details |

Hollow is never reused to mean missed. A final result is never manufactured into a traded 100% point. A raw settlement-era 1.0 is labeled as a captured settlement-era value in details, not a recent trade. A source's opening price is not relabeled pregame unless the baseline contract actually allows that fallback and the fallback is disclosed.

The actual score and market price have independent timestamps. A live snapshot does not authorize inventing the actual stat at an earlier/later price time. In the atlas, NBA detail, score and history were separate captures; none is advertised as live now.

## Finite primitive families

These are reusable renderers, not one custom renderer for each league. The dispatch key is semantic structure, not the market's prose alone.

| Primitive | Suitable contracts | Do not infer | Bound reference |
| --- | --- | --- | --- |
| Quantity milestone profile | Continuous/count thresholds: yards, points, rebounds, hits, goals, strikeouts, combined stats, totals and team totals | Density, mean, median, likely range, or chance between thresholds | NFL 42 pregame points; NBA live totals |
| Count probability rails | Discrete 1+/2+/3+ events | That overlapping milestones sum to 100% | Hurts passing TDs; MLB HR pair |
| Signed-margin profile | Handicap/run-line/puck-line, explicitly typed team orientation and scope | Distribution mass by subtracting asynchronous quotes; clipped actuals | Suns spread contracts, actual +10 |
| Forecast/actual dumbbell | Compatible same-unit actual and paired projection | Expected final from a threshold or arbitrary independent legs | NFL pregame/final; NBA recorded live |
| Binary movement rail | Yes/no, both score, extra innings, cut made, retirement, first event | Other leg exists merely because the first leg exists | MLB extra innings 11%→16%, +5pp; earnings Yes |
| Named outcome field | Two-way, three-way, method, winner, first scorer, correct-score option | Missing draw, other outcome, complement, or normalization | Soccer three-way; NHL first scorer; golf/racing |
| Exact-score map | Two explicitly typed discrete score coordinates | Unlisted cells are zero; all cells form a coherent synchronous distribution | Hull–Everton 36 cells + supplied other |
| Period/series path | Set/map/inning/round question or series result | Unplayed steps, joint-path probability, automatic settlement of adjacent questions | Zverev sets; White Sox series; MMA winner/method/round |
| Independent placement field | Top-N, podium, make-cut, finishing position predicates | One winner or total chance 100% | Singapore podium; Open de España top 10 |
| Original-question fallback | Untyped, composite, interval/date, novelty or conflicting contracts | Units, orientation, participant identity, independence, settlement | Real esports Map 1 handicap; all original questions searchable |

A quoted interval can use the named outcome field in numeric order with its full inclusive/exclusive boundaries. Do not draw contiguous probability-density bars unless the upstream contract proves a synchronous, disjoint, exhaustive partition. An explicit provider combination stays one binary/named question; do not multiply its components. Novel ranked combinations of different questions remain v2 (#10353–#10357).

## Required data contract

Each renderable question needs:

- Stable semantic question ID and original venue question/outcome IDs; event/subject identity; original question and selected outcome text.
- Unit and comparator (`>`, `>=`, `<`, `<=`, range endpoints); period; scope including regulation/overtime/tiebreak treatment; settlement rule. Unknown is a real state.
- Probability evidence: value, observed-at, source, eligibility/currentness verdict, reason, spread/activity if supplied, and whether the number is a blend. Do not calculate currentness from a timestamp alone in the UI.
- Baseline: value, basis (kickoff pin/opening fallback), observed-at if known. Preserve separate opening and pregame fields.
- Actual: value, unit, as-of, provider, lifecycle. Projection: paired team values, unit, source/as-of and validity boundary.
- Result: won/lost/void/pending/conflict and authoritative settlement provenance, independently of game lifecycle.

The production default is one blended number per semantic question. Source-specific atlas examples are explicitly historical studies; they do not authorize a production source-comparison page or a second pricing engine.

Grouping requires matching subject, unit, comparator semantics, scope, period, settlement rules, and compatible quote basis. A Polymarket selected Under row may carry `over_probability`; plotting the over ladder and reading the selected Under detail are different operations. The atlas checks and demonstrates that boundary.

## State behavior

| State | Headline and history | Prop card |
| --- | --- | --- |
| Pregame | Win chances; start time; valid projected final | Pregame milestones and main script; no actual invented |
| In progress | Eligible chance + score + sport state; valid projected final | Baseline and selected current point; actual on units axis if available |
| Final | Winner/result, actual final, opening context; completed retained journey | Baseline-versus-actual story; independently graded contracts |
| Stale/currentness unknown | No recent price; last honest history ends at its timestamp; actual remains independently labeled | Keep the named card; omit current dot/connector, last quote in details |
| Loading | Preserve layout and any separately available actual; no animated fake line | Loading label; no arbitrary placeholder percentages |
| Refresh error | Visible update failure, retry through normal refresh; archived history labeled | Keep question and access to last capture; do not erase settled results |
| Suspended/postponed | Literal state, no running clock or elapsed-time invention | Named questions remain; no fake projection |
| Cancelled/void | Cancelled at event level only if authoritative; no winner inferred | Void per question only with authoritative void evidence; otherwise pending |
| Actual only | Actual score/stat visible, no fake expectation | State baseline unavailable; do not call it an upset/surprise |
| Conflicting grade | Source conflict visible; no confident final winner on conflicting contract | Result unconfirmed, original evidence accessible |

The toolbar's price-state controls simulate connection presentation on **unchanged real source rows**. They are a design test harness, not product controls and not a claim that the source was stale/loading at capture. Levante–Bilbao supplies an authoritative fair-value void example. Cancelled/postponed behavior remains specified without a fabricated specimen. Fair-value dollars are settlement amounts, never probabilities; an ungradeable result is not a losing result.

## Ranking and visual diversity

V1 ranks **groups**, not individual duplicate venue legs. Start with eligibility and semantic completeness, then fan relevance to this event and its state, meaningful deviation from a comparable baseline, and recent supported movement. A huge delta caused by stale data, outcome inversion or settlement is ineligible. Sparse activity alone is not a reliable price. A high-volume obvious threshold should not displace a much more useful game story merely because it traded more.

Cap repetition by visual/semantic family in the curated overview: a player milestone, a game-margin/total view, a projection/actual view, then a period/series or notable named event where warranted. Do not force a variety quota to promote misleading data. The atlas card order is curated design evidence, not a deployed ranking algorithm.

A large-screen companion stream can be a later alternate layout: grouped cards, visible as-of and movement, paused on hover/focus/touch, reduced-motion support, stable ordering while reading. It is not a requirement for the primary phone experience.

## Native translation and screen rules

Use native text and layout, Swift Charts PointMark/RuleMark/RectangleMark and SF Symbols. Never flatten the graph into a bitmap for production. The native sources here render the same data and symbol grammar offscreen at 393, 834 and 1280pt, with a separate enlarged-text study. Updated native NFL profiles use hollow pregame dots; the old v4 hit/filled encoding is superseded.

Phone: one card per row, probability hero first, concise direct labels, details behind a sheet. iPad: two columns with shared hero above. Mac: three or four columns where readable, expanded hero chart, persistent inspector optional. Reading order follows DOM/accessibility order. Enlarged text returns to one column, grows chart/card height, wraps labels, and retains full exact predicates in accessible details.

Native adoption gates still owed by implementation owners: real Dynamic Type categories; VoiceOver chart descriptors and adjustable selection; Switch Control; 44pt interactive hit areas; device gestures; contrast; actual iPhone/iPad/macOS integration. Offscreen rendering is feasibility evidence, not those gates.

## Additional source-quality dispatch

`ungradeable_result` is not settlement authority for Won/Lost, even if a boolean is present. A scalar/fair-value venue settlement is a separate terminal state, rendered with a neutral minus and Closed · no winner. A check means won, a cross means lost; hollow probability circles are never reused as loss/void symbols. Both the original rules and amount per contract are accessible in details.

The5 new field specimens deliberately demonstrate refusal states. Mutually exclusive winner quotes that are materially inconsistent or incomplete and have no supplied currentness verdict do not acquire a normalized headline. Independent qualification contracts never share a forced100% denominator. Unknown/held prices preserve contenders without ranking them by unusable values. These are specimen-specific holds; production eligibility remains an upstream verdict, not a hard-coded sum tolerance.


### Same player, separate clocks

The source-backed Hunter Brown reference overlays five hollow pregame strikeout milestones, one solid in-game complementary probability, and a thick final-actual rule. A final actual never supplies the missing in-game actual. Both marks and exact-value readouts repeat the temporal symbols. Small movements may overlap on an honest 0–100% axis; the exact labeled readouts preserve the difference without exaggerating it. Under/No details invert a normalized over/yes baseline consistently with the selected current quote. See LIVE-PLAYER-EVIDENCE.md.


### Compact player presentation

Keep player identity and labeled final actual in one header. Plot probabilities against actual sport units; retain a 0–100% probability scale even when the in-game move is small. Put hollow Pregame and solid In game plus observation time beside the selected milestone's exact chances. Keep unavailable in-game actual and the opening-baseline warning on the card. Move the original contract leg, complementary interpretation, exact source identifiers and clock limitations into an accessible detail sheet. The native reference uses SwiftUI state, minimum 44pt milestone buttons and a sheet; do not replace it with a screenshot. The compact view changes information placement, never eligibility, underlying data or ordering.

## Compact final-total strip and margin selector

Final totals bind one provider contract family and one unit. Plot each supplied threshold at its true position with its provider grade; never use settlement-era 0/1 as forecast probability. Show actual as a rule only when the correct-unit score exists. A retained pregame total projection uses an outlined square and its own timestamp. Delta is actual minus that projection, rounded only for display. Missing actual/projection stays absent; tennis sets cannot supply games actual. A range selector plus44px step controls selects every exact original row. Pending uses question-mark plus word, never the hollow pregame dot.

The demonstrated margin selector is specifically the Suns leg of six original Spurs negative-handicap contracts. It maps Phoenix finish margin greater than−N.5 to “Phoenix wins or loses byN or less.” Do not generalize this parser across sports/periods without typed predicates and integer-score semantics. Six quote positions remain independent; do not smooth their small non-monotonic differences. Quote readout preserves up to two percentage decimals so99.95% does not become100%. No-recent-price/loading/error suppress quote shapes and headline chance while leaving actual and questions visible. Original names, side, quote and clock remain in details. Native counterparts use the same retained input rows and native controls.


## Live-total distance card

Use only a known total-points family with integer scoring and an explicitly typed Over predicate. For a half-point thresholdN.5, the first qualifying integer isN+1; do not apply this conversion to an untyped contract, another scoring unit or an inclusive boundary. Preserve the original selected-side quote and identifier in details. An original Under quote may supply the complementary Over chance only when that exact binary interpretation is supplied/validated. The captured219.5 Under95.05% yields220+ at4.95%.

Lead with the selected chance. Plot actual as a thick rule, the separately captured projected final as an outlined square and the selected milestone as a dashed target on a single sport-unit axis. The distance expresses points, never chance, probability density or scoring pace. More needed is max(0, milestone minus actual); a reached milestone alone never supplies settlement authority. The four220/222/223/226 milestones here preserve four exact rows, including their different quote times; no curve smoothing or inferred intervals.

Pregame chance is unavailable in this specimen. Do not synthesize a baseline from an unrelated opening or another threshold. Each quote, actual and projection keeps its own timestamp. Show seconds in the detail comparison when captures occur within one minute; actual at quote time stays unavailable. This source has190 actual at04:56:57.056560 UTC,199.1 projected at04:56:45.278815 UTC and selected220+ quote at04:56:42.252833 UTC. They are not simultaneous. A price freshness failure suppresses the headline chance while preserving independently qualified and dated actual and projection. The archive review harness does not confer current production eligibility.

SwiftUI uses native milestone controls and a details sheet. Its axis text/ticks share the Chart plot width and domain so numeric labels align exactly with actual/projection/target marks. Do not substitute a static image or collapse the separate observation clocks during adoption.


## Catalog completeness, persistent selections and evidence access

Native `CatalogBrowser`/`CatalogContent` retain all source rows with category filters, search and12-group pagination. A group initially exposes six outcomes, with an explicit Show all action. Missing grades/prices remain visible. The grouping identity includes source, source-market ID, exact market title, category and period. It never merges venues or declares semantic equivalence from matching text. Unknown predicates retain their full original question.

Web Stories and All props remain mounted while hidden. Selection, expanded groups, query, category and pagination survive switching; opening/closing details never resets the reader's place. Production adoption must preserve this behavior when replacing fixture state with live data. This prototype does not implement live ranking/reordering.

Every native score cell is an actual44pt button with selected state, accessibility label and a source-detail sheet. Other story graphics expose exact original evidence through `AtlasCardWithEvidence`; the source record and clocks remain available without crowding the overview. Selection borders survive focus resets. Native views and renderer entry points are separate; include only embeddable views/shared formatter in product targets.

## Numeric precision and independent state eligibility

Use `probabilityLabel.ts` / `ProbabilityLabel.swift`: missing, nonfinite or out-of-range values are Unavailable; exact0/1 alone produce0%/100%; nonzero values below0.01% and non-certain values above99.99% retain inequality labels. A compact map may abbreviate inside a cell, but its selected readout/details preserve the exact supported precision. Results still require settlement authority.

Price state, actual evidence, projection validity and settlement are independent. Missing/failed/loading price suppresses current chance only, retaining independently qualified actual/projection. Suspended, postponed, cancelled, canceled and voided event states suppress the live winner chance/projection; independently graded props remain intact. Unknown lifecycle refuses unsupported winner/projection promotion. `eventLifecycle.ts` tests these behaviors using synthetic state inputs; no new actual halted-game specimen is claimed.


## Connected native composition and history interaction

EventPageReference routes all20 retained contexts by stable event ID. Story sets are explicit fixture mappings, never ranking weights. All props stays mounted while hidden, with no hit testing or accessibility exposure; switching panels retains state. Changing event resets the old event's component tree. Adaptive layout uses one column for accessibility categories, two at740pt and three at1120pt; headline/chart split at740pt. Existing enlarged card typography is selected automatically, but this does not prove continuous OS text scaling.

Native history selection exposes a real observation and its exact captured timestamp. A chart selection between observations may choose the nearer endpoint only within a continuous segment. Cross-segment gaps, invalid values and out-of-domain moments remain unavailable. Buttons/slider enumerate original observations, never generated intermediate percentages. Inspecting history does not move or fabricate the separately captured score/projection.

NFL profile arrows are real44pt controls; their selected milestone changes the exact baseline readout and original-question sheet. Every42 source-row link is checked. Product targets may embed ExpectationProfiles, EventPageReference, AtlasCards, CatalogReference and ProbabilityLabel; renderer entry points are excluded.
