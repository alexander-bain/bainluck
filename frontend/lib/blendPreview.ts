/**
 * #10090 — a provisional blend shown before its event stamp commits
 * (`backend/app/utils/blend_preview.py`).
 *
 * The server sends these only for its canary events, as a separate `preview`
 * SSE event. Without one, every function here returns its input and the page
 * renders exactly what it renders today.
 *
 * A preview is never written into the page's committed cache. It is an overlay
 * on the hero and a disposable chart projection, and it gives way to committed truth by rule:
 *
 * - It carries no committed revision. Its `base_rev` is the revision it was
 *   composed on; it shows only while the page holds no NEWER committed
 *   revision of its one row. Any newer commit wins, whoever wrote it.
 * - `epoch` is the writing process's display claim, fenced at Redis: a
 *   replacement worker's claim is a higher epoch, and a superseded worker can
 *   no longer publish a blend. The reader keeps the highest epoch it has seen
 *   and refuses anything older (`readerAfter`) — an earlier epoch never
 *   regains the display, whatever order frames arrive in. A higher epoch voids
 *   whatever the older one showed.
 * - Within an epoch, previews order by `seq`: a lower seq never replaces a
 *   higher one, and a `revoke` withdraws every preview up to `through_seq`.
 * - It expires after `ttl_ms` from arrival — a backstop for a revoke lost with
 *   a stopped worker; the server revokes on its own clock as well.
 * - A reconnect clears the held preview (previews are never replayed, so a
 *   missed revoke cannot be ruled out across a reconnect); the epoch floor is
 *   kept, because epochs only rise.
 * - It shows only for the same quote status the page holds, on a live blend
 *   hero (`hero_probability_source === "blend"`).
 */

import { parseFoldRevision } from "./foldRevision";
import { advanceMultiOrigin, openMultiOrigin, parseMultiOriginPreview, resetMultiOrigin,
  type MultiOriginPreview, type MultiOriginReader } from './multiOriginPreview';

const PREVIEW_STATUSES = new Set(["live", "scheduled", "suspended"]);

export interface BlendPreviewFrame {
  event_id: number;
  p: number | null;
  p_away?: number | null;
  sport?: string | null;
  status?: string | null;
  provisional?: boolean;
  /** Legacy producer attempt time; never used as a chart observation. */
  observed_at?: string;
  /** Complete blend observation clock, independent of retries and receipt time. */
  display_observed_at?: string | null;
  preview: {
    kind: "blend" | "revoke";
    epoch: number;
    seq: number;
    base_rev?: number;
    ttl_ms?: number;
    through_seq?: number;
    reason?: string;
    pending?: Record<string, number>;
    folded_version?: number;
    origin_event_id?: number;
    base_fold_revision?: Record<string, number>;
    fold_session?: string;
    fold_seq?: number;
    origin_authority?: MultiOriginPreview["origin_authority"];
  };
}

export interface BlendPreviewState {
  eventId: number;
  epoch: number;
  seq: number;
  baseRev: number;
  p: number;
  status: string | null;
  /** `now()` milliseconds after which the preview is no longer shown. */
  expiresAt: number;
  observedAt?: string;
  baseFoldRevision?: Record<string, number>;
  originEventId?: number;
  pAway?: number | null;
  sport?: string | null;
}

const safeInt = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

