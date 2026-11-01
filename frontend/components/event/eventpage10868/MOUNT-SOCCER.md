# #10868 soccer match screen: proposed web mount (PROPOSED, NOT applied)

Pillars: FORMATTING / TRUTH / DISCOVER.

Ship: a soccer fan's web event page opens on the three-outcome chances (home / draw / away), the
match's history and the stories the match has content for, with All props and exact Details, and
prints the same answers as the iPhone screen.

Nothing below is applied. `app/events/[id]/page.tsx` is untouched (it is contended: other worktrees
have it dirty). The page owner applies this under its own grant after the web gates
(`npm run build` → `npm run typecheck` → `npx jest --testPathPatterns=soccerMatch`) and a real
browser render. Line numbers are approximate (read 2026-10-31, page.tsx 4,347 lines). This mirrors
`MOUNT.md` (hockey).

## Design disposition (to confirm)

The hockey disposition (2026-10-30) was REPLACE, never stack. The same is proposed for soccer: for
a soccer match the screen shows in place of

- the hero's probability block: the score/state rows inside
  `<SectionErrorBoundary label="The score and probability">` (~page.tsx:2844);
- the win-probability chart card: `<SectionErrorBoundary label="The win probability chart">`
  (~page.tsx:3561).

Design confirms this for soccer before the mount is applied.

## 1. Imports (top of page.tsx)

```tsx
import { buildSoccerMatch, soccerMatchApplies } from "@/lib/eventPage10868/soccerMatch";
const SoccerMatchPage = dynamic(() => import("@/components/event/eventpage10868/SoccerMatchPage"), { ssr: false });
```

## 2. View model: recomputed from passed values, no memo

`buildSoccerMatch` is pure (no fetch, SWR, subscription, timer, ranking or cache). Call it on each
render AFTER the early returns and after `connectionPresentation`, as the hockey proposal does. It
is not a hook.

```tsx
const soccerMatch = soccerMatchApplies(event.sport)
  ? buildSoccerMatch({
      event,                         // SWR ["event", id]
      history: historyData,          // SWR ["history", id, full]; undefined ⇒ only the chart says "History unavailable"
      gameMarkets,                   // the page's own memo (~:1403)
      // `admitted` is OMITTED: no production owner admits the soccer story markets (see step 3).
      host: {
        nowMs: Date.now(),
        // The hero's own pair (~:1946). Only its HOME value is read: on a draw sport the hero's away
        // is a complement or a two-way number, never the away WIN chance.
        hero: resolvedProbability
          ? {
              homeProb: resolvedProbability.homeProb,
              awayProb: resolvedProbability.awayProb,
              homePct: resolvedProbability.homePct,
              awayPct: resolvedProbability.awayPct,
              probSourceLabel: resolvedProbability.probSourceLabel,
            }
          : null,
        probabilityObservedAt: acceptedPriceClock, // ~:1984; null ⇒ "Last recorded win chance"
        deliveryInterrupted: false,               // UNPAID, see step 5
      },
    })
  : null;
```

## 3. JSX: in place of the soccer hero probability block and the win-probability card

```tsx
{soccerMatch ? (
  <SectionErrorBoundary label="The soccer match" resetKey={event}>
    <SoccerMatchPage match={soccerMatch} />
  </SectionErrorBoundary>
) : (
  <>{/* the existing hero probability block and win-probability card, unchanged */}</>
)}
```

## What a reader sees on real inputs today

- Headline: the hero's home win chance (before kickoff and during play) or the stored pre-match
  chance (after the final), with Draw and the away win in their own words unless the opening object
  serves its own away. Never a derived draw, never 1 − home, never the settled 1 / 0.5 / 0.
- History: the home win line only; Draw and the away win keyed by their own absence words.
- Stories: the stream's own words, "No stories in this order. Every original prop is still in All
  props.", because no owner admits the story markets.
- All props: every original in the page's catalogue with its soccer readings and exact Details.

## Owner wiring steps (all UNPAID)

1. **Release switch.** No soccer-match flag exists on web. The page owner names one; turning it off
   is the backout.
2. **Hero cut.** Decide what of the hero stays for soccer (broadcast, date meta row, pin button).
   The screen has its own state, kickoff and score lines and no pin button.
3. **Story-market producer (the stories' owner).** Production has no owner admission for the soccer
   story markets (goal totals, both teams to score, first team to score, the two halves) and no
   exact-score descriptor. Until a producer serves them by exact venue market id, `admitted` stays
   omitted and every story shows the owner-unavailable state. Never match story markets by title
   or position. Native's owner-own-clock proof for goal rows (`ownClockGoals`) has no producer either.
4. **Chart replacement and duplicates.** Remove the win-probability card for soccer. The Player
   props, What's moving, All markets and score-differential sections may repeat facts the screen
   now carries; keeping each is the page owner's call. Nothing here hides them.
5. **Interrupted delivery, the real predicate.** Native reads `vm.liveUpdateStatus == .interrupted`.
   The web twin is somewhere in the page's live-connection state (`streamStatus` /
   `connectionPresentation`, `lib/event/liveConnectionStatus.ts`). Until the owner names it,
   `deliveryInterrupted: false`, and only the stale window on the quote's own clock demotes the
   home chance to "Last recorded win chance".
6. **Held choices.** The stream's shown story and each card's choice are held inside
   `SoccerMatchStories` for the life of the mounted section, within the stream's reading scope
   (`stories.scope`, one per event and phase). Each choice resolves by its exact id, exactly once:
   a withdrawn or duplicated id says "Selected … unavailable." and is kept, so the same identity
   returns; nothing is substituted. Never give the section a `key` that changes per refresh.
7. **Census enrolment (approved by the user, applied append-only).** `SoccerMatchStories.tsx` and
   `SoccerMatchPage.tsx` reach `lib/propGrade.ts` and are enrolled at the end of
   `__tests__/lib/settledVocabulary.test.tsx` `SURFACES` (soccer imports, one CONSTRUCTED forced
   pair, two entries; no existing line changed). The forced pair's non-vacuity check is in
   `__tests__/lib/soccerMatch10868.test.ts`.
8. **Checks under grant.** `npm run build`, `npm run typecheck`, the soccer jest files, then real
   browser views at 375 px and 393 px with normal and 200% text: no clipped value, no tiny type, no
   horizontal page scroll; the headline keeps its three aligned columns on a normal phone and falls
   back to one labelled block per outcome only at an accessibility text size or when a measured
   column cell does not fit; each story card's marks, readouts and heat map read at that width.

## Increment 2 (not built)

- Card-level Details: opening one original's exact Details from a story card. Every original's
  Details is reachable from All props today.
- The full-size story leaves (goal milestone chart, first-team plot, halves dot plot, exact-score
  shading and legend), the reader sheet and the history reader.
