import { ImageResponse } from "next/og";

import { UnfurlCard } from "@/components/og/UnfurlCard";
import { hubCardCopy, type HubShareSource } from "@/lib/hubShareMeta";
import type { ResolutionFailure } from "@/lib/unresolvedShareMeta";

export const runtime = "edge";
export const alt = "Bain Luck competition probabilities";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * The same screen `layout.tsx` applies, for the same reason: this route runs on
 * every crawl of an attacker-supplied path, and a segment that could never name
 * a competition is not worth an upstream round trip.
 */
const COMPETITION = /^[a-z0-9][a-z0-9-]{0,31}$/;

type HubLookup =
  | { ok: true; hub: HubShareSource }
  | { ok: false; failure: ResolutionFailure };

/**
 * ═══ WHY THIS FETCHES AGAIN INSTEAD OF TAKING THE LAYOUT'S PAYLOAD ═══
 *
 * It cannot. `opengraph-image.tsx` is its own route handler — a separate request
 * from a separate process, made by the unfurler after it has read the HTML — so
 * there is no layout render in scope to share state with. All four sibling cards
 * fetch twice for the same reason.
 *
 * `revalidate: 300` matches the layout's, so the picture and the words come from
 * the same five-minute window rather than drifting apart.
 *
 * The 404-vs-anything-else split is the layout's, kept because the CARD makes
 * the same claim the title does: "this competition isn't on Bain Luck" is a
 * statement about the world, and saying it because the API was restarting is
 * the failure `unresolvedShareMeta.ts` documents at length (gotcha #53).
 */
async function fetchHubMeta(competition: string): Promise<HubLookup> {
  if (!COMPETITION.test(competition)) return { ok: false, failure: "not-found" };

  try {
    const response = await fetch(
      `${API_URL}/api/hub/${encodeURIComponent(competition)}`,
      { next: { revalidate: 300 } },
    );
    if (response.status === 404) return { ok: false, failure: "not-found" };
    if (!response.ok) return { ok: false, failure: "unavailable" };
    return { ok: true, hub: await response.json() };
  } catch {
    return { ok: false, failure: "unavailable" };
  }
}

/**
 * The card a pasted `/hub/<competition>` link unfurls with.
 *
 * #5877 gave this route its WORDS — before it, all five hubs and a competition
 * that does not exist were byte-identical in metadata, naming the home page. It
 * did not give it a PICTURE, so `/hub/tennis` shipped "Tennis" beside the same
 * house card `/hub/boxing` and the front door use. This is the last of the six
 * routes on check 8's ratchet to draw its own.
 *
 * ═══ THIS CARD HAS NO ROWS, AND THAT IS THE DESIGN ═══
 *
 * Its four siblings lead with a probability because each names ONE question. A
 * hub names a COLLECTION — `/hub/tennis` served 98 matches, 66 props, 17 more
 * markets and 1 future on the morning `hubShareMeta.ts` was written — so there
 * is no single number to quote. Picking one of 182 markets to headline would be
 * arbitrary, and quoting the COUNT would put a fact about our inventory on the
 * most public screen we have, which is what notice 34 exists to prevent.
 *
 * So the card carries what the page itself leads with: the competition's name
 * and the product-written blurb underneath it — the same two fields
 * `buildHubShareCopy` gives the title, from the same call, so the picture and
 * the sentence beside it can never disagree. `UnfurlCard`'s empty-`rows` shape
 * is drawn for exactly this.
 *
 * ═══ WHAT MAKES THE FIVE CARDS DIFFERENT PICTURES ═══
 *
 * The competition's own name, its own blurb, and its own accent — `mma`,
 * `boxing`, `golf`, `tennis` and `esports` are all keys in `CATEGORY_ACCENT`,
 * so each hub's stripe and pill carry that sport's colour. The segment is the
 * signal `UnfurlCard` documents as the one available before the payload is
 * fetched, and it is still available when the fetch fails.
 */
export default async function Image({
  params,
}: {
  params: Promise<{ competition: string }>;
}) {
  const { competition } = await params;
  const lookup = await fetchHubMeta(competition);

  // Every decision is `hubCardCopy`'s, and both branches draw the same shape,
  // so a dead link cannot render the live layout with its facts missing — the
  // open defect on `/events/[id]`, whose dead card draws "Prediction market", a
  // `- -` glyph and "0 outcomes tracked".
  return new ImageResponse(
    <UnfurlCard {...hubCardCopy(lookup, competition)} />,
    size,
  );
}
