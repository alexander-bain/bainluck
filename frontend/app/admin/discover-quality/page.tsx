"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import {
  AlertTriangle,
  BarChart3,
  ChevronDown,
  CheckCircle2,
  Filter,
  Play,
  RefreshCw,
  Search,
} from "lucide-react";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface DebugSummary {
  items: number;
  boring_count: number;
  ladder_count: number;
  duplicate_family_count: number;
  duplicate_families: Record<string, number>;
  explanation_ok_count: number;
  ground_truth_hit_count_50: number;
  positive_archetype_hits: number;
  positive_targets_total: number;
  strict_variety_hits: number;
  strict_targets_total: number;
  category_spread: number;
  max_category_count: number;
  category_distribution: Record<string, number>;
  archetype_distribution: Record<string, number>;
  positive_targets: Record<string, boolean>;
  strict_targets: Record<string, boolean>;
}

interface DebugItem {
  rank: number;
  type: string;
  id: number | null;
  score: number;
  name: string;
  category: string;
  archetype: string;
  source: string;
  headline: string | null;
  reason: string | null;
  hook: boolean;
  image: boolean;
  explanation_ok: boolean;
  quality_class: string;
  family_key: string;
  story_key: string | null;
  ladder: boolean;
  reasons: string[];
  ground_truth: boolean;
  personalization_trace?: PersonalizationTrace | null;
}

interface PersonalizationTrace {
  item_type: string;
  category: string;
  base_score: number;
  final_score: number;
  score_delta: number;
  multiplier: number;
  is_personalized: boolean;
  reasons: string[];
  category_affinity_delta: number;
  bounded: boolean;
}

interface MissingGroundTruthItem {
  name: string;
  source: string;
  category: string;
  probability: string | null;
  quality_class: string;
  archetype: string;
  reasons: string[];
  family_key: string;
  story_key: string | null;
  triage_bucket: string;
  recommended_action: string;
  db_trace?: MissingDbTrace;
}

interface MissingDbMatch {
  id: number;
  name: string;
  source: string;
  status: string;
  category: string | null;
  market_tier: number | null;
  volume_24h: number | null;
  resolution_date: string | null;
  has_hook: boolean;
  has_image: boolean;
  blocked_reasons: string[];
}

interface MissingDbTrace {
  trace_status: string;
  trace_summary: string;
  recommended_action: string;
  matches: MissingDbMatch[];
}

interface MissingGroundTruthSummary {
  total: number;
  bucket_counts: Record<string, number>;
}

interface FeedDebugResponse {
  debug_summary: DebugSummary;
  debug_items: DebugItem[];
  missing_ground_truth: MissingGroundTruthItem[];
  missing_ground_truth_summary: MissingGroundTruthSummary;
  debug_timing?: {
    total_ms: number;
    stages: Array<{
      stage: string;
      ms: number;
      elapsed_ms: number;
    }>;
  };
}

interface CandidatePoolTrace {
  name: string;
  limit: number;
  candidate_count: number;
  included: boolean;
  position: number | null;
}

interface DiscoverMarketTrace {
  market: {
    id: number;
    name: string;
    source: string;
    status: string;
    category: string | null;
    llm_sport_category: string | null;
    market_tier: number | null;
    market_type: string | null;
    external_id: string | null;
    canonical_market_key: string | null;
    source_count: number;
    volume_24h: number | null;
    resolution_date: string | null;
    updated_at: string | null;
  };
  base_eligibility: {
    eligible: boolean;
    blockers: string[];
    checks: Record<string, string | number | boolean | null>;
  };
  candidate_pools: {
    included: boolean;
    deduped_candidate_count: number;
    candidate_position: number | null;
    pools: CandidatePoolTrace[];
  };
  score_trace: {
    eligible_before_caps: boolean;
    blockers: string[];
    runtime_filters: {
      eligible: boolean;
      blockers: string[];
      checks: Record<string, string | number | boolean | null>;
    };
    scores: {
      highlight: number;
      after_quality: number;
      after_explanation: number;
      personalization_multiplier: number;
      final: number;
    };
    highlight: {
      headline: string | null;
      reason: string | null;
      primary_reason: string | null;
      reasons: string[];
      leader_name: string | null;
      leader_probability: number | null;
      top_mover_name: string | null;
      top_mover_change: number | null;
      top_surprise_name: string | null;
      top_surprise_change: number | null;
    };
    quality: {
      class: string;
      family_key: string;
      story_key: string | null;
      reasons: string[];
    };
    explanation: {
      has_hook: boolean;
      has_image: boolean;
      headline_ok: boolean;
    };
    top_outcomes: Array<{
      name: string;
      probability: number | null;
      probability_change_24h: number | null;
      rank: number | null;
      rank_change_24h: number | null;
      opening_probability: number | null;
    }>;
  };
  final_ranking: {
    survived_final_caps: boolean;
    final_futures_rank: number | null;
    final_score: number | null;
    scored_futures_count: number;
  };
  rank_phases?: {
    mode: {
      include_events: boolean;
      event_pct: number | null;
      limit: number;
    };
    raw_futures_rank: number | null;
    post_canonical_dedupe_rank: number | null;
    post_initial_sort_rank: number | null;
    post_event_demote_rank: number | null;
    post_event_mix_rank: number | null;
    post_diversity_rank: number | null;
    returned_rank: number | null;
    returned: boolean;
    raw_futures_count: number;
    post_dedupe_futures_count: number;
    assembled_count: number;
    dropped_by_canonical_dedupe: boolean;
    canonical_replacement: {
      id: number | null;
      name: string | null;
      score: number | null;
    } | null;
  };
  suggested_fix: string;
}

