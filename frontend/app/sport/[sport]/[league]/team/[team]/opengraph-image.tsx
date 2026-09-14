import { ImageResponse } from "next/og";

import { UnfurlCard } from "@/components/og/UnfurlCard";
import {
  classifyTeamShare,
  fetchTeamShare,
  teamCardCopy,
} from "@/lib/teamShareMeta";
import { unfurlImageOptions } from "@/lib/unfurlImageCache";

export const runtime = "edge";
export const alt = "Bain Luck team probabilities";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/**
 * The card a pasted team link unfurls with.
 *
 * This is the last route on check 8's ratchet to draw its own picture: measured
 * with a crawler UA on production 2026-09-13 12:31:54Z, the Red Sox, the
 * Celtics and the Chiefs all named `https://www.bainluck.com/opengraph-image`
 * in BOTH namespaces, and `<route>/opengraph-image` was a 404.
 *
 * ═══ WHY THIS FETCHES AGAIN INSTEAD OF TAKING THE LAYOUT'S PAYLOAD ═══
 *
 * It cannot. `opengraph-image.tsx` is its own route handler — a separate
 * request from a separate process, made by the unfurler after it has read the
 * HTML — so there is no layout render in scope to share state with. All five
 * sibling cards fetch twice for the same reason. `fetchTeamShare`'s
 * `revalidate: 300` means the picture and the sentence beside it come from one
 * five-minute window.
 *
 * Every decision — including the accent and whether there is a row at all — is
 * `teamCardCopy`'s, so there is nothing here a test cannot reach. Both the
 * miss branch and the wrong-sport branch draw the same SHAPE as the live one,
 * which is what stops a dead link rendering the live layout with its facts
 * replaced by defaults: the #5846 defect, where `/events/<id>` answered a
 * rotted link with "Away" against "Home" at 50% each.
 */
export default async function Image({
  params,
}: {
  params: Promise<{ sport: string; league: string; team: string }>;
}) {
  const { sport, league, team } = await params;
  const lookup = await fetchTeamShare(sport, league, team);
  const verdict = classifyTeamShare(lookup, sport);

  return new ImageResponse(
    <UnfurlCard {...teamCardCopy(verdict, sport, league)} />,
    // #6166 — THE SPECIMEN. Measured on production 2026-09-14 14:08Z, this
    // route's canonical URL served a picture reading "6%" and "81-68" beside
    // words reading "5%", while `/api/teams/boston-red-sox` said 0.0485 and
    // 82-68. The code was already right — a cache-busted render drew 5% and
    // 82-68 — and the default `immutable, max-age=31536000` that `ImageResponse`
    // supplies had frozen the first render taken after the deploy.
    //
    // MOVING FOR ALL THREE VERDICTS, and no "settled" arm is possible:
    // `TeamShareVerdict` is `team | off-route | unresolved`, none of them
    // terminal. A team is never settled — a record moves every game and a
    // championship probability moves between them, so there is no state in
    // which this card stops being a forecast.
    unfurlImageOptions(size, "moving"),
  );
}