export function parseBlendPreview(raw: unknown): BlendPreviewFrame | null {
  let frame: unknown = raw;
  if (typeof raw === "string") {
    try {
      frame = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!frame || typeof frame !== "object") return null;
  const f = frame as Record<string, unknown>;
  const preview = f.preview as Record<string, unknown> | undefined;
  // A committed revision on a "preview" is a contradiction: refuse it.
  if (typeof f.event_id !== "number" || "rev" in f || !preview || typeof preview !== "object") return null;
  if (preview.folded_version === 2) {
    const multi = parseMultiOriginPreview(preview);
    if (!multi || !safeInt(f.event_id) || f.event_id <= 0
        || !Object.prototype.hasOwnProperty.call(multi.base_fold_revision, String(f.event_id))
        || (multi.kind === 'blend' && (typeof f.p !== 'number' || !Number.isFinite(f.p) || f.p < 0 || f.p > 1
          || !(f.p_away === null || (typeof f.p_away === 'number' && Number.isFinite(f.p_away) && f.p_away >= 0 && f.p_away <= 1))
          || !(f.sport === null || typeof f.sport === 'string')
          || typeof f.status !== 'string' || !PREVIEW_STATUSES.has(f.status)
          || !(f.display_observed_at === null || (typeof f.display_observed_at === 'string' && Number.isFinite(Date.parse(f.display_observed_at))))))
        || (multi.kind === 'revoke' && f.p !== null)) return null;
    // Internal shape only: v2 never orders by these legacy scalar fields.
    return { ...f, preview: { ...multi, epoch: 0, seq: multi.fold_seq,
      base_rev: multi.base_fold_revision[String(f.event_id)] } } as BlendPreviewFrame;
  }
  if (!safeInt(preview.epoch) || !safeInt(preview.seq)) return null;
  if (preview.kind === "revoke") {
    return safeInt(preview.through_seq) ? (frame as BlendPreviewFrame) : null;
  }
  if (preview.kind !== "blend") return null;
  if (typeof f.p !== "number" || !Number.isFinite(f.p) || f.p < 0 || f.p > 1) return null;
  if (!safeInt(preview.base_rev) || !safeInt(preview.ttl_ms)) return null;
  if (preview.folded_version !== undefined || preview.base_fold_revision !== undefined) {
    const vector = parseFoldRevision(preview.base_fold_revision);
    if (preview.folded_version !== 1 || !vector || Object.keys(vector).length < 2
        || !safeInt(preview.origin_event_id) || preview.origin_event_id <= 0
        || !Object.prototype.hasOwnProperty.call(vector, String(f.event_id))
        || vector[String(preview.origin_event_id)] !== preview.base_rev
        || !(typeof f.sport === "string" || f.sport === null)
        || !(f.p_away === null || (typeof f.p_away === "number"
          && Number.isFinite(f.p_away) && f.p_away >= 0 && f.p_away <= 1))) return null;
  }
  return frame as BlendPreviewFrame;
}

/** What one event's reader holds: its preview, and the highest epoch it has seen. */
export interface BlendPreviewReader {
  held: BlendPreviewState | null;
  /** The fence floor: frames from a lower epoch are refused. -1 before any. */
  epoch: number;
  floors?: Record<string, number>;
  foldedSequence?: { epoch: number; seq: number };
  multiOrigin?: MultiOriginReader;
}

export const EMPTY_BLEND_PREVIEW_READER: BlendPreviewReader = { held: null, epoch: -1 };

/**
 * The reader after `frame` arrives at `now`. A lower epoch is fenced out; a
 * higher one raises the floor and voids the older epoch's preview first.
 */
export function readerAfter(
  reader: BlendPreviewReader, frame: BlendPreviewFrame, eventId: number, now: number,
): BlendPreviewReader {
  if (frame.event_id !== eventId) return reader;
  if (frame.preview.folded_version === 2) {
    const packet = parseMultiOriginPreview(frame.preview);
    if (!packet) return reader;
    const advance = advanceMultiOrigin(reader.multiOrigin, packet, now);
    if (!advance) return reader;
    const blocked = reader.floors && !coversPreviewFloors(packet.base_fold_revision, reader.floors);
    const held = packet.kind === 'blend' && !blocked ? previewAfter(null, frame, eventId, now) : null;
    return { ...reader, multiOrigin: advance.reader,
      held: held ? { ...held, expiresAt: advance.expiresAt } : null };
  }
  if (reader.multiOrigin?.entered) return reader;
  const epoch = frame.preview.epoch;
  if (epoch < reader.epoch) return reader;
  const held = epoch > reader.epoch ? null : reader.held;
  if (reader.foldedSequence?.epoch === epoch
      && frame.preview.seq <= reader.foldedSequence.seq) return reader;
  if (frame.preview.base_fold_revision && reader.floors
      && !coversPreviewFloors(frame.preview.base_fold_revision, reader.floors)) {
    return { ...reader, held: null, epoch };
  }
  if (frame.preview.kind === "revoke" && held?.originEventId !== undefined
      && frame.preview.origin_event_id !== held.originEventId) return reader;
  const nextHeld = previewAfter(held, frame, eventId, now);
  const origin = String(frame.preview.origin_event_id ?? eventId);
  const multiOrigin = reader.multiOrigin ?? { session: null, sequence: -1, entered: false, seen: [], authorities: {} };
  const priorAuthority = multiOrigin.authorities[origin];
  const authority = { epoch, seq: frame.preview.seq,
    state: frame.preview.kind === 'blend' ? 'pending' as const : 'revoked' as const,
    ...(nextHeld ? { expiresAt: nextHeld.expiresAt } : {}) };
  // Keep the independent origin fence even while legacy display rules apply.
  // Duplicate packets and resets must not erase its original deadline/retirement.
  const remembered = priorAuthority && (priorAuthority.epoch > epoch
    || (priorAuthority.epoch === epoch && priorAuthority.seq > authority.seq)
    || (priorAuthority.epoch === epoch && priorAuthority.seq === authority.seq && authority.state === 'pending'))
    ? priorAuthority : authority;
  return { ...reader, held: nextHeld, epoch,
    multiOrigin: { ...multiOrigin, authorities: { ...multiOrigin.authorities, [origin]: remembered } },
    ...((frame.preview.base_fold_revision || reader.foldedSequence) ? {
      foldedSequence: { epoch, seq: frame.preview.seq },
    } : {}),
  };
}

/** Only authoritative detail membership may retire removed origin fences. */
export function readerAfterPreviewMembership(reader: BlendPreviewReader, value: unknown, eventId: number): BlendPreviewReader {
  const vector = parseFoldRevision(value);
  if (!vector || !Object.prototype.hasOwnProperty.call(vector, String(eventId))
      || !Object.keys(vector).every(key => /^[1-9]\d*$/.test(key) && Number.isSafeInteger(Number(key)))) return reader;
  const members = Object.keys(vector).sort();
  if (JSON.stringify(reader.multiOrigin?.members) === JSON.stringify(members)) return reader;
  const keep = (key: string) => Object.prototype.hasOwnProperty.call(vector, key);
  const authorities = Object.fromEntries(Object.entries(reader.multiOrigin?.authorities ?? {}).filter(([key]) => keep(key)));
  const floors = { ...vector };
  for (const [key, revision] of Object.entries(reader.floors ?? {})) if (keep(key)) floors[key] = Math.max(floors[key], revision);
  const singleton = members.length === 1 ? authorities[String(eventId)] : undefined;
  return { ...reader, held: null, floors,
    ...(members.length === 1 ? { epoch: singleton?.epoch ?? -1,
      foldedSequence: singleton ? { epoch: singleton.epoch, seq: singleton.seq } : undefined } : {}),
    multiOrigin: { session: null, sequence: -1, seen: [], authorities, members,
      entered: members.length > 1 && (reader.multiOrigin?.entered ?? false) } };
}

export function readerAfterPreviewOpen(reader: BlendPreviewReader, raw: unknown, eventId: number): BlendPreviewReader {
  const multiOrigin = openMultiOrigin(reader.multiOrigin, raw, eventId);
  return multiOrigin === reader.multiOrigin ? reader : { ...reader, held: null, multiOrigin };
}

export function readerAfterPreviewReset(reader: BlendPreviewReader): BlendPreviewReader {
  return { ...reader, held: null,
    ...(reader.multiOrigin ? { multiOrigin: resetMultiOrigin(reader.multiOrigin) } : {}) };
}

function coversPreviewFloors(base: Record<string, number>, floors: Record<string, number>): boolean {
  return Object.entries(floors).every(([key, value]) =>
    Object.prototype.hasOwnProperty.call(base, key) && base[key] >= value);
}

/** Raw commit evidence invalidates before a slower folded quote is available. */
export function readerAfterCommitFloor(reader: BlendPreviewReader, value: unknown): BlendPreviewReader {
  const incoming = parseFoldRevision(value);
  if (!incoming) return { ...reader, held: null };
  const floors = { ...reader.floors };
  for (const [key, revision] of Object.entries(incoming)) {
    floors[key] = Math.max(revision, floors[key] ?? -1);
  }
  const held = reader.held?.baseFoldRevision
    && !coversPreviewFloors(reader.held.baseFoldRevision, floors) ? null : reader.held;
  return { ...reader, floors, held };
}

/** Within one epoch: the preview to hold after `frame` arrives at `now`. */
export function previewAfter(
  state: BlendPreviewState | null, frame: BlendPreviewFrame, eventId: number, now: number,
): BlendPreviewState | null {
  if (frame.event_id !== eventId) return state;
  const { preview } = frame;
  const sameEpoch = state !== null && state.epoch === preview.epoch;
  if (preview.kind === "revoke") {
    if (!state) return null;
    if (!sameEpoch) return null; // a new epoch spoke; the old one's preview cannot be trusted
    return state.seq <= (preview.through_seq as number) ? null : state;
  }
  if (sameEpoch && preview.seq <= state.seq) return state;
  return {
    eventId,
    epoch: preview.epoch,
    seq: preview.seq,
    baseRev: preview.base_rev as number,
    p: frame.p as number,
    status: frame.status ?? null,
    expiresAt: now + (preview.ttl_ms as number),
    observedAt: typeof frame.display_observed_at === "string" ? frame.display_observed_at : undefined,
    ...(preview.base_fold_revision ? {
      baseFoldRevision: { ...preview.base_fold_revision }, originEventId: preview.origin_event_id,
      pAway: frame.p_away, sport: frame.sport,
    } : {}),
  };
}

interface HeldBlend {
  id?: unknown;
  status?: string | null;
  hero_probability_source?: string | null;
  blend_fold_revision?: unknown;
  sport?: string | null;
}

/** The provisional hero probability to show, or null for committed truth. */
export function displayedPreview(
  state: BlendPreviewState | null, held: HeldBlend | null | undefined, now: number,
): number | null {
  if (!state || !held || now >= state.expiresAt) return null;
  if (held.id !== state.eventId) return null;
  if (held.hero_probability_source !== "blend") return null;
  const status = held.status ?? null;
  if (status === null || !PREVIEW_STATUSES.has(status) || status !== state.status) return null;
  // Only a singleton revision of this very row can be ordered against base_rev;
  // a folded hero (several rows) or no revision at all shows committed truth.
  const committed = parseFoldRevision(held.blend_fold_revision);
  if (state.baseFoldRevision) {
    if (!committed || held.sport !== state.sport
        || Object.keys(committed).length !== Object.keys(state.baseFoldRevision).length
        || !coversPreviewFloors(state.baseFoldRevision, committed)) return null;
    return state.p;
  }
  const key = String(state.eventId);
  if (!committed || Object.keys(committed).length !== 1 || !(key in committed)) return null;
  return committed[key] > state.baseRev ? null : state.p;
}

/**
 * `event` with the provisional hero overlaid, or `event` itself (same object)
 * when no preview applies — so a page without previews renders unchanged.
 */
export function overlayBlendPreview<T extends HeldBlend | null | undefined>(
  event: T, state: BlendPreviewState | null, now: number,
): T {
  const p = displayedPreview(state, event, now);
  if (p === null || !event) return event;
  return { ...event, hero_probability: p,
    hero_probability_away: state?.baseFoldRevision ? state.pAway : 1 - p } as T;
}

/**
 * The observation clock of the probability actually displayed. A preview with
 * no usable observation clock is unknown, not the committed value's time (and
 * never the producer attempt time). The headline's exact admission gate also
 * restores the committed clock on expiry, withdrawal or a newer commit.
 */
export function displayedProbabilityObservedAt(
  event: HeldBlend | null | undefined,
  state: BlendPreviewState | null,
  now: number,
  committedClock: string | null | undefined,
): string | null | undefined {
  if (displayedPreview(state, event, now) === null) return committedClock;
  const timestamp = state?.observedAt;
  return timestamp && Number.isFinite(Date.parse(timestamp)) ? timestamp : null;
}

interface PreviewChartHistory {
  event_id: number;
  aggregate_line?: PreviewChartPoint[] | null;
  blend_edge_pinned?: boolean | null;
  blend_edge_observed_at?: string | null;
  blend_edge_fold_revision?: unknown;
}

interface PreviewChartPoint {
  timestamp: string;
  home_probability: number;
}

/**
 * A disposable render projection, never committed history. Use the exact same
 * preview fence as the headline and its supplied observation time. A preview
 * with no usable time, or behind the committed chart, cannot extend the edge.
 * Revoke, expiry, reconnect and a newer commit return the original line.
 */
export function overlayBlendPreviewLine(
  event: HeldBlend | null | undefined,
  state: BlendPreviewState | null,
  now: number,
  line: PreviewChartPoint[] | undefined,
  served?: PreviewChartHistory | null,
): PreviewChartPoint[] | undefined {
  const p = displayedPreview(state, event, now);
  const timestamp = state?.observedAt;
  if (p === null || !timestamp) return line;
  const at = Date.parse(timestamp);
  if (!Number.isFinite(at)) return line;
  // A refreshed history may pin its old committed value at the READ time,
  // after this preview's actual observation. That synthetic edge is not a
  // newer quote. Remove only that proven presentation point from this render
  // copy; leave the cached history and all real observations untouched.
  const edge = line?.[line.length - 1];
  const servedEdge = served?.aggregate_line?.[served.aggregate_line.length - 1];
  const edgeRevision = parseFoldRevision(served?.blend_edge_fold_revision);
  const base = state?.baseFoldRevision ?? (state ? { [String(state.eventId)]: state.baseRev } : null);
  // History can advance ahead of detail while retaining an earlier observation
  // time. Its revision wins before either extending or replacing the edge. An
  // older membership (events.py serves one beside newly folded detail) may be
  // extended when the base covers every member; replacement needs exact membership.
  if (served && (served.event_id !== state?.eventId
      || ((served.blend_edge_pinned === true || served.blend_edge_fold_revision != null)
        && (!edgeRevision || !base || !coversPreviewFloors(base, edgeRevision))))) return line;
  const edgeObserved = Date.parse(served?.blend_edge_observed_at ?? "");
  const replaceSyntheticEdge = edge !== undefined && servedEdge !== undefined
    && served?.event_id === state?.eventId && served.blend_edge_pinned === true
    && Number.isFinite(edgeObserved) && edgeObserved < at
    && Date.parse(edge.timestamp) >= at
    && Date.parse(servedEdge.timestamp) === Date.parse(edge.timestamp)
    && servedEdge.home_probability === edge.home_probability
    && edgeRevision !== null && base !== null
    && Object.keys(edgeRevision).length === Object.keys(base).length
    && coversPreviewFloors(base, edgeRevision);
  const historical = replaceSyntheticEdge ? line!.slice(0, -1) : line ?? [];
  for (const point of historical) {
    const committedAt = Date.parse(point.timestamp);
    if (!Number.isFinite(committedAt) || committedAt >= at) return line;
  }
  return [...historical, { timestamp, home_probability: p }];
}
