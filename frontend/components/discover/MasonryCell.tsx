"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";

/**
 * #8491 — the Discover feed places cards ACROSS then down.
 *
 * The feed used to be a CSS multi-column layout. Multi-column fills top to
 * bottom one column at a time, so on a laptop the first row across the screen
 * was card 1 and then whichever cards started the later columns — measured on
 * production at 1280px with the whole feed loaded: cards 1, 30, 63 and 95. The
 * served page one sat below the fold, and every page that loaded re-flowed
 * every column under the reader.
 *
 * This is a CSS grid with the SAME 1/2/3/4 column ladder and the same 16px
 * gutter, so column widths (and `heroSrcSet`'s `sizes`) are unchanged. Rows are
 * a small fixed unit and each cell spans the rows its measured height needs, so
 * the grid's own auto-placement drops each card into the first column with
 * room: row one is cards 1–4, and a new page appends below instead of moving
 * cards the reader has already seen. DOM order stays feed order (tab order,
 * screen readers, the `discover-card` audit hook).
 *
 * One column (the phone) is plain flow — no row unit, no span — so a long feed
 * never approaches a browser's grid-line cap there.
 */
export const MASONRY_ROW_PX = 8;
export const MASONRY_GAP_PX = 16;

export const MASONRY_GRID_CLASS =
  "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-x-4 sm:auto-rows-[8px]";

/** Number of column tracks in a computed `grid-template-columns` value. */
export function gridColumnCount(templateColumns: string | null | undefined): number {
  const value = (templateColumns ?? "").trim();
  if (!value || value === "none") return 1;
  return value.split(/\s+/).length;
}

/**
 * Rows a cell of `contentHeight` px spans, gutter included — or null in a
 * single-column grid, where the cell is left in normal flow.
 */
export function masonryRowSpan(contentHeight: number, columns: number): number | null {
  if (columns <= 1) return null;
  return Math.max(1, Math.ceil((contentHeight + MASONRY_GAP_PX) / MASONRY_ROW_PX));
}

/**
 * Write the cell's span from its content height and its grid's computed
 * `grid-template-columns` — cleared (normal flow) in one column.
 */
export function placeMasonryCell(
  cell: { style: { gridRowEnd: string } },
  contentHeight: number,
  templateColumns: string | null | undefined,
): void {
  const span = masonryRowSpan(contentHeight, gridColumnCount(templateColumns));
  cell.style.gridRowEnd = span == null ? "" : `span ${span}`;
}

export default function MasonryCell({
  className = "",
  children,
  ...rest
}: {
  className?: string;
  children: ReactNode;
  "data-testid"?: string;
}) {
  const cellRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const cell = cellRef.current;
    const content = contentRef.current;
    if (!cell || !content) return;

    const place = () => {
      const grid = cell.parentElement;
      placeMasonryCell(
        cell,
        content.getBoundingClientRect().height,
        grid ? window.getComputedStyle(grid).gridTemplateColumns : null,
      );
    };

    place();
    // Width changes when the column count does, and height when an image
    // loads or a card expands — both re-place the cell.
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(place);
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={cellRef} className={`pb-4 ${className}`.trim()} {...rest}>
      <div ref={contentRef}>{children}</div>
    </div>
  );
}
