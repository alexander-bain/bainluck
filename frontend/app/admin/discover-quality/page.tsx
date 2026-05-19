"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import {
  AlertTriangle,
  BarChart3,
  ChevronDown,
  CheckCircle2,
  ExternalLink,
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
import { getIdToken } from "@/lib/firebase";

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
  url?: string | null;
  published_at?: string | null;
  platform?: string | null;
  handle?: string | null;
  engagement?: string | null;
  email_subject?: string | null;
  hook?: string | null;
  interestingness?: string | null;
  timeliness?: string | null;
  shareability?: string | null;
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

interface EmailGroundTruthDiagnostics {
  configured: boolean;
  source: string | null;
  source_paths?: string[];
  raw_row_count: number;
  loaded_count: number;
  latest_date?: string | null;
  stale?: boolean | null;
  stale_after_days?: number;
  min_interestingness?: number;
  lookback_days?: number | null;
  source_counts?: Record<string, number>;
  source_health?: Array<{
    source: string;
    count: number;
    latest_date: string | null;
    stale: boolean | null;
    platform_counts: Record<string, number>;
  }>;
  total: number;
  top20_hits: number;
  top50_hits: number;
  missing: number;
  hit_rate_50: number;
  error?: string | null;
}

interface DiscoverDiagnosticRun {
  run_id: string;
  captured_at: string | null;
  total: number;
  by_source_group: Record<string, { total: number; hit: number; miss: number }>;
  by_triage_bucket: Record<string, number>;
}

interface DiscoverDiagnosticRunsResponse {
  runs: DiscoverDiagnosticRun[];
}

interface DiscoverDiagnosticTrendRun extends DiscoverDiagnosticRun {
  top_triage_bucket: { bucket: string; count: number } | null;
  combined_misses: number;
  email_hits: number;
  email_misses: number;
  external_curator_hits: number;
  external_curator_misses: number;
  deltas: Partial<Record<
    | "combined_misses"
    | "email_hits"
    | "email_misses"
    | "external_curator_hits"
    | "external_curator_misses",
    number
  >>;
}

interface DiscoverDiagnosticTrendsResponse {
  runs: DiscoverDiagnosticTrendRun[];
}

interface DiscoverDiagnosticRow {
  id: number;
  captured_at: string | null;
  source_group: string;
  source: string | null;
  status: string;
  item_name: string;
  feed_name: string | null;
  category: string | null;
  probability: string | null;
  source_url: string | null;
  published_at: string | null;
  rank: number | null;
  score: number | null;
  quality_class: string | null;
  archetype: string | null;
  family_key: string | null;
  story_key: string | null;
  triage_bucket: string | null;
  recommended_action: string | null;
  matched_market_id: number | null;
  trace_status: string | null;
  trace_summary: string | null;
  db_match_count: number | null;
}

interface DiscoverDiagnosticRowsResponse {
  run_id: string;
  total: number;
  limit: number;
  offset: number;
  rows: DiscoverDiagnosticRow[];
}

interface FeedDebugResponse {
  debug_summary: DebugSummary;
  debug_items: DebugItem[];
  missing_ground_truth: MissingGroundTruthItem[];
  missing_ground_truth_summary: MissingGroundTruthSummary;
  email_ground_truth?: EmailGroundTruthDiagnostics;
  email_ground_truth_misses?: MissingGroundTruthItem[];
  external_curator_ground_truth?: EmailGroundTruthDiagnostics;
  external_curator_ground_truth_misses?: MissingGroundTruthItem[];
  debug_timing?: {
    total_ms: number;
    stages: Array<{
      stage: string;
      ms: number;
      elapsed_ms: number;
    }>;
  };
}

type PersonalizationFilter = "all" | "personalized" | "boosted" | "suppressed" | "neutral" | "missing";
type Top50QuickFilter = "all" | "weak_explanation" | "low_quality" | "ladder" | "ground_truth" | "missing_trace";

interface PersonalizationRollup {
  total: number;
  traced: number;
  personalized: number;
  boosted: number;
  suppressed: number;
  neutral: number;
  missing: number;
  avgMultiplier: number | null;
  avgScoreDelta: number | null;
  categories: Array<{
    category: string;
    count: number;
    avgMultiplier: number;
    avgScoreDelta: number;
    boosted: number;
    suppressed: number;
  }>;
  reasons: Array<{
    reason: string;
    count: number;
  }>;
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

interface DiscoverEngagementReviewItem {
  kind: "promote" | "investigate" | "downrank";
  priority: number;
  item_type: string;
  item_id: string;
  item_name: string | null;
  category: string | null;
  surface: string;
  auth_segment: "signed_in" | "anonymous" | string;
  family_key: string;
  archetype: string;
  impressions: number;
  opens: number;
  dismisses: number;
  shares: number;
  context_expands: number;
  avg_rank: number | null;
  avg_score: number | null;
  open_rate: number;
  dismiss_rate: number;
  share_rate: number;
  context_expand_rate: number;
  recommendation: string;
}

interface DiscoverScoreBucket {
  bucket: string;
  impressions: number;
  opens: number;
  dismisses: number;
  shares: number;
  context_expands: number;
  actions: number;
  open_rate: number;
  dismiss_rate: number;
  share_rate: number;
  context_expand_rate: number;
  engagement_score: number;
}

interface DiscoverRuntimeConfig {
  interaction_suppression_enabled: boolean;
  seen_suppression_hours: number;
  dismiss_suppression_days: number;
  stale_no_movement_days: number;
  no_resolution_stale_days: number;
}

interface DiscoverLaunchHealthItem {
  item_type: string;
  item_id: string;
  item_name: string | null;
  category: string | null;
  surface: string | null;
  impressions: number;
  extra_impressions?: number;
  reason?: string;
}

interface DiscoverReviewDecision {
  id: number;
  item_type: string;
  item_id: string;
  item_name: string | null;
  category: string | null;
  surface: string | null;
  auth_segment: string | null;
  family_key: string | null;
  archetype: string | null;
  decision: string;
  admin_notes: string | null;
  created_at: string | null;
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
  score_buckets: DiscoverScoreBucket[];
  opportunities: DiscoverEngagementOpportunity[];
  review_queue: DiscoverEngagementReviewItem[];
  runtime_config: DiscoverRuntimeConfig;
  launch_health: {
    repeat_extra_impressions: number;
    repeat_rate: number;
    repeat_sessions: number;
    stale_impressions: number;
    stale_rate: number;
    top_repeat_items: DiscoverLaunchHealthItem[];
    top_stale_items: DiscoverLaunchHealthItem[];
  };
  recent_review_decisions: DiscoverReviewDecision[];
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
  const token = await getIdToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
  const res = await fetch(`${API_URL}/api/feed?${params}`, { headers });
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

async function fetchDiscoverDiagnosticRuns(secret: string): Promise<DiscoverDiagnosticRunsResponse> {
  const res = await fetch(
    `${API_URL}/api/admin/discover-ground-truth-diagnostics/runs?secret=${encodeURIComponent(secret)}&limit=8`
  );
  if (!res.ok) throw new Error(`Diagnostic runs API error: ${res.status}`);
  return res.json();
}

async function fetchDiscoverDiagnosticTrends(secret: string): Promise<DiscoverDiagnosticTrendsResponse> {
  const res = await fetch(
    `${API_URL}/api/admin/discover-ground-truth-diagnostics/trends?secret=${encodeURIComponent(secret)}&limit=8`
  );
  if (!res.ok) throw new Error(`Diagnostic trends API error: ${res.status}`);
  return res.json();
}

async function fetchDiscoverDiagnosticRows(
  secret: string,
  runId: string,
  filters: { sourceGroup: string; status: string; triageBucket: string; offset: number }
): Promise<DiscoverDiagnosticRowsResponse> {
  const params = new URLSearchParams({
    secret,
    limit: "100",
    offset: String(filters.offset),
  });
  if (filters.sourceGroup !== "all") params.set("source_group", filters.sourceGroup);
  if (filters.status !== "all") params.set("status", filters.status);
  if (filters.triageBucket !== "all") params.set("triage_bucket", filters.triageBucket);
  const res = await fetch(
    `${API_URL}/api/admin/discover-ground-truth-diagnostics/runs/${encodeURIComponent(runId)}/rows?${params}`
  );
  if (!res.ok) throw new Error(`Diagnostic rows API error: ${res.status}`);
  return res.json();
}

async function triggerDiscoverDiagnosticSnapshot(secret: string): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/admin/discover-ground-truth-diagnostics/snapshot?secret=${encodeURIComponent(secret)}&limit=50`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`Diagnostic snapshot trigger failed: ${res.status}`);
}

async function updateDiscoverRuntimeConfig(
  secret: string,
  config: Partial<DiscoverRuntimeConfig>
): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/admin/discover-config?secret=${encodeURIComponent(secret)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }
  );
  if (!res.ok) throw new Error(`Runtime config update failed: ${res.status}`);
}

async function submitDiscoverReviewDecision(
  secret: string,
  item: DiscoverEngagementReviewItem,
  decision: string
): Promise<void> {
  const res = await fetch(
    `${API_URL}/api/admin/discover-review-decisions?secret=${encodeURIComponent(secret)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        item_type: item.item_type,
        item_id: item.item_id,
        item_name: item.item_name,
        category: item.category,
        surface: item.surface,
        auth_segment: item.auth_segment,
        family_key: item.family_key,
        archetype: item.archetype,
        decision,
      }),
    }
  );
  if (!res.ok) throw new Error(`Review decision failed: ${res.status}`);
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

