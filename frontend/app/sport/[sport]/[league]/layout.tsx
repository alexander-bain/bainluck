import type { Metadata } from "next";

import { leagueShare } from "@/lib/collectionShareMeta";
import { withSiteSuffix } from "@/lib/eventShareMeta";
import { selfCanonical } from "@/lib/routeMetadata";
import { buildShareUrl } from "@/lib/share";

/**
 * The same two defects as `app/sport/[sport]/layout.tsx`, on the URL a fan is
 * most likely to paste. Measured with a crawler UA on production 2026-09-13:
 *
 *   /sport/football/nfl   <title>        NFL Odds &amp; Schedule - BainLuck
 *                         og:title       NFL - BainLuck
 *                         og:image       https://www.bainluck.com/opengraph-image
 *                         twitter:title  Bain Luck — Prediction Market Discovery
 *   /sport/basketball/nba  the same, with "NBA".
 *
 * The house card and an inherited `twitter` block: a pasted NFL link previewed
 * on X as the home page, and in Slack as the home page's picture beside the
 * word "NFL".
 *
 * `LEAGUE_NAMES` moved to `lib/collectionShareMeta.ts` as
 * `LEAGUE_DISPLAY_NAMES` — the card's headline and this `<title>` are the same
 * string, and the day they come from two tables is the day one says "NFL" and
 * the other "Nfl".
 *
 * ⚠️ `title` carries the suffix here. See the ⚠️ in `app/sport/[sport]/layout.tsx`.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ sport: string; league: string }>;
}): Promise<Metadata> {
  const { sport, league } = await params;
  const path = `/sport/${encodeURIComponent(sport)}/${encodeURIComponent(league)}`;
  const share = leagueShare(sport, league);
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

export default function LeagueLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
