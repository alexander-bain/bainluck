# #10868 MLB game screen, core checkpoint: proposed web mount (PROPOSED, NOT applied)

Pillars: FORMATTING / TRUTH / DISCOVER.

Ship: a baseball fan's web event page shows both teams' win chances, the score the page displays and
the projected final the page already admits together, with the two-team win history and every
original prop's exact Details.

Run-total ship (every phase): before first pitch and during play, the event page shows the run
milestones with each pregame chance, admitted in-game chance and the runs so far kept apart; after
the game, it shows the actual run total against the offered lines, both alongside the
win-probability history. Run totals in EVERY phase are PREPARED in this checkpoint (source, tests and
this note; the final card by the binding increment, the before/live milestones by S2c); see "Run
totals" below. A source package is not app integration, and no route or phase advances from it
alone.

Reader ship (I1 + I2): the baseball page's run-total card offers "Open full card"; a fan explores
the same card full size, closes it, and returns to the same choice and page position. The
full-size reader (`MlbRunTotalsReader.tsx`, I1) and its binding in this page (I2) are PREPARED in
this checkpoint (source, tests and this note); see "The run-total full-size reader" below. Not
mounted, and not visual, accessibility or TestFlight acceptance.

Nothing below is applied. `app/events/[id]/page.tsx` is untouched and stays PROPOSED only; no source
in this checkpoint reads or edits it. The page owner applies this under its own grant (OB-10) after
the web gates (`npm run build` → `npm run typecheck` →
`npx jest --testPathPatterns='mlbGame|mlbRunTotals|soccerMatchReader|settledVocabulary'`) and real
browser views. Line
numbers are approximate (page.tsx 4,347 lines at 91d79dcb). This mirrors `MOUNT.md` (hockey) and
`MOUNT-SOCCER.md`.

This is a CORE checkpoint plus the run-total card in every phase and its full-size reader, not the
full MLB page. What it does not carry is listed under "Held, not dropped" below; none of it is
claimed.

## Design disposition

REPLACE, never stack (the hockey disposition, 2026-10-30). For an MLB game the section shows in
place of:

- the hero's probability block: the score/state rows inside
  `<SectionErrorBoundary label="The score and probability">` (~:2844), including its "Projected
  final" line (~:3194), which the section now prints as a team-paired matrix column;
- the win-probability chart card: `<SectionErrorBoundary label="The win probability chart">` (~:3561).

## 1. Imports (top of page.tsx)

```tsx
import { buildMlbGame, mlbGameApplies } from "@/lib/eventPage10868/mlbGame";
const MlbGamePage = dynamic(() => import("@/components/event/eventpage10868/MlbGamePage"), { ssr: false });
```

## 2. View model: recomputed from values the page already holds, no memo

`buildMlbGame` is pure (no fetch, SWR key, subscription, timer, ranking or cache) and is not a
hook. Call it on each render AFTER the early returns and after every value below exists. Every
host key is REQUIRED; the builder defaults none of them.

```tsx
const mlbGame = event && mlbGameApplies(event.sport)
  ? buildMlbGame({
      event,                       // SWR ["event", id]
      history: historyData,        // ~:1038; another event's body or none ⇒ only the chart says "History unavailable"
      gameMarkets,                 // the page's own memo (~:1403, after withoutEventOwnMoneyline)
      host: {
        nowMs: Date.now(),
        // The hero's own resolved pair for THIS event (~:1946), before its printableAway step.
        hero: resolvedProbability
          ? {
              homeProb: resolvedProbability.homeProb,
              awayProb: resolvedProbability.awayProb,
              homePct: resolvedProbability.homePct,
              awayPct: resolvedProbability.awayPct,
              probSourceLabel: resolvedProbability.probSourceLabel,
            }
          : null,
        probabilityObservedAt: acceptedPriceClock,     // ~:1984; null ⇒ "Last recorded chance"
        deliveryInterrupted: liveDeliveryInterrupted,  // OB-8 UNPAID: no such value exists on page.tsx today
        liveClaimUnbacked,                             // ~:723, pageLiveClaimIsUnbacked(...)
        // The DISPLAYED pair (~:1496-1502, ~:1940) — the same pair heroProjectedFinal's
        // reachability gate reads (~:1839-1844) — and null under the stoppage filler.
        score: heroScoreIsStoppageFiller
          ? null
          : { home: bestHomeScore, away: bestAwayScore, observedAt: renderedScoreStamp },
        projectedFinal: heroProjectedFinal,            // ~:1872, unchanged (D1 = B)
      },
    })
  : null;
```

