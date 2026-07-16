/**
 * SEARCH funnel breadcrumb (Queue L2-133 Item 2 — measurement_spec §2).
 *
 * When a user clicks a search result we drop a short-lived sessionStorage
 * breadcrumb describing the click. The app-wide AnalyticsProvider reads it on the
 * next route and, if the user engages with the destination (dwell/scroll), emits
 * `destination_engaged` — the "Lisa metric" (did they engage with what they
 * found?) — correlated back to the originating query + rank + type.
 *
 * Kept in its own module so the writer (search page) and reader (AnalyticsProvider)
 * agree on the key + shape without importing each other.
 */
export const SEARCH_DEST_KEY = "bl_search_dest";

/** Breadcrumbs older than this are stale — the user browsed elsewhere first. */
export const SEARCH_DEST_MAX_AGE_MS = 60_000;

export interface SearchDestCrumb {
  query: string;
  result_type: string;
  result_id: number | string;
  /** 0-indexed rank of the clicked result in its section. */
  rank: number;
  /** epoch ms when the click happened. */
  ts: number;
}

/** Called on a search result click, just before navigation. */
export function markSearchDestination(crumb: Omit<SearchDestCrumb, "ts">): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.setItem(
      SEARCH_DEST_KEY,
      JSON.stringify({ ...crumb, ts: Date.now() }),
    );
  } catch {
    /* sessionStorage unavailable (private mode / quota) — best-effort only */
  }
}
