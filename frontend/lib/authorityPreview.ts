/** #10090: bounded v3 visit state. Committed history stays outside this reader. */
import { parseFoldRevision } from './foldRevision';
import { parseBlendPreview, previewAfter, type BlendPreviewReader, type BlendPreviewState } from './blendPreview';
import { advanceMultiOrigin, parseMultiOriginPreview, resetMultiOrigin, type MultiOriginReader } from './multiOriginPreview';

type Domain = { incarnation: string; namespace: string };
type Fence = MultiOriginReader['authorities'][string];
type Retirement = { floor: number; fence?: Fence };
export interface AuthorityPreviewReader {
  preview: BlendPreviewReader;
  domain: Domain | null;
  session: string | null;
  members: string[];
  visited: string[];
  retired: Record<string, Retirement>;
  saturated: boolean;
  membershipReady: boolean;
}
export const EMPTY_AUTHORITY_PREVIEW: AuthorityPreviewReader = {
  preview: { held: null, epoch: -1 }, domain: null, session: null,
  members: [], visited: [], retired: {}, saturated: false, membershipReady: false,
};
const positive = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const uuid = (v: unknown): v is string => typeof v === 'string'
  && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v)
  && v !== '00000000-0000-0000-0000-000000000000';
const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: string[]) => Object.keys(v).length === keys.length
  && keys.every(key => Object.prototype.hasOwnProperty.call(v, key));
const sameKeys = (a: string[], b: string[]) => a.length === b.length && a.every(key => b.includes(key));
const sameDomain = (a: Domain | null, b: Domain) => a?.incarnation === b.incarnation && a.namespace === b.namespace;

