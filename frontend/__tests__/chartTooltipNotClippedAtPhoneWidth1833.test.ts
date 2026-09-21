// #1833 — THE WIN-PROBABILITY TOOLTIP WAS PAINTED OFF THE PHONE EDGE.
//
// ── WHAT THE READER SAW ──────────────────────────────────────────────────────
//
// `bainluck.com/events/14780544` (Chiefs v Colts), **390px**, 2026-09-21. Touch
// the chart anywhere past its first third and the tooltip card runs off the
// right edge of the screen. The page does not scroll sideways, so what is off
// the edge is simply gone — and what sits in that right-hand column is the
// period and clock, which `justify-between` pins there:
//
//     Chiefs 17 – 20 Colts              Halftim|
//     Chiefs 24 – 20 Colts        End of 3rd Qua|
//
// Measured with `tools/chart-tooltip-clip-1833.mjs` (it reads the rendered card
// against the viewport, because this is a layout fact and nothing else can see
// it). Inline chart: card 306px pinned at left=100 → right=406 on a 390px
// viewport, 16px gone, on 4 of 5 sampled positions. The fullscreen modal is
// worse: 330px at left=88 → right=418, 28px gone, on 5 of 5. At 375px: 3 of 5
// and 5 of 5.
//
// ── THE CAUSE, WHICH IS NOT "THE CARD IS TOO WIDE" ───────────────────────────
//
// The card carried `max-w-sm` (384px) and that cap NEVER BOUND. The card is
// absolutely positioned with auto width, and its content — score header, period,
// the blend row, then one row per source — wants more than a phone gives it, so
// it grew to its containing block instead: the chart wrapper (306px / 330px).
// The card was therefore exactly as wide as the chart, every time.
//
// Recharts then places it (`util/tooltip/translate.js`):
//
//     translateX = Math.max(coordinate.x - width - offset, viewBox.x)
//
// When the card cannot fit to the left of the cursor it is pinned at `viewBox.x`
// — the y-axis inset, measured 44px on both surfaces. A card as wide as the
// wrapper, pushed 44px right of the wrapper's left edge, therefore ends 44px
// PAST the wrapper's right edge. Not sometimes: always, and at every cursor
// position that triggers the flip. That is why the measured right edge is a
// CONSTANT (406, then 418) rather than something that tracks the pointer.
//
// So the fix is not "make it narrower" by feel. The card has to be bounded by
// the space that actually exists between the plot's left inset and the screen:
// worst-case inset is wrapperLeft(56) + viewBox.x(44) = 100px, and `7rem` covers
// that with a small margin. `min()` leaves the desktop card at 384px untouched —
// the cap only binds below 496px.
//
// ── WHY THE UNDERSCORES ARE LOAD-BearING ─────────────────────────────────────
//
// Tailwind turns `_` into a space in an arbitrary value. `calc(100vw-7rem)`
// without spaces around the minus is INVALID CSS, which a browser drops
// silently — leaving `max-width` unset and the bug exactly where it was, under a
// diff that reads like a fix. Verified from the built stylesheet rather than
// assumed: the class compiles to
//     max-width:min(24rem,calc(100vw - 7rem))
// so this guard asserts the operator has its spaces.
//
// ── WHY A SOURCE SCAN ────────────────────────────────────────────────────────
//
// jsdom does not lay out, so it reports this card as fine both before and after
// the fix — a test that passes on the broken code is worse than none. The rule
// is stated over the class list, and the POSITIVE CONTROL below proves the
// predicate really does fire on the markup that shipped. The layout claim itself
// is carried by the probe, which was run against production before the fix and
// returned exit 1.
//
// ── WHAT THIS GUARD DELIBERATELY DOES NOT COVER ──────────────────────────────
//
// The same card also runs off the BOTTOM of the viewport on the inline chart
// (measured 27–79px on 4 of 5 positions). That is a SEPARATE and PRE-EXISTING
// defect — it measures the same in the before-tree — and it is filed on its own,
// not folded in here. A 444px-tall card pinned at the plot's top does not fit an
// 844px phone, and narrowing the card does not change that.
//
// The sibling `ScoreDifferentialChart` tooltip is NOT this bug and is
// deliberately untouched: measured in the same probe run on the same page, its
// card is 110–187px, well inside the same container, 0 of 5 positions clipped.
// Its `max-w-xs` never binds for the same reason this one's `max-w-sm` did —
// content size — only with the opposite outcome. Widening the fix to it would
// have been a change with no defect under it.

