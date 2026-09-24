"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { fetchEvent, fetchEventHistory, fetchGameMarkets, fetchTeamProgression, fetchEventTournament, formatProbability } from "@/lib/api";
import type { EventTournamentResponse, TeamProgressionResponse } from "@/lib/types";
import { EVENT_BOOT_HISTORY_HOURS } from "@/lib/event/detailBoot";
import {
  EVENT_SLOW_LOAD_NOTICE_MS,
  eventLoadingView,
} from "@/lib/event/loadingPresentation";
import {
  effectiveChartRange,
  historyRangeParam,
  nextFullHistoryLatch,
} from "@/lib/event/historyRange";
import { canonicalEventHref } from "@/lib/canonicalEventUrl";
import { withoutEventOwnMoneyline } from "@/lib/eventOwnMoneyline";
import { teamTextColor } from "@/lib/teamColors";
import { useLiveEventStream } from "@/hooks/useLiveEventStream";
import { mergeLiveChartHistory } from "@/lib/liveChartHistory";
import FreshnessChip from "@/components/event/FreshnessChip";
import {
  applyLiveFrame,
  eventFeedIsStalled,
  makeEventRefreshInterval,
  pageLiveClaimIsUnbacked,
} from "@/lib/eventLivePush";
import LiveAgeStamp, { heroStampIsStale } from "@/components/event/LiveAgeStamp";
import { heroFreshness } from "@/lib/event/heroFreshness";
import LiveSparkline from "@/components/event/LiveSparkline";
import {
  eventTournamentKey,
  isTournamentSportKey,
  resolveEventOutcome,
  liveHeroGamesLine,
} from "@/lib/eventOutcome";
import SettledOutcomeHero from "@/components/event/SettledOutcomeHero";
const ChartSkeleton = () => <div className="animate-pulse h-48 bg-surface-card rounded-xl" />;
const OddsChart = dynamic(() => import("@/components/OddsChart"), { ssr: false, loading: ChartSkeleton });
const ScoreDifferentialChart = dynamic(() => import("@/components/ScoreDifferentialChart"), { ssr: false, loading: ChartSkeleton });
const BookmakerTable = dynamic(() => import("@/components/BookmakerTable"), { ssr: false });
const RelatedFutures = dynamic(() => import("@/components/RelatedFutures"), { ssr: false });
const GamePlayCard = dynamic(() => import("@/components/GamePlayCard"), { ssr: false });
const SeriesProbability = dynamic(() => import("@/components/SeriesProbability"), { ssr: false });
const TotalPointsSpectrum = dynamic(() => import("@/components/TotalPointsSpectrum"), { ssr: false });
const PlayerPropsDashboard = dynamic(() => import("@/components/PlayerPropsDashboard"), { ssr: false, loading: ChartSkeleton });
// UX-P098: the rail LEADS the props body, so it is a static import — a dynamic
// one would paint a skeleton in the one slot the page is supposed to answer first.
import PropDivergenceRail from "@/components/PropDivergenceRail";
const SpecialEventMarkets = dynamic(() => import("@/components/SpecialEventMarkets"), { ssr: false });
const MarketMapSection = dynamic(() => import("@/components/MarketMapSection"), { ssr: false, loading: ChartSkeleton });
// UX-P152: the tournament's sections OF this page. Dynamic and below the fold —
// 94 events on the whole site render it and none of them should pay for it in
// the initial bundle.
const TournamentExtensions = dynamic(() => import("@/components/event/TournamentExtensions"), { ssr: false });
/* #2448: the way back UP the container. Same SWR key as the sections below, so
   the two are one request. Renders nothing off-tournament. */
const TournamentBackLink = dynamic(
  () => import("@/components/event/TournamentExtensions").then((m) => m.TournamentBackLink),
  { ssr: false }
);
/* #2447: the register's censused player photo, at the FRONT of the hero's
   existing team-logo ladder. Same SWR key again, so still one request.
   NOT `dynamic`, unlike its two neighbours above: this component WRAPS the
   hero's existing logo markup as its fallback, so lazy-loading it would blank
   the avatar of every event on the site until the chunk arrived. The two
   sections below are additive and can afford to appear late; a hero cannot. */
import {
  TournamentPlayerFace,
  servedParticipantImage,
} from "@/components/event/TournamentExtensions";
// L2-118 Phase 1: the archetype-agnostic props body (SCRIPT / DIVERGENCE / WHAT HIT).
const PropsSection = dynamic(() => import("@/components/event/PropsSection"), { ssr: false });
import type { PropMark } from "@/components/event/PropsSection";
import { indexPropRowsByScriptKey, verifyScriptGrade } from "@/lib/propGrade";
import { isChildTitleMark } from "@/lib/propFamily";
import { countOf } from "@/lib/plural";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorBoundary from "@/components/ErrorBoundary";
import SectionErrorBoundary from "@/components/SectionErrorBoundary";
import ErrorMessage from "@/components/ErrorMessage";
import { describeLoadFailure } from "@/lib/loadFailure";
import Tooltip from "@/components/Tooltip";
import RelatedByTag from "@/components/RelatedByTag";
import { getLeagueDisplay } from "@/lib/sportCategories";
import { relatedRailQuery } from "@/lib/relatedRailQuery";
import { participantNames } from "@/lib/railParticipantOrder";
import {
  completedSetsForTennis,
  decidedSetsWinnerFor,
  tennisSetsWonFor,
} from "@/lib/otherMarketGroups";
import { sportVocab, marketMapSectionMounts, totalsMapRenders } from "@/lib/marketMapUtils";
import { awayIsTheComplement, printableAway, sportPricesADraw } from "@/lib/drawPricedWinner";
import {
  actualScoreSeriesDrawn,
  scoreDifferentialHeading,
} from "@/lib/scoreDifferentialHeading";
import { espnTeamLogoByName } from "@/lib/images";
import {
  useAnalytics,
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
  usePinnedEvents,
} from "@/hooks";
import { isCloseGame, calculateMinutesToStart } from "@/lib/analytics";
import { isPregameStatus } from "@/lib/settledQuote";
import { derivePeriodBoundaries } from "@/lib/periodMarkers";
import { formatLiveClockLabel } from "@/lib/gameTimeLabel";
import {
  SUSPENDED_DESCRIPTION,
  VENUE_SETTLED_DESCRIPTION,
  blendCaptionIsStale,
  hasNoReportedResult,
  isFinishedStatus,
  startBadgeLabel,
  suspendedSummary,
  venueSettledSummary,
} from "@/lib/eventState";
import type { ActiveChartPoint } from "@/lib/types";
import TeamNameLink from "@/components/TeamNameLink";
import { PinIcon } from "@/components/PinButton";
import { teamShortNames, shippableCrestBadge } from "@/lib/teamShortName";
import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import { SignalBars } from "@/components/discover/shared";
import { confidenceFromSources, countProbabilitySources } from "@/lib/confidence";
import { pinChartEdgeToHero } from "@/lib/chartEdgePin";
import {
  SPORT_KEY_TO_LEAGUE_PATH,
  hasAnyWinProbData,
  formatCountdown,
  shouldShowRefreshCountdown,
  headerShowsAge,
  startClockState,
  formatEventStartLabel,
  resolveProbability,
  computeSharedChartDomain,
  computeLastChartPoint,
  defaultChartTimeRange,
} from "@/lib/eventKeyStats";
import { renderedPercent } from "@/lib/renderedPercent";

interface EventPageProps {
  params: { id: string };
}

const LIVE_REFRESH_INTERVAL = 32000; // Match backend LIVE_POLL_INTERVAL (32s)
const SCHEDULED_REFRESH_INTERVAL = 120000;

