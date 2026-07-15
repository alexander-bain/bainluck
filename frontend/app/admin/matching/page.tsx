"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import { adminFetch } from "@/lib/adminFetch";
import PageHeader from "@/components/admin/PageHeader";
import MetricSection from "@/components/admin/MetricSection";
import { AlertTriangle, CheckCircle2, Database, Link2, Unlink } from "lucide-react";

interface SourceCounts {
  total: number;
  odds_api: number;
  espn: number;
  statpal: number;
  [key: string]: number;
}

interface SportAccuracy {
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

interface AccuracyData {
  period_days: number;
  sports: Record<string, SportAccuracy>;
}

// L2-128 Item 2a: the page predated the prediction-market era, so it only showed
// event→source linkage (Odds API / ESPN / StatPal). Kalshi & Polymarket link the
// OTHER direction — game markets → events (via FuturesMarket.event_id) — which is
// what makes a Kalshi/Polymarket line show up on an event page at all. We surface
// it from the existing /prediction-markets/link-rate endpoint (no backend change).
interface LinkRateSport {
  sport: string;
  league: string | null;
  total: number;
  linked: number;
  open_total: number;
  open_linked: number;
  link_rate: number;
  link_rate_all: number;
}
interface LinkRateSourceBlock {
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
interface LinkRateData {
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

const TIER1_SPORTS = [
  { key: "basketball_nba", label: "NBA", emoji: "🏀" },
  { key: "icehockey_nhl", label: "NHL", emoji: "🏒" },
  { key: "baseball_mlb", label: "MLB", emoji: "⚾" },
  { key: "americanfootball_nfl", label: "NFL", emoji: "🏈" },
  { key: "basketball_ncaab", label: "NCAAB", emoji: "🏀" },
];

const TIER2_SPORTS = [
  { key: "basketball_wnba", label: "WNBA", emoji: "🏀" },
  { key: "soccer_epl", label: "EPL", emoji: "⚽" },
  { key: "soccer_usa_mls", label: "MLS", emoji: "⚽" },
  { key: "mma_mixed_martial_arts", label: "MMA", emoji: "🥊" },
];

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
    <div className={`bg-surface-card rounded-xl border ${statusBg} p-4`}>
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
    <div className={`bg-surface-card rounded-xl border ${statusBg} p-4`}>
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

export default function MatchingPage() {
  usePageTracking({ pageType: "admin_matching", pageTitle: "Admin: Data Quality — Matching" });
  useScrollDepth({ pageType: "admin_matching" });
  useEngagementTime({ pageType: "admin_matching" });

  const { secret } = useAdminAuth();

  const { data: accuracy, isLoading } = useSWR<AccuracyData>(
    ["schedule-accuracy", secret],
    () =>
      adminFetch("/api/admin/schedule/accuracy?days=14", secret)
        .then((r) => r.ok ? r.json() : null),
    { refreshInterval: 300000 }
  );

  // L2-128 Item 2a: prediction-market linkage (game markets → events). Served
  // from the L2-90 warm cache; a cold read falls back to inline compute.
  const { data: linkRate, isLoading: linkRateLoading } = useSWR<LinkRateData>(
    ["prediction-market-link-rate", secret],
    () =>
      adminFetch("/api/admin/prediction-markets/link-rate", secret)
        .then((r) => r.ok ? r.json() : null),
    { refreshInterval: 300000 }
  );

  const tier1Data = TIER1_SPORTS.map((s) => ({
    sport: s,
    data: accuracy?.sports?.[s.key],
  }));

  const tier2Data = TIER2_SPORTS.map((s) => ({
    sport: s,
    data: accuracy?.sports?.[s.key],
  }));

  const tier1Total = tier1Data.reduce((sum, s) => sum + (s.data?.total ?? 0), 0);
  const tier1Linked = tier1Data.reduce((sum, s) => sum + (s.data?.sources?.odds_api ?? 0), 0);
  const tier1Pct = tier1Total > 0 ? Math.round((tier1Linked / tier1Total) * 100) : 0;

  const overallStatus = tier1Pct >= 80 ? "good" : tier1Pct >= 50 ? "warning" : "critical";

  const pmPct = linkRate?.overall?.link_rate_pct ?? 0;
  const pmStatus: "good" | "warning" | "critical" = pmPct >= 80 ? "good" : pmPct >= 50 ? "warning" : "critical";

  return (
    <div className="max-w-4xl space-y-6">
      <PageHeader
        question="Are events properly linked across data sources?"
        status={isLoading ? "loading" : overallStatus as "good" | "warning" | "critical"}
        summary={
          isLoading
            ? "Loading..."
            : `${tier1Linked}/${tier1Total} Tier 1 events have Odds API data (${tier1Pct}%)`
        }
        ideal="Every Tier 1 event should have Odds API, ESPN, and StatPal data."
        subtitle="Source linkage determines whether event pages show sportsbook odds, charts, and cross-source comparison."
      />

      <MetricSection
        question="Do Tier 1 sports have sportsbook coverage?"
        status={overallStatus as "good" | "warning" | "critical"}
        summary={`${tier1Linked}/${tier1Total} events linked to Odds API`}
        ideal="100% of NBA, NHL, MLB, NFL, NCAAB events should have Odds API external_id."
        action={
          tier1Pct < 80
            ? "These bars now measure TRUE linkage (events carrying external_id / espn_id / statpal_fixture_id), not commence_time_source. A genuinely low Odds API bar means that league's odds polling or ingestion is dropping games — check odds_polling for the sport tier and the Odds API quota circuit breaker, not the Event Registry cascade (which is verified correct)."
            : undefined
        }
        defaultExpanded
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
          {tier1Data.map(({ sport, data }) => (
            <SportCard key={sport.key} sport={sport} data={data} />
          ))}
        </div>
      </MetricSection>

      <MetricSection
        question="Do Tier 2 sports have sportsbook coverage?"
        status="good"
        summary={`${TIER2_SPORTS.length} secondary sports tracked`}
        ideal="Tier 2 sports should have Odds API coverage where available."
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-3">
          {tier2Data.map(({ sport, data }) => (
            <SportCard key={sport.key} sport={sport} data={data} />
          ))}
        </div>
      </MetricSection>

      <MetricSection
        question="Are prediction markets linked to events?"
        status={linkRateLoading ? "loading" : pmStatus}
        summary={
          linkRateLoading
            ? "Loading..."
            : `${linkRate?.overall?.open_linked ?? 0}/${linkRate?.overall?.open_total ?? 0} open game markets linked (${pmPct}%)`
        }
        ideal="Every open Kalshi/Polymarket game market should carry an event_id so its line shows on the event page."
        action={
          !linkRateLoading && pmPct < 80
            ? "Game markets below 80% linkage means Kalshi/Polymarket lines are missing from event pages. Run the matcher (POST /api/admin/prediction-markets/match) and check tier1-gaps for the leagues dragging the rate — this is the market→event FK, separate from the event→source linkage above. Tracked under the prediction-market matching pipeline (gotchas #15, #16)."
            : undefined
        }
        defaultExpanded={!linkRateLoading && pmStatus !== "good"}
      >
        <p className="text-xs text-text-muted mt-3 mb-2">
          A different question from the source bars above: this is game markets → events
          (<code className="bg-surface-card px-1 rounded">FuturesMarket.event_id</code>), the FK that
          decides whether a Kalshi/Polymarket line appears on an event page. Bars show open markets by
          league, largest first.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
          <PredictionMarketLinkage block={linkRate?.kalshi} sourceLabel="Kalshi" />
          <PredictionMarketLinkage block={linkRate?.polymarket} sourceLabel="Polymarket" />
        </div>
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

      <MetricSection
        question="What does each source contribute?"
        status="good"
        summary="Source coverage breakdown"
        ideal="All three primary sources (Odds API, ESPN, StatPal) should contribute to Tier 1 events."
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
    </div>
  );
}
