/**
 * THE PATHS NO CRAWLER IS INVITED TO FETCH.
 *
 * One list, read by two callers that must never disagree:
 *
 *   * `app/robots.ts` emits it as `Disallow:` lines — the actual instruction.
 *   * `__tests__/shareUnfurl.test.ts` uses it to exempt those routes from the
 *     rule that every page self-canonicalises.
 *
 * ═══ WHY THE EXEMPTION IS THE HONEST ANSWER, NOT A HOLE ═══
 *
 * `/admin/*` inherits the root `canonical: "/"` like every other unfixed route
 * (#4193). The obvious fix — give it `robots: { index: false }` — is advice a
 * crawler can never read: it would have to FETCH the page to see the meta tag,
 * and robots.txt already told it not to. A `Disallow:` is the stronger and
 * earlier signal, and it is already in place.
 *
 * So these prefixes are deliberately left inheriting. Deriving the exemption
 * from the disallow list rather than hardcoding route names makes that decision
 * self-maintaining in the direction that matters: **the day someone opens
 * `/admin` to crawlers, the guard immediately starts demanding canonicals for
 * it.** A hand-written exemption list would have stayed silent.
 *
 * ⚠️ Adding a prefix here does not just change robots.txt — it also switches off
 * a correctness guard for everything underneath it. Add public content paths at
 * your peril.
 */

/**
 * Root-relative path prefixes disallowed in robots.txt.
 *
 * `/admin` — staff-only tooling, not content.
 * `/api/`  — the proxy routes; machine surfaces with no reader.
 * `/share/` — ephemeral share redirects; the destination is the content.
 */
export const CRAWLER_DISALLOWED_PREFIXES = ["/admin", "/api/", "/share/"] as const;

/** Is this root-relative path one robots.txt tells crawlers to skip? */
export function isCrawlerDisallowed(path: string): boolean {
  return CRAWLER_DISALLOWED_PREFIXES.some((prefix) => path.startsWith(prefix));
}
