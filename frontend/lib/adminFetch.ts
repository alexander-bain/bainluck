const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Fetch an admin endpoint with Authorization header instead of ?secret= query param. */
export async function adminFetch(
  path: string,
  secret: string,
  options?: RequestInit
): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_URL}${path}`;
  return fetch(url, {
    ...options,
    headers: {
      ...options?.headers,
      Authorization: `Bearer ${secret}`,
    },
  });
}

/** Convenience: fetch + parse JSON. Throws on non-OK response. */
export async function adminFetchJSON<T = unknown>(
  path: string,
  secret: string,
  options?: RequestInit
): Promise<T> {
  const res = await adminFetch(path, secret, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Admin API error ${res.status}: ${text.slice(0, 300)}`);
  }
  return res.json();
}
