import { ImageResponse } from "next/og";

import { UnfurlCard } from "@/components/og/UnfurlCard";
import { categoryShare, collectionCardCopy } from "@/lib/collectionShareMeta";

export const runtime = "edge";
export const alt = "Bain Luck category probabilities";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The card a pasted `/categories/<slug>` link unfurls with.
 *
 * Before this, the route had no words and no picture of its own: measured with
 * a crawler UA on production 2026-09-13, `/categories/politics` served the home
 * page's title, the home page's description and
 * `https://www.bainluck.com/opengraph-image` in both namespaces. The full read
 * is in `lib/collectionShareMeta.ts`.
 *
 * ═══ NO FETCH, AND NO DEAD BRANCH ═══
 *
 * Every sibling card in this family fetches. This one cannot usefully: the
 * PAGE resolves its own `<h1>` from `getCategoryByKey(slug)` with a title-cased
 * fallback and never 404s, so there is no absence to discover and nothing a
 * round trip would add but latency on a path every crawl hits. `categoryShare`
 * makes the same call the page makes, which is what keeps the picture and the
 * page agreeing by construction.
 *
 * A slug this site has no category for is therefore drawn, not refused —
 * correctly, because the page renders it too.
 */
export default async function Image({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  return new ImageResponse(
    <UnfurlCard {...collectionCardCopy(categoryShare(slug))} />,
    size,
  );
}
