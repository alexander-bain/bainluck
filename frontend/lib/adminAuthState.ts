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
export interface AdminAuthState {
  /** The secret this tab is holding. `null` ⇒ show the prompt. */
  secret: string | null;
  /** True when the prompt is showing because the server refused the last one. */
  rejected: boolean;
}

/** The opening state: no secret, and no accusation about a previous one. */
export const ADMIN_AUTH_INITIAL: AdminAuthState = { secret: null, rejected: false };

/**
 * Take a secret the reader typed.
 *
 * It is NOT validated here and must not be: the server is the only judge of a
 * secret, and a client-side opinion about one is either useless or a bypass.
 * Trimming and the non-empty check are input hygiene, nothing more. `rejected`
 * clears because the accusation belonged to the previous attempt.
 */
export function adminAuthSubmit(input: string): AdminAuthState {
  return { secret: input.trim(), rejected: false };
}

/**
 * Drop the secret and return to the prompt.
 *
 * `rejected: true` is the 403 path — the reader is told the secret was refused.
 * The default (the sidebar's "Change admin secret") is a deliberate swap, which
 * accuses nothing.
 */
export function adminAuthClear(opts?: { rejected?: boolean }): AdminAuthState {
  return { secret: null, rejected: opts?.rejected ?? false };
}
