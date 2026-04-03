"use client";

/**
 * Source Comparison Module — shows how different probability sources see a game.
 *
 * Displays BainLuck composite vs individual sources (sportsbooks, Kalshi,
 * Polymarket, ESPN, stat models) with probability bars and change indicators.
 * Highlights divergence when sources disagree significantly.
 */

import type { WinProbHistoryPoint, WinProbSourceMeta } from "@/lib/types";

interface SourceEntry {
  key: string;
  label: string;
  shortLabel: string;
  homeProb: number; // 0-1
  color: string;
  badgeColor: string; // bg + text for the icon badge
  change: number | null; // delta from opening or from 1h ago
  type: "composite" | "sportsbook" | "market" | "model";
}

interface SourceComparisonProps {
  homeProb: number | null;
  awayProb: number | null;
  homeTeam: string;
  awayTeam: string;
  homeTeamColor?: string;
  awayTeamColor?: string;
  // Sportsbook consensus from odds history
  bookmakerHistory?: Record<string, Array<{ timestamp: string; home_probability: number | null }>>;
  // Win probability sources
  winProbHistory?: Record<string, WinProbHistoryPoint[]>;
  winProbSources?: Record<string, WinProbSourceMeta>;
  // Opening odds for change computation
  openingHomeProb?: number | null;
}

// Source display config
const SOURCE_CONFIG: Record<string, {
  label: string;
  shortLabel: string;
  color: string;
  badgeColor: string;
  type: "market" | "model";
}> = {
  kalshi: {
    label: "Kalshi",
    shortLabel: "K",
    color: "#7C3AED",
    badgeColor: "bg-violet-100 text-violet-700",
    type: "market",
  },
  polymarket: {
    label: "Polymarket",
    shortLabel: "PM",
    color: "#2563EB",
    badgeColor: "bg-blue-100 text-blue-700",
    type: "market",
  },
  espn: {
    label: "ESPN",
    shortLabel: "E",
    color: "#DC2626",
    badgeColor: "bg-red-100 text-red-700",
    type: "model",
  },
  stat_model: {
    label: "Stat Model",
    shortLabel: "SM",
    color: "#059669",
    badgeColor: "bg-emerald-100 text-emerald-700",
    type: "model",
  },
  mlb: {
    label: "MLB Model",
    shortLabel: "MLB",
    color: "#1D4ED8",
    badgeColor: "bg-blue-100 text-blue-700",
    type: "model",
  },
  datagolf: {
    label: "DataGolf",
    shortLabel: "DG",
    color: "#15803D",
    badgeColor: "bg-green-100 text-green-700",
    type: "model",
  },
};

function getLatestProb(
  points: WinProbHistoryPoint[] | undefined
): number | null {
  if (!points || points.length === 0) return null;
  for (let i = points.length - 1; i >= 0; i--) {
    if (points[i].home_probability !== null) return points[i].home_probability;
  }
  return null;
}

function getChangeFromHourAgo(
  points: WinProbHistoryPoint[] | undefined
): number | null {
  if (!points || points.length < 2) return null;
  const latest = getLatestProb(points);
  if (latest === null) return null;

  const oneHourAgo = Date.now() - 60 * 60 * 1000;
  // Find the point closest to 1h ago
  let hourAgoProb: number | null = null;
  for (const p of points) {
    if (new Date(p.timestamp).getTime() <= oneHourAgo && p.home_probability !== null) {
      hourAgoProb = p.home_probability;
    }
  }
  if (hourAgoProb === null) {
    // Use earliest point as fallback
    for (const p of points) {
      if (p.home_probability !== null) {
        hourAgoProb = p.home_probability;
        break;
      }
    }
  }
  if (hourAgoProb === null) return null;
  const delta = latest - hourAgoProb;
  return Math.abs(delta) >= 0.005 ? delta : null;
}

