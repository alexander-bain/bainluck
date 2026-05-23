export interface DebugSummary {
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

export interface DebugItem {
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
  context?: string | null;
  hook_description?: string | null;
  image_url?: string | null;
  hook: boolean;
  image: boolean;
  explanation_ok: boolean;
  quality_class: string;
  family_key: string;
  story_key: string | null;
  group_id?: string | null;
  rendered_probability?: number | null;
  top_outcomes?: Array<{
    name?: string | null;
    probability?: number | null;
    current_probability?: number | null;
    probability_change_24h?: number | null;
  }>;
  ladder: boolean;
  reasons: string[];
  ground_truth: boolean;
  personalization_trace?: PersonalizationTrace | null;
}

export interface PersonalizationTrace {
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

export interface MissingGroundTruthItem {
  name: string;
  source: string;
  category: string;
  probability: string | null;
  url?: string | null;
  published_at?: string | null;
  platform?: string | null;
  handle?: string | null;
  engagement?: string | null;
  evidence?: string | null;
  confidence?: string | null;
  extraction_notes?: string | null;
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

export interface MissingDbMatch {
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

export interface MissingDbTrace {
  trace_status: string;
  trace_summary: string;
  recommended_action: string;
  matches: MissingDbMatch[];
}

export interface MissingGroundTruthSummary {
  total: number;
  bucket_counts: Record<string, number>;
}

export interface EmailGroundTruthDiagnostics {
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

export interface DiscoverDiagnosticRun {
  run_id: string;
  captured_at: string | null;
  total: number;
  by_source_group: Record<string, { total: number; hit: number; miss: number }>;
  by_triage_bucket: Record<string, number>;
}

export interface DiscoverDiagnosticRunsResponse {
  runs: DiscoverDiagnosticRun[];
}

export interface DiscoverDiagnosticTrendRun extends DiscoverDiagnosticRun {
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

export interface DiscoverDiagnosticTrendsResponse {
  runs: DiscoverDiagnosticTrendRun[];
}

export interface DiscoverDiagnosticRow {
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

export interface DiscoverDiagnosticRowsResponse {
  run_id: string;
  total: number;
  limit: number;
  offset: number;
  rows: DiscoverDiagnosticRow[];
}

export type DiscoverLabelEvalMetricKey =
  | "tapworthy_at_k"
  | "boring_rate_at_k"
  | "duplicate_family_rate_at_k"
  | "unclear_rate_at_k"
  | "bad_explanation_rate_at_k"
  | "bad_image_rate_at_k"
  | "broad_appeal_at_k"
  | "fixable_interest_rate_at_k"
  | "tapworthy_recall_at_k";

export interface DiscoverLabelEvalRegression {
  metric: DiscoverLabelEvalMetricKey | string;
  previous: number | null;
  current: number | null;
  delta: number | null;
}

export interface DiscoverLabelEvalRun {
  run_id: string;
  eval_name: string;
  status: string;
  surface: string | null;
  reviewer: string | null;
  top_k: number;
  row_count: number;
  captured_at: string | null;
  dataset_window_start: string | null;
  dataset_window_end: string | null;
  tapworthy_at_k: number | null;
  boring_rate_at_k: number | null;
  duplicate_family_rate_at_k: number | null;
  unclear_rate_at_k: number | null;
  bad_explanation_rate_at_k: number | null;
  bad_image_rate_at_k: number | null;
  broad_appeal_at_k: number | null;
  fixable_interest_rate_at_k: number | null;
  tapworthy_recall_at_k: number | null;
  notable_regressions: DiscoverLabelEvalRegression[];
}

export interface DiscoverLabelEvalTrendRun extends DiscoverLabelEvalRun {
  deltas: Partial<Record<DiscoverLabelEvalMetricKey, number>>;
}

export interface DiscoverLabelEvalRunsResponse {
  runs: DiscoverLabelEvalRun[];
}

export interface DiscoverLabelEvalTrendsResponse {
  runs: DiscoverLabelEvalTrendRun[];
}

export interface DiscoverFixableInterestExample {
  judgment_id: number;
  created_at: string | null;
  market_id: number | null;
  event_id: number | null;
  market_name: string | null;
  snapshot_name: string | null;
  label: string;
  rank_seen: number | null;
  score_at_review: number | null;
  would_be_interesting_if: string;
  notes: string | null;
  card_snapshot: Record<string, unknown>;
}

export interface DiscoverFixableInterestCluster {
  cluster_id: string;
  status: string;
  triage: Record<string, unknown>;
  triage_counts: Record<string, number>;
  fix_type: string;
  item_key: string;
  story_key: string | null;
  family_key: string | null;
  group_id: string | null;
  desired_entity_or_variant: string;
  current_entity_or_variant: string;
  would_be_interesting_if: string;
  count: number;
  issue_candidate_count: number;
  max_fixable_interest_score: number | null;
  latest_created_at: string | null;
  categories: string[];
  labels: string[];
  affected_ranks: number[];
  market_ids: number[];
  examples: DiscoverFixableInterestExample[];
}

export interface DiscoverFixableInterestClustersResponse {
  status: string;
  total: number;
  clusters: DiscoverFixableInterestCluster[];
}

export interface ExternalCuratorGroundTruthStatus {
  metadata: {
    configured: boolean;
    source: string | null;
    source_paths?: string[];
    raw_row_count: number;
    loaded_count: number;
    latest_date?: string | null;
    stale?: boolean | null;
    stale_after_days?: number;
    source_counts?: Record<string, number>;
    source_health?: Array<{
      source: string;
      count: number;
      latest_date: string | null;
      stale: boolean | null;
      platform_counts: Record<string, number>;
    }>;
    error?: string | null;
  };
  status_counts: Record<string, number>;
  items: Array<Partial<MissingGroundTruthItem> & { name: string }>;
}

export interface GroundTruthHealthIssue {
  severity: "critical" | "warning" | "info" | "ok";
  code: string;
  message: string;
}

export interface GroundTruthHealthReport {
  label: string;
  severity: "critical" | "warning" | "info" | "ok";
  ok: boolean;
  configured: boolean;
  raw_row_count: number;
  loaded_count: number;
  load_rate: number | null;
  eligible_row_count?: number | null;
  eligible_load_rate?: number | null;
  latest_date: string | null;
  latest_source_date?: string | null;
  latest_loaded_date?: string | null;
  stale: boolean | null;
  stale_after_days?: number | null;
  min_interestingness?: number | null;
  lookback_days?: number | null;
  cutoff_date?: string | null;
  filter_counts?: Record<string, number>;
  issues: GroundTruthHealthIssue[];
}

export interface GroundTruthHealthResponse {
  severity: "critical" | "warning" | "info" | "ok";
  ok: boolean;
  reports: GroundTruthHealthReport[];
  issue_count: number;
}

export interface FeedDebugResponse {
  feed_request_id?: string | null;
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

export type PersonalizationFilter = "all" | "personalized" | "boosted" | "suppressed" | "neutral" | "missing";
export type Top50QuickFilter = "all" | "weak_explanation" | "low_quality" | "ladder" | "ground_truth" | "missing_trace";

export interface PersonalizationRollup {
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

export interface CandidatePoolTrace {
  name: string;
  limit: number;
  candidate_count: number;
  included: boolean;
  position: number | null;
}

export interface DiscoverMarketTrace {
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

export interface HookCoverage {
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

export interface DiscoverEngagementGroup {
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

export interface DiscoverEngagementItem {
  item_type: string;
  item_id: string;
  item_name: string | null;
  category: string | null;
  surface: string | null;
  actions: number;
}

export interface DiscoverEngagementOpportunity {
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

export interface DiscoverEngagementReviewItem {
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

export interface DiscoverScoreBucket {
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

export interface DiscoverRuntimeConfig {
  interaction_suppression_enabled: boolean;
  seen_suppression_hours: number;
  dismiss_suppression_days: number;
  stale_no_movement_days: number;
  no_resolution_stale_days: number;
}

export interface DiscoverLaunchHealthItem {
  item_type: string;
  item_id: string;
  item_name: string | null;
  category: string | null;
  surface: string | null;
  impressions: number;
  extra_impressions?: number;
  reason?: string;
}

export interface DiscoverReviewDecision {
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

export interface DiscoverEngagementResponse {
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

export interface DiscoverLaunchHealthTrend {
  window: string;
  impressions: number;
  repeat_extra_impressions: number;
  repeat_rate: number;
  repeat_sessions: number;
  stale_impressions: number;
  stale_rate: number;
  stale_root_causes: Record<string, number>;
}

export interface DiscoverLaunchHealthTrendsResponse {
  windows: DiscoverLaunchHealthTrend[];
}
