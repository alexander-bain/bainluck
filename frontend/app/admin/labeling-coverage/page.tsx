"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import {
  usePageTracking,
  useScrollDepth,
  useEngagementTime,
} from "@/hooks";
import { useAdminAuth } from "@/components/admin/AdminAuthProvider";
import PageHeader from "@/components/admin/PageHeader";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const VERDICT_COLORS: Record<string, string> = {
  love: "bg-green-500",
  fine: "bg-blue-400",
  bad: "bg-yellow-500",
  kill: "bg-red-500",
  skip: "bg-gray-400",
};

const VERDICT_ORDER = ["love", "fine", "bad", "kill", "skip"];

const WINDOW_OPTIONS = [
  { value: "24h", label: "24h" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "all", label: "All time" },
];

// --- Types ---

interface StratumRow {
  stratum: string;
  verdicts: Record<string, number>;
  total: number;
  sufficient: boolean;
}

interface ReviewerRow {
  reviewer_hash: string;
  total: number;
  today: number;
  this_week: number;
}

interface QueueRow {
  stratum: string;
  total_candidates: number;
  reviewed: number;
  unreviewed: number;
  exhausted: boolean;
}

interface CoverageData {
  window: string;
  total_reviewed: number;
  by_stratum: StratumRow[];
  by_verdict: Record<string, number>;
  by_category: Record<string, Record<string, number>>;
  reviewer_progress: ReviewerRow[];
  queue_health: QueueRow[];
  insufficient_strata: string[];
  generated_at: string;
}

// --- Helpers ---

