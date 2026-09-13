import { ImageResponse } from "next/og";

import { UnfurlCard } from "@/components/og/UnfurlCard";
import { collectionCardCopy, leagueShare } from "@/lib/collectionShareMeta";

export const runtime = "edge";
export const alt = "Bain Luck league probabilities";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The card a pasted `/sport/<sport>/<league>` link unfurls with.
 *
 * `/sport/football/nfl` is, with the team page, the URL a fan is most likely to
 * paste into a group chat — and measured on production 2026-09-13 it named
 * `https://www.bainluck.com/opengraph-image` in both namespaces while
 * `twitter:title` read "Bain Luck — Prediction Market Discovery". The full read
 * is in `lib/collectionShareMeta.ts`.
 *
 * The accent comes from the SPORT segment rather than the league — `nfl` is not
 * a key in `CATEGORY_ACCENT` and keying on it would draw all 26 leagues in the
 * same default green, which is the defect `hubCardCopy` was written to stop.
 * That decision is `leagueShare`'s, not this file's, so a test can reach it.
 */
export default async function Image({
  params,
}: {
  params: Promise<{ sport: string; league: string }>;
}) {
  const { sport, league } = await params;

  return new ImageResponse(
    <UnfurlCard {...collectionCardCopy(leagueShare(sport, league))} />,
    size,
  );
}
