"use client";

import { useMemo, useState, useCallback } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useAuthContext } from "@/components/AuthProvider";
import { fetchFeed, fetchMyTeamFutures } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData, TeamFutureItem } from "@/lib/types";
import FeedCard from "@/components/FeedCard";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import { getCategoryForLeague } from "@/lib/sportCategories";
import { usePinnedEvents, usePinnedFutures } from "@/hooks";
import { fetchEventsByIds, fetchFuturesByIds } from "@/lib/api";
import type { Event, FuturesMarketDetailResponse } from "@/lib/types";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";

export default function MyStuffPage() {
  const { isAuthenticated, isLoading: authLoading, signInWithGoogle } = useAuthContext();

  // State A: Not authenticated
  if (!authLoading && !isAuthenticated) {
    return <SignInPrompt onSignIn={signInWithGoogle} />;
  }

  // Auth is still loading — show skeleton
  if (authLoading) {
    return <SkeletonGrid count={4} />;
  }

  // State B & C: Authenticated — render the feed
  return <MyTeamsFeed />;
}

// ---------------------------------------------------------------------------
// Sign-in prompt (State A)
// ---------------------------------------------------------------------------

function SignInPrompt({ onSignIn }: { onSignIn: () => Promise<void> }) {
  return (
    <div className="max-w-lg mx-auto">
      <div className="text-center py-16 px-4">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-surface-elevated flex items-center justify-center">
          <span className="text-2xl">&#9917;</span>
        </div>
        <h2 className="text-lg font-semibold text-text-primary mb-2">
          See your teams in one place
        </h2>
        <p className="text-sm text-text-secondary mb-6 max-w-xs mx-auto">
          Sign in and follow your favorite teams to track their games and championship odds.
        </p>
        <button
          onClick={onSignIn}
          className="px-6 py-2.5 bg-text-primary text-surface-deep rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Sign in with Google
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Team-filtered feed (State B + C)
// ---------------------------------------------------------------------------

function MyTeamsFeed() {
  // Pinned items
  const { pinnedIds, togglePin, isMaxReached } = usePinnedEvents();
  const {
    pinnedIds: pinnedFuturesIds,
    togglePin: toggleFuturesPin,
    isMaxReached: isFuturesMaxReached,
  } = usePinnedFutures();

  // Fetch team-only feed (events only — team futures section handles futures)
  const {
    data: feedData,
    error: feedError,
    isLoading: feedLoading,
    mutate: refreshFeed,
  } = useSWR(
    "my-teams-feed",
    () => fetchFeed({ limit: 100, my_teams_only: true, include_futures: false }),
    { refreshInterval: 15000 },
  );

  // Fetch team futures ("Your Teams' Odds")
  const { data: teamFuturesData } = useSWR(
    "my-team-futures",
    () => fetchMyTeamFutures(30),
    { refreshInterval: 300000 }, // 5 min
  );

  // State B check (must be after all hooks)
  const teamCount = feedData?.personalization?.team_count ?? null;

  // Pinned events from feed data
  const feedEventIds = useMemo(() => {
    if (!feedData) return new Set<number>();
    return new Set(
      feedData.items
        .filter(i => i.type === "event")
        .map(i => (i.data as FeedEventData).id)
    );
  }, [feedData]);

  const missingPinnedIds = useMemo(() => {
    return pinnedIds.filter(id => !feedEventIds.has(id));
  }, [feedEventIds, pinnedIds]);

  const { data: fetchedPinnedEvents } = useSWR(
    missingPinnedIds.length > 0 ? ["my-stuff-pinned-events", ...missingPinnedIds] : null,
    () => fetchEventsByIds(missingPinnedIds),
  );

  const pinnedEvents = useMemo(() => {
    const feedEventMap = new Map<number, Event>();
    if (feedData) {
      for (const item of feedData.items) {
        if (item.type === "event") {
          const d = item.data as FeedEventData;
          feedEventMap.set(d.id, {
            id: d.id,
            external_id: d.external_id,
            sport: d.sport,
            home_team: d.home_team,
            away_team: d.away_team,
            commence_time: d.commence_time,
            status: d.status,
            home_score: d.home_score,
            away_score: d.away_score,
            current_odds: d.current_odds ? {
              home_probability: d.current_odds.home_probability,
              away_probability: d.current_odds.away_probability,
              bookmaker_count: d.current_odds.bookmaker_count,
              projected_home_score: null,
              projected_away_score: null,
            } : undefined,
            opening_odds: d.opening_odds ? {
              home_probability: d.opening_odds.home_probability,
              away_probability: d.opening_odds.away_probability ?? null,
              favorite: d.opening_odds.favorite ?? null,
            } : undefined,
          } as Event);
        }
      }
    }
    const fetchedMap = new Map((fetchedPinnedEvents ?? []).map(e => [e.id, e]));
    return pinnedIds
      .map(id => fetchedMap.get(id) ?? feedEventMap.get(id))
      .filter((e): e is Event => e !== undefined);
  }, [feedData, fetchedPinnedEvents, pinnedIds]);

  // Pinned futures
  const feedFuturesIds = useMemo(() => {
    if (!feedData) return new Set<number>();
    return new Set(
      feedData.items
        .filter(i => i.type === "futures")
        .map(i => (i.data as FeedFuturesData).id)
    );
  }, [feedData]);

  const missingPinnedFuturesIds = useMemo(() => {
    return pinnedFuturesIds.filter(id => !feedFuturesIds.has(id));
  }, [feedFuturesIds, pinnedFuturesIds]);

  const { data: fetchedPinnedFutures } = useSWR(
    missingPinnedFuturesIds.length > 0 ? ["my-stuff-pinned-futures", ...missingPinnedFuturesIds] : null,
    () => fetchFuturesByIds(missingPinnedFuturesIds),
  );

  const pinnedFutures = useMemo(() => {
    const fetchedMap = new Map((fetchedPinnedFutures ?? []).map(f => [f.id, f]));
    return pinnedFuturesIds
      .map(id => fetchedMap.get(id))
      .filter((f): f is FuturesMarketDetailResponse => f !== undefined);
  }, [fetchedPinnedFutures, pinnedFuturesIds]);

  // Group feed items into sections: Live → Upcoming → Recently Completed
  const feedSections = useMemo(() => {
    if (!feedData || feedData.items.length === 0) return [];

    const liveNow: FeedItem[] = [];
    const upcoming: FeedItem[] = [];
    const recentlyCompleted: FeedItem[] = [];

    for (const item of feedData.items) {
      if (item.type === "futures") {
        // Skip futures from feed — team futures section handles them
        continue;
      }
      const data = item.data as FeedEventData;
      if (data.status === "live") {
        liveNow.push(item);
      } else if (data.status === "completed" || data.status === "closed") {
        recentlyCompleted.push(item);
      } else {
        upcoming.push(item);
      }
    }

    const sections: { key: string; emoji: string; title: string; accent: string; items: FeedItem[] }[] = [];
    if (liveNow.length > 0)
      sections.push({ key: "live", emoji: "\uD83D\uDD34", title: "Live Now", accent: "text-accent-live", items: liveNow });
    if (upcoming.length > 0)
      sections.push({ key: "upcoming", emoji: "\uD83C\uDFDF\uFE0F", title: "Upcoming", accent: "text-text-secondary", items: upcoming });
    if (recentlyCompleted.length > 0)
      sections.push({ key: "completed", emoji: "\u2705", title: "Recently Completed", accent: "text-text-muted", items: recentlyCompleted });

    return sections;
  }, [feedData]);

  // State B: Authenticated but no teams followed
  if (feedData && teamCount === 0) {
    return <OnboardingPrompt />;
  }

  const hasEvents = feedSections.length > 0;
  const hasFutures = teamFuturesData && teamFuturesData.items.length > 0;
  const hasPinned = pinnedEvents.length > 0 || pinnedFutures.length > 0;
  const hasContent = hasEvents || hasFutures || hasPinned;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-text-primary">My Teams</h1>
          {feedData?.matched_teams && feedData.matched_teams.length > 0 && (
            <p className="text-xs text-text-muted mt-0.5">
              {feedData.matched_teams.join(" \u00B7 ")}
            </p>
          )}
        </div>
        <Link
          href="/preferences"
          className="text-xs text-accent-brand font-medium hover:opacity-80 transition-opacity"
        >
          Edit
        </Link>
      </div>

      {/* Error */}
      {feedError && (
        <ErrorMessage
          message={feedError.message}
          onRetry={() => refreshFeed()}
        />
      )}

      {/* Loading */}
      {feedLoading && !feedData && <SkeletonGrid count={4} />}

      {/* Still waiting for auth token — show skeleton instead of misleading "No games" */}
      {feedData?.requires_auth && <SkeletonGrid count={4} />}

      {/* Content */}
      {feedData && !feedData.requires_auth && (
        <>
          {!hasContent ? (
            <div className="text-center py-12">
              <p className="text-sm text-text-secondary mb-1">
                No games or markets right now for your teams
              </p>
              <p className="text-xs text-text-muted">
                Check back when your teams are playing
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Pinned Section */}
              {hasPinned && (
                <section>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-sm">&#128204;</span>
                    <h2 className="text-sm font-semibold text-text-primary">
                      Pinned
                    </h2>
                    <span className="text-micro text-text-muted">
                      {pinnedEvents.length + pinnedFutures.length}
                    </span>
                  </div>
                  <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}>
                    {pinnedEvents.map((event, index) => (
                      <EventCard
                        key={`pinned-${event.id}`}
                        event={event}
                        showSport={true}
                        sourceSection="my_stuff"
                        positionIndex={index}
                        highlightLabel={event.highlight?.label}
                        isPinned={true}
                        onPinToggle={togglePin}
                        pinDisabled={isMaxReached}
                      />
                    ))}
                    {pinnedFutures.map((market) => (
                      <FuturesCard
                        key={`pinned-futures-${market.id}`}
                        market={market}
                        showSport={true}
                        isPinned={true}
                        onPinToggle={toggleFuturesPin}
                        pinDisabled={isFuturesMaxReached}
                      />
                    ))}
                  </div>
                </section>
              )}

              {/* Event sections: Live → Upcoming → Recently Completed */}
              {feedSections.map((section) => (
                <section key={section.key}>
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-sm">{section.emoji}</span>
                    <h2 className={`text-sm font-semibold ${section.accent}`}>
                      {section.title}
                    </h2>
                    <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
                      {section.items.length}
                    </span>
                  </div>
                  <div
                    className="grid gap-3"
                    style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}
                  >
                    {section.items.map((item) => {
                      const key = item.type === "event"
                        ? `my-event-${(item.data as FeedEventData).id}`
                        : `my-futures-${(item.data as FeedFuturesData).id}`;
                      const category = item.type === "event"
                        ? getCategoryForLeague((item.data as FeedEventData).sport ?? "")?.key ?? "other"
                        : (item.data as FeedFuturesData).llm_sport_category ?? "other";
                      return (
                        <FeedCard
                          key={key}
                          item={item}
                          category={category}
                        />
                      );
                    })}
                  </div>
                </section>
              ))}

              {/* Your Teams' Odds Section */}
              {hasFutures && (
                <TeamFuturesSection
                  items={teamFuturesData!.items}
                  teamIds={teamFuturesData!.team_ids}
                  totalCount={teamFuturesData!.total_count}
                />
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Your Teams' Odds section — grouped by market type with context
// ---------------------------------------------------------------------------

const INITIAL_SHOW = 8;

function TeamFuturesSection({
  items,
  teamIds,
  totalCount,
}: {
  items: TeamFutureItem[];
  teamIds: number[];
  totalCount: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  // Group by market type for better organization
  const grouped = useMemo(() => {
    const championships: TeamFutureItem[] = [];
    const awards: TeamFutureItem[] = [];
    const other: TeamFutureItem[] = [];

    for (const item of items) {
      const name = (item.market_name || "").toLowerCase();
      const tier = item.market_tier;
      if (
        tier === 1 ||
        name.includes("champion") ||
        name.includes("winner") ||
        name.includes("world series") ||
        name.includes("super bowl") ||
        name.includes("stanley cup") ||
        name.includes("finals")
      ) {
        championships.push(item);
      } else if (
        name.includes("mvp") ||
        name.includes("award") ||
        name.includes("player") ||
        name.includes("rookie") ||
        name.includes("defensive") ||
        name.includes("coach") ||
        name.includes("cy young") ||
        name.includes("heisman")
      ) {
        awards.push(item);
      } else {
        other.push(item);
      }
    }

    return { championships, awards, other };
  }, [items]);

  // Flatten for display: championships first, then awards, then other
  const orderedItems = useMemo(() => {
    return [...grouped.championships, ...grouped.awards, ...grouped.other];
  }, [grouped]);

  const displayed = expanded ? orderedItems : orderedItems.slice(0, INITIAL_SHOW);

  const handleShare = useCallback(async () => {
    const url = `${window.location.origin}/share/my-odds?teams=${teamIds.join(",")}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this link:", url);
    }
  }, [teamIds]);

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">&#127919;</span>
          <h2 className="text-sm font-semibold text-text-primary">
            Your Teams&apos; Odds
          </h2>
          <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
            {totalCount}
          </span>
        </div>
        <button
          onClick={handleShare}
          className="text-xs text-accent-brand font-medium hover:opacity-80 transition-opacity"
        >
          {copied ? "Copied!" : "Share"}
        </button>
      </div>

      {/* Championship odds */}
      {grouped.championships.length > 0 && displayed.some(i => grouped.championships.includes(i)) && (
        <div className="mb-3">
          <p className="text-[10px] uppercase tracking-widest text-text-muted mb-1.5 px-1">
            Championships
          </p>
          <div className="space-y-0.5">
            {displayed
              .filter(i => grouped.championships.includes(i))
              .map(item => (
                <TeamFutureRow key={`${item.market_id}-${item.outcome_id}`} item={item} />
              ))}
          </div>
        </div>
      )}

      {/* Award/player odds */}
      {grouped.awards.length > 0 && displayed.some(i => grouped.awards.includes(i)) && (
        <div className="mb-3">
          <p className="text-[10px] uppercase tracking-widest text-text-muted mb-1.5 px-1">
            Awards &amp; Players
          </p>
          <div className="space-y-0.5">
            {displayed
              .filter(i => grouped.awards.includes(i))
              .map(item => (
                <TeamFutureRow key={`${item.market_id}-${item.outcome_id}`} item={item} />
              ))}
          </div>
        </div>
      )}

      {/* Other markets */}
      {grouped.other.length > 0 && displayed.some(i => grouped.other.includes(i)) && (
        <div className="mb-3">
          <p className="text-[10px] uppercase tracking-widest text-text-muted mb-1.5 px-1">
            Other Markets
          </p>
          <div className="space-y-0.5">
            {displayed
              .filter(i => grouped.other.includes(i))
              .map(item => (
                <TeamFutureRow key={`${item.market_id}-${item.outcome_id}`} item={item} />
              ))}
          </div>
        </div>
      )}

      {orderedItems.length > INITIAL_SHOW && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 text-xs text-accent-brand font-medium hover:opacity-80 transition-opacity w-full text-center py-1"
        >
          {expanded
            ? "Show less"
            : `See all ${totalCount} futures \u2192`}
        </button>
      )}
    </section>
  );
}

function TeamFutureRow({ item }: { item: TeamFutureItem }) {
  const prob = item.probability;
  const change = item.probability_change_24h;
  const probStr = prob !== null ? `${Math.round(prob * 100)}%` : "-";

  let changeEl: React.ReactNode = null;
  if (change !== null && change !== 0 && Math.abs(change) >= 0.001) {
    const isUp = change > 0;
    changeEl = (
      <span className={`text-[11px] font-medium ${isUp ? "text-accent-live" : "text-accent-danger"}`}>
        {isUp ? "\u2191" : "\u2193"} {Math.abs(change * 100).toFixed(1)}%
      </span>
    );
  }

  // Make market name more readable
  const marketName = (item.market_name || "")
    .replace(/\s*Winner\s*$/i, "")
    .replace(/\s*20\d{2}(-\d{2})?\s*$/i, "")
    .replace(/\s*20\d{2}-\d{2}\s*/i, " ")
    .trim();

  // Build rank context if available
  const rankStr = item.rank && item.total_outcomes
    ? `#${item.rank} of ${item.total_outcomes}`
    : item.rank
      ? `#${item.rank}`
      : null;

  return (
    <Link
      href={`/futures/${item.market_id}`}
      className="flex items-center gap-3 px-2.5 py-2 rounded-lg hover:bg-surface-elevated transition-colors group"
    >
      {/* Team logo */}
      <div className="w-6 h-6 flex-shrink-0">
        {item.matched_team.logo_small ? (
          <img
            src={item.matched_team.logo_small}
            alt={item.matched_team.name}
            className="w-6 h-6 object-contain"
          />
        ) : (
          <div
            className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white"
            style={{ backgroundColor: item.matched_team.primary_color || "#666" }}
          >
            {(item.matched_team.name || "?")[0]}
          </div>
        )}
      </div>

      {/* Market info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text-primary truncate">
          <span className="font-medium">{item.outcome_name}</span>
          <span className="text-text-muted"> &mdash; </span>
          <span className="text-text-secondary">{marketName}</span>
        </p>
        {rankStr && (
          <p className="text-[11px] text-text-muted">
            Ranked {rankStr}
          </p>
        )}
      </div>

      {/* Probability + movement */}
      <div className="text-right flex-shrink-0 flex items-center gap-1.5">
        {changeEl}
        <p className="text-sm font-semibold text-text-primary font-mono tabular-nums min-w-[2.5rem] text-right">
          {probStr}
        </p>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Onboarding prompt (State B)
// ---------------------------------------------------------------------------

function OnboardingPrompt() {
  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-xl font-bold text-text-primary mb-6">My Teams</h1>
      <div className="text-center py-12 px-4">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-surface-elevated flex items-center justify-center">
          <span className="text-2xl">&#127942;</span>
        </div>
        <h2 className="text-lg font-semibold text-text-primary mb-2">
          Follow some teams to get started
        </h2>
        <p className="text-sm text-text-secondary mb-6 max-w-xs mx-auto">
          Tell us your favorite teams and we&apos;ll show their games and championship odds here.
        </p>
        <Link
          href="/onboarding"
          className="inline-block px-6 py-2.5 bg-text-primary text-surface-deep rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Set up your teams
        </Link>
      </div>
    </div>
  );
}
