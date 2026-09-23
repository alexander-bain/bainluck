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
  fetchEventConcept,
} from "@/lib/api";
import type { FuturesOutcome } from "@/lib/types";
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
import { isCadenceDormant, priceCadenceNote } from "@/lib/priceCadenceCopy";
import { newestInstant } from "@/lib/seriesFreshness";
import FuturesTrendRangeControls from "@/components/futures/FuturesTrendRangeControls";
import FuturesTrendEmptyState from "@/components/futures/FuturesTrendEmptyState";
import {
  defaultFuturesRange,
  futuresRangeHours,
  isFuturesRangeKey,
  type FuturesRangeKey,
} from "@/lib/futuresHistoryRange";
import { renderedOutcomeRowPercents } from "@/lib/renderedPercent";
import ErrorMessage from "@/components/ErrorMessage";
import { usePinnedFutures } from "@/hooks";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { useAnalyticsContext } from "@/components/Analytics";
import { FuturesHero } from "@/components/FuturesHero";
import { FuturesChart } from "@/components/FuturesChart";
import TournamentProgressionTable from "@/components/TournamentProgressionTable";
import QuantityGroup, { buildThresholdRungs } from "@/components/QuantityGroup";
import ProgressionTable from "@/components/ProgressionTable";
import OutcomeRow, {
  outcomeRowPrintsMove,
  outcomeRowShowsEntityImage,
} from "@/components/futures/OutcomeRow";
import RelatedByTag from "@/components/RelatedByTag";
import GamesThisWeek from "@/components/futures/GamesThisWeek";
import { toTitleCaseAcronymSafe } from "@/lib/titleCase";
import { renderedPricesAsOf } from "@/lib/futuresCardPriceAge";
import {
  asOfLabel,
  gradedWinner,
  movementExplanation as movementExplanationHelper,
  boardOutcomeLabel,
  movementWindowLabel,
  noPricedOutcomesNote,
  partitionOutcomesByPrice,
  pickCaptionSubject,
  pickChartSeedOutcomes,
  pickHeroOutcome,
  sortFuturesOutcomes,
  visibleChartOutcomes,
} from "@/lib/futuresDetailDisplay";
import type { FuturesSortField, FuturesSortDirection } from "@/lib/futuresDetailDisplay";
import { PinButton } from "@/components/PinButton";
import { resolveShape, SHAPE_QUANTITY } from "@/lib/marketShape";
import {
  buildOutcomeLadderRungs,
  ladderNeedsWideLabels,
  ladderOrderFor,
  thresholdLadderTitles,
} from "@/lib/futuresLadder";
import { buildAmbientPoints } from "@/lib/futuresAmbient";
import { formatResolvesLabel } from "@/lib/gameTimeLabel";
import { settlementBannerText } from "@/lib/settlementBanner";
import { independentOutcomesNote } from "@/lib/outcomeExclusivity";

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

