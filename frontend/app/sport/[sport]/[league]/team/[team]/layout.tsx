import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ sport: string; league: string; team: string }>;
}): Promise<Metadata> {
  const { sport, league, team } = await params;
  const name = team
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
  const leagueUpper = league.toUpperCase();

  const path = `/sport/${sport}/${league}/team/${team}`;

  return {
    title: `${name} ${leagueUpper} Odds & Probabilities — Bain Luck`,
    description: `${name} win probabilities, championship odds, upcoming ${leagueUpper} schedule, and season futures.`,
    // LAT-P278: a team page had NO canonical of its own, so it inherited the
    // root layout's `canonical: "/"` and told search engines every team page in
    // the site was a duplicate of the homepage. Measured on production
    // 2026-09-08: the Red Sox team page served a canonical pointing at the bare
    // apex origin. Relative here, so it resolves against `metadataBase` and
    // names one host.
    alternates: { canonical: path },
    openGraph: {
      title: `${name} — ${leagueUpper} — Bain Luck`,
      description: `${name} ${leagueUpper} odds, schedule, and championship path.`,
      url: path,
      // Explicit: `generateMetadata` does NOT inherit the root
      // `opengraph-image` (lib/shareCard.ts carries the measured table).
      images: defaultShareCard(),
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
