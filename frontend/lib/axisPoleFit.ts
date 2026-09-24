import type { CSSProperties } from "react";

/**
 * #8392 — how much of the chart's side gutter each team name may use.
 *
 * The Win Probability and Score Differential charts print the two team names
 * sideways in a 28px gutter, one at the top and one at the bottom. Nothing
 * limited their length, so two long names ran into each other, and on Score
 * Differential (a 192px chart) the lower one was pushed off the bottom:
 * "Borussia Mönchengladbach / Union Berlin" overlapped by 17px on one chart and
 * overflowed by 12px on the other. #5634 made long names more common on
 * purpose — a club keeps its whole name ("Union Berlin", not "Berlin") — so the
 * axis has to make room for them rather than the name rule shortening them.
 *
 * The rule, in the order a reader would want it:
 *
 *  1. Both names fit: nothing changes.
 *  2. One name fits in half the gutter: it is printed whole, and the other takes
 *     every pixel that is left. A fixed half-and-half split was tried and
 *     clipped "Union Berlin" on Score Differential for no reason — its opponent
 *     "FC Köln" needed a third of the space, not half.
 *  3. Neither fits in half: each gets half.
 *
 * A name that does not get all it needs ends in an ellipsis (the chart does
 * that with CSS); the full name stays in the screen-reader sentence and the
 * label's `title`.
 *
 * Lengths are in pixels along the gutter. `null` means "no limit".
 */
export interface AxisPoleCaps {
  home: number | null;
  away: number | null;
}

/**
 * The space kept clear between the two names, so they never touch. Small on
 * purpose: it is also the threshold for "fits", and a larger one would clip
 * pairs that fit today with a few pixels between them into "UNION BERLI…".
 */
export const AXIS_POLE_MIN_GAP_PX = 4;

export function allocateAxisPoles(
  available: number,
  homeNeed: number,
  awayNeed: number,
  minGap: number = AXIS_POLE_MIN_GAP_PX,
): AxisPoleCaps {
  // A gutter that has not been laid out yet (0 tall) or a label we could not
  // measure says nothing about fit — leave both names alone rather than
  // collapse them to nothing.
  if (!(available > 0) || !(homeNeed >= 0) || !(awayNeed >= 0)) {
    return { home: null, away: null };
  }
  if (homeNeed + awayNeed + minGap <= available) {
    return { home: null, away: null };
  }
  const room = Math.max(0, available - minGap);
  const half = Math.floor(room / 2);
  if (homeNeed <= half) return { home: null, away: Math.floor(room - homeNeed) };
  if (awayNeed <= half) return { home: Math.floor(room - awayNeed), away: null };
  return { home: half, away: half };
}

/**
 * The pole's style: the sideways writing both charts have always used, plus the
 * cap when there is one. A capped pole may shrink below its content (flex items
 * otherwise refuse to) and clips what does not fit.
 */
export function axisPoleStyle(cap: number | null): CSSProperties {
  const base: CSSProperties = { writingMode: "vertical-rl", transform: "rotate(180deg)" };
  if (cap === null) return base;
  return { ...base, maxHeight: cap, minHeight: 0, overflow: "hidden" };
}

/**
 * The name's style. Always ONE line: before #8392 a squeezed pole shrank to its
 * longest word and the name WRAPPED into a second sideways column, so
 * "Barracas Central" printed as two stacked words and ran into "Independiente"
 * (production, /events/15306110, 390px). One line is also what makes the name's
 * `scrollHeight` its full length, which the measurement reads. A name that fits
 * was never wrapped, so for it `nowrap` changes nothing.
 *
 * Inside a capped pole the name gives up length before the crest does and ends
 * in an ellipsis rather than a hard cut.
 */
export function axisLabelStyle(cap: number | null): CSSProperties {
  if (cap === null) return { whiteSpace: "nowrap" };
  return { whiteSpace: "nowrap", minHeight: 0, overflow: "hidden", textOverflow: "ellipsis" };
}

/** The few layout reads the measurement needs — an `HTMLElement` has them all. */
export interface AxisLayoutNode {
  offsetHeight: number;
  scrollHeight: number;
  querySelector(selector: string): AxisLayoutNode | null;
}

export interface AxisGutterNode {
  clientHeight: number;
  children: ArrayLike<AxisLayoutNode>;
}

/**
 * One pole's natural length along the gutter: everything in it that is not the
 * name (the crest and the gap), plus the name's FULL length. `scrollHeight` is
 * the name's content length whether or not a cap is clipping it, so this reads
 * the same before and after the cap is applied and the hook settles in one pass.
 */
export function axisPoleNeed(pole: AxisLayoutNode | undefined): number {
  const label = pole?.querySelector("[data-axis-label]");
  if (!pole || !label) return NaN;
  return pole.offsetHeight - label.offsetHeight + label.scrollHeight;
}

/**
 * Reads a laid-out gutter (first child = home pole, second = away) and returns
 * the caps. `paddingTop`/`paddingBottom` are the gutter's computed padding.
 */
export function readAxisPoleCaps(
  gutter: AxisGutterNode,
  paddingTop: number,
  paddingBottom: number,
): AxisPoleCaps {
  const available = gutter.clientHeight - (paddingTop || 0) - (paddingBottom || 0);
  return allocateAxisPoles(available, axisPoleNeed(gutter.children[0]), axisPoleNeed(gutter.children[1]));
}
