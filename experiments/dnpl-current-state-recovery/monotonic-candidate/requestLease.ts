/** TEST-ONLY: a private client binding, never accepted from JSON/wire fields. */
export type RequestLease = { key: string; deadline: number };
const leases = new WeakMap<object, RequestLease>();
export const MAX_GET_LEASE_MS = 60_000;
/** A well-formed expired/zero budget still supplies a non-renewal watermark. */
export function validatedBudgetDeadline(start: number, now: number, remainingMs: unknown): number | null {
  if (!Number.isFinite(start) || start < 0 || !Number.isFinite(now) || now < start
      || typeof remainingMs !== 'number' || !Number.isSafeInteger(remainingMs)
      || remainingMs < 0 || remainingMs > MAX_GET_LEASE_MS) return null;
  const deadline = start + remainingMs;
  return Number.isFinite(deadline) ? deadline : null;
}
export function requestStartDeadline(start: number, now: number, remainingMs: unknown): number | null {
  const deadline=validatedBudgetDeadline(start,now,remainingMs);
  return deadline!==null&&now<deadline?deadline:null;
}
export function leaseKey(frame: any): string | null {
  const p = frame?.preview;
  if (!Number.isSafeInteger(frame?.event_id) || !Number.isSafeInteger(p?.epoch)
      || typeof p?.lease_id !== 'string' || p.lease_id.length < 1 || p.lease_id.length > 160) return null;
  return `${frame.event_id}:${p.epoch}:${p.lease_id}`;
}
/** Binding can be expired: the reducer then records the cap but shows nothing. */
export function bindRequestLease(frame: object, requestStart: number, now: number, remainingMs: unknown): object | null {
  const key = leaseKey(frame), deadline = validatedBudgetDeadline(requestStart, now, remainingMs);
  if (key === null || deadline === null) return null;
  leases.set(frame, {key, deadline});
  return frame;
}
export function localRequestLease(frame: object): RequestLease | undefined { return leases.get(frame); }
