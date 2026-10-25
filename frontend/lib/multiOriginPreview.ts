/** Folded-v2 authority: independent origin clocks, one connection's snapshots. */
import { parseFoldRevision } from './foldRevision';

export interface OriginAuthority {
  epoch: number;
  seq: number;
  state: 'pending' | 'revoked' | 'expired' | 'committed';
  ttl_ms?: number;
}
export interface MultiOriginPreview {
  folded_version: 2;
  fold_session: string;
  fold_seq: number;
  base_fold_revision: Record<string, number>;
  origin_authority: Record<string, OriginAuthority>;
  kind: 'blend' | 'revoke';
  ttl_ms: number;
}
interface RememberedAuthority extends OriginAuthority { expiresAt?: number }
export interface MultiOriginReader {
  session: string | null;
  sequence: number;
  entered: boolean;
  seen: string[];
  authorities: Record<string, RememberedAuthority>;
  members?: string[];
}
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
const rowId = (v: string) => /^[1-9]\d*$/.test(v) && Number.isSafeInteger(Number(v));
const sessionId = (v: unknown): v is string => typeof v === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(v);

export function parseMultiOriginPreview(value: unknown): MultiOriginPreview | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const v = value as Record<string, unknown>;
  const base = parseFoldRevision(v.base_fold_revision);
  if (v.folded_version !== 2 || !sessionId(v.fold_session) || !integer(v.fold_seq)
      || !base || Object.keys(base).length < 2 || !Object.keys(base).every(rowId)
      || !integer(v.ttl_ms) || (v.kind !== 'blend' && v.kind !== 'revoke')) return null;
  const raw = v.origin_authority;
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const entries = Object.entries(raw);
  if (entries.length > 2) return null;
  let pending = 0;
  let minimum = Infinity;
  for (const [key, entry] of entries) {
    if (!rowId(key) || !Object.prototype.hasOwnProperty.call(base, key)
        || !entry || typeof entry !== 'object' || Array.isArray(entry)) return null;
    const a = entry as Record<string, unknown>;
    if (!integer(a.epoch) || !integer(a.seq)
        || !['pending', 'revoked', 'expired', 'committed'].includes(String(a.state))) return null;
    if (a.state === 'pending') {
      if (!integer(a.ttl_ms) || a.ttl_ms <= 0) return null;
      pending += 1;
      minimum = Math.min(minimum, a.ttl_ms);
    } else if (a.ttl_ms !== undefined) return null;
  }
  if (v.kind === 'blend' ? pending === 0 || v.ttl_ms <= 0 || v.ttl_ms > minimum : v.ttl_ms !== 0) return null;
  return v as unknown as MultiOriginPreview;
}

export function openMultiOrigin(reader: MultiOriginReader | undefined, raw: unknown, eventId: number): MultiOriginReader | undefined {
  if (raw === undefined) return reader ? { ...reader, session: null, sequence: -1, seen: [] } : undefined;
  let packet: unknown = raw;
  if (typeof raw === 'string') { try { packet = JSON.parse(raw); } catch { return reader; } }
  if (!packet || typeof packet !== 'object') return reader;
  const v = packet as Record<string, unknown>;
  if (v.event_id !== eventId || !sessionId(v.fold_session)) return reader;
  if (reader?.session === v.fold_session) return reader;
  return { session: v.fold_session, sequence: -1, seen: [], entered: reader?.entered ?? false,
    authorities: reader?.authorities ?? {}, ...(reader?.members ? { members: reader.members } : {}) };
}

export function resetMultiOrigin(reader: MultiOriginReader | undefined): MultiOriginReader | undefined {
  if (!reader) return undefined;
  const authorities = Object.fromEntries(Object.entries(reader.authorities).map(([key, authority]) =>
    [key, authority.state === 'pending' ? { ...authority, state: 'expired' as const, ttl_ms: undefined } : authority]));
  return { ...reader, authorities };
}

/** Returns nothing for a refused packet; never partially advances its fences. */
export function advanceMultiOrigin(reader: MultiOriginReader | undefined, packet: MultiOriginPreview, now: number):
  { reader: MultiOriginReader; expiresAt: number } | null {
  if (!reader || (reader.members && (Object.keys(packet.base_fold_revision).length !== reader.members.length
      || reader.members.some(key => !Object.prototype.hasOwnProperty.call(packet.base_fold_revision, key))))
      || reader.session !== packet.fold_session || packet.fold_seq <= reader.sequence
      || reader.seen.some(key => !Object.prototype.hasOwnProperty.call(packet.origin_authority, key))) return null;
  const authorities = { ...reader.authorities };
  let expiresAt = now + packet.ttl_ms;
  for (const [key, authority] of Object.entries(packet.origin_authority)) {
    const before = authorities[key];
    const same = before && authority.epoch === before.epoch && authority.seq === before.seq;
    if (before && (authority.epoch < before.epoch
        || (authority.epoch === before.epoch && authority.seq < before.seq))) return null;
    if (same && authority.state === 'pending'
        && (before.state !== 'pending' || (before.expiresAt ?? -Infinity) <= now)) return null;
    const deadline = authority.state === 'pending'
      ? Math.min(now + authority.ttl_ms!, same ? before.expiresAt ?? Infinity : Infinity) : undefined;
    authorities[key] = { ...authority, ...(deadline === undefined ? {} : { expiresAt: deadline }) };
    if (deadline !== undefined) expiresAt = Math.min(expiresAt, deadline);
  }
  // Membership changes require a new detail/navigation boundary; never grow
  // remembered origin state without bound on a long-held page.
  if (Object.keys(authorities).length > 2) return null;
  return { reader: { session: reader.session, sequence: packet.fold_seq, entered: true,
    seen: Object.keys(packet.origin_authority), authorities, ...(reader.members ? {members: reader.members} : {}) }, expiresAt };
}
