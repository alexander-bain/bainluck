/**
 * #8449 — a browser clamp is not the reader taking over the grid.
 *
 * WHAT A READER SAW. `/playoffs/ncaa-basketball`, 390px, production, landing
 * state: a stray "ne" in the header between the pinned `Team` cell and
 * `Champion` — the tail of "Title Game", the column straddling the seam. The
 * #7268 cover exists for exactly that column and was not painted.
 *
 * THE MECHANISM, measured in the live page (scroll setter + capture-phase scroll
 * listener): the grid aligned itself to scrollLeft 331 with scrollWidth 655,
 * then the table settled to 634 and the browser clamped the scroller to 318 and
 * fired a scroll event nobody claimed. `handleScroll` read that as the reader,
 * set `restingOnAlignment` false — and the cover is painted only while resting.
 * Header boxes at that moment: `Team` ends at 188, `Title Game` spans
 * 126.4–213.4, so 25.4px of it was showing and the cover's width would have
 * been exactly that.
 */
import { readFileSync } from "fs";
import { join } from "path";

import { isLayoutClamp, stickyStraddleCover } from "../../components/TournamentProgressionTable";

const CODE = readFileSync(
  join(process.cwd(), "components", "TournamentProgressionTable.tsx"),
  "utf8",
);

describe("#8449 isLayoutClamp — the one position a reader cannot be in", () => {
  test("the production specimen: 331 → 318 after the table narrowed 655 → 634", () => {
    // clientWidth 316, so the new maximum is 634 − 316 = 318.
    expect(isLayoutClamp({ previousScrollLeft: 331, scrollLeft: 318, maxScrollLeft: 318 })).toBe(true);
  });

  test("a reader dragging to the far right edge is still a reader", () => {
    expect(isLayoutClamp({ previousScrollLeft: 290, scrollLeft: 318, maxScrollLeft: 318 })).toBe(false);
  });

  test("a reader dragging left from the far right is still a reader", () => {
    expect(isLayoutClamp({ previousScrollLeft: 318, scrollLeft: 300, maxScrollLeft: 318 })).toBe(false);
  });

  test("a reader at the edge nudging within a subpixel is still a reader", () => {
    expect(isLayoutClamp({ previousScrollLeft: 318.3, scrollLeft: 318, maxScrollLeft: 318 })).toBe(false);
  });

  test("the table narrowing but not enough to move the scroller is not a clamp", () => {
    // Previous position still within the new bounds: the browser moved nothing.
    expect(isLayoutClamp({ previousScrollLeft: 200, scrollLeft: 200, maxScrollLeft: 318 })).toBe(false);
  });

  test("unmeasured (jsdom: every number 0) is not a clamp", () => {
    expect(isLayoutClamp({ previousScrollLeft: 0, scrollLeft: 0, maxScrollLeft: 0 })).toBe(false);
  });

  test("the cover it re-enables is the width the production header left showing", () => {
    // `Title Game` 126.4–213.4 against the `Team` cell's right edge at 188.
    expect(
      stickyStraddleCover({ cols: [{ left: 126.4, right: 213.4 }], stickyRight: 188 }),
    ).toBeCloseTo(25.4, 5);
  });
});

describe("#8449 the scroll handler asks before it blames the reader", () => {
  const handler = CODE.slice(
    CODE.indexOf("const handleScroll = useCallback"),
    CODE.indexOf("}, [syncScrollAffordance]);", CODE.indexOf("const handleScroll = useCallback")),
  );

  test("the handler this guards is there", () => {
    expect(handler.length).toBeGreaterThan(100);
    expect(handler).toContain("setRestingOnAlignment(false)");
  });

  test("a clamp is tested BEFORE the reader is marked", () => {
    const clamp = handler.indexOf("isLayoutClamp(");
    const blame = handler.indexOf("readerScrolled.current = true");
    expect(clamp).toBeGreaterThan(-1);
    expect(blame).toBeGreaterThan(clamp);
  });

  test("the previous position is read before it is overwritten", () => {
    const read = handler.indexOf("const previousScrollLeft = lastScrollLeft.current");
    const write = handler.indexOf("lastScrollLeft.current = el.scrollLeft");
    expect(read).toBeGreaterThan(-1);
    expect(write).toBeGreaterThan(read);
  });

  test("our own alignment move records where it left the scroller", () => {
    const align = CODE.slice(
      CODE.indexOf("const alignSortColumn = useCallback"),
      CODE.indexOf("const handleScroll = useCallback"),
    );
    expect(align).toMatch(/el\.scrollLeft = next;\s*lastScrollLeft\.current = el\.scrollLeft;/);
  });
});
