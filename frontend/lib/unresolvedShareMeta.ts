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

/**
 * Which of the five things a link can name — one per unfurl route.
 *
 * `"tournament"` and `"event"` joined in #5861. Their two routes were fixed by
 * #5813 and #5833 and are correct about `canonical` and `og:url`; what neither
 * declared was a `twitter` block, so a dead link on either still sent the home
 * page's `twitter:title` and `twitter:description`. Adopting this builder
 * closes that and settles the voice — the same condition was reading "This game
 * isn't on Bain Luck" on two routes and "Tournament Odds" on another.
 *
 * `"hub"` joined in #5877, the last real route on check 8's ratchet. It is the
 * one subject whose NOUN is not its own name: the segment is `[competition]`,
 * the nav calls these pages "MMA" and "Tennis", and no reader has ever called
 * one a hub. "Hub" is our word for the route; "competition" is the reader's
 * word for the thing, and `SUBJECT_NOUN` exists precisely so the two can differ.
 *
 * `"team"` joined with `/sport/[sport]/[league]/team/[team]`'s own card. Only
 * the `"not-found"` branch is ever reached on that route from a segment that
 * names nothing; the WRONG-SPORT case (#5852) is not this subject and must not
 * use it, because "this team isn't on Bain Luck" is false about a team that is
 * on Bain Luck at a different address. `lib/teamShareMeta.ts` owns that one.
 *
 * `"bracket"` joined with the four collection routes (`lib/collectionShareMeta.ts`).
 * It is the one subject whose absence is decided WITHOUT a request: the fourteen
 * leagues that have a championship grid are a local table, and
 * `/playoffs/<anything-else>` renders "League Not Found" and a league picker for
 * exactly the slugs that table misses. So `"not-found"` here is as well-founded
 * as a 404 is elsewhere — and `"unavailable"` is UNREACHABLE from that route,
 * because there is nothing to be unavailable. A `Record` keyed on this union has
 * to carry an entry for it anyway; the tables below say so where it happens
 * rather than leaving a reader to wonder which branch ships.
 */
export type UnresolvedSubject =
  | "game"
  | "market"
  | "tournament"
  | "event"
  | "hub"
  | "team"
  | "bracket";

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
  tournament: "tournament",
  event: "event",
  hub: "competition",
  team: "team",
  // "Bracket" and not "playoff grid": the page's own `<h1>` says "Championship
  // Grid", but that is the name of the TABLE on it. A reader who pasted
  // `/playoffs/nfl` was after the bracket.
  bracket: "bracket",
};

/**
 * The `"unavailable"` copy, which is the text each route ALREADY shipped.
 *
 * That branch is not a new claim — it is the old fallback, now merely saying
 * which page it is on. Keeping the existing words is what makes this table
 * reviewable: every string here can be found in the route it came from.
 *
 * ⚠️ `hub` is the one exception, and it is worth stating rather than hiding:
 * `/hub/[competition]` shipped NO fallback text, because it declared no
 * metadata at all — that was #5877's defect. So its two strings are new, and
 * they are written to the pattern of the four above rather than to taste.
 */
const UNAVAILABLE_COPY: Record<UnresolvedSubject, UnresolvedCopy> = {
  game: {
    title: "Game Odds",
    description: "Game probabilities translated into plain English.",
  },
  market: {
    title: "Market Odds",
    description: "Prediction market probabilities translated into plain English.",
  },
  tournament: {
    title: "Tournament Odds",
    description: "Every contender's chance of winning, as one clean probability.",
  },
  event: {
    title: "Event Odds",
    description: "Every market on this event, as one clean probability.",
  },
  hub: {
    title: "Competition Odds",
    description: "Every market in this competition, as one clean probability.",
  },
  // The words `app/sport/[sport]/[league]/team/[team]/layout.tsx` already
  // shipped, reduced to the subject: its title was
  // `"<Name> <LEAGUE> Odds & Probabilities"`, which cannot be said when the
  // name is exactly what did not arrive.
  team: {
    title: "Team Odds",
    description: "Win probabilities, championship odds and season futures, as one clean number.",
  },
  // ⚠️ UNREACHABLE from `/playoffs/[sport]`, and deliberately so: that route
  // resolves against a local table, so it never has a payload that could fail
  // to arrive. Present because the `Record` demands it. If a later ship gives
  // the bracket a fetch, this is the text it starts from — don't invent a
  // second voice for it then.
  bracket: {
    title: "Championship Grid",
    description: "Every team's road to the title, as one clean probability.",
  },
};

