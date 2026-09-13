import type { Metadata } from "next";

import { withSiteSuffix } from "@/lib/eventShareMeta";
import { selfCanonical } from "@/lib/routeMetadata";
import { defaultShareCard } from "@/lib/shareCard";
import {
  buildTournamentShareCopy,
  type TournamentShareSource,
} from "@/lib/tournamentShareMeta";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * Slugs this route will spend a request on.
 *
 * `/events/[id]` parses an integer for the same reason: the segment is
 * attacker-supplied, `generateMetadata` runs on every crawl, and a path that
 * could never name a register is not worth an upstream round trip. Registered
 * slugs are lowercase kebab (`us-open`, `us-open-2026`), so anything else is
 * refused here rather than 404'd upstream.
 */
const SLUG = /^[a-z0-9][a-z0-9-]{0,63}$/;

/**
 * Why `?sections=first` and not the whole hub.
 *
 * The full payload is ~1.75 MB; `first` is ~1.38 MB and carries `title`,
 * `subtitle` and `boards` — every field the copy reads. `rest` owns `grids` and
 * `results`, which this card does not name. The route's own docs warn that
 * splitting a READER's load into two requests costs ~38% more server work in
 * total; that warning does not apply to a single `first` request, which is
 * strictly less work than the unsplit call it replaces.
 *
 * A metadata request must never take the page down over a card, so every
 * failure path returns `null` and the copy falls back.
 */
async function fetchTournament(slug: string): Promise<TournamentShareSource | null> {
  if (!SLUG.test(slug)) return null;

  try {
    const response = await fetch(
      `${API_URL}/api/tournaments/${encodeURIComponent(slug)}?sections=first`,
      { next: { revalidate: 300 } },
    );
    // A slug with no register answers 404, and that is the ONLY honest "this is
    // not a tournament" signal here — the page itself renders client-side and
    // answers 200 for a typo, which is why the unfurl could not tell the two
    // apart in the first place.
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

/**
 * #5813 — a pasted `/tournaments/<slug>` link used to unfurl as the home page.
 *
 * The route had no layout, so it inherited the root's metadata whole: the site
 * title, the site card, and `canonical`/`og:url` pointing at
 * `https://www.bainluck.com`. Every tournament link therefore told search
 * engines it was a duplicate of the home page and told a share sheet that a
 * share of the US Open was a share of the front door.
 *
 * `selfCanonical` supplies the identity half (`alternates.canonical`,
 * `openGraph.url`, and the default card — the root `opengraph-image` provably
 * does not reach every descendant, see `lib/shareCard.ts`). It is spread FIRST
 * so the explicit `openGraph` below is the one that wins, and that block
 * restates `url` and `images` rather than relying on a merge: a partial
 * `openGraph` is how `/discover/stats` ended up asking for a large card and
 * supplying no picture.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const path = `/tournaments/${slug}`;
  const identity = selfCanonical(path);

  const tournament = await fetchTournament(slug);
  if (!tournament) {
    // Unresolvable: still say "this page is itself" — a page that cannot name
    // its tournament is not thereby the home page — but claim no tournament and
    // no probability.
    return {
      ...identity,
      title: "Tournament Odds",
      description: "Every contender's chance of winning, as one clean probability.",
      openGraph: {
        title: withSiteSuffix("Tournament Odds"),
        description: "Every contender's chance of winning, as one clean probability.",
        url: path,
        siteName: "Bain Luck",
        images: defaultShareCard(),
      },
    };
  }

  const { title, description } = buildTournamentShareCopy(tournament);
  const socialTitle = withSiteSuffix(title);

  return {
    ...identity,
    title,
    description,
    openGraph: {
      title: socialTitle,
      description,
      url: path,
      siteName: "Bain Luck",
      type: "article",
      images: defaultShareCard(),
    },
    twitter: {
      card: "summary_large_image",
      title: socialTitle,
      description,
      images: defaultShareCard().map((image) => image.url),
    },
  };
}

export default function TournamentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
