"use client";

/**
 * Generic competition HUB (landing) page — B1 / #1028.
 *
 * ONE config-driven route: `/hub/[competition]` (MMA first). The backend
 * (`GET /api/hub/{competition}`) is the adapter — this page renders whatever it
 * returns: an "upcoming" rail of event-concept cards (link to `/event/{key}`)
 * plus futures/awards/props sections. Adding boxing/esports is a backend config
 * entry, not new page code.
 */

import { useParams } from "next/navigation";
import Link from "next/link";
import useSWR from "swr";
import ErrorBoundary from "@/components/ErrorBoundary";
import ErrorState from "@/components/ErrorState";
import HubSkeleton from "@/components/skeletons/HubSkeleton";
import { usePageTracking, useScrollDepth, useEngagementTime } from "@/hooks";
import { fetchHub, formatProbability } from "@/lib/api";
import type { HubResponse, HubUpcoming, LeagueMarket, LeagueMarketOutcome } from "@/lib/api";
import { eventPath } from "@/lib/eventKey";

// ---------------------------------------------------------------------------
// Section display config: friendly labels + render order. Sections the backend
// returns that aren't listed here still render (title-cased) after these.
// ---------------------------------------------------------------------------

const SECTION_META: Record<string, { label: string }> = {
  futures: { label: "Tournament Winners" },
  props: { label: "Fight Props" },
  matches: { label: "Fight Markets" },
  awards: { label: "Awards" },
  season_stats: { label: "Fighter Stats" },
  series: { label: "Series" },
  more_markets: { label: "More Markets" },
};
const SECTION_ORDER = ["futures", "props", "matches", "awards", "season_stats", "series", "more_markets"];

function sectionLabel(key: string): string {
  return (
    SECTION_META[key]?.label ||
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

function orderedSections(sections: Record<string, LeagueMarket[]>): [string, LeagueMarket[]][] {
  const keys = Object.keys(sections);
  const ordered = SECTION_ORDER.filter((k) => keys.includes(k) && sections[k]?.length);
  const extra = keys.filter((k) => !SECTION_ORDER.includes(k) && sections[k]?.length);
  return [...ordered, ...extra].map((k) => [k, sections[k]]);
}

// ---------------------------------------------------------------------------
// Small presentational helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function StatusPill({ status }: { status: string }) {
  if (status === "live") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wide text-accent-live">
        <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
        Live
      </span>
    );
  }
  if (status === "settled") {
    return <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Final</span>;
  }
  return <span className="text-[10px] font-semibold uppercase tracking-wide text-accent-brand">Upcoming</span>;
}

function UpcomingCard({ card }: { card: HubUpcoming }) {
  return (
    <Link
      href={eventPath(card.key)}
      className="group flex-shrink-0 w-64 bg-surface-card border border-surface-border rounded-2xl p-4 transition-colors hover:border-accent-brand/50 hover:bg-surface-elevated"
    >
      <div className="flex items-center justify-between mb-2">
        <StatusPill status={card.status} />
        {card.is_major && (
          <span className="text-[10px] font-bold uppercase tracking-wide text-accent-brand">★ Marquee</span>
        )}
      </div>
      <div className="text-[15px] font-semibold text-text-primary leading-snug line-clamp-2 min-h-[2.6em]">
        {card.name}
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
        <span>{formatDate(card.start_date) || "TBD"}</span>
        {typeof card.fight_count === "number" && card.fight_count > 0 && (
          <span className="font-mono">{card.fight_count} fights</span>
        )}
      </div>
    </Link>
  );
}

function OutcomeRow({ o }: { o: LeagueMarketOutcome }) {
  const pct = o.probability != null ? Math.round(o.probability * 100) : null;
  return (
    <div className="flex items-center gap-2 py-1.5">
      <span className="flex-1 text-[13px] text-text-secondary truncate">{o.name}</span>
      <div className="w-20 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
        <div
          className="h-full rounded-full bg-accent-brand"
          style={{ width: `${pct ?? 0}%` }}
        />
      </div>
      <span className="w-10 text-right font-mono text-[13px] font-semibold text-text-primary">
        {formatProbability(o.probability)}
      </span>
    </div>
  );
}

