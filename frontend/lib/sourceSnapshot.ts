import { PROBABILITY_SOURCE_KEYS } from "./confidence";
import { compareFoldRevision, parseFoldRevision, type FoldRevision } from "./foldRevision";

/**
 * #10090 — `source_snapshot` on a normal price frame: the complete public
 * source map the producer computed in the SAME committed write as the frame's
 * `p` and `rev` (PR #11264). It has no price or clock of its own.
 *
 *   {"event_id":1,"p":0.61,"source":"kalshi",…,"rev":{"1":14},
 *    "source_snapshot":{"event_id":1,"rev":{"1":14},"win_probability_sources":{…}}}
 *
 * Decoded to one of three states, shared with Native
 * (reconciliation-contract-20261019/NATIVE-SOURCE-SNAPSHOT-CONSUMER-CONTRACT.md §2):
 * `absent`, `refused` (behaves exactly as absent: legacy, nothing paid) or
 * `valid`. A valid snapshot is `priced` only when the frame's `p` is a
 * probability AND the map holds a real source other than `final_result`; an
 * unpriced one is not a live blend (the producer's fallback `p` is the opening
 * or ESPN number), so no client adopts its `p` or its map.
 *
 * It proves only the rail it replaces when actually adopted. It never pays
 * history, a reconcile floor or freshness on its own.
 */
export type SourceSnapshot =
  | { state: "absent" }
  | { state: "refused" }
  | { state: "valid"; revision: FoldRevision; sources: Record<string, Record<string, unknown>>; priced: boolean };

export const SOURCE_SNAPSHOT_MAX_ENTRIES = 32;
export const SOURCE_SNAPSHOT_MAX_KEY_BYTES = 64;
/** D3: a larger raw frame decodes as legacy, its snapshot absent. */
export const SOURCE_SNAPSHOT_MAX_FRAME_BYTES = 16 * 1024;

/** UTF-8 byte length, stopping once past `limit`. */
function utf8BytesOver(text: string, limit: number): boolean {
  if (text.length > limit) return true;
  if (text.length * 3 <= limit) return false;
  let bytes = 0;
  for (let i = 0; i < text.length; i += 1) {
    const code = text.charCodeAt(i);
    if (code < 0x80) bytes += 1;
    else if (code < 0x800) bytes += 2;
    else if (code >= 0xd800 && code <= 0xdbff) { bytes += 4; i += 1; }
    else bytes += 3;
    if (bytes > limit) return true;
  }
  return false;
}

/** True when a raw probability frame is too large for its snapshot to be read. */
export function snapshotFrameIsOversize(raw: string): boolean {
  return utf8BytesOver(raw, SOURCE_SNAPSHOT_MAX_FRAME_BYTES);
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

const REFUSED: SourceSnapshot = { state: "refused" };
const ABSENT: SourceSnapshot = { state: "absent" };

export function readSourceSnapshot(frame: {
  event_id?: unknown; p?: unknown; rev?: unknown; source_snapshot?: unknown;
  folded_quote?: unknown; folded_quote_pending?: unknown;
}): SourceSnapshot {
  if (!("source_snapshot" in frame) || frame.source_snapshot === undefined) return ABSENT;
  // Never on a fold: a folded hero's rail is its `folded_quote`, not a row's map.
  if ("folded_quote" in frame || frame.folded_quote_pending !== undefined) return REFUSED;
  const snapshot = frame.source_snapshot;
  const eventId = frame.event_id;
  if (!record(snapshot) || typeof eventId !== "number" || !Number.isSafeInteger(eventId) ||
      snapshot.event_id !== eventId) return REFUSED;
  // D1: one row, this event's, and exactly the frame's own revision.
  const revision = parseFoldRevision(snapshot.rev);
  const frameRevision = parseFoldRevision(frame.rev);
  const row = String(eventId);
  if (!revision || !frameRevision || Object.keys(revision).length !== 1 || !(row in revision) ||
      Object.keys(frameRevision).length !== 1 || frameRevision[row] !== revision[row]) return REFUSED;
  // D2: a bounded map of rail entries.
  const map = snapshot.win_probability_sources;
  if (!record(map)) return REFUSED;
  const entries = Object.entries(map);
  if (entries.length > SOURCE_SNAPSHOT_MAX_ENTRIES) return REFUSED;
  for (const [key, entry] of entries) {
    if (key.length === 0 || utf8BytesOver(key, SOURCE_SNAPSHOT_MAX_KEY_BYTES) || !record(entry)) return REFUSED;
    const value = entry.value;
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0 ||
        (PROBABILITY_SOURCE_KEYS.has(key) && value > 1)) return REFUSED;
    if (["display_name", "type", "color"].some((field) => entry[field] !== undefined && typeof entry[field] !== "string")) {
      return REFUSED;
    }
    if (entry.updated_at !== undefined &&
        (typeof entry.updated_at !== "string" || !Number.isFinite(Date.parse(entry.updated_at)))) return REFUSED;
  }
  const p = frame.p;
  const priced = typeof p === "number" && Number.isFinite(p) && p >= 0 && p <= 1 &&
    entries.some(([key]) => key !== "final_result" && PROBABILITY_SOURCE_KEYS.has(key));
  return { state: "valid", revision: { [row]: revision[row] }, sources: map as Record<string, Record<string, unknown>>, priced };
}

/** A valid snapshot that is not a live blend: its frame carries no adoptable price. */
export function frameCarriesUnpricedSnapshot(frame: Parameters<typeof readSourceSnapshot>[0]): boolean {
  const snapshot = readSourceSnapshot(frame);
  return snapshot.state === "valid" && !snapshot.priced;
}

/**
 * True when an adopted snapshot rail at `shown`'s revision discharges a
 * priceless trigger (`p` null, or an unpriced snapshot): that trigger owed only
 * the rail at its own revision, and the rail on screen is now the complete map
 * at or past it. Any other trigger (a status change, a non-blend hero) is not a
 * rail debt and stays owed.
 */
export function snapshotRailPaysPricelessTrigger(
  trigger: { event_id?: unknown; p?: unknown; rev?: unknown; source_snapshot?: unknown } | null,
  shown: { event_id?: unknown; rev?: unknown },
): boolean {
  if (!trigger || trigger.event_id !== shown.event_id) return false;
  if (trigger.p !== null && !frameCarriesUnpricedSnapshot(trigger)) return false;
  const owed = parseFoldRevision(trigger.rev);
  const at = parseFoldRevision(shown.rev);
  if (!owed || !at) return false;
  const order = compareFoldRevision(at, owed);
  return order === "newer" || order === "same";
}
