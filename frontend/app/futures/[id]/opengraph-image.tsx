import { ImageResponse } from "next/og";
import type { FuturesMarketDetailResponse, FuturesOutcome } from "@/lib/types";
import { formatShareProbability, truncateShareText } from "@/lib/share";

export const runtime = "edge";
export const alt = "Bain Luck market probability";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

type FuturesMarketMetadata = FuturesMarketDetailResponse & {
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

export default async function Image({ params }: { params: { id: string } }) {
  const market = await fetchMarket(params.id);
  const leader = market ? topOutcome(market) : null;
  const probability = formatShareProbability(leader?.probability) || "--";
  const barWidth = Math.max(3, Math.min(97, Math.round((leader?.probability ?? 0) * 100)));
  const title = market?.name || "Prediction market";
  const subtitle = truncateShareText(
    market?.hook_description ||
      (leader ? `${leader.name} leads this market at ${probability}.` : "Prediction markets translated into intuitive probabilities."),
    120
  );

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 64,
          background: "#f8fafc",
          color: "#111827",
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ fontSize: 38 }}>🍀</div>
            <div style={{ fontSize: 30, fontWeight: 800 }}>Bain Luck</div>
          </div>
          <div
            style={{
              border: "2px solid #d1d5db",
              borderRadius: 999,
              padding: "10px 18px",
              fontSize: 20,
              color: "#4b5563",
            }}
          >
            {market?.sport_name || market?.llm_sport_category || "Discover"}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <div style={{ fontSize: 88, fontWeight: 900, letterSpacing: 0, lineHeight: 1 }}>
            {probability}
          </div>
          <div style={{ fontSize: 44, fontWeight: 800, lineHeight: 1.12, maxWidth: 980 }}>
            {leader?.name || title}
          </div>
          <div style={{ fontSize: 28, color: "#4b5563", lineHeight: 1.25, maxWidth: 960 }}>
            {subtitle}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div
            style={{
              width: "100%",
              height: 30,
              borderRadius: 999,
              background: "#e5e7eb",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${barWidth}%`,
                height: "100%",
                borderRadius: 999,
                background: "#2563eb",
              }}
            />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", color: "#64748b", fontSize: 23 }}>
            <div>{truncateShareText(title, 84)}</div>
            <div>bainluck.com/discover</div>
          </div>
        </div>
      </div>
    ),
    size
  );
}
