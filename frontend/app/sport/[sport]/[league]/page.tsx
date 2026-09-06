"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import ErrorBoundary from "@/components/ErrorBoundary";
import LoadingState from "@/components/LoadingState";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchSportHierarchyDetail,
  fetchGolfData,
  fetchChampionshipGrid,
  fetchGolfLeaderboard,
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
} from "@/lib/types";
import type { ApiError, LeagueFuturesResponse, LeagueMarket } from "@/lib/api";
import { describeLoadFailure } from "@/lib/loadFailure";
import {
  classifySportResolutionFailure,
  isUnreachable,
  type SportResolutionFailure,
} from "@/lib/hierarchyLoadFailure";
import PageLoadFailureScreen from "@/components/PageLoadFailureScreen";
import { gridCellsToProgression } from "@/lib/gridCellState";
import { partitionLeagueMarkets } from "@/lib/leagueCards";
import TournamentCard from "@/components/TournamentCard";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import LeagueMarketSection from "@/components/LeagueMarketSection";
import LeagueBinaryBoard from "@/components/LeagueBinaryBoard";
import LeagueGameRail from "@/components/LeagueGameRail";
import type { PositionOption } from "@/components/EvolutionView";
import MoversRibbon from "@/components/MoversRibbon";
import { earnsCountChip, earnsMoversStrip } from "@/lib/entityPageChrome";
import {
  countRenderedSections,
  resolveGridSlug,
  resolveLeagueTerminalState,
} from "@/lib/leaguePageChrome";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";

// Lazy-load the heavy interactive EvolutionView so it is not in this page's
// initial bundle (it stalled the league page 6–15s on first load while its APIs
// returned <0.4s — #901). Mirrors the event-detail page's chart code-splitting
// (app/events/[id]/page.tsx). L2-149: EvolutionView now renders the hand-rolled
// FuturesChart kernel (no recharts/date-fns), but the split still pays off — the
// component SWR-fetches its own data and shows its own loader, so deferring it
// has no data-correctness impact.
const ChartSkeleton = () => <div className="animate-pulse h-48 bg-surface-card rounded-xl" />;
const EvolutionView = dynamic(
  () => import("@/components/EvolutionView").then((m) => m.EvolutionView),
  { ssr: false, loading: ChartSkeleton },
);

// Some inbound URLs use the Odds API sport-key prefix (e.g. "icehockey",
// "americanfootball") while the /api/sports/hierarchy endpoint keys off the
// friendly sport slug ("hockey", "football"). Fetching the hierarchy with the
// raw prefix 404s, which previously surfaced as "Failed to load league data".
// Map known prefixes to their hierarchy slug so both URL forms resolve.
const SPORT_SLUG_ALIASES: Record<string, string> = {
  icehockey: "hockey",
  americanfootball: "football",
  mixed_martial_arts: "mma",
  aussierules: "aussie-rules",
};