// UX-P230: aliases of the sorter's own types, so the buttons and the comparator
// can never disagree about which fields exist.
type SortField = FuturesSortField;
type SortDirection = FuturesSortDirection;

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

  // #7545 — the reader's chosen history rung. `null` means "not chosen yet", which
  // is NOT the same as 1W: until the market loads we cannot tell whether its
  // default is a week, a month or its whole life, and defaulting to a week first
  // would fire a throwaway 168h fetch on every settled market.
  const rangeParam = searchParams.get("range");
  const [pickedRange, setPickedRange] = useState<FuturesRangeKey | null>(
    isFuturesRangeKey(rangeParam) ? rangeParam : null
  );

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

  // #7545 — the history window is a RUNG THE READER CAN SEE AND MOVE, not a
  // number derived behind the chart.
  //
  // What this replaces: the page used to compute one `historyHours` on mount —
  // 168h, or up to 720h for a market that had gone quiet, or up to 4320h for a
  // settled one — fetch it once, and offer no control. Two costs, both measured
  // on production 2026-09-20 and both recorded in `lib/futuresHistoryRange.ts`:
  // months of real history the reader could not reach (112921 served 161 points
  // at the default and 4,527 at `hours=8760`), and a span that moved on its own
  // as the backend's sparse-window extension tripped in and out.
  //
  // The rung the page OPENS on still honours all three of those intents — see
  // `defaultFuturesRange` — but it is now a named rung with a lit chip, and the
  // reader can leave it.
  const effectiveRange: FuturesRangeKey = pickedRange ?? defaultFuturesRange(market);

  // `created_at` sizes "All", so "All" reaches the market's own open instead of
  // the 4320h constant that truncated 112921 at 180 days with 213 available.
  const historyHours = useMemo(
    () => futuresRangeHours(effectiveRange, market?.created_at),
    [effectiveRange, market?.created_at]
  );

  // Put the choice in the URL so it survives a refresh and travels in a shared
  // link. `history.replaceState` rather than `router.replace`: this is the same
  // page with a different chip lit, so it should not push a navigation, refetch
  // the route, or move the reader's scroll position away from the chart they
  // just tapped under.
  const selectRange = (next: FuturesRangeKey) => {
    setPickedRange(next);
    // No `track()` here: the analytics taxonomy in `lib/analytics/types.ts` is a
    // governed vocabulary with its own sanitize layer, and inventing an event
    // name for it is a separate change from this one.
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    url.searchParams.set("range", next);
    window.history.replaceState(window.history.state, "", url.toString());
  };

  const {
    data: historyData,
    error: historyError,
    isLoading: historyLoading,
  } = useSWR(
    market ? ["futures-history", marketId, historyHours] : null,
    () => fetchFuturesHistory(marketId, historyHours),
    // #7545 — hold the previous rung's chart on screen while the next one loads.
    // Without this the card unmounts on every chip tap, which takes the CHIPS
    // down with it: the reader's own tap removes the control they just used, and
    // a wide "All" fetch (1.18 MB on /futures/1) leaves them looking at an empty
    // slot for the whole request. Keyed by hours, so the return trip to an
    // already-loaded rung is served from cache with no flash at all.
    { keepPreviousData: true }
  );
  const historyOutcomes = Array.isArray(historyData?.outcomes)
    ? historyData.outcomes
    : [];

  // L2-175 Item 3a: a UFC/boxing fight belongs to its CARD. Fetch the card concept
  // (combat only) so the breadcrumb can name it ("← UFC Fight Night · Aug 2") and we
  // can rail the card's OTHER fights — the hierarchy the URL pair implies but never
  // expressed. Combat-scoped so non-combat futures pay no extra request.
  const cardConceptKey = market
    ? market.event_concept_key || marketEventKey(market)
    : null;
  const isCombatCard = !!cardConceptKey && /^event:(ufc|boxing|mma):/i.test(cardConceptKey);
  const { data: cardConcept } = useSWR(
    isCombatCard ? ["event-concept-card", cardConceptKey] : null,
    () => fetchEventConcept(cardConceptKey as string),
    { revalidateOnFocus: false },
  );
  // The card's other fights (exclude props and THIS fight); each links to its page.
  const siblingFights = (cardConcept?.children || []).filter(
    (c) => c.kind !== "prop" && typeof c.market_id === "number" && c.market_id !== marketId,
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
  // #8167 — one decision for the whole set: a card's heading can depend on what
  // its SIBLINGS are called, so the headings are computed together and consumed
  // positionally beside the same array.
  const thresholdLadderHeadings = thresholdLadderTitles(
    thresholdEntries.map(([stem, outcomes]) => ({
      stem,
      outcomeNames: outcomes.map((o) => o.name),
    })),
    groupData?.group_title,
    market?.name,
  );

  // Q478 — dispatch on the SHAPE FIELD (`market_type`, #194), the one value every
  // surface is supposed to key off (lib/marketShape.ts). Until now the detail page
  // never read it: the ladder could only be reached through the backend's
  // `threshold_groups`, whose threshold parser is numeric-only, so a date ladder
  // ("Before April" … "Before 2027") rendered as a ranked leaderboard with rank
  // badges and "BA"/"BJ" initial avatars. `resolveShape` prefers the stored field
  // and keeps its structural fallback for the rows the #194 backfill hasn't reached.
  const marketShape = market
    ? resolveShape({
        market_type: market.market_type,
        outcomeNames: (market.outcomes ?? []).map((o) => o.name),
        groupId: market.group_id,
        groupSize: groupMarkets.length || undefined,
      })
    : null;
  // `threshold_groups` still owns the CROSS-MARKET ladder (many markets, one
  // question) — this covers the other half: one market whose own outcomes are the
  // rungs. Only one of the two ever draws, so the page can't print the ladder twice.
  //
  // Q481 (CERT-605) — A SETTLED MARKET NEVER LADDERS. Two measured reasons, and the
  // second is why "just add Won/Lost chrome to the rungs" is not the fix:
  //
  //  1. The ladder cannot show a RESULT. `QuantityRung` carries no winner state, so
  //     a resolved market drew four percentage bars under a "Final Results" heading
  //     while suppressing the one render that says `Won`/`Lost`/`Settled`. That is
  //     the `settled means settled` ruling broken on 278,151 markets — 96.6% of all
  //     `quantity` rows (resolved 278,151 vs open 9,678, production 2026-08-31).
  //  2. The ladder cannot ORDER a settled market either. Its rung order comes from
  //     ascending price, and settlement collapses price: of 1,500 settled quantity
  //     markets carrying a true winner, 1,260 (84%) hold two or fewer distinct
  //     probabilities and 60 hold exactly one. With every rung at 0% or 100% the
  //     order falls through to the stable-sort tiebreak — serve order — which for
  //     109349 is `2027, October, April, July`, i.e. the backwards timeline this
  //     queue exists to fix, now wearing a ladder's clothes. `opening_probability`
  //     is not a rescue: only 891 of those 1,500 (59.4%) have it on every row.
  //
  // So the graded table renders instead, exactly as it did before Q478. This costs
  // the ship NOTHING it ever measured: `census_quantity_ladder_q478.py` counts
  // `WHERE m.market_type = 'quantity' AND m.status = 'open'`, so the whole
  // 2,882 -> 9,491 win is open markets and every one of them still ladders.
  // Laddering settled markets was unmeasured scope, not a claim.
  // Teaching the ladder to grade AND to order itself without prices is filed as a
  // follow-up; it needs an ordering signal that survives settlement, which is a
  // data question, not a rendering one.
  const ownLadderRungs = useMemo(() => {
    if (marketShape !== SHAPE_QUANTITY) return [];
    if (thresholdEntries.length > 0) return [];
    if (market?.status === "resolved") return [];
    const outcomes = market?.outcomes ?? [];
    if (outcomes.length < 2) return [];
    return buildOutcomeLadderRungs(
      outcomes.map((o) => ({ id: o.id, name: o.name, probability: o.probability })),
      ladderOrderFor(market?.mutually_exclusive),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    marketShape,
    thresholdEntries.length,
    market?.outcomes,
    market?.mutually_exclusive,
    market?.status,
  ]);
  const hasOwnLadder = ownLadderRungs.length > 0;
  // D102 / #4568 — the same partition the ranked table below uses, on the rungs.
  // `buildOutcomeLadderRungs` already sorts a null probability to the end of a
  // cumulative ladder (POSITIVE_INFINITY), so this folds a block that was
  // already contiguous at the foot rather than reordering anything.
  const { listed: pricedRungs, folded: numberlessRungs } = useMemo(
    () => partitionOutcomesByPrice(ownLadderRungs),
    [ownLadderRungs],
  );
  // Progression-ordered markets (e.g., playoff rounds)
  const progressionMarkets = groupMarkets
    .filter((m) => m.group_position !== null && m.group_position !== undefined)
    .sort((a, b) => (a.group_position ?? 0) - (b.group_position ?? 0));
  const hasGroupProgression = progressionMarkets.length >= 2;
  const relatedEvents = Array.isArray(relatedEventsData?.events)
    ? relatedEventsData.events
    : [];

  // Sort outcomes. UX-P230: the comparators live in futuresDetailDisplay so all
  // six field×direction combinations can be exercised, not just the page default.
  // UX-P232 (CERT-598): the settled flag goes with them. On a resolved market the
  // hero features the GRADED WINNER (`pickHeroOutcome` below), whose frozen last
  // price is routinely not the highest on the board — so without this the section
  // headed "Final Results" led with a loser. `market.status`, never `is_winner`
  // alone: a stray flag must not make a live market claim a result.
  const sortedOutcomes = useMemo(() => {
    if (!market?.outcomes) return [];
    return sortFuturesOutcomes(
      market.outcomes,
      sortField,
      sortDirection,
      market.status === "resolved",
    );
  }, [market?.outcomes, market?.status, sortField, sortDirection]);

  // #2831: a two-outcome market prints both sides of one question, so the pair is
  // decided ONCE — here, over `market.outcomes` — and looked up per row by id.
  //
  // Derived from the UNSORTED market set on purpose. The rows below are sortable,
  // and a rule anchored on display order would print 93/7 by probability and 8/92
  // by name for the same market. `renderedOutcomeRowPercents` picks the favourite
  // whatever position it arrives in, and the id lookup means re-ordering the rows
  // cannot re-assign a number to a different outcome.
  //
  // Both price columns get it: the current pair and the OPENING pair are each two
  // sides of one question, exactly as `EventCard` treats its `opened` pair.
  const renderedById = useMemo(() => {
    const outs = market?.outcomes ?? [];
    const current = renderedOutcomeRowPercents(outs.map((o) => o.probability));
    const opening = renderedOutcomeRowPercents(outs.map((o) => o.opening_probability));
    return new Map(
      outs.map((o, i) => [o.id, { current: current[i] ?? null, opening: opening[i] ?? null }]),
    );
  }, [market?.outcomes]);

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

    // #7439 — the seed rule moved into `pickChartSeedOutcomes` so it could be
    // asserted directly; while it was inline the only available test was a
    // source grep, which cannot tell a correct filter from an inverted one.
    // Behaviour on settled markets is unchanged (L2-156 Item 2); on a LIVE,
    // non-mutually-exclusive field it no longer seeds a row already graded won,
    // which is what drew a flat 100% line across an open market's trend.
    const seeds: FuturesOutcome[] = pickChartSeedOutcomes(
      market.outcomes,
      market.status === "resolved",
      market.mutually_exclusive,
    );

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
  }, [market?.outcomes, market?.status, market?.mutually_exclusive, historyOutcomes]);

  // #883: the clarification that EXPLAINS the blend line's movement (#871-style,
  // deterministic from opening vs current — no per-source detail, blend-only).
  // Pure logic in lib/futuresDetailDisplay.ts (unit-tested).
  //
  // #8016 — ITS SUBJECT COMES FROM THE CHART, NOT FROM THE LEG LIST. `leader` is
  // the highest-probability row of the WHOLE field, and the chart deliberately
  // does not draw all of it (#7439 drops graded rows from a live non-mutex
  // board), so the caption could name a leg with no line: /futures/109257
  // captioned "Lionel Messi up 81.0 pts from opening." under a legend reading
  // Burnham · Putin · bin Salman. The subject is now the leading DRAWN line, and
  // there is deliberately no fallback to `leader` — a chart drawing nothing gets
  // no sentence (notice 34). `leader` itself is untouched: the hero's movement
  // pill asks a different question and keeps its own answer.
  const captionSubject = useMemo(() => {
    const drawnIds = new Set(
      visibleChartOutcomes(historyOutcomes, selectedOutcomes).map(
        (o) => o.outcome_id,
      ),
    );
    return pickCaptionSubject(market?.outcomes ?? [], drawnIds);
  }, [historyOutcomes, selectedOutcomes, market?.outcomes]);

  const movementExplanation = useMemo(
    () => movementExplanationHelper(captionSubject, market?.name),
    [captionSubject, market?.name]
  );

  // #8135 — when did this BOARD last print a number? The cadence promise below
  // is a claim about the market, not about whichever lines the reader has left
  // selected, so it reads every outcome the page holds. That is also the
  // conservative side: the more outcomes counted, the newer this instant, and a
  // promise is only withdrawn once nothing on the board has moved.
  //
  // The chart computes its own freshness over the DRAWN outcomes (#2961) and the
  // two are meant to differ: a board can still be printing numbers while the one
  // line on screen is behind. Same filter on both, so neither counts a priceless
  // row as an observation.
  const boardLastObservationMs = useMemo(
    () =>
      newestInstant(
        historyOutcomes.flatMap((o) =>
          o.history
            .filter((p) => p.probability !== null)
            .map((p) => p.timestamp),
        ),
      ),
    [historyOutcomes]
  );

  // D102 / #4568 — the rows that print a number, and the numberless ones folded
  // behind a disclosure. The reasoning, the four measured payloads and why the
  // predicate is the render's own live in `partitionOutcomesByPrice`.
  //
  // Everything downstream counts `pricedOutcomes`, never `sortedOutcomes`: the
  // 25-cap, the "Show all N" label and the "Show N more" button are all claims
  // about the list a reader is looking at, and folding rows out of that list
  // without moving its counters is how a "Show all 19" button comes to reveal
  // fourteen rows.
  const { listed: pricedOutcomes, folded: unpricedOutcomes } = useMemo(
    () => partitionOutcomesByPrice(sortedOutcomes),
    [sortedOutcomes],
  );

  // Limit displayed outcomes unless "show all" is enabled
  const displayedOutcomes = showAllOutcomes
    ? pricedOutcomes
    : pricedOutcomes.slice(0, 25);

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
      {/* #1763 decision 1: the /futures index is retired, so this pointed at a
          redirect and the label became a lie — "Back to Futures" landing on
          Discover. The staged brief called the index orphaned with ZERO inbound
          links; this is the one, and it lives on the very page the retirement
          keeps alive. When decision 3 rebuilds a real /futures landing, this is
          the link that should point back at it. */}
      <Link
        href="/discover"
        className="inline-flex items-center text-caption text-text-secondary hover:text-text-primary transition-colors"
      >
        <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to Discover
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
  // #7060 — the banner is gated on settlement EVIDENCE (`status`), never on a
  // scheduled date having gone by. See `lib/settlementBanner.ts`.
  const settlementBanner = settlementBannerText(market);
  // #3358: whether the "Last move" column is worth any width is a decision about the
  // WHOLE table, so it is made here and passed down, never re-derived per row. On
  // this issue's own market and on `/futures/202` every row prints `–`, and that dead
  // 80px column is most of why the name column had 26px to print a name in.
  const showLastMove = displayedOutcomes.some((o) =>
    outcomeRowPrintsMove(o, isResolved),
  );
  // #4483: whether the rows draw an entity picture is also a whole-table decision,
  // and it reuses the `marketShape` already resolved above rather than resolving a
  // second time — two calls are two chances to disagree.
  //
  // This is the OTHER half of the Q478 comment up there. Q478 routed a date/threshold
  // ladder away from the ranked table so it would stop drawing "BA"/"BJ" avatars —
  // but Q481 then ruled that a SETTLED quantity market never ladders, so it falls
  // back to this very table and draws them again. That is exactly how #4483's
  // specimen (a resolved `quantity` market) ends up with four identical `A5` chips:
  // the avatar was fixed on the ladder path and left standing on the fallback path.
  //
  // #6632: the names are the THIRD input, and deliberately the same whole set
  // `marketShape` was resolved from above — `market.outcomes`, not
  // `displayedOutcomes`. The "show more" toggle must not be able to change what the
  // board IS, and #4416's rule is all-or-nothing over the shipped set.
  const showEntityImage = outcomeRowShowsEntityImage(
    market.llm_sport_category,
    marketShape,
    (market.outcomes ?? []).map((o) => o.name),
  );
  // UX-P233 (board item 11): "as of Aug 28" when the prices are older than a day,
  // null when they are current. One line for the whole board — see the render.
  //
  // #7785 — THE FLOOR OVER THE ROWS THIS PAGE DRAWS, NOT THE LEADER'S STAMP.
  //
  // This read `asOfLabel(leader?.last_updated)`, and `leader` is the
  // HIGHEST-PROBABILITY outcome. #6018 rejected exactly that rule for the search
  // card in as many words — "taking the newest would let one refreshed favourite
  // vouch for four stale rungs" — and shipped `renderedPricesAsOf`, which every
  // other surface (card, My Stuff, the iOS twin) has read since. The one surface
  // that puts the most rows under a single label kept the ceiling.
  //
  // Because the leader is also the most-polled row, the failure is SILENCE
  // rather than a visibly wrong date: `asOfLabel` returns null and the header
  // says nothing. Production, 2026-09-21 at 390px: `/futures/12046267` (the WNBA
  // title board) drew Minnesota's 46% written that morning above Phoenix,
  // Toronto and Los Angeles at 0% last written 2026-09-19, under a bare "All
  // Outcomes". `/futures/275` (Pro Baseball Champion) is the same shape. Across
  // the served payloads of the 199 busiest open tier-1/2 boards, the leader rule
  // labels 37 and the floor labels 41.
  //
  // WHICH ROWS. The claim is "nothing you can see here is older than this", so
  // the scope is what the branch below actually renders:
  //
  //   - the ranked table draws `displayedOutcomes` — the 25-cap matters. On the
  //     391 open tier-1–3 boards with more than 25 priced rows the two scopes
  //     print a different date on 17, and on 7 of those the wider scope would
  //     date the header from rows BELOW the cap that the reader cannot see,
  //     which is #6018's own named mirror-image lie.
  //   - the ladder draws every priced rung: `QuantityGroup` is neither `compact`
  //     nor given `maxRungs` here, and `buildOutcomeLadderRungs` is a 1:1 map
  //     over `market.outcomes` that filters nothing, so `pricedRungs` and
  //     `pricedOutcomes` are the same membership under the same
  //     `probability == null` predicate.
  //
  // `renderedPricesAsOf` (not a second opinion written here) also carries #6803:
  // a rung showing no number has no age this sentence is about, and 0 IS a price
  // and keeps its vote. `pricedOutcomes`/`displayedOutcomes` are already that
  // partition, so the helper's guard is a belt over a brace, not the only one.
  const asOfRows = hasOwnLadder ? pricedOutcomes : displayedOutcomes;
  const marketAsOf = asOfLabel(renderedPricesAsOf({ outcomes: asOfRows }));
  // #883 L2-49: on a resolved market the hero features the actual WINNER (which
  // may differ from the highest-probability outcome), labeled as final — not a
  // live probability. Falls back to the leader if no winner is flagged yet.
  //
  // #6301 — RENAMED from `resolvedWinner`, which is what this variable was called
  // while it held a rider who lost. It is the FEATURED row on a settled market and
  // the fallback means it is frequently not a winner at all; the old name read as
  // a guarantee the value never made, and every misuse below started by trusting it.
  const resolvedFeatured = isResolved ? pickHeroOutcome(market.outcomes, leader, true) : null;
  // #7439 — on a LIVE, non-mutually-exclusive field the hero features the live
  // leader, not a row already graded won (which sits at 1.0 and wins the sort
  // forever). `mutually_exclusive` is passed through rather than read inside the
  // helper because the mutex half of that population must NOT move — see the
  // fork documented on `pickHeroOutcome`. `resolvedFeatured` above passes a
  // literal `true` and is unaffected.
  const heroOutcome = pickHeroOutcome(
    market.outcomes,
    leader,
    isResolved,
    market.mutually_exclusive,
  );
  // #6301 — the GRADE, asked for BY NAME through the one helper that owns the test.
  // `gradedWinner` returns the featured row only when `is_winner === true`, and null
  // on every settled field that never graded one. `layout.tsx` adopted it under #6079
  // and this page did not, which is the whole of why the unfurl title was right about
  // the Vuelta while the page it links to was wrong.
  // #7906 — `market_type` is passed so a board that graded MANY winners (72 of the
  // 163 golfers on this page's own specimen made the cut) crowns none of them,
  // while a cumulative ladder — the one shape whose plural grades are the design —
  // still names its rung. See the helper's block comment.
  const gradedChampion = gradedWinner(
    market.outcomes,
    leader,
    market.status,
    market.market_type,
    market.mutually_exclusive,
  );
  // #6301 — A SETTLED FIELD WITH NO WINNER NAMES NOBODY.
  //
  // `pickHeroOutcome` answers "which row does this surface feature", and on a
  // resolved market with nothing graded it answers with the price leader. That
  // is the right answer to its question (#6079 settled this: the subject and
  // the verdict are two questions) and it is the wrong thing to print in 24px
  // above a table whose first row says that rider LOST.
  //
  // Production, `/futures/58675941` — *Vuelta a Espana 2026: Winner*:
  //
  //     Tadej Pogacar   RESOLVED
  //     Final Results
  //      1  Tadej Pogacar   Lost   0%   Settled
  //
  // All 30 outcomes carry `is_winner:false` and `probability:0.0`; the only
  // thing that singled him out is `rank: 1`, a stale PRE-RACE rank frozen from
  // when he was the favourite. Enric Mas Nicolau won that race, and we crown him
  // correctly on our Kalshi copy of the same question.
  //
  // The chip was already honest — it reads grey "Resolved", not "Won", because
  // `resolvedWon` has always been gated on the grade. The NAME beside it was
  // not, and a name in the hero position IS the crowning.
  //
  // 🔴 NOT a blanket suppression on settled markets, and the difference is the
  // whole fix: this declines only when the grade is ABSENT. A field with a real
  // champion still names them. `all_losers`' own producer comment says it means
  // "the winning outcome isn't in our DB" — a statement of absence, which this
  // page was reading as an answer (#4923: no verdict beats a wrong one).
  //
  // Declined SILENTLY (notice 34): `FuturesHero` already guards its name on
  // `outcomeName &&`, so withholding it leaves the title and the grey chip and
  // no hole. The "Final Results" table below is honest and carries the page.
  const heroNamesNobody = isResolved && gradedChampion === null;
  // L2-161 Hero C: the hero outcome's own 7-day curve, drawn as ambient texture
  // behind the numeral. Empty ⇒ the hero falls back to a plain numeral.
  const ambientPoints = buildAmbientPoints(historyOutcomes, heroOutcome?.id ?? null);

  // lane1-Q479 (defect 13). Counted off `market.outcomes`, not `outcome_count`:
  // the note is a claim about the rows the reader can actually see and add up,
  // and those two numbers are not the same field.
  // CERT-609: `source` is load-bearing, not decoration. Polymarket's parser turns
  // an ABSENT `negRisk` key into `false`, so only Kalshi's `false` is affirmative.
  const independenceNote = independentOutcomesNote(
    market.mutually_exclusive,
    market.outcomes?.length ?? 0,
    isResolved,
    market.source
  );

  // #6989 — every row in the ranked table below is numberless, so the table's
  // furniture is making claims about numbers that are not on screen. ONE call
  // decides all three suppressions and the sentence, so a future edit cannot
  // teach the chips and the caption two different answers to the same question.
  // The rows themselves stay, folded, in `More outcomes (N)`.
  const noPricesNote = noPricedOutcomesNote(pricedOutcomes.length);

  // L2-65 Item 1b / B7 L2-91: link UP to the richer event-concept surface. Prefer
  // the server-derived key (covers UFC/boxing/F1/golf-majors/tennis/awards and never
  // dead-links); fall back to the client resolver for older payloads. When there's
  // no specific concept but the competition has a hub (/hub/mma, /hub/golf, …), link
  // that instead. Where neither exists, no link — honest.
  const conceptKey = market.event_concept_key || marketEventKey(market);
  const conceptLabel = conceptDisplayLabel(conceptKey, market.name);
  // L2-175 Item 3a: a named card breadcrumb ("← UFC Fight Night · Aug 2") when the
  // combat card concept resolved — beats the generic "the full fight card".
  const cardDate = cardConcept?.event?.start_date ? new Date(cardConcept.event.start_date) : null;
  const cardDateLabel =
    cardDate && !Number.isNaN(cardDate.getTime())
      ? cardDate.toLocaleDateString("en-US", { month: "short", day: "numeric" })
      : null;
  const cardName = cardConcept?.event?.name || null;
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

      {/* Settled market banner — #7060/#7058. The decision and the words live in
          `lib/settlementBanner.ts`: this page is a client component, so that is
          the only place a guard test can reach them. A `resolution_date` is a
          SCHEDULE and never reaches this render. */}
      {settlementBanner && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3 text-sm text-amber-400">
          {settlementBanner}
        </div>
      )}

      {/* Probability Hero — design spec FD-1 (resolved-aware, #883 L2-49) */}
      <FuturesHero
        name={market.name}
        probability={heroNamesNobody ? null : heroOutcome?.probability ?? null}
        // #6301 — the number travels with the name, and this half is DEFENSIVE
        // rather than a visible repair. Measured before writing it: every `pct`
        // site in `FuturesHero` is gated on `!resolved` (the 64px numeral, the
        // Yes/No bar) or on `resolvedWon` (the "Markets gave this just X%" note),
        // and `heroNamesNobody` implies `resolved && !resolvedWon` — so on today's
        // component this ternary changes no pixel and no test can kill it. It is
        // stated as an equivalent mutant in the PR rather than counted as a guard.
        //
        // It is kept because the coupling is the thing that stops a REOPENING: the
        // settled hero is one design change away from carrying a numeral again, and
        // `/futures/60010606` (Vuelta Stage 3, void at the venue, 184 legs, 0
        // winners) serves its rank-1 loser at `probability: 0.35` — not the 0.0 the
        // all-losers fields serve. The day that branch prints a number, it would
        // print "35%" under no name at all.
        outcomeName={
          heroNamesNobody || !heroOutcome
            ? undefined
            : boardOutcomeLabel(heroOutcome.name, market.name)
        }
        movement={!isResolved && leader?.probability_change_24h != null ? leader.probability_change_24h * 100 : null}
        // UX-P233 (board item 11): the pill used to render a bare "↓ 71.5 pts"
        // with no window at all, directly above a caption reading "Amazon up 13.5
        // pts from opening" — two true numbers about one outcome, reading as a
        // contradiction. It now says which window it covers. NOT "24h": see
        // `movementWindowLabel` for why the payload disproves that word.
        movementLabel={movementWindowLabel(leader?.last_updated)}
        sourceCount={market.source_count ?? undefined}
        // UX-P054 (#1719) — the third copy of the "Resolves <date>" rule, and the
        // one the authority guard could not see: it named this line as its blind
        // spot because it sits outside `components/` and `lib/`.
        //
        // The year was already right here. What was missing is the authority's
        // past-date rule, so an unresolved market whose scheduled date had gone
        // would assert "Resolves Dec 19, 2025". `resolution_date` is the SCHEDULED
        // resolution, never an observed one, so the page must neither state it as
        // upcoming nor infer settlement from it — it says nothing.
        //
        // REACHABILITY IS UNPROVEN, DELIBERATELY NOT OVERCLAIMED: 8,609 open
        // markets carry a passed date (UX-P053), but 0 were reachable via
        // /api/futures/browse (200 sampled) or /api/events/search (10 queries).
        // This lands for the mechanism — one formatter, no third copy — not on a
        // prevalence claim.
        resolveDate={isResolved ? undefined : formatResolvesLabel(market.resolution_date) || undefined}
        categoryEmoji={getCategoryEmoji(market.llm_sport_category)}
        categoryLabel={market.sport_name || market.llm_sport_category || undefined}
        isMultiOutcome={(market.outcome_count ?? 0) > 2}
        sparklinePoints={ambientPoints}
        resolved={isResolved}
        resolvedWon={gradedChampion !== null}
      />

      {/* L2-65 / B7 L2-91: breadcrumb UP into the richer event-concept surface
          (leaderboard, race chart, matchups), or the competition hub when there's no
          specific concept. */}
      {conceptKey && cardName ? (
        // L2-175 Item 3a: the named card breadcrumb — a fight belongs to its card.
        <Link
          href={eventPath(conceptKey)}
          className="inline-flex items-center gap-1 text-sm font-medium text-accent-brand hover:underline"
        >
          <span aria-hidden="true">←</span>
          {cardName}
          {cardDateLabel ? ` · ${cardDateLabel}` : ""}
        </Link>
      ) : conceptKey && conceptLabel ? (
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

      {/* L2-175 Item 3a: the card's OTHER fights — the sibling rail the card concept
          already carries. Each links to its own fight page (data exists; give the
          hierarchy a home). */}
      {siblingFights.length > 0 && (
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-2">
            Also on this card
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
            {siblingFights.map((f) => (
              <Link
                key={f.market_id}
                href={`/futures/${f.market_id}`}
                className="flex-shrink-0 rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm text-text-primary hover:shadow-card-hover transition-shadow"
              >
                {f.market_name || f.name || "Fight"}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Context line (auto-upgrades when #870 ships) */}
      {market.hook_description && (
        <p className="text-[13px] leading-relaxed text-text-secondary mb-4 max-w-2xl">{market.hook_description}</p>
      )}

      {/* UX-P234 (board item 15): the pin. This used to be a bare word inside a
          container whose own comment read "Legacy hero kept for share/pin actions"
          — scaffolding that shipped. It is now the SAME affordance the Discover
          feed and the card surfaces use (`components/PinButton`), so a pin looks
          like a pin wherever a reader meets one. That comment is retired with the
          thing it described; there is no legacy hero here, only the pin. */}
      <div className="flex items-center gap-3 mb-4">
        <PinButton
          pinned={marketIsPinned}
          onToggle={() => togglePin(marketId)}
          atMax={isMaxReached}
          noun="market"
          variant="labelled"
        />
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
              {priceCadenceNote(isResolved, { long: true })}
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
              {/* #7545 — the rung the reader is on, and one line reconciling it
                  with what came back. This replaces two captions that could only
                  describe a window the reader never chose ("Extended to 30 days
                  for more data"): the chip now says what was asked for, and
                  `rangeCoverageNote` says what arrived when they differ. */}
              <FuturesTrendRangeControls
                className="mt-2"
                range={effectiveRange}
                onSelect={selectRange}
                requestedHours={historyHours}
                actualHours={historyData.actual_hours}
                /* #8135: `sparse` asks how MUCH history there is; `dormant` asks
                   whether any of it is recent. The specimen was sparse, open and
                   four weeks cold, so the old gate returned the live promise over
                   a chart captioned "Last number 29 days ago". */
                cadenceNote={
                  historyData.sparse
                    ? priceCadenceNote(isResolved, {
                        dormant: isCadenceDormant(boardLastObservationMs),
                      })
                    : null
                }
              />
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
            // #4259: "fixed 0-100%" above was the bug for the FIELD case. This page
            // plots many-outcome markets (championship/award) whose leader sits in
            // single digits, so every line drew on the floor. `fieldCeiling` steps the
            // top down the #2451 ladder — zero stays the floor, the labels state the
            // top. A binary market, and a resolved one whose winner is at 100%, both
            // land back on the 1.0 rung untouched. See lib/chartCeiling.ts.
            // #7813: the ONE call site that passes a board name, for the same
            // reason the hero and the All Outcomes rows take one (#6765) — this
            // page's `<h1>` is the board's name, so a legend entry that repeats
            // it wraps to two lines to say `Set 1 Winner`. The chart's other
            // seven call sites pass nothing and are byte-identical; the rule is
            // a property of THIS page, not of the names.
            <FuturesChart
              historyData={historyOutcomes}
              selectedOutcomes={selectedOutcomes}
              onToggleOutcome={toggleOutcomeSelection}
              stepInterpolation={historyData.sparse}
              fixedYAxis
              fieldCeiling
              settled={isResolved}
              marketName={market?.name}
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
          {isResolved && resolvedFeatured && (
            <p className="text-[13px] leading-relaxed text-text-secondary mt-3">
              {/* #6301 — the caption's own verdict comes from the grade, never from
                  the featured row. Unchanged in behaviour (it already tested
                  `is_winner`); it now asks the same helper as the hero above it so
                  the two can never drift into naming different champions. */}
              {/* #6765 — the market name is passed here for the same reason it is
                  passed to the hero three hundred lines up: this sentence sits on
                  the board whose `<h1>` already asked the question, so "Settled —
                  Korea Open: A vs B Set 1 O/U 9.5 won." is the title again plus
                  four words. The helper refuses every shape it cannot shorten, so
                  a normal champion's name reaches this sentence untouched. */}
              Settled{gradedChampion ? ` — ${boardOutcomeLabel(gradedChampion.name, market?.name)} won.` : "."}
            </p>
          )}
        </div>
      )}

      {/* Honest empty/sparse state: market loaded but no usable price history.
          Never render a broken/degenerate chart — say so plainly. (#883 L2-49) */}
      {/* #7545 — WHICH emptiness this is, and a way out of it. See
          FuturesTrendEmptyState: once the reader picks the window, an empty
          payload no longer means "this market has no history". */}
      {!historyLoading && !historyError && historyOutcomes.length === 0 && (
        <FuturesTrendEmptyState
          range={effectiveRange}
          onSelect={selectRange}
          requestedHours={historyHours}
          actualHours={historyData?.actual_hours}
          createdAt={market?.created_at}
        />
      )}

      {/* Threshold ladder — one question, many rungs, heat-strip.
          QuantityGroup (Queue L2-118) replaced the old ThresholdGrid: a "≥ N"
          market is one continuous question, not N yes/no cards. */}
      {/* #7398 — the map key is a SCOPE KEY, and it used to be handed straight
          to `title`: `# OR BELOW` over the 20-rung Treasury board, `ABOVE #`
          over the Strait of Hormuz. `thresholdLadderTitle` refuses any scope
          key as a heading and prints the payload's own `group_title` only when
          it says something this page's `<h1>` does not. */}
      {/* #8019 — and when BOTH are refused the rungs name their own subject.
          This board draws one ladder per NFL team and every rung reads `≥ N`,
          so without the fourth argument the reader meets 32 unlabelled stacks,
          two of them identical. The outcome names are the only place the team
          survives. */}
      {/* #8167 — a SPREAD board writes the same fact without a colon ("Atlanta
          wins by over 2.5 runs"), so #8019's separator rule finds nothing and
          the two sides drew as identical unlabelled stacks. The headings are
          decided for the whole page at once because what distinguishes these
          cards is the words their siblings do NOT share — see
          `thresholdLadderTitles`. Each card is still decided on its own first. */}
      {thresholdEntries.map(([stem, outcomes], i) => (
        <QuantityGroup
          key={stem}
          title={thresholdLadderHeadings[i]}
          rungs={buildThresholdRungs(outcomes)}
        />
      ))}

      {/* Q478 — the same ladder for a market whose OWN outcomes are the rungs.
          Rungs already carry their final position in `value`, so QuantityGroup's
          sort is a no-op over them rather than a second opinion. */}
      {/* Q481 — the title is no longer a ternary on `isResolved`. `hasOwnLadder` is
          false for every resolved market, so the "Final Results" arm was dead code
          that read, to anyone scanning this file, as a settled path the ladder
          handles. It never handled one — that is what CERT-605 blocked. A ladder
          here always describes a live question. */}
      {/* D102 / #4568 — the SECOND renderer of this page's outcome set, and the
          one #4568's own specimens sit on. `108555` (Starlink) drew three bare
          `-` rungs at the foot of its ladder while `114175` drew five in the
          ranked table below; the two paths are chosen by market SHAPE, so a fix
          to either one alone leaves the issue live on half its evidence.
          `partitionOutcomesByPrice` is the same rule both call — notice 35's
          one-family rule, and ux/1316's lesson that a rule landing on one of two
          renderers is the defect, not the fix. */}
      {hasOwnLadder && (
        <>
          {pricedRungs.length > 0 && (
            /* #7785 — and the ladder carries the SAME freshness line as the
               ranked table. `marketAsOf` used to render only in the
               `!hasOwnLadder` branch below, so a quantity-shaped board had no
               as-of anywhere on the page: measured on the served payloads of
               the 199 busiest open tier-1/2 boards, 8 of the 59 ladder-shaped
               ones draw prices 2 to 159 days old with nothing saying so. (The
               oldest of those are ALSO drawing rungs whose dates have passed —
               a backend-owned defect, #7784, which this does not fix and does
               not hide.) `hint` is QuantityGroup's existing header slot and
               defaults to `undefined` on a non-interactive group, which this
               one is, so no other caller of the component changes. */
            <QuantityGroup
              title="All Outcomes"
              rungs={pricedRungs}
              hint={marketAsOf ?? undefined}
              wideLabels={ladderNeedsWideLabels(pricedRungs)}
            />
          )}
          {numberlessRungs.length > 0 && (
            <details data-testid="futures-more-rungs" className="px-6">
              <summary className="cursor-pointer select-none py-1 text-[11px] text-text-muted">
                More outcomes ({numberlessRungs.length})
              </summary>
              {/* Titleless: the disclosure's own summary is the heading. */}
              <QuantityGroup
                rungs={numberlessRungs}
                wideLabels={ladderNeedsWideLabels(numberlessRungs)}
              />
            </details>
          )}
        </>
      )}

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
      <GamesThisWeek events={relatedEvents} />

      {/* More from this category */}
      {market?.llm_sport_category && (
        <RelatedByTag
          tags={[`sport:${market.llm_sport_category}`]}
          excludeId={market.id}
          excludeType="futures"
          limit={4}
          title={`More ${toTitleCaseAcronymSafe(market.llm_sport_category)}`}
        />
      )}

      {/* #883 blend-only: per-source SourceAggregationBlock removed — the blend
          is the product; source divergence is an upstream data-quality bug, not a
          surface to expose. Users see ONE clean number. */}

      {/* All Outcomes Table — suppressed when the quantity ladder above already
          rendered these same outcomes. Two renders of one outcome set is how the
          ladder reads as "extra" instead of as the answer, and the ranked table is
          the wrong one: it prints rank badges and initial avatars over rungs. */}
      {!hasOwnLadder && (
      <div className="bg-surface-card rounded-card shadow-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-title-3 font-semibold text-text-primary flex items-center gap-2">
            <span>📊</span>
            {isResolved ? "Final Results" : "All Outcomes"}
            {/* UX-P233 (board item 11): ONE as-of for the whole table, so every
                number under it is interpretable without repeating a date on all
                eight rows. Absent entirely when the prices are genuinely fresh —
                a label on a current price is noise, not honesty. #7785: read
                from the OLDEST of the rows drawn below, not from the leader —
                see `marketAsOf`. */}
            {/* #6989: and absent when NO row prints a number. The date is read
                from the leader, and on an all-withheld market the leader is a
                withheld leg — so this was dating prices the reader cannot see. */}
            {!isResolved && marketAsOf && !noPricesNote && (
              <span
                data-testid="market-as-of"
                className="text-xs font-normal text-text-muted"
              >
                {marketAsOf}
              </span>
            )}
          </h2>
          {pricedOutcomes.length > 25 && (
            <button
              onClick={() => setShowAllOutcomes(!showAllOutcomes)}
              className="text-sm text-text-secondary hover:text-text-primary transition-colors"
            >
              {showAllOutcomes
                ? "Show less"
                : `Show all ${pricedOutcomes.length}`}
            </button>
          )}
        </div>

        {/* lane1-Q479 (defect 13): a ranked list of rows each showing a percent is
            the geometry of a race, and a reader adds up a race. When the SOURCE has
            told us the set is NOT one — Kalshi's event `mutually_exclusive`, already
            on this payload and already read by the backend — the page has to say so,
            because on 109441 the honest answer to "why don't these eight add to 100?"
            is "they were never meant to".
            Only a positive denial prints: the column defaults to TRUE, so `true`
            and absent are both silence rather than the opposite claim.
            CERT-609: and only Kalshi's denial is positive. Polymarket's `neg_risk`
            parser turns an ABSENT `negRisk` key into `false`, so its `false` is
            absence wearing evidence's clothes — see `lib/outcomeExclusivity.ts`.
            Never a renormalisation — the source says independent, and dividing by
            the sibling sum would invent the exclusivity it denies. */}
        {independenceNote && (
          <p
            data-testid="independent-outcomes-note"
            className="text-sm text-text-secondary mb-4"
          >
            {independenceNote}
          </p>
        )}

        {/* #6989 — the honest line, printed once, in place of the sort chips.
            "No outcomes" is not what this says and not what is true: the rows
            exist and are one tap away below; it is their PRICES that are not
            here. */}
        {noPricesNote && (
          <p
            data-testid="futures-no-priced-outcomes"
            className="text-sm text-text-secondary"
          >
            {noPricesNote}
          </p>
        )}

        {/* Sort controls — #6989: three chips that reorder an empty list are a
            control panel with nothing behind it. Suppressed, not disabled: a
            greyed chip still invites the tap. */}
        {!noPricesNote && (
        <div data-testid="futures-sort-controls" className="flex gap-2 mb-4 flex-wrap">
          <SortButton
            label="Probability"
            field="probability"
            currentField={sortField}
            direction={sortDirection}
            onClick={() => toggleSort("probability")}
          />
          <SortButton
            // UX-P233: was "24h Change". It sorts `probability_change_24h`, which
            // CAL-P159 proved is a per-write delta that freezes — every row on
            // 109441 is dated 2026-08-28. A control that names a window the data
            // does not have is the same false claim as the badge beside it.
            label="Last move"
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
        )}

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
              rendered={renderedById.get(outcome.id)?.current ?? null}
              renderedOpening={renderedById.get(outcome.id)?.opening ?? null}
              showLastMove={showLastMove}
              showEntityImage={showEntityImage}
            />
          ))}
        </div>

        {/* Show more button */}
        {!showAllOutcomes && pricedOutcomes.length > 25 && (
          <button
            onClick={() => setShowAllOutcomes(true)}
            className="w-full mt-4 py-2 text-sm text-text-secondary hover:text-text-primary border border-surface-border rounded-lg hover:bg-charcoal/5 transition-colors"
          >
            Show {pricedOutcomes.length - 25} more outcomes
          </button>
        )}

        {/* D102 / #4568 — the numberless rows, collapsed but never dropped
            (gotcha #43). The markup is `ScriptFold`'s from the props twin
            deliberately: notice 35 says a second problem of the same shape does
            not get a second component, and this is the same disclosure with the
            same neutral D111 label. Closed it costs one row of height and names
            its own count; open it shows every folded outcome in the normal row
            presentation, keeping its served `rank` so the numbering a reader saw
            never restarts at 1. */}
        {unpricedOutcomes.length > 0 && (
          <details data-testid="futures-more-outcomes" className="mt-4">
            <summary className="cursor-pointer select-none py-1 text-[11px] text-text-muted">
              More outcomes ({unpricedOutcomes.length})
            </summary>
            <div className="mt-1 space-y-2">
              {unpricedOutcomes.map((outcome, index) => (
                <OutcomeRow
                  key={outcome.id}
                  outcome={outcome}
                  rank={outcome.rank ?? pricedOutcomes.length + index + 1}
                  isLeader={false}
                  isSelected={selectedOutcomes.has(outcome.id)}
                  onToggleSelect={() => toggleOutcomeSelection(outcome.id)}
                  hasHistory={historyOutcomes.some(
                    (h) => h.outcome_id === outcome.id
                  )}
                  marketCategory={market?.llm_sport_category}
                  marketName={market?.name}
                  isResolved={isResolved}
                  rendered={renderedById.get(outcome.id)?.current ?? null}
                  renderedOpening={renderedById.get(outcome.id)?.opening ?? null}
                  showLastMove={showLastMove}
                  showEntityImage={showEntityImage}
                />
              ))}
            </div>
          </details>
        )}
      </div>
      )}
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

