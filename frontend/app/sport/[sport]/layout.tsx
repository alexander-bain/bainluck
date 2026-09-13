import type { Metadata } from "next";

import { sportShare } from "@/lib/collectionShareMeta";
import { withSiteSuffix } from "@/lib/eventShareMeta";
import { selfCanonical } from "@/lib/routeMetadata";
import { buildShareUrl } from "@/lib/share";

/**
 * LAT-P278 gave this route its own `canonical` and its own `openGraph` words.
 * It did not give it a picture or a `twitter` block. Measured with a crawler UA
 * on production 2026-09-13:
 *
 *   <title>        Football Odds &amp; Probabilities - BainLuck
 *   og:title       Football - BainLuck
 *   og:image       https://www.bainluck.com/opengraph-image
 *   twitter:title  Bain Luck — Prediction Market Discovery
 *   twitter:image  https://www.bainluck.com/opengraph-image
 *
 * Two defects in one read. The card was the site's house card — the same
 * picture `/tournaments/us-open` and the front door both used, md5
 * `99618661539802337202ef69dc6595bc`. And an omitted `twitter` block inherits
 * the ROOT's, so on X — where a sport link is most likely to be pasted — the
 * preview said "Bain Luck — Prediction Market Discovery" beside a card that
 * said the same, with nothing naming the sport at all.
 *
 * The third thing fixed here is the brand: "BainLuck" unspaced is not the
 * wordmark, which `__tests__/chartFooterOneSourceLegend4083.test.tsx` already
 * asserts one surface over. It was in the tab and in `og:title`.
 *
 * ⚠️ `title` carries the suffix HERE and is bare on this ship's `/categories`
 * and `/playoffs` routes. `app/sport/layout.tsx` sets a plain-string `title`,
 * which REPLACES the root's `%s | Bain Luck` template for everything beneath
 * it — so a bare title on this route ships brandless. That ancestor is shared
 * with other lanes' routes and is not changed here;
 * `__tests__/collectionUnfurlCard.test.tsx` reads it and asserts the split, so
 * the day it grows a template the guard says so instead of a reader finding
 * "Football | Bain Luck | Bain Luck" in a tab.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ sport: string }>;
}): Promise<Metadata> {
  const { sport } = await params;
  const path = `/sport/${encodeURIComponent(sport)}`;
  const share = sportShare(sport);
  const socialTitle = withSiteSuffix(share.name);
  const image = buildShareUrl(`${path}/opengraph-image`);

  return {
    ...selfCanonical(path),
    title: withSiteSuffix(share.pageTitle),
    description: share.description,
    openGraph: {
      title: socialTitle,
      description: share.description,
      url: path,
      siteName: "Bain Luck",
      type: "website",
      images: [{ url: image, alt: share.name, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description: share.description,
      images: [image],
    },
  };
}

export default function SportDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
