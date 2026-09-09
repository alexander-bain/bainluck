/**
 * THE DEFAULT SHARE CARD, FOR THE ROUTES THAT DO NOT INHERIT IT.
 *
 * ═══ THE TRAP THIS FILE EXISTS TO CLOSE ═══
 *
 * `app/opengraph-image.tsx` reaches SOME descendant segments and not others.
 * Measured against built HTML on 2026-09-08 (LAT-P278), reading the rendered
 * `<meta>` tags out of the real production build:
 *
 *   | route                                  | metadata source    | og:image  |
 *   |----------------------------------------|--------------------|-----------|
 *   | `/sports`, `/calibration`, `/politics` | static `metadata`  | inherited |
 *   | `/discover`                            | static `metadata`  | inherited |
 *   | `/discover/stats`                      | static `metadata`  | **NONE**  |
 *   | `/sport/[sport]`                       | `generateMetadata` | **NONE**  |
 *   | `/sport/[sport]/[league]`              | `generateMetadata` | **NONE**  |
 *   | `/sport/[sport]/[league]/team/[team]`  | `generateMetadata` | **NONE**  |
 *
 * The routes that lost the picture include the team and league pages — the URLs
 * a fan actually pastes into a group chat. The failure is silent: the build is
 * valid, the page is fine, and the only symptom is a small grey card in someone
 * else's iMessage.
 *
 * ⚠️ **Note rows 2 and 3.** `/discover` and `/discover/stats` are the same kind
 * of declaration, one segment apart, and they disagree. The first attempt at
 * this fix assumed "only `generateMetadata` loses it" and would have shipped
 * `/discover/stats` still broken. So the rule here is deliberately NOT a theory
 * of Next's merge order:
 *
 *     a route that declares `openGraph` declares its own `images`.
 *
 * `__tests__/shareUnfurl.test.ts` enforces exactly that over the app directory,
 * and then reads the built HTML back to prove the tag actually rendered.
 *
 * ⚠️ **Do not add a `?hash` to the URL.** Next appends its own cache-busting
 * query to the file-based route; hardcoding one here would pin a stale build's
 * hash and 404 after the next deploy.
 */

/**
 * The site's default 1200x630 card, as an `openGraph.images` value.
 *
 * Relative on purpose: Next resolves it against `metadataBase` (the one host,
 * `lib/siteUrl.ts`), so this cannot be the thing that reintroduces the apex.
 *
 * A getter rather than a shared constant for two reasons: Next's `OGImage[]` is
 * mutable, so a `readonly` tuple does not typecheck against it; and handing
 * every route the SAME array object would let one route's metadata pipeline
 * mutate the card every other route is using.
 */
export function defaultShareCard(): OGImageLike[] {
  return [
    {
      url: "/opengraph-image",
      width: 1200,
      height: 630,
      alt: "Bain Luck — see what the world thinks will happen, as probabilities.",
    },
  ];
}

interface OGImageLike {
  url: string;
  width: number;
  height: number;
  alt: string;
}
