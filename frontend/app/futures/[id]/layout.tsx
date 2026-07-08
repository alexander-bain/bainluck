import type { Metadata } from "next";
import type { FuturesMarketDetailResponse, FuturesOutcome } from "@/lib/types";
import { buildShareUrl, formatShareProbability, truncateShareText } from "@/lib/share";
import { pickHeroOutcome, leaderLabel, futuresTitleText } from "@/lib/futuresDetailDisplay";

type FuturesMarketMetadata = FuturesMarketDetailResponse & {
  image_url?: string | null;
  hook_description?: string | null;
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

async function fetchMarket(id: string): Promise<FuturesMarketMetadata | null> {
  const marketId = Number.parseInt(id, 10);
  if (!Number.isFinite(marketId) || marketId <= 0) return null;

  try {
    const response = await fetch(`${API_URL}/api/futures/${marketId}`, {
      next: { revalidate: 60 },
    });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

function topOutcome(market: FuturesMarketMetadata): FuturesOutcome | null {
  const outcomes = market.outcomes ?? market.top_outcomes ?? [];
  if (outcomes.length === 0) return null;
  return [...outcomes].sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))[0];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const market = await fetchMarket(id);
  if (!market) {
    return {
      title: "Market Odds",
      description: "Prediction market probabilities translated into plain English.",
    };
  }

  const leader = topOutcome(market);
  const probability = formatShareProbability(leader?.probability);
  // #883 L2-55: a settled market's title must NOT carry the last-traded % — it's
  // "<winner> won", mirroring the L2-53 hero. Same winner selection as the page.
  const isResolved = market.status === "resolved";
  const outcomes = market.outcomes ?? market.top_outcomes ?? [];
  const winnerName = isResolved ? leaderLabel(pickHeroOutcome(outcomes, leader, true)) : null;

  const titleText = futuresTitleText({
    marketName: market.name,
    isResolved,
    winnerName,
    leaderName: leader?.name,
    probabilityLabel: probability,
  });
  const description = truncateShareText(
    market.hook_description ||
      (isResolved && winnerName
        ? `${winnerName} won ${market.name}. See the full probability board on Bain Luck.`
        : leader && probability
          ? `${leader.name} leads ${market.name} at ${probability}. See the full probability board on Bain Luck.`
          : `See ${market.name} translated into intuitive probabilities on Bain Luck.`)
  );
  const url = buildShareUrl(`/futures/${market.id}`);
  const image = buildShareUrl(`/futures/${market.id}/opengraph-image`);

  return {
    title: titleText,
    description,
    alternates: { canonical: url },
    openGraph: {
      title: `${titleText} | Bain Luck`,
      description,
      url,
      siteName: "Bain Luck",
      type: "article",
      images: [{ url: image, alt: market.name, width: 1200, height: 630 }],
    },
    twitter: {
      card: "summary_large_image",
      title: `${titleText} | Bain Luck`,
      description,
      images: [image],
    },
  };
}

export default function FuturesDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
