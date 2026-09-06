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
import {
  applyCountedCap,
  earnsCountChip,
  earnsGrid,
  earnsSectionHeader,
  probabilityBarWidth,
} from "@/lib/entityPageChrome";
import { fetchHub, formatProbability } from "@/lib/api";
import type { HubResponse, LeagueMarket, LeagueMarketOutcome } from "@/lib/api";
import { toTitleCaseAcronymSafe } from "@/lib/titleCase";
// UX-P209: the pill lives outside this route file so a guard can render it and
// so a second copy cannot quietly become the one that ships. See its header.
// UX-P210 (CERT-525): and so does the whole rail, for the same reason one level
// up — the heading is a phase claim about the cards under it, and a guard can
// only judge that by rendering the section. See `HubUpcomingRail`'s header.
import { HubUpcomingRail } from "@/components/hub/HubUpcomingRail";

// ---------------------------------------------------------------------------
// Section display config: friendly labels + render order. Sections the backend
// returns that aren't listed here still render (title-cased) after these.
//
// ── UX-P167 (#2167): these are the NEUTRAL defaults, and that is the whole fix ──
//
// This map used to hold MMA's words — `matches: "Fight Markets"`, `season_stats:
// "Fighter Stats"` — because MMA was the only hub when it was written. The page
// is generic across five competitions, so those words shipped verbatim onto the
// others: measured live on 2026-08-29, during US Open week, `/hub/tennis` printed
// "FIGHT MARKETS" over 103 tennis markets, `/hub/esports` printed it over 98, and
// `/hub/golf` printed "FIGHTER STATS" over five golf markets.
//
// The sport-specific vocabulary now lives in `HubConfig.section_labels` and
// arrives in the payload (`data.section_labels`), beside the `label`/`title`/
// `blurb` that were already served per competition. What stays here is the
// neutral word for each key.
//
// The direction matters. Defaults are neutral and OVERRIDES add flavour, so
// every failure path lands on a label that is plain but true: a hub that
// declares nothing, an unmapped section key, and a payload cached before this
// shipped (the hub mirror lives up to 24h) all read "Matches", never another
// sport's word. The inverse — combat defaults with per-hub escapes — would make
// silence mean "Fight Markets" again, which is exactly the bug.
// ---------------------------------------------------------------------------

const SECTION_META: Record<string, { label: string }> = {
  futures: { label: "Tournament Winners" },
  props: { label: "Props" },
  matches: { label: "Matches" },
  awards: { label: "Awards" },
  season_stats: { label: "Player Stats" },
  series: { label: "Series" },
  more_markets: { label: "More Markets" },
};
// Matches sit ABOVE props (UX-P181, #2167). Props outranked them until the
// linked-match rail started finding real fixtures, and then the order stopped
// making sense: measured on /hub/tennis during the US Open, "Matches" began at
// y=23,746px on a 390px phone — roughly 28 screens of set-games props before
// the live match a reader opened the page for. The derivative markets follow
// the thing they are derived from.
const SECTION_ORDER = ["futures", "matches", "props", "awards", "season_stats", "series", "more_markets"];

