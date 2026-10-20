"use client";

// The Matching view's presentation for the Correctness Console's Matching tab
// (#847), carried over from `/admin/matching`. Pure: no fetch, no analytics
// hook, no auth — the console page owns its reads and its three GA hooks.
//
// Why a copy and not a module both routes import: a module two routes import
// is emitted as a numbered SHARED chunk, and the shipped-copy gate
// (`shippedCopyBans`, ruling 141) treats shared chunks as reader surfaces, so
// this staff copy — which names venues because an operator has to go and fix
// them — would fail it. Imported by the console alone, it ships inside the
// `app/admin/correctness` route chunk, where ruling 138 exempts staff copy.
// The standalone page stays untouched until its parity is accepted and it is
// retired; `correctnessConsoleTabs847.test.tsx` checks that every reader-
// visible sentence of that page is carried here, so the two cannot drift
// silently.
//
// Every section takes its data plus an optional `notice`. A route that has no
// trustworthy number for a section (a miss, a refused snapshot, a failed read)
// passes the notice and the section shows it INSTEAD of numbers — never a zero
// card, never a 0% bar built from an absent denominator.

import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Database, Link2, Unlink } from "lucide-react";

import MetricSection from "@/components/admin/MetricSection";

export interface SportAccuracy {
  total: number;
  // sources = TRUE source linkage counts (events carrying external_id / espn_id /
  // statpal_fixture_id). These overlap — one event can link to several sources.
  sources: Record<string, number>;
  // commence_time_sources = which single source won the race to set commence_time
  // (data-provenance audit, NOT linkage). Do not read this as source coverage.
  commence_time_sources?: Record<string, number>;
  odds_api_linked_pct?: number;
  reliability?: string;
}

export interface AccuracyData {
  period_days: number;
  sports: Record<string, SportAccuracy>;
}

// L2-128 Item 2a: the page predated the prediction-market era, so it only showed
// event→source linkage (Odds API / ESPN / StatPal). Kalshi & Polymarket link the
// OTHER direction — game markets → events (via FuturesMarket.event_id) — which is
// what makes a Kalshi/Polymarket line show up on an event page at all.
export interface LinkRateSport {
  sport: string;
  league: string | null;
  total: number;
  linked: number;
  open_total: number;
  open_linked: number;
  link_rate: number;
  link_rate_all: number;
}
export interface LinkRateSourceBlock {
  totals: {
    total: number;
    linked: number;
    open_total: number;
    open_linked: number;
    link_rate_pct: number;
    link_rate_all_pct: number;
  };
  by_sport: LinkRateSport[];
}
export interface LinkRateData {
  overall: {
    total_game_markets: number;
    linked: number;
    link_rate_pct: number;
    open_total: number;
    open_linked: number;
  };
  kalshi: LinkRateSourceBlock;
  polymarket: LinkRateSourceBlock;
}

export interface MaturedLinkageMiss {
  event_id: number;
  source: string;
  sport: string;
  matchup: string;
}

/**
 * Queue #223 Item 4 — the stronger linkage class the matured-linkage payload
 * carries beside its headline: a game-winner market we HOLD (open, event_id
 * NULL) whose both teams match an imminent event.
 */
export interface UnlinkedHeldMiss extends MaturedLinkageMiss {
  market_id?: number;
  market_name?: string | null;
  commence_time?: string | null;
}
export type UnlinkedHeld =
  | {
      status: "ok" | "insufficient_slate";
      headline_unlinked_held: number;
      events_checked: number;
      candidates_scanned?: number;
      derivatives_excluded?: number;
      misses: UnlinkedHeldMiss[];
      definition?: string;
    }
  | { status: "error"; error: string };

// Queue #220/221 Item 2 — the matured-linkage HEADLINE metric. Below-100 MEANS a
// real defect: an imminent event (≤24h) carries a prediction-market source in its
// blend but has no linked winner market behind it (a phantom blend source).
export interface MaturedLinkageData {
  headline_pct: number | null;
  status: string;
  checkable_pairs: number;
  backed: number;
  phantom: number;
  events_checked: number;
  events_consistent: number;
  misses: MaturedLinkageMiss[];
  window: string;
  unlinked_held?: UnlinkedHeld;
}

