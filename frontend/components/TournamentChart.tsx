"use client";

import { useState, useMemo, useCallback } from "react";
import useSWR from "swr";
import { fetchProbabilityTimeline, fetchCrossSourceTimeline } from "@/lib/api";
import type { ProbabilityTimelineResponse, TimelineEntry, TimelineOutcomeMeta } from "@/lib/types";
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceArea,
} from "recharts";
import { isInternationalSport, flagUrl } from "@/lib/images";

// =============================================================================
// Constants
// =============================================================================

/** Position-based fallback colors when no team colors available */
const POSITION_COLORS = [
  "#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c",
  "#0891b2", "#be185d", "#4f46e5", "#ca8a04", "#0d9488",
  "#6366f1", "#d946ef", "#14b8a6", "#f97316", "#8b5cf6",
  "#ef4444", "#06b6d4", "#84cc16", "#ec4899", "#78716c",
];

const FIELD_COLOR = "#6b7280";

/** Source display labels and colors for cross-source legend */
const SOURCE_DISPLAY: Record<string, { label: string; color: string }> = {
  odds_api: { label: "Sportsbooks", color: "#94a3b8" },
  kalshi: { label: "Kalshi", color: "#22c55e" },
  polymarket: { label: "Polymarket", color: "#3b82f6" },
};

type TopFilter = 5 | 10 | "all";
type SortColumn = "prob" | "change" | "name";

// =============================================================================
// Types
// =============================================================================

interface TournamentChartProps {
  marketId: number;
  /** Canonical market key — when provided, fetches cross-source merged timeline */
  canonicalKey?: string | null;
  /** Hours of history to fetch (default 168 = 7 days) */
  hours?: number;
  /** Chart height in px (default 300) */
  height?: number;
  /** Optional CSS class */
  className?: string;
  /** Anchor ID for deep-linking from category pages */
  id?: string;
}

/** Enriched participant for display */
interface Participant {
  id: number | null;
  name: string;
  displayName: string;       // Last name or short name
  fullName: string;           // Full name
  currentProbability: number;
  change24h: number | null;
  openingProbability: number | null;
  rank: number | null;
  // Team enrichment
  color: string;
  logoSmall: string | null;
  logoLarge: string | null;
  abbreviation: string | null;
  record: string | null;
  espnId: string | null;
  // Computed
  trend: number;              // difference from opening
  isField: boolean;
}

// =============================================================================
// Helpers
// =============================================================================

/** Extract a display name (last name or short version) */
function getDisplayName(name: string): string {
  // Handle "First Last" pattern
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return parts[parts.length - 1];
  return name;
}

/** Get participant color: team primary_color > position-based fallback */
function getColor(meta: TimelineOutcomeMeta, index: number): string {
  if (meta.primary_color) return `#${meta.primary_color.replace("#", "")}`;
  return POSITION_COLORS[index % POSITION_COLORS.length];
}

/** Build ESPN logo URL from espn_id if logo_small isn't set */
function getLogoUrl(meta: TimelineOutcomeMeta, sportCategory?: string | null): string | null {
  if (meta.logo_small) return meta.logo_small;
  if (meta.espn_id) {
    // Infer sport from category
    const sportMap: Record<string, string> = {
      basketball: "nba", football: "nfl", baseball: "mlb", hockey: "nhl",
      soccer: "soccer", golf: "golf",
    };
    const sport = sportMap[sportCategory ?? ""] ?? "nba";
    return `https://a.espncdn.com/combiner/i?img=/i/teamlogos/${sport}/500/${meta.espn_id}.png&w=40&h=40&transparent=true`;
  }
  return null;
}

