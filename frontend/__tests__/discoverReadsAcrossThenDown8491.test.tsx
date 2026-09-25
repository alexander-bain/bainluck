/**
 * #8491 — desktop Discover read DOWN each column, so the first screen at 1280px
 * was cards 1, 30, 63 and 95 (production, 2026-09-24, whole feed loaded).
 *
 * The feed container was a CSS multi-column layout; the fix is a grid with the
 * same column ladder whose cells span the rows their measured height needs, so
 * auto-placement fills across then down. These tests pin the three parts that
 * are ours: the page renders the grid (not multi-column), the span arithmetic,
 * and that a cell writes its span only in a multi-column grid.
 */
import fs from "fs";
import path from "path";
import { renderToStaticMarkup } from "react-dom/server";
import MasonryCell, {
  MASONRY_GAP_PX,
  MASONRY_GRID_CLASS,
  MASONRY_ROW_PX,
  gridColumnCount,
  masonryRowSpan,
  placeMasonryCell,
} from "@/components/discover/MasonryCell";

const PAGE = fs.readFileSync(path.join(process.cwd(), "app/discover/page.tsx"), "utf8");

describe("#8491 the Discover feed container", () => {
  it("is the across-then-down grid, not a multi-column layout", () => {
    expect(PAGE).toContain("<div className={MASONRY_GRID_CLASS}>");
    // The defect's container. `columns-*` on the feed is what made row one 1/30/63/95.
    const feedBlock = PAGE.slice(PAGE.indexOf("visibleItems.map((gi, idx)") - 400, PAGE.indexOf("visibleItems.map((gi, idx)"));
    expect(feedBlock).not.toMatch(/columns-\d/);
    expect(MASONRY_GRID_CLASS).toMatch(/^grid /);
    expect(MASONRY_GRID_CLASS).not.toMatch(/columns-/);
  });

  it("wraps every feed card in a MasonryCell that keeps the audit hook", () => {
    expect(PAGE).toMatch(/<MasonryCell\s+key=\{key\}\s+data-testid="discover-card"/);
    expect(PAGE).not.toMatch(/data-testid="discover-card"\s+className=\{`break-inside-avoid/);
  });

  it("uses the row unit only off the phone, so one column stays plain flow", () => {
    expect(MASONRY_GRID_CLASS).toContain(`sm:auto-rows-[${MASONRY_ROW_PX}px]`);
    expect(MASONRY_GRID_CLASS).not.toMatch(/(^| )auto-rows-/);
  });
});

describe("#8491 span arithmetic", () => {
  it("counts computed column tracks", () => {
    expect(gridColumnCount("368px 368px 368px 368px")).toBe(4);
    expect(gridColumnCount("  301.5px 301.5px ")).toBe(2);
    expect(gridColumnCount("334px")).toBe(1);
    expect(gridColumnCount("none")).toBe(1);
    expect(gridColumnCount("")).toBe(1);
    expect(gridColumnCount(undefined)).toBe(1);
  });

  it("spans the content plus one gutter, rounded up to whole rows", () => {
    expect(MASONRY_GAP_PX).toBe(16);
    expect(masonryRowSpan(400, 4)).toBe(52); // (400 + 16) / 8
    expect(masonryRowSpan(401, 4)).toBe(53); // never clips a pixel
    expect(masonryRowSpan(0, 2)).toBe(2);
  });

  it("returns null in one column so the phone never gets a span", () => {
    expect(masonryRowSpan(400, 1)).toBeNull();
    expect(masonryRowSpan(400, 0)).toBeNull();
  });
});

describe("#8491 MasonryCell", () => {
  it("writes the span in a four-column grid", () => {
    const cell = { style: { gridRowEnd: "" } };
    placeMasonryCell(cell, 400, "368px 368px 368px 368px");
    expect(cell.style.gridRowEnd).toBe("span 52");
  });

  it("clears a span when the grid drops to one column (resize to phone width)", () => {
    const cell = { style: { gridRowEnd: "span 52" } };
    placeMasonryCell(cell, 400, "334px");
    expect(cell.style.gridRowEnd).toBe("");
  });

  it("renders the audit hook, the gutter and the caller's class on the grid item", () => {
    const html = renderToStaticMarkup(
      <MasonryCell data-testid="discover-card" className="animate-peek-right">
        <p>card</p>
      </MasonryCell>,
    );
    expect(html).toBe('<div class="pb-4 animate-peek-right" data-testid="discover-card"><div><p>card</p></div></div>');
  });
});
