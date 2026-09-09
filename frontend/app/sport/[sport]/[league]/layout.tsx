import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

const LEAGUE_NAMES: Record<string, string> = {
  pga: "PGA Tour",
  dpworld: "DP World Tour",
  lpga: "LPGA",
  liv: "LIV Golf",
  kft: "Korn Ferry Tour",
  nba: "NBA",
  wnba: "WNBA",
  ncaab: "NCAA Men's Basketball",
  wncaab: "NCAA Women's Basketball",
  nfl: "NFL",
  ncaaf: "NCAA Football",
  cfl: "CFL",
  ufl: "UFL",
  nhl: "NHL",
  mlb: "MLB",
  ncaa: "College Baseball",
  epl: "Premier League",
  mls: "MLS",
  laliga: "La Liga",
  bundesliga: "Bundesliga",
  seriea: "Serie A",
  ligue1: "Ligue 1",
  ucl: "Champions League",
  atp: "ATP Tour",
  wta: "WTA Tour",
  ufc: "UFC",
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ sport: string; league: string }>;
}): Promise<Metadata> {
  const { sport, league } = await params;
  const name = LEAGUE_NAMES[league] || league.toUpperCase();
  const path = `/sport/${sport}/${league}`;
  return {
    title: `${name} Odds & Schedule - BainLuck`,
    description: `${name} win probabilities, championship odds, upcoming schedule, and event cards. Betting markets translated into intuitive probabilities.`,
    // LAT-P278: no canonical of its own meant this inherited the root's
    // `canonical: "/"` and declared itself a duplicate of the homepage.
    alternates: { canonical: path },
    openGraph: {
      title: `${name} - BainLuck`,
      description: `${name} schedule, odds, and championship grid.`,
      url: path,
      // Explicit because `generateMetadata` does NOT inherit the root
      // `opengraph-image` — see `lib/shareCard.ts` for the measured table.
      images: defaultShareCard(),
    },
  };
}

export default function LeagueLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
