"use client";

import { useEffect, useMemo, useState } from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import LoadingState from "@/components/LoadingState";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchSportHierarchyDetail,
  fetchGolfData,
  fetchChampionshipGrid,
  fetchGolfLeaderboard,
  fetchFeed,
  fetchLeagueMarkets,
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
  FeedItem,
  FeedEventData,
} from "@/lib/types";
import type { LeagueFuturesResponse, LeagueMarket } from "@/lib/api";
import TournamentCard from "@/components/TournamentCard";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import LeagueMarketSection from "@/components/LeagueMarketSection";
import { EvolutionView, type PositionOption } from "@/components/EvolutionView";
import FeedCard from "@/components/FeedCard";
import MoversRibbon from "@/components/MoversRibbon";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

const SECTION_META: Record<string, { label: string; order: number }> = {
  series: { label: "Playoff Series", order: 0 },
  matches: { label: "Upcoming Matches", order: 0 },
  awards: { label: "Awards", order: 1 },
  props: { label: "Props", order: 2 },
  season_stats: { label: "Season Stats", order: 3 },
  more_markets: { label: "More Markets", order: 4 },
};

// ============================================================================
// Adapters
// ============================================================================

/** Convert ChampionshipGridResponse -> ProgressionResponse for TournamentProgressionTable */
function gridToProgression(grid: ChampionshipGridResponse): ProgressionResponse {
  const stages: ProgressionStage[] = (grid.columns || []).map((c) => ({
    key: c.key,
    label: c.label,
    order: c.order,
    market_id: null,
    market_name: null,
  }));

  const participants: ProgressionParticipant[] = (grid.teams || []).map((t) => {
    const probabilities: Record<string, number | null> = {};
    const changes_24h: Record<string, number | null> = {};
    const status: Record<string, "clinched" | "eliminated" | null> = {};
    const sources_data: Record<string, { source: string; probability: number }[]> = {};
    const minimum_ticks: Record<string, boolean> = {};

    for (const [colKey, cell] of Object.entries(t.cells || {})) {
      probabilities[colKey] = cell?.merged_probability ?? null;
      changes_24h[colKey] = cell?.trend_24h ?? null;
      status[colKey] = null;
      if (cell?.sources) {
        sources_data[colKey] = cell.sources;
      }
      if (cell?.is_minimum_tick) {
        minimum_ticks[colKey] = true;
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
  const [todayEvents, setTodayEvents] = useState<FeedItem[]>([]);
  const [leagueMarkets, setLeagueMarkets] = useState<LeagueFuturesResponse | null>(null);
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

        // Championship grid + today's events + league markets (parallel, all supplementary)
        const sportKey = l.sport_keys[0];
        if (sportKey) {
          // Map sport_key to grid slug — grid slugs don't always match sport key suffixes
          const GRID_SLUG_MAP: Record<string, string> = {
            "soccer_usa_mls": "mls",
            "soccer_epl": "epl",
            "soccer_uefa_champs_league": "champions-league",
            "soccer_spain_la_liga": "la-liga",
            "soccer_germany_bundesliga": "bundesliga",
            "americanfootball_nfl": "nfl",
            "americanfootball_ncaaf": "ncaa-football",
            "basketball_nba": "nba",
            "basketball_ncaab": "ncaa-basketball",
            "basketball_wnba": "wnba",
            "icehockey_nhl": "nhl",
            "baseball_mlb": "mlb",
          };
          const gridSlug = GRID_SLUG_MAP[sportKey] || sportKey.split("_").slice(1).join("_") || sportKey;
          const [gridResult, feedResult, marketsResult] = await Promise.allSettled([
            fetchChampionshipGrid(gridSlug),
            fetchFeed({ sport: sportKey, include_futures: false, limit: 30 }),
            fetchLeagueMarkets(sportKey),
          ]);
          if (cancelled) return;
          if (gridResult.status === "fulfilled") setGrid(gridResult.value);
          if (marketsResult.status === "fulfilled" && marketsResult.value.total_markets > 0) {
            setLeagueMarkets(marketsResult.value);
          }
          if (feedResult.status === "fulfilled") {
            const events = feedResult.value.items
              .filter((item): item is FeedItem & { data: FeedEventData } => item.type === "event")
              .sort((a, b) => {
                const statusOrder = { live: 0, scheduled: 1, completed: 2, closed: 2 };
                const da = (a.data as FeedEventData).status;
                const db = (b.data as FeedEventData).status;
                const orderA = statusOrder[da] ?? 3;
                const orderB = statusOrder[db] ?? 3;
                if (orderA !== orderB) return orderA - orderB;
                return b.score - a.score;
              });
            setTodayEvents(events);
          }
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
          marketIds: c.market_ids,
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
        <LoadingState message="Loading league..." />
      </div>
    );
  }

  if (error || !league) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-4">
          <p className="text-text-secondary text-sm mb-3">{error || "League not found"}</p>
          <div className="flex items-center justify-center gap-4">
            <button
              onClick={() => window.location.reload()}
              className="text-sm text-accent-brand hover:underline transition-colors"
            >
              Try again
            </button>
            <Link href={`/sport/${sportSlug}`} className="text-sm text-text-muted hover:text-text-primary transition-colors">
              Back to {hierarchy?.name || sportSlug}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const heroTournament = liveTournaments[0] || upcomingTournaments[0];

  return (
    <ErrorBoundary fallback={<div className="p-8 text-center"><h2>Something went wrong</h2><button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">Reload page</button></div>}>
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-surface-border">
        <div className="max-w-7xl mx-auto px-4 py-8">
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
          {!golfData && grid && (
            <p className="text-text-secondary mt-2">
              {grid.team_count > 0 && `${grid.team_count} teams`}
              {grid.season && ` \u00b7 ${grid.season}`}
              {grid.sources_available?.length > 0 && (
                <> &middot; {grid.sources_available.length} source{grid.sources_available.length !== 1 ? "s" : ""}</>
              )}
              {leagueMarkets && leagueMarkets.total_markets > 0 && (
                <> &middot; {leagueMarkets.total_markets} market{leagueMarkets.total_markets !== 1 ? "s" : ""}</>
              )}
            </p>
          )}
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-8 space-y-10">

        {/* ============================================================ */}
        {/* GOLF LAYOUT: Hero tournament → Games → Evolution → Grid → Markets → Upcoming → Completed */}
        {/* ============================================================ */}

        {/* Hero: Current/Live Tournament (golf) */}
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

        {/* ============================================================ */}
        {/* TEAM SPORT LAYOUT: Movers → Games → Grid → Evolution → Markets */}
        {/* ============================================================ */}

        {/* Movers Ribbon (team sports only — golf doesn't have movers) */}
        {sportSlug !== "golf" && grid && grid.movers && grid.movers.length > 0 && (
          <MoversRibbon
            movers={grid.movers}
            gridHref={`/sport/${sportSlug}/${leagueSlug}`}
          />
        )}

        {/* Today's Games */}
        {todayEvents.length > 0 && (
          <section>
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
              {todayEvents.some((e) => (e.data as FeedEventData).status === "live")
                ? "Live & Today's Games"
                : "Today's Games"}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {todayEvents.map((item) => (
                <FeedCard key={(item.data as FeedEventData).id} item={item} />
              ))}
            </div>
          </section>
        )}

        {/* Championship Grid — before evolution chart for team sports, after for golf */}
        {sportSlug !== "golf" && grid && grid.teams && grid.teams.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide">Championship Odds</h2>
              <Link
                href={`/sport/${sportSlug}/${leagueSlug}`}
                className="text-xs font-medium text-accent-brand hover:underline"
              >
                View full grid &rarr;
              </Link>
            </div>
            <TournamentProgressionTable
              data={gridToProgression(grid)}
              pageType="sport_league"
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
              entityLabel={sportSlug === "golf" ? "Players" : "Teams"}
            />
          </section>
        )}

        {/* Championship Grid — after evolution chart for golf */}
        {sportSlug === "golf" && grid && grid.teams && grid.teams.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide">Championship Odds</h2>
              <Link
                href={`/sport/${sportSlug}/${leagueSlug}`}
                className="text-xs font-medium text-accent-brand hover:underline"
              >
                View full grid &rarr;
              </Link>
            </div>
            <TournamentProgressionTable
              data={gridToProgression(grid)}
              pageType="sport_league"
            />
          </section>
        )}

        {/* League Market Sections (Series, Awards, Props, Stats, etc.) */}
        {leagueMarkets && Object.entries(leagueMarkets.sections)
          .sort(([a], [b]) => (SECTION_META[a]?.order ?? 99) - (SECTION_META[b]?.order ?? 99))
          .map(([sectionKey, markets]) => (
            <LeagueMarketSection
              key={sectionKey}
              sectionKey={sectionKey}
              label={SECTION_META[sectionKey]?.label ?? sectionKey}
              markets={markets as LeagueMarket[]}
            />
          ))
        }

        {/* Upcoming Tournaments (golf) */}
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

        {/* Recently Completed (golf) */}
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

        {/* Empty state — only when there is truly no data at all */}
        {sportSlug !== "golf" && !grid && todayEvents.length === 0 && !leagueMarkets && (
          <div className="text-center py-16">
            <p className="text-text-secondary text-lg">
              No {league.name} data available right now
            </p>
            <p className="text-text-muted text-sm mt-2">
              Check back when the season is active for championship odds, games, and market analysis
            </p>
          </div>
        )}
      </div>
    </div>
    </ErrorBoundary>
  );
}
