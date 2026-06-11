import { getIdToken } from "@/lib/firebase";
import { adminFetch, adminFetchJSON } from "@/lib/adminFetch";
import type {
  FeedDebugResponse,
  HookCoverage,
  DiscoverMarketTrace,
  DiscoverEngagementResponse,
  DiscoverLaunchHealthTrendsResponse,
  DiscoverDiagnosticRunsResponse,
  DiscoverDiagnosticTrendsResponse,
  DiscoverDiagnosticRowsResponse,
  DiscoverLabelEvalRunsResponse,
  DiscoverLabelEvalTrendsResponse,
  DiscoverFixableInterestClustersResponse,
  ExternalCuratorGroundTruthStatus,
  GroundTruthHealthResponse,
  DiscoverRuntimeConfig,
  DiscoverEngagementReviewItem,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchDiscoverDebug(secret: string): Promise<FeedDebugResponse> {
  const params = new URLSearchParams({
    limit: "50",
    include_events: "false",
    include_futures: "true",
    event_pct: "0.15",
    debug: "true",
    debug_ground_truth: "false",
    secret,
  });
  const token = await getIdToken();
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
  const res = await fetch(`${API_URL}/api/feed?${params}`, { headers });
  if (!res.ok) throw new Error(`Feed debug API error: ${res.status}`);
  return res.json();
}

export async function fetchHookCoverage(secret: string): Promise<HookCoverage> {
  return adminFetchJSON<HookCoverage>("/api/admin/hook-coverage", secret);
}

export async function fetchDiscoverTrace(secret: string, marketId: number): Promise<DiscoverMarketTrace> {
  return adminFetchJSON<DiscoverMarketTrace>(
    `/api/admin/discover-quality/trace/${marketId}?include_events=false&event_pct=0.15&limit=50`,
    secret
  );
}

export async function fetchDiscoverEngagement(secret: string, days: number): Promise<DiscoverEngagementResponse> {
  return adminFetchJSON<DiscoverEngagementResponse>(
    `/api/admin/discover-engagement?days=${days}`,
    secret
  );
}

export async function fetchDiscoverLaunchHealthTrends(secret: string): Promise<DiscoverLaunchHealthTrendsResponse> {
  return adminFetchJSON<DiscoverLaunchHealthTrendsResponse>(
    "/api/admin/discover-engagement/launch-health-trends",
    secret
  );
}

export async function fetchDiscoverDiagnosticRuns(secret: string): Promise<DiscoverDiagnosticRunsResponse> {
  return adminFetchJSON<DiscoverDiagnosticRunsResponse>(
    "/api/admin/discover-ground-truth-diagnostics/runs?limit=8",
    secret
  );
}

export async function fetchDiscoverDiagnosticTrends(secret: string): Promise<DiscoverDiagnosticTrendsResponse> {
  return adminFetchJSON<DiscoverDiagnosticTrendsResponse>(
    "/api/admin/discover-ground-truth-diagnostics/trends?limit=8",
    secret
  );
}

export async function fetchDiscoverDiagnosticRows(
  secret: string,
  runId: string,
  filters: { sourceGroup: string; status: string; triageBucket: string; offset: number }
): Promise<DiscoverDiagnosticRowsResponse> {
  const params = new URLSearchParams({
    limit: "100",
    offset: String(filters.offset),
  });
  if (filters.sourceGroup !== "all") params.set("source_group", filters.sourceGroup);
  if (filters.status !== "all") params.set("status", filters.status);
  if (filters.triageBucket !== "all") params.set("triage_bucket", filters.triageBucket);
  return adminFetchJSON<DiscoverDiagnosticRowsResponse>(
    `/api/admin/discover-ground-truth-diagnostics/runs/${encodeURIComponent(runId)}/rows?${params}`,
    secret
  );
}

export async function triggerDiscoverDiagnosticSnapshot(secret: string): Promise<void> {
  const res = await adminFetch(
    "/api/admin/discover-ground-truth-diagnostics/snapshot?limit=50",
    secret,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`Diagnostic snapshot trigger failed: ${res.status}`);
}

export async function fetchDiscoverLabelEvalRuns(secret: string): Promise<DiscoverLabelEvalRunsResponse> {
  return adminFetchJSON<DiscoverLabelEvalRunsResponse>(
    "/api/admin/discover-label-eval/runs?limit=8",
    secret
  );
}

export async function fetchDiscoverLabelEvalTrends(secret: string): Promise<DiscoverLabelEvalTrendsResponse> {
  return adminFetchJSON<DiscoverLabelEvalTrendsResponse>(
    "/api/admin/discover-label-eval/trends?limit=8",
    secret
  );
}

export async function triggerDiscoverLabelEvalSnapshot(secret: string): Promise<void> {
  const res = await adminFetch(
    "/api/admin/discover-label-eval/snapshot?days=30&top_k=20&limit=5000",
    secret,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`Label eval snapshot trigger failed: ${res.status}`);
}

export async function fetchDiscoverFixableInterestClusters(
  secret: string,
  status = "open"
): Promise<DiscoverFixableInterestClustersResponse> {
  return adminFetchJSON<DiscoverFixableInterestClustersResponse>(
    `/api/admin/ranking-judgments/fixable-interest/clusters?status=${encodeURIComponent(status)}&limit=20`,
    secret
  );
}

export async function triageDiscoverFixableInterestCluster(
  secret: string,
  clusterId: string,
  payload: {
    status: "open" | "dismissed" | "linked" | "experiment";
    github_issue_url?: string;
    github_issue_number?: number;
    experiment_key?: string;
    notes?: string;
  }
): Promise<void> {
  const res = await adminFetch(
    `/api/admin/ranking-judgments/fixable-interest/clusters/${encodeURIComponent(clusterId)}/triage`,
    secret,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!res.ok) throw new Error(`Fixable-interest triage failed: ${res.status}`);
}

export async function fetchExternalCuratorGroundTruthStatus(secret: string): Promise<ExternalCuratorGroundTruthStatus> {
  return adminFetchJSON<ExternalCuratorGroundTruthStatus>(
    "/api/admin/discover-external-curator-ground-truth/status?item_limit=8",
    secret
  );
}

export async function fetchGroundTruthHealth(secret: string): Promise<GroundTruthHealthResponse> {
  return adminFetchJSON<GroundTruthHealthResponse>(
    "/api/admin/discover-ground-truth-health",
    secret
  );
}

export async function triggerExternalCuratorGroundTruthImport(secret: string): Promise<void> {
  const res = await adminFetch(
    "/api/admin/discover-external-curator-ground-truth/import",
    secret,
    { method: "POST" }
  );
  if (!res.ok) throw new Error(`Curator ground truth import failed: ${res.status}`);
}

export async function updateDiscoverRuntimeConfig(
  secret: string,
  config: Partial<DiscoverRuntimeConfig>
): Promise<void> {
  const res = await adminFetch(
    "/api/admin/discover-config",
    secret,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }
  );
  if (!res.ok) throw new Error(`Runtime config update failed: ${res.status}`);
}

export async function submitDiscoverReviewDecision(
  secret: string,
  item: DiscoverEngagementReviewItem,
  decision: string
): Promise<void> {
  const res = await adminFetch(
    "/api/admin/discover-review-decisions",
    secret,
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
