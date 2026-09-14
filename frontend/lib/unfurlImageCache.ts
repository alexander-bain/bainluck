/**
 * #6049 — HOW LONG AN UNFURL PICTURE MAY BE CACHED IS A PROPERTY OF WHAT IT DRAWS.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-14 02:57-03:05Z ═══
 *
 * `bainluck.com/futures/60276241` pasted into Messages, read at one instant with
 * a crawler UA:
 *
 *   og:description   "Above 1 inch 19%"
 *   og:image         a 96px "26%", a bar at 26%, "Above 1 inch leads at 26%"
 *
 * Two numbers for one question, on one card. `GET /api/futures/60276241` at
 * 02:58Z said `Above 1 inch = 0.19`, `status open` — the TEXT was right and the
 * PICTURE was stale.
 *
 * ═══ WHY THE PICTURE COULD NOT CATCH UP ═══
 *
 * Not a 60-second skew. The picture was frozen until the next DEPLOY. Measured
 * on both routes at 03:05Z, the second on a cold `x-vercel-cache: MISS` with
 * `age: 0`, which is what proves the header is the origin's and not a CDN rule:
 *
 *   cache-control: public, immutable, no-transform, max-age=31536000
 *
 * One year, `immutable`. It comes from `ImageResponse` itself — next@14.2.35,
 * `next/dist/server/og/image-response.js`:
 *
 *   headers: {
 *     "content-type": "image/png",
 *     "cache-control": NODE_ENV === "development" ? … : "public, immutable, …",
 *     ...options.headers          // ← the override, spread AFTER the default
 *   }
 *
 * That default is right for the case the file convention was built for: a
 * `og:image` URL carries a DEPLOYMENT-scoped hash (`?abc750316894a8f6` — at
 * 02:58Z the unrelated `/futures/60544511` served the same token, and both
 * changed at the v4509 deploy), so for a picture drawn from the SOURCE TREE the
 * URL really does change whenever the bytes do. Our two market cards are drawn
 * from a PRICE, which moves under a URL that cannot. So the first crawler to
 * fetch a market after a deploy froze that market's number for every reader
 * until the next one.
 *
 * `fetchMarket`'s `next: { revalidate: 60 }` does not help and never did: it
 * bounds the Data Cache behind the render, not the response the CDN keeps.
 *
 * ═══ THE RULE ═══
 *
 * A picture either draws something that can change on its own, or something
 * that can only be CORRECTED. Those want different windows, and the routes
 * already know which they are drawing.
 *
 * MOVING is the live price — and also the "we couldn't load this" card. That
 * one is not a number, but it is a claim about the world made while the API was
 * restarting (gotcha #53), and `futures/[id]/opengraph-image.tsx` says in its
 * own header that "a picture is harder to take back than a sentence, because
 * the unfurler caches it". A claim we may need to retract must not be immutable
 * for a year; retracting it was, until this file, impossible without a deploy.
 *
 * SETTLED is a finished game's score and a resolved market's winner. Settled
 * means settled, so this could have stayed `immutable` — but our RECORD of a
 * settlement is correctable, and a wrong winner frozen for a year is the one
 * outcome worse than a stale price. `stale-while-revalidate` makes the honest
 * window free: the reader is still served instantly from cache.
 */

/** Which kind of thing the card draws — the whole input to the decision. */
export type UnfurlPictureKind = "moving" | "settled";

/**
 * 60s because that is the window the TEXT half already lives in: both
 * `layout.tsx`'s `generateMetadata` and the image route read the API through a
 * `next: { revalidate: 60 }` fetch. Matching it is what makes the two halves of
 * one card unable to disagree by more than a single revalidation — which is the
 * defect, stated as a bound.
 *
 * `stale-while-revalidate` is the same 60 rather than something generous: it
 * exists so a paste never waits on a cold satori render, not to buy more
 * staleness. Two windows is the worst case a reader can see, and the reader who
 * sees it is the one who refreshes it for everyone behind them.
 *
 * `max-age=0` keeps private caches revalidating; `s-maxage` overrides it for the
 * CDN, which is the only cache we can actually reason about.
 */
export const UNFURL_CACHE_MOVING =
  "public, max-age=0, s-maxage=60, stale-while-revalidate=60";

/**
 * An hour fresh, a day stale-while-revalidate. Long, because the content is
 * genuinely stable and every render we skip is one we do not pay for; finite,
 * because a settlement correction has to be able to reach the picture without a
 * deploy. A reader never waits for this one — inside 24h it is always served
 * from cache.
 */
export const UNFURL_CACHE_SETTLED =
  "public, max-age=0, s-maxage=3600, stale-while-revalidate=86400";

export function unfurlImageCacheControl(kind: UnfurlPictureKind): string {
  return kind === "settled" ? UNFURL_CACHE_SETTLED : UNFURL_CACHE_MOVING;
}

/**
 * The whole second argument to `new ImageResponse(...)`, so a call site cannot
 * pass the size and forget the header — the two routes' four call sites are the
 * entire population, and every one of them wants both.
 */
export function unfurlImageOptions(
  size: { width: number; height: number },
  kind: UnfurlPictureKind,
): { width: number; height: number; headers: Record<string, string> } {
  return { ...size, headers: { "cache-control": unfurlImageCacheControl(kind) } };
}
