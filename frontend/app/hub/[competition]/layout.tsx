import type { Metadata } from "next";

import { withSiteSuffix } from "@/lib/eventShareMeta";
import { buildHubShareCopy, type HubShareSource } from "@/lib/hubShareMeta";
import { selfCanonical } from "@/lib/routeMetadata";
import { buildShareUrl } from "@/lib/share";
import {
  unresolvedMetadata,
  unresolvedPath,
  type ResolutionFailure,
} from "@/lib/unresolvedShareMeta";

/** The hub, or WHY there is none — a 404 and a bad minute are not the same. */
type HubLookup =
  | { ok: true; hub: HubShareSource }
  | { ok: false; failure: ResolutionFailure };

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * Segments this route will spend a request on.
 *
 * `generateMetadata` runs on every crawl and the segment is attacker-supplied,
 * so a path that could never name a competition is refused here rather than
 * upstream. Real keys are the five short lowercase names the nav links —
 * `mma`, `boxing`, `golf`, `tennis`, `esports` — and the backend's config is
 * keyed the same way. `/event/[domain]/[slug]` and `/tournaments/[slug]` screen
 * their segments for the same reason.
 */
const COMPETITION = /^[a-z0-9][a-z0-9-]{0,31}$/;

/**
 * The hub envelope, or why not.
 *
 * This is the same call the page already makes, and `revalidate: 300` means one
 * per hub per five minutes rather than one per crawl. The payload is not small
 * — `/hub/tennis` carries 182 markets across four sections — and only four of
 * its scalar fields are read here; a projection parameter would be a backend
 * change and is not this ship.
 *
 * A metadata request must never take the page down over a card, so every
 * failure path returns a `failure` rather than throwing.
 */
async function fetchHubMeta(competition: string): Promise<HubLookup> {
  if (!COMPETITION.test(competition)) return { ok: false, failure: "not-found" };

  try {
    const response = await fetch(
      `${API_URL}/api/hub/${encodeURIComponent(competition)}`,
      { next: { revalidate: 300 } }
    );
    // A competition with no config answers 404 — measured on production
    // 2026-09-13 09:47Z, `/api/hub/not-a-real-competition-99999` is a clean 404
    // while all five real hubs are 200. That is the ONLY honest "this is not a
    // competition" signal here, because the page renders client-side and
    // answers 200 for a typo, which is why the unfurl could not tell a real hub
    // from a fake one in the first place.
    //
    // Anything else — a 500, a timeout, a body that will not parse — is
    // `"unavailable"`: still self-canonical, still carrying its own card, but
    // claiming nothing about whether the hub exists and never `noindex`-ed.
    // Deindexing `/hub/tennis` because the API was restarting would be a worse
    // and more durable outcome than the defect being repaired (gotcha #53).
    if (response.status === 404) return { ok: false, failure: "not-found" };
    if (!response.ok) return { ok: false, failure: "unavailable" };
    return { ok: true, hub: await response.json() };
  } catch {
    return { ok: false, failure: "unavailable" };
  }
}

/**
 * #5877 — a pasted `/hub/<competition>` link used to unfurl as the home page.
 *
 * The route had no layout, so it inherited the root's metadata whole: the site
 * title, the site card, and `canonical`/`og:url` naming
 * `https://www.bainluck.com`. Measured with a crawler UA on production at
 * 09:46:33Z, all five hubs and a competition that does not exist were
 * BYTE-IDENTICAL in metadata — the card could not tell `/hub/tennis` from a
 * typo, and `index, follow` on top asked search engines to index all six as
 * duplicates of the front door.
 *
 * `/hub/mma`, `/hub/boxing`, `/hub/golf`, `/hub/tennis` and `/hub/esports` are
 * hardcoded in both `BottomNav` and `DesktopNav`, so this was five links on the
 * navigation of every page on the site.
 *
 * ═══ THE CANONICAL IS THE SEGMENT, NOT A PAYLOAD FIELD ═══
 *
 * Unlike `/event/[domain]/[slug]`, a hub has exactly one address. The payload's
 * `competition` echoes the key that was requested rather than offering a
 * prettier alias, so there is no second URL to consolidate and the requested
 * segment IS the page.
 *
 * It is still passed through `encodeURIComponent`. ⚠️ On today's code that call
 * is PROVABLY A NO-OP and no test can catch its removal: this branch only runs
 * for a segment that already passed `COMPETITION`, which admits nothing outside
 * `[a-z0-9-]`. It is kept because the screen and the canonical are two
 * independent decisions, and the day someone widens the regex — to admit a dot,
 * an underscore, a unicode name — the encoding is what stops a crafted request
 * canonicalising to a path that is not this page. `unresolvedPath` does the same
 * job on the branch where it is NOT a no-op, and that one is asserted.
 *
 * `selfCanonical` supplies the identity half (`alternates.canonical`,
 * `openGraph.url`, and the default card — the root `opengraph-image` provably
 * does not reach every descendant, see `lib/shareCard.ts`). It is spread FIRST
 * so the explicit `openGraph` below wins, and that block restates `url` and
 * `images` rather than relying on a merge: a partial `openGraph` is how
 * `/discover/stats` ended up asking for a large card and supplying no picture.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ competition: string }>;
}): Promise<Metadata> {
  const { competition } = await params;
  const lookup = await fetchHubMeta(competition);

  if (!lookup.ok) {
    // Unresolvable: still say "this page is itself" — a page that cannot name
    // its competition is not thereby the home page — but claim no competition
    // and no probability.
    //
    // ...and it names THIS route's card in both namespaces. Next's file
    // convention overrides `og:image` only, so without the fourth argument a
    // dead `/hub/<typo>` would preview as the quiet "isn't on Bain Luck" card
    // in Slack and as the home page on X — the split measured on production for
    // `/events/[id]` and `/futures/[id]`, which still have it.
    const deadPath = unresolvedPath("hub", competition);
    return unresolvedMetadata(
      deadPath,
      "hub",
      lookup.failure,
      buildShareUrl(`${deadPath}/opengraph-image`),
    );
  }

  const path = `/hub/${encodeURIComponent(competition)}`;
  const identity = selfCanonical(path);

  const { title, description } = buildHubShareCopy(lookup.hub, competition);
  const socialTitle = withSiteSuffix(title);
  // This route's OWN card, not the site's. `opengraph-image.tsx` beside this
  // file is the picture; Next's file convention would win over `images` anyway
  // (measured, `lib/unresolvedShareMeta.ts`), but naming it here keeps the
  // source honest about what ships and satisfies the "a route that declares
  // openGraph declares its images" rule with the right value rather than the
  // default card. The other five card-shipping routes state theirs the same way.
  const image = buildShareUrl(`${path}/opengraph-image`);

  return {
    ...identity,
    title,
    description,
    openGraph: {
      title: socialTitle,
      description,
      url: path,
      siteName: "Bain Luck",
      type: "website",
      images: [{ url: image, alt: title, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description,
      images: [image],
    },
  };
}

export default function HubLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
