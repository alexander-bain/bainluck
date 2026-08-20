// The whole percent this surface prints for a probability — web's arm of
// `contracts/rendered_percent.json` (#1933).
//
// This was `Math.round(probability * 100)` inline in the Label Pass page, which
// is correct and was never the bug. It is extracted because it is now half of a
// CROSS-RUNTIME contract: the server takes the graded card's fingerprint at this
// exact resolution so that a drift refusal is always explicable to the person
// who was looking at the card, and Swift prints the same number on native. An
// expression inlined in a JSX attribute cannot be driven through a shared table;
// a named function can, and all three arms now are.
//
// UX-P110 shipped the Python side using banker's rounding against this, and the
// test beside it asserted the JavaScript answer in a comment while expecting the
// Python one in the assertion. See the contract file for why a comment was never
// going to hold this together.

export function renderedPercent(probability: number | null | undefined): number | null {
  if (probability === null || probability === undefined) return null;
  if (!Number.isFinite(probability)) return null;
  return Math.round(probability * 100);
}
