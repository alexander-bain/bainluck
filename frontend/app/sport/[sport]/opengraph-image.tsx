import { ImageResponse } from "next/og";

import { UnfurlCard } from "@/components/og/UnfurlCard";
import { collectionCardCopy, sportShare } from "@/lib/collectionShareMeta";

export const runtime = "edge";
export const alt = "Bain Luck sport probabilities";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The card a pasted `/sport/<sport>` link unfurls with.
 *
 * This route's WORDS were already its own — `og:title: "Football - BainLuck"`,
 * measured on production 2026-09-13 — and its picture was the house card in
 * both namespaces, with `twitter:title` still reading "Bain Luck — Prediction
 * Market Discovery" because the layout declared no `twitter` block at all.
 * `lib/collectionShareMeta.ts` carries the full read.
 *
 * No fetch, for the reason the sibling category card gives: the name comes from
 * the same local table the layout's `<title>` already used, so a round trip on
 * a path every crawl hits would buy nothing.
 */
export default async function Image({
  params,
}: {
  params: Promise<{ sport: string }>;
}) {
  const { sport } = await params;

  return new ImageResponse(
    <UnfurlCard {...collectionCardCopy(sportShare(sport))} />,
    size,
  );
}
