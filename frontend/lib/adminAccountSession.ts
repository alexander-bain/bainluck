/**
 * #5952 — "is the account I am signed in with an admin?", asked of the server.
 *
 * This is the entire client side of the authorization decision, and it decides
 * nothing. It hands the account token to `GET /api/admin/whoami` and believes
 * the answer. There is deliberately no local rule here — no email comparison,
 * no allowlist, no claim parsing, not even a JWT decode — because any of those
 * would be a second opinion about privilege formed in a place the reader can
 * edit. The server's 200/403 is the only input.
 *
 * Dependencies are injected rather than imported so the whole thing is testable
 * without a DOM, a network or the Firebase SDK (the admin suites render with
 * `renderToStaticMarkup`; there is no jsdom to mock in).
 */

/** What `/api/admin/whoami` answers. `email` is display-only. */
export interface AdminAccountSession {
  token: string;
  email: string | null;
}

export interface AdminAccountProbeDeps {
  /** The account token for the signed-in reader, or null when signed out. */
  getToken: () => Promise<string | null>;
  /**
   * Ask the server. Resolves with the parsed body on 200; REJECTS on any
   * non-OK status, which is how a 403 ("you are signed in, but not an admin")
   * reaches us. `adminFetchJSON` already has exactly these semantics.
   */
  whoami: (token: string) => Promise<unknown>;
}

/**
 * True when this browser has an account session worth asking about.
 *
 * Checked before `getToken`, and it is a performance guard, not a security one
 * — a false positive costs a 403, which is handled. Without it, opening /admin
 * in a browser that has never signed in pulls ~200KB of Firebase SDK to
 * discover there is no user, delaying the secret prompt for the lanes and the
 * one-off visits that are most of this page's traffic. `useAuth` defers the SDK
 * on the same marker for the same reason.
 */
export function hasStoredAccountSession(
  markerKey: string,
  backendAuthKey: string
): boolean {
  if (typeof window === "undefined") return false;
  try {
    return (
      localStorage.getItem(markerKey) === "true" ||
      localStorage.getItem(backendAuthKey) !== null
    );
  } catch {
    // Storage blocked (private browsing, embedded webview). Treat as no
    // session: the reader can still use the secret prompt, which needs nothing.
    return false;
  }
}

/**
 * Returns the verified session, or `null` for every way of not having one.
 *
 * `null` covers signed out, signed in as an ordinary reader, an expired or
 * revoked token, a deleted account, and the API being unreachable. They are
 * deliberately not distinguished: the caller's response to all of them is the
 * same (show the secret prompt), and a UI that named them would be guessing at
 * the server's reason from the outside.
 */
export async function probeAdminAccount(
  deps: AdminAccountProbeDeps
): Promise<AdminAccountSession | null> {
  let token: string | null = null;
  try {
    token = await deps.getToken();
  } catch {
    return null;
  }
  if (!token) return null;

  let body: unknown;
  try {
    body = await deps.whoami(token);
  } catch {
    // A 403 lands here, and so does a network failure. Neither is an admin.
    return null;
  }

  return readWhoami(body, token);
}

/**
 * Read the server's answer, and require it to actually say yes.
 *
 * Split out and exported because this is the fail-open seam: "the request did
 * not throw" is not "the server authorized you". A 200 whose body is a cached
 * error page, an unrelated JSON document, or a future response that dropped the
 * field must not open the dashboard, so the grant is keyed on `authorized`
 * being literally `true` and nothing else.
 */
export function readWhoami(body: unknown, token: string): AdminAccountSession | null {
  if (typeof body !== "object" || body === null) return null;
  const answer = body as { authorized?: unknown; email?: unknown };
  if (answer.authorized !== true) return null;
  return {
    token,
    email: typeof answer.email === "string" && answer.email ? answer.email : null,
  };
}