/** Format timestamp for chart tooltip */
function formatTooltipTime(ts: string, bucketSeconds: number): string {
  const d = new Date(ts);
  if (bucketSeconds <= 3600) {
    return d.toLocaleString("en-US", {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });
  }
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Format chart X-axis ticks */
function formatXAxisTick(ts: string, rangeHours: number): string {
  const d = new Date(ts);
  if (rangeHours <= 48) {
    return d.toLocaleTimeString("en-US", { hour: "numeric" });
  }
  if (rangeHours <= 168) {
    return d.toLocaleDateString("en-US", { weekday: "short" });
  }
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// =============================================================================
// Main Component
// =============================================================================

export default function TournamentChart({
  marketId,
  canonicalKey,
  hours = 168,
  height = 300,
  className,
  id,
}: TournamentChartProps) {
  const [topFilter, setTopFilter] = useState<TopFilter>(10);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [sortColumn, setSortColumn] = useState<SortColumn>("prob");
  const [sortAsc, setSortAsc] = useState(false);

  // Fetch with top=50 to get all outcomes, then filter client-side
  // Use cross-source endpoint when canonical key is available
  const swrKey = canonicalKey
    ? `tournament-timeline-cross-${canonicalKey}-${hours}`
    : `tournament-timeline-${marketId}-${hours}`;

  const fetcher = () =>
    canonicalKey
      ? fetchCrossSourceTimeline(canonicalKey, 50, hours)
      : fetchProbabilityTimeline(marketId, 50, hours);

  const { data, error, isLoading } = useSWR(
    swrKey,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60_000 }
  );

  // Build enriched participants from API data
  const participants: Participant[] = useMemo(() => {
    if (!data) return [];
    return data.outcomes
      .filter((o) => o.name !== "Field")
      .map((o, idx) => ({
        id: o.id,
        name: o.name,
        displayName: getDisplayName(o.name),
        fullName: o.name,
        currentProbability: o.current_probability ?? 0,
        change24h: o.probability_change_24h ?? null,
        openingProbability: o.opening_probability ?? null,
        rank: o.rank ?? idx + 1,
        color: getColor(o, idx),
        logoSmall: getLogoUrl(o, data.sport_category),
        logoLarge: o.logo_large ?? null,
        abbreviation: o.abbreviation ?? null,
        record: o.record ?? null,
        espnId: o.espn_id ?? null,
        trend: o.probability_change_24h
          ? o.probability_change_24h
          : o.opening_probability && o.current_probability
            ? o.current_probability - o.opening_probability
            : 0,
        isField: false,
      }));
  }, [data]);

  // Auto-select top 3 on first load
  const effectiveSelected = useMemo(() => {
    if (selectedIds.size > 0) return selectedIds;
    // Default: select top 3
    return new Set(participants.slice(0, 3).map((p) => p.name));
  }, [selectedIds, participants]);

  // Filter + chart data
  const { displayedNames, nameToColor, hasField, chartData } = useMemo(() => {
    if (!data || data.timeline.length === 0) {
      return {
        displayedNames: [] as string[],
        nameToColor: {} as Record<string, string>,
        hasField: false,
        chartData: [] as Record<string, string | number>[],
      };
    }

    const allOutcomes = data.outcomes;
    const topN = topFilter === "all" ? allOutcomes.length : topFilter;
    const topOutcomes = allOutcomes.filter((o) => o.name !== "Field").slice(0, topN);
    const topNames = new Set(topOutcomes.map((o) => o.name));
    const showField = topFilter !== "all" && allOutcomes.length > topN;

    // Map names to enriched colors
    const colors: Record<string, string> = {};
    topOutcomes.forEach((o, i) => {
      const participant = participants.find((p) => p.name === o.name);
      colors[o.name] = participant?.color ?? POSITION_COLORS[i % POSITION_COLORS.length];
    });
    if (showField) colors["Field"] = FIELD_COLOR;

    // Build Recharts-compatible data
    const rechartsData: Record<string, string | number>[] = data.timeline.map((entry) => {
      const point: Record<string, string | number> = {
        timestamp: entry.timestamp,
      };
      let fieldProb = 0;

      for (const [name, prob] of Object.entries(entry.outcomes)) {
        if (name === "Field") continue;
        if (topNames.has(name)) {
          point[name] = Math.round(prob * 10000) / 100; // Convert to percentage
        } else if (showField) {
          fieldProb += prob;
        }
      }
      // Add server-side Field for outcomes beyond top 50
      if (showField && entry.outcomes.Field !== undefined) {
        fieldProb += entry.outcomes.Field;
      }
      if (showField && fieldProb > 0) {
        point["Field"] = Math.round(fieldProb * 10000) / 100;
      }
      return point;
    });

    return {
      displayedNames: topOutcomes.map((o) => o.name),
      nameToColor: colors,
      hasField: showField,
      chartData: rechartsData,
    };
  }, [data, topFilter, participants]);

  // Sorted participants for grid
  const sortedParticipants = useMemo(() => {
    const filtered = topFilter === "all"
      ? participants
      : participants.slice(0, typeof topFilter === "number" ? topFilter : participants.length);

    return [...filtered].sort((a, b) => {
      const dir = sortAsc ? 1 : -1;
      switch (sortColumn) {
        case "prob":
          return (b.currentProbability - a.currentProbability) * dir;
        case "change":
          return ((b.trend) - (a.trend)) * dir;
        case "name":
          return a.name.localeCompare(b.name) * dir;
        default:
          return 0;
      }
    });
  }, [participants, topFilter, sortColumn, sortAsc]);

  const togglePlayer = useCallback((name: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }, []);

  const handleSortClick = useCallback((col: SortColumn) => {
    if (sortColumn === col) {
      setSortAsc((prev) => !prev);
    } else {
      setSortColumn(col);
      setSortAsc(false);
    }
  }, [sortColumn]);

  // ==========================================================================
  // Render
  // ==========================================================================

  if (isLoading) {
    return (
      <div className={`h-48 flex items-center justify-center text-sm text-muted-foreground ${className ?? ""}`}>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-muted-foreground/30 border-t-muted-foreground rounded-full animate-spin" />
          Loading timeline...
        </div>
      </div>
    );
  }

  if (error || !data) return null;
  if (chartData.length < 2 || displayedNames.length === 0) return null;

  const sportCategory = data.sport_category ?? "";
  const isGolf = sportCategory === "golf";
  const isInternational = isInternationalSport(sportCategory);

  return (
    <div id={id} className={`bg-card rounded-lg border border-border overflow-hidden ${className ?? ""}`}>
      {/* Controls Row */}
      <div className="px-4 py-2.5 border-b border-border flex items-center justify-between bg-muted/30">
        {/* Top filter */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground uppercase tracking-wider mr-1">Show</span>
          <div className="flex rounded-md overflow-hidden border border-border">
            {([5, 10, "all"] as TopFilter[]).map((f) => (
              <button
                key={String(f)}
                onClick={() => setTopFilter(f)}
                className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                  topFilter === f
                    ? "bg-foreground text-background"
                    : "bg-card text-muted-foreground hover:bg-muted"
                }`}
              >
                {f === "all" ? "All" : `Top ${f}`}
              </button>
            ))}
          </div>
        </div>
        {/* Cross-source badge */}
        {data.sources && data.sources.length > 1 && (
          <div className="flex items-center gap-2">
            {data.sources.map((src) => {
              const label = SOURCE_DISPLAY[src]?.label ?? src;
              const color = SOURCE_DISPLAY[src]?.color ?? "#6b7280";
              return (
                <div key={src} className="flex items-center gap-1">
                  <div
                    className="w-1.5 h-1.5 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-[10px] text-muted-foreground">
                    {label}
                  </span>
                </div>
              );
            })}
            <span className="text-[10px] bg-primary/10 text-primary px-1.5 py-0.5 rounded font-medium">
              Merged
            </span>
          </div>
        )}
      </div>

      {/* Evolution Chart + Player Selection Panel */}
      <div className="px-4 py-3 border-b border-border">
        <div className="flex gap-4">
          {/* Chart */}
          <div className="flex-1" style={{ height: `${height}px` }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={chartData}
                margin={{ top: 10, right: 10, bottom: 5, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="hsl(var(--border))"
                  opacity={0.5}
                  vertical={false}
                />
                <XAxis
                  dataKey="timestamp"
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                  axisLine={{ stroke: "hsl(var(--border))" }}
                  tickLine={false}
                  tickFormatter={(v) => formatXAxisTick(v, hours)}
                  interval="preserveStartEnd"
                  minTickGap={60}
                />
                <YAxis
                  domain={[0, "auto"]}
                  tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `${v}%`}
                  width={40}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "6px",
                    fontSize: "11px",
                  }}
                  labelFormatter={(label) => formatTooltipTime(label, data.bucket_seconds)}
                  formatter={(value: number, name: string) => {
                    const p = participants.find((pp) => pp.name === name);
                    return [`${value.toFixed(1)}%`, p?.fullName ?? name];
                  }}
                  itemSorter={(item) => -(item.value as number ?? 0)}
                />

                {/* Outcome lines */}
                {[...displayedNames].reverse().map((name) => {
                  const isSelected = effectiveSelected.size === 0 || effectiveSelected.has(name);
                  const color = nameToColor[name] ?? FIELD_COLOR;
                  const isLeader = name === displayedNames[0];
                  return (
                    <Line
                      key={name}
                      type="monotone"
                      dataKey={name}
                      stroke={color}
                      strokeWidth={isLeader ? 2.5 : 1.5}
                      dot={false}
                      opacity={isSelected ? 1 : 0.12}
                      connectNulls
                    />
                  );
                })}

                {/* Field line */}
                {hasField && (
                  <Line
                    type="monotone"
                    dataKey="Field"
                    stroke={FIELD_COLOR}
                    strokeWidth={1.5}
                    strokeDasharray="6 3"
                    dot={false}
                    opacity={0.4}
                    connectNulls
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Player Selection Panel */}
          <div className="w-44 border-l border-border pl-3 flex-shrink-0 hidden sm:block">
            <div className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Highlight</div>
            <div className="space-y-0.5 max-h-64 overflow-y-auto pr-1">
              {participants.slice(0, Math.min(15, typeof topFilter === "number" ? topFilter : 15)).map((p) => {
                const isSelected = effectiveSelected.has(p.name);
                return (
                  <button
                    key={p.name}
                    onClick={() => togglePlayer(p.name)}
                    className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-left hover:bg-muted/50 transition-colors"
                  >
                    <div
                      className={`w-2.5 h-2.5 rounded-full flex-shrink-0 transition-opacity ${isSelected ? "" : "opacity-25"}`}
                      style={{ backgroundColor: p.color }}
                    />
                    {p.logoSmall ? (
                      <img
                        src={p.logoSmall}
                        alt=""
                        className={`w-4 h-4 object-contain flex-shrink-0 ${isSelected ? "" : "opacity-30"}`}
                      />
                    ) : null}
                    <span className={`text-xs truncate ${isSelected ? "text-foreground font-medium" : "text-muted-foreground"}`}>
                      {p.displayName}
                    </span>
                    <span className="text-[10px] text-muted-foreground ml-auto font-mono">
                      {Math.round(p.currentProbability * 100)}%
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Leaderboard Grid */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="px-3 py-2.5 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider w-10">#</th>
              <th
                className="px-3 py-2.5 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider cursor-pointer hover:text-foreground"
                onClick={() => handleSortClick("name")}
              >
                Participant {sortColumn === "name" && (sortAsc ? "↑" : "↓")}
              </th>
              {/* Record column (only for team sports) */}
              {participants.some((p) => p.record) && (
                <th className="px-3 py-2.5 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-20 hidden md:table-cell">
                  Record
                </th>
              )}
              <th
                className="px-3 py-2.5 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-20 cursor-pointer hover:text-foreground"
                onClick={() => handleSortClick("prob")}
              >
                Prob {sortColumn === "prob" && (sortAsc ? "↑" : "↓")}
              </th>
              <th
                className="px-3 py-2.5 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-20 cursor-pointer hover:text-foreground hidden sm:table-cell"
                onClick={() => handleSortClick("change")}
              >
                24h {sortColumn === "change" && (sortAsc ? "↑" : "↓")}
              </th>
              <th className="px-3 py-2.5 text-center text-xs font-medium text-muted-foreground uppercase tracking-wider w-24 hidden lg:table-cell">
                Trend
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedParticipants.map((p, index) => {
              const probPct = Math.round(p.currentProbability * 10000) / 100;
              const changePct = p.change24h != null ? Math.round(p.change24h * 10000) / 100 : null;
              const trendPct = Math.round(p.trend * 10000) / 100;
              const isSelected = effectiveSelected.has(p.name);

              return (
                <tr
                  key={p.name}
                  className={`border-b border-border transition-colors cursor-pointer ${
                    isSelected ? "bg-muted/20" : "hover:bg-muted/10"
                  }`}
                  onClick={() => togglePlayer(p.name)}
                >
                  {/* Position */}
                  <td className="px-3 py-2.5 text-muted-foreground text-xs">
                    <div className="flex items-center gap-1.5">
                      <div
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ backgroundColor: p.color }}
                      />
                      {index + 1}
                    </div>
                  </td>

                  {/* Participant name with logo/flag */}
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      {p.logoSmall ? (
                        <img
                          src={p.logoSmall}
                          alt=""
                          className="w-5 h-5 object-contain flex-shrink-0"
                        />
                      ) : isInternational || isGolf ? (
                        <FlagEmoji name={p.name} />
                      ) : (
                        <div
                          className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold text-white flex-shrink-0"
                          style={{ backgroundColor: p.color }}
                        >
                          {p.name.charAt(0)}
                        </div>
                      )}
                      <span className="font-medium text-foreground truncate max-w-[200px]">
                        {p.fullName}
                      </span>
                      {p.abbreviation && (
                        <span className="text-xs text-muted-foreground hidden md:inline">
                          {p.abbreviation}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Record */}
                  {participants.some((pp) => pp.record) && (
                    <td className="px-3 py-2.5 text-center text-xs text-muted-foreground hidden md:table-cell">
                      {p.record ?? "—"}
                    </td>
                  )}

                  {/* Probability */}
                  <td className="px-3 py-2.5 text-center">
                    <div className="flex items-center justify-center gap-1.5">
                      <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden hidden sm:block">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${Math.min(100, probPct)}%`,
                            backgroundColor: p.color,
                          }}
                        />
                      </div>
                      <span className="font-semibold text-foreground tabular-nums">
                        {probPct < 1 && probPct > 0 ? `${probPct.toFixed(1)}%` : `${Math.round(probPct)}%`}
                      </span>
                    </div>
                  </td>

                  {/* 24h Change */}
                  <td className="px-3 py-2.5 text-center hidden sm:table-cell">
                    {changePct != null ? (
                      <span className={`text-xs font-medium tabular-nums ${
                        changePct > 0 ? "text-green-600 dark:text-green-400" :
                        changePct < 0 ? "text-red-500 dark:text-red-400" :
                        "text-muted-foreground"
                      }`}>
                        {changePct > 0 ? "+" : ""}{changePct.toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>

                  {/* Trend (mini sparkline placeholder — from opening) */}
                  <td className="px-3 py-2.5 text-center hidden lg:table-cell">
                    <span className={`flex items-center justify-center gap-0.5 text-xs font-medium ${
                      trendPct > 0 ? "text-green-600 dark:text-green-400" :
                      trendPct < 0 ? "text-red-500 dark:text-red-400" :
                      "text-muted-foreground"
                    }`}>
                      {trendPct > 0 ? "▲" : trendPct < 0 ? "▼" : "—"}
                      {trendPct !== 0 && ` ${Math.abs(trendPct).toFixed(1)}%`}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

const COUNTRY_FLAGS: Record<string, string> = {
  "USA": "🇺🇸", "AUS": "🇦🇺", "AUT": "🇦🇹", "SWE": "🇸🇪", "ENG": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
  "CAN": "🇨🇦", "JPN": "🇯🇵", "KOR": "🇰🇷", "GER": "🇩🇪", "FRA": "🇫🇷",
  "ESP": "🇪🇸", "ITA": "🇮🇹", "NOR": "🇳🇴", "RSA": "🇿🇦", "IRL": "🇮🇪",
  "SCO": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "MEX": "🇲🇽", "ARG": "🇦🇷", "BRA": "🇧🇷", "COL": "🇨🇴",
  "CHI": "🇨🇱", "NZL": "🇳🇿", "IND": "🇮🇳", "THA": "🇹🇭", "CHN": "🇨🇳",
};

/** Tries to show a flag emoji for golfers / international participants */
function FlagEmoji({ name }: { name: string }) {
  // Known country suffixes in golfer names or parentheticals
  // For now, show a generic globe for unknown
  return (
    <span className="text-sm flex-shrink-0">🌐</span>
  );
}
