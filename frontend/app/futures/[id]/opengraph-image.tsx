/* eslint-disable @next/next/no-img-element */
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

// OG images render as PNGs via ImageResponse — CSS variables are unavailable.
// Inline colors are required and intentional for this file.

const CATEGORY_ACCENT: Record<string, string> = {
  basketball: "#c24005",
  football: "#0d803d",
  baseball: "#ba1c1c",
  hockey: "#2663eb",
  soccer: "#049966",
  golf: "#176633",
  mma: "#991c1c",
  economics: "#7c3aed",
  politics: "#4338ca",
  tech: "#0891b2",
  culture: "#db2777",
  weather: "#0284c7",
  entertainment: "#bf26d6",
  cricket: "#14b8a6",
  olympics: "#d97706",
};

const DEFAULT_ACCENT = "#10B981";
const COLOR_WHITE = "#ffffff";
const COLOR_PRIMARY = "#111827";
const COLOR_SECONDARY = "#374151";
const COLOR_MUTED = "#6b7280";
const COLOR_SUBTLE = "#94a3b8";
const COLOR_BAR_BG = "#f1f5f9";
const COLOR_UP = "#16a34a";
const COLOR_DOWN = "#dc2626";

function getAccent(category: string | null | undefined): string {
  if (!category) return DEFAULT_ACCENT;
  return CATEGORY_ACCENT[category.toLowerCase()] || DEFAULT_ACCENT;
}

export default async function Image({ params }: { params: { id: string } }) {
  const market = await fetchMarket(params.id);
  const leader = market ? topOutcome(market) : null;
  const probability = formatShareProbability(leader?.probability) || "--";
  const barWidth = Math.max(3, Math.min(97, Math.round((leader?.probability ?? 0) * 100)));
  const title = market?.name || "Prediction market";
  const accent = getAccent(market?.llm_sport_category);

  const change = leader?.probability_change_24h;
  const hasMovement =
    change !== null && change !== undefined && change !== 0 && Math.abs(change) >= 0.005;
  const changeLabel = hasMovement
    ? `${change! > 0 ? "+" : ""}${Math.round(change! * 100)}% 24h`
    : null;
  const changeColor = hasMovement ? (change! > 0 ? COLOR_UP : COLOR_DOWN) : COLOR_MUTED;

  const subtitle = truncateShareText(
    market?.hook_description ||
      (leader
        ? `${leader.name} leads at ${probability} — ${market?.outcome_count ?? "?"} outcomes tracked.`
        : "Prediction markets translated into intuitive probabilities."),
    130
  );

  const categoryLabel = market?.sport_name || market?.llm_sport_category || "Discover";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          background: COLOR_WHITE,
          color: COLOR_PRIMARY,
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        {/* Accent stripe */}
        <div style={{ height: 6, background: accent, width: "100%" }} />

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            flex: 1,
            padding: "48px 64px 52px",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontSize: 34 }}>🍀</span>
              <span style={{ fontSize: 28, fontWeight: 800 }}>Bain Luck</span>
            </div>
            <div
              style={{
                border: `2px solid ${accent}`,
                borderRadius: 999,
                padding: "8px 20px",
                fontSize: 19,
                fontWeight: 700,
                color: accent,
                textTransform: "capitalize",
              }}
            >
              {categoryLabel}
            </div>
          </div>

          {/* Body */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 8 }}>
            <div style={{ fontSize: 36, fontWeight: 700, lineHeight: 1.2, color: COLOR_SECONDARY, maxWidth: 1000 }}>
              {truncateShareText(title, 90)}
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 20 }}>
              <span style={{ fontSize: 96, fontWeight: 900, letterSpacing: -2, lineHeight: 1, color: COLOR_PRIMARY }}>
                {probability}
              </span>
              {changeLabel && (
                <span style={{ fontSize: 28, fontWeight: 700, color: changeColor }}>
                  {change! > 0 ? "↑" : "↓"} {changeLabel}
                </span>
              )}
            </div>

            <div style={{ fontSize: 40, fontWeight: 800, lineHeight: 1.15, color: COLOR_PRIMARY, maxWidth: 900 }}>
              {leader?.name || ""}
            </div>

            <div style={{ fontSize: 24, color: COLOR_MUTED, lineHeight: 1.35, maxWidth: 920 }}>
              {subtitle}
            </div>
          </div>

          {/* Footer bar + URL */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ width: "100%", height: 24, borderRadius: 999, background: COLOR_BAR_BG, overflow: "hidden", display: "flex" }}>
              <div style={{ width: `${barWidth}%`, height: "100%", borderRadius: 999, background: accent }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: COLOR_SUBTLE, fontSize: 20 }}>
              <span>
                {market?.outcome_count ?? 0} outcome{(market?.outcome_count ?? 0) !== 1 ? "s" : ""} tracked
              </span>
              <span style={{ fontWeight: 600 }}>bainluck.com</span>
            </div>
          </div>
        </div>
      </div>
    ),
    size
  );
}
