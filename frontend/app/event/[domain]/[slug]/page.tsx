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
