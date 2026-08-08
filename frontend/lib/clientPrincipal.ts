/**
 * The client-side account boundary (UX-P017 / #1496).
 *
 * This module is L2-217's My Stuff identity boundary, promoted to the general
 * case. Nothing in it was ever My-Stuff-specific except the name and a hard
 * coded key prefix: the rule it encodes — *authenticated client state is bound
 * to WHICH ACCOUNT, never to an `isAuthenticated` boolean* — is the rule every
 * personalized surface needs.
 *
 * The defect class it exists to make impossible: an A→B account switch keeps
 * `isAuthenticated === true`, so a cache key derived from that boolean never
 * changes, an effect depending on it never re-fires, and a timer captured under
 * it never cancels. Account B then reads — and, on the write paths, durably
 * adopts — account A's state.
 *
 * Everything here is pure, so the whole account matrix (A→B, logout→B, late-A
 * response, slow B, rejected auth, remount, same user) is deterministically
 * testable without a browser, a DOM, or a real Firebase session. That property
 * is load-bearing rather than incidental: the rendered A→B proof for this class
 * is blocked on the browser rail (#1493), so purity is what lets the boundary be
 * verified at all.
 */

/** The auth facts needed to resolve who the current viewer is. */
export interface AuthSnapshot {
  /** Auth restore has not settled yet. */
  isLoading: boolean;
  /** A user object is present. */
  isAuthenticated: boolean;
  /** The stable account id, when known. */
  uid?: string | null;
}

/**
 * The opaque principal for the current viewer, or `null` when there is no
 * stable signed-in identity to bind data to YET.
 *
 * Returns null — "suppress every personalized request, render no personalized
 * data" — in three fail-closed cases:
 *   • auth restore is still in flight (`isLoading`), so the account is unknown;
 *   • nobody is signed in;
 *   • a user object exists but carries no usable `uid` — an auth supersession
 *     window. Guessing a principal here is exactly how one account's data ends
 *     up under another, so it resolves to "not ready" instead.
 *
 * The `user:` prefix matches the native `APIClient` principal shape
 * (`user:<id>` / `anon:<session>`), so both platforms describe identity alike.
 */
export function resolvePrincipal(auth: AuthSnapshot): string | null {
  if (auth.isLoading) return null;
  if (!auth.isAuthenticated) return null;
  const uid = (auth.uid ?? "").trim();
  if (uid === "") return null;
  return `user:${uid}`;
}

/**
 * Which state bucket the current viewer owns.
 *
 * `resolvePrincipal` collapses "still resolving" and "signed out" into the same
 * `null`, which is right for a surface that is *only* meaningful when signed in
 * (My Stuff, Preferences). It is wrong for state an anonymous visitor legitimately
 * owns — pins and category interests both work signed-out — because those
 * surfaces must tell "nobody is signed in, use the device bucket" apart from
 * "we don't know yet, touch nothing".
 *
 * Three states, not two, is the whole point:
 *   • `pending`   — read nothing, write nothing, migrate nothing.
 *   • `anonymous` — the device bucket is the user's own state.
 *   • `principal` — an account owns the state; the bucket is partitioned by it.
 */
export type ClientScope =
  | { kind: "pending" }
  | { kind: "anonymous" }
  | { kind: "principal"; principal: string };

export function resolveScope(auth: AuthSnapshot): ClientScope {
  if (auth.isLoading) return { kind: "pending" };
  if (!auth.isAuthenticated) return { kind: "anonymous" };
  const principal = resolvePrincipal(auth);
  // Authenticated but with no usable uid: an account owns this state and we
  // cannot name it. Falling back to the anonymous bucket here would hand one
  // account the device bucket, so this stays `pending` instead.
  if (!principal) return { kind: "pending" };
  return { kind: "principal", principal };
}

/** True when two scopes address the same bucket — a same-user re-mount. */
export function sameScope(a: ClientScope, b: ClientScope): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "principal" && b.kind === "principal") {
    return a.principal === b.principal;
  }
  return true;
}

/**
 * The SWR key for one personalized record, or `null` to SUPPRESS the request.
 *
 * SWR treats a null key as "do not fetch", so an unresolved principal issues no
 * personalized request at all — not a request that races auth. When the principal
 * IS resolved it is part of the key, so account B cannot read the entry account A
 * wrote: their keys differ even for an identical resource. Same-principal keys are
 * byte-identical across re-mounts, so SWR dedup/reuse is untouched.
 *
 * `extra` carries per-request parameters (e.g. the pinned ids being recovered)
 * and is appended after the principal so it can never shadow it.
 */
export function principalKey(
  surface: string,
  principal: string | null,
  resource: string,
  extra: ReadonlyArray<string | number> = []
): (string | number)[] | null {
  if (!principal) return null;
  return [surface, resource, principal, ...extra];
}

/**
 * A payload bound to the principal that fetched it. The binding is what makes
 * the render gate provable rather than incidental: a body only ever reaches the
 * screen alongside the identity it was fetched for.
 */
export interface PrincipalBound<T> {
  principal: string;
  data: T;
}

/** Bind a freshly fetched payload to the principal that requested it. */
export function bindToPrincipal<T>(principal: string, data: T): PrincipalBound<T> {
  return { principal, data };
}

/**
 * Unwrap a bound payload FOR the current principal, or `undefined` when it
 * belongs to anyone else (or when there is no current principal).
 *
 * This is the second, independent guard behind the principal-keyed SWR key: even
 * if a record were somehow served across identities, or a fetch dispatched under
 * account A resolved after the switch to account B, the mismatch resolves to
 * "render nothing" rather than "render the previous account". The surface falls
 * through to its normal loading state and B's own request populates it.
 */
export function dataForPrincipal<T>(
  record: PrincipalBound<T> | undefined | null,
  principal: string | null
): T | undefined {
  if (!record || !principal) return undefined;
  return record.principal === principal ? record.data : undefined;
}
