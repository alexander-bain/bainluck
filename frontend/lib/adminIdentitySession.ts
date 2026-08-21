/**
 * The admin-by-identity credential lifecycle, as a pure state transition.
 *
 * Queue 390, `C-2063-REVIEW` finding 1 (P1). `AdminAuthProvider` captured a
 * bearer in a mount-time probe and had no path that could ever clear it: it did
 * not subscribe to auth changes, and it is mounted under the persistent
 * `/admin` layout, so the header's `signOut()` runs while the provider stays
 * alive. Firebase and backend storage were cleared; the React state holding the
 * bearer was not, and that bearer kept authorizing labeling. The reviewer
 * replayed a real 30-day backend session token across the boundary and it
 * verified unchanged afterwards.
 *
 * The decision lives here rather than inside the component for a reason that is
 * about testability, not tidiness: the frontend suite runs `testEnvironment:
 * 'node'` with no jsdom, and `renderToStaticMarkup` does not run effects, so a
 * credential lifecycle expressed only as `useState` + `useEffect` cannot be
 * tested in this repo at all — it could only be asserted by scanning the source
 * for the shape of its own fix. Extracted, it is exhaustively testable, and the
 * component keeps only the wiring.
 */

export interface AdminIdentityState {
  /** The Firebase/backend UID this credential belongs to. */
  uid: string | null;
  /** The bearer sent on admin requests. */
  token: string | null;
  /** The authenticated admin's email, for display and attribution. */
  email: string | null;
}

/** No identity credential is held. The only safe resting state. */
export const NO_ADMIN_IDENTITY: AdminIdentityState = {
  uid: null,
  token: null,
  email: null,
};

/**
 * Fold a new auth-principal observation into the held identity credential.
 *
 * The rule is deliberately asymmetric, because the two directions have very
 * different costs:
 *
 * - **Dropping a credential is cheap.** The worst case is one extra `whoami`
 *   probe and a moment of the token-entry prompt.
 * - **Keeping one too long is the vulnerability.** So anything that is not
 *   positively "the same principal we verified" clears.
 *
 * Note what this function CANNOT do: it never grants. A uid arriving does not
 * produce a credential, because only the server knows whether that uid holds
 * the admin role — a grant requires a `whoami` answer. This is only ever
 * subtractive.
 *
 * Returns the SAME object when nothing changed, so an unchanged principal does
 * not re-render every admin page on each token refresh (Firebase emits on load,
 * on refresh, and on tab focus).
 */
export function adminIdentityAfterAuthChange(
  current: AdminIdentityState,
  nextUid: string | null,
): AdminIdentityState {
  if (current.uid === null) {
    // Nothing held. A uid alone is not a grant; only a probe can grant.
    return NO_ADMIN_IDENTITY;
  }
  if (nextUid === null) {
    // Signed out — including the backend-only path, which clears localStorage
    // without Firebase ever emitting. See `onAuthChange` in lib/firebase.ts.
    return NO_ADMIN_IDENTITY;
  }
  if (nextUid !== current.uid) {
    // Account switch. The new principal may also be an admin, but that is the
    // probe's answer to give, not this one's assumption.
    return NO_ADMIN_IDENTITY;
  }
  return current;
}
