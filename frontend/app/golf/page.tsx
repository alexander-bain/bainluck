"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchGolfData } from "@/lib/api";
import type {
  GolfResponse,
  GolfTournament,
  GolfGolfer,
  GolfCurrentEvent,
  GolfMover,
} from "@/lib/types";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

// ============================================================================
// Constants
// ============================================================================

const TOURNAMENT_EMOJI: Record<string, string> = {
  masters: "\u{1F7E2}",
  pga_championship: "\u{1F3C6}",
  us_open: "\u{1F1FA}\u{1F1F8}",
  the_open: "\u{1F1EC}\u{1F1E7}",
  players: "\u26F3",
  ryder_cup: "\u{1F91D}",
  presidents_cup: "\u{1F30D}",
  liv: "\u{1F4B0}",
};

// ============================================================================
// Helper Components
// ============================================================================

function ProbabilityBar({ probability }: { probability: number }) {
  const pct = Math.round(probability * 100);
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: pct > 15 ? "#22c55e" : pct > 5 ? "#eab308" : "#6b7280",
          }}
        />
      </div>
      <span className="text-sm font-mono text-gray-300 w-[42px] text-right">
        {pct}%
      </span>
    </div>
  );
}

function AmericanOdds({ odds }: { odds: number | null }) {
  if (odds === null) return null;
  const formatted = odds > 0 ? `+${odds}` : `${odds}`;
  return <span className="text-xs text-gray-500 font-mono">{formatted}</span>;
}

function MovementBadge({ movement }: { movement: number | null }) {
  if (!movement || Math.abs(movement) < 0.005) return null;
  const pctPts = (movement * 100).toFixed(1);
  const isUp = movement > 0;
  return (
    <span
      className={`text-xs font-medium px-1.5 py-0.5 rounded ${
        isUp ? "bg-green-900/40 text-green-400" : "bg-red-900/40 text-red-400"
      }`}
    >
      {isUp ? "\u25B2" : "\u25BC"} {Math.abs(parseFloat(pctPts))}
    </span>
  );
}

function SourceDots({ sources }: { sources: Record<string, number> }) {
  const sourceColors: Record<string, string> = {
    odds_api: "#3b82f6",
    kalshi: "#22c55e",
    polymarket: "#8b5cf6",
  };
  const sourceLabels: Record<string, string> = {
    odds_api: "Sportsbooks",
    kalshi: "Kalshi",
    polymarket: "Polymarket",
  };
  return (
    <div className="flex gap-1">
      {Object.keys(sources).map((s) => (
        <span
          key={s}
          className="w-2 h-2 rounded-full inline-block"
          style={{ backgroundColor: sourceColors[s] || "#6b7280" }}
          title={`${sourceLabels[s] || s}: ${Math.round(sources[s] * 100)}%`}
        />
      ))}
    </div>
  );
}

// ============================================================================
// Current Event Banner
// ============================================================================

