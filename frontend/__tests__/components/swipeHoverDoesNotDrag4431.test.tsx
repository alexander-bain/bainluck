/**
 * #4431 — `4431-HOVER-IS-NOT-A-DRAG`
 *
 * A DISCOVER CARD NEVER FOLLOWS A CURSOR THAT IS NOT PRESSING IT.
 *
 * ── WHAT ALEX HIT ───────────────────────────────────────────────────────────
 *
 * Reading Discover on the web on 2026-09-09 the page got "stuck in a
 * swipe-left/right mode he could not leave". Reproduced on production at
 * 1440px, reading the translating node's transform:
 *
 *   hover across the card, never pressing (CONTROL)      translateX   0
 *   press, flick out of the card, release outside        translateX   0
 *   then hover LEFT  with no button held                 translateX -75  "Less like this"
 *   then hover RIGHT with no button held                 translateX +75  "More like this"
 *
 * The card follows the bare cursor forever, and a hover wandering past 80px
 * arms a real dismiss or like.
 *
 * ── WHY IT STICKS ───────────────────────────────────────────────────────────
 *
 * `onPointerDown` sets `swiping.current = true` and deliberately does NOT
 * capture the pointer — capture is deferred to the first move past
 * `DRAG_THRESHOLD_PX`, because capturing on pointerdown made Chromium retarget
 * the `click` and killed the inner <Link> (L2-175 Item 1). That deferral is
 * right and this fix keeps it.
 *
 * Its consequence is a window where the card is "swiping" and has captured
 * nothing. If the pointer leaves the card before any pointermove reaches it — a
 * fast trackpad flick — no capture is taken and the card never sees the
 * pointerup, so nothing clears the flag: `onPointerUp`/`onPointerCancel` cannot
 * fire on an element that is neither under the pointer nor holding capture, and
 * the hook exposes no `onPointerLeave`. `onPointerMove` then asked only whether
 * `swiping.current` was set, never whether a button was actually held.
 *
 * ── HOW THIS IS OBSERVED WITHOUT A DOM ──────────────────────────────────────
 *
 * `testEnvironment` is `node` and there is no jsdom or react-test-renderer, so
 * the hook cannot be mounted and driven with real events. It does not need to
 * be: an SSR render hands out the real handler closures, and the real `ref` is
 * returned too. `setOffset` is a no-op under SSR, so the offset itself is not
 * the observable — `setPointerCapture` is. A move past the threshold captures
 * only while `swiping.current` is still set, so "did a later genuine drag
 * capture?" reports the flag's state exactly, through the hook's own code path
 * rather than a copy of it.
 */

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";

import { useSwipe } from "../../components/discover/shared";

type Handlers = ReturnType<typeof useSwipe>["handlers"];

/** Runs the real hook once and hands back its live handlers and ref. */
function mountSwipe(): { handlers: Handlers; captured: number[] } {
  let handlers: Handlers | null = null;
  const captured: number[] = [];

  function Probe() {
    const swipe = useSwipe(undefined, undefined, undefined);
    handlers = swipe.handlers;
    // The element the hook would call setPointerCapture on.
    (swipe.ref as React.MutableRefObject<unknown>).current = {
      setPointerCapture: (id: number) => captured.push(id),
      releasePointerCapture: () => {},
    };
    return null;
  }

  renderToStaticMarkup(<Probe />);
  if (!handlers) throw new Error("the probe never rendered");
  return { handlers, captured };
}

const move = (clientX: number, buttons: number, pointerId = 7) =>
  ({ pointerType: "mouse", clientX, buttons, pointerId }) as unknown as React.PointerEvent;
const down = (clientX: number) =>
  ({ pointerType: "mouse", clientX }) as unknown as React.PointerEvent;

describe("#4431 — a bare hover never drags a Discover card", () => {
  it("the observable works: a real held drag past the threshold DOES capture", () => {
    // Without this arm every assertion below could pass because the rig never
    // captures at all, rather than because the flag was cleared.
    const { handlers, captured } = mountSwipe();

    handlers.onPointerDown(down(100));
    handlers.onPointerMove(move(300, 1));

    expect(captured).toEqual([7]);
  });

  it("clears the gesture when a move arrives with no button held", () => {
    const { handlers, captured } = mountSwipe();

    // The trackpad flick: press, then the pointer leaves the card without the
    // card ever seeing a move or the pointerup. The flag is left set.
    handlers.onPointerDown(down(100));

    // The reader now simply moves the mouse back across the card.
    handlers.onPointerMove(move(180, 0));

    // A later genuine drag must find no gesture in progress, so it cannot
    // capture — which is only true if the hover cleared `swiping`.
    handlers.onPointerMove(move(300, 1));
    expect(captured).toEqual([]);
  });

  it("does not break an ordinary press-drag-release", () => {
    const { handlers, captured } = mountSwipe();

    handlers.onPointerDown(down(100));
    handlers.onPointerMove(move(112, 1)); // past DRAG_THRESHOLD_PX, button held
    handlers.onPointerMove(move(190, 1));

    expect(captured).toEqual([7]);
  });

  it("CONTROL: touch is untouched — a phone sends buttons:0 on every touch move", () => {
    // A real touch drag reports `buttons: 0` throughout, so the new check would
    // kill swiping on phones — the surface this gesture exists for — if it were
    // ever reached. It is not: the pointer handlers bail on pointerType "touch"
    // first, and touch is driven by onTouchStart/Move/End instead. This arm is
    // green both with and WITHOUT the fix, which is the point: it pins the
    // ordering that keeps the fix off the touch path.
    const { handlers, captured } = mountSwipe();

    handlers.onTouchStart({ touches: [{ clientX: 100 }] } as unknown as React.TouchEvent);
    handlers.onPointerMove(
      { pointerType: "touch", clientX: 300, buttons: 0, pointerId: 7 } as unknown as React.PointerEvent,
    );
    // The touch gesture is still live and still tracked by its own handler.
    // (onTouchEnd is deliberately not called: past 80px it reaches
    // `window.setTimeout`, and this suite runs in the `node` environment.)
    handlers.onTouchMove({ touches: [{ clientX: 300 }] } as unknown as React.TouchEvent);

    // The mouse path was never entered, so nothing was captured.
    expect(captured).toEqual([]);
  });
});
