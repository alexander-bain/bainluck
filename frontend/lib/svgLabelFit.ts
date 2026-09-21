/**
 * svgLabelFit — where to put a one-line SVG label so the reader sees ALL of it.
 *
 * SVG text does not wrap, does not shrink and is not clipped gracefully: a label
 * anchored past the canvas edge simply loses its first glyphs, and the reader has
 * no way to tell a cut-off word from a typo. #7748 was exactly that — the /about
 * Alcaraz chart annotated its lowest point with "Adductor injury — 14%, the brink"
 * anchored `end`, so 16.7 user units hung off the left of a 320-unit viewBox and
 * the App Store reviewer's About screen read "ductor injury".
 *
 * The placement decision needs the label's rendered width, which a server-rendered
 * SVG cannot measure (no DOM, no canvas). So we estimate it from a per-character
 * table, deliberately biased to OVER-estimate: over-estimating moves a label inward
 * a few units, under-estimating puts it back off the edge.
 *
 * The table is calibrated against Chrome's own `getBBox()` on production, with the
 * shipped font stack (Inter 600) at the size the charts use — see
 * `__tests__/lib/svgLabelFit.test.ts`, which holds the measured widths as the
 * control and fails if the estimate ever drops below one of them.
 */

/** Glyphs materially wider than the lowercase average. */
const WIDE = new Set("mwMW%@—–×→~".split(""));
/** Glyphs materially narrower than the lowercase average. */
const NARROW = new Set("iljtfI.,;:'`!|()[]{}/\\-·".split(""));

const EM_WIDE = 0.95;
const EM_NARROW = 0.36;
const EM_SPACE = 0.28;
const EM_UPPER = 0.72;
const EM_DIGIT = 0.65;
const EM_DEFAULT = 0.58;

/**
 * Safety factor on the estimate. The table lands within ~2.5% of Chrome on the
 * shipped labels; this keeps the estimate on the safe (wider) side of every one.
 */
const SAFETY = 1.05;

/** Approximate rendered width, in user units, of `text` at `fontSize`. Never exact. */
export function estimateSvgTextWidth(text: string, fontSize: number): number {
  let em = 0;
  for (const ch of text) {
    if (ch === " " || ch === " ") em += EM_SPACE;
    else if (WIDE.has(ch)) em += EM_WIDE;
    else if (NARROW.has(ch)) em += EM_NARROW;
    else if (ch >= "0" && ch <= "9") em += EM_DIGIT;
    else if (ch >= "A" && ch <= "Z") em += EM_UPPER;
    else em += EM_DEFAULT;
  }
  return em * fontSize * SAFETY;
}

export interface LabelPlacement {
  /** The `x` attribute for the `<text>`. */
  x: number;
  /** The `text-anchor` that goes with it. */
  anchor: "start" | "middle" | "end";
}

/**
 * Place a label beside the point at `anchorX`, keeping its whole box inside
 * `[left, right]`.
 *
 * Preferred side is unchanged from the original heuristic — a point in the right
 * half is labelled leftward — but the side is only taken if the label FITS there.
 * If neither side fits, the label is centred on its point and clamped into the
 * plot area, which is the only placement that stays both readable and attached.
 */
export function placeLabel({
  anchorX,
  label,
  fontSize,
  gap,
  left,
  right,
  preferLeft = anchorX > (left + right) / 2,
}: {
  anchorX: number;
  label: string;
  fontSize: number;
  gap: number;
  left: number;
  right: number;
  preferLeft?: boolean;
}): LabelPlacement {
  const w = estimateSvgTextWidth(label, fontSize);
  const fitsLeft = anchorX - gap - w >= left;
  const fitsRight = anchorX + gap + w <= right;

  if (preferLeft ? fitsLeft : fitsRight) {
    return preferLeft
      ? { x: anchorX - gap, anchor: "end" }
      : { x: anchorX + gap, anchor: "start" };
  }
  if (preferLeft ? fitsRight : fitsLeft) {
    return preferLeft
      ? { x: anchorX + gap, anchor: "start" }
      : { x: anchorX - gap, anchor: "end" };
  }

  // Neither side has room. Centre on the point, clamped so the box stays inside —
  // and if the label is wider than the plot itself, centre it in the plot so what
  // spills is split evenly rather than losing a whole word off one edge.
  const lo = left + w / 2;
  const hi = right - w / 2;
  const x = lo > hi ? (left + right) / 2 : Math.min(Math.max(anchorX, lo), hi);
  return { x, anchor: "middle" };
}
