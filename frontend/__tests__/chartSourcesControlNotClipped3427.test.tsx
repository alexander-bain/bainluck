// #3427 — THE `Sources` CONTROL WAS PAINTED OFF THE PHONE EDGE.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `bainluck.com/events/15306225` (Tiafoe v Michelsen, US Open QF) and
// `/events/15306160` (Sabalenka v Noskova), **390px**, 2026-09-07, and before
// that on `/events/15304445` mid-fifth-set when the issue was filed:
//
//     — BainLuck   — Sportsbooks   — Kalshi   — Polymarket   Sou
//
// The word cut mid-"Sources" and the chevron gone entirely. Not truncated with
// an ellipsis, not wrapped — painted past the card boundary. A TAPPABLE control
// the reader can neither read nor reach.
//
// ── THE CAUSE, WHICH IS NOT THE ONE THE ISSUE GUESSED ────────────────────────
//
// The issue supposed "a width calculation that omits the inter-item gaps and
// the card's horizontal padding". There is no width calculation anywhere near
// this row. It is a `justify-between` flex row whose LEFT child was a nowrap
// flex group carrying no `min-w-0`, and whose RIGHT child — the button — carried
// no `shrink-0`. The chip group therefore claimed its full intrinsic width and
// the button was pushed past the edge. Nothing measured anything, so nothing
// could be measuring it wrong.
//
// Measured at 390px: `px-4` leaves 358px; four chips are ≈336px including their
// three `gap-4`s; the button is ≈74px. 410 > 358, over by ≈52px — the width of
// the missing "rces ⌄".
//
// ── WHY IT SURFACED ON MARQUEE PAGES ─────────────────────────────────────────
//
// The trigger is the CHIP COUNT, and four chips means BainLuck + sportsbooks +
// Kalshi + Polymarket: an event with both prediction markets attached. So the
// row broke precisely on the BEST-attached events. `/events/15305579`
// (Andreeva v Potapova, two chips) rendered the control in full throughout —
// same component, same width, same session. The richer the data, the more
// certainly the control vanished.
//
// ── WHY A SOURCE SCAN ────────────────────────────────────────────────────────
//
// This is a layout property of JSX inside a default-exported Next.js page, so
// there is no function to call and no value to assert on. jsdom is no help
// either: it does not lay out, so it would report this row as fine both before
// and after the fix — a test that passes on the broken code is worse than none.
// The rule is therefore stated over the class list, and the positive control
// below proves the predicate DOES fire on the markup that shipped.
//
// ── WHY ALL THREE PROPERTIES, TOGETHER ───────────────────────────────────────
//
// Any one of them alone leaves the control reachable only by luck:
//
//   * `shrink-0` on the button alone — the button survives, but the chip group
//     still overflows and pushes it out of the padded box.
//   * `flex-wrap` on the chips alone — without `shrink-0` the button can still
//     be compressed to nothing before the chips agree to wrap.
//   * `min-w-0` alone — permits shrinking, does not cause wrapping.
//
// So the guard asserts the set, not the members.
//
// ═══ AMENDED BY #4083, 2026-09-08 — THE CHIP GROUP IS GONE ═══════════════════
//
// The chips in this row were a SECOND copy of the chart's own legend, sitting
// directly under it, and #4083 deleted them (D91's restore: one source legend,
// and it is the chart's). So the overflow this file was written for now has no
// source — there is nothing left in the row to claim 336px beside a 74px
// button.
//
// 🔴 THAT IS NOT A REASON TO DELETE THIS FILE. The bug was never "those seven
// chips"; it was "a growable child in this row next to a button with no
// `shrink-0`", and the row is still a flex row with a button in it. A guard
// retired because today's instance is gone is a guard that has to be
// rediscovered by the next reader of a 390px screenshot.
//
// So the rules split in two:
//
//   * UNCONDITIONAL — the button keeps `shrink-0` and the row buys no room by
//     hiding its own contents. True of the row as it stands today.
//   * CONDITIONAL — IF a chip group ever returns to this row, it wraps and it
//     shrinks. Written as an implication because there is nothing to assert it
//     over right now, and given a POSITIVE CONTROL below so that "the premise
//     is false" can never be confused with "the rule is satisfied".
//
// The conditional half is the weak kind of assertion, so it is paired with
// #4083's own guard (`chartFooterOneSourceLegend4083.test.tsx`), which asserts
// the premise stays false. Between them: no chips, and if chips, wrapping ones.

