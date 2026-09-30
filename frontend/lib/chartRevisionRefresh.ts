import { isQuoteStreamStatus } from "./eventQuoteStream";
import { PINNABLE_HERO_SOURCE } from "./chartEdgePin";
import { compareFoldRevision, parseFoldRevision } from "./foldRevision";
import type { ChartHistory, HeroObservation } from "./liveChartHistory";

type RevisionHero = HeroObservation & { blend_fold_revision?: unknown };
type RevisionHistory = ChartHistory & {
  blend_edge_pinned?: boolean | null;
  blend_edge_fold_revision?: unknown;
};

/**
 * #9051: removing a source can advance membership while leaving an older
 * surviving quote. That quote must not overwrite a real chart observation or
 * acquire an invented time. If the ordinary push/hero composition still ends
 * on another value, request history's authoritative current-state endpoint.
 * Ordinary pushes already extend that composition and request nothing here.
 *
 * Returns a stable revision key, so the page requests once per accepted fold
 * (burst changes are coalesced by its scheduler). An unchanged cached response
 * cannot loop; the existing history poll remains the retry for that case.
 */
export function chartRevisionRefreshKey(
  event: RevisionHero | null | undefined,
  served: RevisionHistory | null | undefined,
  plotted: ChartHistory | null | undefined,
): string | null {
  if (!event || !isQuoteStreamStatus(event.status) || event.hero_probability_source !== PINNABLE_HERO_SOURCE ||
      !served?.blend_edge_pinned) return null;
  const p = event.hero_probability;
  if (typeof p !== "number" || !Number.isFinite(p) || p < 0 || p > 1) return null;
  const heldRevision = parseFoldRevision(event.blend_fold_revision);
  const servedRevision = parseFoldRevision(served.blend_edge_fold_revision);
  if (!heldRevision || !servedRevision) return null;
  const order = compareFoldRevision(heldRevision, servedRevision);
  if (order !== "newer" && order !== "incomparable") return null;
  const line = plotted?.aggregate_line;
  if (!line?.length || !served.aggregate_line?.length) return null;
  let edge = line[0];
  for (const point of line) {
    if (Date.parse(point.timestamp) > Date.parse(edge.timestamp)) edge = point;
  }
  if (!Number.isFinite(Date.parse(edge.timestamp)) || edge.home_probability === p) return null;
  return JSON.stringify(Object.entries(heldRevision).sort(([a], [b]) => a.localeCompare(b)));
}