export default function EventPage({ params }: EventPageProps) {
  const eventId = parseInt(params.id, 10);
  const searchParams = useSearchParams();
  const sharedSource = searchParams.get("utm_source");
  const sharedMedium = searchParams.get("utm_medium") || undefined;
  const sharedCampaign = searchParams.get("utm_campaign") || undefined;
  const isSharedLink = sharedSource === "share";
  const [countdown, setCountdown] = useState<number>(0);
  const [gameCountdown, setGameCountdown] = useState<string>("");
  const [lastRefresh, setLastRefresh] = useState<number>(Date.now());
  const hasTrackedDetailView = useRef(false);
  const hasTrackedSharedOpen = useRef(false);
  const [activeChartPoint, setActiveChartPoint] = useState<ActiveChartPoint | null>(null);
  const [oddsChartDomain, setOddsChartDomain] = useState<{ start: string; end: string } | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [chartTimeRange, setChartTimeRange] = useState<"all" | "live">("live");
  // Once the reader picks a range it is theirs — the evidence sync below stops.
  const [chartRangeUserSet, setChartRangeUserSet] = useState(false);
  const handleChartTimeRangeChange = useCallback((range: "all" | "live") => {
    setChartRangeUserSet(true);
    setChartTimeRange(range);
  }, []);
  const handleRenderedDomain = useCallback((start: string, end: string) => {
    setOddsChartDomain((prev) => {
      if (prev && prev.start === start && prev.end === end) return prev;
      return { start, end };
    });
  }, []);

  // Analytics
  const { track, trackNavigationClick, recordEvent } = useAnalytics();

  // Pinned events
  const { isPinned, togglePin, isMaxReached } = usePinnedEvents();
  const eventIsPinned = isPinned(eventId);

  // live/034 S2 — see the `refreshInterval` note below. Declared here because
  // the SWR config closes over it and the hook that sets it needs `event`.
  const streamConnectedRef = useRef(false);

  // #7621 — ONE callback for the life of the mount, and that is the whole fix.
  //
  // This used to be an inline arrow in the config below. swr keeps
  // `refreshInterval` in its polling effect's DEPENDENCY ARRAY and clears the
  // pending timeout on cleanup, so a new identity each render restarted the
  // timer from zero — and this page re-renders about once a second for its
  // countdown ring, so the 120s poll never survived to fire. Measured on
  // production: 3 event fetches in 480s, all three of them the stream-disconnect
  // handler below, against 30 sibling fetches on the same page. See
  // `makeEventRefreshInterval` for the swr source and the full measurement.
  //
  // `useMemo` with an EMPTY dependency list is correct rather than lazy here:
  // the callback closes over nothing reactive (status arrives as swr's argument,
  // liveness through the ref, the cadences are module constants), which is the
  // precondition the factory documents.
  const eventPollInterval = useMemo(
    () => makeEventRefreshInterval(streamConnectedRef, {
      live: LIVE_REFRESH_INTERVAL,
      scheduled: SCHEDULED_REFRESH_INTERVAL,
    }),
    [],
  );

  const {
    data: event,
    error: eventError,
    isLoading: eventLoading,
    mutate: refreshEvent,
  } = useSWR(
    ["event", eventId],
    () => fetchEvent(eventId),
    {
      // live/034 S2 — when the SSE stream is delivering, the 32s poll stands
      // down. That is the ship: the same number, arriving instead of being
      // waited for. The instant the stream stops delivering — errored, refused,
      // closed, or silently dead — `streamConnected` goes false and the 32s
      // poll comes straight back. A push path that dies must degrade to
      // polling, never to a frozen number.
      //
      // CERT-1994: "stands down" is not "stops". It used to be 0, and a frame
      // carries ONE probability, so every other field on a page somebody left
      // open was frozen at first fetch — including the tennis games line and the
      // `observed_at` its freshness chip counts from, which the server
      // re-confirms every ~10 minutes. The chip then said `Stale · 40m ago`
      // about a number re-confirmed a minute earlier: the honesty mechanism
      // itself lying, which is worse than the staleness it exists to disclose.
      // See `eventRefreshInterval` for why the pushed cadence is 120s and not a
      // taste — it is derived from the chip's own stale threshold.
      //
      // Read through a REF, not the state value: `streamConnected` is derived
      // from `event`, which is what this very call produces, so naming it here
      // would be a use-before-declare. The ref is written just after the hook
      // below, and SWR only ever invokes this after a render has completed.
      // #7621: a STABLE reference, built above. Inlining the arrow here again
      // is the bug — see the note on `eventPollInterval`.
      refreshInterval: eventPollInterval,
      onSuccess: () => setLastRefresh(Date.now()),
    }
  );

  // ── Q050: this url named a duplicate, so correct the url ─────────────────
  //
  // `/api/events/{id}` now answers a market-born duplicate with the row it
  // duplicates (ruling 048's drain clause, read side), so `event.id` can come
  // back different from the id in the path. Rendering the canonical event under
  // the ghost's id would be half a fix and a worse-looking one: every sibling
  // fetch on this page — history, game markets, tournament, team progression —
  // is keyed on `eventId` from the ROUTE, so the reader would get a FINAL hero
  // above an empty chart and no markets. Moving the url moves all of them.
  //
  // `replace`, not `push`: the ghost url is not a place anyone chose to be, and
  // leaving it in history would make Back a no-op that lands here again. The
  // query string rides along so a shared link keeps its `utm_*` attribution.
  const router = useRouter();
  const canonicalEventId = event?.id;
  const canonicalHref = canonicalEventHref(
    eventId,
    canonicalEventId,
    searchParams.toString(),
  );
  useEffect(() => {
    if (!canonicalHref) return;
    router.replace(canonicalHref);
  }, [canonicalHref, router]);

  // Check if the game has actually started (commence_time is in the past)
  const hasStarted = event?.commence_time
    ? new Date(event.commence_time).getTime() <= Date.now()
    : false;

  // Only consider "live" if the status is "live" AND the game has actually started
  // This guards against cases where the backend status might be incorrect
  const isLive = event?.status === "live" && hasStarted;
  const isFinished = isFinishedStatus(event?.status);
  // live/048 — non-terminal, and it must not fall through to either branch:
  // not Final (nothing reported a result) and not upcoming (it already began).
  //
  // #3211 widens it from the literal status to the DISPLAY question, and this
  // page is where that matters most: it is the destination of every card the
  // league and team rails newly surface, and until now a `scheduled` row hours
  // past its own kickoff arrived here as "Pregame" **with a running countdown
  // to a moment in the past**. The two consumers below (the countdown
  // suppression and the hero badge) are the ones live/048 wrote for exactly
  // this shape of lie; they need the widened predicate, not a second branch.
  // #5459 declares these three below, after `freshestSourceStamp`, because the
  // page's answer to "is this live" now depends on how old its own number is.
  const refreshInterval = isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL;

  // ── live/034 S2 — SSE push ────────────────────────────────────────────────
  // Live events only, per the ruling; everything else keeps polling. The number
  // in the database was already live (worker-ws flushes every 2s, the blend is
  // stamped at most once per event per 5s) — it was the 32s poll that made it
  // look stale on screen.
  const { frame: liveFrame, connected: streamConnected, chartPoints } = useLiveEventStream(
    eventId,
    isLive,
  );
  streamConnectedRef.current = streamConnected;

  // Apply a pushed frame to the SWR cache rather than holding it in a local
  // override. One source of truth: the stream writes the same cache the poller
  // writes, so the hero, the sources rail and every other consumer stay
  // consistent and nothing downstream needs to know push exists.
  useEffect(() => {
    if (!liveFrame || liveFrame.p === null || liveFrame.p === undefined) return;
    const frame = { ...liveFrame, p: liveFrame.p };
    refreshEvent(
      // `applyLiveFrame` spreads `prev` FIRST and then only the fields a frame
      // speaks for, so a frame arriving after the background poll carries the
      // newer games line forward instead of reverting it (CERT-1994).
      (prev) => applyLiveFrame(prev, frame),
      // No revalidate: the frame IS the new value. Refetching here would put a
      // request on every tick and undo the point of pushing.
      { revalidate: false },
    );
    setLastRefresh(Date.now());
  }, [liveFrame, refreshEvent]);

  // The freshest write across all sources — what the age stamp counts from.
  // MAX, not the pushed frame's own stamp: the hero is a blend, and its age is
  // the age of the most recent thing that went into it. Reading only the source
  // that last moved would make the number look stale whenever a quiet feed
  // happened to be the one to tick.
  const freshestSourceStamp = useMemo(() => {
    const stamps = Object.values(event?.win_probability_sources ?? {})
      .map((s) => s?.updated_at)
      .filter((s): s is string => typeof s === "string" && !Number.isNaN(Date.parse(s)));
    if (stamps.length === 0) return null;
    return stamps.reduce((a, b) => (Date.parse(a) >= Date.parse(b) ? a : b));
  }, [event?.win_probability_sources]);

  // ── #5459 / #5077 — THE PAGE STOPS PROMISING LIVENESS IT CANNOT BACK ───────
  //
  // On Jeanjean v Liu (production, 2026-09-12) this header carried a LIVE chip,
  // a 20s ticker, a second 20s beside the chart — and its own age badge reading
  // a grey `146m ago`, over a hero of 1% – 99% with no score and a chart flat
  // for three hours. The reasoning, both disqualifiers and the measured reach of
  // each live in `liveClaimIsUnbacked`; this is only the wiring.
  //
  // Read during render rather than held in state: `countdown` already re-renders
  // this component once a second, so the age is re-derived on the same tick the
  // chrome is drawn from and there is no second timer to fall out of step with
  // the first — the same argument `feedStalled` below is written to.
  //
  // #5885 — AND ONLY ONCE THE GAME HAS STARTED. A claim of liveness cannot be
  // unbacked on a page that has not made one.
  //
  // Without `hasStarted` this fires on any PREGAME page whose freshest source
  // write is over the hour, and through `isSuspended` below it prints "No result
  // reported" on a game that has not kicked off. Measured on production
  // 2026-09-13 10:09Z: /events/14780147, Chargers–Cardinals, `status
  // "scheduled"`, kickoff 20:25Z — ten hours out — with kalshi 08:52:40Z,
  // betting 09:06:12Z and polymarket 09:08:03Z, so a 61-minute blend and the
  // suspended badge on a hero that had read "Starts in 10h 34m" twenty minutes
  // earlier. It also silently deleted `Projected final: 28 – 19`, which
  // `isSuspended` gates under #5257.
  //
  // The 60-minute bound is not wrong, it was being asked the wrong question:
  // `LIVE_CLAIM_MAX_BLEND_AGE_MS` reasons explicitly about a live game ("an NFL
  // game on a two-minute beat never comes within thirty times of this one"),
  // and a pregame market is polled on a slow cadence by design, so an hour-old
  // blend hours before kickoff is the ordinary state rather than evidence of
  // anything going dark.
  //
  // Composed inside `pageLiveClaimIsUnbacked` rather than spelled here as
  // `hasStarted && …`: a Next.js page carries no named exports, so an inline
  // conjunction is a decision no test can hold. `liveClaimIsUnbacked` stays
  // keyed on the blend alone, the way `hasNoReportedResult` stays keyed on
  // status and time alone, and this page keeps ONE answer for its four
  // consumers of the flag.
  const liveClaimUnbacked = pageLiveClaimIsUnbacked({
    hasStarted,
    pinned: event?.live_probability_pinned,
    blendAgeMs: freshestSourceStamp
      ? Date.now() - Date.parse(freshestSourceStamp)
      : null,
  });

  // Everything on this page that ASSERTS motion reads this, so there is exactly
  // one answer: the pulsing phase badge, the header's ring and the `isLive` the
  // charts are handed. (The two `{countdown}s` tickers it once gated are gone —
  // #8336 left the header age badge as the page's one freshness answer.) #4861 dropped the
  // header's countdown group on a stalled feed and left those behind, which is
  // why Jeanjean v Liu still said LIVE in three places.
  const effectivelyLive = isLive && !liveClaimUnbacked;

  // THE PAGE'S ONE `hasNoReportedResult` ANSWER (#4015), and #5459 widens it
  // rather than adding a second predicate beside it.
  //
  // A pinned live match IS this state, in the exact words `SUSPENDED_LABEL` was
  // chosen for — *this match should have happened and nobody has told us
  // anything*. It is also the only honest destination for the phase badge:
  // `effectivelyLive` alone would drop it through to "Pregame" on a match hours
  // past its own kickoff, which is #3211's lie told in the other direction.
  //
  // Widened HERE and not inside `hasNoReportedResult`, which is shared card
  // vocabulary keyed on status and time alone and must stay that way — a page
  // payload field has no business in it. Widened rather than forked because
  // #4015 exists precisely so the hero badge, the games map (`noResultReported`)
  // and the projected-final suppression cannot answer this question three ways.
  const isSuspended =
    hasNoReportedResult(event?.status, event?.commence_time) || liveClaimUnbacked;

  // #6381 — WHAT THAT STATE SAYS, when a source that carried this match's
  // markets has already graded it. Null on every other row, so the badge keeps the sentence
  // it had.
  //
  // Computed BESIDE `isSuspended` and not inside it: the flag's other four
  // consumers (the suppressed countdown, the suppressed projected final, the
  // map's past-tense marks, the withdrawn age stamp) are all still right about
  // a venue-settled match — it has no forecast left and no update to promise —
  // and flipping the flag to move one sentence would quietly un-suppress them.
  // Only the words were wrong. The page keeps its ONE `hasNoReportedResult`
  // answer (#4015) and gains one string derived from it.
  const venueSettledSentence = isSuspended
    ? venueSettledSummary(event?.venue_settled, event?.venue_settled_result)
    : null;

  // When the stream stops delivering, refetch ONCE. This does two jobs: it
  // settles the page on a number that came from the database rather than the
  // last frame we happened to receive, and it restarts SWR's polling chain,
  // which a `refreshInterval` of 0 had halted.
  const wasStreamConnected = useRef(false);
  useEffect(() => {
    if (wasStreamConnected.current && !streamConnected) {
      refreshEvent();
    }
    wasStreamConnected.current = streamConnected;
  }, [streamConnected, refreshEvent]);

  // UX-P051 (#1710) — which of ESPN's two clock fields the phase badge may
  // believe. `espn.period` is ESPN's status detail, and while ESPN still has the
  // game as scheduled that detail is a sentence ("Mon, August 10th at 8:00 PM
  // EDT") shipped with `game_clock: "0.0"` — both untrustworthy together.
  const liveClockLabel = formatLiveClockLabel(event?.espn?.period, event?.espn?.game_clock, " · ");

  // Track page view with event-specific parameters
  usePageTracking({
    pageType: 'event_detail',
    pageTitle: event ? `${event.home_team} vs ${event.away_team} - Bain Luck` : 'Event - Bain Luck',
    additionalParams: event ? {
      event_id: event.id,
      sport: event.sport || undefined,
      league: event.sport || undefined,
      event_status: event.status,
    } : {},
    deps: [event?.id],
  });

  // Track scroll depth
  useScrollDepth({
    pageType: 'event_detail',
    eventId: event?.id,
    enabled: !!event,
  });

  // Track engagement time
  useEngagementTime({
    pageType: 'event_detail',
    eventId: event?.id,
    enabled: !!event,
  });

  // Track event detail view (once per page load)
  useEffect(() => {
    if (event && !hasTrackedDetailView.current) {
      hasTrackedDetailView.current = true;

      // Check staleness for analytics (not shown to user)
      const now = new Date();
      const commenceTime = new Date(event.commence_time);
      const hoursSinceStart = (now.getTime() - commenceTime.getTime()) / (1000 * 60 * 60);
      const isNeedsReview = event.status === "live" && hoursSinceStart > 4;

      let isStale = false;
      if (event.current_odds?.captured_at) {
        const lastUpdate = new Date(event.current_odds.captured_at);
        const minutesSinceUpdate = (now.getTime() - lastUpdate.getTime()) / (1000 * 60);
        isStale = minutesSinceUpdate > 30;
      }

      track('event_detail_view', {
        event_id: event.id,
        sport: event.sport || 'unknown',
        league: event.sport || 'unknown',
        home_team: event.home_team,
        away_team: event.away_team,
        status: event.status,
        home_probability: event.current_odds?.home_probability ?? null,
        away_probability: event.current_odds?.away_probability ?? null,
        is_close_game: isCloseGame(event.current_odds?.home_probability),
        is_live: event.status === 'live',
        is_stale: isStale,
        is_needs_review: isNeedsReview,
        bookmaker_count: event.current_odds?.bookmaker_count ?? event.bookmaker_odds?.length ?? 0,
        minutes_to_start: calculateMinutesToStart(event.commence_time),
        entry_method: document.referrer.includes(window.location.hostname) ? 'card_click' : 'direct',
      });

      // Record for session stats
      recordEvent(event.id, event.sport || undefined);
    }
  }, [event, track, recordEvent]);

  useEffect(() => {
    if (event && isSharedLink && !hasTrackedSharedOpen.current) {
      hasTrackedSharedOpen.current = true;
      track("shared_link_open", {
        content_type: "event",
        item_id: event.id,
        source: sharedSource,
        medium: sharedMedium,
        campaign: sharedCampaign,
      });
    }
  }, [event, isSharedLink, sharedCampaign, sharedMedium, sharedSource, track]);

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Date.now() - lastRefresh;
      const remaining = refreshInterval - (elapsed % refreshInterval);
      setCountdown(Math.ceil(remaining / 1000));
    }, 100);
    return () => clearInterval(interval);
  }, [lastRefresh, refreshInterval]);

  // #2443 — the container the event belongs to, which for a registered
  // tournament carries the decided result the hero needs to name a winner.
  //
  // The SAME key `TournamentExtensions` uses, so this is one request between
  // the two of them and not two; the hero simply needs it resolved above the
  // fold rather than when a lazy section below the chart mounts. Gated on the
  // shared sport-key test, so no event outside a tournament sport asks.
  //
  // HOISTED ABOVE THE COUNTDOWN EFFECT BY #3829, which reads `start_is_tbd` off
  // it — a countdown to a time the authority has not published should never be
  // computed, not merely hidden after the fact.
  const { data: eventTournament } = useSWR<EventTournamentResponse>(
    isTournamentSportKey(event?.sport) ? eventTournamentKey(eventId) : null,
    () => fetchEventTournament(eventId),
    { revalidateOnFocus: false, refreshInterval: 120000 },
  );

  // ── IS THIS EVENT'S START TIME A REAL ONE? (#3829) ──
  //
  // The rule, the three states and why the default keeps the clock all live in
  // `startClockState`, which is pure and guarded. This page only supplies the
  // three facts it is the one that holds.
  const startClock = startClockState({
    startIsTbd: eventTournament?.start_is_tbd,
    isTournamentSport: isTournamentSportKey(event?.sport),
    tournamentResolved: eventTournament !== undefined,
  });
  const hideStartClock = startClock !== "clock";

  useEffect(() => {
    // live/048: `isSuspended` joins the suppression list. A suspended match has
    // a commence_time in the PAST, so counting down to it is counting down to
    // something that already happened.
    //
    // #3829: `hideStartClock` joins it for the mirror-image reason — a fixture
    // with no published order of play has a commence_time that was never a
    // start time at all, so counting down to it is counting down to nothing.
    if (
      !event?.commence_time || isLive || isFinished || isSuspended ||
      hideStartClock
    ) {
      setGameCountdown("");
      return;
    }
    const updateCountdown = () => {
      setGameCountdown(formatCountdown(event.commence_time));
    };
    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [event?.commence_time, isLive, isFinished, isSuspended, hideStartClock]);

  /* ── #6948: THE DEFERRAL IS LOSSLESS ONLY IF THE HEAD CAN STILL BE ASKED FOR ──
     First paint asks for `range=since_start`, which drops the pre-kickoff half
     of the payload — 89.3% of it on KC-DEN, and none of it drawn by the range a
     finished game opens on. The chart's "All" range DOES draw it
     (`filteredHistory` returns `history` untouched on "all"), so a client that
     trims and never re-fetches would silently show a shortened "All".

     THE LATCH IS ONE-WAY, AND THAT IS THE WHOLE DESIGN. The obvious spelling —
     key the request on `chartTimeRange` — oscillates: the full payload comes
     back with `pre_window_omitted: false`, which is also the condition for not
     needing it, so the key flips back, SWR serves the cached trimmed body, and
     the condition re-fires. Latching means the page asks for the whole journey
     at most once and never returns to the trimmed body it has outgrown.

     IT ASKS `pre_window_omitted`, NOT `chartTimeRange === "all"`, so a SCHEDULED
     game costs nothing: the route already served it everything (no post-kickoff
     point to trim to), the flag is false, and the chart's "all" default cannot
     provoke a duplicate request. That cohort is the majority of "all" charts,
     and a duplicate fetch for every one of them is LAT-P171/P172's defect.

     Reading the SERVER's flag rather than re-deriving it is deliberate: a series
     with no pre-kickoff points is indistinguishable from a trimmed one by
     looking at the points. See `lib/types.ts`.

     `chartTimeRange` covers the reader's tap AND the two paths that reach "all"
     without one — the evidence sync below, and OddsChart's own
     `nothingToDrawInLiveWindow` self-reset (#6349), which routes through this
     page's setter. Keying on the resulting RANGE rather than on the tap is what
     makes all three one code path. */
  const [fullHistoryRequested, setFullHistoryRequested] = useState(false);

  const {
    data: servedHistory,
    error: historyError,
    isLoading: historyLoading,
    mutate: refreshHistory,
  } = useSWR(
    ["history", eventId, fullHistoryRequested],
    // LAT-P219: the window is a shared constant, not a literal, so the URL this issues and the URL
    // the document parks at parse time are one expression. Two builders that must stay equal is the
    // exact shape of the LAT-P171/P172 duplicate-fetch defect. #6948 puts the range on the same
    // footing — the boot parks `&range=since_start` from this same constant.
    () =>
      fetchEventHistory(
        eventId,
        EVENT_BOOT_HISTORY_HOURS,
        historyRangeParam(fullHistoryRequested)
      ),
    {
      refreshInterval: isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL,
      // The key changes when the latch flips, and without this the chart would blank to its
      // skeleton while the whole journey loads — a visible regression on a tap that is supposed to
      // ADD points. The trimmed body stays drawn until the wider one replaces it.
      keepPreviousData: true,
    }
  );


  // #920: merge the session's actual published blend observations into the
  // history consumed by both charts. Each publication retains its timestamp;
  // a subsequent REST response wins exact-time overlaps. The renderer still
  // groups the main chart by minute; this is delivery, not a resolution change.
  // Without added publications, preserve #3911's server-authorized edge pin
  // for detail/history responses served by different workers.
  const historyData = useMemo(
    () => {
      const pushed = mergeLiveChartHistory(servedHistory, isLive ? chartPoints : []);
      // A push is an observation at its own time, not permission to rewrite
      // the previous poll's endpoint with today's hero value (#920).
      return pushed !== servedHistory ? pushed : pinChartEdgeToHero(servedHistory, event);
    },
    [servedHistory, event, isLive, chartPoints],
  );

  /* #8066: the chart's blend line must be the BACKEND's blend, and after #920
     `historyData.aggregate_line` can no longer answer that — it holds the
     served blend AND every frame this page accumulated from the live stream,
     which the backend publishes for single-source events too. This reads the
     SERVED response, before the merge, so the answer is about the backend and
     not about how long the tab has been open. `heroBlend` and the hero's
     `latestBlendPoint` fallback keep reading the merged array; only the chart's
     "is there a blend to draw" question is re-pointed. */
  const backendBlendServed = (servedHistory?.aggregate_line?.length ?? 0) > 0;

  /* ── #3612: A GAME THAT HAS BEGUN DOES NOT PROMISE THAT TRACKING WILL BEGIN ──
     No source has ever written a price for this event — no odds history, no
     win-prob history of any kind — and the game is not in the future. Measured
     by ux/1205 on production (last 30 days, `commence_time < NOW()`, zero
     `odds_snapshots` AND zero `win_prob_snapshots`): `closed` 52,006 ·
     `suspended` 10,083 · `voided` 452 · `completed` 112 · `live` 5. Every one
     of them rendered "Tracking will begin when odds are available" — a PSG 6-1
     win in the Champions League and a two-week-old Giants game among them.

     Suppressed, not reworded. Notice 34 / D102: "If a number cannot be shown
     honestly, leave the space empty; do not explain the emptiness in a
     paragraph." The reader keeps the score, the Final chip and the Score
     Differential chart — everything we actually know. Same discipline
     `WinnerEvolutionChart.tsx` already applies ("Honest absence: no real path
     yet → render nothing").

     HAS BEGUN IS THE CLOCK *OR* THE STATUS, and it needs both halves. Status
     alone leaves a `scheduled` row whose start time passed hours ago still
     promising a chart "at game time" — the #3211 / #5158 shape. The clock alone
     cannot see a settled event whose `commence_time` we hold wrong. An unknown
     status with a future start stays pregame, which is the safe end: it keeps
     the card and `OddsChart` speaks for it.

     LOADING AND ERROR ARE NOT ABSENCE. Both must keep rendering the card or a
     slow fetch would make the whole section blink out of the page and a failed
     one would take its Retry button with it.

     🔴 "NOTHING" MEANS EVERY SERIES THE CHART CAN DRAW, AND THE OLD CONDITION
     DID NOT. The arm this replaces tested `history.length === 0 &&
     !hasAnyWinProbData(...)` — sportsbook, espn and win_prob. But `OddsChart`
     builds `chartData` from FIVE inputs: those three plus `bookmaker_history`
     and `aggregate_line`, both of which this page passes it. So an event with
     only a bookmaker series or only an aggregate line was ALREADY being told
     "tracking will begin" over a chart that would have drawn — and suppressing
     on the same test would have turned a wrong sentence into a missing chart,
     which is worse. The predicate below asks the question the chart asks. */
  const hasNoPriceHistoryAtAll =
    !historyLoading &&
    !historyError &&
    !!historyData &&
    (historyData.history?.length ?? 0) === 0 &&
    !hasAnyWinProbData(historyData) &&
    (historyData.aggregate_line?.length ?? 0) === 0 &&
    !Object.values(historyData.bookmaker_history ?? {}).some(
      (points) => Array.isArray(points) && points.length > 0,
    );
  const eventHasBegun = hasStarted || !isPregameStatus(event?.status);
  const suppressWinProbabilityCard = hasNoPriceHistoryAtAll && eventHasBegun;

  /* ═══ #6421: HISTORY ABSENCE IS NOT PRICE ABSENCE ═══

     The per-sportsbook price table used to be written inline as the win
     probability card's footer, so `suppressWinProbabilityCard` took it away
     with the chart. Those are two different questions. The suppression above
     is right about the CHART — an empty chart must not promise tracking, and
     ux/1205's sentence stays gone — but the table beneath it shows prices we
     are holding RIGHT NOW, and a reader who cannot see one of ten books is
     being told we have nothing when we have ten.

     The class is not hypothetical after #6399's history fold, which fixes the
     named specimen and not the shape: for a finished event the history query
     caps at `_finished_event_end_cap` while the detail route's current-odds
     read applies no cap, so a book whose only reading was captured after the
     cap reaches `bookmaker_odds` and no series at all. Ten prices, every
     series empty, card suppressed.

     ONE DEFINITION, TWO PLACEMENTS — never two copies. The markup below is the
     page's only sportsbook disclosure; it renders as the chart's footer when
     the card is there and as its own card when the card is not. A second
     inline copy would be two places to keep in step, which is the failure the
     #4083 note at the render site was written about.

     `placement` changes chrome only, never content. As a footer it keeps the
     divider that separates it from the chart above and stays right-aligned
     under it; standing alone it has nothing to be divided from and reads as
     the card's own heading, so the rule is left. */
  const hasBookmakerOdds = (event?.bookmaker_odds?.length ?? 0) > 0;

  const sportsbooksDisclosure = (placement: "chart-footer" | "own-card") => {
    // Narrowed off the array itself, not off `hasBookmakerOdds` — a boolean
    // computed elsewhere tells the compiler nothing about this field, and the
    // same emptiness test has to be the one the render sites gate on.
    const odds = event?.bookmaker_odds;
    if (!event || !odds || odds.length === 0) return null;
    const isFooter = placement === "chart-footer";
    return (
      <>
        <div
          className={`px-4 sm:px-5 py-2 flex items-center gap-2 ${
            isFooter ? "border-t border-surface-border justify-end" : "justify-start"
          }`}
        >
          <button
            onClick={() => setSourcesOpen(!sourcesOpen)}
            className="shrink-0 flex items-center gap-1 px-2 py-1 rounded-md hover:bg-surface-elevated transition-colors"
          >
            <span className="text-[10px] text-text-muted font-medium">Sportsbooks</span>
            <svg
              className={`w-3 h-3 text-text-muted transition-transform duration-200 ${sourcesOpen ? 'rotate-180' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>

        {/* Sources panel (collapsible) */}
        {sourcesOpen && (
          <div className="border-t border-surface-border">
            <div className="px-4 py-3">
              <BookmakerTable
                bookmakerOdds={odds}
                homeTeam={event.home_team}
                awayTeam={event.away_team}
              />
            </div>
          </div>
        )}
      </>
    );
  };

  // Game-level markets (totals spectrum, player props)
  const { data: servedGameMarkets } = useSWR(
    ["game-markets", eventId],
    () => fetchGameMarkets(eventId),
    { refreshInterval: isLive ? LIVE_REFRESH_INTERVAL : SCHEDULED_REFRESH_INTERVAL }
  );

  // #7064: the hero already answers the game's own moneyline, so the props body must not answer it
  // again — it was arriving once PER VENUE, so the page showed the same question two more times,
  // under two spellings, disagreeing with the hero and with each other (56 + 46 = 102%).
  //
  // Filtered HERE, at the single point the payload enters the page, rather than in each renderer:
  // `player_props` feeds THE DIVERGENCE, the "All N props" count, the dashboard and the section's
  // own mount condition, and a filter applied to some of those would make the count disagree with
  // the list. `withoutEventOwnMoneyline` returns the payload by reference when it drops nothing,
  // which keeps `resetKey={gameMarkets}` stable on the section error boundaries below.
  const gameMarkets = useMemo(
    () => (servedGameMarkets ? withoutEventOwnMoneyline(servedGameMarkets) : servedGameMarkets),
    [servedGameMarkets]
  );

  // Both charts read the same served + received publication history (#920).
  const sparklinePoints = useMemo(() =>
    (historyData?.aggregate_line ?? []).map(p => ({
      timestamp: p.timestamp, value: p.home_probability,
    })), [historyData?.aggregate_line]);

  // Team championship progression (playoff path from grid data — always available for both teams)
  const { data: teamProgression } = useSWR<TeamProgressionResponse>(
    ["team-progression", eventId],
    () => fetchTeamProgression(eventId),
    { revalidateOnFocus: false, dedupingInterval: 300000 }
  );

  // The shared range both charts run on. `history` arrives async, so this is a
  // sync effect rather than a useState initialiser — same shape as each chart's
  // own internal sync. Holding "live" unconditionally is what rendered two empty
  // grids on an event whose commence_time predates every point it has
  // (see maxPostStartSeriesPoints in eventKeyStats.ts).
  const evidenceChartTimeRange = useMemo(
    () => defaultChartTimeRange(historyData, event?.commence_time),
    [historyData, event?.commence_time],
  );
  useEffect(() => {
    if (chartRangeUserSet) return;
    setChartTimeRange(evidenceChartTimeRange);
  }, [evidenceChartTimeRange, chartRangeUserSet]);

  /* #6948 — ask for the pre-kickoff half back once the range that is actually
     settling needs it. Placed HERE, below the evidence range, because it reads
     that memo rather than the `chartTimeRange` state: before the payload lands
     `defaultChartTimeRange` sees zero post-kickoff points and answers "all",
     and that transient survives one commit past the payload's arrival. Latching
     on it made KC-DEN fetch the trimmed body AND the full body on every load —
     found by driving a real browser, invisible to every unit assertion.
     See `lib/event/historyRange.ts`. */
  useEffect(() => {
    setFullHistoryRequested((prev) =>
      nextFullHistoryLatch(
        prev,
        effectiveChartRange(chartRangeUserSet, chartTimeRange, evidenceChartTimeRange),
        servedHistory?.pre_window_omitted
      )
    );
  }, [
    chartRangeUserSet,
    chartTimeRange,
    evidenceChartTimeRange,
    servedHistory?.pre_window_omitted,
  ]);

  // Derive period boundaries from history data for chart annotations.
  //
  // #7901: this used to pass a `realStartTime` here, so the FIRST boundary was
  // redrawn at the (estimated) game start rather than at the moment it was
  // observed. `computeRealStartTime` could never detect a late start anyway —
  // it minimised over every `win_prob_history` series, and Kalshi/Polymarket
  // quotes begin days before first pitch, so its "is the earliest live reading
  // more than 3 minutes after the nominal start?" test was answered by a market
  // price and always said no. It is removed; every marker now stands at its own
  // evidenced time. See `derivePeriodBoundaries`.
  const periodBoundaries = useMemo(() => {
    return derivePeriodBoundaries(
      historyData?.espn_history,
      historyData?.win_prob_history,
      historyData?.scoring_plays,
      historyData?.period_markers,
      // #4888: ESPN's box-score fallback serves bare digits ("3"), which the
      // chart drew as an unlabelled dashed rule. The sport is what turns that
      // into "Q3" — see BARE_PERIOD_UNIT in lib/periodMarkers.ts.
      event?.sport,
    );
  }, [historyData?.espn_history, historyData?.win_prob_history, historyData?.scoring_plays, historyData?.period_markers, event?.sport]);

  // Shared chart domain (see eventKeyStats.ts)
  const sharedChartDomain = useMemo(
    () => computeSharedChartDomain(historyData, chartTimeRange, event?.status, event?.commence_time, event?.sport || undefined),
    [historyData, chartTimeRange, event?.commence_time, event?.status, event?.sport],
  );

  // Most recent chart point for GamePlayCard (see eventKeyStats.ts)
  const lastChartPoint = useMemo<ActiveChartPoint | null>(
    () =>
      computeLastChartPoint(
        historyData,
        event?.home_score,
        event?.away_score,
        // #4571 — the event row's own clock, so the helper can date the score by
        // the arm that supplied it rather than by its neighbouring timestamp.
        event?.score_observed_at,
      ),
    [historyData, event?.home_score, event?.away_score, event?.score_observed_at],
  );

  // Best-known scores. #5521 — the comment that stood here said *"prefer latest
  // ESPN history (more frequent updates) over event SWR"*, which is an empirical
  // claim about relative freshness that nothing re-checked at runtime, and on
  // 15304937 it was simply false: ESPN's last row was 4m30s OLDER than the
  // StatPal snapshot beside it and the hero printed the wrong team ahead for an
  // hour. `computeLastChartPoint` now ranks the two observation series by their
  // own clocks; the event row remains the fallback beneath both.
  const bestHomeScore = lastChartPoint?.homeScore ?? event?.home_score ?? null;
  const bestAwayScore = lastChartPoint?.awayScore ?? event?.away_score ?? null;

  // ── #5720 — A RECORD IS NOT A SCORE, AND ON A STARTED GAME WITH NO SCORE A
  //    READER HAS NOTHING TO TELL THEM APART ────────────────────────────────
  //
  // The record draws in the score's own slot, directly under the team name, in
  // the same small grey type, on every live page. While the score is there the
  // two cannot be confused: a `text-4xl font-black` number sits below it. When
  // the score is missing the record becomes the ONLY score-shaped number on the
  // card — and `W-L` and a football score are the same shape.
  //
  // `/events/15304455`, East Carolina at Appalachian State, LIVE and 3h26m past
  // its own kickoff, read `0-0` under the home crest, beside a hero of `1% –
  // 99%` and a projected final of `18 – 27`. East Carolina carried no record at
  // all, so the two slots read as a score line with one side missing.
  //
  // Not a one-page oddity: 109 of 149 live events carried no score when #5697
  // was re-measured (73%), and every one of those whose team has a record drew
  // this.
  //
  // 🔴 THE PAIR, NOT THE SIDE. The hero's score row is read as `17 – 10`; a lone
  // number says nothing, so a page showing one side's SCORE and the other side's
  // RECORD is the same defect one column over — and the per-side gate would
  // leave exactly that. The two per-side score gates below are deliberately
  // UNCHANGED: whether a half-reported score should print at all is a different
  // question and is not this ship's to answer.
  //
  // A PRE-GAME RECORD STAYS. Before kickoff there is no score slot to be
  // mistaken for, and the record is the framing the hero exists to give. This
  // gate removes the record only where it has stopped being legible as one.
  const heroScorePairPresent = bestHomeScore !== null && bestAwayScore !== null;
  const heroUnderway = isLive || isFinished || hasStarted;
  const recordReadsAsRecord = !heroUnderway || heroScorePairPresent;

  // ── #5697 AC2 — A PROJECTION OF THE FINAL NEEDS A GAME THE READER CAN SEE THE
  //    STATE OF ────────────────────────────────────────────────────────────────
  //
  // `/events/15310565`, Southeastern Louisiana v North Alabama, LIVE and 90
  // minutes past its own kickoff: `LIVE`, `live · 26s ago`, `⟳ 20s`, a full
  // chart, `69% – 31%`, and `Projected final: 29 – 22` — over a game whose score
  // the page cannot name. Every freshness signal on the frame is green and
  // correct, which is the worst shape for a reader: there is no way to tell a
  // missing score from 0–0, and the projection is the one number on the card
  // that LOOKS like a scoreline.
  //
  // BEFORE KICKOFF THE PROJECTION IS THE HONEST THING and stays. A forecast of a
  // game that has not started is exactly what it says it is; there is no absent
  // score for it to be read against. The projection is withdrawn only once the
  // game is underway, where a reader has started expecting a score.
  //
  // THE PAIR, NOT THE SIDE, for the same reason #5720 gives two gates up: the
  // projection is rendered as `29 – 22`, a pair, so a half-reported score leaves
  // the reader comparing a projected pair against a single number.
  //
  // 🔴 THIS IS DELIBERATELY ITS OWN PREDICATE AND NOT `recordReadsAsRecord`,
  // which is the same expression today. #4018's line, quoted again four hundred
  // lines down where this renders: a forecast and a result are two questions and
  // they get two predicates. #5720 asks "can this small grey number be mistaken
  // for a score"; this asks "is there a game state to frame a forecast against".
  // They coincide now; binding them would make either ship silently move the
  // other.
  const projectionHasGameStateToFrame = !heroUnderway || heroScorePairPresent;

  // ── #8156 — A PROJECTED FINAL IS A RESULT, SO IT HAS TO BE ONE THE SPORT CAN
  //    PRODUCE ────────────────────────────────────────────────────────────────
  //
  // `/events/15316961`, Padres @ Dodgers, LIVE, score frozen at 0 – 0 through
  // both frames, 390px, production 2026-09-23:
  //
  //     02:39Z   54% – 46% Dodgers      Projected final: 3 – 3
  //     02:43Z   55% – 45% Dodgers      Projected final: 4 – 3
  //
  // and the payload between them (`2.5 / 3.5`) would have drawn `3 – 4`, the
  // PADRES, under a hero naming the Dodgers. Three outcomes in four minutes
  // with nothing happening in the game — but only one of them is this gate's
  // business. **`3 – 3` is not a bad estimate. MLB has no ties.** The card
  // stated a final score the sport cannot produce, immediately under its own
  // "someone wins" number.
  //
  // 🔴 THE ARITHMETIC IS THE WHOLE CAUSE, AND IT IS HERE, NOT UPSTREAM. The
  // pair is rounded per side, independently, so ANY pair under a run apart
  // collapses onto one integer: `2.9 / 3.1` prints `3 – 3`. The served value is
  // faithful to what the books quoted; the impossible claim is manufactured by
  // the render. 17 of this event's own 164 projection rows (10.4%) round to a
  // tie — the near-pick'em window, where a large share of live baseball sits.
  //
  // NOT THE JITTER. The underlying pair moves every minute because it is one
  // minute's bookmaker sample (median 2 books; the favourite flips 13 times
  // across this event's history) — that is #5455's single-row read, backend,
  // and it is untouched here. This gate does not stabilise anything. It stops
  // the page printing a scoreline that could never happen, which is the half
  // that stands on its own.
  //
  // NOT A NARRATION. Notice 34: a number that cannot be shown honestly leaves
  // the space empty. No "too close to call", no asterisk — the line is absent
  // and the hero above it already says the game is near even.
  //
  // THE SPORT ANSWERS, NOT THIS FILE. `canEndInATie` is declared per sport in
  // `marketMapUtils`; soccer and the NFL say `true` and keep their level
  // projections, because the rule is about IMPOSSIBLE results and not unlikely
  // ones. A sport nobody has declared keeps printing, by the field's default.
  const projectedFinalPair = historyData?.pm_spread_data?.projected_final ?? null;
  const projectedPairIsAPossibleResult =
    projectedFinalPair == null ||
    sportVocab(event?.sport || undefined).canEndInATie ||
    Math.round(projectedFinalPair.home_score) !==
      Math.round(projectedFinalPair.away_score);

  // ── #4885 — A PROJECTED FINAL CANNOT BE BELOW THE SCORE ALREADY ON THE BOARD ─
  //
  // `/events/15316846`, Blue Jays @ Orioles, LIVE, Bottom 8th, 390px, production
  // 2026-09-23 20:06Z: the hero read `4 – 2` and, two lines under it,
  // `Projected final: 3 – 2`. The Orioles were projected to finish with fewer
  // runs than they already had. The pair was `3.3 / 1.9` from sportsbook odds
  // last captured four minutes BEFORE first pitch — the issue's own "pre-game
  // number wearing a live label" — and it passed all five gates above, because
  // none of them compares the forecast with the game.
  //
  // native/150's invariant on the issue, and the reason this is decidable here
  // with no ground truth: runs, goals and points are never taken back, so a
  // final below the current score is always false — whichever book is stale,
  // however the aggregate averaged (#5455's mechanism, backend, untouched).
  //
  // PER SIDE, AFTER THE SAME ROUNDING THE LINE PRINTS. `3.6` under a score of
  // `4` prints `4` and is reachable; comparing the raw float would withhold a
  // line the reader would have read as correct. EQUAL IS REACHABLE: `4 – 2`
  // projected at `4 – 2` is a game with no more scoring, which is a real final.
  //
  // THE PAIR THE HERO PRINTS. `bestHomeScore`/`bestAwayScore` are the exact
  // values rendered in the score slots. On the specimen the event ROW still
  // held `0 – 0` (#8278) while the hero read `4 – 2` from the chart's live arm;
  // a gate reading the row would have passed the photographed defect.
  //
  // No score pair (pre-game, or #5697's live-without-score) ⇒ nothing to
  // contradict, and the other gates decide. Notice 34: the space is left empty,
  // not explained.
  const projectedPairIsReachableFromTheScore =
    projectedFinalPair == null ||
    bestHomeScore === null ||
    bestAwayScore === null ||
    (Math.round(projectedFinalPair.home_score) >= bestHomeScore &&
      Math.round(projectedFinalPair.away_score) >= bestAwayScore);

  // #4571 — the age of the score PAIR the two lines above just resolved.
  //
  // `lastChartPoint` runs the same cascade internally and reports the clock of
  // the arm that won, so the common path is simply to read it. The `??` fallback
  // above is the one case it cannot answer for: with no `historyData` at all
  // `computeLastChartPoint` returns null, and the rendered score is the event
  // row's — dated, then, by the event row's stamp.
  //
  // Null is a real answer and the most common one today: `score_observed_at` is
  // not on production yet (live's backend sha is blocked on this half existing),
  // so the event-row arm reports null and the badge ages on the price alone,
  // exactly as it does now. The ESPN arm is live already and starts telling the
  // truth on merge.
  const renderedScoreStamp = lastChartPoint
    ? lastChartPoint.scoreStamp ?? null
    : bestHomeScore !== null || bestAwayScore !== null
      ? event?.score_observed_at ?? null
      : null;

  // #5607 — a slow load is a slow load, not a failure.
  //
  // This timer used to flip the whole page to a terminal "Loading timed out"
  // card at 12s. It fired before `fetchEvent`'s FIRST stage could even expire
  // (the 20s boot-claim race), so it announced a failure the fetch had not had
  // and could not yet have had. `lib/event/loadingPresentation.ts` carries the
  // full timing table and why neither a bigger constant nor another retry is
  // the repair. The mark survives; what it is allowed to SAY is what changed.
  const [pastSlowLoadMark, setPastSlowLoadMark] = useState(false);
  useEffect(() => {
    if (!eventLoading) {
      setPastSlowLoadMark(false);
      return;
    }
    const timer = setTimeout(
      () => setPastSlowLoadMark(true),
      EVENT_SLOW_LOAD_NOTICE_MS,
    );
    return () => clearTimeout(timer);
  }, [eventLoading]);

  if (eventLoading) {
    // Whatever the clock says, this branch renders a LOADING view. The terminal
    // claim is the `!event` branch below, which reads the real failure.
    const loadingView = eventLoadingView(pastSlowLoadMark);
    return (
      <div className="py-12 flex flex-col items-center gap-4">
        <LoadingSpinner text={loadingView.text} />
        {loadingView.offersRetry && (
          <button
            type="button"
            onClick={() => refreshEvent()}
            // Same affordance the card this replaces used, so the reader's way
            // out looks the way it has always looked (`ErrorMessage`'s retry).
            className="text-caption text-accent-brand underline hover:no-underline transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  // #2783 — this said "Event not found" for EVERY failure. Measured on
  // production 2026-09-03: a client over the 60/minute limit gets a 429 and was
  // told the event does not exist, with "Rate limit exceeded: 60/minute"
  // printed directly underneath — the heading contradicting its own body, and
  // both contradicting the truth, which is that the event is fine.
  //
  // The status decides the heading now (`lib/loadFailure.ts`). A reader told a
  // thing does not exist stops looking for it; a reader told we could not reach
  // it reloads, which is the correct thing to do for every failure here except
  // a real 404 — and that one no longer offers a retry button that cannot help.
  //
  // #5016 — the gate is `!event`, NOT `eventError || !event`. Measured on
  // production during SF@LAR, 2026-09-10: a tab opened at 5:39pm PT held a full
  // live page — 61%–39%, the score, the chart — and at 5:56pm had been replaced
  // by "Couldn't reach the server", still there 57 minutes later, while fresh
  // loads of the same url rendered fine throughout.
  //
  // SWR KEEPS `data` WHEN A REVALIDATION FAILS. That is the whole point of
  // stale-while-revalidate, and it means `eventError` being set says nothing
  // about whether we have a page to draw — here `event` was populated and one
  // line from being rendered when the `||` threw it away. A failed REFRESH is a
  // freshness event, not an existence event, and the page already discloses
  // freshness: `live · Ns ago` counts from the event's own observation stamp,
  // so a page that stops updating goes visibly stale on its own and recovers
  // invisibly the moment any poll succeeds. A page that has discarded its
  // content needs a success AND a rerender before the reader gets anything.
  //
  // The reader this protects is the ordinary one: a phone on a game night, one
  // request in a hundred lost to a lift, a tunnel or a wifi handoff.
  if (!event) {
    const failure = describeLoadFailure(eventError, "event");
    return (
      <ErrorMessage
        title={failure.title}
        message={failure.message}
        onRetry={failure.retryable ? () => refreshEvent() : undefined}
        // #5857: a retired fixture (410) and a missing one (404) are answers,
        // not failures, and this card used to paint both in danger red.
        tone={failure.tone}
      />
    );
  }

  // Resolve display probability based on game status (see eventKeyStats.ts)
  //
  // #4015 — `isSuspended` (the page's one `hasNoReportedResult` answer, computed
  // above) decides the hero for a match that went dark: it reads the chart's last
  // point rather than a `current_odds` the poller stopped rewriting hours earlier.
  // Without it this page printed a 21-hour-old 90% directly above its own chart's 1%.
  const {
    homeProb,
    // #6238 — renamed, not consumed. Every one of these four is `1 − home` by
    // construction, so on a draw-priced sport they are the number this page must
    // not print. The withheld values are derived immediately below; nothing
    // downstream may reach the served away side without going past that comment.
    awayProb: servedAwayProb,
    probSourceLabel,
    openingHomeProb,
    openingAwayProb: servedOpeningAwayProb,
    // #2085 — the whole percents to PRINT for each pair, decided together at
    // the one place that knows which source each pair came from.
    homePct,
    awayPct: servedAwayPct,
    openingHomePct,
    openingAwayPct: servedOpeningAwayPct,
  } = resolveProbability(
    event,
    historyData,
    lastChartPoint,
    isLive,
    isFinished,
    isSuspended,
    // #5069 — the caption must not say "Live" over a number that stopped
    // moving. Fed from `freshestSourceStamp` and NOT from `heroStamp`, and the
    // difference is deliberate: `heroStamp` is the age of the whole GLANCE
    // (min across price and score, #4469), while this caption is a claim about
    // the BLEND alone, whose age is the max across its own sources. Using the
    // glance's age here would strip "Live" off a ten-second-old probability
    // whenever a score on a ten-minute beat happened to be the older fact —
    // the mirror image of the bug #4469 fixed, and just as untrue.
    //
    // `heroStampIsStale` is the badge's own predicate, so the caption and the
    // grey age badge above it cross the same boundary at the same instant.
    //
    // #2800 — OR'd with `liveClaimUnbacked`, because the age is only one of the
    // two ways this number stops being current. A PINNED price is rewritten on
    // schedule with an identical value, so it is permanently fresh to the stamp
    // and permanently frozen in fact (Peliwo v Ziegann, 84 reads over 87
    // minutes, all 0.99, badge reading `1m ago`). This is the same OR the age
    // badge itself already takes through `claimWithdrawn` one line below, and
    // the rule `effectivelyLive` states at :356 — everything that ASSERTS
    // motion reads the withdrawal, and "Live · Bain Luck blend" asserts motion.
    blendCaptionIsStale(
      heroStampIsStale(freshestSourceStamp, "price"),
      liveClaimUnbacked,
    ),
  );

  // ═══ #6238 — THE AWAY NUMBER THIS PAGE IS ALLOWED TO PRINT ═══
  //
  // `/events/15301234` (León v Atlético San Luis, Liga MX) printed `68% – 32%`
  // on a market where the draw is a real outcome, two hours before kickoff,
  // while its OWN correct-score card one section down put 0-0 at 22% and 1-1 at
  // 10%. The served away figure is `1 − home` exactly (`0.317 === 1 − 0.683`),
  // so what sat under the away crest was "León does not win" — away win OR draw
  // — wearing San Luis's name. Measured against the books behind it, León was
  // overstated by ~14pp.
  //
  // Withheld rather than corrected: there is no away price to read. See
  // `lib/drawPricedWinner.ts` for the three payloads that were checked and for
  // why the retained home number is STILL draw-dropped (#1011) — this is the
  // render half only, exactly as native's #5271 was.
  //
  // ── ALL FOUR, AND WHY IT IS NOT JUST THE HERO ─────────────────────────────
  //
  // #5696 found the hero and the `Opened 64% – 36%` line disagreeing on one
  // screen, which is what a partial adoption looks like. The opening pair is the
  // same complement taken at a different instant, so a fix that withholds the
  // hero's away number and leaves the opening line printing one moves the false
  // number three rows down the page instead of deleting it. Both pairs, one
  // rule, one place.
  //
  // `settledWinnerPregameProb` below reads `openingAwayProb` and is null-guarded,
  // so on a draw-priced sport whose AWAY side won, the settled hero withholds
  // the "was priced at N%" line rather than sourcing it to the complement. That
  // is the same rule wherever the number it would print IS the complement — and
  // #6614 is the case where it is not. See below.
  //
  // ── #6614 — THE TWO PAIRS ON THIS PAGE ARE NOT THE SAME KIND OF OBJECT ─────
  //
  // The blanket sport-keyed withhold above is right for `current_odds`, whose
  // away leg `routes/feed.py` derives as `1 - home`. It is WRONG for
  // `opening_odds`, which since #1011 is de-vigged across the whole quoted
  // board: `home + away ≈ 0.76` and the missing ~0.24 IS the draw. Both legs
  // are real, independently sourced prices, and this page was deleting one.
  //
  // Re-taken on production 2026-09-18 ~08:58Z (the filed 2026-09-16 population
  // re-measured on a fresh slate), `/api/feed?mode=sports`, 25 soccer cards:
  //
  //   | pair            | sums to 1.0000 | sums to 0.72 – 0.84 |
  //   |-----------------|----------------|---------------------|
  //   | `current_odds`  | **25 / 25**    | 0                   |
  //   | `opening_odds`  | 16 / 25        | **9 / 25**          |
  //
  // So BOTH arms are live traffic and a blanket flip either way is wrong: 16 of
  // 25 opening pairs really are complements and must still be withheld. The
  // question is per-PAIR, which is exactly what `awayIsTheComplement` asks —
  // the sport prices a draw AND (away is absent OR the pair completes to 1).
  //
  // Specimen, photographed at 390×844 before the fix
  // (`artifacts/ux-1330/BEFORE-6614-15298749-390.png`): `/events/15298749`,
  // Torreense @ Lillestrom, Europa League, final 1–2. Opening pair
  // `0.5476 / 0.2103` sums to **0.7579** — not a complement, both legs real.
  // Torreense WON as a 21% underdog and the settled hero printed no pregame
  // mark at all, so the one fact that made the result worth reading was the
  // fact the page deleted.
  //
  // `settledWinnerPregameProb` is deliberately NOT touched: its existing
  // `openingHomeProb !== null && openingAwayProb !== null` gate passes by
  // itself once the away value survives, because a non-complement pair has two
  // real legs. Loosening that gate would newly print a mark on the 16/25
  // complement pages — a population this issue never reasoned about, and one
  // where the number still IS the complement.
  const awaySlotWithheld = sportPricesADraw(event.sport);
  const awayProb = printableAway(servedAwayProb, event.sport);
  const awayPct = printableAway(servedAwayPct, event.sport);
  const openingAwaySlotWithheld = awayIsTheComplement(
    servedOpeningAwayProb,
    openingHomeProb,
    event.sport,
  );
  const openingAwayProb = openingAwaySlotWithheld ? null : servedOpeningAwayProb;
  const openingAwayPct = openingAwaySlotWithheld ? null : servedOpeningAwayPct;

  // #490: hero confidence signal (1-3 bars), computed client-side from the win-
  // prob sources already on the event + whether the line moved off open. Mirrors
  // the feed-card backend formula (frontend/lib/confidence.ts).
  //
  // #3914: READINGS, not keys. `Object.keys(...).length` counted
  // `betting_book_count` — a count of sportsbooks, not an opinion about who
  // wins — as a third source, saturating the sources component and printing
  // "high / 3 bars" over two readings. `countProbabilitySources` applies the
  // aggregator's own allowlist, so the bars and the blend count the same set.
  const heroConfidence = confidenceFromSources({
    sourceCount: countProbabilitySources(event.win_probability_sources),
    hasMovement:
      homeProb !== null &&
      openingHomeProb !== null &&
      Math.abs(homeProb - openingHomeProb) > 0.001,
  });

  // UX-1065 (#2936): the hero's compact team names. Decided for BOTH sides at
  // once so the pair can never read "IPS vs Liverpool" or "FC vs FC" — see
  // `lib/teamShortName.ts`. Before this, the hero applied `split(" ").pop()`
  // per side and named Ipswich Town "Town" three times on one page.
  //
  // #7163: the sport is passed because it is the only thing that can tell a
  // person from a club, and without it the hero shortened "Alex de Minaur" to
  // "Minaur" — the object of the particle rather than the name. A caller that
  // does not know its sport keeps the last-word rule untouched.
  const heroShortNames = teamShortNames(
    { name: event.home_team, abbreviation: event.home_team_data?.abbreviation },
    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
    event.sport,
  );

  // L2-112 Item 1: settled events get a winner treatment (final score + winner
  // chip), NOT a stale pregame percentage. Mirrors the futures settled-hero rule
  // (FuturesHero.tsx) — the probability journey stays in the chart below.
  // Winner is derived from the result, not the pregame favorite.
  //
  // #2443: "derived from the result" used to mean `home_score > away_score` and
  // nothing else, which is why a settled tennis match — no integers on the row,
  // by nature — printed a bare "Final" over two players and no outcome. The
  // authority ladder lives in `lib/eventOutcome.ts`; the score rung is
  // unchanged, and the container rung answers for every sport whose result is
  // not a pair of integers.
  const settledOutcome = resolveEventOutcome({
    isFinished,
    homeTeam: event.home_team,
    awayTeam: event.away_team,
    homeScore: bestHomeScore,
    awayScore: bestAwayScore,
    tournamentResult: eventTournament?.result ?? null,
    // live/073: what the sets above were won BY, when the event carries a line.
    linescore: event.linescore,
  });

  // #3330: the games under the sets, while it is still being played — the live
  // counterpart of `settledOutcome.resultLine` above. Every rule it follows
  // (home-first, why not `orientLinescore`, why it refuses a finished match)
  // is stated on the helper, beside the settled one it mirrors.
  const liveGamesLine = liveHeroGamesLine({
    isFinished,
    isLive,
    hasStarted,
    linescore: event.linescore,
  });

  // #4469 — THE BADGE AGES FROM THE OLDEST FACT IN THE HERO, NOT THE FRESHEST
  // PRICE. `freshestSourceStamp` above is a MAX across sources and is right for
  // the blend; the hero is not a blend but a glance, and a glance is only as
  // current as the oldest thing in it. Measured on Andreeva v Gauff 2026-09-09:
  // score median 482.9s old, price median 8.4s, so the page printed a green
  // `live · 6s ago` over a score eight minutes behind. The reasoning, and why
  // max-within-the-number and min-across-the-facts are not in conflict, is on
  // `heroFreshness`.
  //
  // Gated on `liveGamesLine`, not on `event.linescore`, and deliberately: an
  // unrendered fact cannot mislead anyone, so it must not age the badge either.
  //
  // #4571 — AND THE SAME GATE NOW COVERS EVERY OTHER SPORT. Until now the
  // `: null` arm was every ordinary integer score — NFL, MLB, NBA — so outside
  // tennis the badge aged the PRICE and printed a green `live · 6s ago` over a
  // score of entirely unknown age. #4469 fixed the glance for one sport and the
  // grader of CERT-2545 said so plainly: *"the badge can still age only the
  // price."*
  //
  // `renderedScoreStamp` (computed beside `bestHomeScore`) is the clock of the
  // score tuple ACTUALLY on screen, chosen by provenance. The tennis arm is
  // untouched and stays first: a games line and an integer score are different
  // renderings, `linescore.observed_at` is the clock of the one that is drawn,
  // and #4469's two guard suites pin it.
  const heroStamp = heroFreshness({
    priceStamp: freshestSourceStamp,
    scoreStamp: liveGamesLine ? event.linescore?.observed_at : renderedScoreStamp,
  });

  // L2-131 Item 1: the settled hero gains the pregame mark — the winner's
  // pre-game win probability ("were 35% pregame"). This is what makes an upset
  // read surprising at a glance. Data = the opening blend (opening_odds).
  //
  // Keyed on the resolved SIDE rather than on the score comparison, so it
  // follows the ladder: an outcome whose winner could not be matched to either
  // competitor reports no side, and this stays silent rather than crediting the
  // home player's opening number to whoever actually won.
  const settledWinnerPregameProb =
    settledOutcome?.winnerSide && openingHomeProb !== null && openingAwayProb !== null
      ? (settledOutcome.winnerSide === "home" ? openingHomeProb : openingAwayProb)
      : null;

  // Calculate countdown progress percentage
  const countdownProgress = ((refreshInterval / 1000 - countdown) / (refreshInterval / 1000)) * 100;

  // #3802 — is this page on a visible poll at all? The rule (and why 3h) lives
  // in `shouldShowRefreshCountdown`.
  //
  // #5459 asks it WITHOUT the withdrawal, deliberately, because two different
  // things read this answer. The RING is a promise and must go. The age badge
  // below is #4861's ADMISSION — the honest thing the header says instead of the
  // promise — and suppressing that would delete the remedy along with the
  // defect. Folding the withdrawal in here did exactly that, and #4861's own
  // guard caught it: its stalled page stopped saying "ago" at all.
  const onVisiblePoll = shouldShowRefreshCountdown({
    isFinished,
    streamConnected,
    isLive,
    isSuspended,
    commenceTime: event?.commence_time,
  });

  // #5459 — and the withdrawal applied, for the ring alone. Passed through
  // `shouldShowRefreshCountdown` rather than `&&`-ed on here so the rule stays
  // in the one pure seam a guard can hold, and because the widened `isSuspended`
  // above would otherwise turn the ring ON for an unbacked page
  // (`isLive || isSuspended` returns true) — the exact promise this withdraws.
  //
  // #6381's second half rides the SAME split, for the same reason. The ring is
  // a promise and a venue-graded match has nothing to promise; the age badge is
  // the admission and must survive. So `venueSettled` is passed HERE and not to
  // `onVisiblePoll` above — exactly where `liveClaimUnbacked` is passed.
  //
  // Derived from `venueSettledSentence` rather than re-reading
  // `event.venue_settled`, which is the centralisation this page's own pill
  // note (below) says `venueSettledSummary` exists to enforce.
  const showRefreshCountdown = shouldShowRefreshCountdown({
    isFinished,
    streamConnected,
    isLive,
    isSuspended,
    commenceTime: event?.commence_time,
    liveClaimUnbacked,
    venueSettled: Boolean(venueSettledSentence),
  });

  // #4861 — and only where one actually IS landing. The ring above counts down
  // a `setInterval` that ticks whether or not anything arrives, so on the page
  // a reader left open it went on promising an update long after the payload
  // stopped coming. `eventFeedIsStalled` carries the case and the measurement.
  //
  // Read during render rather than held in state on purpose: `countdown`
  // already re-renders this component once a second, so the elapsed time is
  // re-derived on the same tick the ring is drawn from, and there is no second
  // timer to fall out of step with the first.
  const feedStalled = eventFeedIsStalled({
    hasError: Boolean(eventError),
    msSinceLastLanding: Date.now() - lastRefresh,
    refreshInterval,
  });

  // Which cases earn the age badge — one answer, in one pure place, because
  // "how old is this number" must have exactly one (#4469). The rule, the two
  // arms it gained for #5039/#5049, and why the polled arm is gated on liveness
  // rather than on the ring's own window are all on `headerShowsAge`.
  //
  // #5459 — `onVisiblePoll`, NOT `showRefreshCountdown`. See its note: the age
  // badge is the admission that replaces the promise, so it must survive the
  // promise being withdrawn.
  const showsAge = headerShowsAge({
    isFinished,
    streamConnected,
    onVisiblePoll,
    feedStalled,
    effectivelyLive,
    isSuspended,
  });

  // The sparkline keeps the pushed branch to itself: it is the last ten minutes
  // of a number that is still arriving, and on a polled page it would be one
  // more thing implying motion.
  const pushedAge = !isFinished && streamConnected;

  // #3802/#4861's ring, as one name — the header now composes it beside the age
  // badge instead of choosing between them.
  const ringVisible = showRefreshCountdown && !feedStalled;

  // #8336 — the page's one freshness answer, built ONCE and placed in the header
  // and (when the chart goes fullscreen and covers the header) the modal. One
  // element rather than two call sites, so the two can never disagree (#4469).
  const ageBadge = showsAge ? (
    <LiveAgeStamp
      updatedAt={heroStamp.stamp}
      oldestFact={heroStamp.fact}
      connected={streamConnected}
      // #5459 — the hero below reads "No result reported" on a pinned page.
      // Without this the badge would pulse a green `live · 20s ago` beside it,
      // whose stamp really is that fresh.
      claimWithdrawn={liveClaimUnbacked}
    />
  ) : null;

  // L2-112 Item 4: the Score Differential card must hide when there is no
  // projected OR actual score data — otherwise ScoreDifferentialChart returns
  // null (or its "Score data is not available" message) inside a card shell,
  // leaving an empty heading. Mirror the child's real data requirement
  // (hasProjectedScoreData || hasActualScoreData) at the parent gate.
  //
  // L2-157 Item 4 (the 15165209 exhibit): "Score Differential" is an IN-GAME
  // concept — actual score divergence over time. Pregame it renders as empty
  // chrome (a bare header over a flat 0-0 ESPN snapshot or a projected-spread
  // line masquerading as innings), which is worse than no chrome (the
  // nothing>unhelpful ruling). Suppress it entirely until the game is in-game
  // or later; the pregame odds-movement story lives in the Win Probability
  // timeline above (time x-axis, with its own clean "tracking will begin" state).
  //
  // ux/1034 B5: the scoreboard half counts toward this gate only where the
  // scoreboard counts the thing the chart's axis is in. For a tennis match it
  // reports SETS against a GAMES projection, so the chart will not draw an
  // actual line from it — and a gate that still admitted it would open the
  // card on an event with nothing but a suppressed series inside it, which is
  // the empty-chrome failure the L2-157 note above exists to prevent.
  //
  // #6144 — AND THE CARD IS NAMED AFTER WHAT IS INSIDE IT. The note above
  // suppresses the masquerade PREGAME only, on the assumption that in-game
  // implies we hold an actual score. For every sport our live-score door
  // cannot read — all 36 of today's live rows, tennis/NPB/esports/soccer, each
  // with NULL score, period and clock — in-game never brings one, so the card
  // opened in-game on a projection alone and headed itself "Score
  // Differential" over a line that is the sportsbooks' projected margin. The
  // reader prices the heading: `/events/15311956` said LIVE, showed no score
  // anywhere, and drew a line falling to −5.5, which reads as Dragons by 5.
  //
  // The gate is deliberately NOT narrowed — in-game that projection is the
  // only read this page has on how the game is going, and ux/1034 B5 ruled
  // exactly that for tennis. What changes is the name: the heading is the
  // series it is drawn over. The decision is `lib/scoreDifferentialHeading`'s
  // and the actual-series half of THIS gate now calls it too, so the card's
  // name, the card's gate and the chart's orange line answer one question
  // once.
  const drawsActualScore = actualScoreSeriesDrawn({
    sportKey: event?.sport || undefined,
    scoreHistory: historyData?.score_history,
    espnHistory: historyData?.espn_history,
  });
  const hasScoreDiffData = (effectivelyLive || isFinished || hasStarted) && !!historyData && (
    (historyData.history ?? []).some(
      (p) => p.projected_home_score != null && p.projected_away_score != null
    ) ||
    drawsActualScore
  );
  const scoreDiffHeading = scoreDifferentialHeading({
    sportKey: event?.sport || undefined,
    actualSeriesDrawn: drawsActualScore,
  });

  return (
    <ErrorBoundary fallback={
      <ErrorMessage
        title="Something went wrong"
        message="This page encountered an error. Try refreshing."
        onRetry={() => window.location.reload()}
      />
    }>
    <div className="space-y-3">
      {/* Navigation */}
      {/* #3974: THE ROW WRAPS, because at 390px three elements do not fit in it.
          Measured on this page at that width: the row has 366px of usable
          width, the two back links need 246px of it, and the countdown group
          needs 125px — 383px of content for 366px of room. The 17px deficit
          came out of the back links, because they are the group carrying
          `min-w-0` + `overflow-hidden`, so the reader got "‹ Back to ever" —
          a clipped NAVIGATION CONTROL, which reads as a broken page rather
          than as an abbreviation — while "Next update:" wrapped over it.

          `flex-wrap` fixes it rather than `min-w-0` doing so, because flex
          breaks lines on each item's CONTENT size and only then shrinks what
          is on the line. So the countdown moves to its own row while the back
          links keep their full 246px, and on any width where all three fit
          nothing moves at all.

          This does not reverse #3802 below. That rule is about ONE long
          tournament title inside the inner group, and it still clips there;
          this is about a third element that has no room on the line. The
          `justify-between` that used to be here is gone because it does
          nothing once the right-hand group carries `ml-auto` — and `ml-auto`
          is what keeps that group right-aligned on the line it wraps to,
          which `justify-between` would not do. `gap-y-1` keeps the wrapped
          row tight; the horizontal gap is unchanged. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {/* #3802: `whitespace-nowrap` sits on the CONTAINER, not on either link.
            `white-space` inherits, so both back links get it without editing
            TournamentExtensions.tsx; `min-w-0` + `overflow-hidden` mean a long
            tournament title clips rather than wrapping the header into ragged
            lines, which is the defect at 390px. */}
        <div className="flex min-w-0 items-center gap-3 overflow-hidden whitespace-nowrap">
        {/* #2448: A TOURNAMENT IS A CONTAINER, AND A CONTAINER NEEDS A WAY OUT.
            Alex: "no link back to the tournament (only Back to events)". The
            tournament page routes a match card down here; this page routed back
            to Discover — not the tournament, not even the sport. Rendered
            BEFORE the generic link because the specific container is the one
            the reader arrived through, and it renders nothing at all for the
            events that are not in a register, which is nearly all of them. */}
        <TournamentBackLink
          eventId={eventId}
          sportKey={event.sport}
          onNavigate={(href) => trackNavigationClick('back', `/events/${eventId}`, href)}
        />
        {/* #3702: NO ARROW GLYPH IN THE LABEL — the <svg> below is the arrow.
            This link used to draw the chevron AND carry a literal arrow
            character in its text, so one link rendered two arrows. Next to the
            #2448 tournament link above, which has the identical chevron and no
            glyph, the header read "US Open 2026 / Back to events" with three
            arrows across two links. The chevron is the shared affordance both
            links use; the label is words. Guarded by
            __tests__/backLinkSingleArrow3702.test.tsx, over BOTH links. */}
        <Link
          href="/"
          onClick={() => trackNavigationClick('back', `/events/${eventId}`, '/')}
          className="inline-flex items-center text-caption text-text-secondary hover:text-text-primary transition-colors"
        >
          <svg
            className="w-4 h-4 mr-1"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15 19l-7-7 7-7"
            />
          </svg>
          Back to events
        </Link>
        </div>

        {/* THE HEADER SAYS HOW OLD ITS NUMBER IS — live/034 S2, #4861, and now
            on the polled path too (#5039/#5049, ship 5).

            It began as the pushed page's substitute for the countdown: on a
            pushed event there is no "next update" to count down to, because
            updates arrive, so the honest thing to show instead is the age. #4861
            added the polled page that has stopped being fed. Both are still
            here; `headerShowsAge` carries the whole rule and the case for the
            arm that made a LIVE, polled page — a halftime, a suspension — say
            its age as well.

            ONE CALL SITE, deliberately (#4469's guard): two would be two answers
            to "how old is this number", and the whole point of the badge is that
            there is one. `connected` is passed through rather than assumed,
            because the branches are no longer mutually exclusive — a polled page
            reaches this with `streamConnected` false, which is exactly the state
            in which the dot must not pulse.

            The sparkline stays on the pushed branch only: it is the last ten
            minutes of a number that is still arriving, and on a page that has
            stopped being fed it would be one more thing implying motion.

            ONE right-hand group, not two. The badge and the ring used to be
            mutually exclusive siblings, each carrying its own `ml-auto`; now
            that a polled live page shows both, two auto margins would put them
            on two ragged lines at 390px. Sharing the group's `gap-3` also means
            they wrap together, as one unit, to the line below — and #3974's
            alignment rule still reads one right-hand group with `ml-auto`. */}
        {(showsAge || ringVisible) && (
          <div className="ml-auto flex items-center gap-3">
            {pushedAge && <LiveSparkline points={sparklinePoints} />}
            {ageBadge}

            {/* Visual countdown timer — #3802 gates it on proximity, not just on
                "not finished and not pushed". #4861: and not while the page's own
                fetches are failing — the ring is a `setInterval` that ticks whether
                or not anything arrives, so it promised an update for three hours
                over a game that had already ended.

                THE PILL IS GONE, not moved, and the badge is why: the pill drew
                only here and only when `effectivelyLive`, and the badge is on
                screen for every one of those inputs — `headerAgeSubsumesLivePill`
                asserts exactly that, so the deletion is a reduction and not a
                loss. Two green live claims side by side are two answers to one
                question, and the pill was the worse one: keyed on the event's
                STATUS, it stayed green and pulsing over a number of any age
                (#5049), where the badge drops the green and the word "live" the
                moment its own fact goes stale.

                The ring and its label are untouched. "Next update:" is the one
                sentence naming what the ring counts, and the ring is the only
                thing on a still page that shows it is still trying — #5039's
                complaint was never that the countdown exists, it was that the
                age went away when the countdown arrived. */}
            {ringVisible && (
              <>
                <span className="text-sm text-text-secondary">Next update:</span>
                <div className="relative w-10 h-10">
                  <svg className="w-10 h-10 transform -rotate-90">
                    <circle
                      cx="20"
                      cy="20"
                      r="16"
                      fill="none"
                      stroke="#E5E7EB"
                      strokeWidth="3"
                    />
                    <circle
                      cx="20"
                      cy="20"
                      r="16"
                      fill="none"
                      stroke={effectivelyLive ? "#10B981" : "#6B7280"}
                      strokeWidth="3"
                      strokeDasharray={`${countdownProgress} 100`}
                      strokeLinecap="round"
                      className="transition-all duration-100"
                    />
                  </svg>
                  <span className="absolute inset-0 flex items-center justify-center text-xs font-mono font-bold text-text-primary">
                    {countdown}
                  </span>
                </div>
              </>
            )}
          </div>
        )}
      </div>

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

      {/* Hero Section — v2 design */}
      {/* UX-P055: the hero is the answer, so it is the LAST thing worth losing —
          which is exactly why it gets its own boundary rather than sharing the
          route's. A hero that throws must not also cost the reader the chart,
          the props and the script. */}
      <SectionErrorBoundary label="The score and probability" resetKey={event}>
      <div className="rounded-card shadow-card overflow-hidden bg-surface-card">
        {/* Top meta row: phase + broadcast + date/time */}
        <div className="px-4 sm:px-5 py-2 flex items-center justify-between border-b border-surface-border/30">
          <div className="flex items-center gap-2">
            {/* Pin button */}
            <button
              onClick={() => togglePin(eventId)}
              disabled={isMaxReached && !eventIsPinned}
              className={`
                p-1 rounded-full transition-all
                ${eventIsPinned
                  ? 'text-amber-500'
                  : 'text-text-muted/40 hover:text-text-secondary'
                }
                ${isMaxReached && !eventIsPinned ? 'cursor-not-allowed opacity-30' : ''}
                focus:outline-none
              `}
              title={eventIsPinned ? 'Unpin event' : isMaxReached ? 'Maximum 6 pins' : 'Pin event'}
              aria-label={eventIsPinned ? 'Unpin event' : 'Pin event'}
            >
              <PinIcon filled={eventIsPinned} className="w-4 h-4" />
            </button>

            {/* Phase badge */}
            {effectivelyLive ? (
              <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-600">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                {/* UX-P051 (#1710): the phase badge read both fields raw and
                    printed "Mon, August 10th at 8:00 PM EDT · 0.0" on a game
                    ESPN had not started.

                    ITS BOTH-REQUIRED RULE IS DELIBERATELY REPLACED, not
                    preserved — that is a stated behaviour change. `period &&
                    game_clock ?` was never a principle, and once a clock already
                    spelled inside the period is dropped as a duplicate, keeping
                    it would have made this badge read "LIVE" on every NBA/WNBA
                    game (measured: "10:00 - 1st Quarter" + "10:00"). It also
                    means a baseball game whose detail is "Top 2nd" with no clock
                    now says so instead of the generic word. */}
                {liveClockLabel || "LIVE"}
              </span>
            ) : isFinished ? (
              <span className="text-[10px] font-semibold text-text-muted">Final</span>
            ) : isSuspended ? (
              /* live/048 — the branch that did not exist. Without it a
                 suspended match fell through to "Pregame", which is the same
                 lie as "Final" told in the other direction: this one already
                 started. It gets its own badge and no start time, and the hero
                 says why in a sentence below. */
              <span
                className="text-[10px] font-semibold text-text-muted"
                title={venueSettledSentence ? VENUE_SETTLED_DESCRIPTION : SUSPENDED_DESCRIPTION}
                data-testid="event-hero-suspended"
                data-venue-settled={venueSettledSentence ? "true" : undefined}
              >
                {/* #6381 — the venue's own grade outranks our silence. When a
                    source that carried this match's markets has settled them, the
                    badge says so (and names the graded score when there is
                    one) instead of denying a result the page draws one screen
                    below. `venueSettledSummary` returns null on every other
                    row, so the branch below is unchanged for them. */}
                {/* CERT-786 — the shared summary, so the hero says exactly what
                    the card the reader tapped said. The page-level sentence
                    stays on the `title`, which has room for it. */}
                {/* #2786 — HOME-AWAY, matching this page's own hero, which
                    stacks the home score above the away score. */}
                {venueSettledSentence ??
                  suspendedSummary(event?.away_score, event?.home_score, "home-away")}
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                <span className="text-[10px] text-amber-500 font-medium">
                  {/* #6031 — the word, and only the word. #3211 suppressed the
                      countdown once `hasStarted`, which left this branch
                      suppressing a countdown to a moment in the past while
                      still printing "Pregame" over a "Since Start" chart. The
                      two-hour hole this falls into, and why the grace is not
                      the thing to widen, are in `startBadgeLabel`. */}
                  {startBadgeLabel(hasStarted, gameCountdown)}
                </span>
              </span>
            )}
          </div>

          {/* Broadcast + date/time + freshness */}
          <div className="flex items-center gap-2">
            {/* #5741 — A BROADCAST IS A PROMISE ABOUT THE FUTURE, so it is
                gated on the same state the badge two lines up reads. It was
                gated on the field's presence and nothing else, which left the
                chip as the only element in this row with no opinion about
                whether the game is over: `/events/15312659` (Diamondbacks 2,
                Marlins 4, Final) told the reader to watch it on
                "MLB.TV, DBACKS.TV, Marlins.TV".

                THE RULE IS NOT NEW AND IS NOT MINE — this page was the last
                holdout of three surfaces. `EventCard`'s footer already reads
                `!isFinished && !isSuspended` (CERT-792) and iOS's hero already
                reads `EventDetailView.showsBroadcast` (#4002). Adopted verbatim
                rather than designed, so the three cannot drift.

                🔴 NOT `effectivelyLive`, which the issue recommended: pregame
                is the chip's whole job — "the hero's real estate is game state
                — pregame start time + broadcast" (L2-157, fifteen lines below)
                — and a positive live gate would delete it for every reader who
                has not yet watched the game. The pregame arm of the guard below
                exists to kill exactly that fix.

                `isSuspended` is the page's ONE `hasNoReportedResult` answer
                (#4015) and is deliberately only READ here: a match nobody can
                report on is not one to tune into either, which is #3821's false
                promise worn as a chip. */}
            {event.espn?.broadcast && !isFinished && !isSuspended && (
              <span
                className="px-1.5 py-0.5 rounded bg-surface-elevated text-[10px] font-semibold text-text-secondary tracking-wide"
                data-testid="event-hero-broadcast"
              >
                {event.espn.broadcast}
              </span>
            )}
            {/* #8336 — a live game prints NOTHING here. This slot used to carry a
                `⟳ 20s` poll ticker, a second freshness indicator one row below
                the header's age badge — and on a stream-fed page a promise of a
                poll nobody was waiting on. The header badge is the page's one
                answer to "how fresh is this" (#4469). */}
            {effectivelyLive ? null : (
              <span className="text-[10px] text-text-muted" data-testid="event-hero-start">
                {/* #3829 — the day is real, the hour may not be. The label and
                    the reason it is shaped this way live in
                    `formatEventStartLabel`, beside the state that selects it. */}
                {formatEventStartLabel(event.commence_time, startClock)}
              </span>
            )}
          </div>
        </div>

        {/* L2-157 (Alex ruling): internal ranking taxonomy pills
            ("competitive / regular season / Playoff Race / Major") are NOT user
            information and are stripped from the hero. The hero's real estate is
            game state — pregame start time + broadcast (above), LIVE the score
            (below). Tags are still computed backend-side for ranking. */}

        {/* Teams + Score + Giant Probability — v2 centered layout */}
        <div className="px-5 sm:px-6 py-4 sm:py-5">
          <div className="flex items-center justify-between">
            {/* Home Team */}
            <div className="flex flex-col items-center flex-1">
              {/* #2447: ONE RESOLVER, BOTH SURFACES. The ladder below is
                  `home_team_data.logo_large` -> `espnTeamLogoByName` ->
                  initials, and both of the first two are TEAM resolvers. A
                  tennis player is not a team, so every US Open match fell
                  straight through to initials while the register — four
                  sections down this same page — held a censused photograph of
                  the same person. This adds the register to the FRONT of the
                  ladder and leaves every other rung exactly where it was. */}
              <TournamentPlayerFace
                eventId={eventId}
                sportKey={event.sport}
                homeName={event.home_team}
                awayName={event.away_team}
                side="home"
                size={56}
                /* #3787 — the payload's own pinned pair, in FRONT of the
                   bracket register. The register answers NOT_IN_REGISTER for
                   any match off the bracket, which is why this hero still drew
                   `DM`/`FT` for a US Open round-of-16 after #2447 shipped. */
                servedImage={servedParticipantImage(
                  event.home_image_url,
                  event.home_flag_url
                )}
                fallback={
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mb-1.5 overflow-hidden"
                style={{ backgroundColor: `${event.home_team_data?.primary_color || "#94A3B8"}15` }}
              >
                {(event.home_team_data?.logo_large || espnTeamLogoByName(event.home_team, event.sport_key)) ? (
                  <img
                    src={event.home_team_data?.logo_large || espnTeamLogoByName(event.home_team, event.sport_key)!}
                    alt=""
                    width={48}
                    height={48}
                    loading="lazy"
                    className="w-12 h-12 object-contain"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden"); }}
                  />
                ) : null}
                <span
                  className={`text-sm font-extrabold ${(event.home_team_data?.logo_large || espnTeamLogoByName(event.home_team, event.sport_key)) ? "hidden" : ""}`}
                  style={{ color: teamTextColor(event.home_team_data?.primary_color) || "var(--text-secondary)" }}
                >
                  {/* #7270 — the badge policy lives in `lib/teamShortName.ts`, which
                      owns the unshippable list. This hero used to inline its own copy
                      of the initials rule and painted `ASS` on a live Big 12 game. */}
                  {shippableCrestBadge(event.home_team, event.sport_key ?? event.sport)}
                </span>
              </div>
                }
              />
              <TeamNameLink
                name={event.home_team}
                sportKey={event.sport}
                className="text-xs font-semibold text-text-primary hover:underline"
              >
                {heroShortNames.home}
              </TeamNameLink>
              {/* #5720 — `recordReadsAsRecord`, computed once beside the scores. */}
              {recordReadsAsRecord &&
                (event.standings_context?.home || event.home_team_data?.record) && (
                <span className="text-[11px] text-text-muted">
                  {event.standings_context?.home || event.home_team_data?.record}
                </span>
              )}
              {(isLive || isFinished || hasStarted) && bestHomeScore !== null && (
                /* L2-163 Item 2a: once there's a real score it is the hero's
                   biggest element after the probability — Alex's 0-4 exhibit
                   rendered it nearly invisible at text-2xl. */
                <span className="text-4xl sm:text-[42px] font-black text-text-primary tabular-nums font-mono leading-none mt-1">
                  {bestHomeScore}
                </span>
              )}
            </div>

            {/* Center: Giant Probability (live/pregame) OR winner treatment (settled)

                #5866 — `min-w-0` and NO `flex-shrink-0`, and the phone padding
                is `px-1`. The three columns are `flex-1` / this / `flex-1`
                around a non-shrinking `w-14` crest, so while this block refused
                to shrink its max-content width DICTATED the row and
                `justify-between` pushed the overflow onto the away column: a
                live K League hero put the away crest's right edge at 406.4 in a
                390 viewport, clipped rather than scrollable
                (`scrollWidth` stayed 390).

                Measured at 390px on today's NFL pregame hero: budget 204.4,
                used 204.5 — HEADROOM −0.1px BEFORE the game goes live and adds
                three more lines to this same block. Two different children can
                be the widest one (the probability pair at 188.5px here; the
                `+N pts <team> since open` chip on a long club name), which is
                why the fix bounds the BLOCK rather than any one line. */}
            <div className="flex flex-col items-center px-1 sm:px-4 min-w-0">
              {isFinished ? (
                /* Settled: winner name + chip + the result in the sport's own
                   units, no big number (mirrors FuturesHero's resolved rule).
                   The win-prob journey stays in the chart below. Extracted to
                   `SettledOutcomeHero` by #2443 so the outcome is renderable —
                   and therefore assertable — on its own. */
                <SettledOutcomeHero
                  outcome={settledOutcome}
                  // #5720 — the same predicate the record gate reads, named once
                  // rather than spelled twice: two copies of "does this hero have
                  // a score pair" is two things to keep in step.
                  hasNumericScore={heroScorePairPresent}
                  winnerPregameProb={settledWinnerPregameProb}
                />
              ) : (
              // #2085: the two sides are ONE decision — see
              // `EventHeroProbabilityPair` and `resolveProbability`. This used
              // to be four spans rounding `homeProb` and `awayProb`
              // independently, which prints 101 whenever `home * 100` lands on
              // a half-percent (8.2% of scheduled/live events, measured).
              <EventHeroProbabilityPair
                homeProb={homeProb}
                awayProb={awayProb}
                homePct={homePct}
                awayPct={awayPct}
                // #6238 — OMIT the away slot, do not dash it. At 48px an
                // em-dash is a solid rectangle and `–  ▬%` reads as a number
                // that failed to draw. See the prop's own note.
                awayWithheld={awaySlotWithheld}
                homeColor={event.home_team_data?.primary_color}
                awayColor={event.away_team_data?.primary_color}
                probSourceLabel={probSourceLabel}
                // live/034 S2 — count to the new value only when it is arriving
                // by push. On the 32s poll a jump IS the honest rendering of
                // what happened; animating it would imply a continuity between
                // two readings half a minute apart that the data does not have.
                animate={streamConnected}
                // #5890 — the no-reading copy's tense. "No price yet" promises a
                // price that is still coming; on a match that has kicked off,
                // the prices came and were withdrawn. The page's own three
                // answers, not a fourth reading of the clock: `isSuspended` is
                // the one `hasNoReportedResult` answer computed above.
                started={isLive || isFinished || isSuspended}
                // #6438 — the page's ONE settled answer, reused. `Settled ·
                // Draw 0-0` in the pill and "No price" between the crests were
                // the same card describing the same graded match two ways, and
                // the loud one was wrong. Derived from `venueSettledSentence`
                // rather than re-reading `event.venue_settled`, so the pill and
                // this slot cannot drift apart — the exact failure
                // `venueSettledSummary` was centralised to end.
                venueSettled={venueSettledSentence !== null}
              />
              )}

              {/* Trend indicator — change since opening (live/pregame only).

                  #5719 — POINTS, and the difference of the PRINTED levels.

                  TWO DEFECTS ON ONE LINE. The caption said `%` over a move
                  measured in percentage POINTS: Michigan 34 -> 75 is +41
                  points, and as a percentage it is +121. It printed `+41%`
                  directly above `Opened 34% – 66%`, which invites the reader to
                  do the subtraction and then answers in the wrong unit. Tenth
                  surface of the family #5623 / #5669 / #5686 walked through, and
                  the biggest one.

                  And it rounded a SECOND, DIFFERENT QUANTITY. The raw difference
                  of the two probabilities is not the difference of the two
                  integers this block prints around it, and the two disagree
                  whenever their fractional parts straddle a boundary — #2951's
                  finding, which #3051 caught on a tennis hero captioning `+3`
                  between a printed 91 and a printed 95. Subtracting the PRINTED
                  levels is the only definition under which `shown − caption =
                  opened` holds on the reader's screen, which is the whole reason
                  this hero prints all three numbers.

                  🔴 SUBTRACTED HERE RATHER THAN THROUGH `renderedDuelMovePoints`,
                  and that is not an oversight. #2951's helper re-derives BOTH
                  pairs from probabilities. This hero's `homePct` may instead be
                  the SERVED `current_odds.{home,away}_rendered_percent` — see
                  `withRenderedPercents`, which takes them only on the branches
                  that read `odds` — so re-deriving would measure the move against
                  a level the page did not print, reintroducing the exact
                  contradiction the helper exists to prevent. The rule is
                  "difference of the printed levels"; `homePct` and
                  `openingHomePct` ARE the printed levels, whichever end decided
                  them.

                  A sub-point move now prints nothing rather than `+1` between two
                  equal numbers. That is #2951's own trade, taken deliberately:
                  a move the levels cannot express is a move this line may not
                  claim.

                  #5995 — THE JOURNEY, BECAUSE ON A SCORING SPORT THERE IS NO
                  SAFE WORD FOR THE UNIT. #5719 left this line printing
                  `+49 pts Giants since open` directly above a 21–14 scoreline:
                  three numbers in one block, one of them a score, and `pts` is
                  the word for the other two. `+7 pts Eagles` over a 7–3 game
                  was the filed specimen; the marquee frame at `+49` is worse,
                  because a number larger than either team's score reads as a
                  running total rather than a delta. `pp` is jargon (D102) and a
                  hero-only unit word would break the family `pts` belongs to
                  (#5623 / #5669 / #5686), so the repair is to stop naming a
                  unit: print the two LEVELS and let the arrow carry direction.
                  The reader no longer has to trust a unit, or subtract at all.

                  This keeps #5719's rule rather than replacing it. "Difference
                  of the printed levels" was only ever a way to make
                  `shown − caption = opened` hold on screen; printing the levels
                  themselves is that same invariant with the arithmetic removed,
                  so the caption is now correct BY CONSTRUCTION and the whole
                  class of second-rounding defects (#2951, #3051) cannot recur
                  on this line.

                  ONE FORMATTER ON ONE SENTENCE, SINCE #6064. This line used to
                  run two: the current level was the bare integer
                  `EventHeroProbabilityPair` printed, the opening level went
                  through `formatProbability`, and they disagreed at the
                  boundary — a live blowout put `100%` in the hero while the
                  line below said `>99%` for the same value. #5995 matched each
                  end to ITS OWN neighbour, which was right while the hero
                  refused to clamp, and filed the disagreement as #6064 rather
                  than smuggling it into a caption fix.
                  #6064 closed it at the source: the hero now clamps too, so
                  both ends go through `formatProbability` and "never contradict
                  the number printed next to you" and "agree with yourself" are
                  the same requirement. The current end MUST keep passing
                  `homeProb` — with only `rendered` the clamp has no probability
                  to test and `100%` comes straight back.

                  Defect 3 on this line is NOT fixed here: the up arrow and its
                  caption are `text-emerald-*`, which emits no CSS at all, so
                  green-up has never rendered while red-down always has. That is
                  #4040 — 195 dead numbered classes tree-wide — and it is a
                  config decision with a blast radius, not this ship's. */}
              {!isFinished && openingHomePct !== null && homePct !== null && (() => {
                const deltaPoints = homePct - openingHomePct;
                if (deltaPoints === 0) return null; // Did not move on screen — say nothing
                const homeShort = heroShortNames.home;
                const isPositive = deltaPoints > 0;
                return (
                  /* #5866: `min-w-0` so this row may shrink and its caption
                     wrap, instead of setting the centre block's width from a
                     club name. The arrow keeps `flex-shrink-0` — a squashed
                     3.5px glyph is not a saving. */
                  <div className="flex items-center gap-1.5 mt-2 min-w-0">
                    <svg
                      className={`w-3.5 h-3.5 flex-shrink-0 ${isPositive ? "text-emerald-500" : "text-red-500"}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      {isPositive ? (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 10l7-7m0 0l7 7m-7-7v18" />
                      ) : (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                      )}
                    </svg>
                    <span className={`text-xs font-semibold min-w-0 text-center ${isPositive ? "text-emerald-600" : "text-red-500"}`}>
                      {/* The two levels, both through `formatProbability` —
                          the same call `Opened …` makes two lines below and,
                          since #6064, the same rule the hero above applies. */}
                      {homeShort}{" "}
                      {formatProbability(openingHomeProb, { rendered: openingHomePct })}
                      {" → "}
                      {formatProbability(homeProb, { rendered: homePct })} since open
                    </span>
                  </div>
                );
              })()}

              {/* Opening odds (faint) — live/pregame only */}
              {!isFinished && openingHomeProb !== null && (
                <div className="mt-1.5">
                  <span className="text-[11px] text-text-muted">
                    {/* #2085 — same pair, same rule. `opening_odds` derives its
                        away side as `1 - home` on the backend too, so this line
                        printed 101 for exactly the same reason the hero did. */}
                    {/* #6238 — the separator and the away figure go together.
                        `formatProbability(null)` is "-", so leaving this pair
                        intact printed `Opened 64% – -`, which reads as a
                        missing number rather than an inapplicable one. */}
                    {/* #6614 — this pair's OWN answer, not the hero pair's.
                        `awaySlotWithheld` here deleted a real, independently
                        sourced opening away price on 9 of 25 live soccer cards:
                        the opening pair is de-vigged across the board (#1011)
                        and sums to ~0.76, so its away leg is a price, not a
                        complement. The hero's current pair above legitimately
                        answers differently on the same screen — it is 25/25 a
                        complement — which is why each locus asks separately. */}
                    Opened {formatProbability(openingHomeProb, { rendered: openingHomePct })}
                    {!openingAwaySlotWithheld && <>{" "}{"–"} {formatProbability(openingAwayProb, { rendered: openingAwayPct })}</>}
                  </span>
                </div>
              )}

              {/* Source label — live/pregame only */}
              {!isFinished && probSourceLabel && (
                <div className="mt-1 flex items-center gap-1.5 min-w-0">
                  <span className="text-[11px] text-text-muted min-w-0 text-center">
                    {probSourceLabel}
                  </span>
                  {heroConfidence && <SignalBars tier={heroConfidence.tier} />}
                </div>
              )}

              {/* Projected final score — derived from spread + total, no gambling jargon.

                  #2441: gated on the sport DECLARING that a derived spread is
                  a real quantity here. The projection is a points model; on a
                  tennis match it is a fabricated scoreline in a unit the sport
                  does not have. An undeclared sport gets the same silence, by
                  design — see `UNSCORED_IN_POINTS`. */}
              {/* #5257: and gated on there still being a result to forecast.
                  The old test was a DENYLIST of two terminal states, so a
                  `suspended` event — and a `scheduled` one long past its own
                  kickoff — fell straight through it and printed a projected
                  final under this card's own "No result reported" badge. This
                  is #5206's defect one card up, and #4018's line applies as
                  verbatim as it did there: a forecast and a result are two
                  questions and they get two predicates. `isSuspended` is the
                  page's ONE `hasNoReportedResult` answer (computed above, #4015)
                  and is the same one the badge four lines up is drawn from, so
                  the card can no longer ask the question one way and answer it
                  the other. */}
              {/* #5697 AC2: and gated on the reader being able to see the state
                  the forecast is about. `projectionHasGameStateToFrame` is
                  computed beside the scores it reads — a live game with no score
                  pair prints no projected final, a game that has not kicked off
                  still does. */}
              {/* #8156: and gated on the pair being a result the sport can
                  produce. The `Math.round` below is applied per side, so any
                  pair under a run apart lands on one integer and a no-tie sport
                  printed an impossible final (`3 – 3` on live MLB).
                  `projectedPairIsAPossibleResult` is computed beside the other
                  projection gates and rounds exactly the way this line does —
                  the two must never drift, which is why the rounding is not
                  written out twice in two different expressions. */}
              {/* #4885: and gated on the pair being reachable from the score
                  the hero prints: `Projected final: 3 – 2` under a live `4 – 2`
                  is always false. `projectedPairIsReachableFromTheScore` rounds
                  the way this line does and reads `bestHomeScore`/`bestAwayScore`,
                  the values in the score slots, never the event row. */}
              {sportVocab(event.sport || undefined).hasDerivedSpread &&
                historyData?.pm_spread_data?.projected_final &&
                event.status !== "completed" && event.status !== "closed" &&
                !isSuspended &&
                projectionHasGameStateToFrame &&
                projectedPairIsAPossibleResult &&
                projectedPairIsReachableFromTheScore &&
                historyData.pm_spread_data.projected_final.home_score > 0 &&
                historyData.pm_spread_data.projected_final.away_score > 0 && (
                <div className="mt-1.5">
                  <span className="text-[11px] text-text-muted">
                    Projected final: {Math.round(historyData.pm_spread_data.projected_final.home_score)}{"\u2009\u2013\u2009"}{Math.round(historyData.pm_spread_data.projected_final.away_score)}
                  </span>
                </div>
              )}
            </div>

            {/* Away Team */}
            <div className="flex flex-col items-center flex-1">
              {/* #2447, the other side. Same ladder, same new first rung. */}
              <TournamentPlayerFace
                eventId={eventId}
                sportKey={event.sport}
                homeName={event.home_team}
                awayName={event.away_team}
                side="away"
                size={56}
                /* #3787, the other side. Same pair, same precedence. */
                servedImage={servedParticipantImage(
                  event.away_image_url,
                  event.away_flag_url
                )}
                fallback={
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center mb-1.5 overflow-hidden"
                style={{ backgroundColor: `${event.away_team_data?.primary_color || "#64748B"}15` }}
              >
                {(event.away_team_data?.logo_large || espnTeamLogoByName(event.away_team, event.sport_key)) ? (
                  <img
                    src={event.away_team_data?.logo_large || espnTeamLogoByName(event.away_team, event.sport_key)!}
                    alt=""
                    width={48}
                    height={48}
                    loading="lazy"
                    className="w-12 h-12 object-contain"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden"); }}
                  />
                ) : null}
                <span
                  className={`text-sm font-extrabold ${(event.away_team_data?.logo_large || espnTeamLogoByName(event.away_team, event.sport_key)) ? "hidden" : ""}`}
                  style={{ color: teamTextColor(event.away_team_data?.primary_color) || "#64748B" }}
                >
                  {/* #7270 — see the home tile above; same policy, same helper. */}
                  {shippableCrestBadge(event.away_team, event.sport_key ?? event.sport)}
                </span>
              </div>
                }
              />
              <TeamNameLink
                name={event.away_team}
                sportKey={event.sport}
                className="text-xs font-semibold text-text-primary hover:underline"
              >
                {heroShortNames.away}
              </TeamNameLink>
              {/* #5720 — same gate as the home side; see `recordReadsAsRecord`. */}
              {recordReadsAsRecord &&
                (event.standings_context?.away || event.away_team_data?.record) && (
                <span className="text-[11px] text-text-muted">
                  {event.standings_context?.away || event.away_team_data?.record}
                </span>
              )}
              {(isLive || isFinished || hasStarted) && bestAwayScore !== null && (
                /* L2-163 Item 2a: score is the hero's biggest element after the
                   probability once the game is underway. */
                <span className="text-4xl sm:text-[42px] font-black text-text-primary tabular-nums font-mono leading-none mt-1">
                  {bestAwayScore}
                </span>
              )}
            </div>
          </div>

          {/* #3330: the games, under the sets, while it is still being played.
              Centered under the row rather than inside either column, because
              one line states BOTH sides and splitting it would ask the reader
              to re-pair `6` with `3` across the probability. Reads
              left-to-right against the two columns — see `liveGamesLine`. */}
          {liveGamesLine && (
            <div className="flex flex-wrap items-center justify-center gap-2 mt-3">
              <span className="text-[13px] font-semibold text-text-primary tabular-nums font-mono bg-surface-elevated px-2.5 py-1 rounded">
                {liveGamesLine}
              </span>
              {/* HOW OLD THIS GAMES COUNT IS (#3242).
                  It is NOT the badge above it. That one reads the freshest
                  win-probability write and can honestly say `1s ago` while this
                  line is a full beat behind: measured on production 2026-09-05,
                  ESPN published a match's first game at 15:12 and we showed it
                  at 15:22. The beat is ~10 minutes, so a games count with no age
                  on it is a confident number that may be from ten minutes ago.
                  `observed_at` is when we last CONFIRMED this line with ESPN, so
                  an unchanged score still reads fresh, and a beat that stalls
                  (#3316 measured a 42.8-minute hole) makes the chip go Stale
                  rather than letting the page keep a straight face. */}
              <FreshnessChip asOf={event.linescore?.observed_at} />
            </div>
          )}

          {/* Stakes context from standings */}
          {event.standings_context?.stakes && (
            <div className="text-center mt-3">
              <span className="text-[10px] text-text-muted bg-surface-elevated px-2 py-0.5 rounded">
                {event.standings_context.stakes}
              </span>
            </div>
          )}

        </div>



      </div>

      </SectionErrorBoundary>

      {/* Win Probability Chart */}
      {/* UX-P055: per-section boundaries. The children below are deliberately
          NOT re-indented — a wrapper that reflows ~900 lines buries the one
          thing a reviewer needs to check, which is where each boundary opens
          and closes. `resetKey` is the fetched object, whose identity changes
          only on a refetch, so a section that failed on a bad payload retries
          when the next one lands instead of staying dead for the session. */}
      {/* #3612: suppressed outright when nothing has ever priced this event and
          it is not in the future — see `suppressWinProbabilityCard`. Wrapped
          rather than re-indented, per the note above. */}
      {!suppressWinProbabilityCard && (
      <SectionErrorBoundary label="The win probability chart" resetKey={historyData}>
      {/* #3612: the guard's handle. The heading text is not usable on its own —
          the fullscreen modal below carries a second "Win Probability" h2 — and
          a class selector would be a test about styling (ux/1192). */}
      <div className="bg-surface-card rounded-card shadow-card overflow-hidden" data-testid="win-probability-card">
        {/* Chart Header — v2: title + freshness */}
        <div className="px-4 sm:px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-[13px] font-semibold text-text-primary">Win Probability</h2>
            {/* #8336 — no ticker here either: the header's age badge is the
                page's one freshness answer, and this was its third copy. */}
            {/* L2-112 Item 1: chart-card "Final" removed — the hero phase badge +
                winner chip already mark the game final (killed the "Final … Final"
                dup Alex flagged). The fullscreen modal keeps its own label. */}
          </div>
          <button
            onClick={() => setChartFullscreen(true)}
            className="p-1.5 rounded-md hover:bg-surface-elevated text-text-muted hover:text-text-primary transition-colors"
            title="Fullscreen"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="10 2 14 2 14 6" />
              <polyline points="6 14 2 14 2 10" />
              <line x1="14" y1="2" x2="9.5" y2="6.5" />
              <line x1="2" y1="14" x2="6.5" y2="9.5" />
            </svg>
          </button>
        </div>

        {/* Chart Content */}
        <div className="p-4 sm:p-5">
          {historyLoading ? (
            <div className="h-48 flex items-center justify-center">
              <LoadingSpinner size="sm" />
            </div>
          ) : historyError ? (
            <div className="h-48 flex flex-col items-center justify-center text-sm text-text-secondary gap-2">
              <span>Unable to load history</span>
              <span className="text-xs text-text-muted">
                {historyError.message || 'Unknown error'}
              </span>
              <button
                onClick={() => refreshHistory()}
                className="text-xs text-blue-600 hover:underline mt-2"
              >
                Retry
              </button>
            </div>
          ) : (
            /* #3612: THE PAGE NO LONGER KEEPS ITS OWN COPY OF THE EMPTY STATE.
               The arm that stood here — an unconditional "Tracking will begin
               when odds are available" — returned BEFORE `OddsChart` mounted,
               so the chart's own status-aware empty state (cleaned under ruling
               142: "Chart available at game time" for `scheduled`, "No history
               data available" otherwise) was unreachable for exactly the
               population that needed it. Two copies of one sentence, and the
               page's copy was the one that could not tell a finished game from
               an upcoming one. One definition now, and it lives in the
               component that owns the chart. */
            <OddsChart
              history={historyData?.history ?? []}
              homeTeam={event.home_team}
              awayTeam={event.away_team}
              commenceTime={event.commence_time}
              /* #8215 — served provenance, never re-derived: `false` means this hour is the
                 venue's expected resolution time, not a kick-off, so it is not a "Since Start"
                 cut. The fullscreen chart below passes no `chartStartTime`, so it needs this
                 directly. */
              commenceTimeIsKickoff={historyData?.commence_time_is_kickoff}
              isLive={effectivelyLive}
              bookmakerHistory={historyData?.bookmaker_history}
              espnHistory={historyData?.espn_history}
              winProbHistory={historyData?.win_prob_history}
              winProbSources={historyData?.win_prob_sources}
              scoringPlays={historyData?.scoring_plays}
              aggregateLine={historyData?.aggregate_line ?? undefined}
              backendBlendServed={backendBlendServed}
              completedAt={historyData?.completed_at ?? undefined}
              eventId={eventId}
              eventStatus={event.status}
              periodBoundaries={periodBoundaries}
              homeTeamColor={event.home_team_data?.primary_color || undefined}
              awayTeamColor={event.away_team_data?.primary_color || undefined}
              homeTeamLogo={event.home_team_data?.logo_small || undefined}
              awayTeamLogo={event.away_team_data?.logo_small || undefined}
              homeTeamAbbrev={event.home_team_data?.abbreviation || undefined}
              awayTeamAbbrev={event.away_team_data?.abbreviation || undefined}
              awayWithheld={awaySlotWithheld}
              onActivePointChange={setActiveChartPoint}
              onRenderedDomain={handleRenderedDomain}
              chartStartTime={sharedChartDomain?.start}
              chartEndTime={sharedChartDomain?.end}
              sharedTicks={sharedChartDomain?.ticks}
            chartLabelFormat={sharedChartDomain?.labelFormat}
              externalTimeRange={chartTimeRange}
              onTimeRangeChange={handleChartTimeRangeChange}
            />
          )}
          {/* Game Play Card — shows score/period/play as user hovers the chart */}
          {(effectivelyLive || isFinished || hasStarted) && historyData ? (
            <GamePlayCard
              activePoint={activeChartPoint}
              homeTeam={event.home_team}
              awayTeam={event.away_team}
              homeTeamColor={event.home_team_data?.primary_color || undefined}
              awayTeamColor={event.away_team_data?.primary_color || undefined}
              homeTeamLogo={event.home_team_data?.logo_small || undefined}
              awayTeamLogo={event.away_team_data?.logo_small || undefined}
              lastPoint={lastChartPoint}
              /* #6238 — the same single derivation the hero reads, handed to
                 the readout below the chart. On `/events/15305024` (2–2 final)
                 this card printed `Citizen 1% — Steelers 99%` two cards above
                 its own "Tie — Won" markets row. */
              awayWithheld={awaySlotWithheld}
              /* #6684 — this badge read `Bottom 8th 0:00` on every live MLB
                 game. The KEY, not a derived boolean: `trustedLiveClock` holds
                 the other three rules about painting ESPN's clock and holds
                 this one too. See the prop's own note. */
              sportKey={event.sport || undefined}
            />
          ) : null}
        </div>

        {/* Chart footer: the per-sportsbook table's disclosure.

            #6421 moved the MARKUP to `sportsbooksDisclosure` (defined beside
            `suppressWinProbabilityCard`) so the same disclosure can also stand
            on its own when this card is suppressed — history absence is not
            price absence. Nothing about it changed; the rationale below is
            still the rationale, and it stays here because here is where a
            reviewer of the chart card will look for it. */}
        {sportsbooksDisclosure("chart-footer")}
        {/* ═══ #4083 (D91's RESTORE): ONE SOURCE LEGEND, AND IT IS THE
                CHART'S OWN ═══

                A second legend used to stand here — seven always-on chips
                (`BainLuck`, `Sportsbooks`, `Kalshi`, `Polymarket`, `MLB Model`,
                `Bain Luck Model`, `ESPN`) — directly beneath the chart legend
                that already names the same seven. Measured on
                `/events/15306264` at 390px, 2026-09-08T22:40Z, the card read:

                    ——— Bain Luck        + 6 sources ⌄     <- OddsChart's legend
                    ——— BainLuck   ——— Sportsbooks   ——— Kalshi
                    ——— Polymarket ——— MLB Model     ——— ESPN     Sources ⌄
                    ——— Bain Luck Model                          <- this strip

                Alex, relayed 2026-09-08 2:05pm PT: *"we had this 99% right for
                months, where the sourcing was clear without coming across as an
                endorsement … the default was the BainLuck aggregated line, but
                you could click in to see the underlying sources."* The click-in
                is `+ N sources`, ratified as UX-P154 panel 3B — and it revealed
                nothing, because this strip had already spread every source name
                across three lines. An always-on roll-call of seven suppliers is
                the half that reads as endorsement rather than as sourcing.

                THE SETS WERE IDENTICAL, so nothing is lost: `+ 6 sources`
                counts `OddsChart`'s `resolvedSources`, and this strip was
                `BainLuck` + `Sportsbooks` + those same six minus the sportsbook
                aggregate. The surviving legend is also the STRICTER one — it is
                keyed off the series the chart actually draws, so it honours the
                stat-model wall-clock suppression that this strip did not, and
                it links each chip to `/events/{id}/models`.

                IT WAS ALSO WHERE WE SPELLED OUR OWN NAME WRONG. The chip above
                was a hard-coded `BainLuck` sitting two rows under the chart's
                `Bain Luck` — the one name we control, and the only one on the
                card spelled two ways. #2442's rule ("through the source
                registry, so this chip and the chart legend beside it cannot
                spell one supplier two ways") was written for suppliers and left
                the brand out; deleting the duplicate settles it rather than
                adding a second place to keep in step.

                ux/1034 B7's rule survives with it. Alex asked that the legend
                "pick [Polymarket] up without a deploy"; `resolvedSources`
                iterates `win_prob_history` and resolves every name and colour
                through `SOURCE_COLORS`, which is the same registry this strip
                was moved onto — so the payload still drives the list, one layer
                up.

                WHAT STAYS is the disclosure below, which never was a chart
                legend: it opens `BookmakerTable`, whose own first column is
                headed "Sportsbook". It was labelled `Sources`, which is why it
                read as a second copy of `+ N sources` stacked under the first.
                Naming the table it opens is what removes the collision.

                #3427 (the control painted off the phone edge at 390px: "… —
                Kalshi — Polymarket  Sou") was the chip group claiming its full
                intrinsic width beside a button with no `shrink-0`. The chip
                group is gone, so the overflow has no source — but the button
                keeps `shrink-0`, and its guard now holds the rule that no chip
                group returns to this row without wrapping. */}
      </div>

      </SectionErrorBoundary>
      )}

      {/* #6421: the same disclosure, standing on its own, when the card that
          used to carry it is suppressed. The prices are current and we hold
          them; only the CHART had nothing to draw. `suppressWinProbabilityCard`
          is untouched — this is the table finding its way out of the container,
          not the container coming back. */}
      {suppressWinProbabilityCard && hasBookmakerOdds && (
        <SectionErrorBoundary label="The sportsbook prices" resetKey={event}>
          <div
            className="bg-surface-card rounded-card shadow-card overflow-hidden"
            data-testid="sportsbook-prices-card"
          >
            {sportsbooksDisclosure("own-card")}
          </div>
        </SectionErrorBoundary>
      )}

      {/* Source Comparison removed — not useful, sources already visible in OddsChart */}

      {/* Score Differential Chart — only when projected/actual score data exists (L2-112 Item 4) */}
      {hasScoreDiffData && (
        <SectionErrorBoundary label="The score differential chart" resetKey={historyData}>
        <div className="bg-surface-card rounded-card shadow-card p-3 sm:p-4">
          {/* #6144: the card is named after the series it draws — see
              `scoreDiffHeading`. "Score Differential" where the played score is
              on the chart, "Projected Run Margin" (the unit is the one the
              margin map below uses) where the only line is the market's. */}
          <h3 className="text-sm font-semibold text-text-secondary mb-2 flex items-center gap-2">
            {scoreDiffHeading}
          </h3>
          <ScoreDifferentialChart
            history={historyData.history || []}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            commenceTime={event.commence_time}
            isLive={effectivelyLive}
            bookmakerHistory={historyData?.bookmaker_history}
            scoreHistory={historyData?.score_history}
            espnHistory={historyData?.espn_history}
            currentHomeScore={event.home_score}
            currentAwayScore={event.away_score}
            eventStatus={event.status}
            periodBoundaries={periodBoundaries}
            homeTeamColor={event.home_team_data?.primary_color || undefined}
            awayTeamColor={event.away_team_data?.primary_color || undefined}
            homeTeamLogo={event.home_team_data?.logo_small || undefined}
            awayTeamLogo={event.away_team_data?.logo_small || undefined}
            homeTeamAbbrev={event.home_team_data?.abbreviation || undefined}
            awayTeamAbbrev={event.away_team_data?.abbreviation || undefined}
            chartStartTime={sharedChartDomain?.start}
            chartEndTime={sharedChartDomain?.end}
            sharedTicks={sharedChartDomain?.ticks}
            chartLabelFormat={sharedChartDomain?.labelFormat}
            externalTimeRange={chartTimeRange}
            onTimeRangeChange={handleChartTimeRangeChange}
            /* ux/1034 B5: the same key the market maps below already take, so
               the three widgets on this page cannot disagree about whether
               `home_score` counts the thing the projection is quoted in. */
            sportKey={event.sport || undefined}
            /* live/073: same reason as `sportKey` — this note and the Games
               map's are the same claim about the same missing number, and one
               of them going stale is how the page tells a reader both that we
               hold the games and that we do not. */
            linescore={event.linescore}
            /* #3240: whether there is a games map below to point at — answered
               by the selectors MarketMapSection builds the card from, not by a
               second reading of the same payload. `/events/15304382` held a
               fresh 2-1 games line and no game-total market, so the note sent
               the reader to a card that was not on the page. */
            totalsMapPresent={totalsMapRenders(gameMarkets, event.status)}
            pmSpreadData={historyData?.pm_spread_data}
          />
        </div>
        </SectionErrorBoundary>
      )}

      {/* Market Map cards — Margin Map + Total Map */}
      {/* #3240: the mount condition is shared with `totalsMapRenders` above, so
          the note's idea of what is on the page and the page cannot diverge. */}
      {gameMarkets && marketMapSectionMounts(gameMarkets) && (
        <SectionErrorBoundary label="The market maps" resetKey={gameMarkets}>
        <MarketMapSection
          gameMarkets={gameMarkets}
          eventStatus={event.status}
          homeTeam={event.home_team}
          awayTeam={event.away_team}
          homeAbbr={event.home_team_data?.abbreviation || undefined}
          awayAbbr={event.away_team_data?.abbreviation || undefined}
          homeColor={event.home_team_data?.primary_color || undefined}
          awayColor={event.away_team_data?.primary_color || undefined}
          homeLogo={event.home_team_data?.logo_small || undefined}
          awayLogo={event.away_team_data?.logo_small || undefined}
          homeWinProb={event.current_odds?.home_probability ?? undefined}
          awayWinProb={event.current_odds?.away_probability ?? undefined}
          /* #5414: `current_odds.home_spread` is a key the API has never
             emitted — it serialises the same column as `spread` — so this prop
             has been null on every render since it was added, and the card's
             PRE-GAME tile has always taken its closest-to-50%-rung fallback.
             Kept, correctly spelled, as the second rung behind the opening
             line: it is the right answer for a live card with no opening
             quote, and it is the one `hasDerivedSpread` governs. */
          homeSpread={event.current_odds?.spread ?? null}
          overUnder={event.current_odds?.over_under ?? null}
          /* #5414: what the market quoted BEFORE play, which is what the three
             markers labelled `Pre-game` are asking for. Served by the detail
             route as of this same change; `?? null` because 90.5% / 95.0% of
             events with sportsbook odds carry one, not all of them. */
          openingHomeSpread={event.opening_odds?.spread ?? null}
          openingOverUnder={event.opening_odds?.over_under ?? null}
          sportKey={event.sport || undefined}
          espnHistory={historyData?.espn_history as Array<{ period?: string; home_score?: number; away_score?: number; timestamp?: string }>}
          // live/073: the games this match was actually played to. Without it a
          // tennis map has nothing to put beside its pre-game quote, because
          // the scoreboard two cards up is counting sets.
          linescore={event.linescore}
          // #5206: the same decision the hero draws "No result reported" from,
          // handed down rather than re-derived. The map's own status chain has
          // no branch for a suspended match and falls through to the branch that
          // draws a forecast.
          noResultReported={isSuspended}
        />
        </SectionErrorBoundary>
      )}

      {/* Game Markets — Player Props + Matchups + Special Markets */}
      {gameMarkets && (gameMarkets.player_props.length > 0 || (gameMarkets.matchups?.length ?? 0) > 0 || (gameMarkets.other?.length ?? 0) >= 3) && (
        <div className="space-y-3">

          {/* UX-P055: #1722's actual crash site. This is the one boundary that
              is not speculative — an unpriced `other` row here took the whole
              route down on 2026-08-10, and 7 of 8 sampled settled MLB events
              carry 55-73 rows of that shape. */}
          {gameMarkets.player_props.length > 0 && (
            <>
            {/* UX-P098 (UX-AMBITION-1 slice 1) — THE DIVERGENCE leads.
                Alex's V1: the pregame page opens with the five questions that
                are actually live, not the whole prop set. On a real MLB payload
                that set is FORTY props; leading with it is the wall this
                replaces. The full set is one click away, below. */}
            <SectionErrorBoundary label="What's moving" resetKey={gameMarkets}>
            <PropDivergenceRail
              playerProps={gameMarkets.player_props}
              status={event.status}
            />
            </SectionErrorBoundary>

            <SectionErrorBoundary label="Player props" resetKey={gameMarkets}>
            <details className="group bg-surface-card rounded-card shadow-card overflow-hidden">
              <summary className="cursor-pointer select-none px-4 sm:px-5 py-3 text-[13px] font-semibold text-text-primary marker:content-none">
                All {countOf(gameMarkets.player_props.length, "prop", "props")}
                <span className="ml-1.5 text-[11px] font-normal text-text-muted group-open:hidden">
                  show
                </span>
                <span className="ml-1.5 text-[11px] font-normal text-text-muted hidden group-open:inline">
                  hide
                </span>
              </summary>
              <PlayerPropsDashboard
                data={gameMarkets}
                eventStatus={event.status}
                homeTeam={event.home_team}
                awayTeam={event.away_team}
                homeColor={event.home_team_data?.primary_color || undefined}
                awayColor={event.away_team_data?.primary_color || undefined}
                boxScore={event.box_score_data}
              />
            </details>
            </SectionErrorBoundary>
            </>
          )}

          {/* Matchups — H2H and 3-ball markets (golf) */}
          {(gameMarkets.matchups?.length ?? 0) > 0 && (
            <SectionErrorBoundary label="Matchups" resetKey={gameMarkets}>
            <div className="bg-surface-card rounded-card shadow-card overflow-hidden">
              <div className="px-4 sm:px-5 py-3 border-b border-surface-border/30">
                <h3 className="text-[13px] font-semibold text-text-primary">Matchups</h3>
              </div>
              <div className="divide-y divide-surface-border/30">
                {gameMarkets.matchups!.map((matchup, idx) => (
                  <div key={idx} className="px-4 sm:px-5 py-3">
                    <div className="flex items-center justify-between mb-2.5">
                      <span className="text-xs font-medium text-text-secondary">{matchup.market_name}</span>
                      {/* L2-52: source-name badge removed (blend-only). */}
                    </div>
                    <div className="space-y-2">
                      {matchup.outcomes.map((outcome, oidx) => {
                        // #3867 (CERT-2224 repair): the label routes through the
                        // contract; `Math.max(pct, 2)` below is still the bar's geometry.
                        const pct = renderedPercent(outcome.probability) ?? 0;
                        const isLeader = outcome.probability === Math.max(...matchup.outcomes.map(o => o.probability));
                        return (
                          <div key={oidx} className="flex items-center gap-3">
                            <span className={`text-xs font-medium w-[140px] sm:w-[180px] truncate ${isLeader ? "text-text-primary" : "text-text-secondary"}`}>
                              {outcome.name}
                            </span>
                            <div className="flex-1 h-5 bg-surface-elevated rounded-full overflow-hidden relative">
                              <div
                                className="h-full rounded-full transition-all duration-300"
                                style={{
                                  width: `${Math.max(pct, 2)}%`,
                                  backgroundColor: isLeader ? "#10B981" : "#94A3B8",
                                  opacity: isLeader ? 1 : 0.5,
                                }}
                              />
                            </div>
                            <span className={`text-xs font-bold tabular-nums w-10 text-right ${isLeader ? "text-text-primary" : "text-text-muted"}`}>
                              {pct}%
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            </SectionErrorBoundary>
          )}

          {/* Special Event Markets (auto-categorized other markets) */}
          {(gameMarkets.other?.length ?? 0) >= 3 && (
            <SectionErrorBoundary label="Special markets" resetKey={gameMarkets}>
              <SpecialEventMarkets
                data={gameMarkets}
                eventStatus={event.status}
                completedSets={completedSetsForTennis(event.sport, gameMarkets)}
                decidedSetsWinner={decidedSetsWinnerFor(event.sport, gameMarkets)}
                setsWon={tennisSetsWonFor(event.sport, gameMarkets)}
              />
            </SectionErrorBoundary>
          )}
        </div>
      )}

      {/* THE SCRIPT → THE DIVERGENCE → WHAT HIT (L2-118 Phase 1, duel = first
          consumer). Now live on the #195 payload: gameMarkets.props_script is a
          first-class GameMarketsResponse field carrying the PropMark contract.
          The section self-gates on an empty array; PropsSection returns null when
          items is empty. Forward-only marks render honest "pending" chips. */}
      {(() => {
        const propsScript = gameMarkets?.props_script;
        if (!Array.isArray(propsScript) || propsScript.length === 0) return null;
        // #1650: hold the WHAT HIT row to the same authority as the Player
        // Props card above it, using the raw typed rows on this same payload.
        const rawPropRowsByKey = indexPropRowsByScriptKey(gameMarkets?.player_props);
        return (
          <SectionErrorBoundary label="The script" resetKey={gameMarkets}>
          <PropsSection
            eventStatus={event.status}
            // #4866: the venue heads every matchup-level family with
            // "<away> vs <home>: ", which the hero above already says. Passing
            // the teams lets the section drop it — and ONLY when it is this
            // event's matchup, so a mis-attached fixture stays visible.
            matchup={{ home: event.home_team, away: event.away_team }}
            items={propsScript
              .map((p, i): PropMark => {
                const verified = verifyScriptGrade(p, rawPropRowsByKey);
                return {
                  key: p.key ?? i,
                  label: p.label,
                  pregame_mark: p.pregame_mark ?? null,
                  current: p.current ?? null,
                  graded_result: verified.graded_result,
                  graded_label: verified.graded_label,
                  // #5088: a window that closed mid-game is settled on its own
                  // while the section is still live. Without this the row falls
                  // to the SECTION state and `DivergenceValue` renders
                  // "script pending" + an em dash — because a closed window
                  // deliberately carries no price (#1735), so `pregame_mark` and
                  // `current` are both null. That is CERT-2535's blank row,
                  // reintroduced by the change that lifted CERT-2535's gate.
                  settled: p.settled ?? null,
                };
              })
              // #3874: drop the undecomposed-child-title rows (gotcha #18) — the
              // same row class, and the same decision, that the Additional Markets
              // card one section lower already drops. Nine of this page's twelve
              // marks were the parent title verbatim plus a remainder the phone
              // clipped away. PropsSection self-gates on an empty array.
              .filter((mark) => !isChildTitleMark(mark))}
          />
          </SectionErrorBoundary>
        );
      })()}

      {/* Standalone pace when no game markets section at all */}
      {gameMarkets && gameMarkets.totals.length === 0 && gameMarkets.player_props.length === 0 && gameMarkets.pace && gameMarkets.pace.projected_total && (
        <div className="bg-surface-card rounded-xl border border-surface-border px-4 py-3">
          <div className="flex items-center justify-between">
            {/* #2441: this carried its OWN three-name chain with "Total
                Points" as the else — the same defect as `sportVocab`'s old
                default, one component over. One registry decides the unit. */}
            <span className="text-xs font-bold text-text-primary">
              {(() => {
                const u = sportVocab(event.sport || undefined).unit;
                return u ? `${u.charAt(0).toUpperCase()}${u.slice(1)} pace` : "Scoring pace";
              })()}
            </span>
            <span className="text-base font-extrabold text-blue-500 tracking-tight">
              {gameMarkets.pace.projected_total}
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1 text-text-secondary text-micro">
            <span>{gameMarkets.pace.total_scored} scored</span>
            <span className="text-text-muted">&middot;</span>
            <span>{gameMarkets.pace.time_remaining_display}</span>
            <span className="text-text-muted">&middot;</span>
            <span>{Math.round(gameMarkets.pace.fraction_elapsed * 100)}% elapsed</span>
          </div>
        </div>
      )}

      {/* Line Movement Analysis — disabled until we have non-obvious insights.
          Current version just states the obvious ("Team X won, odds went up").
          TODO: Revamp with causal analysis, key moments, context. See backlog. */}

      {/* Series Probability — playoff series context */}
      {event.event_tags && (
        event.event_tags.includes("competitive_structure:series") ||
        event.event_tags.includes("competitive_structure:best_of_7")
      ) && event.current_odds?.home_probability != null && (() => {
        // Detect series wins from ESPN data or default to 0-0
        const homeSeriesWins = (event.espn as any)?.series_home_wins ?? 0;
        const awaySeriesWins = (event.espn as any)?.series_away_wins ?? 0;
        const gamesToWin = event.event_tags!.includes("competitive_structure:best_of_7") ? 4 : 4;
        return (
          <SectionErrorBoundary label="The series picture" resetKey={event}>
          <SeriesProbability
            homeWinProb={event.current_odds!.home_probability!}
            homeSeriesWins={homeSeriesWins}
            awaySeriesWins={awaySeriesWins}
            gamesToWin={gamesToWin}
            homeTeam={event.home_team}
            awayTeam={event.away_team}
            homeTeamColor={event.home_team_data?.primary_color || undefined}
            awayTeamColor={event.away_team_data?.primary_color || undefined}
          />
          </SectionErrorBoundary>
        );
      })()}

      {/* TOURNAMENT EXTENSIONS (UX-P152) — the sections a tournament adds to an
          ORDINARY event page, below the graph, for an event that belongs to a
          container: each player's chance of reaching each later round, and the
          match's other questions.

          Alex, 2026-08-28: "I thought that tournaments were containers for
          related events." They are, and this is a section of the event page
          rather than a page of its own — UX-P149's separate
          /tournaments/{slug}/matches/{key} surface is deleted, and a US Open
          match card now routes here like any other game card.

          Renders nothing for every event that is not in a registered
          tournament, and makes no request for one whose sport key rules it out. */}
      <SectionErrorBoundary label="Tournament" resetKey={eventId}>
        <TournamentExtensions eventId={eventId} sportKey={event.sport} />
      </SectionErrorBoundary>

      {/* Related Futures — bigger picture context (below charts) */}
      <SectionErrorBoundary label="Related futures" resetKey={eventId}>
      <RelatedFutures
        eventId={eventId}
        homeTeam={event.home_team}
        awayTeam={event.away_team}
        homeTeamColor={event.home_team_data?.primary_color || undefined}
        awayTeamColor={event.away_team_data?.primary_color || undefined}
        homeTeamLogo={event.home_team_data?.logo_small || undefined}
        awayTeamLogo={event.away_team_data?.logo_small || undefined}
        sportKey={event.sport || undefined}
        eventStatus={event.status}
        homeStandings={event.home_team_data?.standings || undefined}
        awayStandings={event.away_team_data?.standings || undefined}
        hasGameMarkets={!!gameMarkets && (gameMarkets.totals.length > 0 || gameMarkets.player_props.length > 0 || (gameMarkets.team_totals?.length ?? 0) > 0)}
        teamProgression={teamProgression || undefined}
      />
      </SectionErrorBoundary>

      {/* League page link */}
      {event.sport && (() => {
        const league = SPORT_KEY_TO_LEAGUE_PATH[event.sport!];
        if (!league) return null;
        return (
          <Link
            href={league.path}
            className="flex items-center justify-between px-4 py-3 rounded-xl bg-surface-card border border-surface-border hover:border-text-muted/30 transition-colors group"
          >
            <div className="flex items-center gap-2">
              <span className="text-sm">🏆</span>
              <span className="text-sm font-medium text-text-secondary group-hover:text-text-primary transition-colors">
                {league.label} Championship Grid
              </span>
            </div>
            <span className="text-text-muted group-hover:text-text-secondary transition-colors text-sm">→</span>
          </Link>
        );
      })()}

      {/* Related by sport tag — cross-content discovery.

          #8093: THIS ASKED FOR A CATEGORY AND A CATEGORY IS NOT A LEAGUE. A
          WNBA fixture requested `sport:basketball` and was dealt three NBA
          futures under a heading promising more of what it was looking at.
          `relatedRailQuery` adds the `league:` tag the event's own payload
          already carries, and keeps today's query as the fallback for the
          leagues that have no content of their own.

          #5973: AND THE RIGHT LEAGUE IS STILL THE SAME RAIL ON EVERY PAGE IN
          IT. The feed ranks a tag generically, so both WNBA pages and both NHL
          pages measured on 2026-09-22 drew an identical four — `Will Dallas
          Stars advance…` among them, on a Columbus v Buffalo game. Handing the
          rail the two sides lets cards that name one of them sort ahead of the
          rest. A preference, not a filter: the same cards in the same number,
          so no page loses the section the way an #8093-style narrowing would
          have. */}
      {(() => {
        const rail = relatedRailQuery(event.sport, event.event_tags);
        return rail ? (
          <SectionErrorBoundary label="Related content" resetKey={event.id}>
            <RelatedByTag
              tags={rail.tags}
              fallbackTags={rail.fallbackTags}
              excludeId={event.id}
              excludeType="event"
              limit={4}
              title={rail.title}
              fallbackTitle={rail.fallbackTitle}
              preferNames={participantNames(event.away_team, event.home_team)}
            />
          </SectionErrorBoundary>
        ) : null;
      })()}

      {/* Fullscreen Chart Modal */}
      {chartFullscreen && (
        <div className="fixed inset-0 z-50 bg-surface-card flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-text-primary">Win Probability</h2>
              {/* #8336 — the fullscreen view covers the header, so it carries the
                  header's own age badge — the same element, not a copy — rather
                  than a poll ticker: one freshness answer per screen. */}
              {ageBadge}
              {isFinished && (
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-text-muted" />
                  <span className="text-[10px] text-text-muted font-medium">Final</span>
                </div>
              )}
            </div>
            <button
              onClick={() => setChartFullscreen(false)}
              className="p-2 rounded-md hover:bg-surface-elevated text-text-muted hover:text-text-primary transition-colors"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="4" x2="4" y2="12" />
                <line x1="4" y1="4" x2="12" y2="12" />
              </svg>
            </button>
          </div>
          <div className="flex-1 p-4 min-h-0">
            <OddsChart
              history={historyData?.history ?? []}
              homeTeam={event.home_team}
              awayTeam={event.away_team}
              commenceTime={event.commence_time}
              /* #8215 — served provenance, never re-derived: `false` means this hour is the
                 venue's expected resolution time, not a kick-off, so it is not a "Since Start"
                 cut. The fullscreen chart below passes no `chartStartTime`, so it needs this
                 directly. */
              commenceTimeIsKickoff={historyData?.commence_time_is_kickoff}
              isLive={effectivelyLive}
              bookmakerHistory={historyData?.bookmaker_history}
              espnHistory={historyData?.espn_history}
              winProbHistory={historyData?.win_prob_history}
              winProbSources={historyData?.win_prob_sources}
              scoringPlays={historyData?.scoring_plays}
              aggregateLine={historyData?.aggregate_line ?? undefined}
              backendBlendServed={backendBlendServed}
              completedAt={historyData?.completed_at ?? undefined}
              eventId={eventId}
              eventStatus={event.status}
              fillContainer
              periodBoundaries={periodBoundaries}
              homeTeamColor={event.home_team_data?.primary_color || undefined}
              awayTeamColor={event.away_team_data?.primary_color || undefined}
              homeTeamLogo={event.home_team_data?.logo_small || undefined}
              awayTeamLogo={event.away_team_data?.logo_small || undefined}
              homeTeamAbbrev={event.home_team_data?.abbreviation || undefined}
              awayTeamAbbrev={event.away_team_data?.abbreviation || undefined}
              /* #6238 — the fullscreen chart is the same chart. A reader who
                 taps expand must not get the withheld number back. */
              awayWithheld={awaySlotWithheld}
            />
          </div>
        </div>
      )}
    </div>
    </ErrorBoundary>
  );
}

/* #7165 — the local `PinIcon` is gone; this page imports the shared one.
   It was one of three byte-identical copies whose unpinned state drew a goblet,
   and on THIS page that goblet sat beside "No result reported" on an ungraded
   match. The copy is what let the affordance be wrong in four places at once. */
