// #3035 — WHICH END OF A TIME SERIES A PHONE RESTS ON.
//
// The non-mini FuturesChart plot is `min-w-[600px]` inside an `overflow-x-auto`
// card. At a 390px phone width roughly a third of the plot sits outside the
// scroll window, and a scroll container's resting position is its LEFT edge —
// which, for a time series, is the OLDEST data. A reader opening the US Open
// title race saw last week; on the "All" range the entire tournament was
// off-screen while the visible ticks read Jan 2 · Mar 4 · May 4.
//
// Compressing instead (dropping the 600px minimum and letting the plot shrink
// to the viewport) is not an option: the axis labels are 9px inside an 800-unit
// viewBox, so a 390px render would draw them at ~4px.
//
// So the plot still scrolls — it just rests on `now`, and says that it scrolls.
// Both halves live here as pure arithmetic because the repo's jest environment
// is `node` with no DOM (see `lib/chartZoom.ts` for the same split), so the
// component reads element metrics and these functions decide what they mean.

export interface ScrollMetrics {
  scrollLeft: number;
  scrollWidth: number;
  clientWidth: number;
}

/**
 * A fade is suppressed within this many px of a true edge. Fractional layout
 * widths leave sub-pixel slack at the end of a scroll, which without a
 * tolerance strands a fade that is scrolled hard against its edge and never
 * fully fades out.
 */
export const EDGE_TOLERANCE_PX = 1;

/**
 * How far this plot CAN be scrolled — pure geometry, no editorial. Clamped at 0
 * so a plot that does not overflow (desktop, or a short domain) is never handed
 * a negative offset.
 *
 * #6548 split this out of `anchorScrollLeft`. The two were one function only
 * because the resting anchor happened to BE the maximum offset; `edgeOverflowFor`
 * was already calling the anchor to mean "max scroll". The moment the anchor
 * became conditional, that shared call would have made a settled chart compute
 * its fades against 0 and report no right-hand overflow on a plot that has a
 * screen and a half of it.
 */
export function maxScrollLeft(
  metrics: Pick<ScrollMetrics, "scrollWidth" | "clientWidth">,
): number {
  return Math.max(0, metrics.scrollWidth - metrics.clientWidth);
}

/**
 * The resting scroll offset for a time-series plot.
 *
 * LIVE (#3035): the RIGHT edge — the news on a running race is the newest point,
 * and a reader who opened the US Open title race landed on January.
 *
 * SETTLED (#6548): the LEFT edge. #3035's premise inverts once a question is
 * decided — the right edge is then a flat run to the resolution and the race
 * itself is behind the left edge. Measured on `/futures/110141` (South Dakota
 * GOP governor, resolved 7/28): at 390px the phone rested on Jun 18 → Sep 16,
 * a single blue line already at 100%, while the whole contest — Dusty Johnson
 * leading ~50-70% from Mar 20 and the June crossover that decided it — sat
 * off-screen left. The legend still drew his red key, pointing at no line.
 */
export function anchorScrollLeft(
  metrics: Pick<ScrollMetrics, "scrollWidth" | "clientWidth">,
  opts?: { settled?: boolean; movement?: readonly MovementMark[] },
): number {
  if (!opts?.settled) return maxScrollLeft(metrics);
  // #9867: "the race is behind the left edge" was a property of #6548's
  // specimen, not of settled boards. `/futures/60770199` (a halftime result)
  // has one reading on Sep 17, six empty days, then its whole race Sep 23–25 —
  // resting on the left showed the empty gap and hid the winner's climb to
  // 100% behind the RIGHT edge. So a settled chart rests where its lines
  // actually moved; with nothing to go on it falls back to #6548's left edge.
  const max = maxScrollLeft(metrics);
  if (max === 0 || !opts.movement) return 0;
  const start = restingWindowStart(opts.movement, metrics.clientWidth / metrics.scrollWidth);
  return Math.min(max, Math.max(0, start * metrics.scrollWidth));
}

/**
 * One unit of movement on the plot: `weight` is a line's |Δprobability|
 * between two consecutive readings, placed at the later reading's
 * horizontal position `at`, as a fraction (0–1) of the full plot width.
 */
export interface MovementMark {
  at: number;
  weight: number;
}

