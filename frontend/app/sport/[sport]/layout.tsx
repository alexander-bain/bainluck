import type { Metadata } from "next";

import { defaultShareCard } from "@/lib/shareCard";

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
    // LAT-P278: no canonical of its own meant this inherited the root's
    // `canonical: "/"` and declared itself a duplicate of the homepage.
    alternates: { canonical: `/sport/${sport}` },
    openGraph: {
      title: `${name} - BainLuck`,
      description: `${name} odds and win probabilities across all leagues.`,
      url: `/sport/${sport}`,
      // Explicit: `generateMetadata` does NOT inherit the root
      // `opengraph-image` (lib/shareCard.ts carries the measured table).
      images: defaultShareCard(),
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
