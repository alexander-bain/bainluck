/**
 * A LINK THAT NO LONGER RESOLVES SAYS SO. IT DOES NOT IMPERSONATE THE HOME PAGE.
 *
 * ═══ WHAT WENT WRONG (#5840) ═══
 *
 * `/events/<id>` and `/futures/<id>` are the two routes check 8 names — "a
 * pasted game/market link unfurls with plain probability copy". Their LIVE half
 * is correct. Their DEAD half, read with a crawler UA against production at
 * 2026-09-13 07:48:01Z:
 *
 *   /events/99999999   og:title  Bain Luck — Prediction Market Discovery
 *                      og:url    https://www.bainluck.com
 *                      canonical https://www.bainluck.com
 *                      robots    index, follow
 *   /futures/99999999  identical.
 *
 * Both layouts' miss branch returned `{ title, description }` and nothing else,
 * so Next inherited the root's `canonical: "/"` and `openGraph.url: "/"`
 * LITERALLY — the mechanism `lib/routeMetadata.ts` documents, and the same
 * defect #5813 (tournaments) and #5833 (event concepts) already fixed on their
 * own routes. These two were the last on the list.
 *
 * A rotted link therefore previewed as the front door: the site title, the site
 * blurb, and the route's own OG card rendered empty — `Prediction market`, a
 * `- -` glyph where the probability goes, `0 outcomes tracked`. It never said
 * the thing was gone.
 *
 * ═══ WHY TWO FAILURES AND NOT ONE ═══
 *
 * ⚠️ The fetchers returned `null` for a 404 and for a 5xx or a dropped
 * connection ALIKE. Collapsing those is the trap in this fix rather than in the
 * bug: telling a crawler that a real market is "not on Bain Luck" — and
 * `noindex`-ing it — because the API was restarting is a worse outcome than the
 * defect being repaired, and it is silent and durable in a way the defect is
 * not.
 *
 * So absence is claimed ONLY on the signal that means absence. Measured
 * 2026-09-13 07:49Z: `GET /api/events/99999999` and `GET /api/futures/99999999`
 * answer `404`; `GET /api/events/15310371` answers `200`. Anything else — a
 * 500, a timeout, a body that will not parse — is `"unavailable"`: still
 * self-canonical, still carrying its own card, but claiming nothing about
 * whether the thing exists and never `noindex`-ed.
 *
 * This is gotcha #53 in the shape it takes in a metadata function: "it did not
 * answer" is not "it is not there".
 *
 * ═══ WHY THE COPY LIVES HERE AND NOT IN THE TWO LAYOUTS ═══
 *
 * Two routes, one voice — the reason `eventShareMeta`, `tournamentShareMeta`
 * and `eventConceptShareMeta` are each their own pure module. It also makes the
 * copy assertable without a browser or a build, which is what
 * `__tests__/unresolvedShareMeta5840.test.ts` does.
 */

import type { Metadata } from "next";

import { withSiteSuffix } from "@/lib/eventShareMeta";
import { selfCanonical } from "@/lib/routeMetadata";
import { defaultShareCard } from "@/lib/shareCard";

/** Which of the two things a link can name. */
export type UnresolvedSubject = "game" | "market";

/**
 * Why the payload did not arrive.
 *
 * `"not-found"` is reserved for a signal that MEANS absence — a 404, or a
 * segment that could never be an id. Everything else is `"unavailable"`.
 */
export type ResolutionFailure = "not-found" | "unavailable";

export interface UnresolvedCopy {
  /**
   * The `<title>`, WITHOUT a site suffix — the root layout's template is
   * `%s | Bain Luck` and appends one. `app/events/[id]/layout.tsx` used to
   * return `"Event Odds - Bain Luck"` here, which the template rendered as
   * `Event Odds - Bain Luck | Bain Luck` in the tab of every dead game link.
   */
  title: string;
  description: string;
}

const SUBJECT_NOUN: Record<UnresolvedSubject, string> = {
  game: "game",
  market: "market",
};

