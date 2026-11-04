/**
 * WHERE DOES A CHART SAY "NO NUMBERS HERE", AND IN WHAT WORDS?
 *
 * #11929 cause C — Alex, 2026-11-03: "The 2-hour gaps carry a label — the event
 * chart already prints 'No numbers for 37 hours in this stretch'; the futures
 * chart uses the same component instead of a dashed line that implies movement."
 *
 * #3659 broke a line at every hole and spanned the hole with a faint dotted
 * bridge, so the plot would not read as a chart that failed to render. #11929 B
 * made that bridge a hold-then-riser. Either way it is a stroke between two real
 * observations, and a stroke is what a reader reads as movement. Production
 * 2026-11-04, after B: `/futures/65536371` (Denver December snow) drew 5 dotted
 * connectors across 15–60 h holes; the capture-only US Open board (34277822)
 * drew 33.
 *
 * So a full chart draws nothing across a hole, and the hole is named instead —
 * in the caption's own sentence (`gapNote`, `lib/seriesFreshness.ts`), sized by
 * the same round-up rule, from the same threshold that broke the line
 * (`chartSeriesPath`'s `holes`). Line, caption and label cannot disagree about
 * which interval is a hole or how long it was.
 *
 * ═══ ONE LABEL PER STRETCH, NOT PER LINE ═══
 *
 * A board's outcomes are polled together, so their holes coincide: on the US
 * Open board eight of ten lines share the same 156 h hole. Eight copies of one
 * sentence is noise, so holes whose intervals are the same stretch (overlap of
 * at least `SAME_STRETCH_OVERLAP` of their union) carry ONE label, sized by the
 * longest of them — a confessed hole rounds up, never down (#7491).
 *
 * ═══ LONGEST FIRST, AND NEVER ON TOP OF ANOTHER ═══
 *
 * The sentence is ~250 viewBox units wide and a hole on a week-long window can
 * be 70. Labels are placed longest-hole first, each centred on its stretch (and
 * inside its own hole — see below), above the lines it explains, then below them, then in
 * the plot's top and bottom bands; a label that fits nowhere without touching
 * one already placed is left out. The line still breaks there, and the caption
 * under the plot still names the largest hole, so nothing is left unconfessed —
 * but a plot papered in overlapping sentences would be a worse chart than the
 * dotted one it replaced.
 *
 * A hole drawn narrower than `MIN_LABELLED_HOLE_SHARE` of the plot is a hairline
 * break — on the US Open board's 44-day window a 7 h hole is 5 units of 730 —
 * and a 250-unit sentence centred on it points at nothing a reader can find. It
 * stays a break in the line, unlabelled.
 *
 * ═══ A LABEL SITS INSIDE ITS OWN HOLE, OR NOT AT ALL ═══
 *
 * Production 2026-11-04, 390 px, after C shipped: Denver December snow's 3-day
 * hole at the right edge was narrower than its sentence, so centring-then-
 * clamping slid "No numbers for 3 days in this stretch" left over a week of
 * real readings, and on 108629 a label was clamped onto the y-axis. A sentence
 * that says "no numbers" over numbers is a false statement. So a label is
 * placed only where its whole width fits between the hole's two bracketing
 * observations; a hole too narrow for its sentence keeps B's faint
 * hold-then-riser bridge (`holeIsLabelled` tells the chart which), so no hole
 * is ever left unexplained and no label ever covers data.
 *
 * Pure and total, like the two modules it reads: no clock, no DOM, every input
 * produces an answer, because the caller is a render path.
 */

import { gapNote } from "@/lib/seriesFreshness";
import type { ChartHole } from "@/lib/chartSeriesPath";