import { readFileSync } from "fs";
import { join } from "path";

const PAGE = join(process.cwd(), "app/events/[id]/page.tsx");

/**
 * The chart footer row: the `border-t` strip holding the disclosure (and, until
 * #4083, the legend chips beside it). Located by the button it contains rather
 * than by a line number, so ordinary edits above it do not silently move the
 * guard onto a different element.
 */
function chartFooterRow(source: string): string {
  const button = source.indexOf("setSourcesOpen(!sourcesOpen)");
  expect(button).toBeGreaterThan(-1);
  // Back up to the opening <div> of the row that contains the button.
  const rowStart = source.lastIndexOf("border-t border-surface-border", button);
  expect(rowStart).toBeGreaterThan(-1);
  return source.slice(rowStart, button + 400);
}

/** True when the row carries a growable group of legend chips beside the button. */
function hasChipGroup(row: string): boolean {
  return /w-4 h-\[2px\]/.test(row) || /\.map\(\s*\(?\s*chip/.test(row);
}

describe("#3427 the chart's disclosure survives phone width", () => {
  const source = readFileSync(PAGE, "utf8");
  const row = chartFooterRow(source);

  it("any legend chips in this row wrap instead of overflowing the card", () => {
    // The chips are what is allowed to grow, so they are what must give.
    // Vacuous today by #4083's design — the premise is what that guard holds.
    if (hasChipGroup(row)) expect(row).toContain("flex-wrap");
  });

  it("any chip group in this row can shrink below its intrinsic width", () => {
    // A flex item's default `min-width: auto` refuses to go below its content,
    // which is what let the group push the button out even inside a row that
    // had room to redistribute.
    if (hasChipGroup(row)) expect(row).toContain("min-w-0");
  });

  it("pins the disclosure button so it is never the thing that gives", () => {
    const buttonTag = row.slice(row.indexOf("<button"));
    expect(buttonTag).toContain("shrink-0");
  });

  it("does NOT buy room by scrolling the chips out of sight", () => {
    // THE FIX THAT WOULD HAVE BEEN WRONG. `overflow-x-auto` on the chip group
    // makes the button reachable and hides legend keys instead — every chip
    // names a line drawn on the chart directly above, so a hidden chip is an
    // unexplained curve. Trading a hidden control for hidden sources is not a
    // fix, and it would have passed the three assertions above.
    expect(row).not.toContain("overflow-x-auto");
    expect(row).not.toContain("overflow-hidden");
    expect(row).not.toContain("truncate");
  });

  it("POSITIVE CONTROL: the predicate fires on the markup that shipped", () => {
    // The exact classes from before the fix. If this reconstruction passed the
    // rules above, the rules would be describing something other than the bug.
    const shipped =
      '<div className="px-4 sm:px-5 py-2 border-t border-surface-border ' +
      'flex items-center justify-between">' +
      '<div className="flex items-center gap-4">' +
      '<div className="w-4 h-[2px] rounded" /><span>BainLuck</span>' +
      '<button className="flex items-center gap-1 px-2 py-1 rounded-md">';

    // 🔴 THE PREMISE FIRES. Both conditional rules above are implications, and
    // an implication whose premise is never satisfiable is a green test that
    // asserts nothing. This is the row the bug shipped in: chips present, so
    // both rules engage — and both fail it.
    expect(hasChipGroup(shipped)).toBe(true);
    expect(shipped).not.toContain("flex-wrap");
    expect(shipped).not.toContain("min-w-0");
    expect(shipped.slice(shipped.indexOf("<button"))).not.toContain("shrink-0");
  });

  it("POSITIVE CONTROL: the premise is genuinely false on the row today", () => {
    // The other half. If `hasChipGroup` had a typo it would read false on
    // everything, the two implications would pass vacuously forever, and the
    // control above would still be green. So the detector is exercised in both
    // directions on real inputs, not just on a reconstruction.
    expect(hasChipGroup(row)).toBe(false);
  });
});