import { readFileSync } from "fs";
import { join } from "path";

const ODDS_CHART = join(process.cwd(), "components/OddsChart.tsx");

/**
 * The tooltip card: the root <div> returned by `CustomTooltip`. Located by the
 * component and then by the card's own styling, rather than by a line number,
 * so ordinary edits elsewhere in a 2,600-line file cannot slide the guard onto
 * some other element and keep passing.
 */
function tooltipCardClasses(source: string): string {
  const component = source.indexOf("const CustomTooltip");
  expect(component).toBeGreaterThan(-1);
  const card = source.indexOf("bg-surface-card p-3 rounded-lg shadow-lg", component);
  expect(card).toBeGreaterThan(-1);
  // The className string literal the card is rendered with.
  const quoteEnd = source.indexOf('"', card);
  expect(quoteEnd).toBeGreaterThan(-1);
  const quoteStart = source.lastIndexOf('"', card);
  return source.slice(quoteStart + 1, quoteEnd);
}

/**
 * THE RULE. The cap has to be measured against the VIEWPORT, because the thing
 * it must not exceed is the screen — not the chart, which is what the card grew
 * to when the cap was a fixed width.
 */
function capIsViewportRelative(classes: string): boolean {
  const m = classes.match(/max-w-\[([^\]]+)\]/);
  if (!m) return false;
  return m[1].includes("100vw");
}

/**
 * The silent-failure mode: a `calc()` whose operator has no spaces is invalid
 * CSS and is dropped, so the cap disappears without any visible sign.
 */
function calcOperatorIsSpaced(classes: string): boolean {
  const calls = classes.match(/calc\([^)]*\)/g) ?? [];
  if (calls.length === 0) return true; // no calc() to get wrong
  // Tailwind's `_` becomes a space; a bare `-` between two terms does not.
  return calls.every((c) => !/[\dA-Za-z%)]-[\d.]/.test(c.replace(/_/g, " ")));
}

describe("#1833 the win-probability tooltip stays on the phone screen", () => {
  const source = readFileSync(ODDS_CHART, "utf8");

  it("caps the tooltip card against the viewport, not against a fixed width", () => {
    const classes = tooltipCardClasses(source);
    expect(capIsViewportRelative(classes)).toBe(true);
  });

  it("writes the calc() operator with spaces, so the cap is valid CSS", () => {
    const classes = tooltipCardClasses(source);
    expect(calcOperatorIsSpaced(classes)).toBe(true);
  });

  it("leaves the desktop card at its original width", () => {
    // The cap must be a `min()` with the old 24rem in it: a bare viewport
    // expression would shrink the desktop tooltip too, which no defect asked for.
    const classes = tooltipCardClasses(source);
    const m = classes.match(/max-w-\[([^\]]+)\]/);
    expect(m).not.toBeNull();
    expect(m![1]).toContain("24rem");
    expect(m![1]).toMatch(/^min\(/);
  });

  // ── POSITIVE CONTROLS ──────────────────────────────────────────────────────
  // Without these, every assertion above would also pass on a predicate that
  // can never fail.

  it("POSITIVE CONTROL: the predicate rejects the markup that actually shipped", () => {
    const shipped = "bg-surface-card p-3 rounded-lg shadow-lg border border-surface-border max-w-sm";
    expect(capIsViewportRelative(shipped)).toBe(false);
  });

  it("POSITIVE CONTROL: the predicate rejects an unspaced calc(), the silent no-op", () => {
    const unspaced = "max-w-[min(24rem,calc(100vw-7rem))]";
    expect(calcOperatorIsSpaced(unspaced)).toBe(false);
    // ...and accepts the form that compiles to valid CSS.
    expect(calcOperatorIsSpaced("max-w-[min(24rem,calc(100vw_-_7rem))]")).toBe(true);
  });
});
