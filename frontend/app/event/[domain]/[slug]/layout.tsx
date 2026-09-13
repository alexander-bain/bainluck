import type { Metadata } from "next";

import { withSiteSuffix } from "@/lib/eventShareMeta";
import {
  buildEventConceptShareCopy,
  type EventConceptShareSource,
} from "@/lib/eventConceptShareMeta";
import { selfCanonical } from "@/lib/routeMetadata";
import { defaultShareCard } from "@/lib/shareCard";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * Segments this route will spend a request on.
 *
 * `generateMetadata` runs on every crawl and both segments are
 * attacker-supplied, so a path that could never name a concept is refused here
 * rather than upstream. Real keys are `event:<domain>:<slug>` where the domain
 * is an adapter name (`ufc`, `election`, `tennis`, `golf`, `awards`, `f1`) and
 * the slug is lowercase kebab — a date token (`26sep15`), a headliner
 * (`contender-series-hunt-vs-perea-26sep15`) or a name slug
 * (`us-open-men-s-singles-winner`). `/events/[id]` and `/tournaments/[slug]`
 * screen their segments for the same reason.
 */
const DOMAIN = /^[a-z0-9][a-z0-9-]{0,31}$/;
const SLUG = /^[a-z0-9][a-z0-9-]{0,95}$/;

/**
 * The concept envelope, or null.
 *
 * `GET /api/event/{key}` takes no projection parameter, so this is the whole
 * envelope — 2 KB for a fight card, 36 KB for the midterms, 1.1 MB for a tennis
 * winner field carrying per-competitor history. It is the same call the page
 * already makes, and `revalidate: 300` means one per route per five minutes
 * rather than one per crawl; a narrower projection is a backend change and is
 * not this ship.
 *
 * A metadata request must never take the page down over a card, so every
 * failure path returns `null` and the copy falls back.
 */
async function fetchConcept(
  domain: string,
  slug: string
): Promise<EventConceptShareSource | null> {
  if (!DOMAIN.test(domain) || !SLUG.test(slug)) return null;

  try {
    const response = await fetch(
      `${API_URL}/api/event/${encodeURIComponent(`event:${domain}:${slug}`)}`,
      { next: { revalidate: 300 } }
    );
    // A key with no concept answers 404, and that is the ONLY honest "this is
    // not an event" signal here — the page renders client-side and answers 200
    // for a typo, which is why the unfurl could not tell the two apart in the
    // first place.
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

/**
 * #5833 — a pasted `/event/<domain>/<slug>` link used to unfurl as the home
 * page.
 *
 * The route had no layout, so it inherited the root's metadata whole: the site
 * title, the site card, and `canonical`/`og:url` naming
 * `https://www.bainluck.com`. Every event-concept link therefore told search
 * engines it was a duplicate of the home page and told a share sheet that a
 * share of the 2026 Midterms was a share of the front door — including the link
 * in the bottom nav of every page on the site.
 *
 * ═══ THE CANONICAL FOLLOWS THE PAYLOAD'S OWN SLUG ═══
 *
 * A concept is reachable by two slugs: the bare key (`26sep15`, which Discover
 * and search cards link with) and the pretty one the backend supplies
 * (`contender-series-hunt-vs-perea-26sep15`). Both resolve — verified against
 * production, the pretty form answers 200 and returns the same canonical key.
 * The page already upgrades the address bar to the pretty slug in a
 * `useEffect`; a crawler never runs it, so the two URLs have been indexed as
 * two pages. When the payload names a slug, that is the canonical here.
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
  params: Promise<{ domain: string; slug: string }>;
}): Promise<Metadata> {
  const { domain, slug } = await params;
  const concept = await fetchConcept(domain, slug);

  const canonicalSlug = concept?.event?.slug?.trim() || slug;
  const path = `/event/${encodeURIComponent(domain)}/${encodeURIComponent(canonicalSlug)}`;
  const identity = selfCanonical(path);

  if (!concept) {
    // Unresolvable: still say "this page is itself" — a page that cannot name
    // its event is not thereby the home page — but claim no event and no
    // probability.
    return {
      ...identity,
      title: "Event Odds",
      description: "Every market on this event, as one clean probability.",
      openGraph: {
        title: withSiteSuffix("Event Odds"),
        description: "Every market on this event, as one clean probability.",
        url: path,
        siteName: "Bain Luck",
        images: defaultShareCard(),
      },
    };
  }

  const { title, description } = buildEventConceptShareCopy(concept);
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

export default function EventConceptLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