function getSportsbookConsensus(
  bookmakerHistory: Record<string, Array<{ timestamp: string; home_probability: number | null }>> | undefined
): number | null {
  if (!bookmakerHistory) return null;
  const probs: number[] = [];
  for (const points of Object.values(bookmakerHistory)) {
    if (!points || points.length === 0) continue;
    // Get latest point
    for (let i = points.length - 1; i >= 0; i--) {
      if (points[i].home_probability !== null) {
        probs.push(points[i].home_probability!);
        break;
      }
    }
  }
  if (probs.length === 0) return null;
  return probs.reduce((a, b) => a + b, 0) / probs.length;
}

export default function SourceComparison({
  homeProb,
  awayProb,
  homeTeam,
  awayTeam,
  homeTeamColor,
  awayTeamColor,
  bookmakerHistory,
  winProbHistory,
  winProbSources,
  openingHomeProb,
}: SourceComparisonProps) {
  if (homeProb === null) return null;

  const sources: SourceEntry[] = [];

  // 1. BainLuck Composite (always shown when we have a probability)
  const compositeChange = openingHomeProb != null
    ? homeProb - openingHomeProb
    : null;
  sources.push({
    key: "bainluck",
    label: "BainLuck",
    shortLabel: "BL",
    homeProb,
    color: homeTeamColor || "#111827",
    badgeColor: "bg-gray-900 text-white",
    change: compositeChange && Math.abs(compositeChange) >= 0.005 ? compositeChange : null,
    type: "composite",
  });

  // 2. Sportsbook Consensus
  const sbConsensus = getSportsbookConsensus(bookmakerHistory);
  if (sbConsensus !== null) {
    sources.push({
      key: "sportsbooks",
      label: "Sportsbook Consensus",
      shortLabel: "SB",
      homeProb: sbConsensus,
      color: "#6B7280",
      badgeColor: "bg-emerald-100 text-emerald-700",
      change: null,
      type: "sportsbook",
    });
  }

  // 3. Win probability sources (Kalshi, Polymarket, ESPN, stat model, etc.)
  if (winProbHistory) {
    for (const [sourceKey, points] of Object.entries(winProbHistory)) {
      if (sourceKey === "betting") continue; // Skip — this is the sportsbook consensus
      const latestProb = getLatestProb(points);
      if (latestProb === null) continue;

      const config = SOURCE_CONFIG[sourceKey];
      const sourceMeta = winProbSources?.[sourceKey];
      const change = getChangeFromHourAgo(points);

      sources.push({
        key: sourceKey,
        label: config?.label || sourceMeta?.display_name || sourceKey,
        shortLabel: config?.shortLabel || sourceKey.substring(0, 2).toUpperCase(),
        homeProb: latestProb,
        color: config?.color || sourceMeta?.color || "#6B7280",
        badgeColor: config?.badgeColor || "bg-gray-100 text-gray-700",
        change,
        type: config?.type || "model",
      });
    }
  }

  // Don't render if we only have the composite (no additional sources to compare)
  if (sources.length < 2) return null;

  // Detect max divergence
  const probs = sources.map((s) => s.homeProb);
  const maxProb = Math.max(...probs);
  const minProb = Math.min(...probs);
  const maxDivergence = maxProb - minProb;

  // Find the most divergent pair for the callout
  let divergenceCallout: string | null = null;
  if (maxDivergence >= 0.05) {
    const highSource = sources.find((s) => s.homeProb === maxProb);
    const lowSource = sources.find((s) => s.homeProb === minProb);
    if (highSource && lowSource && highSource.key !== lowSource.key) {
      const homeShort = homeTeam.split(" ").pop() || homeTeam;
      divergenceCallout = `${highSource.label} has ${homeShort} at ${Math.round(maxProb * 100)}% vs ${lowSource.label} at ${Math.round(minProb * 100)}%`;
    }
  }

  return (
    <div className="bg-surface-card rounded-card shadow-card overflow-hidden">
      <div className="px-4 sm:px-5 pt-4 pb-3">
        <h2 className="text-[13px] font-semibold text-text-primary">Source Comparison</h2>
        <p className="text-[10px] text-text-muted mt-0.5">How different sources see this game</p>
      </div>

      <div className="px-4 sm:px-5 pb-4 space-y-2">
        {sources.map((source, i) => (
          <SourceRow
            key={source.key}
            source={source}
            isPrimary={i === 0}
            homeTeamColor={homeTeamColor}
            awayTeamColor={awayTeamColor}
          />
        ))}

        {/* Divergence callout */}
        {divergenceCallout && (
          <div className="mt-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-100">
            <div className="flex items-start gap-2">
              <span className="text-amber-500 mt-0.5 flex-shrink-0 text-xs">⚠️</span>
              <p className="text-[11px] text-amber-700 leading-relaxed">
                <span className="font-semibold">{Math.round(maxDivergence * 100)}% divergence</span>
                {" — "}
                {divergenceCallout}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SourceRow({
  source,
  isPrimary,
  homeTeamColor,
  awayTeamColor,
}: {
  source: SourceEntry;
  isPrimary: boolean;
  homeTeamColor?: string;
  awayTeamColor?: string;
}) {
  const homePct = Math.round(source.homeProb * 100);
  const awayPct = 100 - homePct;

  const changeDisplay = source.change !== null
    ? source.change > 0
      ? `+${Math.round(source.change * 100)}%`
      : `${Math.round(source.change * 100)}%`
    : null;
  const changeColor = source.change !== null
    ? source.change > 0
      ? "text-emerald-600"
      : "text-red-500"
    : "";

  if (isPrimary) {
    // Composite — larger, highlighted style
    return (
      <div className="px-4 py-3.5 rounded-xl bg-surface-elevated border border-surface-border">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2">
            <div className={`w-6 h-6 rounded-md flex items-center justify-center ${source.badgeColor}`}>
              <span className="text-[9px] font-bold">{source.shortLabel}</span>
            </div>
            <div>
              <span className="text-xs font-semibold text-text-primary">{source.label}</span>
              <span className="text-[10px] text-text-muted ml-1.5">Composite</span>
            </div>
          </div>
          {changeDisplay && (
            <div className="flex items-center gap-1">
              <ChangeArrow positive={source.change! > 0} />
              <span className={`text-[10px] font-medium ${changeColor}`}>{changeDisplay}</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span
            className="text-lg font-bold tabular-nums"
            style={{ color: homeTeamColor || "#111827" }}
          >
            {homePct}%
          </span>
          <div className="flex-1 h-2 rounded-full bg-gray-200 overflow-hidden flex">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${homePct}%`,
                backgroundColor: homeTeamColor || "#111827",
              }}
            />
          </div>
          <span
            className="text-lg font-bold tabular-nums"
            style={{ color: awayTeamColor || "#6B7280" }}
          >
            {awayPct}%
          </span>
        </div>
      </div>
    );
  }

  // Secondary sources — compact style
  return (
    <div className="px-4 py-3 rounded-xl hover:bg-surface-elevated transition-colors">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-5 h-5 rounded flex items-center justify-center ${source.badgeColor}`}>
            <span className="text-[8px] font-bold">{source.shortLabel}</span>
          </div>
          <span className="text-xs font-medium text-text-secondary">{source.label}</span>
          {source.type === "market" && (
            <span className="text-[10px] text-text-muted">Prediction Market</span>
          )}
          {source.type === "model" && (
            <span className="text-[10px] text-text-muted">Model</span>
          )}
        </div>
        {changeDisplay && (
          <div className="flex items-center gap-1">
            <ChangeArrow positive={source.change! > 0} />
            <span className={`text-[10px] font-medium ${changeColor}`}>{changeDisplay}</span>
          </div>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold tabular-nums text-text-secondary">{homePct}%</span>
        <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden flex">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${homePct}%`,
              backgroundColor: source.color,
            }}
          />
        </div>
        <span className="text-sm font-semibold tabular-nums text-text-secondary">{awayPct}%</span>
      </div>
    </div>
  );
}

function ChangeArrow({ positive }: { positive: boolean }) {
  return (
    <svg
      className={`w-3 h-3 ${positive ? "text-emerald-500" : "text-red-500"}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      {positive ? (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
      ) : (
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
      )}
    </svg>
  );
}
