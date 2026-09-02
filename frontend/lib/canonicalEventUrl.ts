/**
 * Q050 — where to send a reader who arrived on a duplicate event url.
 *
 * `/api/events/{id}` answers a market-born duplicate with the row it duplicates
 * (ruling 048's drain clause, read side), so the `id` in the payload can differ
 * from the `id` in the path. The event page must then MOVE, not just render:
 * every sibling fetch on it — history, game markets, tournament, team
 * progression — is keyed on the route's id, so rendering the canonical event in
 * place would put a FINAL hero above an empty chart and no markets.
 *
 * Pure and framework-free on purpose. `frontend/jest` is `testEnvironment:
 * node` with no jsdom, so a `useEffect` has no render path to assert against;
 * the decision lives here where it can be tested, and the page's only job is to
 * hand the answer to `router.replace`.
 */
export function canonicalEventHref(
  requestedEventId: number,
  servedEventId: number | null | undefined,
  query?: string | null,
): string | null {
  // Nothing to correct: no payload yet, or the url was already right. Returning
  // `null` rather than the current href matters — the caller feeds this
  // straight to `router.replace`, and replacing with the page you are already
  // on is a re-render loop, not a no-op.
  if (!servedEventId || servedEventId === requestedEventId) return null;

  // A `NaN` route id (`/events/whatever`) is not a duplicate to redirect; it is
  // a bad url, and the page's own error handling owns it.
  if (!Number.isFinite(requestedEventId)) return null;

  const suffix = query ? `?${query}` : "";
  return `/events/${servedEventId}${suffix}`;
}
