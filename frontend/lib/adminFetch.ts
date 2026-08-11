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

/** Convenience: fetch + parse JSON. Throws on non-OK response. */
export async function adminFetchJSON<T = unknown>(
  path: string,
  secret: string,
  options?: RequestInit,
  destructiveToken?: string | null
): Promise<T> {
  const res = await adminFetch(path, secret, options, destructiveToken);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Admin API error ${res.status}: ${text.slice(0, 300)}`);
  }
  return res.json();
}