The run-total card adds NO host key in any phase: it reads the `gameMarkets` body, the `score` pair
(with its own `observedAt`) and `nowMs` already passed above, and the builder's own
`noReportedResult` (from `liveClaimUnbacked` and the no-reported-result state).

## 3. JSX: in place of the MLB hero probability block and the win-probability card

```tsx
{mlbGame ? (
  <SectionErrorBoundary label="The baseball game" resetKey={event}>
    <MlbGamePage model={mlbGame} />
  </SectionErrorBoundary>
) : (
  <>{/* the existing hero probability block and win-probability card, unchanged */}</>
)}
```

Never give the section a `key` that changes per refresh. Its history and All props are keyed by the
model's own `scope` (`mlb:<event>:<phase>`), so an open list, an open Details or a chart disclosure
survives a refresh in the same scope (each Details is held by the original's exact key) and resets on
a new event or phase. The run-total card's chosen line, and whether its full-size reader is open, are
held inside the section, above the card, for the same `scope` (see "Run totals" and "The run-total
full-size reader"). The reader is the section's own local `<dialog>`: no route, history entry,
query parameter or global modal layer is added for it. `resetKey={event}` only retries a failed
section; it does not remount it.

## Owner-binding debt (all UNPAID)

1. **OB-8, interrupted delivery.** `deliveryInterrupted` is REQUIRED and has no default in source.
   Native reads `vm.liveUpdateStatus == .interrupted`. The web twin is somewhere in the page's
   live-connection state (`streamStatus` / `connectionPresentation`,
   `lib/event/liveConnectionStatus.ts`), and page.tsx names no single answer. Until the page owner
   names one, `liveDeliveryInterrupted` above does not exist and the mount cannot be applied as
   written. Writing a literal `false` there would be this debt left unpaid, and must be recorded as
   that, not as an answer. Today only the quote's own clock (stale over 30 minutes or undated),
   `liveClaimUnbacked` and the no-reported-result state demote "Current chance".
2. **OB-10, the mount itself.** A release switch (no MLB-screen flag exists on web; turning it off is
   the backout); the hero cut (what of the hero stays for MLB: broadcast, date row, pin); removing
   the win-probability card for MLB; and the duplicates. The During player chances matrix, Player
   props, All markets, The series picture and Related futures sections may repeat facts or originals
   the section carries; keeping each is the page owner's call. Nothing here hides them.
3. **D1 = B, kept as the page's own value.** `projectedFinal` is `heroProjectedFinal` exactly: the
   section never recalculates, rounds, re-gates or relaxes it, and prints it beside the same
   displayed pair its reachability gate was checked against. Native parity (package 56 declines every
   baseball projection), the live pregame-forecast comparison (`livePregameComparison` requires
   `admittedLiveProjection`, which refuses baseball) and the final forecast comparison
   (`finalForecastComparison` refuses baseball) remain unpaid owner obligations.
4. **Census enrolment (approved shape, applied append-only, separate commit).** `MlbGamePage.tsx`
   reaches `lib/propGrade.ts` through `HockeyJourneyAllProps` and is enrolled at the end of
   `__tests__/lib/settledVocabulary.test.tsx` `SURFACES` with one CONSTRUCTED forced pair. No
   existing line changed. Its non-vacuity check is in `__tests__/lib/mlbGame10868.test.ts`.
   `MlbRunTotalsCard.tsx` (the leaf) is enrolled there too, by the S1 commit, and
   `MlbRunTotalsReader.tsx` by the I1 census commit (its verdict slot delegated to the enrolled
   card). Neither S2c nor I2 edits the census. The page's census entry builds over the reduced
   fixture, which has no matrix, so it draws no card, entry or reader in any phase and its
   differential is unchanged.
5. **Checks under grant.** `npm run build`, `npm run typecheck`, the focused jest files, then real
   browser views on the exact committed export at 375 px, 393 px and 1280 px with 100% and 200% text:
   no clipped value, no tiny or grey substitute figure, no word split, no horizontal page scroll; the
   four live columns stay aligned on a normal phone (full, short, then content-sized names-above
   grid) and fall back to one labelled block per team only when a measured grid does not fit or at
   an enlarged text size. For the run-total card in each phase (final card; before and live
   milestones): history then card stacked at 375 / 393 px, normal and enlarged text, with no
   miniature history; side by side at wide width only when both bases fit; choosing a line or a
   milestone works, the final card never rescales its bar; the headline and history are unchanged.
   For the full-size reader, at the same widths and text sizes: "Open full card" sits under the
   card inside its item; the reader opens as a true modal (background inert, page scroll held, Close
   always reachable, the compact context and card readable and wrapping, the final plot taller
   without shrunken labels); Close and Escape (the dialog's cancel) return the page to its position
   with focus on the entry (or on the named history row when the entry is gone); the choice made in
   either view is the other's. No genuine before/live specimen exists for this check yet (see
   "Held, not dropped").

## What a reader sees on real inputs today (event 15321836, final 3–7)

- Headline, away first: White Sox 41% pregame, 7 final runs, Won; Astros 59%, 3, Lost; "Pre-match"
  and "Final score" under the matrix; "Pregame projected final: Unavailable" said once for both
  teams. The settled 0 / 1 hero is never printed as a chance.
- History: the Bain Luck blend, Astros traced, White Sox drawn as the documented other side of the
  same line (with H2's visible note), gaps blank, no settlement row, no inning guides.
- Run totals (when the body carries its matrix, which the retained body does): "Where the total
  finished", final total 10 (Astros 3, White Sox 7), 13 full-game lines 2.5 to 14.5, opening on 9.5
  ("Final 10 runs · above this line", source result HIT); 10.5 reads "below this line", MISS. Every
  pregame chance is "Unavailable". The matrix's five first-five-innings run lines are not drawn.
  The capture is FINAL only: what the before/live milestones show is proved on CONSTRUCTED quotes,
  pins, clocks and pairs over this matrix, never on a genuine before/live capture.
- All props: every original in the page's catalogue with its readings, grades in the one settled
  vocabulary, and exact Details (Market ID, Outcome ID).

## Run totals (every phase; prepared in this checkpoint, not mounted)

- **Model.** `MlbGameView.runTotals: MlbRunTotalsInput | null` (`lib/eventPage10868/mlbRunTotals.ts`:
  `MlbFinalTotals | MlbRunMilestones`, S1 and S2b, unchanged). After the final it is the final
  card's input (`kind: "final"`); before first pitch and during play it is the milestones of that
  phase (`kind: "milestones"`, its `phase` the page's). Null when the matrix offers no card.
- **Exact input.** The lines are admitted ONCE, `mlbRunLines(ownMarkets?.game_question_matrix)`.
  `ownMarkets` is `ownHockeyMarkets(gameMarkets, event)`, the same exact-`event_id` body All props
  reads. Then, by phase:
  - final: `mlbFinalTotals(lines, host.score, { home: headline.home.name, away: headline.away.name })`,
    unchanged. `host.score` is the displayed pair the "Final runs" column prints; the names are the
    built headline's.
  - before / live: `mlbRunMilestones(lines, phase, event, host.score, state.noReportedResult,
    host.nowMs)`. `event` gives only the listed start and the sport; `host.score` is the same
    displayed pair with its own `observedAt`; `state.noReportedResult` is `mlbGameState`'s own answer
    (the one that also titles the headline's chance and withholds the projected final).
- **Never read.** `event.home_score` / `away_score`, any other total, the price history, or a line or
  result taken as the actual. No clock, quote or count is made up, and no decoder, policy or
  formatter is added. D1 = B is unchanged.
- **Matrix (S1's rules, every phase).** Contract `10238.v1`; the envelope's `display_scope` absent,
  null or "game". Lines are typed `count_threshold` questions (quantity `runs`, subject `game`,
  period `full_game`, relation `ge`) with exactly one `over` option. A repeated option key or line
  value refuses both copies, and fewer than 3 lines gives null. Another event's body, no body, no
  matrix or a refused matrix gives NO card and no empty panel.
- **Final card.**
  - Pair: two whole, non-negative counts whose sum is a safe integer give the total and a stacked
    home/away bar. Anything else (missing, partial, negative, fractional, unrepresentable) gives total
    "Unavailable" and no bar. Every line is still offered, opening on the lowest. A missing side is
    never 0.
  - Default: the highest line below the total, else the lowest.
  - Pregame chance: the comparable baseline, else the admitted pregame reading, else
    "Unavailable".
  - Source result: the venue's won / lost in `propVerdictLabel` words, else "Result unavailable".
    It is never graded from the runs; the comparison ("above / below / on this line") is the pair
    against the number.
- **Before / live milestones (S2b's rules, drawn by S2a's `CountMilestoneCard`).** Each line is a
  milestone ("Over 9.5" is "10+ runs").
  - Before first pitch: the pregame chance is a quoted value only while its own clock is readable
    and recent. A pin never fills it. No in-game chance and no count before play, even when a pair
    is displayed.
  - During play: the pregame chance is the pin (the comparable baseline, else the admitted
    pregame reading) on its own clock. The in-game chance is a quoted value only while recent,
    observed at or after a readable start and not under `noReportedResult`, else "In-game chance
    unavailable". The runs so far are the displayed pair's total (the same RT1 guard as the final
    total), dated only by the pair's own clock; a partial pair is no count, never 0. A reached line
    says "Reached so far" (performance, never 100%); otherwise "k more for N+".
  - No source result shows before or during play, though the venue may already have graded the
    line.
  - Default: the shown pregame chance nearest even odds; none shown is no default, so nothing is
    chosen until the reader chooses.
- **Page.** The row's second item is `MlbRunTotalsSlot` (page-local, in `MlbGamePage.tsx`, no
  key). It draws `<MlbRunTotalsCard totals={runTotals} scope={model.scope} colors={lineColors}
  selection={{ held, onSelect }} />` only for an input that agrees with the page's phase, and draws
  nothing otherwise.
- **Phase agreement (S2c).** The final-only guard is replaced by a defence, not removed: after the
  final only a `kind: "final"` input draws; before first pitch and during play only a
  `kind: "milestones"` input whose own `phase` is the page's phase draws. A wrong-kind or
  wrong-phase input (constructed or stale) draws no card, so a final card never shows during play
  and one phase's milestones never show in another. The builder already agrees; the defence is for
  any other model.
- **The chosen line or milestone persists (B1, every phase; native `BaseballStoriesAdapter10868`
  holds `selectedOptionKey` outside the card).** The slot stays mounted whether or not a card is
  drawn. It holds the chosen option key for `model.scope`. Its only state is that scope and key: no
  totals model, line, milestone or probability is cached.
  - A same-scope refresh keeps the key.
  - A same-scope pass with no matrix at all draws NO card, placeholder or stale card. The key
    survives, and when this event's own matrix returns the card opens on it, readout included.
  - A held key the returned lines do not carry exactly once (withdrawn or duplicated) reads
    "Selected line unavailable" on the final card and "Selected milestone unavailable." on the
    milestones, never the default or a neighbour. It shows again when it is offered once more.
  - A new event or phase (a new scope) clears the key while rendering, even while no card is
    drawn, so the new scope opens on its own default.
  - Each deliberate tap calls `onSelect` once. There is no effect, timer, fetch or automatic
    selection.
- **The card's optional `selection` input** (`MlbRunTotalsCard.tsx`) is a host-held key plus that
  callback. Without it, the card keeps its own per-scope selection exactly as before, which is how
  the standalone and census uses render it.
- **The row (D4, built for this card in every phase).** `data-mlb-history-row` is a wrapping flex
  row with a 1.5rem gap.
  - The history is always its first item, in the same tree position, so the chart and its
    disclosure never remount when the card comes or goes.
  - Each item grows from a flex base taken from native's minimum readable widths: history 28.75rem
    (`anchorMinWidth` 460 pt), card 22.5rem (`storiesMinWidth` 360 pt). Either may shrink below
    its base (`min-w-0`).
  - They sit side by side only while the row holds 52.75rem. Below that, the card wraps under the
    history and each takes the full row.
  - The rem bases grow with the reader's text, so enlarged text stacks them.
  - With no card, the history alone fills the row as before.
  - Whether the page's content column at 1280 px holds both bases at 100% is measured in the
    browser lab, not assumed.
- **Evidence.** The jest tests use the REAL final matrix joined in-test onto the reduced body. Every
  before/live quote, pin, clock, status, displayed pair, raw row score and `noReportedResult` in
  them is CONSTRUCTED. They prove behaviour, not pixel fit or a genuine before/live specimen.
- **Not in this increment.** Details on the card (run-line and milestone Details), in the page or
  the reader, in any phase.

## The run-total full-size reader (I1 + I2; prepared in this checkpoint, not mounted)

- **Reader (I1, `MlbRunTotalsReader.tsx`).** The EXISTING `SoccerMatchReader` shell, unchanged
  (one local `<dialog>` with `showModal()` — a true modal or nothing; page scroll held; Close,
  Escape and cancel through the owner once; an asked close restores the page position and focuses
  `returnTo()` with `preventScroll`; an owner close restores no scroll and moves focus only if it
  was lost). Title native's "Run totals"; a single card, no Previous / Next or position; no
  Details. It draws the SAME `MlbRunTotalsCard` on the caller's SAME controlled selection with
  `layout="expanded"`: only the final plot is taller, in native's 108 → 132 proportion (the web
  plot block 7.5rem → 9.1667rem, the axis-label row unchanged, so the marks area 6rem → 7.6667rem);
  the milestones leaf is unchanged. With no input (the whole matrix gone) the open reader keeps
  only its title, Close and native baseball's `storyUnavailable` words: no context, card,
  probability or count.
- **Slot state (I2, `MlbRunTotalsSlot` in `MlbGamePage.tsx`).** `{ scope, key, open, unavailable }`
  plus the entry's ref; no model, line or probability is held. A new event or phase resets all
  four while rendering, so the reader closes in the same render as the key clears: no frame shows
  it for the old phase.
- **Entry.** With an agreeing card, "Open full card" (spoken "Open full card: Run totals") sits
  inside the run-total row item, under the card, disabled while the reader is open. After a failed
  attempt (`showModal` missing or throwing) a status line beside it says "Full-size view
  unavailable. You can still explore this on the page." until the next attempt or a new scope; the
  page card keeps working.
- **One reading, two views.** The page card and the reader get the SAME phase-agreed input
  (`runTotalsForPhase`) and the SAME selection object, so a choice in either is the other's and
  survives close / reopen and same-scope refreshes.
- **Input lost while open.** The page draws no row item, card, entry or placeholder; the reader,
  a fragment sibling after the item (its dialog out of the row's flow), stays mounted on its
  absence words; the key is kept and the exact returning input restores it.
- **Compact context, from the built headline only.** Away first, each team's short name else its
  name; both runs slots' printed text from this phase's runs column (live index 2, final index 1)
  only when the matrix is this phase's and both are values; never before first pitch, never a 0,
  a half pair or the event row; then `headline.state`.
- **Focus return (R-F3).** The entry while it is connected and enabled; else the history row
  (`data-mlb-history-row`, `tabIndex={-1}`, `role="group"`, named "Win probability and run
  totals"), which stays while the page does; null only once the page is gone. No Tab stop is added
  and the row's geometry is unchanged.
- **Evidence.** `__tests__/components/mlbRunTotalsReader10868.test.tsx` (I1, a test host) and
  `__tests__/components/mlbGamePageRunReader10868.test.tsx` (I2, the actual builder and page) on
  the REAL final matrix plus CONSTRUCTED before/live inputs, with jsdom's dialog stubbed: they
  prove state and wiring, not modality, fit or pixel parity.

## Held, not dropped (the next increments toward the same full route)

- `mlbGamePlayers.ts` and `MlbGameStories.tsx`: the live home-run and strikeout player cards over
  During `10236.v1`, with exact-once player and milestone identity.
- OB-1 (the hockey card's signature-only boundary), OB-11 (the During baseline owner extraction),
  OB-13 (frozen milestone Details).
- The player (home runs, strikeouts), extra-innings and series stories.
- Genuine before-first-pitch and live specimens for the run milestones (the retained capture is
  final only; every before/live reading in the tests is CONSTRUCTED).
- Producer `observed_at_basis` exposure for the matrix: its options' `published` clock carries no
  `observed_at_basis` (the retained capture has none), so web cannot tell an option's own clock from
  a capped or borrowed one. The milestones' recency and after-start rules read the clock as served
  until the producer exposes it.
- G1 (no typed pregame player channel), G2 (no live count), G3 (no role-qualified identity), M1 (no
  genuine live HR/K specimen).
- The pregame and final forecast comparisons; inning guides (OB-3); the MLB Full chart reader and
  every other full-size reader; multi-card browsing (Previous / Next) once other MLB stories exist
  on web; run-line and milestone Details on the run-total card (page and reader); the league
  eyebrow (web's event type declares no `metadata.league`); native fidelity, interaction and
  accessibility parity.
- The run-total reader's real browser behaviour: modality, focus containment, scroll locking, fit
  at 375 / 393 / 1280 px and 200% text, and the expanded plot against native (no pixel parity is
  claimed).
- The owner bindings OB-8 (interrupted delivery) and OB-10 (the release switch and the duplicates),
  the production mount (page.tsx stays PROPOSED), and every native, device, accessibility and
  TestFlight obligation.