/**
 * #9867 — where a window `windowFraction` wide (a fraction of the full plot
 * width) should start so it holds the most movement. It is then CENTRED on the
 * span of the marks it holds, so the race does not sit hard against an edge
 * with the end-of-domain date label clipped beside it. Returns 0 (#6548's left
 * edge) when there is no movement, or when the window holds the whole plot.
 */
export function restingWindowStart(
  marks: readonly MovementMark[],
  windowFraction: number,
): number {
  const room = 1 - windowFraction;
  if (!(room > 0)) return 0;
  const sorted = marks
    .filter((m) => m.weight > 0 && Number.isFinite(m.at))
    .slice()
    .sort((a, b) => a.at - b.at);
  if (sorted.length === 0) return 0;

  const prefix = [0];
  for (const m of sorted) prefix.push(prefix[prefix.length - 1] + m.weight);
  // First index whose `at` is > x (upper) or >= x (lower).
  const bound = (x: number, upper: boolean) => {
    let lo = 0;
    let hi = sorted.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (upper ? sorted[mid].at <= x : sorted[mid].at < x) lo = mid + 1;
      else hi = mid;
    }
    return lo;
  };
  const clamp = (s: number) => Math.min(room, Math.max(0, s));

  // The best window always has a mark on one of its edges (or sits at an end
  // of the plot), so those are the only starts worth trying. Ties keep the
  // leftmost — #6548's preference when the evidence does not choose.
  const candidates = [0, room];
  for (const m of sorted) candidates.push(clamp(m.at), clamp(m.at - windowFraction));
  candidates.sort((a, b) => a - b);

  let best = { start: 0, mass: -1, first: 0, last: 0 };
  for (const s of candidates) {
    const first = bound(s, false);
    const last = bound(s + windowFraction, true);
    const mass = prefix[last] - prefix[first];
    if (mass > best.mass + 1e-12) best = { start: s, mass, first, last };
  }
  if (best.mass <= 0 || best.last <= best.first) return 0;

  const spanMid = (sorted[best.first].at + sorted[best.last - 1].at) / 2;
  return clamp(spanMid - windowFraction / 2);
}

/**
 * #9867 — the movement marks for a set of drawn series, positioned on a plot
 * whose x axis runs `minTime`→`maxTime` across `[left, width - right]` of a
 * `width`-unit frame (the chart's viewBox and padding).
 */
export function seriesMovementMarks(
  series: readonly { history: readonly { timestamp: string; probability: number | null }[] }[],
  frame: { width: number; left: number; right: number },
): MovementMark[] {
  let minTime = Infinity;
  let maxTime = -Infinity;
  const parsed = series.map((s) =>
    s.history
      .filter((p) => p.probability !== null)
      .map((p) => ({ t: new Date(p.timestamp).getTime(), p: p.probability as number }))
      .filter((p) => Number.isFinite(p.t))
      .sort((a, b) => a.t - b.t),
  );
  for (const pts of parsed) {
    for (const { t } of pts) {
      if (t < minTime) minTime = t;
      if (t > maxTime) maxTime = t;
    }
  }
  if (!(maxTime > minTime)) return [];
  const inner = frame.width - frame.left - frame.right;
  const marks: MovementMark[] = [];
  for (const pts of parsed) {
    for (let i = 1; i < pts.length; i++) {
      const x = frame.left + ((pts[i].t - minTime) / (maxTime - minTime)) * inner;
      marks.push({ at: x / frame.width, weight: Math.abs(pts[i].p - pts[i - 1].p) });
    }
  }
  return marks;
}

/**
 * Which edges still have plot hidden behind them, and therefore which fades to
 * draw. Both false when nothing overflows, so a desktop chart gets no chrome.
 */
export function edgeOverflowFor(metrics: ScrollMetrics): {
  left: boolean;
  right: boolean;
} {
  // `maxScrollLeft`, NOT `anchorScrollLeft` — see the note on the split above.
  const maxScroll = maxScrollLeft(metrics);
  return {
    left: metrics.scrollLeft > EDGE_TOLERANCE_PX,
    right: metrics.scrollLeft < maxScroll - EDGE_TOLERANCE_PX,
  };
}
