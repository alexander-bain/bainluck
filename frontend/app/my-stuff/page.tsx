"use client";

import { useMemo, useState, useCallback, useEffect } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useAuthContext } from "@/components/AuthProvider";
import { preloadFirebaseAuth } from "@/lib/firebase";
import { fetchFeed, fetchMyTeamFutures } from "@/lib/api";
import type { FeedItem, FeedEventData, FeedFuturesData, TeamFutureItem } from "@/lib/types";
import FeedCard from "@/components/FeedCard";
import { SkeletonGrid } from "@/components/SkeletonCard";
import ErrorMessage from "@/components/ErrorMessage";
import { getCategoryForLeague } from "@/lib/sportCategories";
import { usePinnedEvents, usePinnedFutures, usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchEventsByIds, fetchFuturesByIds } from "@/lib/api";
import type { Event, FuturesMarketDetailResponse } from "@/lib/types";
import EventCard from "@/components/EventCard";
import FuturesCard from "@/components/FuturesCard";
import ProgressionLadder from "@/components/ProgressionLadder";
import { useRouter } from "next/navigation";

export default function MyStuffPage() {
  // Analytics hooks must be called before conditional returns
  usePageTracking({ pageType: 'my_stuff', pageTitle: 'My Teams' });
  useScrollDepth({ pageType: 'my_stuff' });
  useEngagementTime({ pageType: 'my_stuff' });

  const { isAuthenticated, isLoading: authLoading, signInWithGoogle, signInWithApple } = useAuthContext();

  // State A: Not authenticated
  if (!authLoading && !isAuthenticated) {
    return <SignInPrompt onSignInGoogle={signInWithGoogle} onSignInApple={signInWithApple} />;
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

function SignInPrompt({ onSignInGoogle, onSignInApple }: { onSignInGoogle: () => Promise<void>; onSignInApple: () => Promise<void> }) {
  // Pre-load Firebase Auth module so Apple popup opens instantly on click
  useEffect(() => { preloadFirebaseAuth(); }, []);

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
        <div className="flex flex-col gap-3 items-center">
          <button
            onClick={onSignInGoogle}
            className="w-64 px-6 py-2.5 bg-text-primary text-surface-deep rounded-lg text-sm font-medium hover:opacity-90 transition-opacity flex items-center justify-center gap-3"
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5 flex-shrink-0" aria-hidden="true">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
            </svg>
            Continue with Google
          </button>
          <button
            onClick={onSignInApple}
            className="w-64 px-6 py-2.5 bg-text-primary text-surface-deep rounded-lg text-sm font-medium hover:opacity-90 transition-opacity flex items-center justify-center gap-3"
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5 flex-shrink-0 fill-current" aria-hidden="true">
              <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
            </svg>
            Continue with Apple
          </button>
        </div>
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
    () => fetchMyTeamFutures(100),
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

    // Sort upcoming by commence_time ascending — soonest games first.
    // The backend sorts by interestingness score which is great for discovery
    // feeds, but in My Stuff the user wants time-proximity ordering.
    upcoming.sort((a, b) => {
      const da = (a.data as FeedEventData).commence_time;
      const db_ = (b.data as FeedEventData).commence_time;
      return new Date(da).getTime() - new Date(db_).getTime();
    });

    // Sort recently completed by commence_time descending — most recent first
    recentlyCompleted.sort((a, b) => {
      const da = (a.data as FeedEventData).commence_time;
      const db_ = (b.data as FeedEventData).commence_time;
      return new Date(db_).getTime() - new Date(da).getTime();
    });

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
// Your Teams' Odds section — grouped by market type with cross-source merging
// and playoff journey detection
// ---------------------------------------------------------------------------

const INITIAL_SHOW = 10;

// Source display helpers (same palette as CombinedFeedCard)
const SOURCE_LABELS: Record<string, string> = {
  odds_api: "Sportsbooks",
  kalshi: "Kalshi",
  polymarket: "Polymarket",
};
const SOURCE_COLORS: Record<string, { dot: string; text: string }> = {
  polymarket: { dot: "bg-blue-500", text: "text-blue-400" },
  kalshi: { dot: "bg-green-500", text: "text-green-400" },
  odds_api: { dot: "bg-slate-400", text: "text-slate-300" },
};

/** Merged view of the same outcome across multiple sources. */
interface MergedTeamFuture {
  /** Primary item used for display metadata (team logo, market name, rank). */
  primary: TeamFutureItem;
  /** Per-source probability data. */
  sources: {
    source: string;
    probability: number | null;
    change: number | null;
    market_id: number;
  }[];
  /** Average probability across sources. */
  avgProbability: number | null;
  /** Best movement (largest absolute change). */
  bestChange: number | null;
  /** Extracted market_type from canonical_market_key (e.g., "championship", "make_playoffs"). */
  marketType: string | null;
}

// Playoff progression stages — order determines funnel display.
// Labels match ProgressionLadder demo style (short, no "Make"/"Win" prefix).
const PROGRESSION_STAGES: Record<string, { order: number; label: string }> = {
  make_playoffs: { order: 1, label: "Playoffs" },
  division_winner: { order: 2, label: "Division" },
  conference_winner: { order: 3, label: "Conf Finals" },
  championship: { order: 4, label: "Champion" },
};

/** Extract market_type from canonical_market_key (format: sport:league:type:season). */
function extractMarketType(key: string | null | undefined): string | null {
  if (!key) return null;
  const parts = key.split(":");
  return parts.length >= 3 ? parts[2] : null;
}

/**
 * Detect market type from market name when canonical_market_key is missing.
 * Mirrors backend _MARKET_TYPE_PATTERNS in futures_categorization.py.
 */
function detectMarketTypeFromName(name: string): string | null {
  const n = name.toLowerCase();
  if (/make.*playoffs|playoffs.*qualification|will make.*playoffs/i.test(n)) return "make_playoffs";
  if (/division\s*(winner|champion|title)/i.test(n)) return "division_winner";
  if (/conference\s*(winner|champion|title|finals)/i.test(n) && !/seed|#\d/i.test(n)) return "conference_winner";
  if (/champion(ship)?\s*(winner|20\d{2})|win.*championship|nba\s+champion|nfl\s+champion|mlb\s+champion|nhl\s+champion|world\s+series|super\s+bowl|stanley\s+cup/i.test(n)) return "championship";
  return null;
}

/** Convert hex color (e.g. "1D428A" or "#1D428A") to RGB string (e.g. "29, 66, 138"). */
function hexToRgb(hex: string): string {
  const h = hex.replace(/^#/, "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
}

/** A team's playoff journey — multiple stages from "Make Playoffs" to "Championship". */
interface PlayoffJourney {
  teamId: number;
  teamName: string;
  teamLogo: string | null;
  teamColor: string | null;
  /** Stages sorted by progression order (make_playoffs → championship). */
  stages: {
    merged: MergedTeamFuture;
    stageOrder: number;
    stageLabel: string;
  }[];
}

/**
 * Merge TeamFutureItems that share the same canonical_market_key + outcome_name
 * into single entries with multi-source probabilities.
 */
function mergeTeamFutures(items: TeamFutureItem[]): MergedTeamFuture[] {
  const byKey = new Map<string, MergedTeamFuture>();

  for (const item of items) {
    const detectedType = extractMarketType(item.canonical_market_key)
      ?? detectMarketTypeFromName(item.market_name || "");

    // Build grouping key:
    // 1. If canonical_market_key exists, use it + outcome (cross-source merge)
    // 2. If we detected a progression type, use type + category + outcome
    //    so "NBA Championship Winner" from 3 sources merges for the same team
    // 3. Fallback: unique per market (no merge)
    let canonKey: string;
    if (item.canonical_market_key) {
      canonKey = item.canonical_market_key;
    } else if (detectedType) {
      canonKey = `synth:${item.category || "unknown"}:${detectedType}`;
    } else {
      canonKey = `market_${item.market_id}`;
    }
    // For progression stages, merge by team_id so "Boston Celtics", "Celtics",
    // and "BOS" all group together for the same team across sources.
    // For non-progression items, merge by outcome name as before.
    const isProgression = detectedType != null && PROGRESSION_STAGES[detectedType] != null;
    const groupSuffix = isProgression
      ? `team_${item.matched_team.id}`
      : (item.outcome_name || "").toLowerCase().trim();
    const groupKey = `${canonKey}::${groupSuffix}`;

    if (!byKey.has(groupKey)) {
      byKey.set(groupKey, {
        primary: item,
        sources: [],
        avgProbability: null,
        bestChange: null,
        marketType: detectedType,
      });
    }

    const entry = byKey.get(groupKey)!;
    entry.sources.push({
      source: item.source || "unknown",
      probability: item.probability,
      change: item.probability_change_24h,
      market_id: item.market_id,
    });

    // Use the item with the highest rank (best rank = lowest number) as primary
    if (
      item.rank !== null &&
      (entry.primary.rank === null || item.rank < entry.primary.rank)
    ) {
      entry.primary = item;
    }
  }

  // Compute averages
  for (const entry of Array.from(byKey.values())) {
    const probs = entry.sources
      .map((s: MergedTeamFuture["sources"][0]) => s.probability)
      .filter((p: number | null): p is number => p !== null && p > 0);
    entry.avgProbability =
      probs.length > 0 ? probs.reduce((a: number, b: number) => a + b, 0) / probs.length : null;

    // Best movement: largest absolute change
    let best: number | null = null;
    for (const s of entry.sources) {
      if (s.change !== null && (best === null || Math.abs(s.change) > Math.abs(best))) {
        best = s.change;
      }
    }
    entry.bestChange = best;
  }

  return Array.from(byKey.values());
}

/**
 * Detect playoff journeys: teams with 2+ progression stages.
 * Returns journeys and remaining items that aren't part of any journey.
 */
function detectPlayoffJourneys(merged: MergedTeamFuture[]): {
  journeys: PlayoffJourney[];
  remaining: MergedTeamFuture[];
} {
  // Group by team across progression stages
  const teamStages = new Map<number, { team: TeamFutureItem["matched_team"]; stages: { merged: MergedTeamFuture; stageOrder: number; stageLabel: string }[] }>();
  const remaining: MergedTeamFuture[] = [];

  for (const m of merged) {
    const mType = m.marketType;
    const stage = mType ? PROGRESSION_STAGES[mType] : null;

    if (!stage) {
      remaining.push(m);
      continue;
    }

    const teamId = m.primary.matched_team.id;
    if (!teamStages.has(teamId)) {
      teamStages.set(teamId, {
        team: m.primary.matched_team,
        stages: [],
      });
    }

    teamStages.get(teamId)!.stages.push({
      merged: m,
      stageOrder: stage.order,
      stageLabel: stage.label,
    });
  }

  // Build journeys for teams with 2+ stages; singles go to remaining
  const journeys: PlayoffJourney[] = [];
  for (const [teamId, data] of Array.from(teamStages.entries())) {
    if (data.stages.length >= 2) {
      // Sort by progression order (make_playoffs first → championship last)
      data.stages.sort((a, b) => a.stageOrder - b.stageOrder);
      journeys.push({
        teamId,
        teamName: data.team.name,
        teamLogo: data.team.logo_small,
        teamColor: data.team.primary_color,
        stages: data.stages,
      });
    } else {
      // Single stage — treat as regular item
      remaining.push(data.stages[0].merged);
    }
  }

  // Sort journeys by championship probability (descending)
  journeys.sort((a, b) => {
    const champA = a.stages.find((s) => s.stageOrder === 4)?.merged.avgProbability ?? 0;
    const champB = b.stages.find((s) => s.stageOrder === 4)?.merged.avgProbability ?? 0;
    return champB - champA;
  });

  return { journeys, remaining };
}

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
  const router = useRouter();

  // Merge cross-source duplicates, detect journeys, then group remainder
  const { journeys, awards, other, uniqueCount } = useMemo(() => {
    const merged = mergeTeamFutures(items);
    const { journeys: detectedJourneys, remaining } = detectPlayoffJourneys(merged);

    const awardItems: MergedTeamFuture[] = [];
    const otherItems: MergedTeamFuture[] = [];

    for (const m of remaining) {
      const name = (m.primary.market_name || "").toLowerCase();
      if (
        name.includes("mvp") ||
        name.includes("award") ||
        name.includes("player") ||
        name.includes("rookie") ||
        name.includes("defensive") ||
        name.includes("coach") ||
        name.includes("cy young") ||
        name.includes("heisman") ||
        name.includes("improved") ||
        name.includes("sixth man") ||
        name.includes("clutch")
      ) {
        awardItems.push(m);
      } else {
        otherItems.push(m);
      }
    }

    const sortByProb = (a: MergedTeamFuture, b: MergedTeamFuture) =>
      (b.avgProbability ?? 0) - (a.avgProbability ?? 0);
    awardItems.sort(sortByProb);
    otherItems.sort(sortByProb);

    // Count unique entries: each journey counts as 1 + individual items
    const count = detectedJourneys.length + awardItems.length + otherItems.length;

    return {
      journeys: detectedJourneys,
      awards: awardItems,
      other: otherItems,
      uniqueCount: count,
    };
  }, [items]);

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

  // Apply show-more limit to flat items (journeys always show)
  const allFlatItems = [...awards, ...other];
  const displayedFlat = expanded
    ? allFlatItems
    : allFlatItems.slice(0, Math.max(0, INITIAL_SHOW - journeys.length));
  const displayedAwards = displayedFlat.filter((m) => awards.includes(m));
  const displayedOther = displayedFlat.filter((m) => other.includes(m));
  const totalItems = journeys.length + allFlatItems.length;

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">&#127919;</span>
          <h2 className="text-sm font-semibold text-text-primary">
            Your Teams&apos; Odds
          </h2>
          <span className="text-[11px] text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded-full font-medium">
            {uniqueCount}
          </span>
        </div>
        <button
          onClick={handleShare}
          className="text-xs text-accent-brand font-medium hover:opacity-80 transition-opacity"
        >
          {copied ? "Copied!" : "Share"}
        </button>
      </div>

      {/* Playoff Journey cards — using ProgressionLadder from demo */}
      {journeys.length > 0 && (
        <div className="grid gap-3 mb-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 320px), 1fr))" }}>
          {journeys.map((journey) => (
            <ProgressionLadder
              key={journey.teamId}
              entityName={journey.teamName}
              stages={journey.stages.map((s) => ({
                id: s.merged.primary.market_id,
                name: s.merged.primary.market_name || "",
                stage_name: s.stageLabel,
                stage_order: s.stageOrder,
                probability: s.merged.avgProbability,
                status:
                  s.merged.avgProbability !== null && s.merged.avgProbability >= 0.99
                    ? ("achieved" as const)
                    : undefined,
              }))}
              logoUrl={journey.teamLogo || undefined}
              teamColors={
                journey.teamColor
                  ? { primary: hexToRgb(journey.teamColor), secondary: "128, 128, 128" }
                  : undefined
              }
              onStageClick={(stage) => router.push(`/futures/${stage.id}`)}
            />
          ))}
        </div>
      )}

      {/* Remaining items (awards + other) */}
      {(displayedAwards.length > 0 || displayedOther.length > 0) && (
        <div className="bg-surface-card border border-surface-border rounded-card overflow-hidden">
          {displayedAwards.length > 0 && (
            <MergedFuturesGroup label="Awards & Players" items={displayedAwards} />
          )}
          {displayedOther.length > 0 && (
            <MergedFuturesGroup
              label="Other Markets"
              items={displayedOther}
              borderTop={displayedAwards.length > 0}
            />
          )}
        </div>
      )}

      {totalItems > INITIAL_SHOW && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 text-xs text-accent-brand font-medium hover:opacity-80 transition-opacity w-full text-center py-1.5"
        >
          {expanded
            ? "Show less"
            : `See all ${uniqueCount} markets \u2192`}
        </button>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Flat items (awards, other) — individual rows with cross-source merging
// ---------------------------------------------------------------------------

function MergedFuturesGroup({
  label,
  items,
  borderTop = false,
}: {
  label: string;
  items: MergedTeamFuture[];
  borderTop?: boolean;
}) {
  return (
    <div className={borderTop ? "border-t border-surface-border" : ""}>
      <p className="text-[10px] uppercase tracking-widest text-text-muted px-3 pt-2.5 pb-1">
        {label}
      </p>
      <div className="divide-y divide-surface-border/40">
        {items.map((m) => (
          <MergedTeamFutureRow
            key={`${m.primary.market_id}-${m.primary.outcome_id}`}
            merged={m}
          />
        ))}
      </div>
    </div>
  );
}

function MergedTeamFutureRow({ merged }: { merged: MergedTeamFuture }) {
  const { primary, sources, avgProbability, bestChange } = merged;
  const isMultiSource = sources.length > 1;

  // Display average probability for multi-source, single probability otherwise
  const displayProb = isMultiSource ? avgProbability : primary.probability;
  const probPct = displayProb !== null ? Math.round(displayProb * 100) : null;
  const probStr = probPct !== null ? `${probPct}%` : "-";

  // Movement indicator
  let changeEl: React.ReactNode = null;
  const change = bestChange;
  if (change !== null && change !== 0 && Math.abs(change) >= 0.001) {
    const isUp = change > 0;
    changeEl = (
      <span className={`text-[11px] font-medium ${isUp ? "text-accent-live" : "text-accent-danger"}`}>
        {isUp ? "\u2191" : "\u2193"}{Math.abs(change * 100).toFixed(1)}%
      </span>
    );
  }

  // Make market name more readable
  const marketName = (primary.market_name || "")
    .replace(/\s*Winner\s*$/i, "")
    .replace(/\s*20\d{2}(-\d{2})?\s*$/i, "")
    .replace(/\s*20\d{2}-\d{2}\s*/i, " ")
    .trim();

  // Build rank context
  const rankStr = primary.rank && primary.total_outcomes
    ? `#${primary.rank} of ${primary.total_outcomes}`
    : primary.rank
      ? `#${primary.rank}`
      : null;

  // Link to primary market's detail page
  const linkMarketId = primary.market_id;

  return (
    <Link
      href={`/futures/${linkMarketId}`}
      className="flex items-center gap-3 px-3 py-2.5 hover:bg-surface-elevated/50 transition-colors group"
    >
      {/* Team logo */}
      <div className="w-7 h-7 flex-shrink-0">
        {primary.matched_team.logo_small ? (
          <img
            src={primary.matched_team.logo_small}
            alt={primary.matched_team.name}
            className="w-7 h-7 object-contain"
          />
        ) : (
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold text-white"
            style={{ backgroundColor: primary.matched_team.primary_color || "#666" }}
          >
            {(primary.matched_team.name || "?")[0]}
          </div>
        )}
      </div>

      {/* Market info */}
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text-primary truncate leading-tight">
          <span className="font-medium">{primary.outcome_name}</span>
        </p>
        <div className="flex items-center gap-1.5 mt-0.5">
          <p className="text-[11px] text-text-muted truncate">
            {marketName}
            {rankStr && <span className="text-text-muted/70"> &middot; {rankStr}</span>}
          </p>
          {/* Source dots */}
          {isMultiSource && (
            <div className="flex items-center gap-1 flex-shrink-0">
              {sources.map((s) => {
                const colors = SOURCE_COLORS[s.source] || { dot: "bg-gray-500", text: "text-gray-400" };
                return (
                  <div
                    key={s.source}
                    className={`w-1.5 h-1.5 rounded-full ${colors.dot}`}
                    title={SOURCE_LABELS[s.source] || s.source}
                  />
                );
              })}
            </div>
          )}
        </div>
        {/* Probability bar */}
        {probPct !== null && (
          <div className="h-1 rounded-full bg-surface-border mt-1.5 overflow-hidden max-w-[140px]">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.min(probPct, 100)}%`,
                backgroundColor: primary.matched_team.primary_color || "var(--accent-futures)",
                opacity: 0.7,
              }}
            />
          </div>
        )}
      </div>

      {/* Probability + source breakdown */}
      <div className="flex flex-col items-end flex-shrink-0 gap-0.5">
        {isMultiSource ? (
          <>
            {/* Per-source probabilities */}
            <div className="flex items-center gap-1.5">
              {sources.map((s) => {
                const colors = SOURCE_COLORS[s.source] || { dot: "bg-gray-500", text: "text-gray-400" };
                const p = s.probability !== null ? Math.round(s.probability * 100) : null;
                return (
                  <span
                    key={s.source}
                    className={`text-[11px] font-mono font-semibold tabular-nums ${colors.text}`}
                    title={SOURCE_LABELS[s.source] || s.source}
                  >
                    {p !== null ? `${p}%` : "—"}
                  </span>
                );
              })}
            </div>
            {changeEl}
          </>
        ) : (
          <>
            <p className="text-sm font-bold text-text-primary font-mono tabular-nums">
              {probStr}
            </p>
            {changeEl}
          </>
        )}
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
