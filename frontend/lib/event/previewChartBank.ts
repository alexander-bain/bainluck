import type { LiveChartFrame } from "../liveChartHistory";

/**
 * #10090 (Alex 2026-11-01) — every number the headline SHOWED stays on the line.
 *
 * "Can't we save all the updates we've been receiving ... so we'd end up with
 * the same total number of chart points, with the right timestamps?" The
 * headline moves on each receipt preview (about once a second on a live NFL
 * game); the line only gained a point per committed frame (about one in eight
 * seconds), and the preview drawn at its end (`overlayBlendPreviewLine`) was
 * replaced by the next one, so every superseded preview left the line.
 *
 * This keeps each displayed preview at its own observation time, for this page
 * session. Only SUPERSEDED values are handed to the chart: the current preview
 * is still drawn by `overlayBlendPreviewLine` exactly as before, and with no
 * preview up only values older than the newest committed observation are, so
 * the line never ends on a number the headline has stopped showing.
 */
export const MAX_PREVIEW_CHART_POINTS = 5000;

export type PreviewChartBank = { eventId: number; points: LiveChartFrame[] };

/** The bank with the headline's displayed preview added (same object when nothing changes). */
export function rememberPreviewPoint(
  bank: PreviewChartBank | null, eventId: number, p: number | null, observedAt: string | undefined,
): PreviewChartBank {
  const current = bank?.eventId === eventId ? bank : { eventId, points: [] };
  if (p === null || !Number.isFinite(p) || p < 0 || p > 1 || !observedAt) return current;
  const at = Date.parse(observedAt);
  if (!Number.isFinite(at)) return current;
  const points = current.points;
  const last = points[points.length - 1];
  if (last && last.home_probability === p && Date.parse(last.timestamp) <= at) return current;
  const next = points.filter(point => Date.parse(point.timestamp) !== at);
  next.push({ timestamp: observedAt, home_probability: p });
  if (last && Date.parse(last.timestamp) > at) {
    next.sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
  }
  return { eventId, points: next.slice(-MAX_PREVIEW_CHART_POINTS) };
}

/**
 * The kept values the chart may draw. With a preview on screen (`currentAt`):
 * those older than it, since that preview is the line's end. With none on
 * screen: those older than the newest committed observation (`committedAt`, or
 * a committed frame), so the line never ends on a value the headline has
 * stopped showing. Instants already held by `frames` are left to them.
 */
export function supersededPreviewPoints(
  bank: PreviewChartBank | null, eventId: number, currentAt: string | undefined,
  frames: LiveChartFrame[] = [], committedAt?: string | null,
): LiveChartFrame[] {
  if (!bank || bank.eventId !== eventId || bank.points.length === 0) return [];
  let limit = currentAt ? Date.parse(currentAt) : NaN;
  if (!Number.isFinite(limit)) {
    limit = committedAt ? Date.parse(committedAt) : NaN;
    for (const frame of frames) {
      const t = Date.parse(frame.timestamp);
      if (Number.isFinite(t) && !(t <= limit)) limit = t;
    }
    if (!Number.isFinite(limit)) return [];
  }
  const held = new Set(frames.map(frame => Date.parse(frame.timestamp)));
  return bank.points.filter(point => {
    const t = Date.parse(point.timestamp);
    return t < limit && !held.has(t);
  });
}
