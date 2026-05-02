import type { Metadata } from "next";

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

  return {
    title: `${name} ${leagueUpper} Odds & Probabilities — Bain Luck`,
    description: `${name} win probabilities, championship odds, upcoming ${leagueUpper} schedule, and season futures.`,
    openGraph: {
      title: `${name} — ${leagueUpper} — Bain Luck`,
      description: `${name} ${leagueUpper} odds, schedule, and championship path.`,
      url: `https://bainluck.com/sport/${sport}/${league}/team/${team}`,
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
