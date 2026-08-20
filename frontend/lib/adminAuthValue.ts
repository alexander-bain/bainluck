/**
 * The admin auth context value, derived in one pure place.
 *
 * Queue 386 Item 2 (Alex ruling 2026-08-20). This is three lines of ternary and
 * it lives in its own file anyway, because two of those lines are security
 * properties rather than presentation:
 *
 *  - `secret` is the pasted ADMIN_TOKEN or `""`. **A session JWT is never
 *    assigned to it.** Twenty admin call sites read `secret`, and some of them
 *    build query strings with it; a JWT reaching one of those would put a
 *    30-day credential into browser history, the Referer header and the access
 *    log — the exact leak Queue #252 Item 3 removed `?secret=` to close.
 *  - `identityAdmin` is true only when there is NO pasted token. A page uses it
 *    to decide whether token-only tools are reachable, so "he pasted a token AND
 *    is an identity admin" must read as the token case.
 *
 * Inline in the component these are two ternaries nobody would test. Here they
 * are testable under the node-environment jest suite that gates deploys, with
 * no DOM and no React.
 */

export interface AdminAuthValue {
  secret: string;
  identityAdmin: boolean;
  identityEmail: string | null;
  authToken: string;
}

export function deriveAdminAuthValue(input: {
  /** The pasted ADMIN_TOKEN, or null if none was entered this session. */
  secret: string | null;
  /** The signed-in admin's session JWT, or null if not an identity admin. */
  identityToken: string | null;
  identityEmail: string | null;
}): AdminAuthValue {
  const { secret, identityToken, identityEmail } = input;
  return {
    secret: secret ?? "",
    identityAdmin: !secret && !!identityToken,
    identityEmail,
    // The pasted token wins when both are present: it is the stronger
    // credential (it opens the token-only routes) and it is what the person
    // explicitly chose to use.
    authToken: secret ?? identityToken ?? "",
  };
}
