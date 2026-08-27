/**
 * The tournament hub's page-level layout classes (UX-P145).
 *
 * ═══ WHY THESE ARE NOT IN `page.tsx`, AND NOT IN `lib/` ═══
 *
 * They started in `page.tsx`, where they are used. Next.js rejects that: a
 * route file's exports are a contract (`default`, `metadata`, `dynamic`, …) and
 * `.next/types/app/tournaments/[slug]/page.ts` fails the typecheck gate on any
 * other named export. That gate is a fail-on-new ratchet, so it is a hard stop
 * rather than a style note.
 *
 * The obvious second home is `lib/`, and it is wrong for a reason that would
 * not have shown up until the page rendered unstyled: `tailwind.config.ts`
 * scans `./app/**` and `./components/**` and NOTHING ELSE. A Tailwind class
 * that only ever appears in `lib/` is a class Tailwind never generates. So
 * anything holding literal class text lives under `components/`.
 *
 * EXPORTED, rather than inlined at the one call site, because the capture rig
 * renders them (`__tests__/capture/usOpenDesktopCapture.test.tsx`). A rig that
 * hard-codes its own frame width is drawing a picture of the page; it has to
 * render the shipped string, or a desktop artifact proves nothing about the
 * desktop.
 */

/**
 * The page shell — one phone column, then a real desktop page.
 *
 * Alex, on the live page in a desktop browser: "weirdly narrow, like we only
 * made a mobile version." The whole hub lived inside `max-w-[560px]`, so a
 * 1400px window rendered a 560px phone in the middle of 840px of grey.
 *
 * 560 → 1024 → 1280 rather than a bare `max-w-screen-xl`: **560 is the measured
 * phone column every ruling from UX-P131 on was verdicted against and it must
 * not move**, `lg` (1024px) is where the two-column split turns on, and 1280 is
 * where the shell stops so a 21" monitor does not stretch the match list out to
 * the bezels.
 */
export const TOURNAMENT_SHELL =
  "mx-auto w-full max-w-[560px] lg:max-w-[1024px] xl:max-w-[1280px]";

/**
 * The Tournament tab's two columns above `lg`, one column below it.
 *
 * `minmax(0,…)` on both tracks, not `1.35fr 1fr` alone: a grid track's default
 * `min-width:auto` refuses to shrink below its content, and the match list
 * holds long player names inside `truncate`. Without the explicit `0` minimum
 * one wide row pushes its track past its share and the right column falls off
 * the shell — the classic CSS-grid overflow, which does not appear until real
 * data carries a long enough name.
 */
export const TOURNAMENT_COLUMNS =
  "lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-start lg:gap-x-8";
