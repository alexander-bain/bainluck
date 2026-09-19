/**
 * #7246 — the sticky block reaches the card edge.
 *
 * WHAT A READER SAW. `/playoffs/mlb`, 390px, at the grid's resting scroll
 * position (which #7192 moved off zero): two orphan letters, `fs`, immediately
 * left of the `#` header — the tail of the scrolled-away `Make Playoffs`
 * column — and, on rows whose probability bar happened to be there, a floating
 * pale-blue sliver at the same x. Read cold it looks like a rendering fault,
 * not like a table sliding under a card edge.
 *
 * THE MECHANISM. `position: sticky; left: 0` pins to the scroller's CONTENT
 * edge, so with the scroller's own `px-2` the `#` cell's box starts at x=8 and
 * the strip at [0, 8] is covered by nothing. Measured at rest on production:
 *
 *   cell            left   background   box in the scroller
 *   #  (sticky)     0px    #ffffff      [8, 40]
 *   Team (sticky)   32px   #ffffff      [40, 188]
 *   Make Playoffs   —      transparent  [-89, 19]
 *
 * NOT a regression of #7192. The slot has existed since the sticky columns were
 * written; it was invisible while the grid rested at scrollLeft 0 because it sat
 * over nothing.
 *
 * WHY THIS IS A SOURCE SCAN AND NOT A RENDER. jsdom has no layout: every number
 * here is a declared Tailwind constant, and the defect is an arithmetic
 * relationship BETWEEN those constants across three elements. A render in jsdom
 * would report 0 for all of them and pass against the bug. Arm A therefore reads
 * the constants out of the classes and does the geometry; arm B pins the wiring
 * that decides whether the cover is on the page at all. Comment-stripped per
 * #3035 — this fix's own comment quotes `px-2`, `w-2` and `-left-2`, so an
 * un-stripped scan reads the prose as code and passes on a component that
 * renders none of it.
 */

import { readFileSync } from "fs";
import { join } from "path";

const CODE = readFileSync(
  join(__dirname, "../../components/TournamentProgressionTable.tsx"),
  "utf8",
)
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/^\s*\/\/.*$/gm, "");

/** Tailwind spacing step -> px. */
const STEP = 4;

/**
 * The JSX block for one element, from its testid back to its opening `<div`
 * and forward to the self-closing `/>`. Element-scoped, because a file-scoped
 * `toContain` cannot tell which element carries the class it found — that is
 * the exact over-reach #7246 had to narrow in #7192's own guard.
 */
function blockFor(testid: string): string {
  const at = CODE.indexOf(`data-testid="${testid}"`);
  expect(at).toBeGreaterThan(-1);
  const open = CODE.lastIndexOf("<div", at);
  const close = CODE.indexOf("/>", at);
  expect(open).toBeGreaterThan(-1);
  expect(close).toBeGreaterThan(at);
  return CODE.slice(open, close + 2);
}

/** The scroller's own class list — the element the padding lives on. */
function scrollerClasses(): string {
  const m = CODE.match(/ref=\{scrollRef\}[\s\S]{0,200}?className="([^"]+)"/);
  expect(m).not.toBeNull();
  return m![1];
}

function px(classes: string, pattern: RegExp): number {
  const m = classes.match(pattern);
  expect(m).not.toBeNull();
  const n = Number(m![1]);
  expect(Number.isFinite(n)).toBe(true);
  return n * STEP;
}

const COVER = "progression-sticky-bleed-cover";

