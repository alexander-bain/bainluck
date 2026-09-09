/**
 * A PAGE SAYS IT IS ITSELF, NOT THAT IT IS THE HOME PAGE.
 *
 * ═══ WHAT WENT WRONG ═══
 *
 * `app/layout.tsx` sets `alternates: { canonical: "/" }` and
 * `openGraph: { url: "/" }`. Those are the RIGHT values for the root and the
 * WRONG values for everyone else — and in Next they are inherited literally, so
 * a route that does not restate them ships two claims about itself:
 *
 *   <link rel="canonical" href="https://www.bainluck.com">   ← "index the home page instead of me"
 *   <meta property="og:url" content="https://www.bainluck.com">  ← "a share of me is a share of the home page"
 *
 * Measured on production 2026-09-09 (LAT-P280, after #4149 fixed the host):
 * 12 static routes and both dynamic hub families — including `/categories/politics`
 * and `/playoffs/nfl`, which are content pages — declared exactly that. The
 * distribution audit's #1 finding is that non-branded searches return no
 * bainluck.com hits; a site whose inner pages ask not to be indexed has at least
 * one mechanism pointing that way.
 *
 * ═══ WHY A HELPER AND NOT TWELVE HAND-WRITTEN BLOCKS ═══
 *
 * The same mistake was already made once at scale: `lib/siteUrl.ts` exists
 * because the apex origin had been hand-written in 21 places. Twelve hand-written
 * `alternates` blocks is the same shape of debt — the thirteenth page is the one
 * that drifts. One call, one fact.
 *
 * It also makes the two guard rules structurally true rather than remembered:
 *
 *   * **Relative, always.** An absolute URL here is how the apex came back last
 *     time, so `selfCanonical` REFUSES one (see `assertRoutePath`) instead of
 *     trusting a review to catch it. Next resolves the relative path against
 *     `metadataBase`, which names the one host.
 *   * **`openGraph` implies `images`.** `__tests__/shareUnfurl.test.ts` enforces
 *     that any route declaring `openGraph` declares its own card, because the
 *     root card provably does not reach every descendant (`lib/shareCard.ts` has
 *     the measured table). Setting `og:url` without an image would have silently
 *     broken the unfurl #4149 just fixed, so the helper supplies both together.
 *
 * ⚠️ This is for routes a reader can reach and a crawler may fetch. Prefixes in
 * `CRAWLER_DISALLOWED_PREFIXES` (`/admin`, `/api/`, `/share/`) are handled by
 * robots.txt instead — see `lib/crawlPolicy.ts` for why a meta tag on a
 * disallowed path is unreachable advice.
 */

import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

/**
 * The identity metadata for one route: "this page is `path`".
 *
 * Merge into a route's own `metadata` (or `generateMetadata` return) with a
 * spread. Everything else — title, description, robots — keeps inheriting.
 *
 * @param path A root-relative path with a leading slash and no origin,
 *   e.g. `"/privacy"` or `` `/categories/${slug}` ``.
 */
export function selfCanonical(path: string): Metadata {
  assertRoutePath(path);
  return {
    alternates: { canonical: path },
    openGraph: {
      url: path,
      images: defaultShareCard(),
    },
  };
}

/**
 * Refuse anything that is not a root-relative path.
 *
 * Throwing at module-evaluation time is deliberate: these calls run during
 * `next build`, so a bad path fails the build rather than shipping a page that
 * quietly re-advertises the redirecting apex. That is the exact failure #4149
 * spent three rounds on, and a build error is the cheapest place to catch it.
 *
 * The test is `URL`-based rather than a `startsWith("/")` character check —
 * `//evil.example` also starts with a slash and is a protocol-relative ABSOLUTE
 * URL, which is precisely the spelling that walked past the first version of the
 * apex guard (see `isApexUrl` in `__tests__/shareUnfurl.test.ts`).
 */
export function assertRoutePath(path: string): void {
  const resolved = new URL(path, "https://route-path.invalid");
  if (resolved.origin !== "https://route-path.invalid") {
    throw new Error(
      `selfCanonical() takes a root-relative path, got "${path}". ` +
        `An absolute URL here reintroduces the two-host split #4149 fixed; ` +
        `Next resolves a relative path against metadataBase (lib/siteUrl.ts).`
    );
  }
  if (!path.startsWith("/")) {
    throw new Error(
      `selfCanonical() takes a path with a leading slash, got "${path}".`
    );
  }
}
