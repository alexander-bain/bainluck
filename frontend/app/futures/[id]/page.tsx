"use client";

import { useState, useMemo, useEffect, useRef } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import {
  fetchFuturesMarket,
  fetchFuturesHistory,
  fetchRelatedEvents,
  fetchProgression,
  fetchFuturesGroup,
  formatProbability,
  formatAmericanOdds,
} from "@/lib/api";
import type { FuturesOutcome, RelatedEvent } from "@/lib/types";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import { usePinnedFutures } from "@/hooks";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAnalyticsContext } from "@/components/Analytics";
import { FuturesChart } from "@/components/FuturesChart";
import { EvolutionView } from "@/components/EvolutionView";
import TournamentChart from "@/components/TournamentChart";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import CombinedMarketCard from "@/components/CombinedMarketCard";
import ThresholdGrid from "@/components/ThresholdGrid";
import ProgressionTable from "@/components/ProgressionTable";
import EntityImage from "@/components/EntityImage";
import RelatedByTag from "@/components/RelatedByTag";
import { isNonSportsCategory, isInternationalSport, flagUrl } from "@/lib/images";

interface FuturesDetailPageProps {
  params: { id: string };
}

/**
 * Format bookmaker key to display name
 */
function formatBookmakerName(key: string): string {
  const names: Record<string, string> = {
    draftkings: "DraftKings",
    fanduel: "FanDuel",
    betmgm: "BetMGM",
    caesars: "Caesars",
    pointsbet: "PointsBet",
    betrivers: "BetRivers",
    unibet: "Unibet",
    williamhill_us: "Caesars",
    bovada: "Bovada",
    betonlineag: "BetOnline",
    mybookieag: "MyBookie",
    pinnacle: "Pinnacle",
    superbook: "SuperBook",
    espnbet: "ESPN BET",
    fliff: "Fliff",
    hardrockbet: "Hard Rock",
    betus: "BetUS",
  };
  return names[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Get emoji for sport category
 */
function getSportEmoji(sportKey: string | null): string {
  if (!sportKey) return "🏆";
  const key = sportKey.toLowerCase();
  if (key.includes("basketball") || key.includes("nba") || key.includes("ncaab")) return "🏀";
  if (key.includes("football") || key.includes("nfl") || key.includes("ncaaf")) return "🏈";
  if (key.includes("baseball") || key.includes("mlb")) return "⚾";
  if (key.includes("hockey") || key.includes("nhl")) return "🏒";
  if (key.includes("soccer") || key.includes("mls") || key.includes("epl") || key.includes("uefa")) return "⚽";
  if (key.includes("golf") || key.includes("pga")) return "⛳";
  if (key.includes("tennis") || key.includes("atp") || key.includes("wta")) return "🎾";
  if (key.includes("mma") || key.includes("ufc")) return "🥊";
  if (key.includes("nascar") || key.includes("f1") || key.includes("racing")) return "🏎️";
  return "🏆";
}

type SortField = "probability" | "change" | "name";
type SortDirection = "asc" | "desc";

export default function FuturesDetailPage({ params }: FuturesDetailPageProps) {
  const marketId = parseInt(params.id, 10);
  const isValidId = !isNaN(marketId) && marketId > 0;
  const searchParams = useSearchParams();
  const sharedSource = searchParams.get("utm_source");
  const sharedMedium = searchParams.get("utm_medium") || undefined;
  const sharedCampaign = searchParams.get("utm_campaign") || undefined;
  const isSharedLink = sharedSource === "share";

  // Analytics hooks must be called before conditional returns
  usePageTracking({
    pageType: 'futures_detail',
    pageTitle: 'Futures Market',
    additionalParams: { event_id: marketId },
    deps: [marketId],
  });
  useScrollDepth({ pageType: 'futures_detail' });
  useEngagementTime({ pageType: 'futures_detail' });
  const { track } = useAnalyticsContext();

  const [sortField, setSortField] = useState<SortField>("probability");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [selectedOutcomes, setSelectedOutcomes] = useState<Set<number>>(new Set());
  const [showAllOutcomes, setShowAllOutcomes] = useState(false);
  const [trendView, setTrendView] = useState<"evolution" | "progression">("evolution");

  // Pinned futures
  const { isPinned, togglePin, isMaxReached } = usePinnedFutures();
  const marketIsPinned = isPinned(marketId);

  const {
    data: market,
    error: marketError,
    isLoading: marketLoading,
    mutate: refreshMarket,
  } = useSWR(
    isValidId ? ["futures-market", marketId] : null,
    () => fetchFuturesMarket(marketId),
    { refreshInterval: 60000, keepPreviousData: true, revalidateOnFocus: false }
  );

  // Request more history for markets that haven't been updated recently,
  // so the chart isn't empty when the last poll was days ago.
  const historyHours = useMemo(() => {
    if (!market?.updated_at) return 168; // 7 days default
    const hoursSinceUpdate = (Date.now() - new Date(market.updated_at).getTime()) / (1000 * 60 * 60);
    // If last update was >3 days ago, expand the window to cover it
    if (hoursSinceUpdate > 72) {
      return Math.min(Math.ceil(hoursSinceUpdate + 48), 720); // up to 30 days
    }
    return 168; // 7 days
  }, [market?.updated_at]);

  const {
    data: historyData,
    error: historyError,
    isLoading: historyLoading,
  } = useSWR(
    market ? ["futures-history", marketId, historyHours] : null,
    () => fetchFuturesHistory(marketId, historyHours)
  );

  // Track futures detail view once data loads
  const hasTrackedFutures = useRef(false);
  const hasTrackedSharedOpen = useRef(false);
  useEffect(() => {
    if (market && !hasTrackedFutures.current) {
      hasTrackedFutures.current = true;
      track('futures_detail_view', {
        market_id: marketId,
        category: market.display_category || market.category || 'unknown',
        source_count: market.source_count ?? 1,
      });
    }
  }, [market, marketId, track]);

  useEffect(() => {
    if (market && isSharedLink && !hasTrackedSharedOpen.current) {
      hasTrackedSharedOpen.current = true;
      track("shared_link_open", {
        content_type: "futures",
        item_id: marketId,
        source: sharedSource,
        medium: sharedMedium,
        campaign: sharedCampaign,
      });
    }
  }, [isSharedLink, market, marketId, sharedCampaign, sharedMedium, sharedSource, track]);

  // Related events (upcoming/recent games featuring contender teams)
  const { data: relatedEventsData } = useSWR(
    market ? ["futures-related-events", marketId] : null,
    () => fetchRelatedEvents(marketId),
    { revalidateOnFocus: false }
  );

  // Tournament progression (cross-stage table)
  const { data: progressionData } = useSWR(
    market ? ["futures-progression", marketId] : null,
    () => fetchProgression(marketId, 40),
    { revalidateOnFocus: false, refreshInterval: 120_000 }
  );
  const hasProgression = !!(progressionData && progressionData.stages.length >= 2);

  // Market group (cross-source comparison + threshold variants)
  const { data: groupData } = useSWR(
    market?.group_id ? ["futures-group", market.group_id] : null,
    () => fetchFuturesGroup(market!.group_id!),
    { revalidateOnFocus: false }
  );
  const hasMultipleSources = !!(groupData && groupData.sources.length >= 2);
  const thresholdEntries = groupData
    ? Object.entries(groupData.threshold_groups).filter(([, outcomes]) => outcomes.length >= 2)
    : [];
  // Progression-ordered markets (e.g., playoff rounds)
  const progressionMarkets = groupData
    ? groupData.markets
        .filter((m) => m.group_position !== null && m.group_position !== undefined)
        .sort((a, b) => (a.group_position ?? 0) - (b.group_position ?? 0))
    : [];
  const hasGroupProgression = progressionMarkets.length >= 2;

  // Sort outcomes
  const sortedOutcomes = useMemo(() => {
    if (!market?.outcomes) return [];

    const sorted = [...market.outcomes].sort((a, b) => {
      let comparison = 0;

      switch (sortField) {
        case "probability":
          comparison = (b.probability ?? 0) - (a.probability ?? 0);
          break;
        case "change":
          // Sort by actual change value, not absolute value
          // Descending shows biggest gainers first, ascending shows biggest losers first
          const aChange = a.probability_change_24h ?? 0;
          const bChange = b.probability_change_24h ?? 0;
          comparison = bChange - aChange;
          break;
        case "name":
          comparison = a.name.localeCompare(b.name);
          break;
      }

      return sortDirection === "asc" ? comparison : -comparison;
    });

    return sorted;
  }, [market?.outcomes, sortField, sortDirection]);

  // The leader is always the outcome with highest probability (independent of sort)
  const leader = useMemo(() => {
    if (!market?.outcomes || market.outcomes.length === 0) return null;
    return [...market.outcomes].sort(
      (a, b) => (b.probability ?? 0) - (a.probability ?? 0)
    )[0];
  }, [market?.outcomes]);

  // Limit displayed outcomes unless "show all" is enabled
  const displayedOutcomes = showAllOutcomes
    ? sortedOutcomes
    : sortedOutcomes.slice(0, 25);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection(field === "name" ? "asc" : "desc");
    }
  };

  const toggleOutcomeSelection = (outcomeId: number) => {
    setSelectedOutcomes((prev) => {
      const next = new Set(prev);
      if (next.has(outcomeId)) {
        next.delete(outcomeId);
      } else {
        next.add(outcomeId);
      }
      return next;
    });
  };

  const backLink = (
    <div className="flex items-center gap-2">
      <Link
        href="/futures"
        className="inline-flex items-center text-caption text-text-secondary hover:text-text-primary transition-colors"
      >
        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to Futures
      </Link>
    </div>
  );

  if (marketLoading) {
    return (
      <div className="space-y-6">
        {backLink}
        <div className="py-12">
          <LoadingSpinner text="Loading market..." />
        </div>
      </div>
    );
  }

  if (marketError || !market) {
    return (
      <div className="space-y-6">
        {backLink}
        <ErrorMessage
          title="Market not found"
          message={
            !isValidId
              ? "This market ID is invalid. It may have been removed or the link is incorrect."
              : marketError?.message || "Unable to load this market. It may have been removed or is temporarily unavailable."
          }
          onRetry={isValidId ? () => refreshMarket() : undefined}
        />
      </div>
    );
  }

  const sportEmoji = getSportEmoji(market.sport);
  const isResolved = market.status === "resolved";

  return (
    <div className="space-y-6">
      {/* Navigation */}
      {backLink}

      {isSharedLink && (
        <div className="rounded-card border border-accent-brand/20 bg-accent-brand/5 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-text-primary">Shared from Discover</p>
            <p className="text-xs text-text-secondary">Explore the rest of today&apos;s probability stories.</p>
          </div>
          <Link
            href="/discover"
            className="inline-flex items-center justify-center rounded-lg bg-accent-brand px-3 py-2 text-sm font-semibold text-white hover:opacity-90 transition-opacity"
          >
            Open Discover
          </Link>
        </div>
      )}

      {/* Expired market banner */}
      {(isResolved || (market.resolution_date && new Date(market.resolution_date) < new Date())) && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3 text-sm text-amber-400">
          {isResolved
            ? `This market has been settled.${market.resolution_date ? ` Resolved ${new Date(market.resolution_date).toLocaleDateString()}.` : ""}`
            : `This market resolved on ${new Date(market.resolution_date!).toLocaleDateString()}. Showing final probabilities.`}
        </div>
      )}

      {/* Hero Section */}
      <div
        className={`rounded-card shadow-card p-6 ${
          isResolved
            ? "bg-slate-50 border border-slate-200"
            : "bg-surface-card"
        }`}
      >
        {/* Sport badge */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {/* Pin button */}
            <button
              onClick={() => togglePin(marketId)}
              disabled={isMaxReached && !marketIsPinned}
              className={`
                p-1.5 rounded-full transition-all
                ${marketIsPinned
                  ? 'text-amber-500 bg-amber-50 hover:bg-amber-100'
                  : 'text-text-secondary/40 hover:text-text-secondary hover:bg-slate/10'
                }
                ${isMaxReached && !marketIsPinned ? 'cursor-not-allowed opacity-30' : ''}
                focus:outline-none focus:ring-2 focus:ring-amber-300
              `}
              title={marketIsPinned ? 'Unpin market' : isMaxReached ? 'Maximum 6 pins' : 'Pin market'}
              aria-label={marketIsPinned ? 'Unpin market' : 'Pin market'}
            >
              <PinIcon filled={marketIsPinned} className="w-5 h-5" />
            </button>

            {market.sport && (() => {
              const categoryKey = market.llm_sport_category || undefined;
              const badge = (
                <span className="text-sm bg-slate/10 px-3 py-1 rounded-full flex items-center gap-2">
                  <span className="text-lg">{sportEmoji}</span>
                  <span className="text-text-secondary font-medium">
                    {market.sport_name || market.sport}
                  </span>
                </span>
              );
              return categoryKey ? (
                <Link href={`/categories/${categoryKey}`} className="hover:opacity-80 transition-opacity">
                  {badge}
                </Link>
              ) : badge;
            })()}
          </div>

          {/* Status badge */}
          {isResolved && (
            <span className="flex items-center gap-1 bg-slate/20 text-text-secondary px-3 py-1 rounded-full text-sm font-medium">
              Resolved
            </span>
          )}
        </div>

        {/* Market name */}
        <h1 className="text-title-1 text-text-primary mb-2">{market.name}</h1>

        {market.description && (
          <p className="text-body text-text-secondary mb-4">{market.description}</p>
        )}

        {/* Market info strip */}
        <div className="flex flex-wrap gap-4 text-sm text-text-secondary">
          <span>
            {market.outcome_count} outcome{market.outcome_count !== 1 ? "s" : ""}
          </span>
          {market.commence_time && (
            <span>
              Starts:{" "}
              {new Date(market.commence_time).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          )}
          {market.resolution_date && (
            <span>
              Resolves:{" "}
              {new Date(market.resolution_date).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          )}
          {market.updated_at && (
            <span>
              Updated:{" "}
              {new Date(market.updated_at).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}{" "}
              at{" "}
              {new Date(market.updated_at).toLocaleTimeString("en-US", {
                hour: "numeric",
                minute: "2-digit",
              })}
            </span>
          )}
        </div>

        {/* Sportsbooks */}
        {market.bookmakers && market.bookmakers.length > 0 && (
          <div className="mt-4 pt-4 border-t border-surface-border">
            <div className="text-sm text-text-secondary mb-2">
              Odds from {market.bookmakers.length} sportsbook{market.bookmakers.length !== 1 ? "s" : ""}
            </div>
            <div className="flex flex-wrap gap-2">
              {market.bookmakers.map((bookmaker) => (
                <span
                  key={bookmaker}
                  className="text-xs bg-slate/10 px-2 py-1 rounded-full text-text-secondary capitalize"
                >
                  {formatBookmakerName(bookmaker)}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Current Leader */}
        {leader && (
          <div className="mt-6 pt-4 border-t border-surface-border">
            <div className="text-sm text-text-secondary mb-2">Current Favorite</div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="w-8 h-8 flex items-center justify-center text-lg bg-amber-100 text-amber-700 rounded-full font-bold">
                  1
                </span>
                <span className="text-xl font-semibold text-text-primary">
                  {leader.name}
                </span>
                {leader.is_winner && (
                  <span className="text-sm bg-emerald-500/15 text-emerald-400 px-2 py-0.5 rounded font-medium">
                    Winner
                  </span>
                )}
              </div>
              <div className="text-right">
                <div className="font-mono text-2xl font-bold text-text-primary">
                  {formatProbability(leader.probability)}
                </div>
                <div className="text-sm text-text-secondary">
                  {formatAmericanOdds(leader.american_odds)}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Cross-Source Comparison (when market is tracked by multiple sources) */}
      {hasMultipleSources && groupData && (
        <CombinedMarketCard
          title={groupData.group_title}
          markets={groupData.markets.map((m) => ({
            id: m.id,
            name: m.name,
            source: m.source,
            external_id: m.external_id,
            status: m.status,
            outcome_count: m.outcome_count,
            outcomes: m.outcomes.map((o) => ({
              id: o.id,
              name: o.name,
              probability: o.probability,
              american_odds: o.american_odds,
              source: m.source,
            })),
          }))}
        />
      )}

      {/* Threshold Variants (e.g., "Bitcoin > $80K / $90K / $100K") */}
      {thresholdEntries.map(([stem, outcomes]) => (
        <ThresholdGrid
          key={stem}
          title={stem}
          outcomes={outcomes}
        />
      ))}

      {/* Progression (e.g., playoff rounds ordered by stage) */}
      {hasGroupProgression && (
        <div className="bg-surface-card rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-text-primary mb-4 flex items-center gap-2">
            <span>🏅</span>
            Round by Round
          </h2>
          <ProgressionTable
            markets={progressionMarkets.map((m) => ({
              id: m.id,
              name: m.name,
              source: m.source,
              group_position: m.group_position,
              status: m.status,
              outcomes: m.outcomes.map((o) => ({
                id: o.id,
                name: o.name,
                probability: o.probability,
                american_odds: o.american_odds,
                source: m.source,
                market_id: m.id,
              })),
            }))}
          />
        </div>
      )}

      {/* Games This Week */}
      {relatedEventsData && relatedEventsData.events.length > 0 && (
        <div className="bg-surface-card rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-text-primary mb-4 flex items-center gap-2">
            <span>📅</span>
            Games This Week
          </h2>
          <div className="space-y-2">
            {relatedEventsData.events.map((event) => (
              <RelatedEventRow key={event.event_id} event={event} />
            ))}
          </div>
        </div>
      )}

      {/* More from this category */}
      {market?.llm_sport_category && (
        <RelatedByTag
          tags={[`sport:${market.llm_sport_category}`]}
          excludeId={market.id}
          excludeType="futures"
          limit={4}
          title={`More ${market.llm_sport_category.charAt(0).toUpperCase() + market.llm_sport_category.slice(1)}`}
        />
      )}

      {/* Probability Chart (if history available) */}
      {historyData && historyData.outcomes.length > 0 && (
        <div className="bg-surface-card rounded-card shadow-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-title-3 font-semibold text-text-primary flex items-center gap-2">
              <span>📈</span>
              Probability Trends
            </h2>
            {/* Tab toggle: Over Time / By Stage */}
            {hasProgression && (
              <div className="flex bg-white/5 rounded-lg p-0.5 gap-0.5">
                <button
                  onClick={() => setTrendView("evolution")}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    trendView === "evolution"
                      ? "bg-white/10 text-text-primary"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  Over Time
                </button>
                <button
                  onClick={() => setTrendView("progression")}
                  className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                    trendView === "progression"
                      ? "bg-white/10 text-text-primary"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  By Stage
                </button>
              </div>
            )}
          </div>
          {trendView === "progression" && hasProgression && progressionData ? (
            <TournamentProgressionTable data={progressionData} />
          ) : market && market.outcomes.length > 10 ? (
            <TournamentChart
              marketId={marketId}
              canonicalKey={
                market.canonical_market_key && (market.source_count ?? 1) > 1
                  ? market.canonical_market_key
                  : undefined
              }
              hours={historyHours}
            />
          ) : (
            <FuturesChart
              historyData={historyData.outcomes}
              selectedOutcomes={selectedOutcomes}
              onToggleOutcome={toggleOutcomeSelection}
            />
          )}
        </div>
      )}

      {/* All Outcomes Table */}
      <div className="bg-surface-card rounded-card shadow-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-title-3 font-semibold text-text-primary flex items-center gap-2">
            <span>📊</span>
            All Outcomes
          </h2>
          {sortedOutcomes.length > 25 && (
            <button
              onClick={() => setShowAllOutcomes(!showAllOutcomes)}
              className="text-sm text-text-secondary hover:text-text-primary transition-colors"
            >
              {showAllOutcomes
                ? "Show less"
                : `Show all ${sortedOutcomes.length}`}
            </button>
          )}
        </div>

        {/* Sort controls */}
        <div className="flex gap-2 mb-4 flex-wrap">
          <SortButton
            label="Probability"
            field="probability"
            currentField={sortField}
            direction={sortDirection}
            onClick={() => toggleSort("probability")}
          />
          <SortButton
            label="24h Change"
            field="change"
            currentField={sortField}
            direction={sortDirection}
            onClick={() => toggleSort("change")}
          />
          <SortButton
            label="Name"
            field="name"
            currentField={sortField}
            direction={sortDirection}
            onClick={() => toggleSort("name")}
          />
        </div>

        {/* Outcomes list */}
        <div className="space-y-2">
          {displayedOutcomes.map((outcome, index) => (
            <OutcomeRow
              key={outcome.id}
              outcome={outcome}
              rank={outcome.rank ?? index + 1}
              isLeader={outcome.id === leader?.id}
              isSelected={selectedOutcomes.has(outcome.id)}
              onToggleSelect={() => toggleOutcomeSelection(outcome.id)}
              hasHistory={historyData?.outcomes.some(
                (h) => h.outcome_id === outcome.id
              ) ?? false}
              marketCategory={market?.llm_sport_category}
              marketName={market?.name}
            />
          ))}
        </div>

        {/* Show more button */}
        {!showAllOutcomes && sortedOutcomes.length > 25 && (
          <button
            onClick={() => setShowAllOutcomes(true)}
            className="w-full mt-4 py-2 text-sm text-text-secondary hover:text-text-primary border border-surface-border rounded-lg hover:bg-slate/5 transition-colors"
          >
            Show {sortedOutcomes.length - 25} more outcomes
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Sort button component
 */
function SortButton({
  label,
  field,
  currentField,
  direction,
  onClick,
}: {
  label: string;
  field: SortField;
  currentField: SortField;
  direction: SortDirection;
  onClick: () => void;
}) {
  const isActive = field === currentField;

  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors flex items-center gap-1 ${
        isActive
          ? "bg-text-primary text-surface-deep"
          : "bg-surface-elevated text-text-secondary hover:bg-surface-border"
      }`}
    >
      {label}
      {isActive && (
        <span>{direction === "asc" ? "↑" : "↓"}</span>
      )}
    </button>
  );
}

/**
 * Single outcome row
 */
function OutcomeRow({
  outcome,
  rank,
  isLeader,
  isSelected,
  onToggleSelect,
  hasHistory,
  marketCategory,
  marketName,
}: {
  outcome: FuturesOutcome;
  rank: number;
  isLeader: boolean;
  isSelected: boolean;
  onToggleSelect: () => void;
  hasHistory: boolean;
  marketCategory?: string | null;
  marketName?: string;
}) {
  const change = outcome.probability_change_24h;
  const rankChange = outcome.rank_change_24h;

  // Entity image detection
  const isNonSports = isNonSportsCategory(marketCategory ?? null);
  const isIntl = isInternationalSport(marketCategory ?? null);
  const outcomeFlag = isIntl ? flagUrl(outcome.name) : null;

  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-lg transition-colors ${
        isSelected
          ? "bg-blue-50 border border-blue-200"
          : isLeader
          ? "bg-amber-50 border border-amber-200"
          : "bg-slate/5 hover:bg-slate/10"
      }`}
    >
      {/* Selection checkbox (for chart) */}
      {hasHistory && (
        <button
          onClick={(e) => {
            e.preventDefault();
            onToggleSelect();
          }}
          className={`w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
            isSelected
              ? "bg-blue-500 border-blue-500 text-white"
              : "border-slate/30 hover:border-text-secondary"
          }`}
        >
          {isSelected && (
            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                clipRule="evenodd"
              />
            </svg>
          )}
        </button>
      )}

      {/* Rank */}
      <span
        className={`w-8 h-8 flex items-center justify-center text-sm rounded-full shrink-0 ${
          isLeader
            ? "bg-amber-100 text-amber-700 font-bold"
            : "bg-surface-card text-text-secondary border border-surface-border"
        }`}
      >
        {rank}
      </span>

      {/* Rank change indicator */}
      {rankChange !== null && rankChange !== 0 && (
        <span
          className={`text-xs shrink-0 ${
            rankChange < 0 ? "text-emerald-600" : "text-red-500"
          }`}
        >
          {rankChange < 0 ? `↑${Math.abs(rankChange)}` : `↓${rankChange}`}
        </span>
      )}

      {/* Name */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        {outcomeFlag ? (
          <img
            src={outcomeFlag}
            alt={outcome.name}
            width={24}
            height={18}
            loading="lazy"
            className="rounded-sm flex-shrink-0"
          />
        ) : isNonSports ? (
          <EntityImage type="wikipedia" name={outcome.name} size={24} />
        ) : null}
        <div className="min-w-0">
          <span
            className={`text-sm truncate block ${
              isLeader ? "font-semibold text-text-primary" : "text-text-primary"
            }`}
          >
            {outcome.name}
          </span>
          {outcome.is_winner && (
            <span className="text-xs text-emerald-600 font-medium">Winner</span>
          )}
        </div>
      </div>

      {/* Opening vs Current comparison */}
      {outcome.opening_probability !== null && (
        <div className="text-xs text-text-secondary text-right shrink-0">
          <div>
            Open: {formatProbability(outcome.opening_probability)}
          </div>
        </div>
      )}

      {/* 24h Change */}
      <div className="w-20 text-right shrink-0">
        {change !== null && change !== 0 ? (
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              change > 0
                ? "bg-emerald-500/15 text-emerald-400"
                : "bg-red-500/15 text-red-400"
            }`}
          >
            {change > 0 ? "+" : ""}
            {(change * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="text-xs text-text-muted">-</span>
        )}
      </div>

      {/* Current probability and odds */}
      <div className="text-right shrink-0">
        <div
          className={`font-mono text-base tabular-nums ${
            isLeader ? "font-bold text-text-primary" : "font-semibold text-text-primary"
          }`}
        >
          {formatProbability(outcome.probability)}
        </div>
        <div className="text-xs text-text-secondary font-mono">
          {formatAmericanOdds(outcome.american_odds)}
        </div>
      </div>
    </div>
  );
}

/**
 * Compact row for a related event on the futures detail page
 */
function RelatedEventRow({ event }: { event: RelatedEvent }) {
  const isLive = event.status === "live";
  const isFinished = event.status === "completed" || event.status === "closed";
  const hasScore = event.home_score !== null && event.away_score !== null;

  // Format time
  let timeLabel = "";
  if (isLive) {
    timeLabel = "Live";
  } else if (isFinished) {
    timeLabel = "Final";
  } else {
    const d = new Date(event.commence_time);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const isTomorrow = d.toDateString() === tomorrow.toDateString();
    const timeStr = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    if (isToday) {
      timeLabel = `Today ${timeStr}`;
    } else if (isTomorrow) {
      timeLabel = `Tomorrow ${timeStr}`;
    } else {
      timeLabel = d.toLocaleDateString([], { weekday: "short" }) + ` ${timeStr}`;
    }
  }

  return (
    <Link
      href={`/events/${event.event_id}`}
      className="flex items-center gap-3 p-3 rounded-lg bg-slate/5 hover:bg-slate/10 transition-colors"
    >
      {/* Status indicator */}
      <div className="w-16 flex-shrink-0">
        {isLive ? (
          <span className="flex items-center gap-1 text-xs font-semibold text-accent-live">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
            LIVE
          </span>
        ) : isFinished ? (
          <span className="text-xs font-semibold text-text-muted">FINAL</span>
        ) : (
          <span className="text-xs text-text-secondary">{timeLabel}</span>
        )}
      </div>

      {/* Teams + score */}
      <div className="flex-1 min-w-0">
        <div className="text-sm text-text-primary truncate">
          {hasScore ? (
            <span>
              <span className={isFinished && event.away_score! > event.home_score! ? "font-semibold" : ""}>
                {event.away_team}
              </span>
              <span className="font-mono text-text-muted mx-1">
                {event.away_score} - {event.home_score}
              </span>
              <span className={isFinished && event.home_score! > event.away_score! ? "font-semibold" : ""}>
                {event.home_team}
              </span>
            </span>
          ) : (
            <span>
              {event.away_team}
              <span className="text-text-muted mx-1.5">at</span>
              {event.home_team}
            </span>
          )}
        </div>
      </div>

      {/* Linked team odds from this market */}
      <div className="flex items-center gap-3 flex-shrink-0">
        {event.linked_teams.map((lt) => (
          <span key={lt.team_name} className="text-xs text-text-secondary">
            <span className="font-medium text-text-primary">{lt.team_name.split(" ").pop()}</span>
            {lt.probability !== null && (
              <span className="ml-1 font-mono text-text-muted">
                {Math.round(lt.probability * 100)}%
              </span>
            )}
          </span>
        ))}
      </div>
    </Link>
  );
}

/**
 * Pin icon - pushpin style
 */
function PinIcon({ filled, className }: { filled: boolean; className?: string }) {
  if (filled) {
    // Filled pushpin
    return (
      <svg className={className} viewBox="0 0 24 24" fill="currentColor">
        <path d="M16 4c0-.55-.22-1.05-.58-1.41-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-6.01 6.01C5.22 9.95 4 11.59 4 13.5c0 1.1.45 2.1 1.17 2.83L2 19.5l1.41 1.41 3.17-3.17c.73.72 1.73 1.17 2.83 1.17 1.91 0 3.55-1.22 4.91-2.58l6.01-6.01c.36-.36.58-.86.58-1.41s-.22-1.05-.58-1.41c-.37-.37-.86-.59-1.42-.59s-1.05.22-1.41.58l-4.95 4.95-2.12-2.12L16 4z"/>
      </svg>
    );
  }

  // Outline pushpin
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v1H5V5z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 11v6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17h6" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 6h14l-2 5H7L5 6z" />
    </svg>
  );
}
