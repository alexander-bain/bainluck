import { isQuoteStreamStatus } from "./eventQuoteStream";
import { isFinishedStatus } from "./eventState";
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
  if (!frame || frame.event_id !== polled.id || !isQuoteStreamStatus(polled.status)
      || (frame.status != null && frame.status !== polled.status)
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
  const liveBlend = (e: T) => isQuoteStreamStatus(e.status) && e.hero_probability_source === 'blend'
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
 * #10090 — the game state a page HOLDS against a detail payload that landed
 * after it. Two payloads can carry the same `blend_fold_revision` (a kickoff or
 * a touchdown changes no price), so neither the revision nor arrival order says
 * whose `status` and score are current: a fresh read that began before kickoff
 * landed after a `live 0-0` poll and put the game back to `scheduled`, and a
 * `7-0` became `0-0` the same way.
 *
 * The detail route stamps when it read the events row, on the database's one
 * clock (`state_read_not_before`/`_not_after`, PR #11267). The held state is
 * provably newer only when its window starts strictly after the candidate's
 * ends. Anything else — a tie, an overlap, a missing, unparseable or reversed
 * window, another event — is unordered, and the candidate is returned
 * untouched: today's behaviour exactly.
 *
 * When the held state IS newer:
 *   - a finished held payload (`completed`/`closed`) is kept WHOLE — its hero,
 *     result and pre-game reading are coupled to that status, so a splice would
 *     print FINAL over a live blend with no result;
 *   - a finished candidate is returned whole too: it is the final owner (G2),
 *     and its own settled hero cannot sit beside a carried live status;
 *   - otherwise the candidate keeps its price, sources, revision and history,
 *     and takes held's game state as ONE unit (`HELD_STATE_KEYS`, plus the two
 *     ESPN clock fields inside `espn`), with presence semantics: a key held has
 *     is copied, a key held lacks is deleted, so no flag computed against one
 *     status or start ends up beside the other's.
 *
 * Contract: artifacts/live-iteration-goal-20261011/reconciliation-contract-20261019/
 * LIVE-STATE-WINDOW-CONSUMER-CONTRACT.md (v3).
 */
export const HELD_STATE_KEYS = [
  // §2 — events-row columns the window covers, and the window itself.
  "status", "home_score", "away_score", "completed_at", "started_without_result", "authority_not_started",
  "score_source", "score_observed_at", "linescore", "box_score_data",
  "state_read_not_before", "state_read_not_after",
  // §3 — read after the window from that response's status or start; they
  // travel with the status that gated them, never ordered by the window.
  "venue_settled", "venue_settled_result", "venue_closed_no_winner", "live_probability_pinned",
  "start_is_tbd", "opening_odds", "commence_time",
] as const;
/** Inside `espn` only these two are game state; its other keys are price. */
export const HELD_ESPN_STATE_KEYS = ["period", "game_clock"] as const;

type StateBearing = { id: number; status?: string | null };
type Loose = Record<string, unknown>;
const has = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

/** `[not_before, not_after]` in whole milliseconds, or null for no usable claim. */
export function stateReadWindow(payload: unknown): [number, number] | null {
  if (!payload || typeof payload !== "object") return null;
  const { state_read_not_before: from, state_read_not_after: to } = payload as Loose;
  if (typeof from !== "string" || typeof to !== "string") return null;
  const start = Math.floor(Date.parse(from));
  const end = Math.floor(Date.parse(to));
  return Number.isFinite(start) && Number.isFinite(end) && start <= end ? [start, end] : null;
}

/** True only when `held` read the row strictly after `cand` finished reading it. */
export function heldStateIsNewer(held: StateBearing, cand: StateBearing): boolean {
  if (held.id !== cand.id) return false;
  const heldWindow = stateReadWindow(held);
  const candWindow = stateReadWindow(cand);
  return !!heldWindow && !!candWindow && heldWindow[0] > candWindow[1];
}

export function carryNewerHeldState<T extends StateBearing>(cand: T, held: T | undefined): T {
  if (!held || !heldStateIsNewer(held, cand)) return cand;
  if (isFinishedStatus(held.status)) return held;
  if (isFinishedStatus(cand.status)) return cand;
  const from = held as unknown as Loose;
  const next: Loose = { ...(cand as unknown as Loose) };
  for (const key of HELD_STATE_KEYS) {
    if (has(from, key)) next[key] = from[key];
    else delete next[key];
  }
  const heldEspn = from.espn && typeof from.espn === "object" ? from.espn as Loose : null;
  const candEspn = next.espn && typeof next.espn === "object" ? next.espn as Loose : null;
  if (candEspn || (heldEspn && HELD_ESPN_STATE_KEYS.some((key) => has(heldEspn, key)))) {
    const espn: Loose = { ...(candEspn ?? {}) };
    for (const key of HELD_ESPN_STATE_KEYS) {
      if (heldEspn && has(heldEspn, key)) espn[key] = heldEspn[key];
      else delete espn[key];
    }
    next.espn = espn;
  }
  return next as unknown as T;
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
  // #10090: the game state first (it is what the headline guards below read),
  // then the headline, each from what the page holds when the response lands.
  const response = await fetchEvent();
  const held = heldEvent();
  const polled = keepNewerHeldHeadline(carryNewerHeldState(response, held), held);
  return adoptNewerBlendEdge(reconcileEventPoll(polled, latestFrame()), latestBlendEdge())!;
}
