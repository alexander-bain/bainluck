// #4518: the ANSWERS row title must never paint through the outcome column.
//
// This jest setup does logic, not RTL, so it cannot render flexbox and cannot measure a
// collision — that is what `tools/answers-row-overlap-4136.mjs` does against production.
// What CAN be pinned here is the CLASS CONTRACT the no-overlap behaviour rests on, because
// the defect was a single class (`flex-shrink-0` on a tail inside a `min-w-0` container with
// visible overflow) and a revert to it is a one-word edit that nothing else would catch.
//
// 🔴 THE TRAP THIS TEST IS WRITTEN AROUND: the fix's own explanatory comment names
// `flex-shrink-0` and `overflow-hidden` in prose, several times, because it documents the two
// shapes that do NOT work. A naive `source.includes("flex-shrink-0")` therefore passes — or
// fails — on the COMMENT rather than on the JSX, and would keep passing after someone reverted
// the actual class. Every assertion below runs on comment-STRIPPED source, and the first test
// proves the stripping works by checking a string that exists ONLY in the comment.

import { readFileSync } from "fs";
import { join } from "path";

const SRC = readFileSync(
  join(__dirname, "../../components/SearchFamilyCard.tsx"),
  "utf8",
);

/** Source with `//` and block comments removed. Deliberately simple: this file has no
 *  regex literals or string literals containing comment markers, and the negative control
 *  below fails loudly if that ever stops being true. */
const stripComments = (s: string) =>
  s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

const CODE = stripComments(SRC);

/** The JSX of the title container: from `flex-1 min-w-0` to the end of that element. */
const titleBlock = () => {
  // Anchored WITHOUT the closing quote on purpose: #4545 appended `gap-1` to this
  // container, and an anchor that pins the end of the class list turns every
  // assertion below into a false red the next time a class is added.
  const start = CODE.indexOf('"flex-1 min-w-0 flex items-center');
  expect(start).toBeGreaterThan(-1);
  return CODE.slice(start, start + 400);
};

describe("#4518 the title tail yields before it overlaps", () => {
  it("NEGATIVE CONTROL: the comment prose really is stripped, so the rest of this file is testing code", () => {
    // These sentences exist ONLY inside the fix's comment block. If they survive stripping,
    // every assertion below is reading prose and this suite is decorative.
    expect(SRC).toContain("hard-cutting the tail");
    expect(CODE).not.toContain("hard-cutting the tail");
    // ...and the comment does mention the banned class, which is exactly why we strip.
    expect(SRC).toContain("flex-shrink-0");
  });

  it("the tail is NOT flex-shrink-0 — the class that caused the overlap", () => {
    expect(titleBlock()).not.toContain("flex-shrink-0");
  });

  it("the tail can ellipsise inside its own box rather than over its neighbour", () => {
    const block = titleBlock();
    // both head and tail carry `truncate`; the tail's is the new half.
    expect(block.match(/truncate/g)?.length).toBeGreaterThanOrEqual(2);
  });

  it("the head gives up its width FIRST — the order is what stops the collision", () => {
    const block = titleBlock();
    const head = block.indexOf("shrink-[9999]");
    const tail = block.indexOf("shrink}") >= 0 ? block.indexOf("shrink}") : block.indexOf("truncate shrink ");
    expect(head).toBeGreaterThan(-1);
    expect(tail).toBeGreaterThan(-1);
    // the huge-shrink item must be the head, i.e. appear before the tail in the JSX
    expect(head).toBeLessThan(tail);
  });

  it("the title container still lets flexbox size it below content (min-w-0), so the row can compress at all", () => {
    expect(CODE).toContain("flex-1 min-w-0 flex items-center");
  });

  it("#4545: head and tail are separated by LAYOUT, not by a character truncation can eat", () => {
    // The separating space lives at the end of the head (`snapToBoundary` cuts at
    // `sp + 1`), so it is clipped away the moment the head truncates. `gap-1` on the
    // container is what guarantees the gap survives.
    const block = titleBlock();
    const container = block.slice(0, block.indexOf(">"));
    expect(container).toContain("gap-1");
  });

  it("#4545: the gap is on the CONTAINER, so a row with no tail is untouched", () => {
    // gap only applies BETWEEN siblings. If this were a margin on the head instead, a
    // row whose `tail` is empty — the ordinary, overwhelmingly common case #4136
    // promises to leave alone — would shift. Pin that the head/tail divs carry no
    // separating margin of their own.
    const block = titleBlock();
    expect(block).not.toMatch(/\b(ml-|mr-|pl-|pr-)\d/);
    // and the tail is still conditional, which is what makes the container single-child
    expect(block).toContain("title.tail &&");
  });

  it("the answer column keeps the #4136 contract: capped, truncatable, percentage pinned", () => {
    // a revert here would re-evict the percentage — the OTHER half of #4136.
    expect(CODE).toContain("min-w-0 max-w-[55%]");
    expect(CODE).toMatch(/truncate text-text-primary font-medium/);
  });
});
