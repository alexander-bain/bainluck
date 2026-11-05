/**
 * LAB TRAFFIC — our own browsers say so, and the visitor counts skip them (#12030).
 *
 * 216 of GA4's 224 web users in 28 days (Oct 7 – Nov 3, 2026) were our own
 * Browser audit (`.github/workflows/browser-audit.yml`): a daily scheduled run
 * from GitHub's Azure runners, two Playwright device profiles ("Desktop Chrome"
 * reports Windows, "Pixel 5" reports Android), and a consent pack that accepts
 * the banner about four times per profile with a fresh browser context each —
 * 8 new "users" a day, 27 days, 216. Every web retention figure was the lab's.
 *
 * The flag is ONE query parameter, `?bl_lab=<name>` (lowercase letters, digits,
 * dashes; up to 40). On first sight it is kept in localStorage, so the rest of
 * that browser's visit — later navigations, a second tab — stays marked
 * without every URL carrying it. A lab that controls its browser context can
 * write the same key directly before the first page script runs.
 *
 * What a marked visit changes, and nothing else:
 *  - GA4 hits carry `traffic_type: 'internal'` (`core.ts`), which GA4's
 *    Internal Traffic data filter excludes once that filter is Active;
 *  - Vercel Web Analytics drops the visit in its `beforeSend` (`TelemetryGate`).
 * The consent choice, the banner and every gate still behave exactly as for a
 * person — the consent pack exists to prove that, so the lab must still see
 * the real behaviour.
 *
 * Pure and total like the rest of this directory: no throw reaches a caller.
 */

export const LAB_TRAFFIC_PARAM = 'bl_lab';
export const LAB_TRAFFIC_STORAGE_KEY = 'bainluck_lab_traffic';

const LAB_NAME = /^[a-z0-9-]{1,40}$/;

function validName(value: string | null | undefined): string | null {
  return value && LAB_NAME.test(value) ? value : null;
}

/** The lab's name when this browser is marked as our own lab traffic, else null. */
export function readLabTraffic(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const fromUrl = validName(
      new URLSearchParams(window.location.search).get(LAB_TRAFFIC_PARAM),
    );
    if (fromUrl) {
      try {
        localStorage.setItem(LAB_TRAFFIC_STORAGE_KEY, fromUrl);
      } catch {
        // Storage refused: this page is still marked by its URL.
      }
      return fromUrl;
    }
    return validName(localStorage.getItem(LAB_TRAFFIC_STORAGE_KEY));
  } catch {
    return null;
  }
}
