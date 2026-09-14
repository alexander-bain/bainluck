const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Header carrying the second token for destructive routes. Must match
 *  `DESTRUCTIVE_TOKEN_HEADER` in `backend/app/routes/admin_utils.py`. */
export const DESTRUCTIVE_TOKEN_HEADER = "X-Admin-Destructive-Token";

/**
 * Fetch an admin endpoint with Authorization header instead of ?secret= query param.
 *
 * `destructiveToken` is sent ONLY when explicitly passed (see `lib/destructiveToken.ts`).
 * It is deliberately not attached to every admin request: the routes that need it are a
 * censused set of 15, and sending a second credential on reads that cannot use it just
 * widens where it can be observed for no gain.
 */
export async function adminFetch(
  path: string,
  secret: string,
  options?: RequestInit,
  destructiveToken?: string | null
): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_URL}${path}`;
  return fetch(url, {
    ...options,
    headers: {
      ...options?.headers,
      Authorization: `Bearer ${secret}`,
      ...(destructiveToken ? { [DESTRUCTIVE_TOKEN_HEADER]: destructiveToken } : {}),
    },
  });
}

/**
 * The error `adminFetchJSON` throws, carrying the HTTP status it came from.
 *
 * #6024: the status was previously readable only by parsing it back out of the
 * message, so every caller treated "the credential in this tab was rejected"
 * and "the system is broken" as the same event and rendered both as Critical
 * system health. A caller that needs to tell them apart uses
 * `isAdminAuthError`, never a substring of `.message`.
 *
 * Extends Error, so existing `error.message` call sites are unaffected.
 */
export class AdminApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`Admin API error ${status}: ${body}`);
    this.name = "AdminApiError";
    this.status = status;
    this.body = body;
  }
}

/**
 * True when the failure is the server refusing this credential (401/403) rather
 * than a fault in the thing being asked about.
 *
 * Deliberately narrow: 404/500/503 are NOT auth failures and must keep reading
 * as real faults. An unknown error shape is not an auth failure either — the
 * safe default is to keep showing the error, not to blame the credential.
 */
export function isAdminAuthError(err: unknown): boolean {
  return (
    err instanceof AdminApiError && (err.status === 401 || err.status === 403)
  );
}

/** Convenience: fetch + parse JSON. Throws `AdminApiError` on non-OK response. */
export async function adminFetchJSON<T = unknown>(
  path: string,
  secret: string,
  options?: RequestInit,
  destructiveToken?: string | null
): Promise<T> {
  const res = await adminFetch(path, secret, options, destructiveToken);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new AdminApiError(res.status, text.slice(0, 300));
  }
  return res.json();
}
