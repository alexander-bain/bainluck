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
  sources: Record<string, number>;
}

interface AccuracyData {
  period_days: number;
  sports: Record<string, SportAccuracy>;
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
            ? "The Event Registry cascade may not be matching correctly. Check event_registry.py structured match and the merge_duplicate_events task."
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