function stratumLabel(s: string): string {
  return s
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function verdictBar(
  verdicts: Record<string, number>,
  total: number
): React.ReactNode {
  if (total === 0) {
    return (
      <div className="h-5 rounded bg-surface-elevated flex items-center justify-center">
        <span className="text-[10px] text-text-muted">no labels</span>
      </div>
    );
  }
  return (
    <div className="h-5 rounded overflow-hidden flex">
      {VERDICT_ORDER.map((v) => {
        const count = verdicts[v] || 0;
        if (count === 0) return null;
        const pct = (count / total) * 100;
        return (
          <div
            key={v}
            className={`${VERDICT_COLORS[v] || "bg-gray-300"} transition-all relative group`}
            style={{ width: `${pct}%`, minWidth: pct > 0 ? 4 : 0 }}
            title={`${v}: ${count} (${Math.round(pct)}%)`}
          >
            {pct >= 12 && (
              <span className="absolute inset-0 flex items-center justify-center text-[9px] font-medium text-white">
                {count}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// --- Components ---

function VerdictLegend() {
  return (
    <div className="flex items-center gap-3 text-[10px] text-text-muted">
      {VERDICT_ORDER.map((v) => (
        <span key={v} className="flex items-center gap-1">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-sm ${VERDICT_COLORS[v]}`}
          />
          {v}
        </span>
      ))}
    </div>
  );
}

function StratumHeatmap({ data }: { data: StratumRow[] }) {
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Coverage by Stratum
        </h3>
        <VerdictLegend />
      </div>
      <div className="space-y-2">
        {data.map((row) => (
          <div key={row.stratum} className="flex items-center gap-3">
            <span className="w-40 text-xs text-text-secondary truncate text-right">
              {stratumLabel(row.stratum)}
            </span>
            <div className="flex-1">{verdictBar(row.verdicts, row.total)}</div>
            <span className="w-10 text-right text-xs text-text-muted">
              {row.total}
            </span>
            {!row.sufficient && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-500 font-medium"
                title="Fewer than 50 labels"
              >
                &lt;50
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function CategoryHeatmap({
  data,
}: {
  data: Record<string, Record<string, number>>;
}) {
  const rows = useMemo(() => {
    return Object.entries(data)
      .map(([category, verdicts]) => ({
        category,
        verdicts,
        total: Object.values(verdicts).reduce((s, c) => s + c, 0),
      }))
      .sort((a, b) => b.total - a.total);
  }, [data]);

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">
          Coverage by Category
        </h3>
        <VerdictLegend />
      </div>
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.category} className="flex items-center gap-3">
            <span className="w-32 text-xs text-text-secondary truncate text-right">
              {row.category}
            </span>
            <div className="flex-1">
              {verdictBar(row.verdicts, row.total)}
            </div>
            <span className="w-10 text-right text-xs text-text-muted">
              {row.total}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReviewerProgress({ data }: { data: ReviewerRow[] }) {
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">
        Reviewer Progress
      </h3>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-surface-border">
            <th className="text-left py-2 px-1 text-text-muted font-medium">
              Reviewer
            </th>
            <th className="text-right py-2 px-1 text-text-muted font-medium">
              Total
            </th>
            <th className="text-right py-2 px-1 text-text-muted font-medium">
              Today
            </th>
            <th className="text-right py-2 px-1 text-text-muted font-medium">
              This Week
            </th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr
              key={row.reviewer_hash}
              className="border-b border-surface-border/50"
            >
              <td className="py-1.5 px-1 font-mono text-text-secondary">
                {row.reviewer_hash.slice(0, 8)}
              </td>
              <td className="py-1.5 px-1 text-right text-text-primary font-medium">
                {row.total}
              </td>
              <td className="py-1.5 px-1 text-right">
                {row.today > 0 ? (
                  <span className="text-green-400">{row.today}</span>
                ) : (
                  <span className="text-text-muted">0</span>
                )}
              </td>
              <td className="py-1.5 px-1 text-right text-text-secondary">
                {row.this_week}
              </td>
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td
                colSpan={4}
                className="py-4 text-center text-text-muted"
              >
                No labels yet
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function QueueHealth({ data }: { data: QueueRow[] }) {
  return (
    <div className="bg-surface-card rounded-xl border border-surface-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">
        Queue Health
      </h3>
      <p className="text-xs text-text-muted mb-3">
        Unreviewed candidates per stratum (sampled up to 200)
      </p>
      <div className="space-y-2">
        {data.map((row) => {
          const pct =
            row.total_candidates > 0
              ? Math.round(
                  (row.reviewed / row.total_candidates) * 100
                )
              : 0;
          return (
            <div key={row.stratum} className="flex items-center gap-3">
              <span className="w-40 text-xs text-text-secondary truncate text-right">
                {stratumLabel(row.stratum)}
              </span>
              <div className="flex-1 h-4 bg-surface-elevated rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    row.exhausted
                      ? "bg-green-500/60"
                      : pct >= 50
                        ? "bg-blue-400/60"
                        : "bg-surface-border"
                  }`}
                  style={{ width: `${Math.max(pct, 2)}%` }}
                />
              </div>
              <span className="w-20 text-xs text-right">
                {row.exhausted ? (
                  <span className="text-green-400 font-medium">
                    exhausted
                  </span>
                ) : (
                  <span className="text-text-muted">
                    {row.unreviewed} left
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VerdictSummary({ verdicts }: { verdicts: Record<string, number> }) {
  const total = Object.values(verdicts).reduce((s, c) => s + c, 0);
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {VERDICT_ORDER.map((v) => {
        const count = verdicts[v] || 0;
        const pct = total > 0 ? Math.round((count / total) * 100) : 0;
        return (
          <div
            key={v}
            className="bg-surface-card rounded-xl border border-surface-border p-3 text-center"
          >
            <div className="text-micro text-text-muted uppercase tracking-wider">
              {v}
            </div>
            <div className="text-xl font-bold text-text-primary mt-1">
              {count}
            </div>
            <div className="text-xs text-text-muted">{pct}%</div>
          </div>
        );
      })}
    </div>
  );
}

function InsufficientWarning({ strata }: { strata: string[] }) {
  if (strata.length === 0) return null;
  return (
    <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3">
      <p className="text-xs text-yellow-500 font-medium mb-1">
        Insufficient labels for auto-eval
      </p>
      <p className="text-xs text-text-muted">
        These strata have fewer than 50 labels:{" "}
        {strata.map((s) => stratumLabel(s)).join(", ")}
      </p>
    </div>
  );
}

// --- Main ---

export default function LabelingCoveragePage() {
  usePageTracking({
    pageType: "admin_labeling_coverage",
    pageTitle: "Labeling Coverage",
  });
  useScrollDepth({ pageType: "admin_labeling_coverage" });
  useEngagementTime({ pageType: "admin_labeling_coverage" });

  const { secret } = useAdminAuth();
  const [window, setWindow] = useState("all");

  const { data, error, isLoading } = useSWR<CoverageData>(
    secret ? ["labeling-coverage", secret, window] : null,
    () =>
      fetch(
        `${API_URL}/api/admin/ranking-judgments/coverage?secret=${encodeURIComponent(
          secret
        )}&window=${window}`
      ).then((r) => {
        if (!r.ok) throw new Error("API error: " + r.status);
        return r.json();
      }),
    { refreshInterval: 120000 }
  );

  const status = isLoading
    ? "loading"
    : error
      ? "critical"
      : data && data.insufficient_strata.length > 3
        ? "warning"
        : "good";

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <PageHeader
          question="Is labeling coverage sufficient?"
          status={status}
          summary={
            isLoading
              ? "Loading..."
              : error
                ? error.message
                : `${data?.total_reviewed ?? 0} labels reviewed`
          }
          ideal="50+ labels per stratum. All queues have unreviewed candidates."
          subtitle="Labeling Coverage Dashboard"
        />
        <div className="flex items-center gap-1">
          {WINDOW_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setWindow(opt.value)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                window === opt.value
                  ? "bg-accent-brand/10 border-accent-brand text-accent-brand"
                  : "bg-surface-elevated border-surface-border text-text-muted hover:text-text-secondary"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-400/10 p-3 rounded-lg">
          {error.message}
        </div>
      )}
      {isLoading && (
        <div className="text-sm text-text-muted animate-pulse">
          Loading coverage data...
        </div>
      )}

      {data && (
        <>
          {/* Verdict summary cards */}
          <VerdictSummary verdicts={data.by_verdict} />

          {/* Insufficient strata warning */}
          <InsufficientWarning strata={data.insufficient_strata} />

          {/* Stratum heatmap */}
          <StratumHeatmap data={data.by_stratum} />

          {/* Queue health + reviewer progress side by side */}
          <div className="grid md:grid-cols-2 gap-4">
            <QueueHealth data={data.queue_health} />
            <ReviewerProgress data={data.reviewer_progress} />
          </div>

          {/* Category heatmap */}
          <CategoryHeatmap data={data.by_category} />

          <div className="text-xs text-text-muted text-right">
            Generated{" "}
            {new Date(data.generated_at).toLocaleTimeString()}
          </div>
        </>
      )}
    </div>
  );
}
