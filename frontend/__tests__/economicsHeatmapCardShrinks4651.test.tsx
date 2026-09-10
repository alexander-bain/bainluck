/**
 * #4651 (/economics half) — THE SCROLLER IS INNOCENT. THE GRID ITEM IS THE BUG.
 *
 * ═══ WHAT PRODUCTION SERVED ═══
 *
 * `https://bainluck.com/economics` at a 390px viewport, 2026-09-09:
 * `document.scrollWidth` = **558**. The whole page slid sideways by 168px, so
 * every section on it — not just the Fed one — carried a dead strip on the
 * right and the reader could push the header off-screen. `/politics` (485) and
 * `/entertainment` (473) do the same thing for DIFFERENT reasons and are not
 * fixed here; see #4651.
 *
 * ═══ THE MECHANISM ═══
 *
 * `FedHeatmap` already does the right thing: a `minWidth: 500` grid sealed
 * inside `overflow-x-auto`. A heatmap of FOMC meetings genuinely needs 500px,
 * and on a phone it is meant to scroll inside its card.
 *
 * It cannot, because the scroller is never given a narrower box to scroll in.
 * The card holding it is a GRID ITEM (`<div className="grid md:grid-cols-...">`
 * one level up), and a grid item's default `min-width: auto` floors its track
 * at the min-content of its entire subtree. The 500px heatmap is in that
 * subtree. So the track resolves to 500px + padding, the card is 500px wide,
 * the scroller's box is 500px wide, there is nothing to scroll, and the
 * document is 558px wide at a 390px viewport.
 *
 * ═══ THE COUNTERFACTUAL, MEASURED ON PRODUCTION (ux/1169) ═══
 *
 *     injected                                      | document.scrollWidth
 *     ----------------------------------------------|---------------------
 *     nothing                                        | 558
 *     min-width:0 on the GRID ITEM (the card)        | 390   <- the fix
 *     min-width:0 on the SCROLLER (.overflow-x-auto) | 558   <- no change
 *
 * The last row is the point, and it is the same lesson #4631 cost three
 * sessions to learn on the tournament grid: **patching the element that
 * visibly misbehaves does nothing.** The permission to shrink has to be
 * granted on the item whose `min-width: auto` is doing the flooring.
 *
 * ═══ WHY THIS GUARD IS SHAPED THE WAY IT IS ═══
 *
 * jsdom does no layout — `scrollWidth` is 0 for everything, and the CSS that
 * matters here is Tailwind's, which never reaches the test realm. So a render
 * test cannot observe this bug at all. What CAN be pinned is the three-part
 * structural claim the fix rests on, each part read from the source that
 * actually declares it:
 *
 *   1. the precondition still exists  — FedHeatmap still seals a fixed-minimum
 *      box inside a horizontal scroller (if it stops, this guard is obsolete
 *      and should say so out loud rather than pass on a vanished bug);
 *   2. the card wrapping it carries `min-w-0`, and is still a grid item (the
 *      `min-width: auto` rule bites on grid/flex items and nothing else);
 *   3. `Card` still forwards `className` to the rendered element — otherwise
 *      the class in (2) is a comment.
 *
 * Every parser below asserts it found something before it asserts anything
 * about it. A source-scanning guard that silently matches nothing is worse
 * than no guard (ruling: #3704's guard, same shape).
 *
 * The regression this exists to catch is not "someone deletes min-w-0". It is
 * "someone moves the heatmap into a different card, or wraps it in one more
 * div" — at which point the page silently goes back to 558px wide and nothing
 * anywhere fails.
 *
 *   npx jest --testPathPatterns=economicsHeatmapCardShrinks4651
 */

import React from "react";
import { readFileSync } from "fs";
import { join } from "path";
import { renderToStaticMarkup } from "react-dom/server";
import { Card } from "@/components/economics/atoms";

const PAGE_PATH = join(__dirname, "..", "app", "economics", "page.tsx");
const PAGE = readFileSync(PAGE_PATH, "utf8");
const LINES = PAGE.split("\n");

const indentOf = (line: string) => line.search(/\S/);

/** The index of the single line that opens an element, by a matcher. */
function lineIndex(matcher: RegExp, what: string): number {
  const hits = LINES.map((l, i) => (matcher.test(l) ? i : -1)).filter((i) => i >= 0);
  if (hits.length !== 1) {
    throw new Error(
      `#4651 guard expected exactly one ${what} in app/economics/page.tsx, found ` +
        `${hits.length}. If it was renamed, moved or duplicated, re-point this ` +
        `guard — do not delete it. The bug it pins is invisible to every other test.`,
    );
  }
  return hits[0];
}

/**
 * The opening tag of the nearest JSX element that ENCLOSES `fromIdx`.
 *
 * Walks up for the first line indented less than `fromIdx` that starts a tag.
 * Lines opening with `{` (a conditional or a comment) are skipped: they are not
 * elements and cannot be grid items.
 */
