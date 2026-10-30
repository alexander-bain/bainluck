# #10868 `nhl-journey` — proposed web mount (PROPOSED, NOT applied)

Ship: a hockey fan's event page opens on the journey — paired matrix, two-team history,
points/assists stories, All props — printing the same answers as the iPhone screen.

Nothing below is applied. `app/events/[id]/page.tsx` is untouched; the lead applies this under its
own grant after the web gates (`npm run build` → `npm run typecheck` →
`npx jest --testPathPatterns=hockeyJourney10868`). Line numbers are approximate (read 2026-10-30).

## Design disposition (Event page design, 2026-10-30)

The adopted journey headline and history **REPLACE** the hockey headline and history. Stacking a
second headline and a second chart after the existing ones is not design acceptance. For a hockey
event the page shows the journey in place of:

- the hero's probability block — `EventHeroProbabilityPair` and the score/state rows inside
  `<SectionErrorBoundary label="The score and probability">` (~page.tsx:2844-3548);
- the win-probability chart card — `{!suppressWinProbabilityCard && (<SectionErrorBoundary
  label="The win probability chart">…)}` (~page.tsx:3556-3776).

The mount stays PROPOSED until the owner wiring below is done and the I-grant checks pass.

## 1. Imports (top of page.tsx)

```tsx
import { buildHockeyJourney, hockeyJourneyApplies } from "@/lib/eventPage10868/hockeyJourney";
const HockeyJourneyPage = dynamic(() => import("@/components/event/eventpage10868/HockeyJourneyPage"), { ssr: false });
```

## 2. View model — recomputed from passed values, no partial memo

Native removed its partial memo (`HockeyJourneyEventPageHostAdapter10868`: no owner revision
covers every input, so a partial memo would hold a changed score or chance on screen). The web
proposal follows: `buildHockeyJourney` is pure and is called on each render AFTER the early returns
(~page.tsx:2014-2085) and after `connectionPresentation` (~:2451), so it is not a hook and can read
the interrupted state once its owner names it. Any cache needs a complete owner revision first
(performance work, routed — not this mount).

```tsx
const hockeyJourney = hockeyJourneyApplies(event.sport)
  ? buildHockeyJourney({
      event,                         // SWR ["event", id] (:371-400)
      history: historyData,          // SWR ["history", id, full] (:992-1038); undefined while loading/failed ⇒ only the chart says "History unavailable"
      gameMarkets,                   // the page's own memo (:1403), event moneyline already removed
      host: {
        nowMs: Date.now(),
        // The hero's own pair, BEFORE page.tsx:2169's printableAway (the builder applies it).
        hero: resolvedProbability
          ? {
              homeProb: resolvedProbability.homeProb,
              awayProb: resolvedProbability.awayProb,
              homePct: resolvedProbability.homePct,
              awayPct: resolvedProbability.awayPct,
              probSourceLabel: resolvedProbability.probSourceLabel,
            }
          : null,
        probabilityObservedAt: acceptedPriceClock, // :1984 — null ⇒ "Last recorded chance"
        deliveryInterrupted: false,               // UNPAID — see owner step 5
      },
    })
  : null;
```

## 3. JSX — in place of the hockey hero probability block and the win-probability card

```tsx
{hockeyJourney ? (
  <SectionErrorBoundary label="The hockey journey" resetKey={event}>
    <HockeyJourneyPage journey={hockeyJourney} />
  </SectionErrorBoundary>
) : (
  <>{/* the existing hero probability block and win-probability card, unchanged */}</>
)}
```

## Owner wiring steps (all UNPAID)

1. **Release switch.** No hockey-journey flag exists on web. The page owner names one, and turning
   it off is the backout. Do not claim a flag exists until it does.
2. **Hero cut.** Decide what of the hero stays for hockey. The journey has no pin button,
   broadcast or date meta row, so the hero's top meta row (~:2846+) probably stays and only the
   probability/score/state block is replaced. Design and the page owner decide.
3. **Chart replacement.** Remove the win-probability card for hockey. The existing chart's
   fullscreen modal and range controls have no journey equivalent: the journey offers no Full
   chart or Inspect control until a real destination exists.
4. **Duplicates below.** The Player props, What's moving, All markets and score-differential
   sections (~:2559, :3912-4079) repeat facts the journey's stories and All props now carry.
   Keeping or removing each one is the page owner's call. Nothing here hides them.
5. **Interrupted delivery, the real predicate.** Native reads `vm.liveUpdateStatus ==
   .interrupted`. The web twin is somewhere in the page's live-connection state (`streamStatus` /
   `connectionPresentation`, ~:2451, `lib/event/liveConnectionStatus.ts`). This mount does not
   claim which field means "interrupted". Until the owner names it, `deliveryInterrupted: false`,
   and only the stale window on the quote's own clock demotes a frozen pair to "Last recorded
   chance".
6. **Held context.** The stories' player/milestone choice is held inside `HockeyJourneyStories`
   for the life of the mounted section. Keep the section mounted across refreshes: never give it a
   React `key` that changes per refresh (that remounts it and drops the choice).
   `SectionErrorBoundary`'s `resetKey` only retries a failed section and does not remount it.
7. **Checks under grant I.** `npm run build`, `npm run typecheck`, the 10868 jest files, then real
   browser views at 375 px and 393 px with normal text and with 200% text. Pass means: no clipped
   value, no tiny type, no horizontal page scroll, and the matrix arrangement steps
   grid → short names → labelled pairs only when the wider one does not fit.

## Owed / unverified

- No `/history` response (loading or failed): the builder composes the matrix, stories and All
  props as usual, and the chart slot alone says "History unavailable", with no control and no retry.
  The real load/error/retry contract stays the page's; nothing here invents one.
- Live overlays and held inspection of the chart (owner-admitted frames) are not built on web.
