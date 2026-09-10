/**
 * #4631 — `sr-only` IS `position:absolute`, AND AN ABSOLUTE BOX PICKS ITS OWN CLIP.
 *
 * ═══ WHAT THE PAGE DID ═══
 *
 * `/tournaments/us-open` scrolled sideways 71px on a phone: 390px viewport,
 * 461px document, `scrollTo(300,0)` landing at `scrollX 71`.
 *
 * ═══ WHY EVERY RECT-BASED PROBE BLAMED THE WRONG ELEMENT ═══
 *
 * The grid looks guilty and is innocent, which is worth stating because two
 * sessions' worth of probes pointed at it:
 *
 *   - 68 elements inside the grid report a right edge past the viewport, so a
 *     naive "who overflows" scan indicts the grid immediately. **A rect ignores
 *     clipping** — those elements are the grid's own content inside a working
 *     `overflow-x:auto` scroller (`clientWidth` 332, `scrollWidth` 452), and
 *     being wider than the card is the entire point of ruling 5's swipe.
 *   - Filtering to elements with no clipping ancestor returns **zero**.
 *   - Forcing `overflow-x:hidden` on the scroller moved the document width by
 *     **nothing**. The scroller was already clipping; clipping harder is not a
 *     fix for something the clip never covered.
 *
 * The only test that names a cause is counterfactual — hide a subtree and ask
 * whether the overflow left with it. Doing that (`tools/overflow-culprit-4631.mjs`)
 * lands on the grid's 30 `sr-only` spans, and hiding just those took the
 * document from 461 back to 390.
 *
 * ═══ THE ACTUAL RULE, WHICH IS THE THING WORTH GUARDING ═══
 *
 * Tailwind implements `sr-only` as `position:absolute` (plus a 1px box and a
 * clip rect). An absolutely-positioned element is clipped by an ancestor's
 * overflow **only if that ancestor is in its containing block chain** — and a
 * containing block is established by a positioned ancestor, not by an
 * overflowing one. The scroller was `position:static`, so all 30 labels
 * resolved past it to the `relative` wrapper OUTSIDE the scroller, were never
 * subject to its clip, and each parked a 1px box at document x=461.
 *
 * 71px of horizontal scroll, caused entirely by content that is invisible by
 * construction. Adding `relative` to the scroller makes it the containing
 * block, and the labels fall back inside the clip they always looked like they
 * were in.
 *
 * ═══ WHAT THIS FILE CAN AND CANNOT PROVE ═══
 *
 * jsdom does not lay out, so the 461->390 measurement is not reproducible here
 * and is not faked: it was taken on production and is recorded on the issue and
 * in the component's comment. What IS checkable without a browser is the
 * structural precondition — that the element carrying the `sr-only` labels also
 * carries its own containing block. That is the invariant which, if someone
 * drops `relative` while tidying the class list, silently restores the 71px.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "node:fs";
import path from "node:path";

import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import { readPlayoffGrid, type PlayoffGrid as GridModel } from "@/lib/playoffGrid";
import type { TournamentPayload } from "@/lib/tournament";

const PAYLOAD = JSON.parse(
  fs.readFileSync(
    path.join(__dirname, "..", "..", "..", "docs", "mocks", "us-open", "payload-2026-08-27.json"),
    "utf8"
  )
) as TournamentPayload;

function mensGrid(): GridModel {
  const grid = readPlayoffGrid(PAYLOAD.grids?.["mens-singles"]);
  if (grid === null) throw new Error("the committed payload carries no men's grid");
  return grid;
}

/** The scroller's opening tag, which is where the class list lives. */
function scrollerTag(html: string): string {
  const match = html.match(/<div[^>]*data-testid="grid-scroller"[^>]*>/);
  if (match === null) throw new Error("no grid-scroller in the rendered markup");
  return match[0];
}

describe("#4631 — the grid's screen-reader labels stay inside the grid's clip", () => {
  it("the scroller establishes its own containing block", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={mensGrid()} initialExpanded />);
    const tag = scrollerTag(html);

    // `relative` on the SCROLLER, not merely on the wrapper around it. The
    // wrapper has been `relative` throughout — that is precisely what the
    // absolute labels were escaping to.
    expect(tag).toMatch(/\brelative\b/);
  });

  it("...and it is the scroller that carries BOTH the clip and the labels", () => {
    // The reason the fix belongs on this element and nowhere else. If a future
    // change moves the `sr-only` labels out of the scroller, or moves the
    // overflow off it, this pairing is what stops the `relative` above from
    // becoming a cargo-culted class nobody can justify.
    const html = renderToStaticMarkup(<PlayoffGrid grid={mensGrid()} initialExpanded />);
    const tag = scrollerTag(html);

    expect(tag).toContain("overflow-x-auto");

    const scrollerStart = html.indexOf('data-testid="grid-scroller"');
    expect(html.indexOf("sr-only")).toBeGreaterThan(scrollerStart);
  });

  it("a grid too narrow to scroll needs no clip, and the guard says so honestly", () => {
    // The positive control. Without it, "the scroller is relative" could pass
    // on a component that never renders a scroller at all, and the test above
    // would be asserting a constant rather than a decision.
    const narrow = { ...mensGrid(), columns: mensGrid().columns.slice(0, 1) };
    const html = renderToStaticMarkup(<PlayoffGrid grid={narrow} initialExpanded />);

    expect(html).not.toContain("overflow-x-auto");
    // The labels are still rendered — they are the thing being clipped, so
    // their presence is what makes the scrolling case above non-vacuous.
    expect(html).toContain("sr-only");
  });
});
