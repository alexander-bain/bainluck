/**
 * #6024 — the two-value state behind the admin secret gate.
 *
 * It is a module of its own because the transition that matters — "the secret
 * this tab is holding was refused, put the prompt back and say why" — is only
 * reachable in the provider by clicking, and this suite has no DOM to click in
 * (no jsdom, no testing-library; render tests are `renderToStaticMarkup`).
 * Pure functions here mean the transition is asserted directly, and
 * `AdminSecretPrompt` is asserted to draw the state they produce.
 */
/**
 * Which credential this tab is presenting.
 *
 * `account` — the Google account the reader is already signed into Bain Luck
 * with (#5952). `secret` — the shared machine token, typed in.
 *
 * The distinction is NOT an authorization decision, and nothing in the browser
 * treats it as one: the server re-decides on every request either way. It
 * exists so the UI can say true things — which credential was refused, what the
 * control to fix it should say, and whether there is a session to sign out of.
 */
export type AdminAuthMode = "account" | "secret";

export interface AdminAuthState {
  /** The bearer this tab sends. `null` ⇒ show the prompt. */
  secret: string | null;
  /** Which credential `secret` is. */
  mode: AdminAuthMode;
  /** The email the SERVER resolved, for display only. Never sent, never trusted. */
  email: string | null;
  /** True when the prompt is showing because the server refused the last one. */
  rejected: boolean;
}

/** The opening state: no credential, and no accusation about a previous one. */
export const ADMIN_AUTH_INITIAL: AdminAuthState = {
  secret: null,
  mode: "secret",
  email: null,
  rejected: false,
};

/**
 * Adopt a verified admin account session (#5952).
 *
 * Only ever called with a `{token, email}` the SERVER returned from
 * `/api/admin/whoami` — see `lib/adminAccountSession.ts`. The email is carried
 * for display; it is not a credential and removing it would change nothing
 * about what the server allows.
 */
export function adminAuthAccount(token: string, email: string | null): AdminAuthState {
  return { secret: token, mode: "account", email, rejected: false };
}

/**
 * Replace the account token with a freshly-minted one.
 *
 * A Firebase ID token lasts an hour, and /admin is a tab you leave open. This
 * is how the session survives that without the reader doing anything.
 *
 * It is a NO-OP unless the tab is on the account path. That guard is the point
 * of the function: a token arriving while the reader is holding a typed secret
 * (they signed in on another tab, a timer fired after they switched) must never
 * overwrite the credential they chose, and must never silently upgrade a
 * `secret` session into an `account` one.
 */
export function adminAuthRefreshToken(
  state: AdminAuthState,
  token: string | null
): AdminAuthState {
  if (state.mode !== "account" || !state.secret) return state;
  if (!token || token === state.secret) return state;
  return { ...state, secret: token };
}

/**
 * Take a secret the reader typed.
 *
 * It is NOT validated here and must not be: the server is the only judge of a
 * secret, and a client-side opinion about one is either useless or a bypass.
 * Trimming and the non-empty check are input hygiene, nothing more. `rejected`
 * clears because the accusation belonged to the previous attempt.
 */
export function adminAuthSubmit(input: string): AdminAuthState {
  return { secret: input.trim(), mode: "secret", email: null, rejected: false };
}

/**
 * Drop the secret and return to the prompt.
 *
 * `rejected: true` is the 403 path — the reader is told the secret was refused.
 * The default (the sidebar's "Change admin secret") is a deliberate swap, which
 * accuses nothing.
 */
export function adminAuthClear(opts?: { rejected?: boolean }): AdminAuthState {
  return {
    secret: null,
    mode: "secret",
    email: null,
    rejected: opts?.rejected ?? false,
  };
}
