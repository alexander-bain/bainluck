"use client";

// #999 Event Concept Pages — L2-64 visual design. L2-113: colon-free URL
// `/event/<domain>/<slug>` (was `/event/event%3A<domain>%3A<slug>` — the "looks
// TERRIBLE" URL Alex flagged). The API still keys on `event:<domain>:<slug>`, so
// this route just reconstructs that key from the two path segments. When the
// backend returns a prettier, self-resolving `event.slug` (combat headliner+date),
// we canonicalize + client-replace up to it. Generic /event rendering of any
// individual-competitor event via /api/event/{key}.

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import Link from "next/link";
import { fetchEventConcept } from "@/lib/api";
import {
  marketsTracked,
  renderedFinishColumns,
  headlinerMatchup,
} from "@/lib/eventConceptDisplay";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import EventHeader from "@/components/event/EventHeader";
import MoversStrip from "@/components/event/MoversStrip";
import RaceToTitleChart from "@/components/event/RaceToTitleChart";
import TwoSidedTimeline from "@/components/event/TwoSidedTimeline";
import SoccerContainerHero from "@/components/event/SoccerContainerHero";
import EventLeaderboard from "@/components/event/EventLeaderboard";
import MatchupsRail from "@/components/event/MatchupsRail";
import EventProps from "@/components/event/EventProps";
import PropsSection, { type PropMark } from "@/components/event/PropsSection";
import SettledPathChart from "@/components/event/SettledPathChart";
import WinnerEvolutionChart from "@/components/event/WinnerEvolutionChart";
import BubbleWatch from "@/components/event/BubbleWatch";
import ScoringRecordsLadders, {
  scoringRecordChildren,
  scoringRecordMarketIds,
} from "@/components/event/ScoringRecordsLadders";

// Design tweaks (queue L2-64): global on/off for per-row sparklines and the
// today's-movers strip. Sparklines still degrade to nothing per-row when a
// competitor has no real history — we never invent a series.
const SHOW_SPARKLINE = true;
const SHOW_MOVERS = true;