function itemHref(itemType: string, itemId: string | number | null | undefined) {
  if (itemId === null || itemId === undefined || itemId === "") return null;
  if (itemType === "futures") return `/futures/${itemId}`;
  if (itemType === "event") return `/events/${itemId}`;
  return null;
}

function DeltaPill({
  value,
  lowerIsBetter,
}: {
  value: number | undefined;
  lowerIsBetter: boolean;
}) {
  if (value === undefined) return null;
  const tone =
    value === 0
      ? "muted"
      : lowerIsBetter
        ? value < 0 ? "ok" : "warn"
        : value > 0 ? "ok" : "warn";
  return <StatusPill tone={tone}>{signedNumber(value, 0)}</StatusPill>;
}

function PersonalizationPanel({ rollup }: { rollup: PersonalizationRollup }) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Personalization</h2>
          <p className="text-xs text-text-muted mt-1">
            Authenticated debug traces across the current top 50.
          </p>
        </div>
        <StatusPill tone={rollup.traced > 0 ? "ok" : "muted"}>
          {rollup.traced > 0 ? `${rollup.traced} traced` : "anonymous"}
        </StatusPill>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
        <div>
          <div className="text-text-muted">Personalized</div>
          <div className="text-text-primary font-semibold">{rollup.personalized}/{rollup.total}</div>
        </div>
        <div>
          <div className="text-text-muted">Boosted</div>
          <div className="text-accent-live font-semibold">{rollup.boosted}</div>
        </div>
        <div>
          <div className="text-text-muted">Suppressed</div>
          <div className="text-accent-danger font-semibold">{rollup.suppressed}</div>
        </div>
        <div>
          <div className="text-text-muted">Avg multiplier</div>
          <div className="text-text-primary font-semibold">
            {rollup.avgMultiplier === null ? "none" : `${rollup.avgMultiplier.toFixed(2)}x`}
          </div>
        </div>
        <div>
          <div className="text-text-muted">Avg score delta</div>
          <div className="text-text-primary font-semibold">
            {rollup.avgScoreDelta === null ? "none" : signedNumber(rollup.avgScoreDelta, 1)}
          </div>
        </div>
      </div>

      {rollup.categories.length > 0 ? (
        <div className="space-y-2">
          <div className="text-xs font-medium text-text-primary">Category Effects</div>
          <div className="grid md:grid-cols-2 gap-2">
            {rollup.categories.slice(0, 6).map((row) => (
              <div key={row.category} className="rounded-lg bg-surface-elevated/50 border border-surface-border p-2">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-medium text-text-primary">{formatTargetName(row.category)}</span>
                  <span className="text-text-muted">{row.count} cards</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  <StatusPill tone={row.avgScoreDelta >= 0 ? "ok" : "warn"}>
                    {`score ${signedNumber(row.avgScoreDelta, 1)}`}
                  </StatusPill>
                  <StatusPill tone="muted">{`${row.avgMultiplier.toFixed(2)}x`}</StatusPill>
                  {row.boosted > 0 && <StatusPill tone="ok">{`${row.boosted} boosted`}</StatusPill>}
                  {row.suppressed > 0 && <StatusPill tone="warn">{`${row.suppressed} suppressed`}</StatusPill>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-xs text-text-muted">
          Sign in before loading this admin page to inspect personalized ranking effects.
        </div>
      )}

      {rollup.reasons.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {rollup.reasons.slice(0, 8).map((row) => (
            <StatusPill key={row.reason} tone="muted">
              {`${formatTargetName(row.reason)}: ${row.count}`}
            </StatusPill>
          ))}
        </div>
      )}
    </div>
  );
}

function ReviewPathNav({
  groundTruthHits,
  missingCount,
  persistedRuns,
  hardGateIssues,
  topMissBucket,
  repeatRate,
  staleRate,
}: {
  groundTruthHits: number;
  missingCount: number;
  persistedRuns: number;
  hardGateIssues: number;
  topMissBucket: string | null;
  repeatRate: number | null;
  staleRate: number | null;
}) {
  const links = [
    {
      href: "#health",
      label: "Health",
      sub: hardGateIssues === 0 ? `clean / ${groundTruthHits} GT` : `${hardGateIssues} issues`,
    },
    { href: "#diagnostics", label: "Diagnostics", sub: `${persistedRuns} runs` },
    {
      href: "#misses",
      label: "Misses",
      sub: topMissBucket ? formatTargetName(topMissBucket) : `${missingCount} open`,
    },
    {
      href: "#behavior",
      label: "Behavior",
      sub: repeatRate === null || staleRate === null
        ? "loading"
        : `${rateText(repeatRate)} repeat / ${rateText(staleRate)} stale`,
    },
    { href: "#top50", label: "Top 50", sub: "live cards" },
  ];

  return (
    <div className="sticky top-0 z-20 -mx-4 border-y border-surface-border bg-bg-surface/95 px-4 py-2 backdrop-blur">
      <div className="flex items-center gap-2 overflow-x-auto">
        <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
          Review Path
        </span>
        {links.map((link, index) => (
          <a
            key={link.href}
            href={link.href}
            className="shrink-0 rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-xs hover:bg-surface-elevated"
          >
            <span className="font-medium text-text-primary">{index + 1}. {link.label}</span>
            <span className="ml-2 text-text-muted">{link.sub}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

function DiagnosticTrendsPanel({ runs }: { runs: DiscoverDiagnosticTrendRun[] }) {
  const latest = runs[0];

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Diagnostic Trend</h2>
          <p className="text-xs text-text-muted mt-1">
            Recent persisted snapshots, grouped by source and triage bucket.
          </p>
        </div>
        {latest && (
          <StatusPill tone={latest.combined_misses === 0 ? "ok" : "warn"}>
            {`${latest.combined_misses} latest misses`}
          </StatusPill>
        )}
      </div>

      {latest ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <div className="text-xs text-text-muted">Latest run</div>
              <div className="text-sm font-semibold text-text-primary">
                {latest.captured_at ? new Date(latest.captured_at).toLocaleString() : latest.run_id}
              </div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Email hits</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm font-semibold text-text-primary">
                  {latest.email_hits}/{latest.email_hits + latest.email_misses}
                </span>
                <DeltaPill value={latest.deltas.email_hits} lowerIsBetter={false} />
              </div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Curator hits</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm font-semibold text-text-primary">
                  {latest.external_curator_hits}/{latest.external_curator_hits + latest.external_curator_misses}
                </span>
                <DeltaPill value={latest.deltas.external_curator_hits} lowerIsBetter={false} />
              </div>
            </div>
            <div>
              <div className="text-xs text-text-muted">Top miss bucket</div>
              <div className="text-sm font-semibold text-text-primary">
                {latest.top_triage_bucket
                  ? `${formatTargetName(latest.top_triage_bucket.bucket)} (${latest.top_triage_bucket.count})`
                  : "none"}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-surface-border">
            <table className="w-full text-sm">
              <thead className="bg-surface-elevated text-text-muted text-xs">
                <tr>
                  <th className="text-left font-medium p-3">Run</th>
                  <th className="text-left font-medium p-3">Misses</th>
                  <th className="text-left font-medium p-3">Email</th>
                  <th className="text-left font-medium p-3">Curator</th>
                  <th className="text-left font-medium p-3">Top Bucket</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/60">
                {runs.map((run) => (
                  <tr key={run.run_id} className="hover:bg-surface-elevated/40">
                    <td className="p-3 min-w-[180px]">
                      <div className="font-medium text-text-primary">
                        {run.captured_at ? new Date(run.captured_at).toLocaleString() : run.run_id}
                      </div>
                      <div className="text-xs text-text-muted">{run.total} rows</div>
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className="text-text-primary">{run.combined_misses}</span>
                        <DeltaPill value={run.deltas.combined_misses} lowerIsBetter />
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="text-text-primary">
                        {run.email_hits} hit / {run.email_misses} miss
                      </div>
                      <div className="mt-1 flex gap-1">
                        <DeltaPill value={run.deltas.email_hits} lowerIsBetter={false} />
                        <DeltaPill value={run.deltas.email_misses} lowerIsBetter />
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="text-text-primary">
                        {run.external_curator_hits} hit / {run.external_curator_misses} miss
                      </div>
                      <div className="mt-1 flex gap-1">
                        <DeltaPill value={run.deltas.external_curator_hits} lowerIsBetter={false} />
                        <DeltaPill value={run.deltas.external_curator_misses} lowerIsBetter />
                      </div>
                    </td>
                    <td className="p-3 min-w-[190px]">
                      {run.top_triage_bucket ? (
                        <div>
                          <div className="text-text-primary">
                            {formatTargetName(run.top_triage_bucket.bucket)}
                          </div>
                          <div className="text-xs text-text-muted">
                            {run.top_triage_bucket.count} row{run.top_triage_bucket.count === 1 ? "" : "s"}
                          </div>
                        </div>
                      ) : (
                        <span className="text-text-muted">none</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="text-sm text-text-muted">No trend data yet.</div>
      )}
    </div>
  );
}

function DiagnosticRunsPanel({
  runs,
  rows,
  rowsLoading,
  selectedRunId,
  setSelectedRunId,
  sourceGroup,
  setSourceGroup,
  status,
  setStatus,
  triageBucket,
  setTriageBucket,
  offset,
  setOffset,
  onTrigger,
  triggering,
  onToggleTrace,
  expandedTraceId,
  traceByMarketId,
  traceLoadingId,
  traceError,
}: {
  runs: DiscoverDiagnosticRun[];
  rows?: DiscoverDiagnosticRowsResponse;
  rowsLoading: boolean;
  selectedRunId: string;
  setSelectedRunId: (value: string) => void;
  sourceGroup: string;
  setSourceGroup: (value: string) => void;
  status: string;
  setStatus: (value: string) => void;
  triageBucket: string;
  setTriageBucket: (value: string) => void;
  offset: number;
  setOffset: (value: number) => void;
  onTrigger: () => void;
  triggering: boolean;
  onToggleTrace: (marketId: number) => void;
  expandedTraceId: number | null;
  traceByMarketId: Record<number, DiscoverMarketTrace>;
  traceLoadingId: number | null;
  traceError: string | null;
}) {
  const selectedRun = runs.find((run) => run.run_id === selectedRunId);
  const sourceGroups = selectedRun
    ? Object.keys(selectedRun.by_source_group).sort()
    : [];
  const buckets = selectedRun
    ? Object.keys(selectedRun.by_triage_bucket).sort()
    : [];

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg overflow-hidden">
      <div className="p-4 border-b border-surface-border space-y-3">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">
              Persisted Ground Truth Diagnostics
            </h2>
            <p className="text-xs text-text-muted mt-1">
              Snapshot history for email, curator, and combined ground-truth misses.
            </p>
          </div>
          <button
            type="button"
            onClick={onTrigger}
            disabled={triggering}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-text-primary text-surface-deep text-xs font-medium disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            {triggering ? "Queueing..." : "Queue snapshot"}
          </button>
        </div>

        {runs.length > 0 ? (
          <>
            <div className="grid md:grid-cols-4 gap-2">
              <select
                value={selectedRunId}
                onChange={(event) => setSelectedRunId(event.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-xs text-text-primary md:col-span-2"
              >
                {runs.map((run) => (
                  <option key={run.run_id} value={run.run_id}>
                    {run.captured_at ? new Date(run.captured_at).toLocaleString() : run.run_id}
                  </option>
                ))}
              </select>
              <select
                value={sourceGroup}
                onChange={(event) => setSourceGroup(event.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-xs text-text-primary"
              >
                <option value="all">All sources</option>
                {sourceGroups.map((group) => (
                  <option key={group} value={group}>{formatTargetName(group)}</option>
                ))}
              </select>
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-xs text-text-primary"
              >
                <option value="all">All status</option>
                <option value="miss">Misses</option>
                <option value="hit">Hits</option>
              </select>
            </div>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <select
                value={triageBucket}
                onChange={(event) => setTriageBucket(event.target.value)}
                className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-xs text-text-primary"
              >
                <option value="all">All buckets</option>
                {buckets.map((bucket) => (
                  <option key={bucket} value={bucket}>
                    {formatTargetName(bucket)} ({selectedRun?.by_triage_bucket[bucket]})
                  </option>
                ))}
              </select>
              {selectedRun && (
                <div className="flex flex-wrap gap-1">
                  <StatusPill tone="muted">{`${selectedRun.total} rows`}</StatusPill>
                  {Object.entries(selectedRun.by_source_group).map(([group, counts]) => (
                    <StatusPill key={group} tone="muted">
                      {`${formatTargetName(group)} ${counts.hit}/${counts.total}`}
                    </StatusPill>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="text-sm text-text-muted">No persisted runs yet.</div>
        )}
      </div>

      {rowsLoading ? (
        <div className="p-4 text-sm text-text-muted animate-pulse">Loading diagnostic rows...</div>
      ) : rows && rows.rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-surface-elevated text-text-muted text-xs">
              <tr>
                <th className="text-left font-medium p-3">Item</th>
                <th className="text-left font-medium p-3">Status</th>
                <th className="text-left font-medium p-3">Trace</th>
                <th className="text-left font-medium p-3">Match</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border/60">
              {rows.rows.map((row) => (
                <Fragment key={row.id}>
                  <tr className="hover:bg-surface-elevated/40 align-top">
                    <td className="p-3 min-w-[320px]">
                      <div className="font-medium text-text-primary">{row.item_name}</div>
                      {row.feed_name && (
                        <div className="text-xs text-text-secondary mt-1">{row.feed_name}</div>
                      )}
                      <div className="flex flex-wrap gap-1 mt-2">
                        <StatusPill tone="muted">{formatTargetName(row.source_group)}</StatusPill>
                        {row.source && <StatusPill tone="muted">{row.source}</StatusPill>}
                        {row.category && <StatusPill tone="muted">{row.category}</StatusPill>}
                        {row.probability && <StatusPill tone="muted">{row.probability}</StatusPill>}
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="flex flex-wrap gap-1">
                        <StatusPill tone={row.status === "hit" ? "ok" : "warn"}>
                          {row.status}
                        </StatusPill>
                        {row.triage_bucket && (
                          <StatusPill tone={row.triage_bucket === "candidate_recall_gap" ? "warn" : "muted"}>
                            {formatTargetName(row.triage_bucket)}
                          </StatusPill>
                        )}
                        {row.rank !== null && <StatusPill tone="ok">{`rank ${row.rank}`}</StatusPill>}
                      </div>
                    </td>
                    <td className="p-3 min-w-[260px]">
                      <div className="text-xs text-text-primary">
                        {row.trace_status ? formatTargetName(row.trace_status) : "No trace"}
                      </div>
                      {row.trace_summary && (
                        <div className="text-xs text-text-secondary mt-1 line-clamp-3">
                          {row.trace_summary}
                        </div>
                      )}
                      {row.recommended_action && (
                        <div className="text-xs text-text-muted mt-1 line-clamp-2">
                          {row.recommended_action}
                        </div>
                      )}
                    </td>
                    <td className="p-3">
                      {row.matched_market_id ? (
                        <div className="flex flex-col items-start gap-2">
                          <a
                            href={`/futures/${row.matched_market_id}`}
                            className="inline-flex items-center gap-1 text-xs text-accent-futures hover:underline"
                          >
                            #{row.matched_market_id}
                            <ExternalLink className="w-3 h-3" />
                          </a>
                          <button
                            type="button"
                            onClick={() => onToggleTrace(row.matched_market_id!)}
                            className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-primary"
                          >
                            <ChevronDown className={`w-3 h-3 transition-transform ${expandedTraceId === row.matched_market_id ? "rotate-180" : ""}`} />
                            Trace
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-text-muted">none</span>
                      )}
                      {row.db_match_count !== null && (
                        <div className="text-xs text-text-muted mt-1">
                          {row.db_match_count} DB match{row.db_match_count === 1 ? "" : "es"}
                        </div>
                      )}
                    </td>
                  </tr>
                  {row.matched_market_id && expandedTraceId === row.matched_market_id && (
                    <tr className="bg-surface-elevated/30">
                      <td colSpan={4} className="p-3">
                        {traceLoadingId === row.matched_market_id && (
                          <div className="text-xs text-text-muted animate-pulse">Loading trace...</div>
                        )}
                        {traceError && traceLoadingId !== row.matched_market_id && (
                          <div className="text-xs text-accent-danger">{traceError}</div>
                        )}
                        {traceByMarketId[row.matched_market_id] ? (
                          <TracePanel trace={traceByMarketId[row.matched_market_id]} />
                        ) : !traceError && traceLoadingId !== row.matched_market_id ? (
                          <div className="text-xs text-text-muted">Open trace to load pipeline details.</div>
                        ) : null}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          <div className="p-3 text-xs text-text-muted border-t border-surface-border">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <span>
                Showing {offset + 1}-{Math.min(offset + rows.rows.length, rows.total)} of {rows.total}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setOffset(Math.max(0, offset - rows.limit))}
                  disabled={offset === 0}
                  className="rounded-lg border border-surface-border px-3 py-1 disabled:opacity-40 hover:bg-surface-elevated"
                >
                  Prev
                </button>
                <button
                  type="button"
                  onClick={() => setOffset(offset + rows.limit)}
                  disabled={offset + rows.rows.length >= rows.total}
                  className="rounded-lg border border-surface-border px-3 py-1 disabled:opacity-40 hover:bg-surface-elevated"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-4 text-sm text-text-muted">No rows match these filters.</div>
      )}
    </div>
  );
}

function TracePanel({ trace }: { trace: DiscoverMarketTrace }) {
  const phases = trace.rank_phases;
  const scores = trace.score_trace.scores;
  const scoreSteps = [
    { label: "Highlight", value: scores.highlight, delta: null, sub: null },
    {
      label: "Quality",
      value: scores.after_quality,
      delta: scores.after_quality - scores.highlight,
      sub: null,
    },
    {
      label: "Explanation",
      value: scores.after_explanation,
      delta: scores.after_explanation - scores.after_quality,
      sub: null,
    },
    {
      label: "Final",
      value: scores.final,
      delta: scores.final - scores.after_explanation,
      sub: `${scores.personalization_multiplier.toFixed(2)}x`,
    },
  ];
  const blockers = [
    ...trace.base_eligibility.blockers,
    ...trace.score_trace.blockers,
  ];

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

      <div className="grid md:grid-cols-5 gap-2 text-xs">
        <div className="md:col-span-2">
          <div className="text-text-muted">Score path</div>
          <div className="mt-1 grid grid-cols-2 md:grid-cols-4 gap-1">
            {scoreSteps.map((step) => (
              <div key={step.label} className="rounded-md border border-surface-border bg-surface-card px-2 py-1">
                <div className="text-[10px] uppercase text-text-muted">{step.label}</div>
                <div className="font-semibold text-text-primary">{Math.round(step.value)}</div>
                <div className="text-[11px] text-text-muted">
                  {step.delta === null ? "base" : signedNumber(step.delta, 1)}
                  {step.sub ? ` / ${step.sub}` : ""}
                </div>
              </div>
            ))}
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
            {blockers.length === 0 && <StatusPill tone="ok">No blockers</StatusPill>}
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

function RuntimeActionButton({
  title,
  description,
  busy,
  onClick,
}: {
  title: string;
  description: string;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      className="text-left rounded-lg border border-surface-border bg-surface-card p-3 hover:border-accent-brand/40 disabled:opacity-60"
    >
      <div className="text-xs font-semibold text-text-primary">
        {busy ? "Applying..." : title}
      </div>
      <div className="mt-1 text-[11px] leading-4 text-text-muted">{description}</div>
    </button>
  );
}

function EngagementPanel({
  data,
  secret,
  engagementDays,
}: {
  data: DiscoverEngagementResponse;
  secret: string;
  engagementDays: number;
}) {
  const [savingConfig, setSavingConfig] = useState<string | null>(null);
  const [reviewingKey, setReviewingKey] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const applyRuntimeConfig = async (
    label: string,
    config: Partial<DiscoverRuntimeConfig>
  ) => {
    setSavingConfig(label);
    setActionMessage(null);
    try {
      await updateDiscoverRuntimeConfig(secret, config);
      await mutate(["discover-engagement", secret, engagementDays]);
      setActionMessage(`${label} applied`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Runtime config update failed");
    } finally {
      setSavingConfig(null);
    }
  };

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

  const reviewKey = (item: DiscoverEngagementReviewItem, decision: string) =>
    `${item.surface}:${item.auth_segment}:${item.item_type}:${item.item_id}:${decision}`;

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

      <div className="grid md:grid-cols-3 gap-3 rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
        <div>
          <div className="text-xs text-text-muted">Repeat rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.launch_health?.repeat_rate ?? 0)}</div>
          <div className="text-[11px] text-text-muted">
            {(data.launch_health?.repeat_extra_impressions ?? 0).toLocaleString()} extra impressions across {(data.launch_health?.repeat_sessions ?? 0).toLocaleString()} sessions
          </div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Stale impression rate</div>
          <div className="text-lg font-semibold text-text-primary">{rateText(data.launch_health?.stale_rate ?? 0)}</div>
          <div className="text-[11px] text-text-muted">
            {(data.launch_health?.stale_impressions ?? 0).toLocaleString()} impressions on currently stale cards
          </div>
        </div>
        <div>
          <div className="text-xs text-text-muted">Runtime controls</div>
          <div className="text-sm font-semibold text-text-primary">
            {data.runtime_config?.interaction_suppression_enabled ? "Suppression on" : "Suppression off"}
          </div>
          <div className="text-[11px] text-text-muted">
            Seen {data.runtime_config?.seen_suppression_hours ?? "-"}h, dismiss {data.runtime_config?.dismiss_suppression_days ?? "-"}d, stale {data.runtime_config?.stale_no_movement_days ?? "-"}d
          </div>
        </div>
      </div>

      {data.score_buckets?.length > 0 && (
        <ScoreBucketList rows={data.score_buckets} />
      )}

      <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-xs font-medium text-text-primary">Action Console</div>
            <div className="text-[11px] text-text-muted mt-1">
              Use these for launch guardrails. Use the Human Review Queue below for card-level promote/downrank decisions.
            </div>
          </div>
          {actionMessage && (
            <StatusPill tone={actionMessage.includes("failed") ? "warn" : "ok"}>
              {actionMessage}
            </StatusPill>
          )}
        </div>
        <div className="grid md:grid-cols-3 gap-2">
          <RuntimeActionButton
            title="Suppress Repeats"
            description="Hide seen cards for 72h and dismissed cards for 21d."
            busy={savingConfig === "Suppress repeats"}
            onClick={() =>
              applyRuntimeConfig("Suppress repeats", {
                interaction_suppression_enabled: true,
                seen_suppression_hours: 72,
                dismiss_suppression_days: 21,
              })
            }
          />
          <RuntimeActionButton
            title="Tighten Stale Filter"
            description="Reduce no-movement and no-resolution stale windows."
            busy={savingConfig === "Tighten stale filter"}
            onClick={() =>
              applyRuntimeConfig("Tighten stale filter", {
                stale_no_movement_days: 1,
                no_resolution_stale_days: 3,
              })
            }
          />
          <RuntimeActionButton
            title="Restore Defaults"
            description="Return launch guardrails to the checked-in defaults."
            busy={savingConfig === "Restore defaults"}
            onClick={() =>
              applyRuntimeConfig("Restore defaults", {
                interaction_suppression_enabled: true,
                seen_suppression_hours: 48,
                dismiss_suppression_days: 14,
                stale_no_movement_days: 2,
                no_resolution_stale_days: 5,
              })
            }
          />
        </div>
      </div>

      {((data.launch_health?.top_repeat_items?.length ?? 0) > 0 || (data.launch_health?.top_stale_items?.length ?? 0) > 0) && (
        <div className="grid md:grid-cols-2 gap-3">
          <LaunchHealthList title="Repeated Cards" rows={data.launch_health?.top_repeat_items || []} metric="extra_impressions" />
          <LaunchHealthList title="Currently Stale Cards" rows={data.launch_health?.top_stale_items || []} metric="impressions" />
        </div>
      )}

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

      {data.review_queue?.length > 0 && (
        <div>
          <div className="flex items-center justify-between gap-3 mb-2">
            <div>
              <div className="text-xs font-medium text-text-primary">Human Review Queue</div>
              <div className="text-[11px] text-text-muted">
                Card-level candidates segmented by surface and auth state. Promote/downrank decisions apply a bounded feed score nudge.
              </div>
            </div>
            <StatusPill tone="muted">{data.review_queue.length} candidates</StatusPill>
          </div>
          <div className="space-y-2">
            {data.review_queue.slice(0, 12).map((item) => (
              <div
                key={`${item.kind}-${item.surface}-${item.auth_segment}-${item.item_type}-${item.item_id}`}
                className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-text-primary truncate">
                      {item.item_name || `${item.item_type} #${item.item_id}`}
                    </div>
                    <div className="text-xs text-text-secondary mt-1">{item.recommendation}</div>
                  </div>
                  <StatusPill tone={item.kind === "promote" ? "ok" : item.kind === "downrank" ? "warn" : "muted"}>
                    {item.kind}
                  </StatusPill>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  <StatusPill tone="muted">{item.surface}</StatusPill>
                  <StatusPill tone="muted">{item.auth_segment}</StatusPill>
                  <StatusPill tone="muted">{item.category || "other"}</StatusPill>
                  <StatusPill tone="muted">{formatTargetName(item.archetype)}</StatusPill>
                  <StatusPill tone="muted">{formatTargetName(item.family_key)}</StatusPill>
                </div>
                {itemHref(item.item_type, item.item_id) && (
                  <div className="mt-2">
                    <a
                      href={itemHref(item.item_type, item.item_id) || "#"}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-xs font-medium text-accent-brand hover:underline"
                    >
                      Open card detail
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )}
                <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mt-3 text-xs">
                  <div>
                    <div className="text-text-muted">Impressions</div>
                    <div className="font-semibold text-text-primary">{item.impressions}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Dismiss</div>
                    <div className="font-semibold text-text-primary">{rateText(item.dismiss_rate)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Open</div>
                    <div className="font-semibold text-text-primary">{rateText(item.open_rate)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Share</div>
                    <div className="font-semibold text-text-primary">{rateText(item.share_rate)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Context</div>
                    <div className="font-semibold text-text-primary">{rateText(item.context_expand_rate)}</div>
                  </div>
                  <div>
                    <div className="text-text-muted">Avg rank</div>
                    <div className="font-semibold text-text-primary">{item.avg_rank ?? "-"}</div>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 mt-3">
                  {[
                    ["accepted_promote", "Promote in feed"],
                    ["accepted_downrank", "Downrank in feed"],
                    ["needs_design_fix", "Design fix"],
                    ["needs_data_fix", "Data fix"],
                    ["ignored", "Ignore"],
                  ].map(([decision, label]) => (
                    <button
                      key={decision}
                      type="button"
                      onClick={async () => {
                        const key = reviewKey(item, decision);
                        setReviewingKey(key);
                        setActionMessage(null);
                        try {
                          await submitDiscoverReviewDecision(secret, item, decision);
                          await mutate(["discover-engagement", secret, engagementDays]);
                          setActionMessage(`${label} saved`);
                        } catch (error) {
                          setActionMessage(error instanceof Error ? error.message : "Review decision failed");
                        } finally {
                          setReviewingKey(null);
                        }
                      }}
                      disabled={reviewingKey !== null}
                      className="px-2 py-1 rounded-md border border-surface-border bg-surface-card text-[11px] text-text-secondary hover:text-text-primary disabled:opacity-60"
                    >
                      {reviewingKey === reviewKey(item, decision) ? "Saving..." : label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.recent_review_decisions?.length > 0 && (
        <div>
          <div className="text-xs font-medium text-text-primary mb-2">Recent Review Decisions</div>
          <div className="space-y-1">
            {data.recent_review_decisions.slice(0, 8).map((decision) => (
              <div key={decision.id} className="flex items-center justify-between gap-3 text-xs rounded-md border border-surface-border bg-surface-elevated/30 px-3 py-2">
                <span className="truncate text-text-secondary">{decision.item_name || `${decision.item_type} #${decision.item_id}`}</span>
                <StatusPill tone="muted">{formatTargetName(decision.decision)}</StatusPill>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.opportunities.length > 0 && (
        <div>
          <div className="flex items-center justify-between gap-3 mb-2">
            <div>
              <div className="text-xs font-medium text-text-primary">Ranking Opportunities</div>
              <div className="text-[11px] text-text-muted">
                Aggregate patterns only. Use the Human Review Queue for card-level ranking changes.
              </div>
            </div>
          </div>
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

function ScoreBucketList({ rows }: { rows: DiscoverScoreBucket[] }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div>
          <div className="text-xs font-medium text-text-primary">Score Buckets</div>
          <div className="text-[11px] text-text-muted">
            Engagement by feed score band. Negative scores here are candidates for ranking review.
          </div>
        </div>
        <StatusPill tone="muted">{rows.length} buckets</StatusPill>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-2">
        {rows.slice(0, 8).map((row) => (
          <div key={row.bucket} className="rounded-md border border-surface-border bg-surface-card p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-text-primary">{row.bucket}</span>
              <span className={row.engagement_score < 0 ? "text-xs text-accent-danger" : "text-xs text-accent-live"}>
                {signedNumber(row.engagement_score, 2)}
              </span>
            </div>
            <div className="text-[11px] text-text-muted mt-1">
              {row.impressions.toLocaleString()} impressions
            </div>
            <div className="grid grid-cols-3 gap-1 mt-2 text-[11px]">
              <span className="text-text-secondary">Open {rateText(row.open_rate)}</span>
              <span className="text-text-secondary">Dismiss {rateText(row.dismiss_rate)}</span>
              <span className="text-text-secondary">Share {rateText(row.share_rate)}</span>
            </div>
          </div>
        ))}
      </div>
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

function LaunchHealthList({
  title,
  rows,
  metric,
}: {
  title: string;
  rows: DiscoverLaunchHealthItem[];
  metric: "impressions" | "extra_impressions";
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
      <div className="text-xs font-medium text-text-primary mb-2">{title}</div>
      {rows.length === 0 ? (
        <div className="text-xs text-text-muted">No candidates.</div>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 6).map((row) => (
            <div key={`${title}-${row.item_type}-${row.item_id}-${row.surface || "unknown"}`} className="text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-text-primary truncate">
                  {row.item_name || `${row.item_type} #${row.item_id}`}
                </span>
                <span className="text-text-muted shrink-0">{(row[metric] ?? 0).toLocaleString()}</span>
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                <StatusPill tone="muted">{row.surface || "unknown"}</StatusPill>
                <StatusPill tone="muted">{row.category || "other"}</StatusPill>
                {row.reason && <StatusPill tone="warn">{formatTargetName(row.reason)}</StatusPill>}
              </div>
              {itemHref(row.item_type, row.item_id) && (
                <a
                  href={itemHref(row.item_type, row.item_id) || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-accent-brand hover:underline"
                >
                  Open detail
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
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
  const [personalizationFilter, setPersonalizationFilter] = useState<PersonalizationFilter>("all");
  const [top50QuickFilter, setTop50QuickFilter] = useState<Top50QuickFilter>("all");
  const [missingBucket, setMissingBucket] = useState("all");
  const [search, setSearch] = useState("");
  const [triggering, setTriggering] = useState(false);
  const [triggeringDiagnostics, setTriggeringDiagnostics] = useState(false);
  const [engagementDays, setEngagementDays] = useState(7);
  const [selectedDiagnosticRunId, setSelectedDiagnosticRunId] = useState("");
  const [diagnosticSourceGroup, setDiagnosticSourceGroup] = useState("all");
  const [diagnosticStatus, setDiagnosticStatus] = useState("miss");
  const [diagnosticBucket, setDiagnosticBucket] = useState("all");
  const [diagnosticOffset, setDiagnosticOffset] = useState(0);
  const [expandedTraceId, setExpandedTraceId] = useState<number | null>(null);
  const [traceByMarketId, setTraceByMarketId] = useState<Record<number, DiscoverMarketTrace>>({});
  const [traceLoadingId, setTraceLoadingId] = useState<number | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

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
  const diagnosticRunsKey = submittedSecret ? ["discover-diagnostic-runs", submittedSecret] : null;
  const diagnosticTrendsKey = submittedSecret ? ["discover-diagnostic-trends", submittedSecret] : null;
  const diagnosticRowsKey = submittedSecret && selectedDiagnosticRunId
    ? [
        "discover-diagnostic-rows",
        submittedSecret,
        selectedDiagnosticRunId,
        diagnosticSourceGroup,
        diagnosticStatus,
        diagnosticBucket,
        diagnosticOffset,
      ]
    : null;

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

  const { data: diagnosticRunsData } = useSWR(
    diagnosticRunsKey,
    () => fetchDiscoverDiagnosticRuns(submittedSecret!),
    { refreshInterval: 60000 }
  );

  const { data: diagnosticTrendsData } = useSWR(
    diagnosticTrendsKey,
    () => fetchDiscoverDiagnosticTrends(submittedSecret!),
    { refreshInterval: 60000 }
  );

  const { data: diagnosticRowsData, isLoading: diagnosticRowsLoading } = useSWR(
    diagnosticRowsKey,
    () => fetchDiscoverDiagnosticRows(
      submittedSecret!,
      selectedDiagnosticRunId,
      {
        sourceGroup: diagnosticSourceGroup,
        status: diagnosticStatus,
        triageBucket: diagnosticBucket,
        offset: diagnosticOffset,
      }
    ),
    { refreshInterval: 60000 }
  );

  useEffect(() => {
    const firstRunId = diagnosticRunsData?.runs?.[0]?.run_id;
    if (firstRunId && !selectedDiagnosticRunId) {
      setSelectedDiagnosticRunId(firstRunId);
    }
  }, [diagnosticRunsData, selectedDiagnosticRunId]);

  useEffect(() => {
    setDiagnosticOffset(0);
  }, [selectedDiagnosticRunId, diagnosticSourceGroup, diagnosticStatus, diagnosticBucket]);

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
  const personalizationRollup = useMemo<PersonalizationRollup>(() => {
    const items = data?.debug_items || [];
    const tracedItems = items.filter((item) => item.personalization_trace);
    const categoryMap = new Map<string, {
      count: number;
      multiplierTotal: number;
      scoreDeltaTotal: number;
      boosted: number;
      suppressed: number;
    }>();
    const reasonMap = new Map<string, number>();

    tracedItems.forEach((item) => {
      const trace = item.personalization_trace!;
      const categoryKey = trace.category || item.category || "other";
      const existing = categoryMap.get(categoryKey) || {
        count: 0,
        multiplierTotal: 0,
        scoreDeltaTotal: 0,
        boosted: 0,
        suppressed: 0,
      };
      existing.count += 1;
      existing.multiplierTotal += trace.multiplier;
      existing.scoreDeltaTotal += trace.score_delta;
      if (trace.score_delta > 0) existing.boosted += 1;
      if (trace.score_delta < 0) existing.suppressed += 1;
      categoryMap.set(categoryKey, existing);

      trace.reasons.forEach((reason) => {
        reasonMap.set(reason, (reasonMap.get(reason) || 0) + 1);
      });
    });

    const scoreDeltaTotal = tracedItems.reduce(
      (total, item) => total + (item.personalization_trace?.score_delta || 0),
      0
    );
    const multiplierTotal = tracedItems.reduce(
      (total, item) => total + (item.personalization_trace?.multiplier || 0),
      0
    );

    return {
      total: items.length,
      traced: tracedItems.length,
      personalized: tracedItems.filter((item) => item.personalization_trace?.is_personalized).length,
      boosted: tracedItems.filter((item) => (item.personalization_trace?.score_delta || 0) > 0).length,
      suppressed: tracedItems.filter((item) => (item.personalization_trace?.score_delta || 0) < 0).length,
      neutral: tracedItems.filter((item) => (item.personalization_trace?.score_delta || 0) === 0).length,
      missing: items.length - tracedItems.length,
      avgMultiplier: tracedItems.length > 0 ? multiplierTotal / tracedItems.length : null,
      avgScoreDelta: tracedItems.length > 0 ? scoreDeltaTotal / tracedItems.length : null,
      categories: Array.from(categoryMap.entries())
        .map(([categoryName, row]) => ({
          category: categoryName,
          count: row.count,
          avgMultiplier: row.multiplierTotal / row.count,
          avgScoreDelta: row.scoreDeltaTotal / row.count,
          boosted: row.boosted,
          suppressed: row.suppressed,
        }))
        .sort((a, b) => Math.abs(b.avgScoreDelta) - Math.abs(a.avgScoreDelta)),
      reasons: Array.from(reasonMap.entries())
        .map(([reason, count]) => ({ reason, count }))
        .sort((a, b) => b.count - a.count),
    };
  }, [data]);

  const top50QuickFilterCounts = useMemo<Record<Top50QuickFilter, number>>(() => {
    const items = data?.debug_items || [];
    return {
      all: items.length,
      weak_explanation: items.filter((item) => !item.explanation_ok).length,
      low_quality: items.filter((item) => item.quality_class === "low_quality" || item.quality_class === "suppress").length,
      ladder: items.filter((item) => item.ladder).length,
      ground_truth: items.filter((item) => item.ground_truth).length,
      missing_trace: items.filter((item) => !item.personalization_trace).length,
    };
  }, [data]);

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data?.debug_items || []).filter((item) => {
      if (category !== "all" && item.category !== category) return false;
      if (archetype !== "all" && item.archetype !== archetype) return false;
      if (quality !== "all" && item.quality_class !== quality) return false;
      if (top50QuickFilter === "weak_explanation" && item.explanation_ok) return false;
      if (
        top50QuickFilter === "low_quality"
        && item.quality_class !== "low_quality"
        && item.quality_class !== "suppress"
      ) return false;
      if (top50QuickFilter === "ladder" && !item.ladder) return false;
      if (top50QuickFilter === "ground_truth" && !item.ground_truth) return false;
      if (top50QuickFilter === "missing_trace" && item.personalization_trace) return false;
      const trace = item.personalization_trace;
      if (personalizationFilter === "personalized" && !trace?.is_personalized) return false;
      if (personalizationFilter === "boosted" && (!trace || trace.score_delta <= 0)) return false;
      if (personalizationFilter === "suppressed" && (!trace || trace.score_delta >= 0)) return false;
      if (personalizationFilter === "neutral" && (!trace || trace.score_delta !== 0)) return false;
      if (personalizationFilter === "missing" && trace) return false;
      if (query && !`${item.name} ${item.headline || ""} ${item.reason || ""}`.toLowerCase().includes(query)) {
        return false;
      }
      return true;
    });
  }, [archetype, category, data, personalizationFilter, quality, search, top50QuickFilter]);

  const filteredMissingGroundTruth = useMemo(() => {
    return (data?.missing_ground_truth || []).filter((item) => {
      if (missingBucket !== "all" && item.triage_bucket !== missingBucket) return false;
      return true;
    });
  }, [data, missingBucket]);
  const emailGroundTruthMisses = useMemo(() => {
    return (
      data?.email_ground_truth_misses
      || (data?.missing_ground_truth || []).filter((item) => item.source === "polymarket_email")
    );
  }, [data]);
  const emailMissBucketCounts = useMemo(() => {
    return emailGroundTruthMisses.reduce<Record<string, number>>((acc, item) => {
      acc[item.triage_bucket] = (acc[item.triage_bucket] || 0) + 1;
      return acc;
    }, {});
  }, [emailGroundTruthMisses]);
  const externalCuratorMisses = useMemo(() => {
    return data?.external_curator_ground_truth_misses || [];
  }, [data]);
  const externalCuratorBucketCounts = useMemo(() => {
    return externalCuratorMisses.reduce<Record<string, number>>((acc, item) => {
      acc[item.triage_bucket] = (acc[item.triage_bucket] || 0) + 1;
      return acc;
    }, {});
  }, [externalCuratorMisses]);

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

  const triggerDiagnosticSnapshot = async () => {
    if (!submittedSecret) return;
    setTriggeringDiagnostics(true);
    try {
      await triggerDiscoverDiagnosticSnapshot(submittedSecret);
      setTimeout(() => {
        mutate(diagnosticRunsKey);
        mutate(diagnosticTrendsKey);
      }, 5000);
    } finally {
      setTriggeringDiagnostics(false);
    }
  };

  const refreshAdminView = async () => {
    await Promise.all([
      debugKey ? mutate(debugKey) : Promise.resolve(),
      hookKey ? mutate(hookKey) : Promise.resolve(),
      engagementKey ? mutate(engagementKey) : Promise.resolve(),
      diagnosticRunsKey ? mutate(diagnosticRunsKey) : Promise.resolve(),
      diagnosticTrendsKey ? mutate(diagnosticTrendsKey) : Promise.resolve(),
      diagnosticRowsKey ? mutate(diagnosticRowsKey) : Promise.resolve(),
    ]);
    setLastRefreshedAt(new Date());
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
  const launchHealth = engagementData?.launch_health;
  const hardGateIssues = summary
    ? summary.boring_count
      + summary.ladder_count
      + summary.duplicate_family_count
      + Math.max(0, 20 - summary.explanation_ok_count)
      + failedStrict.length
      + failedPositive.length
    : 0;
  const topMissBucket = summary
    ? Object.entries(data.missing_ground_truth_summary?.bucket_counts || {})
        .sort((a, b) => b[1] - a[1])[0]?.[0] || null
    : null;

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
          onClick={refreshAdminView}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-surface-border text-sm text-text-secondary hover:text-text-primary hover:bg-surface-elevated"
        >
          <RefreshCw className="w-4 h-4" />
          {lastRefreshedAt ? `Refresh ${lastRefreshedAt.toLocaleTimeString()}` : "Refresh"}
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
          <ReviewPathNav
            groundTruthHits={summary.ground_truth_hit_count_50}
            missingCount={data.missing_ground_truth?.length || 0}
            persistedRuns={diagnosticRunsData?.runs?.length || 0}
            hardGateIssues={hardGateIssues}
            topMissBucket={topMissBucket}
            repeatRate={launchHealth?.repeat_rate ?? null}
            staleRate={launchHealth?.stale_rate ?? null}
          />

          <div id="health" className="scroll-mt-20 grid grid-cols-2 md:grid-cols-4 gap-3">
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
            {data.email_ground_truth?.configured && (
              <>
                <StatCard
                  label="Email @20"
                  value={`${data.email_ground_truth.top20_hits}/${data.email_ground_truth.total}`}
                  ok={data.email_ground_truth.total > 0 ? data.email_ground_truth.top20_hits > 0 : undefined}
                  sub={`${data.email_ground_truth.loaded_count}/${data.email_ground_truth.raw_row_count} rows loaded`}
                />
                <StatCard
                  label="Email Freshness"
                  value={data.email_ground_truth.latest_date || "unknown"}
                  ok={data.email_ground_truth.stale === null ? undefined : !data.email_ground_truth.stale}
                  sub={data.email_ground_truth.stale ? `Stale >${data.email_ground_truth.stale_after_days}d` : "Current export"}
                />
              </>
            )}
            {data.external_curator_ground_truth?.configured && (
              <StatCard
                label="Curator @50"
                value={`${data.external_curator_ground_truth.top50_hits}/${data.external_curator_ground_truth.total}`}
                ok={data.external_curator_ground_truth.total > 0 ? data.external_curator_ground_truth.top50_hits > 0 : undefined}
                sub={
                  data.external_curator_ground_truth.latest_date
                    ? `${data.external_curator_ground_truth.loaded_count}/${data.external_curator_ground_truth.raw_row_count} rows, latest ${data.external_curator_ground_truth.latest_date}`
                    : `${data.external_curator_ground_truth.loaded_count}/${data.external_curator_ground_truth.raw_row_count} rows loaded`
                }
              />
            )}
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

          {data.email_ground_truth?.error && (
            <div className="bg-surface-card border border-accent-danger/30 rounded-lg p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-text-primary mb-2">
                <AlertTriangle className="w-4 h-4 text-accent-danger" />
                Email Ground Truth Export
              </div>
              <div className="text-sm text-text-secondary break-words">
                {data.email_ground_truth.error}
              </div>
            </div>
          )}

          {data.external_curator_ground_truth?.error && (
            <div className="bg-surface-card border border-accent-danger/30 rounded-lg p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-text-primary mb-2">
                <AlertTriangle className="w-4 h-4 text-accent-danger" />
                External Curator Ground Truth
              </div>
              <div className="text-sm text-text-secondary break-words">
                {data.external_curator_ground_truth.error}
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

          <div id="personalization" className="scroll-mt-20">
            <PersonalizationPanel rollup={personalizationRollup} />
          </div>

          <div id="diagnostics" className="scroll-mt-20 space-y-3">
            <DiagnosticTrendsPanel runs={diagnosticTrendsData?.runs || []} />
            <DiagnosticRunsPanel
              runs={diagnosticRunsData?.runs || []}
              rows={diagnosticRowsData}
              rowsLoading={diagnosticRowsLoading}
              selectedRunId={selectedDiagnosticRunId}
              setSelectedRunId={setSelectedDiagnosticRunId}
              sourceGroup={diagnosticSourceGroup}
              setSourceGroup={setDiagnosticSourceGroup}
              status={diagnosticStatus}
              setStatus={setDiagnosticStatus}
              triageBucket={diagnosticBucket}
              setTriageBucket={setDiagnosticBucket}
              offset={diagnosticOffset}
              setOffset={setDiagnosticOffset}
              onTrigger={triggerDiagnosticSnapshot}
              triggering={triggeringDiagnostics}
              onToggleTrace={toggleTrace}
              expandedTraceId={expandedTraceId}
              traceByMarketId={traceByMarketId}
              traceLoadingId={traceLoadingId}
              traceError={traceError}
            />
          </div>

          <div id="behavior" className="scroll-mt-20 space-y-3">
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
              <EngagementPanel data={engagementData} secret={submittedSecret!} engagementDays={engagementDays} />
            ) : (
              <div className="bg-surface-card border border-surface-border rounded-lg p-4 text-sm text-text-muted">
                Loading engagement...
              </div>
            )}
          </div>

          {data.email_ground_truth?.configured && (
            <div id="email-misses" className="scroll-mt-20 bg-surface-card border border-surface-border rounded-lg overflow-hidden">
              <div className="p-4 border-b border-surface-border">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <h2 className="text-sm font-semibold text-text-primary">Polymarket Email Misses</h2>
                    <p className="text-xs text-text-muted mt-1">
                      Use this as an editorial audit: inspect candidate recall gaps first, ignore game-market noise, and only tune ranking after confirming the miss is worth showing.
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1">
                    <StatusPill tone="muted">{`${data.email_ground_truth.top20_hits}/${data.email_ground_truth.total} @20`}</StatusPill>
                    <StatusPill tone="muted">{`${data.email_ground_truth.top50_hits}/${data.email_ground_truth.total} @50`}</StatusPill>
                    <StatusPill tone={data.email_ground_truth.stale ? "warn" : "ok"}>
                      {data.email_ground_truth.latest_date || "unknown date"}
                    </StatusPill>
                  </div>
                </div>
                {emailGroundTruthMisses.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-3">
                    {Object.entries(emailMissBucketCounts).map(([bucket, count]) => (
                      <StatusPill key={bucket} tone={bucket === "candidate_recall_gap" ? "warn" : "muted"}>
                        {`${formatTargetName(bucket)}: ${count}`}
                      </StatusPill>
                    ))}
                  </div>
                )}
              </div>
              {emailGroundTruthMisses.length > 0 ? (
                <div className="divide-y divide-surface-border/60">
                  {emailGroundTruthMisses.slice(0, 16).map((item) => (
                    <div key={`email-${item.name}`} className="p-3 hover:bg-surface-elevated/40">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="font-medium text-sm text-text-primary">{item.name}</div>
                          <div className="flex flex-wrap gap-1 mt-2">
                            <StatusPill tone={item.triage_bucket === "candidate_recall_gap" ? "warn" : "muted"}>
                              {formatTargetName(item.triage_bucket)}
                            </StatusPill>
                            <StatusPill tone="muted">{item.category}</StatusPill>
                            <StatusPill tone="muted">{formatTargetName(item.archetype)}</StatusPill>
                            {item.interestingness && <StatusPill tone="muted">{`I ${item.interestingness}`}</StatusPill>}
                            {item.timeliness && <StatusPill tone="muted">{item.timeliness}</StatusPill>}
                            {item.shareability && <StatusPill tone="muted">{`S ${item.shareability}`}</StatusPill>}
                            {item.db_trace && (
                              <StatusPill tone={item.db_trace.matches.length > 0 ? "ok" : "warn"}>
                                {item.db_trace.trace_status ? formatTargetName(item.db_trace.trace_status) : "db trace"}
                              </StatusPill>
                            )}
                          </div>
                          {item.hook && (
                            <div className="text-xs text-text-secondary mt-2 line-clamp-2">{item.hook}</div>
                          )}
                          <div className="text-xs text-text-muted mt-2">{item.recommended_action}</div>
                        </div>
                        {item.db_trace?.matches?.[0] && (
                          <button
                            type="button"
                            onClick={() => toggleTrace(item.db_trace!.matches[0].id)}
                            className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-primary shrink-0"
                          >
                            <ChevronDown className={`w-3 h-3 transition-transform ${expandedTraceId === item.db_trace.matches[0].id ? "rotate-180" : ""}`} />
                            #{item.db_trace.matches[0].id}
                          </button>
                        )}
                      </div>
                      {item.db_trace?.matches?.[0] && expandedTraceId === item.db_trace.matches[0].id && (
                        <div className="mt-3 rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
                          {traceLoadingId === item.db_trace.matches[0].id && (
                            <div className="text-xs text-text-muted animate-pulse">Loading trace...</div>
                          )}
                          {traceByMarketId[item.db_trace.matches[0].id] ? (
                            <TracePanel trace={traceByMarketId[item.db_trace.matches[0].id]} />
                          ) : (
                            <div className="text-xs text-text-secondary">{item.db_trace.trace_summary}</div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-6 text-sm text-text-muted">No Polymarket email misses in the current diagnostic set.</div>
              )}
            </div>
          )}

          {data.external_curator_ground_truth?.configured && (
            <div id="curator-misses" className="scroll-mt-20 bg-surface-card border border-surface-border rounded-lg overflow-hidden">
              <div className="p-4 border-b border-surface-border">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div>
                    <h2 className="text-sm font-semibold text-text-primary">External Curator Misses</h2>
                    <p className="text-xs text-text-muted mt-1">
                      Advisory public-curator inputs only. Use this to find recall gaps before adding any ranking boost.
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1">
                    <StatusPill tone="muted">{`${data.external_curator_ground_truth.top20_hits}/${data.external_curator_ground_truth.total} @20`}</StatusPill>
                    <StatusPill tone="muted">{`${data.external_curator_ground_truth.top50_hits}/${data.external_curator_ground_truth.total} @50`}</StatusPill>
                    {data.external_curator_ground_truth.latest_date && (
                      <StatusPill tone={data.external_curator_ground_truth.stale ? "warn" : "ok"}>
                        {data.external_curator_ground_truth.latest_date}
                      </StatusPill>
                    )}
                  </div>
                </div>
                {externalCuratorMisses.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-3">
                    {Object.entries(externalCuratorBucketCounts).map(([bucket, count]) => (
                      <StatusPill key={bucket} tone={bucket === "candidate_recall_gap" ? "warn" : "muted"}>
                        {`${formatTargetName(bucket)}: ${count}`}
                      </StatusPill>
                    ))}
                    {Object.entries(data.external_curator_ground_truth.source_counts || {}).slice(0, 4).map(([source, count]) => (
                      <StatusPill key={source} tone="muted">
                        {`${source}: ${count}`}
                      </StatusPill>
                    ))}
                  </div>
                )}
                {(data.external_curator_ground_truth.source_health?.length || 0) > 0 && (
                  <div className="mt-3 grid md:grid-cols-2 gap-2">
                    {data.external_curator_ground_truth.source_health!.slice(0, 6).map((source) => (
                      <div key={source.source} className="rounded-lg border border-surface-border bg-surface-elevated/40 p-2">
                        <div className="flex items-center justify-between gap-3 text-xs">
                          <span className="font-medium text-text-primary truncate">{source.source}</span>
                          <StatusPill tone={source.stale ? "warn" : source.latest_date ? "ok" : "muted"}>
                            {source.latest_date || "undated"}
                          </StatusPill>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          <StatusPill tone="muted">{`${source.count} rows`}</StatusPill>
                          {Object.entries(source.platform_counts || {}).slice(0, 3).map(([platform, count]) => (
                            <StatusPill key={platform} tone="muted">
                              {`${platform}: ${count}`}
                            </StatusPill>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {externalCuratorMisses.length > 0 ? (
                <div className="divide-y divide-surface-border/60">
                  {externalCuratorMisses.slice(0, 16).map((item) => (
                    <div key={`curator-${item.name}`} className="p-3 hover:bg-surface-elevated/40">
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <div className="font-medium text-sm text-text-primary">{item.name}</div>
                          <div className="flex flex-wrap gap-1 mt-2">
                            <StatusPill tone={item.triage_bucket === "candidate_recall_gap" ? "warn" : "muted"}>
                              {formatTargetName(item.triage_bucket)}
                            </StatusPill>
                            <StatusPill tone="muted">{item.category}</StatusPill>
                            <StatusPill tone="muted">{formatTargetName(item.archetype)}</StatusPill>
                            {item.source && <StatusPill tone="muted">{item.source}</StatusPill>}
                            {item.platform && <StatusPill tone="muted">{item.platform}</StatusPill>}
                            {item.handle && <StatusPill tone="muted">{item.handle}</StatusPill>}
                            {item.engagement && <StatusPill tone="muted">{`eng ${item.engagement}`}</StatusPill>}
                            {item.db_trace && (
                              <StatusPill tone={item.db_trace.matches.length > 0 ? "ok" : "warn"}>
                                {item.db_trace.trace_status ? formatTargetName(item.db_trace.trace_status) : "db trace"}
                              </StatusPill>
                            )}
                          </div>
                          {item.hook && (
                            <div className="text-xs text-text-secondary mt-2 line-clamp-2">{item.hook}</div>
                          )}
                          {item.url && (
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 text-xs text-accent-futures hover:underline mt-2"
                            >
                              Source
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          )}
                          <div className="text-xs text-text-muted mt-2">{item.recommended_action}</div>
                        </div>
                        {item.db_trace?.matches?.[0] && (
                          <button
                            type="button"
                            onClick={() => toggleTrace(item.db_trace!.matches[0].id)}
                            className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-primary shrink-0"
                          >
                            <ChevronDown className={`w-3 h-3 transition-transform ${expandedTraceId === item.db_trace.matches[0].id ? "rotate-180" : ""}`} />
                            #{item.db_trace.matches[0].id}
                          </button>
                        )}
                      </div>
                      {item.db_trace?.matches?.[0] && expandedTraceId === item.db_trace.matches[0].id && (
                        <div className="mt-3 rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
                          {traceLoadingId === item.db_trace.matches[0].id && (
                            <div className="text-xs text-text-muted animate-pulse">Loading trace...</div>
                          )}
                          {traceByMarketId[item.db_trace.matches[0].id] ? (
                            <TracePanel trace={traceByMarketId[item.db_trace.matches[0].id]} />
                          ) : (
                            <div className="text-xs text-text-secondary">{item.db_trace.trace_summary}</div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-6 text-sm text-text-muted">No external curator misses in the current diagnostic set.</div>
              )}
            </div>
          )}

          <div id="misses" className="scroll-mt-20 bg-surface-card border border-surface-border rounded-lg overflow-hidden">
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

          <div id="top50" className="scroll-mt-20 bg-surface-card border border-surface-border rounded-lg overflow-hidden">
            <div className="p-4 border-b border-surface-border space-y-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                <Filter className="w-4 h-4" />
                Top 50 Diagnostics
              </div>
              <div className="grid md:grid-cols-5 gap-2">
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
                <select value={personalizationFilter} onChange={(e) => setPersonalizationFilter(e.target.value as PersonalizationFilter)} className="px-3 py-2 rounded-lg bg-surface-elevated border border-surface-border text-sm text-text-primary">
                  <option value="all">All personalization</option>
                  <option value="personalized">{`Personalized (${personalizationRollup.personalized})`}</option>
                  <option value="boosted">{`Boosted (${personalizationRollup.boosted})`}</option>
                  <option value="suppressed">{`Suppressed (${personalizationRollup.suppressed})`}</option>
                  <option value="neutral">{`Neutral (${personalizationRollup.neutral})`}</option>
                  <option value="missing">{`Missing trace (${personalizationRollup.missing})`}</option>
                </select>
              </div>
              <div className="flex flex-wrap gap-2">
                {([
                  ["all", "All"],
                  ["weak_explanation", "Weak explanation"],
                  ["low_quality", "Low quality"],
                  ["ladder", "Ladders"],
                  ["ground_truth", "Ground truth"],
                  ["missing_trace", "Missing trace"],
                ] as const).map(([value, label]) => {
                  const selected = top50QuickFilter === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setTop50QuickFilter(value)}
                      className={`rounded-full border px-3 py-1 text-xs font-medium ${
                        selected
                          ? "border-text-primary bg-text-primary text-surface-deep"
                          : "border-surface-border bg-surface-elevated text-text-secondary hover:text-text-primary"
                      }`}
                    >
                      {`${label} ${top50QuickFilterCounts[value]}`}
                    </button>
                  );
                })}
              </div>
              <div className="text-xs text-text-muted">{filteredItems.length} shown</div>
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