describe("#7246 arm A — no scrolled column can show left of the sticky block", () => {
  // Every quantity is read, never written as a literal twice. The point of the
  // arm is that these are ONE number wearing three names, so a future `px-3`
  // with no matching cover has to go red.
  const scroller = scrollerClasses();
  const bleed = px(scroller, /-mx-(\d+)/); // how far the scroller escapes the wrapper
  const padding = px(scroller, /\bpx-(\d+)/); // how far the content is inset again
  const cover = blockFor(COVER);
  const coverWidth = px(cover, /\bw-(\d+)/);
  const coverOffset = -px(cover, /-left-(\d+)/); // wrapper coords, leftward

  // The sticky cells pin at `left-0`, i.e. to the content edge.
  const stickyInset = px(
    CODE.match(/className="sticky left-(\d+) z-10 bg-surface-card py-2/)?.[0] ?? "",
    /left-(\d+)/,
  );

  test("the constants are actually declared, not defaulted into agreement", () => {
    // Guard against the whole arm passing on a file that lost the classes: a
    // regex miss must be a failure, not a zero that satisfies the inequalities.
    expect(bleed).toBeGreaterThan(0);
    expect(padding).toBeGreaterThan(0);
    expect(coverWidth).toBeGreaterThan(0);
    expect(coverOffset).toBeLessThan(0);
    expect(stickyInset).toBe(0);
  });

  test("the uncovered strip is the scroller's padding, and it is not zero", () => {
    // Why this defect exists at all. If these two ever stop differing there is
    // nothing to cover and this whole guard is describing a fix for nothing —
    // which is worth knowing, loudly, rather than passing quietly.
    const stickyStartsAt = padding + stickyInset;
    expect(stickyStartsAt).toBe(8);
    expect(stickyStartsAt).toBeGreaterThan(0);
  });

  test("the cover spans the strip exactly, in the scroller's own coordinates", () => {
    // The wrapper is at 0; the scroller's left edge is at -bleed. So a cover
    // placed at `coverOffset` in wrapper coords starts at (bleed + coverOffset)
    // in scroller coords.
    const coverStart = bleed + coverOffset;
    const coverEnd = coverStart + coverWidth;
    const stickyStartsAt = padding + stickyInset;

    // Reaches the scroller's clip edge: nothing shows to the LEFT of the cover.
    expect(coverStart).toBeLessThanOrEqual(0);
    // Meets the sticky block: nothing shows BETWEEN the cover and the `#` cell.
    expect(coverEnd).toBeGreaterThanOrEqual(stickyStartsAt);
  });

  test("a wider scroller padding re-opens the strip and this arm says so", () => {
    // 🔴 THE ARM'S OWN FALSIFICATION. The three 2s agree today; the guard is
    // worthless unless it can tell agreement from coincidence. Re-run the same
    // arithmetic with the padding a reader-invisible step wider and require it
    // to fail — otherwise every inequality above is satisfied by constants that
    // happen to be equal and would stay green through the regression.
    const widerPadding = padding + STEP;
    const coverEnd = bleed + coverOffset + coverWidth;
    expect(coverEnd).toBeLessThan(widerPadding + stickyInset);
  });
});

describe("#7246 arm B — the cover is on the page, and only where it does work", () => {
  test("the cover exists, is inert, and is opaque rather than a fade", () => {
    const cover = blockFor(COVER);
    // A gradient is what the two CUES are; this one has to actually hide a
    // glyph, and `from-surface-card to-transparent` over 8px would leave the
    // `fs` legible through its tail.
    expect(cover).toContain("bg-surface-card");
    expect(cover).not.toContain("gradient");
    expect(cover).toContain("aria-hidden=\"true\"");
    expect(cover).toContain("pointer-events-none");
    // Full height: the fragment is in the header and the blue sliver is in the
    // body rows, so a header-only cover fixes half of what was reported.
    expect(cover).toContain("inset-y-0");
    expect(cover).toContain("absolute");
  });

  test("the cover never paints over the sticky cells it is extending", () => {
    // 🔴 The sticky cells are `z-10` and they must keep winning. This cover is
    // a later sibling in tree order, so giving it a positive z-index would put
    // it ABOVE them — and since it is card-coloured and opaque, that failure is
    // invisible in a screenshot until the block widens and eats the rank digit.
    const cover = blockFor(COVER);
    expect(cover).not.toMatch(/\bz-\d+/);
    // And it beats the probability bars, which are positioned and z-auto, on
    // tree order alone — so it has to come after the table.
    const tableClose = CODE.indexOf("</table>");
    const coverAt = CODE.indexOf(`data-testid="${COVER}"`);
    expect(tableClose).toBeGreaterThan(-1);
    expect(coverAt).toBeGreaterThan(tableClose);
  });

  test("the cover is a sibling of the scroller, not a child of it", () => {
    // An absolutely positioned child of an overflow container travels with the
    // content it is supposed to be hiding, and is clipped by the very edge it
    // is supposed to reach.
    const scrollerAt = CODE.indexOf("ref={scrollRef}");
    const coverAt = CODE.indexOf(`data-testid="${COVER}"`);
    expect(coverAt).toBeGreaterThan(scrollerAt);
    expect(CODE.indexOf("</table>")).toBeLessThan(coverAt);
  });

  test("the cover is gated on the scroll, and on a stricter test than the cue", () => {
    // 🔴 THE GATE IS THE PART THAT VARIES BY PAGE. The component has five call
    // sites and only two of them (`/playoffs`, `/categories/golf`) wrap it in a
    // `bg-surface-card` card; on `/futures/[id]` and `/sport/[sport]/[league]`
    // the 8px bleed sits over the page background. Ungated, this cover would
    // paint a card-coloured bar down the left of a grid that is resting at zero
    // and hiding nothing — a new defect on two surfaces, to fix one.
    expect(CODE).toContain("setLeftBleedExposed(el.scrollLeft > 0);");
    expect(CODE).toContain("{leftBleedExposed && (");
    // And it is NOT the cue's `> 4`: the cue is advice, this is a cover, and a
    // 4px rest still shows 4px of a scrolled column past the card edge.
    expect(CODE).toContain("setCanScrollLeft(el.scrollLeft > 4)");
    expect(CODE).not.toContain("setLeftBleedExposed(el.scrollLeft > 4)");
  });

  test("the gate is recomputed on scroll rather than frozen at mount", () => {
    // It is set inside the same callback the cues use, and that callback is the
    // scroll handler's — otherwise the cover appears once and then lies.
    const sync = CODE.indexOf("const syncScrollAffordance = useCallback(");
    const set = CODE.indexOf("setLeftBleedExposed(");
    const syncEnd = CODE.indexOf("}, []);", sync);
    expect(sync).toBeGreaterThan(-1);
    expect(set).toBeGreaterThan(sync);
    expect(set).toBeLessThan(syncEnd);
    expect(CODE).toContain("onScroll={handleScroll}");
    expect(CODE).toContain("syncScrollAffordance();");
  });

  test("the cover is one element, and the two cues are still the two cues", () => {
    // #7192's guard counted `pointer-events-none absolute` file-wide to pin
    // "exactly two cues". That count is now three and the third is this cover,
    // so the count moved here where it can name what it is counting.
    const covers = CODE.split("\n").filter((l) => l.includes(COVER));
    expect(covers).toHaveLength(1);
    const cueLines = CODE.split("\n").filter((l) =>
      l.includes("progression-scroll-affordance"),
    );
    expect(cueLines).toHaveLength(2);
    expect(CODE.match(/pointer-events-none absolute/g)).toHaveLength(3);
  });
});