/**
 * What the preview says, for each of the four cases.
 *
 * Plain English and no diagnostics (notice 34): a reader is told the link does
 * not lead anywhere and what the site is for. No status code, no "the upstream
 * API returned", no invitation to retry.
 *
 * The `"unavailable"` copy is deliberately the SAME neutral text the two
 * layouts already shipped. That branch is not a new claim — it is the old
 * fallback, now merely saying which page it is on.
 */
export function unresolvedShareCopy(
  subject: UnresolvedSubject,
  failure: ResolutionFailure
): UnresolvedCopy {
  const noun = SUBJECT_NOUN[subject];

  if (failure === "not-found") {
    return {
      title: `This ${noun} isn't on Bain Luck`,
      description:
        subject === "game"
          ? "There's no game at this link. See today's games and what the world thinks will happen, as probabilities."
          : "There's no market at this link. See what the world thinks will happen, as probabilities.",
    };
  }

  return subject === "game"
    ? {
        title: "Game Odds",
        description: "Game probabilities translated into plain English.",
      }
    : {
        title: "Market Odds",
        description: "Prediction market probabilities translated into plain English.",
      };
}

/**
 * The whole metadata object for a link that did not resolve.
 *
 * `selfCanonical` supplies the identity half and is spread FIRST so the
 * explicit `openGraph` below wins; that block restates `url` and `images`
 * rather than relying on a merge, because a partial `openGraph` is how
 * `/discover/stats` ended up asking for a large card and supplying no picture
 * (`lib/shareCard.ts`).
 *
 * `twitter` is stated rather than omitted: an omitted `twitter` block inherits
 * the ROOT's, which is the home page's title and the home page's card — the
 * same defect one namespace over.
 *
 * ⚠️ On `/events/[id]` and `/futures/[id]` the `images` supplied here is NOT the
 * picture that ships. Both segments have a file-convention
 * `opengraph-image.tsx`, and Next's file convention WINS over
 * `openGraph.images` — measured on the built app, the rendered tag is
 * `og:image  …/events/99999999/opengraph-image?509a39…`, one tag, not the site
 * card. The value stays because this builder is shared and because
 * `shareUnfurl.test.ts` requires any route declaring `openGraph` to declare its
 * own `images`; on a route with no image file it is the picture. The dead
 * link's PICTURE is therefore still the route's own card rendered empty
 * (`Prediction market`, a `- -` glyph, `0 outcomes tracked`) and is a separate
 * fix — it cannot be verified in this sandbox, because the OG routes fetch
 * their font over the network and egress is blocked, so it needs a Vercel
 * preview to see.
 *
 * `robots` is set only for `"not-found"`. A URL that names nothing should not
 * be indexed, but a page that merely could not be fetched this minute must not
 * be deindexed for it.
 *
 * @param path Root-relative, already encoded by the caller. `selfCanonical`
 *   refuses an absolute URL (`assertRoutePath`), which is what keeps a
 *   user-supplied segment from becoming an off-site canonical.
 */
export function unresolvedMetadata(
  path: string,
  subject: UnresolvedSubject,
  failure: ResolutionFailure
): Metadata {
  const { title, description } = unresolvedShareCopy(subject, failure);
  const socialTitle = withSiteSuffix(title);
  const card = defaultShareCard();

  return {
    ...selfCanonical(path),
    title,
    description,
    ...(failure === "not-found" ? { robots: { index: false, follow: true } } : {}),
    openGraph: {
      title: socialTitle,
      description,
      url: path,
      siteName: "Bain Luck",
      images: card,
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description,
      images: card.map((image) => image.url),
    },
  };
}

/**
 * The route path for a segment that did NOT resolve to a row.
 *
 * The resolved branches canonicalise to the payload's own id, so
 * `/futures/86832?x` and `/futures/86832` agree. There is no id to ask here, so
 * the requested segment is what the page is — percent-encoded, which keeps
 * `//evil.example` and `../` a single inert path segment rather than a new
 * origin or a climb out of the route.
 */
export function unresolvedPath(base: "events" | "futures", segment: string): string {
  return `/${base}/${encodeURIComponent(segment)}`;
}