interface HookCoverage {
  total_open: number;
  with_hook: number;
  with_image: number;
  hook_pct: number;
  image_pct: number;
  latest_hook_generated_at: string | null;
  hooks_generated_last_24h: number;
  tier_1_3_total: number;
  tier_1_3_with_hook: number;
  tier_1_3_hook_pct: number;
}

interface DiscoverEngagementGroup {
  surface: string;
  category: string;
  item_type: string;
  impressions: number;
  opens: number;
  dismisses: number;
  shares: number;
  likes: number;
  group_expands: number;
  context_expands: number;
  context_collapses: number;
  challenge_starts: number;
  challenge_completes: number;
  actions: number;
  open_rate: number;
  dismiss_rate: number;
  share_rate: number;
  context_expand_rate: number;
  challenge_completion_rate: number;
}

interface DiscoverEngagementItem {
  item_type: string;
  item_id: string;
  item_name: string | null;
  category: string | null;
  surface: string | null;
  actions: number;
}

interface DiscoverEngagementOpportunity {
  kind: "promote" | "investigate" | "downrank";
  priority: number;
  label: string;
  surface: string;
  category: string;
  item_type: string;
  metric: string;
  value: number;
  impressions: number;
  recommendation: string;
}

interface DiscoverEngagementResponse {
  days: number;
  totals: {
    impressions: number;
    opens: number;
    dismisses: number;
    shares: number;
    likes: number;
    group_expands: number;
    context_expands: number;
    context_collapses: number;
    challenge_starts: number;
    challenge_completes: number;
    actions: number;
    open_rate: number;
    dismiss_rate: number;
    share_rate: number;
    context_expand_rate: number;
    challenge_completion_rate: number;
  };
  groups: DiscoverEngagementGroup[];
  opportunities: DiscoverEngagementOpportunity[];
  top_items: DiscoverEngagementItem[];
}

async function fetchDiscoverDebug(secret: string): Promise<FeedDebugResponse> {
  const params = new URLSearchParams({
    limit: "50",
    include_events: "false",
    include_futures: "true",
    event_pct: "0.15",
    debug: "true",
    secret,
  });
  const res = await fetch(`${API_URL}/api/feed?${params}`);
  if (!res.ok) throw new Error(`Feed debug API error: ${res.status}`);
  return res.json();
}

async function fetchHookCoverage(secret: string): Promise<HookCoverage> {
  const res = await fetch(
    `${API_URL}/api/admin/hook-coverage?secret=${encodeURIComponent(secret)}`
  );
  if (!res.ok) throw new Error(`Hook coverage API error: ${res.status}`);
  return res.json();
}

async function fetchDiscoverTrace(secret: string, marketId: number): Promise<DiscoverMarketTrace> {
  const res = await fetch(
    `${API_URL}/api/admin/discover-quality/trace/${marketId}?secret=${encodeURIComponent(secret)}&include_events=false&event_pct=0.15&limit=50`
  );
  if (!res.ok) throw new Error(`Trace API error: ${res.status}`);
  return res.json();
}

async function fetchDiscoverEngagement(secret: string, days: number): Promise<DiscoverEngagementResponse> {
  const res = await fetch(
    `${API_URL}/api/admin/discover-engagement?secret=${encodeURIComponent(secret)}&days=${days}`
  );
  if (!res.ok) throw new Error(`Engagement API error: ${res.status}`);
  return res.json();
}

function ratioText(value: number, total: number) {
  return `${value}/${total}`;
}

function formatTargetName(name: string) {
  return name.replaceAll("_", " ");
}

function StatCard({
  label,
  value,
  ok,
  sub,
}: {
  label: string;
  value: string | number;
  ok?: boolean;
  sub?: string;
}) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-text-muted">{label}</span>
        {ok === undefined ? null : ok ? (
          <CheckCircle2 className="w-4 h-4 text-accent-live" />
        ) : (
          <AlertTriangle className="w-4 h-4 text-accent-danger" />
        )}
      </div>
      <div className="mt-2 text-2xl font-semibold text-text-primary">{value}</div>
      {sub && <div className="mt-1 text-xs text-text-muted">{sub}</div>}
    </div>
  );
}

