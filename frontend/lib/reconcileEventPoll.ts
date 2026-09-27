import { adoptNewerBlendEdge, type BlendEdgeObservation } from './blendObservationClock';
import { applyLiveFrame } from './eventLivePush';
import { compareFoldRevision, frameFoldOrder, parseFoldRevision } from './foldRevision';
import type { LiveStreamFrame } from './liveStreamController';

type PolledEvent = {
  id: number;
  status: string;
  hero_probability?: number | null;
  hero_probability_away?: number | null;
  hero_probability_source?: string;
  hero_probability_observed_at?: string | null;
  win_probability_sources?: Record<string, { updated_at?: string }>;
  blend_fold_revision?: unknown;
};

/**
 * #837/#920: a cached REST response may arrive after a newer pushed price.
 * Keep the REST score/status/metadata, but do not roll the headline back while
 * the chart still contains the newer publication. Only comparable source write
 * times justify preservation; missing clocks, non-live outcomes and equally
 * new REST remain authoritative. Never invent a new observation timestamp.
 * #9051: when the response and the frame both carry fold revisions, commit
 * order decides BEFORE any clock gate (`lib/foldRevision.ts`) — a hero whose
 * observation clock is explicitly unknown still takes a strictly newer write.
 * With no claim on either side the clock gates below apply unchanged.
 */
export function reconcileEventPoll<T extends PolledEvent>(
  polled: T,
  frame: LiveStreamFrame | null,
): T {
  if (!frame || frame.event_id !== polled.id || polled.status !== 'live'
      || polled.hero_probability_source !== 'blend'
      || typeof polled.hero_probability !== 'number'
      || !Number.isFinite(polled.hero_probability)
      || frame.p === null || !Number.isFinite(frame.p) || frame.p < 0 || frame.p > 1) {
    return polled;
  }
  const foldOrder = frameFoldOrder(polled.blend_fold_revision, frame.rev);
  if (foldOrder !== null) return foldOrder === 'newer' ? applyLiveFrame(polled, { ...frame, p: frame.p })! : polled;
  const frameTime = Date.parse(frame.updated_at);
  // #8749: the contract's clock dates the hero itself and counts only the
  // sources it folded; any source's stamp is the fallback for a payload that
  // does not carry one.
  const observed = Date.parse(polled.hero_probability_observed_at ?? '');
  // Explicit null/invalid provenance is not a legacy payload: another source
  // cannot date an admitted unclocked contribution to this whole blend.
  if (polled.hero_probability_observed_at !== undefined && !Number.isFinite(observed)) return polled;
  const sourceTimes = Number.isFinite(observed) ? [observed]
    : Object.values(polled.win_probability_sources ?? {})
      .map(source => Date.parse(source.updated_at ?? ''))
      .filter(Number.isFinite);
  if (!Number.isFinite(frameTime) || sourceTimes.length === 0
      || Math.max(...sourceTimes) >= frameTime) return polled;

  return applyLiveFrame(polled, { ...frame, p: frame.p })!;
}

/**
 * #9051: a completed poll against the headline the page ALREADY accepted.
 *
 * The page's frames and history edges move the cached headline between polls,
 * and the refs the fetcher reads hold only the LATEST frame and edge — a
 * refused old edge replaces an adopted newer one there. So the poll compares
 * against the cache itself: a response whose fold revision is strictly OLDER
 * (same rows, dominated) keeps the held headline, its sources and its revision,
 * and takes everything else — score, status, clock — from the response. A
 * newer, equal or incomparable response is the authoritative read and wins
 * whole; that is how a changed fold (a twin joined or left) is ever adopted.
 *
 * A live-blend response with NO revision (a pre-contract cache entry, or a
 * malformed vector) cannot be ordered against the held one, and a value is
 * never tagged with a revision borrowed from another value (Codex on
 * 64a14a3d8d: that pairing let the next history edge see equal vectors and
 * leave a removed source's .6 standing). So the held blend, its rail and its
 * vector stay together and the REST fields land around them; the next poll is
 * the re-read (an immediate one would hit the same cache entry). A response
 * that ends the game or leaves the live blend wins whole, and a page that holds
 * no revision takes every response as before.
 */
export function keepNewerHeldHeadline<T extends PolledEvent>(polled: T, held: T | undefined): T {
  if (!held || held.id !== polled.id) return polled;
  const heldRevision = parseFoldRevision(held.blend_fold_revision);
  if (!heldRevision) return polled;
  const liveBlend = (e: T) => e.status === 'live' && e.hero_probability_source === 'blend'
    && typeof e.hero_probability === 'number' && Number.isFinite(e.hero_probability);
  if (!liveBlend(polled) || !liveBlend(held)) return polled;
  const polledRevision = parseFoldRevision(polled.blend_fold_revision);
  if (polledRevision && compareFoldRevision(polledRevision, heldRevision) !== 'older') return polled;
  return {
    ...polled,
    hero_probability: held.hero_probability,
    hero_probability_away: polled.hero_probability_away == null ? polled.hero_probability_away : held.hero_probability_away,
    hero_probability_observed_at: held.hero_probability_observed_at,
    win_probability_sources: held.win_probability_sources,
    blend_fold_revision: heldRevision,
  };
}

/**
 * Read the latest frame AFTER the response, including pushes during its flight,
 * then the chart's pinned edge (#8749): a detail cache can serve a hero older
 * than the history the page already drew, and without this every such poll
 * rolled the headline back until the next history response moved it again.
 * #9051: first against the headline the page holds when the response lands.
 */
export async function fetchEventWithLiveFrame<T extends PolledEvent>(
  fetchEvent: () => Promise<T>,
  latestFrame: () => LiveStreamFrame | null,
  latestBlendEdge: () => BlendEdgeObservation | null = () => null,
  heldEvent: () => T | undefined = () => undefined,
): Promise<T> {
  const polled = keepNewerHeldHeadline(await fetchEvent(), heldEvent());
  return adoptNewerBlendEdge(reconcileEventPoll(polled, latestFrame()), latestBlendEdge())!;
}
