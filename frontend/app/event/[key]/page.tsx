"use client";

// #999 Event Concept Pages — L2-64 visual design. Generic /event/[key] rendering
// any individual-competitor event via /api/event/{key}. Event-framed header +
// today's movers + "race to the title" chart + winner-field leaderboard +
// matchups rail + (settled) path-to-resolution. Co-equal domains (fights) get a
// two-sided timeline instead of the race chart. Probability-only (no odds),
// light-mode tokens, blend-only (no source names on rows), straight segments.

import { useParams } from "next/navigation";
import useSWR from "swr";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchEventConcept } from "@/lib/api";
import { marketsTracked } from "@/lib/eventConceptDisplay";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorMessage from "@/components/ErrorMessage";
import EventHeader from "@/components/event/EventHeader";
import MoversStrip from "@/components/event/MoversStrip";
import RaceToTitleChart from "@/components/event/RaceToTitleChart";
import TwoSidedTimeline from "@/components/event/TwoSidedTimeline";
import EventLeaderboard from "@/components/event/EventLeaderboard";
import MatchupsRail from "@/components/event/MatchupsRail";
import EventProps from "@/components/event/EventProps";
import SettledPathChart from "@/components/event/SettledPathChart";

// Design tweaks (queue L2-64): global on/off for per-row sparklines and the
// today's-movers strip. Sparklines still degrade to nothing per-row when a
// competitor has no real history — we never invent a series.
const SHOW_SPARKLINE = true;
const SHOW_MOVERS = true;

export default function EventConceptPage() {
  // Next.js 14: dynamic params for a CLIENT component come from useParams().
  // `use(params)` on a plain object throws at render (L2-60 P1). useParams()
  // returns the segment STILL percent-encoded, so decode ONCE here before
  // fetchEventConcept re-encodes it for the URL — otherwise the key double-encodes
  // (event%253A…) and the fetch 404s (L2-61). decodeURIComponent is safe/idempotent
  // for our keys (colons aren't %-escapes). #999
  const params = useParams();
  const rawKey = (params?.key as string) || "";
  const decodedKey = (() => {
    try {
      return decodeURIComponent(rawKey);
    } catch {
      return rawKey;
    }
  })();

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
      refreshInterval: (latest) => (latest?.event?.status === "live" ? 45000 : 0),
    },
  );

  // L2-71: per-competitor history now rides IN the envelope (competitor.history),
  // so the leaderboard sparklines + race chart read from it directly — no separate
  // history fetch. evolutionId is still needed for the settled path-to-resolution
  // chart.
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
  // L2-84: UFC cards tag children kind="fight"|"prop" so fights render in the
  // matchups rail and props get a dedicated section. Untagged children (golf /
  // tennis / f1) are treated as matchups (unchanged behavior).
  const fightChildren = children.filter((c) => c.kind !== "prop");
  const propChildren = children.filter((c) => c.kind === "prop");
  const competitors = primary.competitors || [];
  const isCoEqual = primary.kind === "co_equal_list";
  const isSettled = event.status === "settled";
  const isLive = event.status === "live";
  const hasWinnerField = primary.kind === "winner_field" && competitors.length > 0;

  // Section nav — only the sections that will actually render.
  const nav: { id: string; label: string }[] = [];
  if (hasWinnerField && evolutionId && !isSettled) nav.push({ id: "race", label: "Race" });
  if (isCoEqual) nav.push({ id: "head-to-head", label: "Head to head" });
  if (hasWinnerField) nav.push({ id: "leaderboard", label: "Leaderboard" });
  if (fightChildren.length > 0) nav.push({ id: "matchups", label: "Matchups" });
  if (propChildren.length > 0) nav.push({ id: "props", label: "Props" });
  if (isSettled && evolutionId) nav.push({ id: "path", label: "Path" });

  return (
    <div className="max-w-4xl mx-auto space-y-6 pb-12">
      <EventHeader
        event={event}
        marketsTracked={marketsTracked(data)}
        nav={nav}
        fallbackName={decodedKey}
      />

      <MoversStrip movers={movers} show={SHOW_MOVERS} />

      {/* Race to the title (winner-field, live/upcoming) OR co-equal two-sided
          timeline. Settled events show the path-to-resolution chart below. */}
      {isCoEqual ? (
        <TwoSidedTimeline
          competitors={competitors}
          label={primary.label}
          evolutionMarketId={evolutionId}
        />
      ) : (
        hasWinnerField &&
        !isSettled && <RaceToTitleChart competitors={competitors} domain={event.domain} />
      )}

      {hasWinnerField && (
        <EventLeaderboard
          competitors={competitors}
          label={primary.label}
          showSparkline={SHOW_SPARKLINE}
          live={isLive}
          settled={isSettled}
          asOf={event.as_of}
        />
      )}

      <MatchupsRail items={fightChildren} />

      <EventProps items={propChildren} />

      {isSettled && evolutionId && (
        <SettledPathChart marketId={evolutionId} domain={event.domain} />
      )}
    </div>
  );
}