export const TIER1_SPORTS = [
  { key: "basketball_nba", label: "NBA", emoji: "🏀" },
  { key: "icehockey_nhl", label: "NHL", emoji: "🏒" },
  { key: "baseball_mlb", label: "MLB", emoji: "⚾" },
  { key: "americanfootball_nfl", label: "NFL", emoji: "🏈" },
  { key: "basketball_ncaab", label: "NCAAB", emoji: "🏀" },
];

export const TIER2_SPORTS = [
  { key: "basketball_wnba", label: "WNBA", emoji: "🏀" },
  { key: "soccer_epl", label: "EPL", emoji: "⚽" },
  { key: "soccer_usa_mls", label: "MLS", emoji: "⚽" },
  { key: "mma_mixed_martial_arts", label: "MMA", emoji: "🥊" },
];

export type MatchingStatus = "good" | "warning" | "critical";

/** Misses listed before the rest fold under "Show all". */
export const MISSES_VISIBLE = 8;

/** The page's tier-1 Odds API linkage headline, from the 14-day sport cards. */
export function tier1Summary(accuracy: AccuracyData | null | undefined): {
  linked: number;
  total: number;
  pct: number;
  status: MatchingStatus;
} {
  const total = TIER1_SPORTS.reduce((sum, s) => sum + (accuracy?.sports?.[s.key]?.total ?? 0), 0);
  const linked = TIER1_SPORTS.reduce((sum, s) => sum + (accuracy?.sports?.[s.key]?.sources?.odds_api ?? 0), 0);
  const pct = total > 0 ? Math.round((linked / total) * 100) : 0;
  return { linked, total, pct, status: pct >= 80 ? "good" : pct >= 50 ? "warning" : "critical" };
}

export function linkRateStatus(linkRate: LinkRateData | null | undefined): MatchingStatus {
  const pmPct = linkRate?.overall?.link_rate_pct ?? 0;
  return pmPct >= 80 ? "good" : pmPct >= 50 ? "warning" : "critical";
}