function CurrentEventBanner({ event }: { event: GolfCurrentEvent }) {
  const now = new Date();

  // Determine timing from start/end dates (StatPal) or resolution_date (fallback)
  let statusLabel = "Coming Up";
  let dateLabel = "";

  if (event.start_date && event.end_date) {
    const start = new Date(event.start_date);
    const end = new Date(event.end_date);
    if (now >= start && now <= end) {
      statusLabel = "This Week";
      dateLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${end.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
    } else if (now > end) {
      statusLabel = "Just Finished";
    } else {
      const daysUntil = Math.ceil((start.getTime() - now.getTime()) / 86400000);
      statusLabel = daysUntil <= 7 ? "This Week" : "Coming Up";
      dateLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
    }
  } else if (event.resolution_date) {
    const resDate = new Date(event.resolution_date);
    const daysUntil = Math.ceil((resDate.getTime() - now.getTime()) / 86400000);
    if (daysUntil < 0) {
      statusLabel = "Just Finished";
    } else if (daysUntil <= 7) {
      statusLabel = "This Week";
      dateLabel = `Ends ${resDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`;
    } else {
      dateLabel = resDate.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    }
  }

  return (
    <div className="bg-gradient-to-r from-green-900/30 via-green-800/20 to-emerald-900/30 border border-green-700/30 rounded-xl p-5 mb-8">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="text-green-400 text-xs font-semibold uppercase tracking-wider mb-1">
            {statusLabel}
          </p>
          <h2 className="text-xl font-bold text-white">{event.name}</h2>
          <p className="text-gray-400 text-sm mt-1">
            {event.venue && (
              <span>{event.venue} &middot; </span>
            )}
            {event.golfer_count} golfers with odds
            {dateLabel && (
              <span> &middot; {dateLabel}</span>
            )}
          </p>
        </div>
        {event.leader && event.leader_probability !== null && (
          <div className="text-right">
            <p className="text-xs text-gray-400 uppercase tracking-wider">
              Favorite
            </p>
            <p className="text-lg font-semibold text-white">{event.leader}</p>
            <p className="text-green-400 font-mono text-sm">
              {Math.round(event.leader_probability * 100)}%
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Golfer Row
// ============================================================================

function GolferRow({ golfer, rank }: { golfer: GolfGolfer; rank: number }) {
  return (
    <div className="flex items-center gap-3 py-2.5 px-3 hover:bg-white/[0.02] rounded-lg transition-colors">
      <span className="text-gray-500 text-sm font-mono w-6 text-right">
        {rank}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-white font-medium truncate">{golfer.name}</span>
          <MovementBadge movement={golfer.movement_24h} />
        </div>
      </div>
      <SourceDots sources={golfer.sources} />
      <AmericanOdds odds={golfer.american_odds} />
      <ProbabilityBar probability={golfer.probability} />
    </div>
  );
}

// ============================================================================
// Tournament Section
// ============================================================================

function TournamentSection({
  tournament,
  defaultExpanded,
}: {
  tournament: GolfTournament;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const emoji = TOURNAMENT_EMOJI[tournament.key] || "\u26F3";
  const golferCount = tournament.golfers.length;

  let timingLabel = "";
  if (tournament.start_date && tournament.end_date) {
    const start = new Date(tournament.start_date);
    const end = new Date(tournament.end_date);
    const now = new Date();
    if (now >= start && now <= end) {
      timingLabel = "In Progress";
    } else if (now > end) {
      timingLabel = "Completed";
    } else {
      const days = Math.ceil((start.getTime() - now.getTime()) / 86400000);
      if (days <= 7) {
        timingLabel = `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} – ${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
      } else {
        timingLabel = start.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      }
    }
  } else if (tournament.resolution_date) {
    const res = new Date(tournament.resolution_date);
    const now = new Date();
    const days = Math.ceil((res.getTime() - now.getTime()) / 86400000);
    if (days < 0) {
      timingLabel = "Completed";
    } else if (days === 0) {
      timingLabel = "Today";
    } else if (days <= 7) {
      timingLabel = res.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
    } else {
      timingLabel = res.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      });
    }
  }

  return (
    <div
      className={`rounded-xl border transition-colors ${
        tournament.is_major
          ? "border-yellow-700/30 bg-yellow-900/5"
          : tournament.is_tour_event
            ? "border-green-700/20 bg-green-900/5"
            : "border-gray-800 bg-gray-900/30"
      }`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-white/[0.02] rounded-xl transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">{emoji}</span>
          <div>
            <h3 className="text-lg font-semibold text-white">
              {tournament.name}
              {tournament.is_major && (
                <span className="ml-2 text-xs text-yellow-500 font-normal uppercase tracking-wider">
                  Major
                </span>
              )}
              {tournament.is_tour_event && (
                <span className="ml-2 text-xs text-green-500 font-normal uppercase tracking-wider">
                  Tour Event
                </span>
              )}
            </h3>
            <p className="text-sm text-gray-400">
              {golferCount} golfer{golferCount !== 1 ? "s" : ""}
              {tournament.venue && <span> &middot; {tournament.venue}</span>}
              {timingLabel && <span> &middot; {timingLabel}</span>}
            </p>
          </div>
        </div>
        <svg
          className={`w-5 h-5 text-gray-400 transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      {expanded && (
        <div className="px-4 pb-4">
          <div className="border-t border-gray-800/50 pt-3">
            {tournament.golfers.map((g, i) => (
              <GolferRow key={g.name} golfer={g} rank={i + 1} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Biggest Movers
// ============================================================================

function BiggestMovers({ movers }: { movers: GolfMover[] }) {
  if (movers.length === 0) return null;
  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold text-white mb-3">
        Biggest Movers (24h)
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {movers.map((m) => {
          const isUp = m.movement_24h > 0;
          const pctPts = Math.abs(m.movement_24h * 100).toFixed(1);
          return (
            <div
              key={`${m.name}-${m.tournament_key}`}
              className={`rounded-lg border p-3 ${
                isUp
                  ? "border-green-800/30 bg-green-900/10"
                  : "border-red-800/30 bg-red-900/10"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-white truncate">
                  {m.name}
                </span>
                <span
                  className={`font-mono text-sm font-semibold ${
                    isUp ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {isUp ? "\u25B2" : "\u25BC"} {pctPts}%
                </span>
              </div>
              <p className="text-xs text-gray-400 mt-1">
                {m.tournament_name} &middot;{" "}
                {Math.round(m.probability * 100)}% now
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// Main Page
// ============================================================================

export default function GolfPage() {
  usePageTracking({ pageType: "golf", pageTitle: "Golf Odds" });
  useScrollDepth({ pageType: "golf" });
  useEngagementTime({ pageType: "golf" });

  const [data, setData] = useState<GolfResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const result = await fetchGolfData();
        setData(result);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load golf data"
        );
      } finally {
        setLoading(false);
      }
    }
    load();

    const interval = setInterval(() => {
      fetchGolfData()
        .then(setData)
        .catch(() => {});
    }, 120_000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#09090b] text-white">
        <div className="max-w-4xl mx-auto px-4 py-12">
          <div className="animate-pulse space-y-6">
            <div className="h-8 bg-gray-800 rounded w-48" />
            <div className="h-24 bg-gray-800/50 rounded-xl" />
            <div className="h-64 bg-gray-800/30 rounded-xl" />
            <div className="h-64 bg-gray-800/30 rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-[#09090b] text-white flex items-center justify-center">
        <div className="text-center">
          <p className="text-xl mb-2">Unable to load golf data</p>
          <p className="text-gray-400 text-sm">{error}</p>
          <Link
            href="/"
            className="text-blue-400 hover:underline text-sm mt-4 inline-block"
          >
            Back to home
          </Link>
        </div>
      </div>
    );
  }

  const majors = data.tournaments.filter((t) => t.is_major);
  const tourEvents = data.tournaments.filter((t) => t.is_tour_event);
  const otherTournaments = data.tournaments.filter(
    (t) => !t.is_major && !t.is_tour_event
  );

  return (
    <div className="min-h-screen bg-[#09090b] text-white">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <Link
            href="/"
            className="text-gray-400 hover:text-white text-sm mb-4 inline-block transition-colors"
          >
            &larr; Back
          </Link>
          <h1 className="text-3xl font-bold">Golf Odds</h1>
          <p className="text-gray-400 mt-2">
            Tournament winner odds from sportsbooks and prediction markets.{" "}
            {data.total_golfers} golfers across {data.total_tournaments}{" "}
            tournaments.
          </p>
          {/* Source legend */}
          <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" />
              Sportsbooks
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
              Kalshi
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-purple-500 inline-block" />
              Polymarket
            </span>
          </div>
        </div>

        {/* Current Tour Event Banner */}
        {data.current_event && (
          <CurrentEventBanner event={data.current_event} />
        )}

        {/* Biggest Movers */}
        <BiggestMovers movers={data.biggest_movers} />

        {/* Majors */}
        {majors.length > 0 && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-yellow-400 mb-3">
              Major Championships
            </h2>
            <div className="space-y-3">
              {majors.map((t) => (
                <TournamentSection
                  key={t.key}
                  tournament={t}
                  defaultExpanded={true}
                />
              ))}
            </div>
          </div>
        )}

        {/* Tour Events */}
        {tourEvents.length > 0 && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-green-400 mb-3">
              Tour Events
            </h2>
            <div className="space-y-3">
              {tourEvents.map((t) => (
                <TournamentSection
                  key={t.key}
                  tournament={t}
                  defaultExpanded={tourEvents.length <= 3}
                />
              ))}
            </div>
          </div>
        )}

        {/* Other Tournaments */}
        {otherTournaments.length > 0 && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold text-gray-300 mb-3">Other</h2>
            <div className="space-y-3">
              {otherTournaments.map((t) => (
                <TournamentSection
                  key={t.key}
                  tournament={t}
                  defaultExpanded={false}
                />
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="mt-12 pt-6 border-t border-gray-800 text-center text-xs text-gray-500">
          <p>
            Odds aggregated from The Odds API, Kalshi, and Polymarket.
            Probabilities normalized per tournament. Updated every 2 minutes.
          </p>
        </div>
      </div>
    </div>
  );
}
