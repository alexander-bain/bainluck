"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetchChampionshipGrid } from "@/lib/api";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import type {
  ChampionshipGridResponse,
  ChampionshipGridTeam,
  ProgressionResponse,
  ProgressionStage,
  ProgressionParticipant,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// League registry — all 13 leagues from backend config
// ---------------------------------------------------------------------------

interface LeagueInfo {
  slug: string;
  label: string;
  emoji: string;
  group: "us" | "college" | "soccer" | "other";
  conferences?: string[];
}

const LEAGUES: LeagueInfo[] = [
  { slug: "nba", label: "NBA", emoji: "\u{1F3C0}", group: "us", conferences: ["Eastern", "Western"] },
  { slug: "nfl", label: "NFL", emoji: "\u{1F3C8}", group: "us", conferences: ["AFC", "NFC"] },
  { slug: "mlb", label: "MLB", emoji: "\u26BE", group: "us", conferences: ["American League", "National League"] },
  { slug: "nhl", label: "NHL", emoji: "\u{1F3D2}", group: "us", conferences: ["Eastern", "Western"] },
  { slug: "wnba", label: "WNBA", emoji: "\u{1F3C0}", group: "us" },
  { slug: "ncaa-basketball", label: "NCAAB", emoji: "\u{1F3C0}", group: "college" },
  { slug: "ncaa-football", label: "NCAAF", emoji: "\u{1F3C8}", group: "college" },
  { slug: "epl", label: "EPL", emoji: "\u26BD", group: "soccer" },
  { slug: "la-liga", label: "La Liga", emoji: "\u26BD", group: "soccer" },
  { slug: "champions-league", label: "UCL", emoji: "\u26BD", group: "soccer" },
  { slug: "bundesliga", label: "Bundesliga", emoji: "\u26BD", group: "soccer" },
  { slug: "mls", label: "MLS", emoji: "\u26BD", group: "soccer" },
  { slug: "golf", label: "Golf", emoji: "\u26F3", group: "other" },
];

const LEAGUE_MAP = Object.fromEntries(LEAGUES.map((l) => [l.slug, l]));

const SOURCE_LABELS: Record<string, string> = {
  odds_api: "Sportsbooks",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
  datagolf: "DataGolf",
};

// ---------------------------------------------------------------------------
// Adapters: ChampionshipGridResponse -> ProgressionResponse
// ---------------------------------------------------------------------------

function teamsToProgression(
  columns: ChampionshipGridResponse["columns"],
  teams: ChampionshipGridTeam[],
  sportLabel: string,
  tournamentName: string,
): ProgressionResponse {
  const stages: ProgressionStage[] = columns.map((c) => ({
    key: c.key,
    label: c.label,
    order: c.order,
    market_id: null,
    market_name: null,
  }));

  const participants: ProgressionParticipant[] = teams.map((t) => {
    const probabilities: Record<string, number | null> = {};
    const changes_24h: Record<string, number | null> = {};
    const status: Record<string, "clinched" | "eliminated" | null> = {};
    const sources_data: Record<string, { source: string; probability: number }[]> = {};

    for (const [colKey, cell] of Object.entries(t.cells)) {
      probabilities[colKey] = cell.merged_probability;
      changes_24h[colKey] = cell.trend_24h;
      status[colKey] = null;
      if (cell.sources) {
        sources_data[colKey] = cell.sources;
      }
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
      sources_data,
    };
  });

  return {
    sport: sportLabel,
    tournament_name: tournamentName,
    stages,
    participants,
  };
}

// ---------------------------------------------------------------------------
// Movers Section
// ---------------------------------------------------------------------------

