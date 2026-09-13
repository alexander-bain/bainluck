import type { Metadata } from "next";

import { playoffShare } from "@/lib/collectionShareMeta";
import { withSiteSuffix } from "@/lib/eventShareMeta";
import { selfCanonical } from "@/lib/routeMetadata";
import { buildShareUrl } from "@/lib/share";
import { unresolvedMetadata, unresolvedPath } from "@/lib/unresolvedShareMeta";

/**
 * #4193 gave this route a canonical of its own. It gave it nothing else.
 *
 * Measured with a crawler UA on production 2026-09-13, `/playoffs/nfl` served
 * its own `canonical` and `og:url` and the HOME PAGE's title, description,
 * `og:title`, `og:description`, `twitter:title` and card — byte-identical to
 * `/categories/politics`, the sibling this ship fixes in the same diff. A
 * pasted bracket previewed as the front door.
 *
 * ═══ THE DEAD BRANCH IS DECIDED HERE, NOT UPSTREAM ═══
 *
 * `playoffShare` returns `null` for a slug with no bracket, and that is a
 * well-founded absence rather than a failure to look: the fourteen leagues with
 * a championship grid are a local table (`lib/playoffLeagues.ts`) and the page
 * renders "League Not Found" and a league picker for exactly the slugs it
 * misses. So the `noindex` that `unresolvedMetadata` applies on `"not-found"`
 * is aimed at a URL that really does name nothing — the condition gotcha #53
 * says to be sure of before claiming it.
 *
 * There is no `"unavailable"` branch because there is no request to fail.
 *
 * `title` is bare in both branches: `app/playoffs/layout.tsx` sets none, so the
 * root's `%s | Bain Luck` template reaches this route and appends one. See the
 * ⚠️ in `app/categories/[slug]/layout.tsx` for why the two `/sport` routes in
 * this ship differ, and `__tests__/collectionUnfurlCard.test.tsx` for the guard.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ sport: string }>;
}): Promise<Metadata> {
  const { sport } = await params;
  const share = playoffShare(sport);

  if (!share) {
    // It names this route's OWN card in both namespaces. Without the fourth
    // argument a dead `/playoffs/<typo>` would preview as the quiet "isn't on
    // Bain Luck" card in Slack and as the home page on X — the split measured
    // on production for `/events/[id]` before #5846.
    const deadPath = unresolvedPath("playoffs", sport);
    return unresolvedMetadata(
      deadPath,
      "bracket",
      "not-found",
      buildShareUrl(`${deadPath}/opengraph-image`),
    );
  }

  const path = `/playoffs/${encodeURIComponent(sport)}`;
  const socialTitle = withSiteSuffix(share.name);
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

export default function PlayoffsSportLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