/** The plot rectangle, in viewBox units. */
export interface GapLabelFrame {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface GapLabel {
  /** The caption's sentence for this hole — `gapNote`. */
  text: string;
  /** Centre of the text (`text-anchor="middle"`) and its baseline. */
  x: number;
  y: number;
  /** The stretch it names: real instants and pixels of the bracketing observations. */
  fromT: number;
  toT: number;
  fromX: number;
  toX: number;
  /** The hole's length — the longest of the coinciding holes it stands for. */
  ms: number;
}

/**
 * `text-xs` (12px) is 12 viewBox units on a chart whose viewBox is 800 wide.
 * The width is an estimate — SSR has no font metrics — taken generously so two
 * labels judged apart are apart on any sans the reader's device draws.
 */
const CHAR_UNITS = 6.4;
/** Ascender above the baseline and descender below it, for collision boxes. */
const ASCENT_UNITS = 10;
const DESCENT_UNITS = 3;
/** Air between two labels, and between a label and the line it sits over. */
const LABEL_GAP_UNITS = 3;
const ABOVE_LINE_UNITS = 5;

/** A hole drawn narrower than this share of the plot's width is not labelled. */
export const MIN_LABELLED_HOLE_SHARE = 0.01;

/** Two holes are one stretch when they overlap by at least this share of their union. */
export const SAME_STRETCH_OVERLAP = 0.9;

/**
 * Every displayed line, as the chart plots it: its points and its own holes.
 * Fable's read at 9ee16863: a label that fits inside ONE line's hole can still
 * sit over ANOTHER line's readings when the lines' holes differ (the
 * capture-only US Open board 34277822 is the normal case), and its halo would
 * hide them under "No numbers…". So a candidate box is also refused when it
 * touches any drawn point or segment of any line.
 */
export interface GapLabelLine {
  points: readonly { t: number; x: number; y: number }[];
  holes: readonly ChartHole[];
}

/**
 * Does this box touch anything a line draws? A point inside it, or a segment
 * between consecutive points whose bounding box meets it. The bounding box
 * covers both linear and step drawing, so it errs toward refusing. A pair that
 * is one of the line's own holes draws no solid segment and is skipped; if that
 * hole is unlabelled its faint bridge may pass under the label, which is the
 * hole the label names, so it is not a reading.
 */
function coversADrawnReading(box: Box, lines: readonly GapLabelLine[]): boolean {
  for (const line of lines) {
    const holeStarts = new Set(line.holes.map((h) => h.from.t));
    const pts = line.points;
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      if (p.x > box.x0 && p.x < box.x1 && p.y > box.y0 && p.y < box.y1) return true;
      if (i === 0) continue;
      const a = pts[i - 1];
      if (holeStarts.has(a.t)) continue;
      const sx0 = Math.min(a.x, p.x);
      const sx1 = Math.max(a.x, p.x);
      const sy0 = Math.min(a.y, p.y);
      const sy1 = Math.max(a.y, p.y);
      if (sx0 < box.x1 && box.x0 < sx1 && sy0 <= box.y1 && box.y0 <= sy1) return true;
    }
  }
  return false;
}

export function gapLabelWidth(text: string): number {
  return text.length * CHAR_UNITS;
}

interface Stretch {
  fromT: number;
  toT: number;
  fromX: number;
  toX: number;
  minY: number;
  maxY: number;
  ms: number;
}