function DistributionBars({
  title,
  data,
}: {
  title: string;
  data: Record<string, number>;
}) {
  const entries = Object.entries(data);
  const max = Math.max(...entries.map(([, count]) => count), 1);

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4">
      <h2 className="text-sm font-semibold text-text-primary mb-3">{title}</h2>
      <div className="space-y-2">
        {entries.map(([name, count]) => (
          <div key={name}>
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="text-text-secondary truncate">{formatTargetName(name)}</span>
              <span className="text-text-muted">{count}</span>
            </div>
            <div className="mt-1 h-1.5 bg-surface-elevated rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-futures rounded-full"
                style={{ width: `${Math.max(4, (count / max) * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusPill({ children, tone }: { children: string; tone: "ok" | "warn" | "muted" }) {
  const classes =
    tone === "ok"
      ? "bg-accent-live/10 text-accent-live border-accent-live/30"
      : tone === "warn"
        ? "bg-accent-danger/10 text-accent-danger border-accent-danger/30"
        : "bg-surface-elevated text-text-muted border-surface-border";

  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${classes}`}>
      {children}
    </span>
  );
}

function percentText(value: number | null) {
  return value === null ? "none" : `${Math.round(value * 100)}%`;
}

function rateText(value: number) {
  return `${Math.round(value * 100)}%`;
}

function signedNumber(value: number, digits = 0) {
  const fixed = value.toFixed(digits);
  return value > 0 ? `+${fixed}` : fixed;
}

function rankText(value: number | null) {
  return value === null ? "out" : `#${value}`;
}

function TracePanel({ trace }: { trace: DiscoverMarketTrace }) {
  const phases = trace.rank_phases;
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3 space-y-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-semibold text-text-primary">Suggested fix</div>
          <div className="text-xs text-text-secondary mt-1">{trace.suggested_fix}</div>
        </div>
        <div className="flex flex-wrap justify-end gap-1 shrink-0">
          <StatusPill tone={trace.base_eligibility.eligible ? "ok" : "warn"}>
            {trace.base_eligibility.eligible ? "base eligible" : "base blocked"}
          </StatusPill>
          <StatusPill tone={trace.candidate_pools.included ? "ok" : "warn"}>
            {trace.candidate_pools.included ? "in pool" : "pool miss"}
          </StatusPill>
          <StatusPill tone={trace.final_ranking.survived_final_caps ? "ok" : "warn"}>
            {trace.final_ranking.survived_final_caps ? "survived caps" : "not in final"}
          </StatusPill>
        </div>
      </div>

      <div className="grid md:grid-cols-4 gap-2 text-xs">
        <div>
          <div className="text-text-muted">Score path</div>
          <div className="text-text-primary font-medium">
            {trace.score_trace.scores.highlight} → {trace.score_trace.scores.after_quality} → {trace.score_trace.scores.after_explanation} → {trace.score_trace.scores.final}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Returned rank</div>
          <div className="text-text-primary font-medium">
            {rankText(phases?.returned_rank ?? null)}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Candidate position</div>
          <div className="text-text-primary font-medium">
            {trace.candidate_pools.candidate_position ? `#${trace.candidate_pools.candidate_position}` : "none"}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Quality</div>
          <div className="text-text-primary font-medium">{formatTargetName(trace.score_trace.quality.class)}</div>
        </div>
      </div>

      <div className="text-xs">
        <div className="text-text-muted">Headline</div>
        <div className="text-text-primary mt-1">{trace.score_trace.highlight.headline || "No headline"}</div>
        {trace.score_trace.highlight.reason && (
          <div className="text-text-secondary mt-1">{trace.score_trace.highlight.reason}</div>
        )}
      </div>

      {phases && (
        <div className="text-xs">
          <div className="font-medium text-text-primary mb-1">Rank Phases</div>
          <div className="grid md:grid-cols-3 gap-2">
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">Raw futures</span>
              <span className="text-text-primary">{rankText(phases.raw_futures_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">After canonical dedupe</span>
              <span className="text-text-primary">{rankText(phases.post_canonical_dedupe_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">Initial feed sort</span>
              <span className="text-text-primary">{rankText(phases.post_initial_sort_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">After event demotion</span>
              <span className="text-text-primary">{rankText(phases.post_event_demote_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">After event mix</span>
              <span className="text-text-primary">{rankText(phases.post_event_mix_rank)}</span>
            </div>
            <div className="flex justify-between gap-2">
              <span className="text-text-secondary">After diversity</span>
              <span className="text-text-primary">{rankText(phases.post_diversity_rank)}</span>
            </div>
          </div>
          {phases.dropped_by_canonical_dedupe && phases.canonical_replacement && (
            <div className="mt-2 text-text-muted">
              Deduped behind #{phases.canonical_replacement.id}: {phases.canonical_replacement.name}
            </div>
          )}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-3 text-xs">
        <div>
          <div className="font-medium text-text-primary mb-1">Candidate Pools</div>
          <div className="space-y-1">
            {trace.candidate_pools.pools.map((pool) => (
              <div key={pool.name} className="flex items-center justify-between gap-2">
                <span className="text-text-secondary">{formatTargetName(pool.name)}</span>
                <span className={pool.included ? "text-accent-live" : "text-text-muted"}>
                  {pool.included ? `#${pool.position}` : "out"} / {pool.candidate_count}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="font-medium text-text-primary mb-1">Blockers & Signals</div>
          <div className="flex flex-wrap gap-1">
            {trace.base_eligibility.blockers.map((blocker) => (
              <StatusPill key={blocker} tone="warn">{formatTargetName(blocker)}</StatusPill>
            ))}
            {trace.score_trace.blockers.map((blocker) => (
              <StatusPill key={blocker} tone="warn">{formatTargetName(blocker)}</StatusPill>
            ))}
            {trace.score_trace.quality.reasons.map((reason) => (
              <StatusPill key={reason} tone="muted">{formatTargetName(reason)}</StatusPill>
            ))}
            {trace.score_trace.explanation.has_hook && <StatusPill tone="ok">hook</StatusPill>}
            {trace.score_trace.explanation.has_image && <StatusPill tone="ok">image</StatusPill>}
          </div>
        </div>
      </div>

      {trace.score_trace.top_outcomes.length > 0 && (
        <div className="text-xs">
          <div className="font-medium text-text-primary mb-1">Top Outcomes</div>
          <div className="grid md:grid-cols-2 gap-1">
            {trace.score_trace.top_outcomes.slice(0, 4).map((outcome) => (
              <div key={outcome.name} className="flex justify-between gap-3 text-text-secondary">
                <span className="truncate">{outcome.name}</span>
                <span className="shrink-0">
                  {percentText(outcome.probability)}
                  {outcome.probability_change_24h !== null ? ` (${outcome.probability_change_24h > 0 ? "+" : ""}${Math.round(outcome.probability_change_24h * 100)}pp)` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EngagementPanel({ data }: { data: DiscoverEngagementResponse }) {
  const strongestOpens = data.groups
    .filter((row) => row.impressions >= 5)
    .sort((a, b) => b.open_rate - a.open_rate)
    .slice(0, 5);
  const highDismiss = data.groups
    .filter((row) => row.impressions >= 5)
    .sort((a, b) => b.dismiss_rate - a.dismiss_rate)
    .slice(0, 5);
  const shareSignals = data.groups
    .filter((row) => row.impressions >= 5)
    .sort((a, b) => b.share_rate - a.share_rate)
    .slice(0, 5);
  const contextSignals = data.groups
    .filter((row) => row.impressions >= 5)
    .sort((a, b) => (b.context_expand_rate ?? 0) - (a.context_expand_rate ?? 0))
    .slice(0, 5);

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Engagement</h2>
          <p className="text-xs text-text-muted mt-1">
            First-party Discover behavior from web and native over {data.days} day{data.days === 1 ? "" : "s"}.
          </p>
        </div>
        <BarChart3 className="w-4 h-4 text-text-muted" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <div className="text-xs text-text-muted">Impressions</div>
          <div className="text-lg font-semibold text-text-primary">{data.totals.impressions.toLocaleString()}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Open rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.totals.open_rate)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Dismiss rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.totals.dismiss_rate)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Share rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.totals.share_rate)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Context expands</div>
          <div className="text-lg font-semibold text-text-primary">{(data.totals.context_expands ?? 0).toLocaleString()}</div>
          <div className="text-[11px] text-text-muted">{rateText(data.totals.context_expand_rate ?? 0)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Challenge starts</div>
          <div className="text-lg font-semibold text-text-primary">{(data.totals.challenge_starts ?? 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Challenge completes</div>
          <div className="text-lg font-semibold text-text-primary">{(data.totals.challenge_completes ?? 0).toLocaleString()}</div>
          <div className="text-[11px] text-text-muted">{rateText(data.totals.challenge_completion_rate ?? 0)}</div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Actions</div>
          <div className="text-lg font-semibold text-text-primary">{data.totals.actions.toLocaleString()}</div>
        </div>
      </div>

      {data.totals.impressions === 0 ? (
        <div className="text-sm text-text-muted rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
          No first-party engagement captured yet. Open `/discover` on web or native after this deploy to start populating this panel.
        </div>
      ) : (
        <div className="grid lg:grid-cols-4 gap-3">
          <EngagementList title="Strong Opens" rows={strongestOpens} metric="open_rate" />
          <EngagementList title="High Dismiss" rows={highDismiss} metric="dismiss_rate" warn />
          <EngagementList title="Share Signals" rows={shareSignals} metric="share_rate" />
          <EngagementList title="Context Expands" rows={contextSignals} metric="context_expand_rate" />
        </div>
      )}

      {data.opportunities.length > 0 && (
        <div>
          <div className="text-xs font-medium text-text-primary mb-2">Ranking Opportunities</div>
          <div className="grid md:grid-cols-2 gap-2">
            {data.opportunities.slice(0, 6).map((item) => (
              <div key={`${item.kind}-${item.label}-${item.metric}`} className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-text-primary truncate">{item.label}</div>
                    <div className="text-xs text-text-secondary mt-1">{item.recommendation}</div>
                  </div>
                  <StatusPill tone={item.kind === "investigate" ? "warn" : item.kind === "promote" ? "ok" : "muted"}>
                    {item.kind}
                  </StatusPill>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  <StatusPill tone="muted">{formatTargetName(item.metric)}</StatusPill>
                  <StatusPill tone="muted">{rateText(item.value)}</StatusPill>
                  <StatusPill tone="muted">{`${item.impressions} impressions`}</StatusPill>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.top_items.length > 0 && (
        <div>
          <div className="text-xs font-medium text-text-primary mb-2">Top Actioned Items</div>
          <div className="grid md:grid-cols-2 gap-2">
            {data.top_items.slice(0, 6).map((item) => (
              <div key={`${item.item_type}-${item.item_id}`} className="rounded-lg border border-surface-border bg-surface-elevated/40 p-2">
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-text-primary font-medium truncate">
                    {item.item_name || `${item.item_type} #${item.item_id}`}
                  </span>
                  <span className="text-text-muted shrink-0">{item.actions} actions</span>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  <StatusPill tone="muted">{item.surface || "unknown"}</StatusPill>
                  <StatusPill tone="muted">{item.category || "other"}</StatusPill>
                  <StatusPill tone="muted">{item.item_type}</StatusPill>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EngagementList({
  title,
  rows,
  metric,
  warn,
}: {
  title: string;
  rows: DiscoverEngagementGroup[];
  metric: "open_rate" | "dismiss_rate" | "share_rate" | "context_expand_rate";
  warn?: boolean;
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
      <div className="text-xs font-medium text-text-primary mb-2">{title}</div>
      {rows.length === 0 ? (
        <div className="text-xs text-text-muted">Needs at least 5 impressions per group.</div>
      ) : (
        <div className="space-y-2">
          {rows.map((row) => (
            <div key={`${title}-${row.surface}-${row.category}-${row.item_type}`}>
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="text-text-secondary truncate">
                  {row.surface} · {formatTargetName(row.category)} · {row.item_type}
                </span>
                <span className={warn ? "text-accent-danger" : "text-accent-live"}>
                  {rateText(row[metric])}
                </span>
              </div>
              <div className="text-[11px] text-text-muted">
                {row.impressions} impressions, {row.opens} opens, {row.dismisses} dismisses, {row.shares} shares, {row.context_expands ?? 0} expands
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DiscoverQualityPage() {
  usePageTracking({
    pageType: "admin_discover_quality",
    pageTitle: "Admin: Discover Quality",
  });
  useScrollDepth({ pageType: "admin_discover_quality" });
  useEngagementTime({ pageType: "admin_discover_quality" });

  const [secret, setSecret] = useState("");
  const [submittedSecret, setSubmittedSecret] = useState<string | null>(null);
  const [category, setCategory] = useState("all");
  const [archetype, setArchetype] = useState("all");
  const [quality, setQuality] = useState("all");
  const [missingBucket, setMissingBucket] = useState("all");
  const [search, setSearch] = useState("");
  const [triggering, setTriggering] = useState(false);
  const [engagementDays, setEngagementDays] = useState(7);
  const [expandedTraceId, setExpandedTraceId] = useState<number | null>(null);
  const [traceByMarketId, setTraceByMarketId] = useState<Record<number, DiscoverMarketTrace>>({});
  const [traceLoadingId, setTraceLoadingId] = useState<number | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("secret");
    if (fromUrl) {
      setSecret(fromUrl);
      setSubmittedSecret(fromUrl);
    }
  }, []);

  const debugKey = submittedSecret ? ["discover-quality", submittedSecret] : null;
  const hookKey = submittedSecret ? ["hook-coverage", submittedSecret] : null;
  const engagementKey = submittedSecret ? ["discover-engagement", submittedSecret, engagementDays] : null;

  const { data, error, isLoading } = useSWR(
    debugKey,
    () => fetchDiscoverDebug(submittedSecret!),
    { refreshInterval: 60000 }
  );

  const { data: hookCoverage } = useSWR(
    hookKey,
    () => fetchHookCoverage(submittedSecret!),
    { refreshInterval: 60000 }
  );

  const { data: engagementData } = useSWR(
    engagementKey,
    () => fetchDiscoverEngagement(submittedSecret!, engagementDays),
    { refreshInterval: 60000 }
  );

  const categories = useMemo(
    () => Array.from(new Set((data?.debug_items || []).map((item) => item.category))).sort(),
    [data]
  );
  const archetypes = useMemo(
    () => Array.from(new Set((data?.debug_items || []).map((item) => item.archetype))).sort(),
    [data]
  );
  const qualities = useMemo(
    () => Array.from(new Set((data?.debug_items || []).map((item) => item.quality_class))).sort(),
    [data]
  );
  const missingBuckets = useMemo(
    () => Object.keys(data?.missing_ground_truth_summary?.bucket_counts || {}).sort(),
    [data]
  );

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data?.debug_items || []).filter((item) => {
      if (category !== "all" && item.category !== category) return false;
      if (archetype !== "all" && item.archetype !== archetype) return false;
      if (quality !== "all" && item.quality_class !== quality) return false;
      if (query && !`${item.name} ${item.headline || ""} ${item.reason || ""}`.toLowerCase().includes(query)) {
        return false;
      }
      return true;
    });
  }, [archetype, category, data, quality, search]);

  const filteredMissingGroundTruth = useMemo(() => {
    return (data?.missing_ground_truth || []).filter((item) => {
      if (missingBucket !== "all" && item.triage_bucket !== missingBucket) return false;
      return true;
    });
  }, [data, missingBucket]);

  const triggerHooks = async () => {
    if (!submittedSecret) return;
    setTriggering(true);
    try {
      const res = await fetch(
        `${API_URL}/api/admin/hook-enrichment/trigger?secret=${encodeURIComponent(submittedSecret)}&limit=100`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error(`Trigger failed: ${res.status}`);
      await mutate(hookKey);
    } finally {
      setTriggering(false);
    }
  };

  const toggleTrace = async (marketId: number) => {
    if (!submittedSecret) return;
    if (expandedTraceId === marketId) {
      setExpandedTraceId(null);
      return;
    }
    setExpandedTraceId(marketId);
    setTraceError(null);
    if (traceByMarketId[marketId]) return;

    setTraceLoadingId(marketId);
    try {
      const trace = await fetchDiscoverTrace(submittedSecret, marketId);
      setTraceByMarketId((prev) => ({ ...prev, [marketId]: trace }));
    } catch (err) {
      setTraceError(err instanceof Error ? err.message : "Trace failed");
    } finally {
      setTraceLoadingId(null);
    }
  };

  if (!submittedSecret) {
    return (
      <div className="max-w-md mx-auto mt-20 space-y-4">
        <h1 className="text-lg font-bold text-text-primary">Discover Quality</h1>
        <p className="text-sm text-text-muted">Enter admin secret to inspect feed ranking diagnostics.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSubmittedSecret(secret);
          }}
          className="flex gap-2"
        >
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Admin secret"
            className="flex-1 px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-sm text-text-primary"
          />
          <button
            type="submit"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-text-primary text-surface-deep text-sm font-medium"
          >
            <Search className="w-4 h-4" />
            Load
          </button>
        </form>
      </div>
    );
  }

  const summary = data?.debug_summary;
  const failedStrict = summary
    ? Object.entries(summary.strict_targets).filter(([, passed]) => !passed)
    : [];
  const failedPositive = summary
    ? Object.entries(summary.positive_targets).filter(([, passed]) => !passed)
    : [];

  return (
    <div className="space-y-6 max-w-7xl mx-auto px-4 pb-10">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold text-text-primary">Discover Quality</h1>
          <a href={`/admin?secret=${encodeURIComponent(submittedSecret)}`} className="text-xs font-medium text-accent-futures hover:underline">
            Admin Dashboard
          </a>
        </div>
        <button
          type="button"
          onClick={() => mutate(debugKey)}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-surface-border text-sm text-text-secondary hover:text-text-primary hover:bg-surface-elevated"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-surface-card border border-accent-danger/40 text-accent-danger rounded-lg p-3 text-sm">
          {error.message}
        </div>
      )}
      {isLoading && <div className="text-sm text-text-muted animate-pulse">Loading Discover diagnostics...</div>}

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Boring @20" value={`${summary.boring_count}/20`} ok={summary.boring_count === 0} />
            <StatCard label="Ladders @20" value={`${summary.ladder_count}/20`} ok={summary.ladder_count === 0} />
            <StatCard label="Explanations @20" value={`${summary.explanation_ok_count}/20`} ok={summary.explanation_ok_count === 20} />
            <StatCard
              label="Strict Variety"
              value={ratioText(summary.strict_variety_hits, summary.strict_targets_total)}
              ok={summary.strict_variety_hits >= 4}
              sub={`Spread ${summary.category_spread}, max category ${summary.max_category_count}`}
            />
            <StatCard
              label="Positive Archetypes"
              value={ratioText(summary.positive_archetype_hits, summary.positive_targets_total)}
              ok={summary.positive_archetype_hits >= 5}
            />
            <StatCard label="Duplicate Families" value={`${summary.duplicate_family_count}/20`} ok={summary.duplicate_family_count === 0} />
            <StatCard label="Ground Truth @50" value={`${summary.ground_truth_hit_count_50}/50`} />
            <StatCard
              label="Hook Coverage"
              value={hookCoverage ? `${hookCoverage.hook_pct}%` : "..."}
              sub={hookCoverage ? `${hookCoverage.hooks_generated_last_24h} generated in 24h` : undefined}
            />
          </div>

          {(failedStrict.length > 0 || failedPositive.length > 0) && (
            <div className="bg-surface-card border border-accent-danger/30 rounded-lg p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-text-primary mb-2">
                <AlertTriangle className="w-4 h-4 text-accent-danger" />
                Failed Targets
              </div>
              <div className="flex flex-wrap gap-2">
                {failedStrict.map(([name]) => (
                  <StatusPill key={name} tone="warn">{formatTargetName(name)}</StatusPill>
                ))}
                {failedPositive.map(([name]) => (
                  <StatusPill key={name} tone="warn">{formatTargetName(name)}</StatusPill>
                ))}
              </div>
            </div>
          )}

          <div className="grid md:grid-cols-4 gap-3">
            <DistributionBars title="Categories @20" data={summary.category_distribution} />
            <DistributionBars title="Archetypes @20" data={summary.archetype_distribution} />
            <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
              <h2 className="text-sm font-semibold text-text-primary">Feed Timing</h2>
              {data.debug_timing ? (
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between gap-3 text-sm">
                    <span className="text-text-muted">Total</span>
                    <span className="text-text-primary font-medium">{Math.round(data.debug_timing.total_ms)}ms</span>
                  </div>
                  {data.debug_timing.stages.map((stage) => (
                    <div key={stage.stage} className="flex justify-between gap-3">
                      <span className="text-text-secondary">{formatTargetName(stage.stage)}</span>
                      <span className="text-text-muted">{Math.round(stage.ms)}ms</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-text-muted">No timing data.</div>
              )}
            </div>
            <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
              <h2 className="text-sm font-semibold text-text-primary">Hook Worker</h2>
              {hookCoverage ? (
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between gap-3">
                    <span className="text-text-muted">Tier 1-3 hooks</span>
                    <span className="text-text-primary">{hookCoverage.tier_1_3_hook_pct}%</span>
                  </div>
                  <div className="flex justify-between gap-3">
                    <span className="text-text-muted">Image coverage</span>
                    <span className="text-text-primary">{hookCoverage.image_pct}%</span>
                  </div>
                  <div className="text-xs text-text-muted">
                    Latest hook: {hookCoverage.latest_hook_generated_at ? new Date(hookCoverage.latest_hook_generated_at).toLocaleString() : "none"}
                  </div>
                  <button
                    type="button"
                    onClick={triggerHooks}
                    disabled={triggering}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-text-primary text-surface-deep text-xs font-medium disabled:opacity-50"
                  >
                    <Play className="w-3.5 h-3.5" />
                    {triggering ? "Queueing..." : "Queue 100 hooks"}
                  </button>
                </div>
              ) : (
                <div className="text-sm text-text-muted">Loading hook coverage...</div>
              )}
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <h2 className="text-sm font-semibold text-text-primary">Behavior Signals</h2>
                <p className="text-xs text-text-muted mt-1">
                  Use these to spot ranking/design opportunities after the capture table has traffic.
                </p>
              </div>
              <select
                value={engagementDays}
                onChange={(e) => setEngagementDays(Number(e.target.value))}
                className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-xs text-text-primary"
              >
                <option value={1}>1 day</option>
                <option value={7}>7 days</option>
                <option value={14}>14 days</option>
                <option value={30}>30 days</option>
              </select>
            </div>
            {engagementData ? (
              <EngagementPanel data={engagementData} />
            ) : (
              <div className="bg-surface-card border border-surface-border rounded-lg p-4 text-sm text-text-muted">
                Loading engagement...
              </div>
            )}
          </div>

          <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
            <div className="p-4 border-b border-surface-border">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div>
                  <h2 className="text-sm font-semibold text-text-primary">Missing Ground Truth</h2>
                  <p className="text-xs text-text-muted mt-1">
                    Curated Kalshi/Polymarket examples not present in the current top 50.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={missingBucket}
                    onChange={(e) => setMissingBucket(e.target.value)}
                    className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-xs text-text-primary"
                  >
                    <option value="all">All buckets</option>
                    {missingBuckets.map((bucket) => (
                      <option key={bucket} value={bucket}>
                        {formatTargetName(bucket)} ({data.missing_ground_truth_summary.bucket_counts[bucket]})
                      </option>
                    ))}
                  </select>
                  <span className="text-xs text-text-muted">
                    {filteredMissingGroundTruth.length} shown
                  </span>
                </div>
              </div>
              {data.missing_ground_truth_summary && (
                <div className="flex flex-wrap gap-1 mt-3">
                  {Object.entries(data.missing_ground_truth_summary.bucket_counts).map(([bucket, count]) => (
                    <StatusPill key={bucket} tone={bucket === "candidate_recall_gap" ? "warn" : "muted"}>
                      {`${formatTargetName(bucket)}: ${count}`}
                    </StatusPill>
                  ))}
                </div>
              )}
            </div>
            {filteredMissingGroundTruth.length > 0 ? (
              <div className="divide-y divide-surface-border/60">
                {filteredMissingGroundTruth.slice(0, 12).map((item) => (
                  <div key={`${item.source}-${item.name}`} className="p-3 hover:bg-surface-elevated/40">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="font-medium text-sm text-text-primary">{item.name}</div>
                        {item.probability && (
                          <div className="text-xs text-text-muted mt-1">{item.probability}</div>
                        )}
                        <div className="text-xs text-text-secondary mt-2">{item.recommended_action}</div>
                      </div>
                      <div className="flex flex-wrap justify-end gap-1 shrink-0 max-w-[45%]">
                        <StatusPill tone={item.triage_bucket === "candidate_recall_gap" ? "warn" : "muted"}>
                          {formatTargetName(item.triage_bucket)}
                        </StatusPill>
                        <StatusPill tone="muted">{item.source}</StatusPill>
                        <StatusPill tone="muted">{item.category}</StatusPill>
                        <StatusPill tone={item.quality_class === "low_quality" ? "warn" : "ok"}>
                          {formatTargetName(item.quality_class)}
                        </StatusPill>
                        <StatusPill tone="muted">{formatTargetName(item.archetype)}</StatusPill>
                      </div>
                    </div>
                    {(item.story_key || item.reasons.length > 0) && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {item.story_key && <StatusPill tone="muted">{item.story_key}</StatusPill>}
                        {item.reasons.slice(0, 4).map((reason) => (
                          <StatusPill key={reason} tone="muted">{formatTargetName(reason)}</StatusPill>
                        ))}
                      </div>
                    )}
                    {item.db_trace && (
                      <div className="mt-3 rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="text-xs font-medium text-text-primary">
                            DB trace: {formatTargetName(item.db_trace.trace_status)}
                          </div>
                          <span className="text-xs text-text-muted">
                            {item.db_trace.matches.length} match{item.db_trace.matches.length === 1 ? "" : "es"}
                          </span>
                        </div>
                        <div className="text-xs text-text-secondary mt-1">
                          {item.db_trace.trace_summary}
                        </div>
                        <div className="text-xs text-text-muted mt-1">
                          {item.db_trace.recommended_action}
                        </div>
                        {item.db_trace.matches.length > 0 && (
                          <div className="space-y-2 mt-3">
                            {item.db_trace.matches.slice(0, 3).map((match) => (
                              <div key={match.id} className="text-xs">
                                <div className="flex items-center justify-between gap-3">
                                  <span className="text-text-primary truncate">{match.name}</span>
                                  <button
                                    type="button"
                                    onClick={() => toggleTrace(match.id)}
                                    className="inline-flex items-center gap-1 text-text-muted hover:text-text-primary shrink-0"
                                  >
                                    <ChevronDown className={`w-3 h-3 transition-transform ${expandedTraceId === match.id ? "rotate-180" : ""}`} />
                                    #{match.id}
                                  </button>
                                </div>
                                <div className="flex flex-wrap gap-1 mt-1">
                                  <StatusPill tone="muted">{match.source}</StatusPill>
                                  <StatusPill tone={match.status === "open" ? "ok" : "warn"}>{match.status}</StatusPill>
                                  {match.category && <StatusPill tone="muted">{match.category}</StatusPill>}
                                  {match.volume_24h !== null && (
                                    <StatusPill tone="muted">{`24h $${Math.round(match.volume_24h).toLocaleString()}`}</StatusPill>
                                  )}
                                  {match.has_hook && <StatusPill tone="ok">hook</StatusPill>}
                                  {match.has_image && <StatusPill tone="ok">image</StatusPill>}
                                  {match.blocked_reasons.map((reason) => (
                                    <StatusPill key={reason} tone="warn">{formatTargetName(reason)}</StatusPill>
                                  ))}
                                </div>
                                {expandedTraceId === match.id && (
                                  <div className="mt-2">
                                    {traceLoadingId === match.id && (
                                      <div className="text-xs text-text-muted animate-pulse">Loading trace...</div>
                                    )}
                                    {traceError && traceLoadingId !== match.id && (
                                      <div className="text-xs text-accent-danger">{traceError}</div>
                                    )}
                                    {traceByMarketId[match.id] && <TracePanel trace={traceByMarketId[match.id]} />}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 text-sm text-text-muted">No missing ground-truth examples found in the current diagnostic set.</div>
            )}
          </div>

          <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
            <div className="p-4 border-b border-surface-border space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                <Filter className="w-4 h-4" />
                Top 50 Diagnostics
              </div>
              <div className="grid md:grid-cols-4 gap-2">
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search cards"
                  className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-sm text-text-primary"
                />
                <select value={category} onChange={(e) => setCategory(e.target.value)} className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-sm text-text-primary">
                  <option value="all">All categories</option>
                  {categories.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <select value={archetype} onChange={(e) => setArchetype(e.target.value)} className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-sm text-text-primary">
                  <option value="all">All archetypes</option>
                  {archetypes.map((item) => <option key={item} value={item}>{formatTargetName(item)}</option>)}
                </select>
                <select value={quality} onChange={(e) => setQuality(e.target.value)} className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-sm text-text-primary">
                  <option value="all">All quality</option>
                  {qualities.map((item) => <option key={item} value={item}>{formatTargetName(item)}</option>)}
                </select>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-surface-elevated text-text-muted text-xs">
                  <tr>
                    <th className="text-left font-medium p-3">Rank</th>
                    <th className="text-left font-medium p-3">Market</th>
                    <th className="text-left font-medium p-3">Why</th>
                    <th className="text-left font-medium p-3">Signals</th>
                    <th className="text-left font-medium p-3">Family</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((item) => (
                    <Fragment key={`${item.type}-${item.id}-${item.rank}`}>
                      <tr key={`${item.type}-${item.id}-${item.rank}`} className="border-t border-surface-border/60 hover:bg-surface-elevated/40">
                        <td className="p-3 align-top text-text-muted">#{item.rank}<br /><span className="text-text-primary font-semibold">{item.score}</span></td>
                        <td className="p-3 align-top min-w-[280px]">
                          <div className="font-medium text-text-primary">{item.name}</div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            <StatusPill tone="muted">{item.category}</StatusPill>
                            <StatusPill tone="muted">{formatTargetName(item.archetype)}</StatusPill>
                            {item.ground_truth && <StatusPill tone="ok">ground truth</StatusPill>}
                          </div>
                          {item.type === "futures" && item.id !== null && (
                            <button
                              type="button"
                              onClick={() => toggleTrace(item.id!)}
                              className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-accent-futures hover:underline"
                            >
                              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${expandedTraceId === item.id ? "rotate-180" : ""}`} />
                              Trace pipeline
                            </button>
                          )}
                        </td>
                        <td className="p-3 align-top min-w-[260px]">
                          <div className="text-text-primary">{item.headline || item.reason || "No explanation"}</div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            <StatusPill tone={item.explanation_ok ? "ok" : "warn"}>{item.explanation_ok ? "explained" : "weak explanation"}</StatusPill>
                            {item.hook && <StatusPill tone="ok">hook</StatusPill>}
                            {item.image && <StatusPill tone="ok">image</StatusPill>}
                          </div>
                        </td>
                        <td className="p-3 align-top min-w-[180px]">
                          <div className="flex flex-wrap gap-1">
                            <StatusPill tone={item.quality_class === "low_quality" || item.quality_class === "suppress" ? "warn" : "ok"}>
                              {formatTargetName(item.quality_class)}
                            </StatusPill>
                            {item.ladder && <StatusPill tone="warn">ladder</StatusPill>}
                            {item.personalization_trace && (
                              <StatusPill tone={item.personalization_trace.is_personalized ? "ok" : "muted"}>
                                {`personalized ${item.personalization_trace.multiplier.toFixed(2)}x`}
                              </StatusPill>
                            )}
                            {item.personalization_trace && item.personalization_trace.score_delta !== 0 && (
                              <StatusPill tone={item.personalization_trace.score_delta > 0 ? "ok" : "warn"}>
                                {`score ${signedNumber(item.personalization_trace.score_delta)}`}
                              </StatusPill>
                            )}
                            {item.personalization_trace && item.personalization_trace.category_affinity_delta !== 0 && (
                              <StatusPill tone={item.personalization_trace.category_affinity_delta > 0 ? "ok" : "warn"}>
                                {`category ${signedNumber(item.personalization_trace.category_affinity_delta, 2)}`}
                              </StatusPill>
                            )}
                            {item.reasons.map((reason) => (
                              <StatusPill key={reason} tone="muted">{formatTargetName(reason)}</StatusPill>
                            ))}
                            {item.personalization_trace?.reasons.slice(0, 3).map((reason) => (
                              <StatusPill key={`personalization-${reason}`} tone="muted">{formatTargetName(reason)}</StatusPill>
                            ))}
                          </div>
                        </td>
                        <td className="p-3 align-top min-w-[220px]">
                          <code className="block text-xs text-text-muted break-all">{item.story_key || item.family_key}</code>
                        </td>
                      </tr>
                      {item.type === "futures" && item.id !== null && expandedTraceId === item.id && (
                        <tr key={`${item.type}-${item.id}-${item.rank}-trace`} className="border-t border-surface-border/60">
                          <td colSpan={5} className="p-3">
                            {traceLoadingId === item.id && (
                              <div className="text-xs text-text-muted animate-pulse">Loading trace...</div>
                            )}
                            {traceError && traceLoadingId !== item.id && (
                              <div className="text-xs text-accent-danger">{traceError}</div>
                            )}
                            {traceByMarketId[item.id] && <TracePanel trace={traceByMarketId[item.id]} />}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
              {filteredItems.length === 0 && (
                <div className="p-8 text-center text-sm text-text-muted">No cards match the current filters.</div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
