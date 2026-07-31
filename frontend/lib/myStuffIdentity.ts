/**
 * My Stuff identity boundary (L2-217 Item 1 / C88).
 *
 * My Stuff is the only web surface whose ENTIRE payload is personal: the team
 * feed, "Your Teams' Odds", and the pinned-recovery fetches are all scoped to
 * one account. Before this module its SWR records were keyed on constant
 * strings (`"my-teams-feed"`, `"my-team-futures"`, `["my-stuff-pinned-events",
 * ...ids]`), so nothing in the key said WHO the cached body belonged to. An
 * A→B account switch — or a sign-out followed by signing in as B — reused
 * account A's cached rows for account B for the whole revalidation window.
 *
 * The fix is structural rather than a cache flush: every authenticated record
 * is keyed by the STABLE RESOLVED PRINCIPAL, and the payload itself is bound to
 * the principal that fetched it. A cross-account read is then impossible by
 * construction (different key), and a late response that resolves after a
 * switch still cannot render (its bound principal no longer matches). Nothing
 * here evicts unrelated surfaces' caches, and a same-user re-mount reproduces
 * the identical key so SWR reuse is preserved exactly as before.
 *
 * Everything in this module is pure so the account-boundary matrix (A→B,
 * logout, returning user, slow B, rejected auth, same user) is deterministically
 * testable without a browser or a real Firebase session.
 */

/** The auth facts My Stuff needs to resolve a principal. */
export interface MyStuffAuthSnapshot {
  /** Auth restore has not settled yet. */
  isLoading: boolean;
  /** A user object is present. */
  isAuthenticated: boolean;
  /** The stable account id, when known. */
  uid?: string | null;
}

/**
 * The opaque principal for the current My Stuff viewer, or `null` when there is
 * no stable signed-in identity to bind data to YET.
 *
 * Returns null — meaning "suppress every personalized request and render no
 * personalized data" — in three fail-closed cases:
 *   • auth restore is still in flight (`isLoading`), so the account is unknown;
 *   • nobody is signed in, so there is no personalized surface at all (the page
 *     shows the sign-in prompt, and a rejected/cancelled sign-in lands here);
 *   • a user object exists but carries no usable `uid` — an auth supersession
 *     window. Guessing a principal here is exactly how one account's data ends
 *     up under another, so it resolves to "not ready" instead.
 *
 * The `user:` prefix keeps the namespace explicit and matches the native
 * `APIClient` principal shape (`user:<id>` / `anon:<session>`), so the two
 * platforms describe identity the same way.
 */
export function resolveMyStuffPrincipal(auth: MyStuffAuthSnapshot): string | null {
  if (auth.isLoading) return null;
  if (!auth.isAuthenticated) return null;
  const uid = (auth.uid ?? "").trim();
  if (uid === "") return null;
  return `user:${uid}`;
}

/**
 * The SWR key for one My Stuff record, or `null` to SUPPRESS the request.
 *
 * SWR treats a null key as "do not fetch", so an unresolved principal means no
 * personalized request is ever issued — not a request that races auth. When the
 * principal IS resolved, it is part of the key, so account B literally cannot
 * read the entry account A wrote: their keys differ even for an identical
 * resource. Same-principal keys are byte-identical across re-mounts, so normal
 * SWR dedup/reuse and the progressive sibling rendering are untouched.
 *
 * `extra` carries per-request parameters (e.g. the pinned ids being recovered)
 * and is appended after the principal so it can never shadow it.
 */
export function myStuffKey(
  principal: string | null,
  resource: string,
  extra: ReadonlyArray<string | number> = []
): (string | number)[] | null {
  if (!principal) return null;
  return ["my-stuff", resource, principal, ...extra];
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
 * "render nothing" rather than "render the previous account". The page then
 * falls through to its normal loading state and B's own request populates it.
 */
export function dataForPrincipal<T>(
  record: PrincipalBound<T> | undefined | null,
  principal: string | null
): T | undefined {
  if (!record || !principal) return undefined;
  return record.principal === principal ? record.data : undefined;
}
