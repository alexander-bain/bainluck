"use client";

import { useMemo } from "react";
import { useParams, notFound } from "next/navigation";
import useSWR from "swr";
import Link from "next/link";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchChampionshipGrid, fetchMarchMadness } from "@/lib/api";
import { TOURNAMENT_TYPE_CONFIG } from "@/lib/marchMadnessData";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import SeedHistory from "@/components/MarchMadness/SeedHistory";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import type {
  ChampionshipGridResponse,
  ProgressionResponse,
  ProgressionStage,
  ProgressionParticipant,
} from "@/lib/types";
import "../march-madness.css";

/** Transform ChampionshipGridResponse into ProgressionResponse for TournamentProgressionTable */
function toProgressionResponse(data: ChampionshipGridResponse): ProgressionResponse {
  const stages: ProgressionStage[] = data.columns.map((c) => ({
    key: c.key,
    label: c.label,
    order: c.order,
    market_id: null,
    market_name: null,
  }));

  const participants: ProgressionParticipant[] = data.teams.map((t) => {
    const probabilities: Record<string, number | null> = {};
    const changes_24h: Record<string, number | null> = {};
    const status: Record<string, "clinched" | "eliminated" | null> = {};

    for (const [cellKey, cellData] of Object.entries(t.cells)) {
      probabilities[cellKey] = cellData?.merged_probability ?? null;
      changes_24h[cellKey] = cellData?.trend_24h ?? null;
      status[cellKey] = null;
    }

    return {
      name: t.name,
      team_id: t.team_id,
      logo_url: t.logo_url,
      primary_color: t.primary_color,
      conference: t.conference,
      record: t.record,
      probabilities,
      changes_24h,
      status,
    };
  });

  return {
    sport: "basketball",
    tournament_name: data.name || "NCAA Tournament 2026",
    stages,
    participants,
  };
}

export default function MarchMadnessPage() {
  const params = useParams();
  const type = params?.type as string;

  usePageTracking({ pageType: "march_madness", pageTitle: `March Madness - ${type}` });
  useScrollDepth({ pageType: "march_madness" });
  useEngagementTime({ pageType: "march_madness" });

  const config = TOURNAMENT_TYPE_CONFIG[type as keyof typeof TOURNAMENT_TYPE_CONFIG];

  if (!config) {
    notFound();
  }

  // Use the championship grid endpoint — better data quality with
  // matching_rules and league_name_patterns filtering
  const leagueSlug = type === "womens" ? "wnba" : "ncaa-basketball";
  const {
    data: gridData,
    error: gridError,
    isLoading: gridLoading,
  } = useSWR(
    ["championship-grid", leagueSlug],
    () => fetchChampionshipGrid(leagueSlug),
    { refreshInterval: 60000 }
  );

  // Fetch March Madness API for seed history (static data)
  const {
    data: mmData,
  } = useSWR(
    ["march-madness", config.apiType],
    () => fetchMarchMadness(config.apiType),
    { refreshInterval: 0 }  // Static data, no need to refresh
  );

  const progressionData = useMemo(() => {
    if (!gridData) return null;
    return toProgressionResponse(gridData);
  }, [gridData]);

  return (
    <div className="mm-page">
      <div className="mm-content">
        {/* Hero */}
        <div className="mm-hero">
          <h1>{config.label}</h1>
          <p className="mm-hero-subtitle">
            Round-by-round championship odds from sportsbooks and prediction markets.
          </p>
          {/* Tournament type toggle */}
          <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 12 }}>
            <Link
              href="/march-madness/mens"
              className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                type === "mens"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "bg-white/5 text-white/50 border border-white/10 hover:border-white/20"
              }`}
            >
              Men&apos;s
            </Link>
            <Link
              href="/march-madness/womens"
              className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                type === "womens"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "bg-white/5 text-white/50 border border-white/10 hover:border-white/20"
              }`}
            >
              Women&apos;s
            </Link>
          </div>
        </div>

        {/* Loading state */}
        {gridLoading && <SkeletonGrid count={6} />}

        {/* Error state */}
        {gridError && (
          <ErrorMessage message="Failed to load tournament odds. Please try again." />
        )}

        {/* Championship odds trend chart (inline from grid response) */}
        {gridData?.trend_chart?.timeline && gridData.trend_chart.timeline.length > 0 && (
          <div className="mm-section">
            <div className="mm-section-header">
              <h2 className="mm-section-title">Championship Odds Trend</h2>
            </div>
            <div className="bg-white/[0.03] rounded-xl border border-white/10 p-3">
              <TrendChartInline trendChart={gridData.trend_chart} />
            </div>
          </div>
        )}

        {/* Round-by-round odds grid */}
        {progressionData && progressionData.participants.length > 0 && (
          <>
            <div className="mm-court-line" />
            <div className="mm-section">
              <div className="mm-section-header">
                <h2 className="mm-section-title">Tournament Odds Grid</h2>
                <span className="mm-section-badge">{progressionData.participants.length} teams</span>
              </div>
              <TournamentProgressionTable
                data={progressionData}
                showLogos
                pageType="march_madness"
                className="bg-white/[0.03] rounded-xl border border-white/10 p-4"
              />
            </div>
          </>
        )}

        {/* Empty state */}
        {!gridLoading && !gridError && (!progressionData || progressionData.participants.length === 0) && (
          <div className="mm-section" style={{ textAlign: "center", padding: "48px 24px" }}>
            <p style={{ color: "var(--mm-text-dim)", fontSize: "1.1rem", marginBottom: 8 }}>
              No tournament odds available yet
            </p>
            <p style={{ color: "var(--mm-text-dim)", opacity: 0.6, fontSize: "0.875rem" }}>
              Odds will appear when sportsbooks and prediction markets publish NCAA tournament markets.
            </p>
          </div>
        )}

        {/* Seed History (static data from March Madness API) */}
        {mmData && mmData.seed_history.length > 0 && (
          <>
            <div className="mm-court-line" />
            <SeedHistory
              seedHistory={mmData.seed_history}
              notableUpsets={mmData.notable_upsets}
            />
          </>
        )}

        {/* Sources footer */}
        {gridData && gridData.sources_available.length > 0 && (
          <p style={{
            textAlign: "center",
            fontSize: "0.75rem",
            color: "var(--mm-text-dim)",
            opacity: 0.5,
            marginTop: 16,
          }}>
            {gridData.teams.length} teams · {gridData.columns.length} stage{gridData.columns.length !== 1 ? "s" : ""} ·{" "}
            Sources: {gridData.sources_available.map(s =>
              s === "odds_api" ? "Sportsbooks" : s === "kalshi" ? "Kalshi" : s === "polymarket" ? "Polymarket" : s
            ).join(", ")}
          </p>
        )}
      </div>
    </div>
  );
}