function MoversSection({ movers }: { movers: ChampionshipGridResponse["movers"] }) {
  if (!movers.length) return null;

  return (
    <div className="mb-5">
      <h2 className="text-xs font-medium text-text-secondary mb-2 uppercase tracking-wide">
        Biggest Movers (24h)
      </h2>
      <div className="flex flex-wrap gap-2">
        {movers.map((m) => {
          const pct = Math.abs(m.change_24h * 100);
          const isUp = m.direction === "up";
          return (
            <div
              key={`${m.name}-${m.column}`}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm border ${
                isUp
                  ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                  : "bg-red-500/10 border-red-500/20 text-red-400"
              }`}
            >
              {m.logo_url && (
                <img src={m.logo_url} alt="" className="w-4 h-4 object-contain" />
              )}
              {!m.logo_url && m.primary_color && (
                <span
                  className="w-3 h-3 rounded-full inline-block"
                  style={{ backgroundColor: m.primary_color }}
                />
              )}
              <span className="font-medium">{m.short_name}</span>
              <span className="font-mono text-xs">
                {isUp ? "+" : "-"}
                {pct >= 1 ? Math.round(pct) : pct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trend Mini Chart (renders embedded trend_chart data as SVG)
// ---------------------------------------------------------------------------

function TrendMiniChart({ chart }: { chart: ChampionshipGridResponse["trend_chart"] }) {
  if (!chart.timeline?.length) return null;
  const outcomes = chart.outcomes ?? [];

  // If no outcomes metadata, derive names from timeline data
  const derivedNames = outcomes.length
    ? outcomes.map((o) => o.name)
    : [...new Set(chart.timeline.flatMap((e) => Object.keys(e.outcomes)))];

  if (!derivedNames.length) return null;

  const width = 800;
  const height = 200;
  const pad = { top: 20, right: 20, bottom: 30, left: 45 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const timestamps = chart.timeline.map((t) => new Date(t.timestamp).getTime());
  const minT = Math.min(...timestamps);
  const maxT = Math.max(...timestamps);
  const rangeT = maxT - minT || 1;

  // Find y-axis range from data
  let maxP = 0;
  for (const entry of chart.timeline) {
    for (const p of Object.values(entry.outcomes)) {
      if (p > maxP) maxP = p;
    }
  }
  maxP = Math.max(maxP * 1.15, 0.05); // 15% headroom, min 5%

  const scaleX = (t: number) => pad.left + ((t - minT) / rangeT) * plotW;
  const scaleY = (p: number) => pad.top + plotH - (p / maxP) * plotH;

  // Color map from outcomes metadata
  const DEFAULT_COLORS = [
    "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6",
    "#ec4899", "#14b8a6", "#f97316", "#06b6d4", "#a855f7",
  ];
  const colorMap: Record<string, string> = {};
  derivedNames.forEach((name, i) => {
    const meta = outcomes.find((o) => o.name === name);
    colorMap[name] = meta?.primary_color || DEFAULT_COLORS[i % DEFAULT_COLORS.length];
  });

  // Build polyline paths per outcome
  const outcomeNames = derivedNames;
  const paths = outcomeNames.map((name) => {
    const points: string[] = [];
    for (let i = 0; i < chart.timeline.length; i++) {
      const entry = chart.timeline[i];
      const p = entry.outcomes[name];
      if (p === undefined) continue;
      const x = scaleX(timestamps[i]);
      const y = scaleY(p);
      points.push(`${x},${y}`);
    }
    return { name, points: points.join(" "), color: colorMap[name] || "#666" };
  });

  // Y-axis labels
  const yTicks = [0, maxP * 0.25, maxP * 0.5, maxP * 0.75, maxP];

  // X-axis date labels — evenly spaced across the range
  const xTickCount = 5;
  const xTicks: { ts: number; label: string }[] = [];
  for (let i = 0; i <= xTickCount; i++) {
    const ts = minT + (rangeT * i) / xTickCount;
    const d = new Date(ts);
    const label = `${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
    xTicks.push({ ts, label });
  }

  // Compute trend period label
  const trendDays = Math.round(rangeT / (1000 * 60 * 60 * 24));
  const trendLabel = trendDays <= 1 ? "24h" : `${trendDays}d`;

  return (
    <div className="mb-5 bg-surface-card rounded-xl border border-white/10 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide">
          Championship Odds Trend
        </h2>
        <span className="text-[10px] text-text-secondary/50 font-mono">
          Past {trendLabel}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        style={{ maxHeight: 220 }}
      >
        {/* Grid lines */}
        {yTicks.map((tick, i) => (
          <g key={i}>
            <line
              x1={pad.left}
              y1={scaleY(tick)}
              x2={width - pad.right}
              y2={scaleY(tick)}
              stroke="rgba(255,255,255,0.06)"
              strokeWidth={1}
            />
            <text
              x={pad.left - 6}
              y={scaleY(tick) + 4}
              textAnchor="end"
              fill="rgba(255,255,255,0.3)"
              fontSize={11}
              fontFamily="monospace"
            >
              {Math.round(tick * 100)}%
            </text>
          </g>
        ))}

        {/* Lines */}
        {paths.map((p) => (
          <polyline
            key={p.name}
            points={p.points}
            fill="none"
            stroke={p.color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity={0.85}
          />
        ))}

        {/* X-axis date labels */}
        {xTicks.map((tick, i) => (
          <text
            key={i}
            x={scaleX(tick.ts)}
            y={height - 4}
            textAnchor="middle"
            fill="rgba(255,255,255,0.3)"
            fontSize={10}
            fontFamily="monospace"
          >
            {tick.label}
          </text>
        ))}
      </svg>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {derivedNames.slice(0, 8).map((name) => {
          const meta = outcomes.find((o) => o.name === name);
          return (
            <div key={name} className="flex items-center gap-1.5 text-xs text-text-secondary">
              <span
                className="w-2.5 h-2.5 rounded-full inline-block"
                style={{ backgroundColor: colorMap[name] || "#666" }}
              />
              <span className="truncate max-w-[120px]">{name}</span>
              {meta?.current_probability != null && (
                <span className="font-mono text-text-secondary/60">
                  {Math.round(meta.current_probability * 100)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Golf Tournament Header
// ---------------------------------------------------------------------------

function GolfTournamentHeader({
  tournament,
  fieldCount,
}: {
  tournament: NonNullable<ChampionshipGridResponse["tournament"]>;
  fieldCount?: number;
}) {
  const statusLabel = tournament.status === "live" ? "In Progress" : "Upcoming";
  const statusColor = tournament.status === "live" ? "text-emerald-400" : "text-amber-400";

  return (
    <div className="mb-4 p-4 bg-surface-card rounded-xl border border-white/10">
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
          tournament.status === "live"
            ? "bg-emerald-500/20 text-emerald-400"
            : "bg-amber-500/20 text-amber-400"
        }`}>
          {statusLabel}
          {tournament.current_round && ` \u00B7 Round ${tournament.current_round}`}
        </span>
      </div>
      <h2 className="text-lg font-semibold text-text-primary">{tournament.name}</h2>
      <p className="text-sm text-text-secondary">
        {tournament.course} &middot; {tournament.location}
      </p>
      {fieldCount && (
        <p className="text-xs text-text-secondary/60 mt-1">
          {fieldCount} golfers in the field
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function PlayoffGridPage({
  params,
}: {
  params: { sport: string };
}) {
  const slug = params.sport.toLowerCase();
  const league = LEAGUE_MAP[slug];
  const displayName = league
    ? `${league.label} Championship Grid`
    : `${slug} Championship Grid`;

  usePageTracking({ pageType: "playoff_grid", pageTitle: `${displayName} - Bain Luck` });
  useScrollDepth({ pageType: "playoff_grid" });
  useEngagementTime({ pageType: "playoff_grid" });

  const [conferenceFilter, setConferenceFilter] = useState<string | null>(null);

  const {
    data: gridData,
    error: gridError,
    isLoading,
  } = useSWR(
    ["championship-grid", slug],
    () => fetchChampionshipGrid(slug),
    { refreshInterval: 60000 }
  );

  // Build progression tables — either grouped by conference or flat
  const sections = useMemo(() => {
    if (!gridData) return null;

    if (gridData.grouped_teams) {
      // Conference/region split — hide "Other" as a named group
      return Object.entries(gridData.grouped_teams)
        .filter(([conf]) => conf !== "Other")
        .filter(([conf]) => !conferenceFilter || conf === conferenceFilter)
        .map(([conf, teams]) => ({
          label: conf,
          data: teamsToProgression(
            gridData.columns,
            teams,
            gridData.league,
            conf,
          ),
        }));
    }

    // Flat list — apply conference filter client-side if needed
    const teams = conferenceFilter
      ? gridData.teams.filter((t) => t.conference === conferenceFilter)
      : gridData.teams;

    return [{
      label: null as string | null,
      data: teamsToProgression(
        gridData.columns,
        teams,
        gridData.league,
        gridData.name,
      ),
    }];
  }, [gridData, conferenceFilter]);

  // Get unique conferences from the data for filter buttons
  const conferences = useMemo(() => {
    if (!gridData) return [];
    if (gridData.grouped_teams) {
      return Object.keys(gridData.grouped_teams).filter((c) => c !== "Other");
    }
    // Fallback: extract from league config
    return league?.conferences || [];
  }, [gridData, league]);

  // No config for this slug — show league picker
  if (!league) {
    return (
      <main className="min-h-screen bg-background">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <h1 className="text-2xl font-bold text-text-primary mb-4">
            League Not Found
          </h1>
          <p className="text-text-secondary mb-6">
            No championship grid available for &quot;{slug}&quot;.
          </p>
          <LeagueTabs currentSlug={slug} />
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="mb-4">
          <div className="flex items-center gap-3 mb-1">
            <span className="text-3xl">{league.emoji}</span>
            <h1 className="text-2xl font-bold text-text-primary">{displayName}</h1>
          </div>
          {gridData?.season && (
            <p className="text-sm text-text-secondary">{gridData.season}</p>
          )}
        </div>

        {/* League tabs */}
        <LeagueTabs currentSlug={slug} />

        {/* Source badges + conference filter */}
        {gridData && (
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-text-secondary">Sources:</span>
              {gridData.sources_available.map((source) => (
                <span
                  key={source}
                  className="text-xs px-2 py-0.5 rounded-full bg-surface-card border border-white/10 text-text-secondary"
                >
                  {SOURCE_LABELS[source] || source}
                </span>
              ))}
            </div>

            {conferences.length > 1 && (
              <div className="flex items-center gap-1.5 ml-auto">
                <button
                  onClick={() => setConferenceFilter(null)}
                  className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                    !conferenceFilter
                      ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                      : "bg-surface-card text-text-secondary border border-white/10 hover:border-white/20"
                  }`}
                >
                  All
                </button>
                {conferences.map((conf) => (
                  <button
                    key={conf}
                    onClick={() =>
                      setConferenceFilter(conferenceFilter === conf ? null : conf)
                    }
                    className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
                      conferenceFilter === conf
                        ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                        : "bg-surface-card text-text-secondary border border-white/10 hover:border-white/20"
                    }`}
                  >
                    {conf}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Loading */}
        {isLoading && <SkeletonGrid count={6} />}

        {/* Error */}
        {gridError && (
          <ErrorMessage message="Failed to load championship grid. Please try again." />
        )}

        {/* Golf tournament header */}
        {gridData?.tournament && (
          <GolfTournamentHeader
            tournament={gridData.tournament}
            fieldCount={gridData.field_count}
          />
        )}

        {/* Trend chart */}
        {gridData?.trend_chart && (
          <TrendMiniChart chart={gridData.trend_chart} />
        )}

        {/* Movers */}
        {gridData?.movers && <MoversSection movers={gridData.movers} />}

        {/* Empty state */}
        {!isLoading && !gridError && sections && sections.every((s) => s.data.participants.length === 0) && (
          <div className="text-center py-12">
            <p className="text-text-secondary text-lg mb-2">
              No championship odds available yet
            </p>
            <p className="text-text-secondary/60 text-sm">
              Odds will appear when sportsbooks and prediction markets publish{" "}
              {league.label} championship markets.
            </p>
          </div>
        )}

        {/* Grid sections */}
        {sections &&
          sections.map((section, idx) => (
            <div key={section.label || idx} className="mb-6">
              {section.label && sections.length > 1 && (
                <h2 className="text-base font-semibold text-text-primary mb-2">
                  {section.label}
                </h2>
              )}
              {section.data.participants.length > 0 && (
                <TournamentProgressionTable
                  data={section.data}
                  showLogos
                  pageType="playoff_grid"
                  className="bg-surface-card rounded-xl border border-white/10 p-4"
                />
              )}
            </div>
          ))}

        {/* Footer */}
        {gridData && gridData.team_count > 0 && (
          <p className="text-xs text-text-secondary/50 mt-2 text-center">
            {gridData.team_count} {slug === "golf" ? "golfers" : "teams"} &middot;{" "}
            {gridData.columns.length} columns &middot;{" "}
            {gridData.sources_available.length} source
            {gridData.sources_available.length !== 1 ? "s" : ""}
            {conferenceFilter && ` \u00B7 Showing ${conferenceFilter}`}
          </p>
        )}
      </div>
    </main>
  );
}

// ---------------------------------------------------------------------------
// League Tabs — shared component
// ---------------------------------------------------------------------------

function LeagueTabs({ currentSlug }: { currentSlug: string }) {
  // Group leagues with visual separators
  const groups: { label: string; leagues: LeagueInfo[] }[] = [
    { label: "US Pro", leagues: LEAGUES.filter((l) => l.group === "us") },
    { label: "College", leagues: LEAGUES.filter((l) => l.group === "college") },
    { label: "Soccer", leagues: LEAGUES.filter((l) => l.group === "soccer") },
    { label: "Other", leagues: LEAGUES.filter((l) => l.group === "other") },
  ];

  return (
    <div className="flex gap-1.5 mb-4 overflow-x-auto pb-1 scrollbar-hide">
      {groups.map((group, gi) => (
        <div key={group.label} className="flex gap-1.5 items-center">
          {gi > 0 && (
            <span className="w-px h-5 bg-white/10 mx-1 flex-shrink-0" />
          )}
          {group.leagues.map((l) => (
            <Link
              key={l.slug}
              href={`/playoffs/${l.slug}`}
              className={`px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                l.slug === currentSlug
                  ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                  : "bg-surface-card text-text-secondary border border-white/10 hover:border-white/20"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>
      ))}
    </div>
  );
}
