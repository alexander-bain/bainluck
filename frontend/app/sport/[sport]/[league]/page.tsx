"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchSportHierarchyDetail,
  fetchGolfData,
  fetchChampionshipGrid,
  fetchGolfLeaderboard,
} from "@/lib/api";
import type {
  SportHierarchy,
  SportLeague,
  GolfResponse,
  GolfTournament,
  GolfLeaderboardPlayer,
  ChampionshipGridResponse,
  ChampionshipGridTeam,
  ProgressionResponse,
  ProgressionStage,
  ProgressionParticipant,
} from "@/lib/types";
import TournamentCard from "@/components/TournamentCard";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import { EvolutionView, type PositionOption } from "@/components/EvolutionView";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

// ============================================================================
// Adapters
// ============================================================================

/** Convert ChampionshipGridResponse -> ProgressionResponse for TournamentProgressionTable */
function gridToProgression(grid: ChampionshipGridResponse): ProgressionResponse {
  const stages: ProgressionStage[] = grid.columns.map((c) => ({
    key: c.key,
    label: c.label,
    order: c.order,
    market_id: null,
    market_name: null,
  }));

  const participants: ProgressionParticipant[] = grid.teams.map((t) => {
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
    sport: grid.name,
    tournament_name: grid.name,
    stages,
    participants,
  };
}

// ============================================================================
// Helpers
// ============================================================================

function tournamentStatus(t: GolfTournament): "live" | "completed" | "upcoming" {
  const now = new Date();
  const start = t.start_date ? new Date(t.start_date) : t.commence_time ? new Date(t.commence_time) : null;
  const end = t.resolution_date ? new Date(t.resolution_date) : t.end_date ? new Date(t.end_date) : null;

  if (start && end && now >= start && now <= new Date(end.getTime() + 24 * 3600_000)) return "live";
  if (end && now > new Date(end.getTime() + 24 * 3600_000)) return "completed";
  return "upcoming";
}

function sortTournaments(a: GolfTournament, b: GolfTournament): number {
  const sa = tournamentStatus(a);
  const sb = tournamentStatus(b);
  const order = { live: 0, upcoming: 1, completed: 2 };
  if (order[sa] !== order[sb]) return order[sa] - order[sb];

  const dateA = a.commence_time ? new Date(a.commence_time).getTime() : 0;
  const dateB = b.commence_time ? new Date(b.commence_time).getTime() : 0;
  if (sa === "completed") return dateB - dateA;
  return dateA - dateB;
}

// ============================================================================
// Main Component
// ============================================================================

export default function LeagueShowcasePage() {
  const params = useParams();
  const sportSlug = params.sport as string;
  const leagueSlug = params.league as string;

  const [hierarchy, setHierarchy] = useState<SportHierarchy | null>(null);
  const [league, setLeague] = useState<SportLeague | null>(null);
  const [golfData, setGolfData] = useState<GolfResponse | null>(null);
  const [leaderboard, setLeaderboard] = useState<GolfLeaderboardPlayer[]>([]);
  const [grid, setGrid] = useState<ChampionshipGridResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Analytics
  usePageTracking({
    pageType: "sport_league",
    pageTitle: `${leagueSlug.toUpperCase()} - ${sportSlug} - BainLuck`,
  });
  useScrollDepth({ pageType: "sport_league" });
  useEngagementTime({ pageType: "sport_league" });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const h = await fetchSportHierarchyDetail(sportSlug);
        if (cancelled) return;
        setHierarchy(h);
        const l = h.leagues.find((lg) => lg.slug === leagueSlug);
        if (!l) {
          setError(`League "${leagueSlug}" not found in ${h.name}`);
          setLoading(false);
          return;
        }
        setLeague(l);

        // Golf-specific data loading
        if (sportSlug === "golf") {
          const results = await Promise.allSettled([
            fetchGolfData(),
            fetchGolfLeaderboard(leagueSlug === "dpworld" ? "euro" : leagueSlug),
          ]);
          if (cancelled) return;
          if (results[0].status === "fulfilled") setGolfData(results[0].value);
          if (results[1].status === "fulfilled") setLeaderboard(results[1].value.players || []);
        }

        // Championship grid (works for any sport)
        try {
          const sportKey = l.sport_keys[0];
          if (sportKey) {
            const gridSlug = sportKey.split("_").slice(1).join("_") || sportKey;
            const gridData = await fetchChampionshipGrid(gridSlug);
            if (!cancelled) setGrid(gridData);
          }
        } catch {
          // Grid is supplementary
        }
      } catch {
        if (!cancelled) setError("Failed to load league data");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [sportSlug, leagueSlug]);

  const { liveTournaments, upcomingTournaments, completedTournaments } = useMemo(() => {
    if (!golfData) return { liveTournaments: [] as GolfTournament[], upcomingTournaments: [] as GolfTournament[], completedTournaments: [] as GolfTournament[] };

    const tourFilter = leagueSlug === "dpworld" ? "dp_world"
      : leagueSlug === "kft" ? "korn_ferry"
      : leagueSlug;
    const filtered = golfData.tournaments
      .filter((t) => {
        const tour = t.tour?.toLowerCase() || "";
        return tour === tourFilter || tour === leagueSlug;
      })
      .sort(sortTournaments);

    const live: GolfTournament[] = [];
    const upcoming: GolfTournament[] = [];
    const completed: GolfTournament[] = [];
    for (const t of filtered) {
      const s = tournamentStatus(t);
      if (s === "live") live.push(t);
      else if (s === "upcoming") upcoming.push(t);
      else completed.push(t);
    }
    if (live.length === 0 && upcoming.length === 0 && completed.length === 0 && leagueSlug === "pga") {
      const allSorted = [...golfData.tournaments].sort(sortTournaments);
      for (const t of allSorted) {
        const s = tournamentStatus(t);
        if (s === "live") live.push(t);
        else if (s === "upcoming") upcoming.push(t);
        else completed.push(t);
      }
    }
    return { liveTournaments: live, upcomingTournaments: upcoming, completedTournaments: completed };
  }, [golfData, leagueSlug]);

  // Build evolution chart market ID + stage position options from grid columns
  const { evolutionMarketId, evolutionPositionOptions } = useMemo(() => {
    // Non-golf: build position options from grid columns that have market_ids
    if (grid?.columns) {
      const options: PositionOption[] = grid.columns
        .filter((c) => c.market_id)
        .map((c) => ({
          key: c.key,
          label: c.label,
          marketId: c.market_id!,
        }));
      if (options.length > 0) {
        // Default to the last column (championship) — it's the most interesting
        return {
          evolutionMarketId: options[options.length - 1].marketId,
          evolutionPositionOptions: options.length > 1 ? options : undefined,
        };
      }
    }
    // Fallback: championship_market_id from grid
    if (grid?.championship_market_id) {
      return { evolutionMarketId: grid.championship_market_id, evolutionPositionOptions: undefined };
    }
    // Golf: use the hero tournament's first market
    const hero = liveTournaments[0] || upcomingTournaments[0];
    return {
      evolutionMarketId: hero?.market_ids?.[0] ?? null,
      evolutionPositionOptions: undefined,
    };
  }, [grid, liveTournaments, upcomingTournaments]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-text-muted">Loading...</div>
      </div>
    );
  }

  if (error || !league) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-text-muted mb-4">{error || "League not found"}</p>
          <Link href={`/sport/${sportSlug}`} className="text-accent-brand hover:underline">
            Back to {hierarchy?.name || sportSlug}
          </Link>
        </div>
      </div>
    );
  }

  const heroTournament = liveTournaments[0] || upcomingTournaments[0];

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-surface-border">
        <div className="max-w-5xl mx-auto px-4 py-8">
          <div className="flex items-center gap-2 text-sm text-text-muted mb-4">
            <Link href="/" className="hover:text-text-primary transition-colors">Home</Link>
            <span>/</span>
            <Link href="/sport" className="hover:text-text-primary transition-colors">Sports</Link>
            <span>/</span>
            <Link href={`/sport/${sportSlug}`} className="hover:text-text-primary transition-colors">
              {hierarchy?.name || sportSlug}
            </Link>
            <span>/</span>
            <span className="text-text-primary">{league.name}</span>
          </div>
          <h1 className="text-3xl font-bold text-text-primary">{league.name}</h1>
          {golfData && (
            <p className="text-text-secondary mt-2">
              {liveTournaments.length > 0 && `${liveTournaments.length} live`}
              {liveTournaments.length > 0 && upcomingTournaments.length > 0 && " \u00b7 "}
              {upcomingTournaments.length > 0 && `${upcomingTournaments.length} upcoming`}
              {(liveTournaments.length > 0 || upcomingTournaments.length > 0) && completedTournaments.length > 0 && " \u00b7 "}
              {completedTournaments.length > 0 && `${completedTournaments.length} completed`}
            </p>
          )}
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 py-8 space-y-10">

        {/* Hero: Current/Live Tournament */}
        {heroTournament && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
              {liveTournaments.length > 0 ? "Live Now" : "Next Up"}
            </h2>
            <TournamentCard
              tournament={heroTournament}
              leaderboard={leaderboard}
              href={`/sport/${sportSlug}/${leagueSlug}/${heroTournament.slug || heroTournament.key.replace(/_/g, "-")}`}
            />
          </section>
        )}

        {/* Evolution Chart */}
        {evolutionMarketId && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Odds Movement</h2>
            <EvolutionView
              marketId={evolutionMarketId}
              marketName={heroTournament?.name || grid?.name || league.name}
              defaultTopN={5}
              hours={168}
              positionOptions={evolutionPositionOptions}
            />
          </section>
        )}

        {/* Championship Grid (inline) */}
        {grid && grid.teams && grid.teams.length > 0 && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Championship Odds</h2>
            <TournamentProgressionTable
              data={gridToProgression(grid)}
              pageType="sport_league"
            />
          </section>
        )}

        {/* Upcoming Tournaments */}
        {upcomingTournaments.length > (heroTournament && tournamentStatus(heroTournament) === "upcoming" ? 1 : 0) && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Upcoming</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {upcomingTournaments
                .filter((t: GolfTournament) => t !== heroTournament)
                .map((t: GolfTournament) => (
                  <TournamentCard
                    key={t.key}
                    tournament={t}
                    href={`/sport/${sportSlug}/${leagueSlug}/${t.slug || t.key.replace(/_/g, "-")}`}
                  />
                ))}
            </div>
          </section>
        )}

        {/* Recently Completed */}
        {completedTournaments.length > 0 && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Recently Completed</h2>
            <p className="text-text-muted text-sm mb-4">Showing pre-tournament odds</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {completedTournaments.slice(0, 6).map((t: GolfTournament) => (
                <TournamentCard
                  key={t.key}
                  tournament={t}
                  href={`/sport/${sportSlug}/${leagueSlug}/${t.slug || t.key.replace(/_/g, "-")}`}
                />
              ))}
            </div>
          </section>
        )}

        {/* Empty state for non-golf sports */}
        {sportSlug !== "golf" && !grid && (
          <div className="text-center py-16">
            <p className="text-text-secondary text-lg">
              {league.name} page coming soon
            </p>
            <p className="text-text-muted text-sm mt-2">
              Event cards and championship grid will appear here
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
