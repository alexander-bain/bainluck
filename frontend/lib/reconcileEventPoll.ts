import { adoptNewerBlendEdge, type BlendEdgeObservation } from './blendObservationClock';
import { applyLiveFrame } from './eventLivePush';
import type { LiveStreamFrame } from './liveStreamController';

type PolledEvent = {
  id: number;
  status: string;
  hero_probability?: number | null;
  hero_probability_source?: string;
  hero_probability_observed_at?: string | null;
  win_probability_sources?: Record<string, { updated_at?: string }>;
};

/**
 * #837/#920: a cached REST response may arrive after a newer pushed price.
 * Keep the REST score/status/metadata, but do not roll the headline back while
 * the chart still contains the newer publication. Only comparable source write
 * times justify preservation; missing clocks, non-live outcomes and equally
 * new REST remain authoritative. Never invent a new observation timestamp.
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
  const frameTime = Date.parse(frame.updated_at);
  // #8749: the contract's clock dates the hero itself and counts only the
  // sources it folded; any source's stamp is the fallback for a payload that
  // does not carry one.
  const observed = Date.parse(polled.hero_probability_observed_at ?? '');
  const sourceTimes = Number.isFinite(observed) ? [observed]
    : Object.values(polled.win_probability_sources ?? {})
      .map(source => Date.parse(source.updated_at ?? ''))
      .filter(Number.isFinite);
  if (!Number.isFinite(frameTime) || sourceTimes.length === 0
      || Math.max(...sourceTimes) >= frameTime) return polled;

  return applyLiveFrame(polled, { ...frame, p: frame.p })!;
}

/**
 * Read the latest frame AFTER the response, including pushes during its flight,
 * then the chart's pinned edge (#8749): a detail cache can serve a hero older
 * than the history the page already drew, and without this every such poll
 * rolled the headline back until the next history response moved it again.
 */
export async function fetchEventWithLiveFrame<T extends PolledEvent>(
  fetchEvent: () => Promise<T>,
  latestFrame: () => LiveStreamFrame | null,
  latestBlendEdge: () => BlendEdgeObservation | null = () => null,
): Promise<T> {
  const polled = await fetchEvent();
  return adoptNewerBlendEdge(reconcileEventPoll(polled, latestFrame()), latestBlendEdge())!;
}
