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
} from "@/lib/api";
import type { FuturesOutcome, RelatedEvent } from "@/lib/types";
import {
  marketEventKey,
  eventPath,
  conceptDisplayLabel,
  hubLabel,
  hubPath,
  categoryPageLabel,
  categoryPagePath,
  sportPagePath,
} from "@/lib/eventKey";
import ErrorMessage from "@/components/ErrorMessage";
import { usePinnedFutures } from "@/hooks";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAnalyticsContext } from "@/components/Analytics";
import { FuturesHero } from "@/components/FuturesHero";
import { FuturesChart } from "@/components/FuturesChart";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import QuantityGroup, { buildThresholdRungs } from "@/components/QuantityGroup";
import ProgressionTable from "@/components/ProgressionTable";
import EntityImage from "@/components/EntityImage";
import RelatedByTag from "@/components/RelatedByTag";
import { isNonSportsCategory, isInternationalSport, flagUrl } from "@/lib/images";
import { movementExplanation as movementExplanationHelper, pickHeroOutcome } from "@/lib/futuresDetailDisplay";
import { buildAmbientPoints } from "@/lib/futuresAmbient";

interface FuturesDetailPageProps {
  params: { id: string };
}

/**
 * Category emoji for non-image hero backgrounds
 */
function getCategoryEmoji(category: string | null): string {
  if (!category) return "🍀";
  switch (category.toLowerCase()) {
    case "politics": return "🏛";
    case "geopolitics": return "🌍";
    case "economics": return "📈";
    case "tech": return "💻";
    case "entertainment": return "🎬";
    case "culture": return "🎭";
    case "weather": return "🌤";
    case "health": return "🏥";
    default: return "🍀";
  }
}

/**
 * Detect whether an outcome name is a recognizable entity (person, team, place)
 * vs a generic/date-like identifier that needs extra context in the hero display.
 *
 * Returns true for names like "May 18", "2026", "Q3", "Option A", "Before July",
 * "Over 5.5", bare numbers, single short words, or Yes/No variants.
 * Returns false for names that look like real entities: "Celtics", "Trump",
 * "Kendrick Lamar", "Manchester City".
 */