function enclosingTag(fromIdx: number, what: string): { idx: number; text: string } {
  const inner = indentOf(LINES[fromIdx]);
  for (let i = fromIdx - 1; i >= 0; i--) {
    const line = LINES[i];
    if (!line.trim()) continue;
    const ind = indentOf(line);
    if (ind >= inner) continue;
    if (!/^</.test(line.trim())) continue; // `{cond && (`, `{/* … */}`
    if (/^<\//.test(line.trim())) {
      throw new Error(
        `#4651 guard walked up from ${what} and hit a CLOSING tag first ` +
          `(line ${i + 1}). The indentation the parser reads is no longer ` +
          `reliable; re-point this guard.`,
      );
    }
    return { idx: i, text: line.trim() };
  }
  throw new Error(`#4651 guard found no element enclosing ${what}.`);
}

/* ═══ 1 · the precondition — a fixed minimum sealed in a scroller ═══════ */

describe("#4651 · FedHeatmap still needs its card to be allowed to shrink", () => {
  const heatmapOpen = lineIndex(/^function FedHeatmap\(/, "`function FedHeatmap`");
  const heatmapEnd = LINES.findIndex((l, i) => i > heatmapOpen && /^}/.test(l));
  const BODY = LINES.slice(heatmapOpen, heatmapEnd).join("\n");

  test("it declares a horizontal scroller", () => {
    expect(heatmapEnd).toBeGreaterThan(heatmapOpen);
    expect(BODY).toContain("overflow-x-auto");
  });

  test("and seals a box with an explicit minimum inside it", () => {
    // THE PRECONDITION. If this minimum ever goes away the heatmap can shrink
    // on its own and `min-w-0` below is merely harmless — but the fix would no
    // longer be load-bearing, and whoever removed it deserves to be told that
    // by a red test rather than to discover it on a phone.
    const min = BODY.match(/minWidth:\s*(\d+)/);
    expect(min).not.toBeNull();
    expect(Number(min![1])).toBeGreaterThan(390); // wider than the phone we ship to

    // …and it is INSIDE the scroller, not beside it. Order in the source is
    // the cheap proxy for nesting here, and it is exact: one scroller, one
    // minWidth, in that order.
    expect(BODY.indexOf("overflow-x-auto")).toBeLessThan(BODY.indexOf("minWidth"));
  });
});

/* ═══ 2 · the card is a grid item, and it is allowed to shrink ══════════ */

describe("#4651 · the card holding the heatmap can be narrower than the heatmap", () => {
  const useIdx = lineIndex(/<FedHeatmap\s/, "`<FedHeatmap …/>` call site");
  const card = enclosingTag(useIdx, "`<FedHeatmap />`");
  const parent = enclosingTag(card.idx, "the heatmap's card");

  test("the element wrapping the heatmap is a Card", () => {
    expect(card.text).toMatch(/^<Card\b/);
  });

  test("THE REGRESSION ASSERTION — that Card carries `min-w-0`", () => {
    // Read 558px wide at 390 before this class existed.
    expect(card.text).toMatch(/className="[^"]*\bmin-w-0\b/);
  });

  test("and it is still a grid item, which is the only reason the class works", () => {
    // `min-width: auto` resolves to min-content for grid and flex items, and to
    // 0 for everything else. Move this card out of the grid into a plain block
    // and `min-w-0` becomes a no-op that looks like a fix — so the container is
    // pinned here rather than assumed.
    expect(parent.text).toMatch(/className="[^"]*\b(grid|flex)\b/);
  });

  test("the sibling card in the same grid is deliberately NOT patched", () => {
    // Both `md:grid-cols-[1.6fr_1fr]` sections on this page look identical, and
    // the copy-the-one-liner instinct is exactly what ux/1169 warned against for
    // /politics and /entertainment. The CPI card holds a Histogram, which has no
    // fixed minimum and shrinks fine. A `min-w-0` appearing there means someone
    // swept the class in without measuring, and the next reader will believe a
    // cause that was never proven.
    const patched = LINES.filter((l) => /<Card\b[^>]*\bmin-w-0\b/.test(l));
    expect(patched).toHaveLength(1);
  });
});

/* ═══ 3 · the class actually reaches the DOM ════════════════════════════ */

describe("#4651 · Card forwards className", () => {
  test("a className passed to Card lands on the rendered element", () => {
    // Without this, section 2 is asserting the presence of a string that never
    // becomes CSS. `Card` is a 5-line atom; dropping the prop is a plausible
    // tidy-up and would be completely silent.
    const html = renderToStaticMarkup(
      <Card className="min-w-0">
        <span>x</span>
      </Card>,
    );
    expect(html).toContain("min-w-0");
  });

  test("and the base card styling survives alongside it", () => {
    // Both directions (gotcha #43): a Card that renders ONLY the passed class
    // would pass the test above and would have lost its surface, border and
    // padding.
    const html = renderToStaticMarkup(
      <Card className="min-w-0">
        <span>x</span>
      </Card>,
    );
    expect(html).toContain("bg-surface-card");
    expect(html).toContain("rounded-2xl");
  });
});
