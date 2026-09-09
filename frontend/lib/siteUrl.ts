/**
 * THE ONE CANONICAL ORIGIN, SO THE SITE CANNOT NAME TWO HOSTS.
 *
 * ═══ WHY THIS FILE EXISTS ═══
 *
 * Alex's distribution audit (2026-09-08) found every canonical URL and every
 * `og:url` on the site naming the APEX while the served host is `www`:
 *
 *   > og:url = apex while serving www -> unfurlers split canonical
 *
 * Measured on production the same evening: `https://bainluck.com/` answers
 * `301` -> `https://www.bainluck.com/`, and `https://www.bainluck.com/` answers
 * `200` with no redirect. So `www` is the host that actually serves, and every
 * apex URL we emit is (a) a redirect hop an unfurler may not follow and (b) a
 * second identity for search and share counts to split across.
 *
 * The literal `https://bainluck.com` was hardcoded in **21 places** — 12 page
 * layouts' `openGraph.url`, `metadataBase`, the JSON-LD block, `robots.ts`,
 * `sitemap.ts` and `share.ts`. That is not 21 bugs; it is one fact written 21
 * times, which is why fixing it by hand would have left the 22nd caller to
 * drift the moment someone adds a page. The fact lives here once.
 *
 * ⚠️ **PREFER A RELATIVE URL TO IMPORTING THIS.** Next resolves a relative
 * `openGraph.url` / `alternates.canonical` against `metadataBase`, so a page
 * layout should write `url: "/sports"` and import nothing. This constant is for
 * the handful of places that genuinely need an absolute origin and cannot see
 * `metadataBase`: `metadataBase` itself, JSON-LD, `robots.ts`, `sitemap.ts`,
 * and the client-side share-link builder.
 *
 * `NEXT_PUBLIC_SITE_URL` still overrides, unchanged — preview deployments set
 * it so a Vercel preview does not advertise production URLs.
 */

/** The production origin. `www`, because that is the host that serves 200. */
export const SITE_URL = "https://www.bainluck.com";

/**
 * The origin this deployment should advertise, with no trailing slash.
 *
 * Reads `NEXT_PUBLIC_SITE_URL` first so previews can name themselves; falls
 * back to the production origin.
 */
export function getSiteUrl(): string {
  return (process.env.NEXT_PUBLIC_SITE_URL || SITE_URL).replace(/\/$/, "");
}
