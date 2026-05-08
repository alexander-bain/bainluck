"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR, { mutate } from "swr";
import {
  AlertTriangle,
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

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("secret");
    if (fromUrl) {
      setSecret(fromUrl);
      setSubmittedSecret(fromUrl);
    }
  }, []);

  const debugKey = submittedSecret ? ["discover-quality", submittedSecret] : null;
  const hookKey = submittedSecret ? ["hook-coverage", submittedSecret] : null;

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

          <div className="grid md:grid-cols-3 gap-3">
            <DistributionBars title="Categories @20" data={summary.category_distribution} />
            <DistributionBars title="Archetypes @20" data={summary.archetype_distribution} />
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
                    <tr key={`${item.type}-${item.id}-${item.rank}`} className="border-t border-surface-border/60 hover:bg-surface-elevated/40">
                      <td className="p-3 align-top text-text-muted">#{item.rank}<br /><span className="text-text-primary font-semibold">{item.score}</span></td>
                      <td className="p-3 align-top min-w-[280px]">
                        <div className="font-medium text-text-primary">{item.name}</div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          <StatusPill tone="muted">{item.category}</StatusPill>
                          <StatusPill tone="muted">{formatTargetName(item.archetype)}</StatusPill>
                          {item.ground_truth && <StatusPill tone="ok">ground truth</StatusPill>}
                        </div>
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
                          {item.reasons.map((reason) => (
                            <StatusPill key={reason} tone="muted">{formatTargetName(reason)}</StatusPill>
                          ))}
                        </div>
                      </td>
                      <td className="p-3 align-top min-w-[220px]">
                        <code className="block text-xs text-text-muted break-all">{item.story_key || item.family_key}</code>
                      </td>
                    </tr>
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