/** Candidate hierarchy slugs to try, in order, for a given URL sport slug. */
function hierarchySlugCandidates(sportSlug: string): string[] {
  const candidates = [sportSlug];
  const aliased = SPORT_SLUG_ALIASES[sportSlug];
  if (aliased && aliased !== sportSlug) candidates.push(aliased);
  return candidates;
}

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
    resolved: c.resolved ?? false,
  }));

  const participants: ProgressionParticipant[] = (grid.teams || []).map((t) => {
    // Same register-backed state normalization as /playoffs/[sport] — settled
    // and missing cells render their state, never a stale-looking number.
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
  const [leagueMarkets, setLeagueMarkets] = useState<LeagueFuturesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<SportResolutionFailure | null>(null);

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
      setFailure(null);
      try {
        // Resolve the sport hierarchy. Inbound URLs may use the sport-key
        // prefix (e.g. "icehockey") instead of the hierarchy slug ("hockey"),
        // so try known aliases before giving up. A failure here is the only
        // hard failure for the page — everything below degrades gracefully.
        //
        // #3254: the hard failure is correct, the WORDING it produced was not.
        // This loop used a bare `catch {}` and then said `Sport "tennis" not
        // found` for every outcome, so a reader two seconds over the 60/min
        // anonymous bucket was told tennis does not exist — while the page
        // recovered on its own ~2 minutes later. Gotcha #36 ("never catch-all
        // in an API client returning Optional — 429 must re-raise") and #53
        // ("an empty read and a broken read must not render identically"), on
        // a rendered surface.
        //
        // So the two cases are now distinguished at the only place that can
        // tell them apart. A 404 from one candidate is the ALIAS MECHANISM
        // WORKING — "hockey" 404s before "icehockey" resolves — and must stay
        // silent. Anything else (429, 5xx, timeout, offline) means we could
        // not ask, which is never an answer of "no such sport". A single
        // unreachable candidate is therefore enough to disqualify the
        // not-found claim even if a later candidate cleanly 404s.
        let h: SportHierarchy | null = null;
        let unreachable: ApiError | null = null;
        for (const candidate of hierarchySlugCandidates(sportSlug)) {
          try {
            h = await fetchSportHierarchyDetail(candidate);
            if (h) break;
          } catch (err) {
            if (isUnreachable(err)) unreachable = err as ApiError;
          }
        }
        if (cancelled) return;
        if (!h) {
          setFailure(classifySportResolutionFailure(unreachable, sportSlug));
          setLoading(false);
          return;
        }
        setHierarchy(h);
        const l = h.leagues.find((lg) => lg.slug === leagueSlug);
        if (!l) {
          // The sport resolved and simply does not list this league — an
          // established absence, so "Back to Tennis" stays coherent here.
          setFailure({
            title: `League "${leagueSlug}" not found in ${h.name}`,
            message: `${h.name} does not list this league.`,
            retryable: false,
            sportAbsent: false,
            status: 404,
          });
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

        // Championship grid + league envelope (parallel, both supplementary)
        const sportKey = l.sport_keys[0];
        if (sportKey) {
          // UX-P062 (#1743), register E5: `GRID_SLUG_MAP` used to be hardcoded
          // right here. The grid slug is register data — it now rides the
          // hierarchy payload, so the page holds no map to drift.
          const gridSlug = resolveGridSlug(l.grid_slug, sportKey);
          const [gridResult, marketsResult] = await Promise.allSettled([
            fetchChampionshipGrid(gridSlug),
            fetchLeagueMarkets(sportKey),
          ]);
          if (cancelled) return;
          if (gridResult.status === "fulfilled") setGrid(gridResult.value);
          // Alex's amendment: the games rails ride this same payload, so the tier
          // the backend declared counts exactly the content the page renders.
          // Note the dropped `total_markets > 0` guard — a league with games and
          // no futures still has an envelope worth keeping (and a tier).
          if (marketsResult.status === "fulfilled") {
            setLeagueMarkets(marketsResult.value);
          }
        }
      } catch (err) {
        // Same rule as the loop above: name the failure we actually had rather
        // than the generic one. Nothing here has established an absence.
        if (!cancelled) {
          setFailure({
            ...describeLoadFailure(err as ApiError, "league"),
            sportAbsent: false,
            status: (err as ApiError)?.status,
          });
        }
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

  if (failure || !league) {
    const f: SportResolutionFailure = failure ?? {
      title: "League not found",
      message: `We could not find "${leagueSlug}".`,
      retryable: false,
      sportAbsent: false,
      status: 404,
    };
    // The escape link is chosen on what we ESTABLISHED, not on what failed:
    // pointing "Back to tennis" at a sport we have just declared absent is the
    // incoherence #3254 names. Every other failure leaves the sport presumed
    // fine, so the sport hub remains the useful place to go.
    const escape = f.sportAbsent
      ? { href: "/sports", label: "Browse all sports" }
      : {
          href: `/sport/${sportSlug}`,
          label: `Back to ${hierarchy?.name || sportSlug}`,
        };
    return (
      <PageLoadFailureScreen failure={f} status={f.status} escape={escape} />
    );
  }

  const heroTournament = liveTournaments[0] || upcomingTournaments[0];

  // ── UX-P062 (#1743, epic #1741): render the DECLARED tier, never infer it ──
  //
  // Ruling 021: the moment web and SwiftUI each count arrays to pick a layout, the
  // same league renders as a map on one and an answer on the other, and the parity
  // bug is unfindable because both clients are "correct".
  const tier = leagueMarkets?.tier ?? null;
  const upcomingGames = leagueMarkets?.upcoming_games ?? [];
  const recentResults = leagueMarkets?.recent_results ?? [];
  const unreportedGames = leagueMarkets?.unreported_games ?? [];
  const marketSections = Object.entries(leagueMarkets?.sections ?? {});
  const gridTeams = grid?.teams?.length ?? 0;

  // UX-1052 item 8 — every yes/no question on the page, collected ONCE.
  // `LeagueMarketSection` used to partition its own markets and draw its own
  // block, so the MLB page carried three: 55 binaries in `props`, 9 in
  // `more_markets`, and 1 in `awards` (a header over a single row). Alex saw
  // two of them and asked for the duplicate to go.
  // Not a `useMemo`: this sits below the page's early returns, where a hook
  // cannot go (react-hooks/rules-of-hooks), and the work is a linear pass over
  // the ~120 markets already in memory.
  const hoistedBinaries = marketSections.flatMap(
    ([, markets]) => partitionLeagueMarkets(markets as LeagueMarket[]).binaries,
  );

  // How many CONTAINERS the page is actually rendering — what a section header has
  // to distinguish itself from (spec §4). Counted here rather than inside each
  // section, because "am I the only thing on this page?" is a page-level question.
  const renderedSectionCount = countRenderedSections({
    marketSectionCount: marketSections.length,
    upcomingGameCount: upcomingGames.length,
    recentResultCount: recentResults.length,
    gridTeamCount: gridTeams,
  });

  // T0 (spec §6): a real league with nothing live to say — a STATEMENT, never
  // "check back later". `degraded` stays a DIFFERENT state: an outage that renders
  // as an off-season is the concealment ruling 025 clause 4 names.
  const terminalState = resolveLeagueTerminalState({
    loaded: leagueMarkets != null,
    tier,
    availability: leagueMarkets?.availability,
    marketSectionCount: marketSections.length,
    upcomingGameCount: upcomingGames.length,
  });

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
          {/* A count chip is a STAT. At 1-3 answers the count is already visible
              and printing it is the page apologizing for its size (spec \u00a73 bans it
              at T1) \u2014 this is what stopped boxing printing "0 active markets". */}
          {!golfData && grid && earnsCountChip(tier) && (
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

        {/* Movers Ribbon (team sports only — golf doesn't have movers).
            A movers strip below three is a list of one thing that moved (§4). */}
        {sportSlug !== "golf" && grid && earnsMoversStrip(grid.movers?.length ?? 0) && (
          <MoversRibbon
            movers={grid.movers}
            gridHref={`/sport/${sportSlug}/${leagueSlug}`}
          />
        )}

        {/* Games — Alex's 2026-08-11 amendment. Served by the league envelope, so
            the tier census counts exactly what renders here. */}
        <LeagueGameRail
          title={
            upcomingGames.some((g) => g.status === "live")
              ? "Live & Upcoming"
              : "Upcoming Games"
          }
          games={upcomingGames}
          hasMore={leagueMarkets?.upcoming_games_has_more}
        />

        <LeagueGameRail
          title="Recent Results"
          games={recentResults}
          hasMore={leagueMarkets?.recent_results_has_more}
          settled
        />

        {/* #3211 — matches whose kickoff has passed while the row still says
            `scheduled`. Before this they were on NO rail on this page: 171 US
            Open matches, the whole fortnight, permanently unreachable.

            A THIRD rail rather than more rows on "Recent Results", because they
            are stamped midnight of the current day (gotcha #14) and therefore
            sort above every Final — all eight of that rail's slots, measured,
            with the league's real results pushed off the page. One cap over two
            populations of very different size starves the smaller one; the fix
            is to split the bound, not to raise or reorder it.

            The heading is the same sentence the cards under it print, and it is
            deliberately not "Awaiting results": a promise about a future update
            is not a description of the state, and this state's whole job is to
            say exactly what is and is not known right now. It renders BELOW the
            results because it is the page's least informative content — every
            card says the same thing, which is that we do not know. */}
        <LeagueGameRail
          title="No result reported"
          games={unreportedGames}
          hasMore={leagueMarkets?.unreported_games_has_more}
          settled
        />

        {/* Championship Grid — before evolution chart for team sports, after for golf */}
        {sportSlug !== "golf" && grid && grid.teams && grid.teams.length > 0 && (
          <section>
            {/* UX-P062 (#1743), register E5: "View full grid →" linked to the
                page it was already on. A link that goes nowhere teaches a reader
                their tap did not register. The grid IS the full grid here. */}
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Championship Odds</h2>
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
            {/* UX-P062 (#1743), register E5: "View full grid →" linked to the
                page it was already on. A link that goes nowhere teaches a reader
                their tap did not register. The grid IS the full grid here. */}
            <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">Championship Odds</h2>
            <TournamentProgressionTable
              data={gridToProgression(grid)}
              pageType="sport_league"
            />
          </section>
        )}

        {/* League Market Sections (Series, Awards, Props, Stats, etc.).
            `sectionCount` + `tier` are passed so each section can decide whether
            it has EARNED its header and count chip (§4) — a header over one card
            on a page with one section is chrome organizing nothing. */}
        {marketSections
          .sort(([a], [b]) => (SECTION_META[a]?.order ?? 99) - (SECTION_META[b]?.order ?? 99))
          .map(([sectionKey, markets]) => (
            <LeagueMarketSection
              key={sectionKey}
              sectionKey={sectionKey}
              label={SECTION_META[sectionKey]?.label ?? sectionKey}
              markets={markets as LeagueMarket[]}
              sectionCount={renderedSectionCount}
              tier={tier}
              hoistBinaries
            />
          ))
        }

        {/* UX-1052 item 8 — ONE yes/no board for the whole page.
            Alex: "there is a SECOND Yes/No section at the bottom of the page."
            There were three, one per section that happened to hold a binary.
            The partition is a question about markets, not about sections, so it
            is asked once here. */}
        <LeagueBinaryBoard binaries={hoistedBinaries} />

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

        {/* ── T0 / honest-empty (spec §6, ruling 025) ──
            The old state read "No X data available right now / Check back when the
            season is active" — register E4's anti-pattern precisely: no why, no
            when, no record, and no way out of the page. A thin page is a COMPLETE
            page about a quiet league, so it says what IS true and links up.

            `degraded` is kept distinct from empty on purpose: an outage that
            renders as an off-season is the concealment clause 4 names. */}
        {terminalState === "degraded" && (
          <div className="text-center py-16" data-empty-state-name="league-degraded">
            <p className="text-text-secondary text-lg">
              {league.name} data didn&apos;t load
            </p>
            <p className="text-text-muted text-sm mt-2">
              This is a problem on our side, not a quiet week.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 text-sm text-accent-brand hover:underline"
            >
              Try again
            </button>
          </div>
        )}

        {terminalState === "present" && (
          <div className="text-center py-16" data-empty-state-name="league-present">
            <p className="text-text-secondary text-lg">
              Nothing open on {league.name} right now
            </p>
            {recentResults.length > 0 ? (
              <p className="text-text-muted text-sm mt-2">
                The last {recentResults.length} result
                {recentResults.length !== 1 ? "s" : ""} are above. New markets appear
                when the schedule picks back up.
              </p>
            ) : (
              <p className="text-text-muted text-sm mt-2">
                No live markets and no games in the last two weeks.
              </p>
            )}
            <Link
              href={`/sport/${sportSlug}`}
              className="mt-4 inline-block text-sm text-accent-brand hover:underline"
            >
              See all of {hierarchy?.name || sportSlug} &rarr;
            </Link>
          </div>
        )}
      </div>
    </div>
    </ErrorBoundary>
  );
}
