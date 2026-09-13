import { ImageResponse } from "next/og";

import { UnfurlCard } from "@/components/og/UnfurlCard";
import { collectionCardCopy, playoffShare } from "@/lib/collectionShareMeta";
import { unresolvedCardCopy } from "@/lib/unresolvedCardCopy";

export const runtime = "edge";
export const alt = "Bain Luck championship grid";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The card a pasted `/playoffs/<slug>` link unfurls with.
 *
 * Before this, the route had no words and no picture of its own:
 * `/playoffs/nfl` was byte-identical to the home page in title, description,
 * `og:title` and `og:image`, measured on production 2026-09-13. The full read
 * is in `lib/collectionShareMeta.ts`.
 *
 * ═══ THE ONE CARD IN THIS SHIP WITH A DEAD BRANCH ═══
 *
 * It is the one route of the four whose absence is decidable without a request:
 * the fourteen leagues with a championship grid are a local table, and the PAGE
 * renders "League Not Found" and a picker for every other slug. So the card
 * says the same thing the page does, in the family's existing voice
 * (`unresolvedCardCopy`) rather than a fifth one — and it draws the same SHAPE
 * as the live card, which is what stops a dead link rendering the live layout
 * with its facts defaulted (the #5846 defect, where `/events/<id>` answered a
 * rotted link with "Away" against "Home" at 50% each).
 *
 * Both branches are `.../lib` decisions, so this route is two spreads and has
 * nothing a test cannot reach.
 */
export default async function Image({
  params,
}: {
  params: Promise<{ sport: string }>;
}) {
  const { sport } = await params;
  const share = playoffShare(sport);

  return new ImageResponse(
    <UnfurlCard
      {...(share
        ? collectionCardCopy(share)
        : unresolvedCardCopy("bracket", "not-found"))}
    />,
    size,
  );
}
