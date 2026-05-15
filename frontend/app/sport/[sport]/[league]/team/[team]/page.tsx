"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchTeamPage } from "@/lib/api";
import type { TeamPageResponse, ChampionshipPathEntry, TeamFutureItem } from "@/lib/api";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import TeamNameLink from "@/components/TeamNameLink";

export default function TeamPage() {
  const params = useParams();
  const sport = params.sport as string;
  const league = params.league as string;
  const teamSlug = params.team as string;

  usePageTracking({ pageType: "team", pageTitle: `Team — ${teamSlug}` });
  useScrollDepth({ pageType: "team" });
  useEngagementTime({ pageType: "team" });

  const [data, setData] = useState<TeamPageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
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

  // Document title
  useEffect(() => {
    if (data?.team) {
      const label = data.team.sport_name || league.toUpperCase();
      document.title = `${data.team.name} — ${label} | Bain Luck`;
    }
  }, [data, league]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 text-center">
        <div className="text-4xl mb-4 animate-pulse">...</div>
        <p className="text-text-secondary">Loading team...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 text-center">
        <h1 className="text-title-2 text-text-primary mb-2">Team Not Found</h1>
        <p className="text-text-secondary">
          No team found for &quot;{teamSlug}&quot;
        </p>
        <Link
          href={`/sport/${sport}/${league}`}
          className="mt-4 inline-block text-sm text-accent-brand hover:underline"
        >
          Back to {league.toUpperCase()}
        </Link>
      </div>
    );
  }

  const { team, upcoming_events, recent_events, futures, championship_path } =
    data;
  const leaguePath = `/sport/${sport}/${league}`;
  const leagueLabel = team.sport_name || league.toUpperCase();

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
          {team.sport_name || league.toUpperCase()}
        </Link>
        <span>/</span>
        <span className="text-text-primary">{team.name}</span>
      </nav>

      {/* Hero */}
      <div
        className="bg-surface-card border border-surface-border rounded-card p-6 mb-8 flex items-center gap-6"
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
        <div>
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
      </div>

      {/* Championship Path */}
      {championship_path.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
            Championship Path
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {championship_path.map((entry) => (
              <ChampionshipCard key={entry.tier} entry={entry} color={team.primary_color} />
            ))}
          </div>
        </section>
      )}

      {/* Live & Upcoming Games */}
      {upcoming_events.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
            {upcoming_events.some((e) => e.status === "live")
              ? "Live & Upcoming"
              : "Upcoming Games"}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {upcoming_events.map((event) => (
              <GameCard key={event.id} event={event} teamName={team.name} sportKey={team.sport_key} />
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
              <GameCard key={event.id} event={event} teamName={team.name} sportKey={team.sport_key} />
            ))}
          </div>
        </section>
      )}

      {/* Season Futures */}
      {futures.length > 0 && (
        <section className="mb-8">
          <h2 className="text-xs font-medium text-text-secondary uppercase tracking-wide mb-4">
            Season Futures
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {futures.map((item) => (
              <FutureRow key={`${item.market_id}-${item.outcome_id}`} item={item} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function ChampionshipCard({
  entry,
  color,
}: {
  entry: ChampionshipPathEntry;
  color: string | null;
}) {
  const prob = entry.probability;
  return (
    <Link
      href={`/futures/${entry.market_id}`}
      className="bg-surface-card border border-surface-border rounded-card p-4 hover:shadow-md transition-shadow"
    >
      <div className="text-xs text-text-secondary mb-1">{entry.label}</div>
      <div className="flex items-baseline gap-2">
        <span
          className="text-2xl font-mono font-bold"
          style={{ color: color || undefined }}
        >
          {prob !== null ? `${Math.round(prob * 100)}%` : "—"}
        </span>
        {entry.rank && (
          <span className="text-xs text-text-muted">
            #{entry.rank}
          </span>
        )}
      </div>
      {entry.movement !== null && entry.movement !== 0 && (
        <div
          className={`text-xs mt-1 ${
            entry.movement > 0 ? "text-accent-live" : "text-accent-danger"
          }`}
        >
          {entry.movement > 0 ? "+" : ""}
          {(entry.movement * 100).toFixed(1)}%
        </div>
      )}
    </Link>
  );
}

function GameCard({
  event,
  teamName,
  sportKey,
}: {
  event: TeamPageResponse["upcoming_events"][0];
  teamName: string;
  sportKey?: string | null;
}) {
  const isHome =
    event.home_team === teamName ||
    (event as unknown as Record<string, unknown>).is_home === true;
  const opponent = isHome ? event.away_team : event.home_team;
  const wp = (event as unknown as Record<string, unknown>).win_probability as
    | number
    | null
    | undefined;
  const isLive = event.status === "live";
  const isCompleted = event.status === "completed";

  let score: string | null = null;
  if (event.home_score !== null && event.away_score !== null) {
    const teamScore = isHome ? event.home_score : event.away_score;
    const oppScore = isHome ? event.away_score : event.home_score;
    score = `${teamScore}–${oppScore}`;
    if (isCompleted) {
      score =
        (teamScore ?? 0) > (oppScore ?? 0)
          ? `W ${score}`
          : (teamScore ?? 0) < (oppScore ?? 0)
          ? `L ${score}`
          : `T ${score}`;
    }
  }

  return (
    <Link
      href={`/events/${event.id}`}
      className="bg-surface-card border border-surface-border rounded-card p-4 hover:shadow-md transition-shadow flex items-center justify-between"
    >
      <div>
        <div className="text-xs text-text-muted mb-0.5">
          {isHome ? "vs" : "@"}{" "}
          {isLive && (
            <span className="text-accent-live font-medium">LIVE</span>
          )}
        </div>
        <TeamNameLink
          name={opponent}
          sportKey={sportKey}
          className="text-sm font-medium text-text-primary hover:underline"
        />
        <div className="text-xs text-text-secondary mt-0.5">
          {isCompleted && score
            ? score
            : event.commence_time
            ? formatTime(event.commence_time)
            : "TBD"}
        </div>
      </div>
      {wp !== null && wp !== undefined && (
        <div className="text-right">
          <div className="text-lg font-mono font-bold text-text-primary">
            {Math.round(wp * 100)}%
          </div>
          <div className="text-xs text-text-muted">win prob</div>
        </div>
      )}
    </Link>
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

function formatTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffH = (d.getTime() - now.getTime()) / 3600000;

  if (diffH < 0) return "Recently";
  if (diffH < 1) return `In ${Math.round(diffH * 60)} min`;
  if (diffH < 24) {
    return d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  }
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