/** Inline SVG trend chart from championship grid trend_chart data */
function TrendChartInline({ trendChart }: { trendChart: ChampionshipGridResponse["trend_chart"] }) {
  const { timeline, outcomes } = trendChart;
  if (!timeline || timeline.length < 2) return null;

  const W = 800;
  const H = 220;
  const PAD = { top: 20, right: 16, bottom: 30, left: 48 };

  // Get top 8 outcomes by current probability
  const topOutcomes = (outcomes || [])
    .sort((a, b) => (b.current_probability ?? 0) - (a.current_probability ?? 0))
    .slice(0, 8);
  const names = topOutcomes.map((o) => o.name);

  const COLORS = [
    "#f59e0b", "#3b82f6", "#ef4444", "#22c55e", "#a855f7",
    "#06b6d4", "#f97316", "#ec4899",
  ];

  // Build series data
  const xMin = new Date(timeline[0].timestamp).getTime();
  const xMax = new Date(timeline[timeline.length - 1].timestamp).getTime();

  let yMax = 0;
  for (const entry of timeline) {
    for (const name of names) {
      const v = entry.outcomes[name];
      if (v != null && v > yMax) yMax = v;
    }
  }
  yMax = Math.max(yMax * 1.15, 0.05);

  const xScale = (t: number) => PAD.left + ((t - xMin) / (xMax - xMin)) * (W - PAD.left - PAD.right);
  const yScale = (v: number) => PAD.top + (1 - v / yMax) * (H - PAD.top - PAD.bottom);

  const paths = names.map((name, i) => {
    const points: string[] = [];
    for (const entry of timeline) {
      const v = entry.outcomes[name];
      if (v == null) continue;
      const t = new Date(entry.timestamp).getTime();
      points.push(`${xScale(t).toFixed(1)},${yScale(v).toFixed(1)}`);
    }
    if (points.length < 2) return null;
    return (
      <polyline
        key={name}
        points={points.join(" ")}
        fill="none"
        stroke={COLORS[i % COLORS.length]}
        strokeWidth={i === 0 ? 2.5 : 1.5}
        strokeLinejoin="round"
        opacity={i < 3 ? 1 : 0.7}
      />
    );
  });

  // Y-axis labels
  const yTicks = [0, yMax * 0.25, yMax * 0.5, yMax * 0.75, yMax];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 280 }}>
        {/* Y gridlines and labels */}
        {yTicks.map((v, i) => (
          <g key={i}>
            <line
              x1={PAD.left} y1={yScale(v)} x2={W - PAD.right} y2={yScale(v)}
              stroke="rgba(255,255,255,0.06)" strokeWidth={1}
            />
            <text
              x={PAD.left - 6} y={yScale(v) + 4}
              fill="rgba(255,255,255,0.3)" fontSize={10} textAnchor="end"
            >
              {(v * 100).toFixed(0)}%
            </text>
          </g>
        ))}
        {paths}
      </svg>
      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-2 px-2 justify-center">
        {names.map((name, i) => (
          <div key={name} className="flex items-center gap-1.5 text-xs" style={{ color: "rgba(255,255,255,0.6)" }}>
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
            <span>{name.replace(/ (Blue Devils|Wildcats|Wolverines|Gators|Cougars|Bulldogs|Tigers|Bears|Huskies|Cardinals|Seminoles|Volunteers|Longhorns|Boilermakers|Tar Heels|Jayhawks|Hurricanes|Yellow Jackets|Crimson Tide|Hawkeyes|Spartans|Sun Devils)$/, "")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