/** JSON.parse cannot detect duplicate decoded keys. Scan first, bounded by wire size/depth. */
export function parseUniquePreviewJSON(raw: unknown): unknown {
  if (typeof raw !== 'string' || raw.length > 16384 || new TextEncoder().encode(raw).length > 16384) return null;
  let i = 0;
  const white = () => { while (/[\x20\t\r\n]/.test(raw[i] ?? '') && i < raw.length) i++; };
  const string = () => {
    const re = /"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"/y;
    re.lastIndex = i;
    const found = re.exec(raw);
    if (!found) throw new Error('string');
    i = re.lastIndex;
    return JSON.parse(found[0]) as string;
  };
  const value = (depth: number): void => {
    if (depth > 64) throw new Error('depth');
    white();
    const start = raw[i];
    if (start === '"') { string(); return; }
    if (start === '{' || start === '[') {
      i++; white();
      const end = start === '{' ? '}' : ']';
      const keys = new Set<string>();
      if (raw[i] === end) { i++; return; }
      for (;;) {
        white();
        if (start === '{') {
          const key = string();
          if (keys.has(key)) throw new Error('duplicate');
          keys.add(key); white();
          if (raw[i++] !== ':') throw new Error('colon');
        }
        value(depth + 1); white();
        if (raw[i] === end) { i++; return; }
        if (raw[i++] !== ',') throw new Error('comma');
      }
    }
    const re = /(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/y;
    re.lastIndex = i;
    const found = re.exec(raw);
    if (!found || (/^[-\d]/.test(found[0]) && !Number.isFinite(Number(found[0])))) throw new Error('value');
    i = re.lastIndex;
  };
  try {
    value(0); white();
    return i === raw.length ? JSON.parse(raw) : null;
  } catch { return null; }
}

function envelope(raw: unknown, kind: 'open' | 'frame', eventId: number) {
  const v = parseUniquePreviewJSON(raw);
  if (!record(v) || !exact(v, ['protocol', 'event_id', 'authority', 'stream_session', kind === 'open' ? 'members' : 'frame'])
      || v.protocol !== 3 || v.event_id !== eventId || !positive(v.event_id) || !uuid(v.stream_session)
      || !record(v.authority) || !exact(v.authority, ['incarnation', 'namespace'])) return null;
  const { incarnation, namespace } = v.authority;
  if (typeof incarnation !== 'string' || !/^[1-9]\d*$/.test(incarnation)
      || !positive(Number(incarnation)) || !uuid(namespace)) return null;
  return { authority: { incarnation, namespace }, stream_session: v.stream_session, members: v.members, frame: v.frame };
}

export function authorityPreviewReset(r: AuthorityPreviewReader, endSession = true): AuthorityPreviewReader {
  return { ...r, session: endSession ? null : r.session,
    preview: { ...r.preview, held: null, multiOrigin: resetMultiOrigin(r.preview.multiOrigin) } };
}

/** Adopted detail is the sole membership authority, including rejoining rows. */
export function authorityPreviewMembership(r: AuthorityPreviewReader, raw: unknown, eventId: number): AuthorityPreviewReader {
  const vector = parseFoldRevision(raw);
  if (!vector || !Object.prototype.hasOwnProperty.call(vector, String(eventId))
      || !Object.keys(vector).every(key => /^[1-9]\d*$/.test(key) && positive(Number(key)))) {
    return { ...authorityPreviewReset(r), membershipReady: false };
  }
  if (r.saturated) return r;
  const members = Object.keys(vector).sort((a, b) => Number(a) - Number(b));
  if (members.length > 32) return { ...authorityPreviewReset(r), saturated: true };
  if (sameKeys(members, r.members)) return { ...authorityPreviewFloor(r, vector), membershipReady: true };
  const reset = authorityPreviewReset(r);
  const retired = { ...r.retired };
  const previousFences = reset.preview.multiOrigin?.authorities ?? {};
  for (const key of r.members) if (!members.includes(key)) retired[key] = {
    floor: Math.max(r.preview.floors?.[key] ?? 0, retired[key]?.floor ?? 0),
    fence: previousFences[key] ?? retired[key]?.fence,
  };
  const visited = [...new Set([...r.visited, ...members])];
  // Retire the whole leaving batch before saturation, never evict evidence.
  if (visited.length > 32 || Object.keys(retired).length > 8) {
    return { ...reset, retired, saturated: true };
  }
  const floors: Record<string, number> = {};
  const authorities: Record<string, Fence> = {};
  for (const key of members) {
    floors[key] = Math.max(vector[key], r.preview.floors?.[key] ?? 0, retired[key]?.floor ?? 0);
    const fence = previousFences[key] ?? retired[key]?.fence;
    if (fence) authorities[key] = fence;
    delete retired[key];
  }
  return { ...reset, members, visited, retired, membershipReady: true,
    preview: { held: null, epoch: -1, floors,
      multiOrigin: { session: null, sequence: -1, seen: [], entered: members.length > 1, members, authorities } } };
}

export function authorityPreviewFloor(r: AuthorityPreviewReader, raw: unknown): AuthorityPreviewReader {
  const incoming = parseFoldRevision(raw);
  if (!incoming) return authorityPreviewReset(r, false);
  const floors = { ...r.preview.floors }, retired = { ...r.retired };
  if (!Object.keys(incoming).every(key => /^[1-9]\d*$/.test(key) && positive(Number(key)))) return authorityPreviewReset(r, false);
  if (r.saturated) return authorityPreviewReset(r, false);
  // Preserve out-of-membership commit evidence until authoritative detail
  // adopts the row, with the same visit/retired bounds as membership changes.
  const unknown = Object.keys(incoming).filter(key => !r.members.includes(key) && !retired[key]);
  if (Object.keys(incoming).length > 32) return { ...authorityPreviewReset(r), saturated: true };
  const visited = [...new Set([...r.visited, ...unknown])];
  for (const key of unknown) retired[key] = { floor: incoming[key] };
  if (visited.length > 32 || Object.keys(retired).length > 8) return { ...authorityPreviewReset(r), retired, saturated: true };
  for (const [key, rev] of Object.entries(incoming)) {
    if (retired[key]) retired[key] = { ...retired[key], floor: Math.max(rev, retired[key].floor) };
    else floors[key] = Math.max(rev, floors[key] ?? 0);
  }
  const held = r.preview.held;
  const base = held?.baseFoldRevision ?? (held ? { [String(held.eventId)]: held.baseRev } : {});
  const covered = r.members.every(key => (base[key] ?? -1) >= (floors[key] ?? 0));
  return { ...r, retired, visited, preview: { ...r.preview, floors, held: covered && !unknown.length ? held : null } };
}

export function authorityPreviewOpen(r: AuthorityPreviewReader, raw: unknown, eventId: number): AuthorityPreviewReader {
  const v = envelope(raw, 'open', eventId);
  const members = v?.members;
  if (!v || r.saturated || !r.membershipReady || !Array.isArray(members) || members.length < 1 || members.length > 32
      || !members.every((id: unknown, i: number) => positive(id) && (i === 0 || id > members[i - 1]))
      || !sameKeys(members.map(String), r.members)) return r;
  if (r.domain && (Number(v.authority.incarnation) < Number(r.domain.incarnation)
      || (v.authority.incarnation === r.domain.incarnation && v.authority.namespace !== r.domain.namespace))) return r;
  if (sameDomain(r.domain, v.authority) && r.session === v.stream_session) return r;
  const reset = authorityPreviewReset(r);
  const changed = !sameDomain(r.domain, v.authority);
  const authorities = changed ? {} : reset.preview.multiOrigin?.authorities ?? {};
  return { ...reset, domain: v.authority, session: v.stream_session,
    retired: changed ? Object.fromEntries(Object.entries(r.retired).map(([key, entry]) => [key, { floor: entry.floor }])) : r.retired,
    preview: { held: null, epoch: -1, floors: r.preview.floors,
      multiOrigin: { session: v.stream_session, sequence: -1, seen: [], entered: r.members.length > 1,
        members: r.members, authorities } } };
}

/** Receipt/now are monotonic. Queue/render delay spends the supplied lifetime. */
export function authorityPreviewFrame(r: AuthorityPreviewReader, raw: unknown, eventId: number,
  receipt: number, now: number): AuthorityPreviewReader {
  if (r.saturated || !r.session || !Number.isFinite(receipt) || !Number.isFinite(now) || now < receipt) return r;
  const v = envelope(raw, 'frame', eventId);
  if (!v || !sameDomain(r.domain, v.authority) || v.stream_session !== r.session) return r;
  const frame = parseBlendPreview(v.frame);
  if (!frame || frame.event_id !== eventId) return r;
  // #10090: the admitted domain/session travel with the held preview as its
  // display identity. The held value is reset on every open, so this is never
  // a borrowed identity from an earlier session.
  const adopt = (held: BlendPreviewState | null) => held && {
    ...held, receivedAt: receipt,
    authority: { incarnation: v.authority.incarnation, namespace: v.authority.namespace,
      session: v.stream_session, fold: r.members.length > 1 },
  };
  const p = frame.preview;
  const covers = (base: Record<string, number>) => sameKeys(Object.keys(base), r.members)
    && r.members.every(key => base[key] >= (r.preview.floors?.[key] ?? 0));
  if (r.members.length > 1) {
    const packet = parseMultiOriginPreview(p);
    if (!packet || packet.fold_session !== r.session || !sameKeys(Object.keys(packet.base_fold_revision), r.members)) return r;
    // Advance at original receipt time so fractional processing age cannot
    // round a valid integer wire TTL upward. Refuse expired display afterward.
    const advance = advanceMultiOrigin(r.preview.multiOrigin, packet, receipt, 32);
    if (!advance) return r;
    const held = packet.kind === 'blend' && covers(packet.base_fold_revision) && advance.expiresAt > now
      ? adopt(previewAfter(null, frame, eventId, receipt)) : null;
    return { ...r, preview: { ...r.preview, multiOrigin: advance.reader,
      held: held ? { ...held, expiresAt: advance.expiresAt } : null } };
  }
  if (r.members.length !== 1 || ['folded_version', 'fold_session', 'fold_seq', 'origin_authority', 'base_fold_revision', 'origin_event_id']
    .some(key => Object.prototype.hasOwnProperty.call(p, key))) return r;
  if (p.kind === 'blend' && !['live', 'scheduled', 'suspended'].includes(frame.status ?? '')) return r;
  if (p.kind === 'revoke' && frame.p !== null) return r;
  const key = String(eventId), multi = r.preview.multiOrigin!;
  const before = multi.authorities[key];
  const seq = p.kind === 'revoke' ? Math.max(p.seq, p.through_seq!) : p.seq;
  if (before && (p.epoch < before.epoch || (p.epoch === before.epoch && seq < before.seq))) return r;
  const same = before && p.epoch === before.epoch && seq === before.seq;
  if (p.kind === 'blend' && same && (before.state !== 'pending' || (before.expiresAt ?? -Infinity) <= now)) return r;
  const deadline = p.kind === 'blend' ? Math.min(receipt + p.ttl_ms!, same ? before.expiresAt ?? Infinity : Infinity) : undefined;
  const fence: Fence = { epoch: p.epoch, seq, state: p.kind === 'blend' ? (deadline! > now ? 'pending' : 'expired') : 'revoked',
    ...(deadline !== undefined ? { expiresAt: deadline } : {}) };
  const held = p.kind === 'blend' && covers({ [key]: p.base_rev! }) && deadline! > now
    ? (same ? r.preview.held : adopt(previewAfter(null, frame, eventId, receipt)))
    : p.kind === 'revoke' && r.preview.held?.epoch === p.epoch && r.preview.held.seq > p.through_seq!
      ? r.preview.held : null;
  return { ...r, preview: { ...r.preview, epoch: p.epoch,
    multiOrigin: { ...multi, authorities: { ...multi.authorities, [key]: fence } },
    held: held && deadline !== undefined ? { ...held, expiresAt: deadline } : held } };
}

/** #10090: the longest a withdrawn folded preview stays on the headline. */
export const FLOOR_HANDOVER_MS = 1000;

/**
 * #10090 — display only; the reader above is unchanged and admits nothing over
 * an uncovered base. On a page that folds several rows, a commit floor
 * (`fold_preview_floor`, or a raw frame that promises its folded result)
 * withdraws the held preview before the combined result folding the same write
 * arrives, and until then the committed hero is the value at the OLD base:
 * older than both the floor and the preview. So the page keeps the preview it
 * already holds — the same state, with its own identity, receipt and
 * observation clock, never re-admitted — until that result decides, for at most
 * its own lifetime and FLOOR_HANDOVER_MS. `before`/`after` are the reader either
 * side of the floor; `current` is a hand-over already running (never extended).
 * Anything but a plain floor over this fold's own rows (a reset, a new session,
 * saturation, a row outside the fold, a membership change) hands over nothing.
 */
export function authorityPreviewHandover(before: AuthorityPreviewReader, after: AuthorityPreviewReader,
  raw: unknown, current: BlendPreviewState | null, now: number): BlendPreviewState | null {
  if (after.preview.held) return null;
  const held = current ?? before.preview.held;
  const incoming = parseFoldRevision(raw);
  if (!held || !held.authority?.fold || before.members.length < 2 || after.saturated
      || !before.session || after.session !== before.session || held.authority.session !== after.session
      || !before.preview.multiOrigin || after.preview.multiOrigin !== before.preview.multiOrigin
      || !sameKeys(after.members, before.members)
      || !incoming || !Object.keys(incoming).every(key => before.members.includes(key))
      || !Number.isFinite(now) || now >= held.expiresAt) return null;
  return current ?? { ...held, expiresAt: Math.min(held.expiresAt, now + FLOOR_HANDOVER_MS) };
}