interface Box {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

function overlapShare(a: Stretch, fromT: number, toT: number): number {
  const inter = Math.min(a.toT, toT) - Math.max(a.fromT, fromT);
  const union = Math.max(a.toT, toT) - Math.min(a.fromT, fromT);
  return union > 0 && inter > 0 ? inter / union : 0;
}

function clamp(v: number, lo: number, hi: number): number {
  return lo > hi ? (lo + hi) / 2 : Math.min(hi, Math.max(lo, v));
}

/**
 * The labels a full chart prints over its holes, in time order.
 *
 * `holes` are every displayed line's holes, straight from `chartSeriesPath` —
 * the caller does not filter or re-derive them.
 */
export function placeGapLabels(
  holes: readonly ChartHole[],
  frame: GapLabelFrame,
  lines: readonly GapLabelLine[] = [],
): GapLabel[] {
  const usable = holes.filter(
    (h) =>
      Number.isFinite(h.from.t) &&
      Number.isFinite(h.to.t) &&
      Number.isFinite(h.from.x) &&
      Number.isFinite(h.to.x) &&
      Number.isFinite(h.from.y) &&
      Number.isFinite(h.to.y) &&
      h.to.t > h.from.t,
  );
  if (usable.length === 0) return [];

  // Longest first, so a stretch's first member is its longest and the
  // placement below hands the scarce room to the biggest confession.
  const ordered = [...usable].sort(
    (a, b) => b.to.t - b.from.t - (a.to.t - a.from.t) || a.from.t - b.from.t,
  );

  const stretches: Stretch[] = [];
  for (const h of ordered) {
    const same = stretches.find(
      (s) => overlapShare(s, h.from.t, h.to.t) >= SAME_STRETCH_OVERLAP,
    );
    const yLo = Math.min(h.from.y, h.to.y);
    const yHi = Math.max(h.from.y, h.to.y);
    if (same) {
      same.minY = Math.min(same.minY, yLo);
      same.maxY = Math.max(same.maxY, yHi);
      continue;
    }
    stretches.push({
      fromT: h.from.t,
      toT: h.to.t,
      fromX: h.from.x,
      toX: h.to.x,
      minY: yLo,
      maxY: yHi,
      ms: h.to.t - h.from.t,
    });
  }

  const placed: { label: GapLabel; box: Box }[] = [];
  const baselineLo = frame.top + ASCENT_UNITS;
  const baselineHi = frame.bottom - DESCENT_UNITS;
  const minHoleWidth = (frame.right - frame.left) * MIN_LABELLED_HOLE_SHARE;

  for (const s of stretches) {
    if (!(s.toX - s.fromX >= minHoleWidth)) continue;
    const text = gapNote(s.ms);
    const w = gapLabelWidth(text);
    // Inside its own hole or not at all: never slid over real readings.
    if (w + 2 * LABEL_GAP_UNITS > s.toX - s.fromX) continue;
    const x = (s.fromX + s.toX) / 2;
    const candidates = [
      s.minY - ABOVE_LINE_UNITS,
      s.maxY + ABOVE_LINE_UNITS + ASCENT_UNITS,
      baselineLo,
      baselineHi,
    ].map((y) => clamp(y, baselineLo, baselineHi));

    for (const y of candidates) {
      const box: Box = {
        x0: x - w / 2 - LABEL_GAP_UNITS,
        x1: x + w / 2 + LABEL_GAP_UNITS,
        y0: y - ASCENT_UNITS - LABEL_GAP_UNITS,
        y1: y + DESCENT_UNITS + LABEL_GAP_UNITS,
      };
      const collides =
        placed.some(
          (p) => box.x0 < p.box.x1 && p.box.x0 < box.x1 && box.y0 < p.box.y1 && p.box.y0 < box.y1,
        ) || coversADrawnReading(box, lines);
      if (collides) continue;
      placed.push({
        label: {
          text,
          x,
          y,
          fromT: s.fromT,
          toT: s.toT,
          fromX: s.fromX,
          toX: s.toX,
          ms: s.ms,
        },
        box,
      });
      break;
    }
  }

  return placed.map((p) => p.label).sort((a, b) => a.fromT - b.fromT);
}

/**
 * Does a placed label stand for this hole? The same "one stretch" test that
 * grouped the holes, so a hole sharing a labelled stretch is covered by it. A
 * hole no label stands for keeps its faint bridge (`FuturesChart`).
 */
export function holeIsLabelled(hole: ChartHole, labels: readonly GapLabel[]): boolean {
  const from = hole.from.t;
  const to = hole.to.t;
  return labels.some((l) => {
    const inter = Math.min(l.toT, to) - Math.max(l.fromT, from);
    const union = Math.max(l.toT, to) - Math.min(l.fromT, from);
    return union > 0 && inter > 0 && inter / union >= SAME_STRETCH_OVERLAP;
  });
}
