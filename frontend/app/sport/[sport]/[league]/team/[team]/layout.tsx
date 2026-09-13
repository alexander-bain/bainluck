import type { Metadata } from "next";

import { selfCanonical } from "@/lib/routeMetadata";
import { buildShareUrl } from "@/lib/share";
import {
  buildTeamShareCopy,
  classifyTeamShare,
  fetchTeamShare,
} from "@/lib/teamShareMeta";
import { unresolvedMetadata, unresolvedPath } from "@/lib/unresolvedShareMeta";

/**
 * A pasted team link unfurls as THAT TEAM, picture and all.
 *
 * ═══ WHAT CHANGED ═══
 *
 * The route already had a title, a description and a canonical of its own
 * (LAT-P278). What it did not have was a PICTURE: `images: defaultShareCard()`
 * in both namespaces, so every team page in the site previewed with the same
 * house card. Measured on production 2026-09-13 12:31:54Z — see
 * `lib/teamShareMeta.ts` for the read. `opengraph-image.tsx` beside this file
 * is the card; this names it.
 *
 * The other change is that the NAME and the LEAGUE are now the payload's. They
 * used to be a title-cased slug and `league.toUpperCase()` — the route segment
 * — so a K League 1 team's tab and og:title read "KOREA_KLEAGUE1". That is
 * #5847 exactly, one surface over from the page it was fixed on.
 *
 * ═══ THE THREE BRANCHES ═══
 *
 * A team, a team at the wrong address (#5852), or nothing. The split is
 * `classifyTeamShare`'s and the words are `buildTeamShareCopy`'s, so this
 * function chooses nothing; it fetches and assembles. The unresolved branch
 * hands its card to `unresolvedMetadata`'s fourth argument, because the file
 * convention overrides `og:image` and NOT `twitter:image` — without it a dead
 * team link would preview as the quiet card in Slack and as the home page on X,
 * the split #5846 measured and closed on `/events` and `/futures`.
 *
 * `robots: noindex` is right for the wrong-sport branch too and is stated here
 * rather than inherited: that URL is a real page serving a refusal, and asking
 * search engines to index one per (sport, slug) pair is 282 measured duplicates
 * of a sentence.
 */
export async function generateMetadata({
  params,
}: {
  params: Promise<{ sport: string; league: string; team: string }>;
}): Promise<Metadata> {
  const { sport, league, team } = await params;
  const lookup = await fetchTeamShare(sport, league, team);
  const verdict = classifyTeamShare(lookup, sport);

  const path = unresolvedPath("sport", sport, league, "team", team);
  const image = buildShareUrl(`${path}/opengraph-image`);

  if (verdict.kind === "unresolved") {
    return unresolvedMetadata(path, "team", verdict.failure, image);
  }

  const { title, description, socialTitle } = buildTeamShareCopy(verdict, league);
  const identity = selfCanonical(path);

  return {
    ...identity,
    title,
    description,
    ...(verdict.kind === "off-route"
      ? { robots: { index: false, follow: true } }
      : {}),
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

export default function TeamLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
