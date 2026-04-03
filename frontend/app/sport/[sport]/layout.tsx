import type { Metadata } from "next";

const SPORT_NAMES: Record<string, string> = {
  golf: "Golf",
  basketball: "Basketball",
  football: "Football",
  hockey: "Hockey",
  baseball: "Baseball",
  soccer: "Soccer",
  tennis: "Tennis",
  mma: "MMA",
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ sport: string }>;
}): Promise<Metadata> {
  const { sport } = await params;
  const name = SPORT_NAMES[sport] || sport;
  return {
    title: `${name} Odds & Probabilities - BainLuck`,
    description: `Win probabilities, championship odds, and betting market analysis for ${name}. See odds translated into intuitive probabilities.`,
    openGraph: {
      title: `${name} - BainLuck`,
      description: `${name} odds and win probabilities across all leagues.`,
      url: `https://bainluck.com/sport/${sport}`,
    },
  };
}

export default function SportDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