function LinkRateBar({ linked, total, label }: { linked: number; total: number; label: string }) {
  const pct = total > 0 ? Math.round((linked / total) * 100) : 0;
  const color = pct >= 80 ? "bg-accent-live" : pct >= 50 ? "bg-accent-warning" : "bg-accent-danger";
  const textColor = pct >= 80 ? "text-accent-live" : pct >= 50 ? "text-accent-warning" : "text-accent-danger";

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-text-muted w-16 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-surface-elevated rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.max(2, pct)}%` }} />
      </div>
      <span className={`text-xs font-semibold w-20 text-right ${textColor}`}>
        {linked}/{total} ({pct}%)
      </span>
    </div>
  );
}

function SportCard({ sport, data }: { sport: typeof TIER1_SPORTS[0]; data?: SportAccuracy }) {
  if (!data) return null;

  const oddsApi = data.sources?.odds_api ?? 0;
  const espn = data.sources?.espn ?? 0;
  const statpal = data.sources?.statpal ?? 0;
  const total = data.total;
  const linkPct = total > 0 ? Math.round((oddsApi / total) * 100) : 0;

  const status = linkPct >= 80 ? "good" : linkPct >= 50 ? "warning" : "critical";
  const StatusIcon = status === "good" ? CheckCircle2 : status === "warning" ? AlertTriangle : Unlink;
  const statusColor = status === "good" ? "text-accent-live" : status === "warning" ? "text-accent-warning" : "text-accent-danger";
  const statusBg = status === "good" ? "border-accent-live/20" : status === "warning" ? "border-accent-warning/20" : "border-accent-danger/20";

  return (
    <div className={`bg-surface-card rounded-xl border ${statusBg} p-4`} data-sport-card={sport.key}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">{sport.emoji}</span>
          <span className="text-sm font-semibold text-text-primary">{sport.label}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <StatusIcon className={`w-4 h-4 ${statusColor}`} />
          <span className={`text-sm font-bold ${statusColor}`}>{linkPct}%</span>
        </div>
      </div>

      <div className="space-y-1.5">
        <LinkRateBar linked={oddsApi} total={total} label="Odds API" />
        <LinkRateBar linked={espn} total={total} label="ESPN" />
        <LinkRateBar linked={statpal} total={total} label="StatPal" />
      </div>

      <div className="mt-3 pt-3 border-t border-surface-border">
        <div className="flex items-center justify-between text-xs text-text-muted">
          <span>{total} events (14 days)</span>
          {oddsApi === 0 && total > 0 && (
            <span className="text-accent-danger font-medium">No sportsbook data!</span>
          )}
        </div>
      </div>
    </div>
  );
}

function PredictionMarketLinkage({ block, sourceLabel }: { block?: LinkRateSourceBlock; sourceLabel: string }) {
  if (!block) return null;
  const pct = block.totals.link_rate_pct;
  const status = pct >= 80 ? "good" : pct >= 50 ? "warning" : "critical";
  const StatusIcon = status === "good" ? CheckCircle2 : status === "warning" ? AlertTriangle : Unlink;
  const statusColor = status === "good" ? "text-accent-live" : status === "warning" ? "text-accent-warning" : "text-accent-danger";
  const statusBg = status === "good" ? "border-accent-live/20" : status === "warning" ? "border-accent-warning/20" : "border-accent-danger/20";
  const topSports = [...(block.by_sport ?? [])]
    .filter((s) => s.open_total > 0)
    .sort((a, b) => b.open_total - a.open_total)
    .slice(0, 6);

  return (
    <div className={`bg-surface-card rounded-xl border ${statusBg} p-4`} data-venue-card={sourceLabel}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Link2 className="w-4 h-4 text-accent-brand" />
          <span className="text-sm font-semibold text-text-primary">{sourceLabel}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <StatusIcon className={`w-4 h-4 ${statusColor}`} />
          <span className={`text-sm font-bold ${statusColor}`}>{pct}%</span>
        </div>
      </div>
      <div className="space-y-1.5">
        {topSports.length > 0 ? (
          topSports.map((s) => (
            <LinkRateBar
              key={`${s.sport}-${s.league}`}
              linked={s.open_linked}
              total={s.open_total}
              label={s.league || s.sport}
            />
          ))
        ) : (
          <span className="text-xs text-text-muted">No open game markets right now.</span>
        )}
      </div>
      <div className="mt-3 pt-3 border-t border-surface-border">
        <div className="text-xs text-text-muted">
          {block.totals.open_linked}/{block.totals.open_total} open game markets linked to an event
        </div>
      </div>
    </div>
  );
}

function MissList({ misses, render }: { misses: MaturedLinkageMiss[]; render: (m: MaturedLinkageMiss) => string }) {
  const item = (m: MaturedLinkageMiss, i: number) => (
    <li key={i} className="text-xs text-accent-danger break-words">
      {render(m)}
    </li>
  );
  const rest = misses.slice(MISSES_VISIBLE);
  return (
    <>
      <ul className="mt-2 space-y-1">{misses.slice(0, MISSES_VISIBLE).map(item)}</ul>
      {rest.length > 0 && (
        <details className="mt-1">
          <summary className="text-xs text-text-secondary cursor-pointer py-1">Show all {misses.length}</summary>
          <ul className="space-y-1">{rest.map((m, i) => item(m, i + MISSES_VISIBLE))}</ul>
        </details>
      )}
    </>
  );
}

/** Queue #220/221 Item 2 — MATURED LINKAGE: below-100 = a real phantom blend source. */
export function MaturedLinkageCard({ data, footer }: { data: MaturedLinkageData; footer?: ReactNode }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4" data-section="matured-linkage">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">
            Matured linkage <span className="text-text-muted font-normal">(headline)</span>
          </h2>
          <p className="text-xs text-text-muted mt-0.5">
            Imminent events ({data.window}): every blend prediction-market
            source must have a linked winner market. Below 100% = a real phantom.
          </p>
        </div>
        <div
          className={`text-2xl font-bold ${
            data.status !== "ok"
              ? "text-text-muted"
              : data.headline_pct === 100
              ? "text-accent-live"
              : "text-accent-danger"
          }`}
        >
          {data.status !== "ok" || data.headline_pct === null ? "n/a" : `${data.headline_pct}%`}
        </div>
      </div>
      {data.status === "ok" ? (
        <p className="text-xs text-text-secondary mt-2">
          {data.backed}/{data.checkable_pairs} imminent blend
          sources linked · {data.events_consistent}/{data.events_checked} events
          consistent
          {data.phantom > 0 && (
            <span className="text-accent-danger">
              {" "}· {data.phantom} phantom (filed by the Flow Sentinel)
            </span>
          )}
        </p>
      ) : (
        <p className="text-xs text-text-muted mt-2">
          No imminent Kalshi/Polymarket blend sources to check (off-brand slate).
        </p>
      )}
      {data.status === "ok" && data.misses.length > 0 && (
        <MissList misses={data.misses} render={(m) => `${m.sport}: ${m.matchup} — ${m.source} in blend, no linked market`} />
      )}
      {footer}
    </div>
  );
}

/**
 * Queue #223 Item 4 — unlinked-but-held: markets we hold that the matcher had
 * everything it needed to link and did not. Rides the matured-linkage payload.
 */
export function UnlinkedHeldCard({ held }: { held: UnlinkedHeld }) {
  if (held.status === "error") {
    return (
      <div className="rounded-lg border border-surface-border bg-surface-card p-4" data-section="unlinked-held" data-held-state="error">
        <h2 className="text-sm font-semibold text-text-primary">Unlinked but held</h2>
        <p className="text-xs text-text-secondary mt-2 break-words">
          Unverified — this check failed when the snapshot was built ({held.error}). The headline above is
          unaffected; this class has no number in this snapshot.
        </p>
      </div>
    );
  }
  const n = held.headline_unlinked_held;
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4" data-section="unlinked-held" data-held-state={held.status}>
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Unlinked but held</h2>
          <p className="text-xs text-text-muted mt-0.5 break-words">
            {held.definition ??
              "A Kalshi/Polymarket game-winner market we hold (open, no event) whose both teams match an imminent event. 0 = clean."}
          </p>
        </div>
        <div className={`text-2xl font-bold ${held.status !== "ok" ? "text-text-muted" : n === 0 ? "text-accent-live" : "text-accent-danger"}`}>
          {held.status !== "ok" ? "n/a" : n}
        </div>
      </div>
      {held.status === "ok" ? (
        <p className="text-xs text-text-secondary mt-2">
          {held.events_checked} imminent events checked
          {typeof held.candidates_scanned === "number" && ` · ${held.candidates_scanned} unlinked open markets scanned`}
          {typeof held.derivatives_excluded === "number" && ` · ${held.derivatives_excluded} derivative markets excluded`}
        </p>
      ) : (
        <p className="text-xs text-text-muted mt-2">No imminent events to check this class against.</p>
      )}
      {held.status === "ok" && held.misses.length > 0 && (
        <MissList
          misses={held.misses}
          render={(m) => {
            const h = m as UnlinkedHeldMiss;
            return `${h.sport}: ${h.matchup} — ${h.source} market ${h.market_name ? `"${h.market_name}" ` : ""}held, not linked`;
          }}
        />
      )}
    </div>
  );
}

/**
 * The Tier-1 and Tier-2 sport cards (14-day event→source linkage). With a
 * `notice` and no data, each section shows the notice in place of its cards.
 */
export function SportCoverageSections({
  accuracy,
  loading,
  notice,
  verdictMuted = false,
}: {
  accuracy: AccuracyData | null | undefined;
  loading: boolean;
  notice?: ReactNode;
  verdictMuted?: boolean;
}) {
  const t1 = tier1Summary(accuracy);
  const unread = !accuracy;
  const tier1Data = TIER1_SPORTS.map((s) => ({ sport: s, data: accuracy?.sports?.[s.key] }));
  const tier2Data = TIER2_SPORTS.map((s) => ({ sport: s, data: accuracy?.sports?.[s.key] }));
  const status = loading ? "loading" : t1.status;
  return (
    <>
      <MetricSection
        question="Do Tier 1 sports have sportsbook coverage?"
        status={status}
        summary={unread && notice ? (loading ? "Loading..." : "Unverified") : `${t1.linked}/${t1.total} events linked to Odds API`}
        ideal="100% of NBA, NHL, MLB, NFL, NCAAB events should have Odds API external_id."
        action={
          !unread && t1.pct < 80
            ? "These bars now measure TRUE linkage (events carrying external_id / espn_id / statpal_fixture_id), not commence_time_source. A genuinely low Odds API bar means that league's odds polling or ingestion is dropping games — check odds_polling for the sport tier and the Odds API quota circuit breaker, not the Event Registry cascade (which is verified correct)."
            : undefined
        }
        defaultExpanded
        verdictMuted={verdictMuted || (unread && !!notice)}
      >
        {unread && notice ? (
          <div className="mt-3">{notice}</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
            {tier1Data.map(({ sport, data }) => (
              <SportCard key={sport.key} sport={sport} data={data} />
            ))}
          </div>
        )}
      </MetricSection>

      <MetricSection
        question="Do Tier 2 sports have sportsbook coverage?"
        status="good"
        summary={unread && notice ? (loading ? "Loading..." : "Unverified") : `${TIER2_SPORTS.length} secondary sports tracked`}
        ideal="Tier 2 sports should have Odds API coverage where available."
        verdictMuted={verdictMuted || (unread && !!notice)}
      >
        {unread && notice ? (
          <div className="mt-3">{notice}</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
            {tier2Data.map(({ sport, data }) => (
              <SportCard key={sport.key} sport={sport} data={data} />
            ))}
          </div>
        )}
      </MetricSection>
    </>
  );
}

/** Game markets → events (`FuturesMarket.event_id`): the all-market diagnostic. */
export function PredictionMarketDiagnosticSection({
  linkRate,
  loading,
  notice,
  verdictMuted = false,
}: {
  linkRate: LinkRateData | null | undefined;
  loading: boolean;
  notice?: ReactNode;
  verdictMuted?: boolean;
}) {
  const pmPct = linkRate?.overall?.link_rate_pct ?? 0;
  const pmStatus = linkRateStatus(linkRate);
  const unread = !linkRate && !!notice;
  return (
    <MetricSection
      question="Diagnostic: all-market coverage (Kalshi/Polymarket → events)"
      status={loading ? "loading" : pmStatus}
      summary={
        loading
          ? "Loading..."
          : unread
          ? "Unverified"
          : `${linkRate?.overall?.open_linked ?? 0}/${linkRate?.overall?.open_total ?? 0} open game markets linked (${pmPct}%) — diagnostic, not the headline`
      }
      ideal="Diagnostic only (Item 2): this coverage number is structurally capped by upstream gaps and aged-out settled markets (gotcha #35), so below-100 here does NOT mean a fixable defect. The Matured linkage card above is the headline number. Every open Kalshi/Polymarket game market should carry an event_id so its line shows on the event page."
      action={
        !loading && !unread && pmPct < 80
          ? "Game markets below 80% linkage means Kalshi/Polymarket lines are missing from event pages. Run the matcher (POST /api/admin/prediction-markets/match) and check tier1-gaps for the leagues dragging the rate — this is the market→event FK, separate from the event→source linkage above. Tracked under the prediction-market matching pipeline (gotchas #15, #16)."
          : undefined
      }
      defaultExpanded={!loading && (unread || pmStatus !== "good")}
      verdictMuted={verdictMuted || unread}
    >
      <p className="text-xs text-text-muted mt-3 mb-2">
        A different question from the source bars above: this is game markets → events
        (<code className="bg-surface-card px-1 rounded">FuturesMarket.event_id</code>), the FK that
        decides whether a Kalshi/Polymarket line appears on an event page. Bars show open markets by
        league, largest first.
      </p>
      {unread ? (
        <div className="mt-2">{notice}</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
          <PredictionMarketLinkage block={linkRate?.kalshi} sourceLabel="Kalshi" />
          <PredictionMarketLinkage block={linkRate?.polymarket} sourceLabel="Polymarket" />
        </div>
      )}
      <div className="mt-3 rounded-lg bg-surface-elevated p-3 text-xs text-text-muted">
        <div className="flex items-start gap-2">
          <span className="text-base leading-none">⛳</span>
          <div>
            <span className="font-medium text-text-secondary">DataGolf: </span>
            golf-specific and event-identity-based (live in-play win probabilities + leaderboards),
            not a game-market denominator like Kalshi/Polymarket. It links via the golf event/tour
            matching engine, not this FK count — see the golf hub and the golf commence-time fixes
            rather than reading a link-rate here.
          </div>
        </div>
      </div>
    </MetricSection>
  );
}

/** Static: what each source provides, and how the Event Registry links them. */
export function SourceContributionSection({ verdictMuted = false }: { verdictMuted?: boolean }) {
  return (
    <MetricSection
      question="What does each source contribute?"
      status="good"
      summary="Source coverage breakdown"
      ideal="All three primary sources (Odds API, ESPN, StatPal) should contribute to Tier 1 events."
      verdictMuted={verdictMuted}
    >
      <div className="mt-3 overflow-x-auto rounded-lg border border-surface-border">
        <table className="w-full text-sm">
          <thead className="bg-surface-elevated text-text-muted text-xs">
            <tr>
              <th className="text-left font-medium p-3">Source</th>
              <th className="text-left font-medium p-3">Provides</th>
              <th className="text-left font-medium p-3">Coverage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border/60">
            <tr className="hover:bg-surface-elevated/40">
              <td className="p-3 font-medium text-text-primary">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-accent-brand" />
                  The Odds API
                </div>
              </td>
              <td className="p-3 text-text-secondary">Moneyline, spreads, totals from 10+ sportsbooks</td>
              <td className="p-3 text-text-secondary">All sports — the primary odds source</td>
            </tr>
            <tr className="hover:bg-surface-elevated/40">
              <td className="p-3 font-medium text-text-primary">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-accent-live" />
                  ESPN
                </div>
              </td>
              <td className="p-3 text-text-secondary">Win probability, team colors, logos, box scores, play-by-play</td>
              <td className="p-3 text-text-secondary">{TIER1_SPORTS.length + TIER2_SPORTS.length}+ sports via ESPN API</td>
            </tr>
            <tr className="hover:bg-surface-elevated/40">
              <td className="p-3 font-medium text-text-primary">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-accent-futures" />
                  StatPal
                </div>
              </td>
              <td className="p-3 text-text-secondary">Schedules, rosters, injuries, live scores, standings</td>
              <td className="p-3 text-text-secondary">5 core sports (NFL, NBA, MLB, NHL, soccer)</td>
            </tr>
            <tr className="hover:bg-surface-elevated/40">
              <td className="p-3 font-medium text-text-primary">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-accent-warning" />
                  Kalshi / Polymarket
                </div>
              </td>
              <td className="p-3 text-text-secondary">Prediction-market prices (game markets, futures, props)</td>
              <td className="p-3 text-text-secondary">Linked to events via <code className="bg-surface-card px-1 rounded">event_id</code> — see the section above</td>
            </tr>
            <tr className="hover:bg-surface-elevated/40">
              <td className="p-3 font-medium text-text-primary">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-accent-live" />
                  DataGolf
                </div>
              </td>
              <td className="p-3 text-text-secondary">Golf predictions, live in-play win probabilities, leaderboards</td>
              <td className="p-3 text-text-secondary">Golf only (PGA/LPGA/DP World tours)</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mt-3 rounded-lg bg-surface-elevated p-3 text-xs text-text-muted">
        <div className="flex items-start gap-2">
          <Link2 className="w-4 h-4 mt-0.5 text-accent-brand shrink-0" />
          <div>
            <span className="font-medium text-text-secondary">How linking works: </span>
            When any source encounters a game, the Event Registry tries to match it to an existing event
            by source ID, then by sport + time + team names. If all sources match correctly, each event
            has an <code className="bg-surface-card px-1 rounded">external_id</code> (Odds API),{" "}
            <code className="bg-surface-card px-1 rounded">espn_id</code>, and{" "}
            <code className="bg-surface-card px-1 rounded">statpal_fixture_id</code>. When linking
            fails, odds snapshots attach to orphaned duplicate events that users never see.
          </div>
        </div>
      </div>
    </MetricSection>
  );
}
