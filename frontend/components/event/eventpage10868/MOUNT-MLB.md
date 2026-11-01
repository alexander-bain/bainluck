# #10868 MLB game screen, core checkpoint: proposed web mount (PROPOSED, NOT applied)

Pillars: FORMATTING / TRUTH / DISCOVER.

Ship: a baseball fan's web event page shows both teams' win chances, the score the page displays and
the projected final the page already admits together, with the two-team win history and every
original prop's exact Details.

Nothing below is applied. `app/events/[id]/page.tsx` is untouched; no source in this checkpoint
reads or edits it. The page owner applies this under its own grant (OB-10) after the web gates
(`npm run build` → `npm run typecheck` → `npx jest --testPathPatterns='mlbGame|settledVocabulary'`)
and real browser views. Line numbers are approximate (page.tsx 4,347 lines at 91d79dcb). This mirrors
`MOUNT.md` (hockey) and `MOUNT-SOCCER.md`.

This is a CORE checkpoint, not the full MLB page. What it does not carry is listed under "Held, not
dropped" below; none of it is claimed.

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
a new event or phase. `resetKey={event}` only retries a failed section; it does not remount it.

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
5. **Checks under grant.** `npm run build`, `npm run typecheck`, the focused jest files, then real
   browser views on the exact committed export at 375 px, 393 px and 1280 px with 100% and 200% text:
   no clipped value, no tiny or grey substitute figure, no word split, no horizontal page scroll; the
   four live columns stay aligned on a normal phone (full, short, then content-sized names-above
   grid) and fall back to one labelled block per team only when a measured grid does not fit or at
   an enlarged text size.

## What a reader sees on real inputs today (event 15321836, final 3–7)

- Headline, away first: White Sox 41% pregame, 7 final runs, Won; Astros 59%, 3, Lost; "Pre-match"
  and "Final score" under the matrix; "Projected final: Projected final unavailable" said once for
  both teams. The settled 0 / 1 hero is never printed as a chance.
- History: the Bain Luck blend, Astros traced, White Sox drawn as the documented other side of the
  same line (with H2's visible note), gaps blank, no settlement row, no inning guides.
- All props: every original in the page's catalogue with its readings, grades in the one settled
  vocabulary, and exact Details (Market ID, Outcome ID).

## Future insertion, D4 (documented only; NOT built, no empty panel)

When the approved story cards land (their own admission), they sit BESIDE the history at regular
width when both panels keep native's minimum readable widths (`anchorMinWidth` 460 pt /
`storiesMinWidth` 360 pt, BaseballEventPagePresentation10868.swift, as 28.75rem / 22.5rem bases in a
wrapping row, so the bases grow with the reader's text), and stack history-then-stories on phones and
at enlarged text. No miniature chart and no squeezed card. The insertion point is the
`data-mlb-history-row` wrapper in `MlbGamePage.tsx`; it belongs to the new page presentation, not to
a shared mount change. Whether the page's content column at 1280 px holds both bases at 100% is
measured in the browser lab, not assumed.

## Held, not dropped (the next increments toward the same full route)

- `mlbGamePlayers.ts` and `MlbGameStories.tsx`: the live home-run and strikeout player cards over
  During `10236.v1`, with exact-once player and milestone identity.
- OB-1 (the hockey card's signature-only boundary), OB-11 (the During baseline owner extraction),
  OB-13 (frozen milestone Details).
- The five story families: run totals, home runs, strikeouts, extra innings, series.
- G1 (no typed pregame player channel), G2 (no live count), G3 (no role-qualified identity), M1 (no
  genuine live HR/K specimen).
- The pregame and final forecast comparisons; inning guides (OB-3); full-size readers; the
  league eyebrow (web's event type declares no `metadata.league`); native fidelity, interaction and
  accessibility parity; production bindings and mount; carried TestFlight acceptance.
