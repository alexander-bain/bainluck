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
  /** #10156 — which text the label is showing (the name or its code). */
  textContent?: string | null;
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

/**
 * #10156 — the two served team codes, when they are fit to stand in for the
 * names on the axis: each 2–4 capitals/digits (the chip shape #10124 uses for
 * the props filter, which keeps out the long college names some rows store in
 * that field) and different from each other. Otherwise `null`.
 */
export function axisCodePair(
  homeCode?: string | null,
  awayCode?: string | null,
): { home: string; away: string } | null {
  const chip = (code?: string | null) => {
    const c = (code ?? "").trim();
    return /^[A-Z0-9]{2,4}$/.test(c) ? c : "";
  };
  const home = chip(homeCode);
  const away = chip(awayCode);
  return home !== "" && away !== "" && home !== away ? { home, away } : null;
}

/** A pole's full-name length, remembered while its code is on screen instead. */
export interface AxisPoleNeedCache {
  home?: { label: string; need: number };
  away?: { label: string; need: number };
}

/**
 * #10156 — #8392's rule, with one step before the ellipsis: when either NAME
 * would be cut and the event serves a usable code pair, BOTH poles print their
 * codes. On the 192px Score Differential chart "Golden Hurricane / Mean Green"
 * read "GOLDEN … / MEAN G…" (/events/15319855, 390px) while the margin maps on
 * the same page said TLSA / UNT. Both codes, never one: a code beside a whole
 * name reads as two different kinds of label.
 *
 * A name's length does not depend on the gutter, so it is remembered (`cache`)
 * from the frame that drew it. Without that, the frame drawing the codes would
 * measure the codes, find they fit, put the names back, find they don't, and
 * flip forever. A resize re-decides from the remembered lengths, so a gutter
 * that grows enough brings the names back.
 *
 * Names that fit, or no usable code pair: exactly `readAxisPoleCaps`.
 */
export function readAxisPoleLayout(
  gutter: AxisGutterNode,
  paddingTop: number,
  paddingBottom: number,
  labels: { home: string; away: string },
  codes: { home: string; away: string } | null,
  cache: AxisPoleNeedCache,
): { useCodes: boolean; caps: AxisPoleCaps } {
  const available = gutter.clientHeight - (paddingTop || 0) - (paddingBottom || 0);
  const poles = [gutter.children[0], gutter.children[1]] as const;
  const shown = poles.map((p) => p?.querySelector("[data-axis-label]")?.textContent ?? null);
  (["home", "away"] as const).forEach((side, i) => {
    if (shown[i] === labels[side]) cache[side] = { label: labels[side], need: axisPoleNeed(poles[i]) };
  });
  const fullNeed = (side: "home" | "away") =>
    cache[side]?.label === labels[side] ? (cache[side]?.need ?? NaN) : NaN;
  const fullCaps = allocateAxisPoles(available, fullNeed("home"), fullNeed("away"));
  if (codes === null || (fullCaps.home === null && fullCaps.away === null)) {
    return { useCodes: false, caps: fullCaps };
  }
  const showingCodes = shown[0] === codes.home && shown[1] === codes.away;
  return {
    useCodes: true,
    caps: showingCodes ? allocateAxisPoles(available, axisPoleNeed(poles[0]), axisPoleNeed(poles[1])) : fullCaps,
  };
}