function MarketCard({ market }: { market: LeagueMarket }) {
  return (
    <Link
      href={`/futures/${market.id}`}
      className="block bg-surface-card border border-surface-border rounded-2xl p-4 transition-colors hover:border-accent-brand/50"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="text-[14px] font-semibold text-text-primary leading-snug line-clamp-2">
          {market.name}
        </span>
        {market.prop_type && (
          <span className="flex-shrink-0 text-[10px] font-bold uppercase tracking-wide text-text-muted bg-surface-elevated px-1.5 py-0.5 rounded">
            {market.prop_type}
          </span>
        )}
      </div>
      <div className="divide-y divide-surface-border">
        {market.top_outcomes.slice(0, 4).map((o) => (
          <OutcomeRow key={o.id} o={o} />
        ))}
      </div>
      {market.outcome_count > 4 && (
        <div className="mt-2 text-[11px] text-text-muted">+{market.outcome_count - 4} more</div>
      )}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function HubContent({ competition }: { competition: string }) {
  const { data, error } = useSWR<HubResponse>(
    competition ? ["hub", competition] : null,
    () => fetchHub(competition),
    { refreshInterval: 60000 },
  );

  if (error) {
    return (
      <div className="max-w-3xl mx-auto py-16">
        <ErrorState message="Failed to load this hub" onRetry={() => window.location.reload()} />
      </div>
    );
  }

  if (!data) return <HubSkeleton />;

  const sections = orderedSections(data.sections || {});
  const hasUpcoming = (data.upcoming || []).length > 0;
  const isEmpty = !hasUpcoming && sections.length === 0;

  return (
    <div className="-mx-3 md:-mx-6 -mt-4 bg-surface-deep min-h-screen">
      {/* Hero */}
      <div className="px-4 md:px-6 pt-10 pb-8" style={{ maxWidth: 1200, margin: "0 auto" }}>
        <div className="flex items-center gap-2 mb-3">
          <span className="font-mono text-xs text-text-muted">
            {data.total_markets.toLocaleString()} active markets
          </span>
        </div>
        <h1 className="text-[38px] md:text-[52px] font-semibold text-text-primary leading-[1.1] tracking-tight flex items-center gap-3">
          <span aria-hidden>{data.emoji}</span>
          {data.title}
        </h1>
        <p className="text-base text-text-secondary mt-4 max-w-[620px]">{data.blurb}</p>
      </div>

      <div className="px-4 md:px-6 pb-20" style={{ maxWidth: 1200, margin: "0 auto" }}>
        {isEmpty && (
          <div className="py-20 text-center text-text-muted">
            No open markets right now. Check back when the next card is announced.
          </div>
        )}

        {/* Upcoming rail */}
        {hasUpcoming && (
          <section className="mb-12">
            <h2 className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase mb-3">
              Upcoming Cards
            </h2>
            <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
              {data.upcoming.map((c) => (
                <UpcomingCard key={c.key} card={c} />
              ))}
            </div>
          </section>
        )}

        {/* Market sections */}
        {sections.map(([key, markets]) => (
          <section key={key} className="mb-12">
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase">
                {sectionLabel(key)}
              </h2>
              <span className="font-mono text-[11px] text-text-muted">{markets.length}</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {markets.map((m) => (
                <MarketCard key={m.id} market={m} />
              ))}
            </div>
          </section>
        ))}
      </div>

      <footer className="border-t border-surface-border bg-surface-card">
        <div className="px-4 md:px-6 py-7 flex items-center justify-between flex-wrap gap-3 text-xs text-text-muted" style={{ maxWidth: 1200, margin: "0 auto" }}>
          <span>Prediction market data · Probabilities, not betting advice.</span>
          <span className="font-mono">bainluck.com/hub/{data.competition}</span>
        </div>
      </footer>
    </div>
  );
}

export default function CompetitionHubPage() {
  const params = useParams();
  const competition = (Array.isArray(params?.competition) ? params.competition[0] : params?.competition) || "";

  usePageTracking({ pageType: "competition_hub", pageTitle: `${competition} hub` });
  useScrollDepth({ pageType: "competition_hub" });
  useEngagementTime({ pageType: "competition_hub" });

  return (
    <ErrorBoundary
      fallback={
        <div className="p-8 text-center">
          <h2>Something went wrong</h2>
          <button onClick={() => window.location.reload()} className="mt-2 text-sm text-accent-brand hover:underline">
            Reload page
          </button>
        </div>
      }
    >
      <HubContent competition={competition} />
    </ErrorBoundary>
  );
}