function isGenericOutcomeName(name: string): boolean {
  const trimmed = name.trim();

  // Short single-token names (<=4 chars) are likely generic unless they look like
  // known abbreviations that are still meaningful (e.g., "Yes", "No")
  if (trimmed.length <= 3) return true;

  // Bare numbers or numbers with units: "5", "42.5", "100+", "$50"
  if (/^[$]?\d+([.,]\d+)?[+%]?$/.test(trimmed)) return true;

  // Date patterns: "May 18", "June 2026", "Jan 1, 2027", "2025-06", "Q3 2026"
  const datePatterns = [
    /^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d/i,
    /^(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d/i,
    /^\d{4}(-\d{2})?$/,
    /^Q[1-4]\b/i,
    /^(Before|After|By)\s+(January|February|March|April|May|June|July|August|September|October|November|December)/i,
    /^(Before|After|By)\s+(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)/i,
    /^(Before|After|By)\s+\d{4}/i,
    /^Week\s+\d/i,
  ];
  if (datePatterns.some((p) => p.test(trimmed))) return true;

  // Threshold/range patterns: "Over 5.5", "Under 100", ">=50", "250+"
  if (/^(Over|Under|Above|Below|At least|At most|More than|Less than|Fewer than)\s/i.test(trimmed)) return true;
  if (/^[<>=]+\s*\d/.test(trimmed)) return true;

  // Yes/No variants
  if (/^(Yes|No)(\s|$)/i.test(trimmed)) return true;

  // Option/Choice labels: "Option A", "Choice 1"
  if (/^(Option|Choice|Bucket)\s/i.test(trimmed)) return true;

  return false;
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
    // L2-156 Item 4 — settled markets show the FULL life (open → resolution).
    // Anchor the window to the market's open (created_at) so the whole trend is
    // visible; otherwise a settled market's movement predates the trailing
    // default window and the chart looks flat (exhibit market 37094267).
    const isSettledMarket =
      market?.status === "resolved" ||
      (market?.resolution_date != null && new Date(market.resolution_date) < new Date());
    if (isSettledMarket && market?.created_at) {
      const hoursSinceOpen =
        (Date.now() - new Date(market.created_at).getTime()) / (1000 * 60 * 60);
      // Reach back to the open (+ a small buffer), floored at 7d, capped at ~180d.
      return Math.min(Math.max(Math.ceil(hoursSinceOpen + 24), 168), 4320);
    }
    if (!market?.updated_at) return 168; // 7 days default
    const hoursSinceUpdate = (Date.now() - new Date(market.updated_at).getTime()) / (1000 * 60 * 60);
    // If last update was >3 days ago, expand the window to cover it
    if (hoursSinceUpdate > 72) {
      return Math.min(Math.ceil(hoursSinceUpdate + 48), 720); // up to 30 days
    }
    return 168; // 7 days
  }, [market?.status, market?.resolution_date, market?.created_at, market?.updated_at]);

  const {
    data: historyData,
    error: historyError,
    isLoading: historyLoading,
  } = useSWR(
    market ? ["futures-history", marketId, historyHours] : null,
    () => fetchFuturesHistory(marketId, historyHours)
  );
  const historyOutcomes = Array.isArray(historyData?.outcomes)
    ? historyData.outcomes
    : [];

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
  const progressionStages = Array.isArray(progressionData?.stages)
    ? progressionData.stages
    : [];
  const hasProgression = progressionStages.length >= 2;

  // Market group (cross-source comparison + threshold variants)
  const { data: groupData } = useSWR(
    market?.group_id ? ["futures-group", market.group_id] : null,
    () => fetchFuturesGroup(market!.group_id!),
    { revalidateOnFocus: false }
  );
  const groupMarkets = Array.isArray(groupData?.markets) ? groupData.markets : [];
  const thresholdGroups = groupData?.threshold_groups ?? {};
  const thresholdEntries = Object.entries(thresholdGroups).filter(([, outcomes]) => outcomes.length >= 2);
  // Progression-ordered markets (e.g., playoff rounds)
  const progressionMarkets = groupMarkets
    .filter((m) => m.group_position !== null && m.group_position !== undefined)
    .sort((a, b) => (a.group_position ?? 0) - (b.group_position ?? 0));
  const hasGroupProgression = progressionMarkets.length >= 2;
  const relatedEvents = Array.isArray(relatedEventsData?.events)
    ? relatedEventsData.events
    : [];

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

  // L2-156 Item 2 — the chart is never an empty "select outcomes below" state.
  // Default to the top 2-3 outcomes; on a settled market default to the WINNER
  // (is_winner, which may not be the highest current probability) + runner-up.
  // Only seed ids that actually have history rows, so the chart renders on first
  // paint rather than filtering down to nothing. Seeds once per market.
  const didInitSelection = useRef(false);
  useEffect(() => {
    if (didInitSelection.current) return;
    if (!market?.outcomes || market.outcomes.length === 0) return;

    const byProb = [...market.outcomes].sort(
      (a, b) => (b.probability ?? 0) - (a.probability ?? 0)
    );
    const settled = market.status === "resolved";
    let seeds: FuturesOutcome[];
    if (settled) {
      const winner = market.outcomes.find((o) => o.is_winner === true) ?? byProb[0];
      const runnerUp = byProb.find((o) => o.id !== winner.id);
      seeds = runnerUp ? [winner, runnerUp] : [winner];
    } else {
      seeds = byProb.slice(0, 3);
    }

    // Prefer ids that have history rows. If history hasn't loaded yet, fall back to
    // the computed seed — the effect re-runs when historyOutcomes arrives.
    const historyIds = new Set(historyOutcomes.map((o) => o.outcome_id));
    let seedIds = seeds.map((o) => o.id);
    if (historyIds.size > 0) {
      const withHistory = seedIds.filter((id) => historyIds.has(id));
      if (withHistory.length > 0) seedIds = withHistory;
    }

    if (seedIds.length > 0) {
      didInitSelection.current = true;
      setSelectedOutcomes(new Set(seedIds));
    }
  }, [market?.outcomes, market?.status, historyOutcomes]);

  // #883: the clarification that EXPLAINS the blend line's movement (#871-style,
  // deterministic from opening vs current — no per-source detail, blend-only).
  // Pure logic in lib/futuresDetailDisplay.ts (unit-tested).
  const movementExplanation = useMemo(
    () => movementExplanationHelper(leader),
    [leader]
  );

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
    // #883 L2-49: skeleton mirrors the blend-only anatomy (title → big number →
    // chart → movement → related), not a spinner void, so the layout doesn't
    // jump when data lands.
    return (
      <div className="space-y-6" aria-busy="true" aria-label="Loading market">
        {backLink}
        <div className="animate-pulse space-y-6">
          {/* Hero: category + title + big number */}
          <div className="space-y-4">
            <div className="h-3 w-24 rounded bg-surface-elevated" />
            <div className="h-6 w-3/4 rounded bg-surface-elevated" />
            <div className="h-14 w-40 rounded bg-surface-elevated" />
          </div>
          {/* Chart card + movement line */}
          <div className="bg-surface-card rounded-card shadow-card p-6 space-y-4">
            <div className="h-5 w-40 rounded bg-surface-elevated" />
            <div className="h-40 w-full rounded bg-surface-elevated" />
            <div className="h-3 w-56 rounded bg-surface-elevated" />
          </div>
          {/* Related / outcomes cards */}
          {[0, 1].map((i) => (
            <div key={i} className="bg-surface-card rounded-card shadow-card p-6 space-y-3">
              <div className="h-5 w-36 rounded bg-surface-elevated" />
              <div className="h-4 w-full rounded bg-surface-elevated" />
              <div className="h-4 w-5/6 rounded bg-surface-elevated" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (
    marketError ||
    !market ||
    typeof market.name !== "string" ||
    !Array.isArray(market.outcomes)
  ) {
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

  const isResolved = market.status === "resolved";
  // #883 L2-49: on a resolved market the hero features the actual WINNER (which
  // may differ from the highest-probability outcome), labeled as final — not a
  // live probability. Falls back to the leader if no winner is flagged yet.
  const resolvedWinner = isResolved ? pickHeroOutcome(market.outcomes, leader, true) : null;
  const heroOutcome = pickHeroOutcome(market.outcomes, leader, isResolved);
  // L2-161 Hero C: the hero outcome's own 7-day curve, drawn as ambient texture
  // behind the numeral. Empty ⇒ the hero falls back to a plain numeral.
  const ambientPoints = buildAmbientPoints(historyOutcomes, heroOutcome?.id ?? null);

  // L2-65 Item 1b / B7 L2-91: link UP to the richer event-concept surface. Prefer
  // the server-derived key (covers UFC/boxing/F1/golf-majors/tennis/awards and never
  // dead-links); fall back to the client resolver for older payloads. When there's
  // no specific concept but the competition has a hub (/hub/mma, /hub/golf, …), link
  // that instead. Where neither exists, no link — honest.
  const conceptKey = market.event_concept_key || marketEventKey(market);
  const conceptLabel = conceptDisplayLabel(conceptKey, market.name);
  const hubSlug = !conceptKey ? market.hub_slug || null : null;
  const hubLinkLabel = hubLabel(hubSlug);
  // L2-94: fallbacks below the hub — a themed-category market (politics/economics/
  // weather/entertainment) up-links to its section page; a hub-less sport futures
  // market (soccer, …) up-links to its sport page. First of concept/hub/category/
  // sport that resolves wins; no link where none does (honest).
  const categorySlug = !conceptKey && !hubSlug ? market.category_page || null : null;
  const categoryLinkLabel = categoryPageLabel(categorySlug);
  const sportPageKey =
    !conceptKey && !hubSlug && !categorySlug ? market.sport_page_key || null : null;
  const sportLinkLabel = sportPageKey ? market.sport_name || null : null;

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

      {/* Probability Hero — design spec FD-1 (resolved-aware, #883 L2-49) */}
      <FuturesHero
        name={market.name}
        probability={heroOutcome?.probability ?? null}
        outcomeName={heroOutcome ? (isGenericOutcomeName(heroOutcome.name) ? "Yes" : heroOutcome.name) : undefined}
        movement={!isResolved && leader?.probability_change_24h != null ? leader.probability_change_24h * 100 : null}
        sourceCount={market.source_count ?? undefined}
        resolveDate={
          isResolved
            ? undefined
            : market.resolution_date
              ? `Resolves ${new Date(market.resolution_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`
              : undefined
        }
        categoryEmoji={getCategoryEmoji(market.llm_sport_category)}
        categoryLabel={market.sport_name || market.llm_sport_category || undefined}
        isMultiOutcome={(market.outcome_count ?? 0) > 2}
        sparklinePoints={ambientPoints}
        resolved={isResolved}
        resolvedWon={resolvedWinner?.is_winner === true}
      />

      {/* L2-65 / B7 L2-91: breadcrumb UP into the richer event-concept surface
          (leaderboard, race chart, matchups), or the competition hub when there's no
          specific concept. */}
      {conceptKey && conceptLabel ? (
        <Link
          href={eventPath(conceptKey)}
          className="inline-flex items-center gap-1 text-sm font-medium text-accent-brand hover:underline"
        >
          Part of: {conceptLabel}
          <span aria-hidden="true">→</span>
        </Link>
      ) : hubSlug && hubLinkLabel ? (
        <Link
          href={hubPath(hubSlug)}
          className="inline-flex items-center gap-1 text-sm font-medium text-accent-brand hover:underline"
        >
          Part of: {hubLinkLabel}
          <span aria-hidden="true">→</span>
        </Link>
      ) : categorySlug && categoryLinkLabel ? (
        <Link
          href={categoryPagePath(categorySlug)}
          className="inline-flex items-center gap-1 text-sm font-medium text-accent-brand hover:underline"
        >
          Part of: {categoryLinkLabel}
          <span aria-hidden="true">→</span>
        </Link>
      ) : sportPageKey && sportLinkLabel ? (
        <Link
          href={sportPagePath(sportPageKey)}
          className="inline-flex items-center gap-1 text-sm font-medium text-accent-brand hover:underline"
        >
          Part of: {sportLinkLabel}
          <span aria-hidden="true">→</span>
        </Link>
      ) : null}

      {/* Context line (auto-upgrades when #870 ships) */}
      {market.hook_description && (
        <p className="text-[13px] leading-relaxed text-text-secondary mb-4 max-w-2xl">{market.hook_description}</p>
      )}

      {/* Legacy hero kept for share/pin actions */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={() => togglePin(marketId)}
          disabled={isMaxReached && !marketIsPinned}
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
            marketIsPinned ? "bg-amber-500/10 text-amber-600" : "bg-surface-elevated text-text-secondary hover:text-text-primary"
          } ${isMaxReached && !marketIsPinned ? "cursor-not-allowed opacity-30" : ""}`}
        >
          {marketIsPinned ? "Pinned" : "Pin"}
        </button>
      </div>

      {/* #883 blend-only: cross-source CombinedMarketCard removed — one blended
          number, not a source-by-source comparison table. */}

      {/* Blended probability trend line — directly under the hero (anatomy:
          title → blend line → why it moved → related markets). Single leader
          line by default, fixed 0–100 axis, no smoothing. */}
      {historyError && !historyLoading && (
        <div className="bg-surface-card rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-text-primary flex items-center gap-2 mb-4">
            <span>📈</span>
            Probability Trend
          </h2>
          <div className="h-32 flex flex-col items-center justify-center gap-2 text-sm text-text-secondary">
            <svg className="w-5 h-5 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
            <span>Limited price history available</span>
            <span className="text-xs text-text-muted">
              Prices update every 1{"–"}2 hours for this market
            </span>
          </div>
        </div>
      )}
      {historyData && historyOutcomes.length > 0 && (
        <div className="bg-surface-card rounded-card shadow-card p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-title-3 font-semibold text-text-primary flex items-center gap-2">
                <span>📈</span>
                Probability Trend
              </h2>
              {historyData.sparse && (
                <p className="text-xs text-text-muted mt-1">
                  Showing all available data
                  {historyData.auto_extended && historyData.actual_hours
                    ? ` (${Math.round(historyData.actual_hours / 24)}d window)`
                    : ""}
                  {" · "}Prices update every 1{"-"}2 hours
                </p>
              )}
              {!historyData.sparse && historyData.auto_extended && historyData.actual_hours && (
                <p className="text-xs text-text-muted mt-1">
                  Extended to {Math.round(historyData.actual_hours / 24)} days for more data
                </p>
              )}
            </div>
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
          ) : (
            // #883 slice 2 (L2-47): the hero shows the SINGLE leader blend line for
            // ALL market sizes — including >10-outcome markets that previously
            // rendered the multi-line TournamentChart (a tangle of lines that
            // contradicts "one clean number + why it moved"). selectedOutcomes is
            // seeded to the leader; the full per-outcome breakdown lives in the
            // "All Outcomes" table down in the rail. Fixed 0-100% axis, no smoothing.
            <FuturesChart
              historyData={historyOutcomes}
              selectedOutcomes={selectedOutcomes}
              onToggleOutcome={toggleOutcomeSelection}
              stepInterpolation={historyData.sparse}
              fixedYAxis
            />
          )}
          {/* The clarification: WHY the blend line moved (#871-style). Suppressed
              on resolved markets — the present-tense mover reads wrong once final
              (#883 L2-49); the resolved result is shown in the hero + outcomes. */}
          {movementExplanation && !isResolved && (
            <p className="text-[13px] leading-relaxed text-text-secondary mt-3">
              {movementExplanation}
            </p>
          )}
          {isResolved && resolvedWinner && (
            <p className="text-[13px] leading-relaxed text-text-secondary mt-3">
              Settled{resolvedWinner.is_winner === true ? ` — ${isGenericOutcomeName(resolvedWinner.name) ? "Yes" : resolvedWinner.name} won.` : "."}
            </p>
          )}
        </div>
      )}

      {/* Honest empty/sparse state: market loaded but no usable price history.
          Never render a broken/degenerate chart — say so plainly. (#883 L2-49) */}
      {!historyLoading && !historyError && historyOutcomes.length === 0 && (
        <div className="bg-surface-card rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-text-primary flex items-center gap-2 mb-3">
            <span>📈</span>
            Probability Trend
          </h2>
          <div className="h-24 flex flex-col items-center justify-center gap-1.5 text-sm text-text-secondary">
            <span>Not enough price history yet</span>
            <span className="text-xs text-text-muted">
              The trend line appears once this market has a few price points.
            </span>
          </div>
        </div>
      )}

      {/* Threshold ladder — one question, many rungs, heat-strip.
          QuantityGroup (Queue L2-118) replaces the old ThresholdGrid: a "≥ N"
          market is one continuous question, not N yes/no cards. */}
      {thresholdEntries.map(([stem, outcomes]) => (
        <QuantityGroup
          key={stem}
          title={stem}
          rungs={buildThresholdRungs(outcomes)}
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
      {relatedEvents.length > 0 && (
        <div className="bg-surface-card rounded-card shadow-card p-6">
          <h2 className="text-title-3 font-semibold text-text-primary mb-4 flex items-center gap-2">
            <span>📅</span>
            Games This Week
          </h2>
          <div className="space-y-2">
            {relatedEvents.map((event) => (
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

      {/* #883 blend-only: per-source SourceAggregationBlock removed — the blend
          is the product; source divergence is an upstream data-quality bug, not a
          surface to expose. Users see ONE clean number. */}

      {/* All Outcomes Table */}
      <div className="bg-surface-card rounded-card shadow-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-title-3 font-semibold text-text-primary flex items-center gap-2">
            <span>📊</span>
            {isResolved ? "Final Results" : "All Outcomes"}
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
              hasHistory={historyOutcomes.some(
                (h) => h.outcome_id === outcome.id
              )}
              marketCategory={market?.llm_sport_category}
              marketName={market?.name}
              isResolved={isResolved}
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
  isResolved = false,
}: {
  outcome: FuturesOutcome;
  rank: number;
  isLeader: boolean;
  isSelected: boolean;
  onToggleSelect: () => void;
  hasHistory: boolean;
  marketCategory?: string | null;
  marketName?: string;
  isResolved?: boolean;
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
          : isResolved && outcome.is_winner === true
          ? "bg-emerald-50 border border-emerald-200"
          : isResolved && outcome.is_winner === false
          ? "bg-slate-50/50"
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
          {isResolved && outcome.is_winner === true && (
            <span className="text-xs text-emerald-600 font-medium">Won</span>
          )}
          {isResolved && outcome.is_winner === false && (
            <span className="text-xs text-red-400 font-medium">Lost</span>
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
        {isResolved && outcome.is_winner !== null ? (
          <span className="text-xs text-text-muted">-</span>
        ) : change !== null && change !== 0 ? (
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
        {isResolved && outcome.is_winner === true ? (
          <>
            <div className="font-mono text-base tabular-nums font-bold text-emerald-600">
              100%
            </div>
            <div className="text-xs text-emerald-500 font-medium">
              Settled
            </div>
          </>
        ) : isResolved && outcome.is_winner === false ? (
          <>
            <div className="font-mono text-base tabular-nums font-semibold text-text-muted">
              0%
            </div>
            <div className="text-xs text-text-muted font-medium">
              Settled
            </div>
          </>
        ) : (
          <>
            <div
              className={`font-mono text-base tabular-nums ${
                isLeader ? "font-bold text-text-primary" : "font-semibold text-text-primary"
              }`}
            >
              {formatProbability(outcome.probability)}
            </div>
            {/* #883/L2-48: American moneyline (+9900) removed — probability only.
                The standing no-odds thesis: "60% vs 40%", never "-150/+130". */}
          </>
        )}
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
