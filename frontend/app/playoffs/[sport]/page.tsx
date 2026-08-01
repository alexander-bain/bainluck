"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { fetchChampionshipGrid, fetchGolfSchedule } from "@/lib/api";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import { gridCellsToProgression } from "@/lib/gridCellState";
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
  GolfScheduleResponse,
  GolfScheduleEvent,
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
  { slug: "ncaa-women-basketball", label: "WNCAAB", emoji: "\u{1F3C0}", group: "college" },
  { slug: "ncaa-football", label: "NCAAF", emoji: "\u{1F3C8}", group: "college" },
  { slug: "epl", label: "EPL", emoji: "\u26BD", group: "soccer" },
  { slug: "la-liga", label: "La Liga", emoji: "\u26BD", group: "soccer" },
  { slug: "champions-league", label: "UCL", emoji: "\u26BD", group: "soccer" },
  { slug: "bundesliga", label: "Bundesliga", emoji: "\u26BD", group: "soccer" },
  { slug: "mls", label: "MLS", emoji: "\u26BD", group: "soccer" },
  { slug: "golf", label: "Golf", emoji: "\u26F3", group: "other" },
];

const LEAGUE_MAP: Record<string, LeagueInfo> = Object.fromEntries(LEAGUES.map((l) => [l.slug, l]));
LEAGUE_MAP["ucl"] = LEAGUE_MAP["champions-league"];
LEAGUE_MAP["ncaab"] = LEAGUE_MAP["ncaa-basketball"];
LEAGUE_MAP["ncaaf"] = LEAGUE_MAP["ncaa-football"];
LEAGUE_MAP["wncaab"] = LEAGUE_MAP["ncaa-women-basketball"];
LEAGUE_MAP["ncaa"] = LEAGUE_MAP["ncaa-basketball"];

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
    resolved: c.resolved ?? false,
  }));

  const participants: ProgressionParticipant[] = (teams || []).map((t) => {
    // Register-backed cells (Q295) carry a typed state; a settled or missing
    // cell must never render a live-looking number. The adapter is fail-closed
    // and never throws, so one poison cell cannot blank the row.
    const { probabilities, changes_24h, status, sources_data } = gridCellsToProgression(t?.cells);

    return {
      name: t.name,
      team_id: t.team_id,
      logo_url: t.logo_url,
      primary_color: t.primary_color,
      conference: t.conference,
      region: t.region ?? null,
      seed: t.seed ?? null,
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
  // Floor at 0.5 percentage points to suppress near-zero "0.0%" noise.
  // change_24h is a 0-1 fraction (e.g. 0.005 = 0.5pp), matching the native
  // iOS movers floor.
  const MOVER_FLOOR = 0.005; // 0.5 percentage points
  const realMovers = movers.filter(
    (m) => m.change_24h != null && Math.abs(m.change_24h) >= MOVER_FLOOR
  );
  if (!realMovers.length) return null;

  return (
    <div className="mb-5">
      <h2 className="text-xs font-medium text-text-secondary mb-2 uppercase tracking-wide">
        Biggest Movers (24h)
      </h2>
      <div className="flex flex-wrap gap-2">
        {realMovers.map((m) => {
          const pct = Math.abs((m.change_24h ?? 0) * 100);
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
              <span className="font-medium">{m.name || m.short_name}</span>
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
    : Array.from(new Set(chart.timeline.flatMap((e) => Object.keys(e.outcomes))));

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

  // X-axis date labels — one tick per calendar day at midnight
  const xTicks: { ts: number; label: string }[] = [];
  {
    const startDate = new Date(minT);
    startDate.setHours(0, 0, 0, 0);
    const endDate = new Date(maxT);
    endDate.setHours(23, 59, 59, 999);
    const cursor = new Date(startDate);
    cursor.setDate(cursor.getDate() + 1); // start from second day (first is often partial)
    while (cursor.getTime() <= endDate.getTime()) {
      xTicks.push({
        ts: cursor.getTime(),
        label: cursor.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      });
      cursor.setDate(cursor.getDate() + 1);
    }
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
              className="stroke-gray-200 dark:stroke-white/[0.06]"
              strokeWidth={1}
            />
            <text
              x={pad.left - 6}
              y={scaleY(tick) + 4}
              textAnchor="end"
              className="fill-gray-500 dark:fill-white/30"
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
            className="fill-gray-500 dark:fill-white/30"
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

function formatGolfDates(start?: string | null, end?: string | null): string | null {
  if (!start) return null;
  try {
    const s = new Date(start + "T00:00:00");
    const sStr = s.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    if (!end) return sStr;
    const e = new Date(end + "T00:00:00");
    const eStr = s.getMonth() === e.getMonth()
      ? e.toLocaleDateString("en-US", { day: "numeric" })
      : e.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return `${sStr}\u2013${eStr}`;
  } catch {
    return null;
  }
}

function GolfTournamentHeader({
  tournament,
  fieldCount,
  tourName,
}: {
  tournament: NonNullable<ChampionshipGridResponse["tournament"]>;
  fieldCount?: number;
  tourName?: string;
}) {
  const statusLabel = tournament.status === "live" ? "In Progress" : "Upcoming";
  const dateStr = formatGolfDates(tournament.start_date, tournament.end_date);

  return (
    <div className="mb-4 p-4 bg-surface-card rounded-xl border border-white/10">
      <div className="flex items-center gap-2 mb-1">
        {tourName && (
          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400">
            {tourName}
          </span>
        )}
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
          tournament.status === "live"
            ? "bg-emerald-500/20 text-emerald-400"
            : "bg-amber-500/20 text-amber-400"
        }`}>
          {statusLabel}
          {tournament.current_round && ` \u00B7 Round ${tournament.current_round}`}
        </span>
        {dateStr && (
          <span className="text-xs text-text-secondary/60">{dateStr}</span>
        )}
      </div>
      <h2 className="text-lg font-semibold text-text-primary">{tournament.name}</h2>
      <p className="text-sm text-text-secondary">
        {[tournament.course, tournament.location, tournament.country]
          .filter(Boolean)
          .join(" \u00B7 ")}
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
// Golf Schedule Section
// ---------------------------------------------------------------------------

function GolfScheduleSection({ schedule }: { schedule: GolfScheduleResponse }) {
  const [selectedTour, setSelectedTour] = useState<string>("pga");

  const tours = schedule.tours.filter((t) => t.events.length > 0);
  const activeTour = tours.find((t) => t.tour === selectedTour) || tours[0];
  if (!activeTour) return null;

  // Split events into recent/current/upcoming
  const currentEvent = activeTour.events.find((e) => e.is_current);
  const upcomingEvents = activeTour.events.filter(
    (e) => e.status === "upcoming" && !e.is_current
  );
  const completedEvents = activeTour.events
    .filter((e) => e.status === "completed")
    .reverse(); // Most recent first

  return (
    <div className="mb-6">
      {/* Tour tabs */}
      <div className="flex gap-1.5 mb-3 overflow-x-auto pb-1 scrollbar-hide">
        {tours.map((t) => {
          const hasCurrent = t.events.some((e) => e.is_current);
          return (
            <button
              key={t.tour}
              onClick={() => setSelectedTour(t.tour)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                t.tour === (activeTour?.tour || "pga")
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                  : "bg-surface-card text-text-secondary border border-white/10 hover:border-white/20"
              }`}
            >
              {t.tour_name}
              {hasCurrent && (
                <span className="ml-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block" />
              )}
            </button>
          );
        })}
      </div>

      {/* Current event highlight */}
      {currentEvent && (
        <div className="mb-3 p-3 bg-emerald-500/5 border border-emerald-500/20 rounded-lg">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 uppercase tracking-wider">
              This Week
            </span>
            {currentEvent.current_round && (
              <span className="text-[10px] text-emerald-400/70">
                Round {currentEvent.current_round}
              </span>
            )}
          </div>
          <div className="font-semibold text-text-primary">{currentEvent.name}</div>
          <div className="text-xs text-text-secondary">
            {[currentEvent.course, currentEvent.location]
              .filter(Boolean)
              .join(" · ")}
            {currentEvent.start_date && (
              <span className="ml-2 text-text-secondary/50">
                {formatGolfDates(currentEvent.start_date, currentEvent.end_date)}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Upcoming schedule — compact list */}
      {upcomingEvents.length > 0 && (
        <div className="mb-2">
          <h3 className="text-[10px] font-medium text-text-secondary/50 uppercase tracking-wider mb-1.5">
            Upcoming
          </h3>
          <div className="grid gap-1">
            {upcomingEvents.slice(0, 6).map((event) => (
              <div
                key={event.event_id}
                className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-surface-card/50 border border-white/5 text-sm"
              >
                <span className="text-text-primary truncate mr-2">{event.name}</span>
                <span className="text-xs text-text-secondary/50 whitespace-nowrap font-mono">
                  {event.start_date
                    ? formatGolfDates(event.start_date, event.end_date)
                    : "TBD"}
                </span>
              </div>
            ))}
            {upcomingEvents.length > 6 && (
              <p className="text-[10px] text-text-secondary/40 text-center mt-1">
                +{upcomingEvents.length - 6} more events
              </p>
            )}
          </div>
        </div>
      )}

      {/* Recent results — collapsible */}
      {completedEvents.length > 0 && (
        <details className="group">
          <summary className="text-[10px] font-medium text-text-secondary/50 uppercase tracking-wider cursor-pointer hover:text-text-secondary/70 transition-colors list-none flex items-center gap-1">
            <span className="text-text-secondary/30 group-open:rotate-90 transition-transform">▶</span>
            Recent Results ({completedEvents.length})
          </summary>
          <div className="grid gap-1 mt-1.5">
            {completedEvents.slice(0, 5).map((event) => (
              <div
                key={event.event_id}
                className="flex items-center justify-between px-3 py-1.5 rounded-lg bg-surface-card/30 border border-white/5 text-sm opacity-60"
              >
                <span className="text-text-secondary truncate mr-2">{event.name}</span>
                <span className="text-xs text-text-secondary/40 whitespace-nowrap font-mono">
                  {event.start_date
                    ? formatGolfDates(event.start_date, event.end_date)
                    : ""}
                </span>
              </div>
            ))}
          </div>
        </details>
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
    ? slug === "golf"
      ? "Golf Tournament Odds"
      : `${league.label} Championship Grid`
    : `${slug} Championship Grid`;

  usePageTracking({ pageType: "playoff_grid", pageTitle: `${displayName} - Bain Luck` });
  useScrollDepth({ pageType: "playoff_grid" });
  useEngagementTime({ pageType: "playoff_grid" });

  const [conferenceFilter, setConferenceFilter] = useState<string | null>(null);

  // Fetch grid data
  const {
    data: gridData,
    error: gridError,
    isLoading,
  } = useSWR(
    ["championship-grid", slug],
    () => fetchChampionshipGrid(slug),
    { refreshInterval: 60000 }
  );

  // #901: the server returns {error:"timeout"} (HTTP 200) when the grid rebuild
  // exceeds its 25s wait_for (golf cold-rebuilds were the worst offender). SWR
  // sees a successful response, so without this guard the page fell through to a
  // misleading "no odds available" empty state / infinite skeleton. Treat it as
  // a retryable error instead.
  const gridTimedOut = gridData?.error === "timeout";

  // Fetch golf schedule (only for golf)
  const { data: golfSchedule } = useSWR(
    slug === "golf" ? "golf-schedule" : null,
    () => fetchGolfSchedule(),
    { refreshInterval: 300000 } // 5 min
  );

  // Build progression tables — either grouped by conference or flat
  const sections = useMemo(() => {
    if (!gridData) return null;

    if (gridData.grouped_teams) {
      // Conference/region split
      return Object.entries(gridData.grouped_teams)
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
      // Don't show "Other" as a conference filter button — it's a fallback, not a real conference
      return Object.keys(gridData.grouped_teams).filter((c) => c !== "Other");
    }
    // Fallback: extract from league config
    return league?.conferences || [];
  }, [gridData, league]);

  // No config for this slug — show league picker
  if (!league) {
    return (
      <main className="min-h-screen">
        <div className="max-w-7xl mx-auto px-4 py-8">
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
    <main className="min-h-screen">
      <div className="max-w-7xl mx-auto px-4 py-6">
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

        {/* Golf schedule section */}
        {slug === "golf" && golfSchedule && (
          <GolfScheduleSection schedule={golfSchedule} />
        )}

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

        {/* #901: server-side rebuild timed out (HTTP 200 {error:"timeout"}) */}
        {!gridError && gridTimedOut && (
          <ErrorMessage message="The championship grid is taking longer than usual to load. Please try again in a moment." />
        )}

        {/* Multi-event golf rendering */}
        {gridData?.events && gridData.events.length > 0 ? (
          <>
            {gridData.events.map((event, eventIdx) => {
              const eventProgression = teamsToProgression(
                event.columns,
                event.teams,
                "golf",
                `${event.tour_name}: ${event.tournament.name}`,
              );

              return (
                <div key={event.tour + eventIdx} className={eventIdx > 0 ? "mt-8" : ""}>
                  {/* Tour + Tournament header */}
                  <GolfTournamentHeader
                    tournament={event.tournament}
                    fieldCount={event.field_count}
                    tourName={event.tour_name}
                  />

                  {/* Trend chart — only for primary event, needs 3+ outcomes and 3+ timeline entries */}
                  {eventIdx === 0 &&
                    event.trend_chart?.timeline?.length >= 3 &&
                    ((event.trend_chart.outcomes?.length ?? 0) >= 3 ||
                      Object.keys(event.trend_chart.timeline[0]?.outcomes ?? {}).length >= 3) && (
                    <TrendMiniChart chart={event.trend_chart} />
                  )}

                  {/* Movers */}
                  {event.movers.length > 0 && <MoversSection movers={event.movers} />}

                  {/* Grid */}
                  {eventProgression.participants.length > 0 && (
                    <TournamentProgressionTable
                      data={eventProgression}
                      showLogos={false}
                      pageType="playoff_grid"
                      className="bg-surface-card rounded-xl border border-white/10 p-4"
                    />
                  )}
                </div>
              );
            })}
          </>
        ) : (
          <>
            {/* Single-event rendering (non-golf sports) */}
            {gridData?.tournament && (
              <GolfTournamentHeader
                tournament={gridData.tournament}
                fieldCount={gridData.field_count}
              />
            )}

            {gridData?.trend_chart && (
              <TrendMiniChart chart={gridData.trend_chart} />
            )}

            {gridData?.movers && <MoversSection movers={gridData.movers} />}

            {/* Empty state */}
            {!isLoading && !gridError && !gridTimedOut && sections && sections.every((s) => s.data.participants.length === 0) && (
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
          </>
        )}

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