export default function EventConceptPage() {
  const params = useParams();
  const router = useRouter();
  // Segments arrive percent-encoded; decode once. The API key is the canonical
  // `event:<domain>:<slug>` form (unchanged) reconstructed from the two segments.
  const dec = (v: unknown) => {
    const s = (v as string) || "";
    try {
      return decodeURIComponent(s);
    } catch {
      return s;
    }
  };
  const domain = dec(params?.domain);
  const slug = dec(params?.slug);
  const decodedKey = domain && slug ? `event:${domain}:${slug}` : "";

  // GA4 hooks — before any conditional return (MANDATORY).
  usePageTracking({ pageType: "event_concept", pageTitle: `Event ${decodedKey}` });
  useScrollDepth({ pageType: "event_concept" });
  useEngagementTime({ pageType: "event_concept" });

  const { data, error, isLoading } = useSWR(
    decodedKey ? ["event-concept", decodedKey] : null,
    () => fetchEventConcept(decodedKey),
    {
      revalidateOnFocus: false,
      // L2-66 freshness-as-a-feature: during live play, refetch at in-play cadence
      // (~45s) so the fused leaderboard + "as of" chip stay honestly fresh.
      // L2-91: an UPCOMING event within ~24h of its start also polls slowly (5 min)
      // so a page left open transitions countdown → live on its own when the server
      // flips status — without a manual reload. Only near-start open pages poll.
      refreshInterval: (latest) => {
        const status = latest?.event?.status;
        if (status === "live") return 45000;
        if (status === "upcoming" && latest?.event?.start_date) {
          const start = Date.parse(latest.event.start_date);
          if (!Number.isNaN(start)) {
            const hoursToStart = (start - Date.now()) / 3_600_000;
            if (hoursToStart <= 24 && hoursToStart >= -12) return 300000;
          }
        }
        return 0;
      },
    },
  );

  // L2-113: canonicalize + upgrade to the pretty, self-resolving slug the backend
  // supplies (combat: headliner+date). Discover/search cards link with the bare
  // date-token; once resolved we replace the URL so the address bar reads the
  // headliner and search engines index one canonical URL.
  const canonicalSlug = data?.event?.slug || slug;
  useEffect(() => {
    if (typeof document === "undefined" || !domain || !canonicalSlug) return;
    const href = `${window.location.origin}/event/${encodeURIComponent(
      domain,
    )}/${encodeURIComponent(canonicalSlug)}`;
    let link = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
    const created = !link;
    if (!link) {
      link = document.createElement("link");
      link.rel = "canonical";
      document.head.appendChild(link);
    }
    link.href = href;
    return () => {
      if (created && link && link.parentNode) link.parentNode.removeChild(link);
    };
  }, [domain, canonicalSlug]);

  useEffect(() => {
    if (data?.event?.slug && slug && data.event.slug !== slug) {
      router.replace(`/event/${encodeURIComponent(domain)}/${encodeURIComponent(data.event.slug)}`);
    }
  }, [data?.event?.slug, slug, domain, router]);

  // L2-71: per-competitor history rides IN the envelope (competitor.history), so
  // the leaderboard sparklines + race chart read from it directly. evolutionId is
  // still needed for the settled path-to-resolution chart.
  const evolutionId = data?.primary?.evolution_market_id ?? null;

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto py-12">
        <LoadingSpinner text="Loading event..." />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="max-w-4xl mx-auto py-12">
        <ErrorMessage
          title="Event not found"
          message="This event may have no markets yet, or the link is incorrect."
        />
      </div>
    );
  }

  const { event, primary, children, movers } = data;
  // L2-121: the shared PropsSection body (THE SCRIPT → THE DIVERGENCE) — the ONE
  // props component under the DUEL/FIELD/CONTAINER heroes — replaces the plain
  // EventProps WHERE the envelope supplies props-script marks (golf today). Each
  // mark tracks its current-favorite outcome's opening → current probability. Its
  // markets are deduped out of BOTH rails below so nothing double-renders (Item 2:
  // "don't double-render" — the finish-position ladder is separate, reading
  // `sections`/competitor fields, not `children`). No marks (settled, or a domain
  // that doesn't emit them) → graceful fallback to EventProps.
  // L2-135 Item 3: the scoring/records families render as QuantityGroup ladders in
  // their own section, so drop their single-row props-script marks here — one
  // question, one place ("don't double-render").
  const scoringIds = scoringRecordMarketIds(data.children);
  const scoringFamilyCount = scoringRecordChildren(data.children).length;
  const propMarks: PropMark[] = (data.props_script ?? [])
    .filter((p) => !(typeof p.market_id === "number" && scoringIds.has(p.market_id)))
    .map((p, i) => ({
      key: p.key ?? i,
      label: p.label,
      pregame_mark: p.pregame_mark ?? null,
      current: p.current ?? null,
      graded_result: p.graded_result ?? null,
      graded_label: p.graded_label ?? null,
      // L2-123 / #199: honest pending label for degenerate (unpriced) prop families.
      pending_label: p.pending_label ?? null,
    }));
  const hasPropsScript = propMarks.length > 0;
  const hasScoringRecords = scoringFamilyCount > 0;
  const propScriptIds = new Set(
    (data.props_script ?? [])
      .map((p) => p.market_id ?? p.key)
      .filter((v): v is number => typeof v === "number"),
  );
  // L2-84: UFC cards tag children kind="fight"|"prop" so fights render in the
  // matchups rail and props get a dedicated section. Untagged children (golf /
  // tennis / f1) are treated as matchups (unchanged behavior). Props-script markets
  // are excluded from both so they render once, in PropsSection.
  // L2-130: matchup children (soccer games) have no market_id, so a props-script
  // exclusion can only apply to children that carry one.
  const inPropsScript = (c: (typeof children)[number]) =>
    typeof c.market_id === "number" && propScriptIds.has(c.market_id);
  const fightChildren = children.filter(
    (c) => c.kind !== "prop" && !inPropsScript(c),
  );
  const propChildren = children.filter(
    (c) => c.kind === "prop" && !inPropsScript(c),
  );
  const competitors = primary.competitors || [];
  const isCoEqual = primary.kind === "co_equal_list";
  const isSettled = event.status === "settled";
  const isLive = event.status === "live";
  const hasWinnerField = primary.kind === "winner_field" && competitors.length > 0;
  // L2-130: soccer tournaments (World Cup) are winner-field concepts whose CHILDREN
  // are team duels from the events plane. They open with a container hero (the live
  // /next match), NOT the RaceToTitleChart (the winner-field competitors carry no
  // per-outcome history, so the race chart would render its honest-empty state).
  const isSoccer = event.domain === "soccer";
  const soccerHero =
    isSoccer && !isSettled ? headlinerMatchup(fightChildren) : null;
  // L2-116 → Alex's ruling (The Open 2026): the golfer grid is ONE box. The
  // finish-position columns (Top 5 … Top 40 … Make cut) no longer render as a
  // separate "Finish position" section — they append to the leaderboard rows.
  // Same single source of truth (`renderedFinishColumns`), so `marketsTracked`'s
  // count still matches exactly what renders. Suppressed once settled — a
  // concluded field shows the champion, not stale placement percentages
  // (settled-means-settled).
  const finishColumns =
    hasWinnerField && !isSettled
      ? renderedFinishColumns(data).map((c) => ({ key: c.key, label: c.label }))
      : [];
  // L2-132: the WINNER EVOLUTION chart — the winner field's probability path so
  // far (the tournament's story to date). Soccer (World Cup) has no useful race
  // chart: its winner-field competitors carry no per-outcome history, and the
  // container hero shows the next match, not the title race. So this fetched-by-
  // evolution_market_id chart is the page's view of how the title picture moved.
  // Mounted while live/upcoming; settled events get SettledPathChart instead.
  const showWinnerEvolution =
    isSoccer && hasWinnerField && !isSettled && typeof evolutionId === "number";
  // L2-135: golf cut-line Bubble Watch — live, rounds 1–2 only (a cut is only a
  // live question before it's made). Reads make_cut_prob off the competitors; the
  // component self-suppresses when no golfer sits near the cut. Renders BELOW the
  // leaderboard (Alex's ruling: the leaderboard is the page's spine).
  const golfCurrentRound =
    competitors.find((c) => c.current_round != null)?.current_round ?? null;
  const showBubbleWatch =
    isLive &&
    event.domain === "golf" &&
    golfCurrentRound != null &&
    golfCurrentRound <= 2;

  // Section nav — only the sections that will actually render.
  const nav: { id: string; label: string }[] = [];
  if (soccerHero) nav.push({ id: "headliner", label: "Now" });
  else if (hasWinnerField && evolutionId && !isSettled)
    nav.push({ id: "race", label: "Race" });
  if (isCoEqual) nav.push({ id: "head-to-head", label: "Head to head" });
  if (hasWinnerField) nav.push({ id: "leaderboard", label: "Leaderboard" });
  if (showBubbleWatch) nav.push({ id: "bubble-watch", label: "Bubble Watch" });
  if (showWinnerEvolution) nav.push({ id: "evolution", label: "Evolution" });
  if (fightChildren.length > 0)
    nav.push({ id: "matchups", label: isSoccer ? "Matches" : "Matchups" });
  if (hasPropsScript) nav.push({ id: "props-script", label: "Props" });
  else if (propChildren.length > 0) nav.push({ id: "props", label: "Props" });
  if (hasScoringRecords) nav.push({ id: "scoring-records", label: "Scoring" });
  if (isSettled && evolutionId) nav.push({ id: "path", label: "Path" });

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      {/* L2-130: hub/category up-link. Soccer has no /hub/soccer page, so the World
          Cup concept up-links to the Sports feed (an existing, honest destination). */}
      {isSoccer && (
        <Link
          href="/sports"
          className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors"
        >
          <span aria-hidden>←</span> Sports
        </Link>
      )}

      <EventHeader
        event={event}
        marketsTracked={marketsTracked(data)}
        nav={nav}
        fallbackName={decodedKey}
      />

      <MoversStrip movers={movers} show={SHOW_MOVERS} />

      {/* Hero: co-equal two-sided timeline (combat), soccer container hero (the live
          /next match duel), or the winner-field race chart. Settled events show the
          path-to-resolution chart below instead. */}
      {isCoEqual ? (
        <TwoSidedTimeline
          competitors={competitors}
          label={primary.label}
          evolutionMarketId={evolutionId}
        />
      ) : soccerHero ? (
        <SoccerContainerHero matchups={fightChildren} />
      ) : (
        hasWinnerField &&
        !isSettled && (
          <RaceToTitleChart
            competitors={competitors}
            domain={event.domain}
            startDate={event.start_date}
            endDate={event.end_date}
          />
        )
      )}

      {hasWinnerField && (
        <EventLeaderboard
          competitors={competitors}
          label={primary.label}
          showSparkline={SHOW_SPARKLINE}
          live={isLive}
          settled={isSettled}
          asOf={event.as_of}
          domain={event.domain}
          finishColumns={finishColumns}
        />
      )}

      {/* L2-135: Bubble Watch sits directly below the leaderboard spine. */}
      {showBubbleWatch && (
        <BubbleWatch
          competitors={competitors}
          currentRound={golfCurrentRound}
          domain={event.domain}
        />
      )}

      {showWinnerEvolution && typeof evolutionId === "number" && (
        <WinnerEvolutionChart
          marketId={evolutionId}
          domain={event.domain}
          live={isLive}
        />
      )}

      <MatchupsRail
        items={fightChildren}
        exclude={soccerHero}
        title={isSoccer ? "Matches" : undefined}
      />

      {hasPropsScript ? (
        <PropsSection items={propMarks} eventStatus={event.status} />
      ) : (
        <EventProps items={propChildren} />
      )}

      {/* L2-135: Scoring & Records — the Under-N families as QuantityGroup ladders,
          not a wall of numbers. Suppressed once settled (settled-means-settled). */}
      {hasScoringRecords && !isSettled && (
        <ScoringRecordsLadders items={data.children} />
      )}

      {isSettled && evolutionId && (
        <SettledPathChart
          marketId={evolutionId}
          domain={event.domain}
          startDate={event.start_date}
          endDate={event.end_date}
        />
      )}
    </div>
  );
}
