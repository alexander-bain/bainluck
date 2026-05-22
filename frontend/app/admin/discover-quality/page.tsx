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
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import PageHeader from "@/components/admin/PageHeader";


import type {
  DebugSummary,
  DebugItem,
  PersonalizationTrace,
  MissingGroundTruthItem,
  MissingDbMatch,
  MissingDbTrace,
  MissingGroundTruthSummary,
  EmailGroundTruthDiagnostics,
  DiscoverDiagnosticRun,
  DiscoverDiagnosticRunsResponse,
  DiscoverDiagnosticTrendRun,
  DiscoverDiagnosticTrendsResponse,
  DiscoverDiagnosticRow,
  DiscoverDiagnosticRowsResponse,
  ExternalCuratorGroundTruthStatus,
  GroundTruthHealthIssue,
  GroundTruthHealthReport,
  GroundTruthHealthResponse,
  FeedDebugResponse,
  PersonalizationRollup,
  CandidatePoolTrace,
  DiscoverMarketTrace,
  HookCoverage,
  DiscoverEngagementGroup,
  DiscoverEngagementItem,
  DiscoverEngagementOpportunity,
  DiscoverEngagementReviewItem,
  DiscoverScoreBucket,
  DiscoverRuntimeConfig,
  DiscoverLaunchHealthItem,
  DiscoverReviewDecision,
  DiscoverEngagementResponse,
  DiscoverLaunchHealthTrend,
  DiscoverLaunchHealthTrendsResponse,
} from "@/components/admin/discover/types";
import type { PersonalizationFilter, Top50QuickFilter } from "@/components/admin/discover/types";
import {
  fetchDiscoverDebug,
  fetchHookCoverage,
  fetchDiscoverTrace,
  fetchDiscoverEngagement,
  fetchDiscoverLaunchHealthTrends,
  fetchDiscoverDiagnosticRuns,
  fetchDiscoverDiagnosticTrends,
  fetchDiscoverDiagnosticRows,
  triggerDiscoverDiagnosticSnapshot,
  fetchExternalCuratorGroundTruthStatus,
  fetchGroundTruthHealth,
  triggerExternalCuratorGroundTruthImport,
  updateDiscoverRuntimeConfig,
  submitDiscoverReviewDecision,
} from "@/components/admin/discover/api";
import { ratioText, formatTargetName, percentText, rateText, signedNumber, rankText, itemHref } from "@/components/admin/discover/utils";
import { StatCard, DistributionBars, StatusPill, DeltaPill } from "@/components/admin/discover/ui";
import PersonalizationPanel from "@/components/admin/discover/PersonalizationPanel";
import DiagnosticTrendsPanel from "@/components/admin/discover/DiagnosticTrendsPanel";
import TracePanel from "@/components/admin/discover/TracePanel";
import ReviewPathNav from "@/components/admin/discover/ReviewPathNav";
import ScoreBucketList from "@/components/admin/discover/ScoreBucketList";
import LaunchHealthTrendPanel from "@/components/admin/discover/LaunchHealthTrendPanel";
import DiagnosticRunsPanel from "@/components/admin/discover/DiagnosticRunsPanel";
import EngagementPanel from "@/components/admin/discover/EngagementPanel";
import RuntimeActionButton from "@/components/admin/discover/RuntimeActionButton";
import EngagementList from "@/components/admin/discover/EngagementList";
import LaunchHealthList from "@/components/admin/discover/LaunchHealthList";


