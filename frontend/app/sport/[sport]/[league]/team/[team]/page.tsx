"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchTeamPage, fetchChampionshipGrid } from "@/lib/api";
import type { TeamPageResponse, TeamFutureItem } from "@/lib/api";
import type { ChampionshipGridResponse } from "@/lib/types";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import LoadingState from "@/components/LoadingState";
import { getLeagueDisplay } from "@/lib/sportCategories";
import { isGameLive, assignGameNumbers } from "@/lib/teamGames";
import { sportKeyToGridSlug } from "@/lib/gridSlug";
import { buildDivisionRace } from "@/lib/teamDivisionRace";
import { pickJourneyFuture } from "@/lib/teamSeasonJourney";
import { UpcomingGameCard, RecentGameCard } from "@/components/TeamGameCards";
import { TeamChampionshipPath } from "@/components/TeamChampionshipPath";
import { TeamSeasonJourney } from "@/components/TeamSeasonJourney";
import { TeamDivisionRace } from "@/components/TeamDivisionRace";

export default function TeamPage() {
  const params = useParams();
  const sport = params.sport as string;
  const league = params.league as string;
  const teamSlug = params.team as string;

  usePageTracking({ pageType: "team", pageTitle: `Team — ${teamSlug}` });
  useScrollDepth({ pageType: "team" });
  useEngagementTime({ pageType: "team" });

  const [data, setData] = useState<TeamPageResponse | null>(null);
  const [grid, setGrid] = useState<ChampionshipGridResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setGrid(null);
    fetchTeamPage(teamSlug)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch(() => {
        if (!cancelled) setError("Team not found");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [teamSlug]);

  // Division-race data source: the league championship grid already carries every
  // rival's per-stage probability + division metadata. Supplementary + best-effort
  // — a failed/absent grid simply hides the Division Race section.
  useEffect(() => {
    const sportKey = data?.team?.sport_key;
    const gridSlug = sportKeyToGridSlug(sportKey);
    if (!gridSlug) return;
    let cancelled = false;
    fetchChampionshipGrid(gridSlug)
      .then((result) => {
        if (!cancelled) setGrid(result);
      })
      .catch(() => {
        if (!cancelled) setGrid(null);
      });
    return () => {
      cancelled = true;
    };
  }, [data?.team?.sport_key]);

  // Document title
  useEffect(() => {
    if (data?.team) {
      // Derive a clean league label from sport_key so the breadcrumb/title never
      // carries stale season-phase copy (e.g. "MLB Preseason") baked into
      // sport_name (L2-158 Item 3).
      const label = data.team.sport_key
        ? getLeagueDisplay(data.team.sport_key)
        : data.team.sport_name || league.toUpperCase();
      document.title = `${data.team.name} — ${label} | Bain Luck`;
    }
  }, [data, league]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4">
        <LoadingState message="Loading team..." />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 text-center">
        <p className="text-text-secondary text-sm mb-3">
          {error || `No team found for "${teamSlug}"`}
        </p>
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => window.location.reload()}
            className="text-sm text-accent-brand hover:underline transition-colors"
          >
            Try again
          </button>
          <Link
            href={`/sport/${sport}/${league}`}
            className="text-sm text-text-muted hover:text-text-primary transition-colors"
          >
            Back to {league.toUpperCase()}
          </Link>
        </div>
      </div>
    );
  }

  const { team, upcoming_events, recent_events, futures, championship_path } =
    data;
  const leaguePath = `/sport/${sport}/${league}`;
  // Clean league label — derived from sport_key, not the stale sport_name copy.
  const leagueLabel = team.sport_key
    ? getLeagueDisplay(team.sport_key)
    : team.sport_name || league.toUpperCase();

  // Doubleheader detection: same opponent + same day → G1/G2 chips.
  const upcomingGameNos = assignGameNumbers(upcoming_events);
  const recentGameNos = assignGameNumbers(recent_events);

  // Hero headline number — the team's "price" is its championship probability
  // (the blend-is-the-product ruling: one number per question). Prefer the
  // dedicated championship path (tier-1 Championship, else strongest step). When
  // the backend ships an empty champ-path but the futures payload still carries
  // the season markets (the live Red Sox case), fall back to the best season
  // future so the signature number never silently disappears.
  const headline: { label: string; probability: number; movement: number | null } | null =
    (() => {
      const pathEntry =
        championship_path.find((e) => e.tier === 1) ?? championship_path[0] ?? null;
      if (pathEntry && pathEntry.probability !== null) {
        return {
          label: pathEntry.label,
          probability: pathEntry.probability,
          movement: pathEntry.movement,
        };
      }
      const pick = pickJourneyFuture(futures);
      if (!pick || pick.probability === null) return null;
      const item = futures.find(
        (f) => f.market_id === pick.marketId && f.outcome_id === pick.outcomeId,
      );
      const tierLabel: Record<number, string> = { 1: "Championship", 2: "Conference", 4: "Division" };
      return {
        label: tierLabel[item?.market_tier ?? 1] ?? "Championship",
        probability: pick.probability,
        movement: item?.probability_change_24h ?? null,
      };
    })();

  // Division race (supplementary; null when it can't be shown honestly).
  const race = buildDivisionRace(grid, team.id, team.name);

  // Season futures: the championship path is surfaced as its own progression, so
  // the remaining list is props + awards + other markets (tiers outside 1/2/4).
  const propsAndAwards =
    championship_path.length > 0
      ? futures.filter((f) => ![1, 2, 4].includes(f.market_tier ?? -1))
      : futures;

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SportsTeam",
    name: team.name,
    sport: leagueLabel,
    ...(team.logo_large && { logo: team.logo_large }),
    ...(team.abbreviation && { alternateName: team.abbreviation }),
    memberOf: {
      "@type": "SportsOrganization",
      name: leagueLabel,
    },
    url: `https://bainluck.com/sport/${sport}/${league}/team/${teamSlug}`,
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      {/* Breadcrumb */}
      <nav className="text-sm text-text-secondary mb-6 flex items-center gap-1.5">
        <Link href="/" className="hover:text-text-primary">
          Home
        </Link>
        <span>/</span>
        <Link href={leaguePath} className="hover:text-text-primary">
          {leagueLabel}
        </Link>
        <span>/</span>
        <span className="text-text-primary">{team.name}</span>
      </nav>

      {/* Hero */}
      <div
        className="bg-surface-card border border-surface-border rounded-card p-6 mb-8 flex items-center gap-6 flex-wrap"
        style={
          team.primary_color
            ? { borderLeftWidth: 4, borderLeftColor: team.primary_color }
            : undefined
        }
      >
        {team.logo_large || team.logo_small ? (
          <img
            src={team.logo_large || team.logo_small || ""}
            alt={team.name}
            className="w-20 h-20 object-contain flex-shrink-0"
          />
        ) : (
          <div
            className="w-20 h-20 rounded-lg flex items-center justify-center text-2xl font-bold text-white flex-shrink-0"
            style={{ backgroundColor: team.primary_color || "#6B7280" }}
          >
            {team.abbreviation || team.name.charAt(0)}
          </div>
        )}
        <div className="min-w-[180px]">
          <h1 className="text-title-1 text-text-primary">{team.name}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-text-secondary">
            {team.record && <span className="font-medium">{team.record}</span>}
            {team.standings && (
              <>
                {(team.standings as Record<string, unknown>).conference && (
                  <span>
                    {String((team.standings as Record<string, unknown>).conference)}
                  </span>
                )}
                {(team.standings as Record<string, unknown>).conf_rank && (
                  <span>
                    #{String((team.standings as Record<string, unknown>).conf_rank)} in conference
                  </span>
                )}
              </>
            )}
          </div>
        </div>
        {/* Headline number — the team's championship "price" + 24h delta. */}
        {headline && (
          <div className="ml-auto flex flex-col items-end gap-0.5">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">
              {headline.label}
            </span>
            <span
              className="font-mono font-bold text-3xl leading-none tabular-nums"
              style={{ color: team.primary_color || undefined }}
            >
              {Math.round(headline.probability * 100)}%
            </span>
            {headline.movement !== null && headline.movement !== 0 && (
              <span
                className={`font-mono text-xs font-semibold tabular-nums ${
                  headline.movement > 0 ? "text-accent-live" : "text-accent-danger"
                }`}
              >
                {headline.movement > 0 ? "↑" : "↓"} {Math.abs(headline.movement * 100).toFixed(1)}% today
              </span>
            )}
          </div>
        )}
      </div>

      {/* Live & Upcoming Games */}
      {upcoming_events.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
            {upcoming_events.some((e) => isGameLive(e))
              ? "Live & Upcoming"
              : "Upcoming Games"}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {upcoming_events.map((event) => (
              <UpcomingGameCard
                key={event.id}
                game={event}
                teamName={team.name}
                teamColor={team.primary_color}
                gameNo={upcomingGameNos[event.id]}
              />
            ))}
          </div>
        </section>
      )}

      {/* Recent Results */}
      {recent_events.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
            Recent Results
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {recent_events.map((event) => (
              <RecentGameCard
                key={event.id}
                game={event}
                gameNo={recentGameNos[event.id]}
              />
            ))}
          </div>
        </section>
      )}

      {/* Season Journey — the team's championship prob over the season (one line). */}
      <TeamSeasonJourney futures={futures} teamColor={team.primary_color} />

      {/* Division Race — rivals × (Division / Playoffs / Champion), team highlighted. */}
      {race && <TeamDivisionRace race={race} teamColor={team.primary_color} />}

      {/* Season Futures — championship-path progression + props/awards. */}
      {(championship_path.length > 0 || futures.length > 0) && (
        <section className="mb-8">
          <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
            Season Futures
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {championship_path.length > 0 && (
              <TeamChampionshipPath
                entries={championship_path}
                color={team.primary_color}
              />
            )}
            {propsAndAwards.length > 0 && (
              <div className="flex flex-col gap-3">
                {propsAndAwards.map((item) => (
                  <FutureRow key={`${item.market_id}-${item.outcome_id}`} item={item} />
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      <div className="text-center text-[11px] text-text-muted mt-6">
        {team.name} · {futures.length} market{futures.length === 1 ? "" : "s"} tracked
      </div>
    </div>
  );
}

function FutureRow({ item }: { item: TeamFutureItem }) {
  const tierLabels: Record<number, string> = {
    1: "Championship",
    2: "Conference",
    3: "Award",
    4: "Division",
    5: "Prop",
  };
  const tierLabel = item.market_tier
    ? tierLabels[item.market_tier] || "Market"
    : "Market";

  return (
    <Link
      href={`/futures/${item.market_id}`}
      className="bg-surface-card border border-surface-border rounded-card p-4 hover:shadow-md transition-shadow flex items-center justify-between"
    >
      <div className="min-w-0 flex-1">
        <div className="text-xs text-accent-brand mb-0.5">{tierLabel}</div>
        <div className="text-sm font-medium text-text-primary truncate">
          {item.outcome_name}
        </div>
        <div className="text-xs text-text-secondary truncate">
          {item.market_name}
        </div>
      </div>
      <div className="text-right flex-shrink-0 ml-4">
        <div className="text-lg font-mono font-bold text-text-primary">
          {item.probability !== null
            ? `${Math.round(item.probability * 100)}%`
            : "—"}
        </div>
        {item.rank && item.total_outcomes && (
          <div className="text-xs text-text-muted">
            #{item.rank} of {item.total_outcomes}
          </div>
        )}
        {item.probability_change_24h !== null &&
          item.probability_change_24h !== 0 && (
            <div
              className={`text-xs ${
                item.probability_change_24h > 0
                  ? "text-accent-live"
                  : "text-accent-danger"
              }`}
            >
              {item.probability_change_24h > 0 ? "+" : ""}
              {(item.probability_change_24h * 100).toFixed(1)}%
            </div>
          )}
      </div>
    </Link>
  );
}
