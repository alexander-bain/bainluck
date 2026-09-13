import type { Metadata } from "next";
import type { FuturesMarketDetailResponse, FuturesOutcome } from "@/lib/types";
import { buildShareUrl, formatShareProbability, truncateShareText } from "@/lib/share";
import { pickHeroOutcome, leaderLabel, futuresTitleText } from "@/lib/futuresDetailDisplay";
import {
  unresolvedMetadata,
  unresolvedPath,
  type ResolutionFailure,
} from "@/lib/unresolvedShareMeta";

type FuturesMarketMetadata = FuturesMarketDetailResponse & {
  image_url?: string | null;
  hook_description?: string | null;
};

/** The market, or WHY there is no market — #5840 needs the two apart. */
type MarketLookup =
  | { ok: true; market: FuturesMarketMetadata }
  | { ok: false; failure: ResolutionFailure };

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/**
 * #5840: a 404 and a bad minute are NOT the same answer.
 *
 * This used to return `null` for both, and the miss branch then claimed the
 * market did not exist. Claiming absence on a 500 or a dropped connection would
 * `noindex` a real market for as long as the failure lasted, so absence is
 * claimed only on a 404 — the one status that means it — or on a segment that
 * could never be an id at all.
 */
async function fetchMarket(id: string): Promise<MarketLookup> {
  const marketId = Number.parseInt(id, 10);
  if (!Number.isFinite(marketId) || marketId <= 0) {
    return { ok: false, failure: "not-found" };
  }

  try {
    const response = await fetch(`${API_URL}/api/futures/${marketId}`, {
      next: { revalidate: 60 },
    });
    if (response.status === 404) return { ok: false, failure: "not-found" };
    if (!response.ok) return { ok: false, failure: "unavailable" };
    return { ok: true, market: await response.json() };
  } catch {
    return { ok: false, failure: "unavailable" };
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
  const lookup = await fetchMarket(id);
  if (!lookup.ok) {
    // #5840 — this branch used to return title+description and nothing else, so
    // Next inherited the root's `canonical: "/"` and `og:url: "/"` and a dead
    // market link previewed as the Bain Luck home page.
    return unresolvedMetadata(unresolvedPath("futures", id), "market", lookup.failure);
  }

  const market = lookup.market;
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