export default function DiscoverQualityPage() {
  usePageTracking({
    pageType: "admin_discover_quality",
    pageTitle: "Admin: Discover Quality",
  });
  useScrollDepth({ pageType: "admin_discover_quality" });
  useEngagementTime({ pageType: "admin_discover_quality" });

  const { secret: submittedSecret } = useAdminAuth();
  const [category, setCategory] = useState("all");
  const [archetype, setArchetype] = useState("all");
  const [quality, setQuality] = useState("all");
  const [personalizationFilter, setPersonalizationFilter] = useState<PersonalizationFilter>("all");
  const [top50QuickFilter, setTop50QuickFilter] = useState<Top50QuickFilter>("all");
  const [missingBucket, setMissingBucket] = useState("all");
  const [search, setSearch] = useState("");
  const [triggering, setTriggering] = useState(false);
  const [triggeringDiagnostics, setTriggeringDiagnostics] = useState(false);
  const [triggeringCuratorImport, setTriggeringCuratorImport] = useState(false);
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

  const debugKey = ["discover-quality", submittedSecret];
  const hookKey = ["hook-coverage", submittedSecret];
  const engagementKey = ["discover-engagement", submittedSecret, engagementDays];
  const launchHealthTrendsKey = ["discover-launch-health-trends", submittedSecret];
  const diagnosticRunsKey = ["discover-diagnostic-runs", submittedSecret];
  const diagnosticTrendsKey = ["discover-diagnostic-trends", submittedSecret];
  const externalCuratorStatusKey = ["external-curator-ground-truth-status", submittedSecret];
  const groundTruthHealthKey = ["ground-truth-health", submittedSecret];
  const diagnosticRowsKey = selectedDiagnosticRunId
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

  const { data: launchHealthTrendsData } = useSWR(
    launchHealthTrendsKey,
    () => fetchDiscoverLaunchHealthTrends(submittedSecret!),
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

  const { data: externalCuratorStatus } = useSWR(
    externalCuratorStatusKey,
    () => fetchExternalCuratorGroundTruthStatus(submittedSecret!),
    { refreshInterval: 60000 }
  );

  const { data: groundTruthHealth } = useSWR(
    groundTruthHealthKey,
    () => fetchGroundTruthHealth(submittedSecret!),
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

  const triggerCuratorImport = async () => {
    if (!submittedSecret) return;
    setTriggeringCuratorImport(true);
    try {
      await triggerExternalCuratorGroundTruthImport(submittedSecret);
      setTimeout(() => {
        mutate(externalCuratorStatusKey);
        mutate(groundTruthHealthKey);
        mutate(debugKey);
      }, 5000);
    } finally {
      setTriggeringCuratorImport(false);
    }
  };

  const refreshAdminView = async () => {
    await Promise.all([
      debugKey ? mutate(debugKey) : Promise.resolve(),
      hookKey ? mutate(hookKey) : Promise.resolve(),
      engagementKey ? mutate(engagementKey) : Promise.resolve(),
      launchHealthTrendsKey ? mutate(launchHealthTrendsKey) : Promise.resolve(),
      diagnosticRunsKey ? mutate(diagnosticRunsKey) : Promise.resolve(),
      diagnosticTrendsKey ? mutate(diagnosticTrendsKey) : Promise.resolve(),
      externalCuratorStatusKey ? mutate(externalCuratorStatusKey) : Promise.resolve(),
      groundTruthHealthKey ? mutate(groundTruthHealthKey) : Promise.resolve(),
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
          <PageHeader
          question="Is the Discover feed showing good content?"
          status={
            error ? "critical"
            : isLoading ? "loading"
            : data && data.debug_summary.boring_count > 0 ? "warning"
            : "good"
          }
          summary={
            isLoading ? "Loading feed debug..."
            : error ? error.message
            : data ? `${data.debug_summary.explanation_ok_count}/${data.debug_summary.items} with explanations · ${data.debug_summary.boring_count} boring`
            : "No data"
          }
          ideal="Zero boring/ladder/duplicate items in top 20. 100% explanation coverage."
          subtitle="Ground truth, engagement, personalization, and card-level traces"
        />

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
            <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-text-primary">Curator Store</h2>
                  <div className="text-xs text-text-muted mt-1">
                    {externalCuratorStatus
                      ? `${externalCuratorStatus.metadata.loaded_count}/${externalCuratorStatus.metadata.raw_row_count} accepted rows`
                      : "Loading persisted rows..."}
                  </div>
                </div>
                {externalCuratorStatus?.metadata.latest_date && (
                  <StatusPill tone={externalCuratorStatus.metadata.stale ? "warn" : "ok"}>
                    {externalCuratorStatus.metadata.latest_date}
                  </StatusPill>
                )}
              </div>
              {externalCuratorStatus ? (
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(externalCuratorStatus.status_counts).slice(0, 4).map(([status, count]) => (
                      <StatusPill key={status} tone={status === "accepted" ? "ok" : "muted"}>
                        {`${formatTargetName(status)}: ${count}`}
                      </StatusPill>
                    ))}
                    {(externalCuratorStatus.metadata.source_health || []).slice(0, 2).map((source) => (
                      <StatusPill key={source.source} tone={source.stale ? "warn" : "muted"}>
                        {`${source.source}: ${source.count}`}
                      </StatusPill>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={triggerCuratorImport}
                    disabled={triggeringCuratorImport}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-text-primary text-surface-deep text-xs font-medium disabled:opacity-50"
                  >
                    <Play className="w-3.5 h-3.5" />
                    {triggeringCuratorImport ? "Queueing..." : "Import curator rows"}
                  </button>
                </div>
              ) : (
                <div className="text-sm text-text-muted">Loading curator status...</div>
              )}
            </div>
            <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-text-primary">Ground Truth Health</h2>
                  <div className="text-xs text-text-muted mt-1">
                    {groundTruthHealth
                      ? `${groundTruthHealth.issue_count} issue${groundTruthHealth.issue_count === 1 ? "" : "s"}`
                      : "Loading source health..."}
                  </div>
                </div>
                {groundTruthHealth && (
                  <StatusPill tone={
                    groundTruthHealth.severity === "critical"
                      ? "warn"
                      : groundTruthHealth.severity === "warning"
                        ? "warn"
                        : groundTruthHealth.severity === "ok"
                          ? "ok"
                          : "muted"
                  }>
                    {formatTargetName(groundTruthHealth.severity)}
                  </StatusPill>
                )}
              </div>
              {groundTruthHealth ? (
                <div className="space-y-2">
                  {groundTruthHealth.reports.map((report) => (
                    <div key={report.label} className="rounded-lg border border-surface-border bg-surface-elevated/40 p-2">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="font-medium text-text-primary">{formatTargetName(report.label)}</span>
                        <StatusPill tone={report.severity === "ok" ? "ok" : report.severity === "info" ? "muted" : "warn"}>
                          {report.eligible_row_count && report.eligible_row_count !== report.raw_row_count
                            ? `${report.loaded_count}/${report.eligible_row_count} eligible`
                            : `${report.loaded_count}/${report.raw_row_count}`}
                        </StatusPill>
                      </div>
                      {report.issues[0] && (
                        <div className="mt-1 text-xs text-text-muted line-clamp-2">
                          {report.issues[0].message}
                        </div>
                      )}
                      {report.filter_counts && Object.keys(report.filter_counts).length > 0 && (
                        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-text-muted">
                          <span>CSV rows: {report.filter_counts.csv_rows ?? report.raw_row_count}</span>
                          <span>Source rows: {report.filter_counts.source_rows ?? report.raw_row_count}</span>
                          <span>Old: {report.filter_counts.outside_lookback ?? 0}</span>
                          <span>Not market: {report.filter_counts.non_market_name ?? 0}</span>
                          <span>Low score: {report.filter_counts.low_interestingness ?? 0}</span>
                          <span>Duplicate: {report.filter_counts.duplicate ?? 0}</span>
                          <span>Loaded: {report.filter_counts.loaded ?? report.loaded_count}</span>
                          {report.eligible_row_count !== undefined && report.eligible_row_count !== null && (
                            <span>Eligible: {report.eligible_row_count}</span>
                          )}
                        </div>
                      )}
                      {(report.latest_source_date || report.latest_loaded_date || report.cutoff_date) && (
                        <div className="mt-1 text-[11px] text-text-muted">
                          Source {report.latest_source_date || "unknown"}
                          {report.latest_loaded_date ? `, loaded ${report.latest_loaded_date}` : ""}
                          {report.cutoff_date ? `, cutoff ${report.cutoff_date}` : ""}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-text-muted">Loading ground truth health...</div>
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
              <EngagementPanel
                data={engagementData}
                secret={submittedSecret!}
                engagementDays={engagementDays}
                launchHealthTrends={launchHealthTrendsData?.windows || []}
              />
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
                            {item.confidence && <StatusPill tone="muted">{`confidence ${item.confidence}`}</StatusPill>}
                            {item.db_trace && (
                              <StatusPill tone={item.db_trace.matches.length > 0 ? "ok" : "warn"}>
                                {item.db_trace.trace_status ? formatTargetName(item.db_trace.trace_status) : "db trace"}
                              </StatusPill>
                            )}
                          </div>
                          {item.hook && (
                            <div className="text-xs text-text-secondary mt-2 line-clamp-2">{item.hook}</div>
                          )}
                          {item.evidence && (
                            <div className="text-xs text-text-secondary mt-2 line-clamp-2">
                              Evidence: {item.evidence}
                            </div>
                          )}
                          {item.extraction_notes && (
                            <div className="text-xs text-text-muted mt-1 line-clamp-2">
                              Notes: {item.extraction_notes}
                            </div>
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
