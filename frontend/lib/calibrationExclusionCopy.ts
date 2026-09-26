// #8955 — the page's own words for the exclusion notes under "How We Measure This".
//
// The payload keys its per-cell exclusion counts as `source/category`
// (`kalshi/economics`) or a bare category (`esports`), and its temporary-cell
// map carries the backend's own revert condition, written for a reviewer
// ("the Polymarket player-prop writer stops overwriting the market's own quote
// with a near-0.50 placeholder…"). Both were printed straight onto the page.
// Notice 34 / D102: a reader sees plain words; the machine's keys and its
// explanation of itself stay in the payload.
//
// Kept out of the page so the guard can CALL it — the page is a "use client"
// component behind SWR (same reason as `calibrationCategories.ts`).

import { categoryLabel } from "./calibrationCategories";

/** `kalshi/economics` → "Kalshi Economics"; `esports` → "Esports". Never a raw key. */
export function exclusionCellLabel(cell: string, sourceLabel: (src: string) => string): string {
  const slash = cell.indexOf("/");
  if (slash < 0) return categoryLabel(cell);
  const source = sourceLabel(cell.slice(0, slash));
  return `${source} ${categoryLabel(cell.slice(slash + 1))}`;
}

/**
 * What ends a temporary exclusion, in the page's words.
 *
 * Only cells this page has written a sentence for get one. A cell the backend
 * starts emitting later still gets its disclosure (CAL-P119: a temporary
 * exclusion is always named as temporary), but in a generic clause rather than
 * the server's prose — the #4067 rule that this page never renders text it
 * does not own.
 */
const TEMPORARY_CELL_CONDITIONS: Readonly<Record<string, string>> = {
  "polymarket/baseball":
    "we fix the bug that saved these player-prop prices as a stand-in near 50% " +
    "instead of the price the market actually traded at",
};

export function temporaryCellCondition(cell: string): string {
  return TEMPORARY_CELL_CONDITIONS[cell] ?? "we fix the fault that set them aside";
}