function sectionLabel(key: string, served?: Record<string, string> | null): string {
  // The competition's own word wins when it has one (combat hubs say "Fight
  // Markets"); otherwise the neutral default; otherwise L2-174 Item 3b's
  // acronym-safe title case, so an unmapped key like "pga_tour_major" reads
  // "PGA Tour Major", not "Pga Tour Major".
  return served?.[key] || SECTION_META[key]?.label || toTitleCaseAcronymSafe(key);
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

function OutcomeRow({ o }: { o: LeagueMarketOutcome }) {
  // UX-P061 (#1742), register E2: this was `width: ${pct ?? 0}%`, which renders a
  // NULL probability as a 0%-wide bar — a claim that we measured this and it is
  // zero, about something we did not measure (doctrine A3, honest or absent).
  // The whole track is withheld, not just the fill: a 0%-width bar inside a
  // visible track is the same lie with extra steps.
  const pct = probabilityBarWidth(o.probability);
  return (
    <div className="flex items-center gap-2 py-1.5">
      <span className="flex-1 text-[13px] text-text-secondary truncate">{o.name}</span>
      {pct !== null && (
        <div className="w-20 h-1.5 rounded-full bg-surface-elevated overflow-hidden">
          <div className="h-full rounded-full bg-accent-brand" style={{ width: `${pct}%` }} />
        </div>
      )}
      <span className="w-10 text-right font-mono text-[13px] font-semibold text-text-primary">
        {formatProbability(o.probability)}
      </span>
    </div>
  );
}

const OUTCOME_DISPLAY_CAP = 4;

function MarketCard({ market }: { market: LeagueMarket }) {
  const outcomeCap = applyCountedCap(market.outcome_count, OUTCOME_DISPLAY_CAP);
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
        {market.top_outcomes.slice(0, outcomeCap.shown).map((o) => (
          <OutcomeRow key={o.id} o={o} />
        ))}
      </div>
      {/* UX-P061 (#1742), register E1: `+{n} more` fired at n=1, which costs the
          same row as the item it hides. `applyCountedCap` absorbs a single
          leftover and only announces a remainder of two or more. */}
      {outcomeCap.showMoreLink && (
        <div className="mt-2 text-[11px] text-text-muted">+{outcomeCap.hidden} more</div>
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
    <div
      className="-mx-3 md:-mx-6 -mt-4 bg-surface-deep min-h-screen"
      data-entity-kind="competition"
      data-entity-tier={data.tier ?? undefined}
      data-availability={data.availability ?? undefined}
    >
      {/* Hero */}
      <div className="px-4 md:px-6 pt-10 pb-8" style={{ maxWidth: 1200, margin: "0 auto" }}>
        {/* UX-P061 (#1742): a count chip is a STAT, and spec §3 bans it below T2 —
            at 1-3 answers the count is already visible and printing it is the page
            apologizing for its size. Boxing is T0 today and printed "0 active
            markets", which is the apology in its purest form. */}
        {earnsCountChip(data.tier) && (
          <div className="flex items-center gap-2 mb-3">
            <span className="font-mono text-xs text-text-muted">
              {data.total_markets.toLocaleString()} active markets
            </span>
          </div>
        )}
        <h1 className="text-[38px] md:text-[52px] font-semibold text-text-primary leading-[1.1] tracking-tight flex items-center gap-3">
          <span aria-hidden>{data.emoji}</span>
          {data.title}
        </h1>
        <p className="text-base text-text-secondary mt-4 max-w-[620px]">{data.blurb}</p>
      </div>

      <div className="px-4 md:px-6 pb-20" style={{ maxWidth: 1200, margin: "0 auto" }}>
        {/* UX-P061 (#1742) — spec §6 clause 7 / ruling 012: the browser-audit rail
            must be able to PROVE honest-empty against broken-blank. Without a
            named hook those two render identically to a grader, which is gotcha
            #53 on the rendered surface. The copy already names a WHEN; the full
            T0 statement (identity at full fidelity, the record, a counted
            up-link) arrives with step 2, which is where competitions get their
            record strip. */}
        {isEmpty && (
          <div
            className="py-20 text-center text-text-muted"
            data-testid="hub-empty-state"
            data-empty-state-name="entity-competition-present"
          >
            No open markets right now. This page collects every open market for this competition.
          </div>
        )}

        {/* Upcoming rail — heading included, because the heading is a claim
            about the cards and only the section knows both. */}
        <HubUpcomingRail
          cards={data.upcoming || []}
          label={data.upcoming_label}
          neutralLabel={data.upcoming_label_neutral}
        />

        {/* Market sections */}
        {/* UX-P061 (#1742), register E1 — the broken shelf, fixed at its source.
            Sections rendered at length >= 1, so a single market got a section
            header AND a count chip: chrome organizing nothing. Both are now
            EARNED (spec §4), and the tier that gates the chip is the backend's
            declared field, never a count this client re-derives (ruling 021). */}
        {sections.map(([key, markets]) => {
          const showHeader = earnsSectionHeader(markets.length, sections.length);
          const showChip = showHeader && earnsCountChip(data.tier);
          return (
            <section key={key} className="mb-12" data-section-key={key}>
              {showHeader && (
                <div className="flex items-baseline justify-between mb-3">
                  <h2 className="text-[11px] font-bold tracking-[0.12em] text-text-muted uppercase">
                    {sectionLabel(key, data.section_labels)}
                  </h2>
                  {showChip && (
                    <span className="font-mono text-[11px] text-text-muted">
                      {markets.length}
                    </span>
                  )}
                </div>
              )}
              {/* A grid that would render one orphaned row is a stack. */}
              <div
                className={
                  earnsGrid(markets.length)
                    ? "grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
                    : "flex flex-col gap-3"
                }
              >
                {markets.map((m) => (
                  <MarketCard key={m.id} market={m} />
                ))}
              </div>
            </section>
          );
        })}
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
