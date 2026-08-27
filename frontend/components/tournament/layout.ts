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
 * The page shell — and the point of it is that there is no longer a shell.
 *
 * ═══ UX-P146: THE ARTIFICIAL CONTAINER IS GONE ═══
 *
 * Alex, on the UX-P145 desktop artifact: *"Doesn't the rest of the desktop site
 * just use as much width as the user gives it?"*
 *
 * It does, and it was the right question. UX-P145 answered "weirdly narrow" by
 * making the tournament page's OWN column wider — 560 → 1024 → 1280 — which
 * left the defect's shape intact and only moved its edges. The rest of the site
 * has no page-level column at all. `app/layout.tsx` wraps every route in
 *
 *     <div className="max-w-content mx-auto px-3 md:px-6 py-4">
 *
 * — `max-w-content` is `1600px` in `tailwind.config.ts` — and `/politics`,
 * `/weather`, `/economics`, `/entertainment`, `/search` and `/hub/[competition]`
 * add nothing of their own. They fill it. The tournament hub was nesting a
 * second, narrower container inside that one, so at a 1400px window it drew a
 * 1280px column inside a 1304px box and at a 1200px window a 1024px column
 * inside 1104px — grey down both sides at every size, which is exactly what
 * Alex was looking at.
 *
 * So the shell holds no width. The site's container is the container, one level
 * up, the same one every other page answers to. This is not "a wider number":
 * it is the page no longer having an opinion about how wide the window is.
 *
 * ═══ WHAT THIS DOES NOT CHANGE ═══
 *
 * **The phone.** `max-w-[560px]` never bound a phone — a 390px viewport is
 * narrower than 560, so the cap was inert there and removing it moves nothing.
 * Every ruling from UX-P131 on was verdicted at 390px and every one of them
 * still holds, unchanged and unre-opened. The cap only ever bound between
 * 560px and 1600px of viewport, which is the range where the page looked like
 * a phone in a window.
 *
 * **The padding.** The page keeps its own `px-4 lg:px-6` inside the site's
 * `px-3 md:px-6`, untouched, because changing it WOULD move the phone.
 *
 * `w-full` rather than the empty string so the value is still a class the page
 * renders and the capture rig can import — a constant that evaluates to `""`
 * reads, in a diff, exactly like a constant somebody forgot to finish.
 */
export const TOURNAMENT_SHELL = "w-full";

/**
 * The Tournament tab's two columns above `lg`, one column below it.
 *
 * `minmax(0,…)` on both tracks, not `1.35fr 1fr` alone: a grid track's default
 * `min-width:auto` refuses to shrink below its content, and the match list
 * holds long player names inside `truncate`. Without the explicit `0` minimum
 * one wide row pushes its track past its share and the right column falls off
 * the shell — the classic CSS-grid overflow, which does not appear until real
 * data carries a long enough name.
 *
 * UX-P146 note: with the page-level cap gone these tracks now divide up to
 * 1504px (1600 − the site's and the page's gutters) instead of 1280 − 48. The
 * ratio is unchanged and deliberately so — the left column holds the things
 * you read down and wants the larger share at any width.
 */
export const TOURNAMENT_COLUMNS =
  "lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] lg:items-start lg:gap-x-8";