/** The second sentence of the `"not-found"` copy — what the site offers instead. */
const NOT_FOUND_INVITATION: Record<UnresolvedSubject, string> = {
  game: "See today's games and what the world thinks will happen, as probabilities.",
  market: "See what the world thinks will happen, as probabilities.",
  tournament: "See every contender's chance of winning, as one clean probability.",
  event: "See what the world thinks will happen, as probabilities.",
  hub: "See the sports and competitions we cover, as probabilities.",
  team: "See today's games and what the world thinks will happen, as probabilities.",
  bracket: "See the leagues with a championship grid, and who the season is going to.",
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
  if (failure === "not-found") {
    const noun = SUBJECT_NOUN[subject];
    return {
      title: `This ${noun} isn't on Bain Luck`,
      description: `There's no ${noun} at this link. ${NOT_FOUND_INVITATION[subject]}`,
    };
  }

  return UNAVAILABLE_COPY[subject];
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
 * ⚠️ On a segment holding a file-convention `opengraph-image.tsx`, the default
 * card passed here is NOT the picture that ships: Next's file convention WINS
 * over `openGraph.images`. Measured on the built app, the rendered tag is
 * `og:image  …/events/99999999/opengraph-image?509a39…`, one tag, not the site
 * card.
 *
 * ═══ WHICH IS WHY `image` EXISTS (#5888) ═══
 *
 * The file convention overrides `og:image` and NOT `twitter:image`, so a segment
 * with its own card used to emit two different pictures on one dead link.
 * Measured on production 2026-09-13:
 *
 *   /events/99999999   og:image       …/events/99999999/opengraph-image?509a39…
 *                      twitter:image  https://www.bainluck.com/opengraph-image
 *   /futures/99999999  the same split
 *
 * X reads the `twitter:` namespace, so a rotted link previewed there as the home
 * page while the same link in Slack previewed as the route's own card — the
 * defect #5861 fixed for the title and description, one tag over. A caller that
 * ships its own card passes it here and both namespaces name it.
 *
 * Callers with no `opengraph-image.tsx` pass nothing and keep the site card,
 * which is correct for them: on those routes it really is the picture.
 *
 * That residue was taken by #5846. `/events/[id]` and `/futures/[id]` now pass
 * their own card here, so all four routes name one picture in both namespaces,
 * and their image routes draw `UnfurlCard`'s quiet shape on a miss instead of
 * the live layout with its facts replaced by defaults. The events card was the
 * worse of the two and is worth naming: it did not render empty, it rendered
 * "Away" against "Home" at 50% each — an invented game on a link that names
 * nothing. `lib/unresolvedCardCopy.ts` owns that decision for both.
 *
 * (The older note here said that card "cannot be verified in this sandbox,
 * because the OG routes fetch their font over the network". Measured false on
 * 2026-09-13: no OG route fetches a font. What reaches the network is satori's
 * `loadAdditionalAsset` resolving the 🍀 emoji, so a card with no emoji renders
 * locally and in CI — which is how #5888's before/after was shot.)
 *
 * `robots` is set only for `"not-found"`. A URL that names nothing should not
 * be indexed, but a page that merely could not be fetched this minute must not
 * be deindexed for it.
 *
 * @param path Root-relative, already encoded by the caller. `selfCanonical`
 *   refuses an absolute URL (`assertRoutePath`), which is what keeps a
 *   user-supplied segment from becoming an off-site canonical.
 * @param image Absolute URL of the segment's OWN `opengraph-image`, for callers
 *   that ship one. Omit it and both namespaces keep the site card.
 */
export function unresolvedMetadata(
  path: string,
  subject: UnresolvedSubject,
  failure: ResolutionFailure,
  image?: string
): Metadata {
  const { title, description } = unresolvedShareCopy(subject, failure);
  const socialTitle = withSiteSuffix(title);
  const card = image
    ? [{ url: image, width: 1200, height: 630, alt: title }]
    : defaultShareCard();

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
 * The route path for segments that did NOT resolve to a row.
 *
 * The resolved branches canonicalise to the payload's own id or slug, so
 * `/futures/86832?x` and `/futures/86832` agree. There is nothing to ask here,
 * so the requested segments are what the page is — percent-encoded, which keeps
 * `//evil.example` and `../` a single inert path segment rather than a new
 * origin or a climb out of the route.
 *
 * ⚠️ The encoding is the point, and it is not decoration. Next hands
 * `generateMetadata` a DECODED segment, so a `[slug]` param can already contain
 * `/` or `..`; `app/tournaments/[slug]/layout.tsx` interpolated it raw
 * (`/tournaments/${slug}`) and would canonicalise such a request to a path that
 * is not the page.
 *
 * Variadic because `/event/[domain]/[slug]` is two segments and each must be
 * encoded separately — encoding them joined would escape the slash between them.
 */
export function unresolvedPath(base: string, ...segments: string[]): string {
  return `/${base}/${segments.map(encodeURIComponent).join("/")}`;
}
