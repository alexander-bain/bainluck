import type { Metadata } from "next";

import { categoryShare } from "@/lib/collectionShareMeta";
import { withSiteSuffix } from "@/lib/eventShareMeta";
import { selfCanonical } from "@/lib/routeMetadata";
import { buildShareUrl } from "@/lib/share";

/**
 * #4193 gave this route a canonical of its own. It gave it nothing else.
 *
 * Measured with a crawler UA on production 2026-09-13, `/categories/politics`
 * served its own `canonical` and `og:url` and the HOME PAGE's everything else:
 *
 *   <title>         Bain Luck — Prediction Market Discovery
 *   og:title        Bain Luck — Prediction Market Discovery
 *   og:description  See what the world thinks will happen. Explore prediction …
 *   og:image        https://www.bainluck.com/opengraph-image
 *   twitter:title   Bain Luck — Prediction Market Discovery
 *
 * `selfCanonical` returns `openGraph: { url, images }` and no title, and a
 * partial `openGraph` does not stop the root's title reaching the tag — so the
 * fix to "this page is itself" for SEARCH left it still claiming to be the home
 * page for SHARING. Both namespaces are stated in full below, for the reason
 * `lib/unresolvedShareMeta.ts` records: an omitted `twitter` block inherits the
 * root's, and X is where a category link actually goes.
 *
 * The words are `categoryShare`'s, which resolves the name through the same
 * `getCategoryByKey` call the page renders as its `<h1>`.
 *
 * ⚠️ `title` is bare here and suffixed on the two `/sport` routes in this ship.
 * That asymmetry is real: `app/categories/layout.tsx` sets no title, so the
 * ROOT's `%s | Bain Luck` template reaches this route and appends one, while
 * `app/sport/layout.tsx` sets a plain-string title that replaces the template
 * for everything beneath it. `__tests__/collectionUnfurlCard.test.tsx` reads
 * those ancestors and asserts the split, so it is checked rather than
 * remembered.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const path = `/categories/${encodeURIComponent(slug)}`;
  const share = categoryShare(slug);
  const socialTitle = withSiteSuffix(share.name);
  // This route's OWN card. Next's file convention would win over `images` for
  // `og:image` anyway, but NOT for `twitter:image` — the split measured on
  // production for `/events/[id]` — so it is named here and both namespaces
  // point at the same picture.
  const image = buildShareUrl(`${path}/opengraph-image`);

  return {
    ...selfCanonical(path),
    title: share.pageTitle,
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

export default function CategorySlugLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
