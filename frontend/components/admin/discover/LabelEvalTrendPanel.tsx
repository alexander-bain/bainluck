"use client";

import { Play } from "lucide-react";
import type { DiscoverLabelEvalMetricKey, DiscoverLabelEvalTrendRun } from "./types";
import { DeltaPill, StatusPill } from "./ui";
import { formatTargetName, rateText } from "./utils";

const metricColumns: Array<{
  key: DiscoverLabelEvalMetricKey;
  label: string;
  lowerIsBetter: boolean;
}> = [
  { key: "tapworthy_at_k", label: "Tapworthy", lowerIsBetter: false },
  { key: "boring_rate_at_k", label: "Boring", lowerIsBetter: true },
  { key: "duplicate_family_rate_at_k", label: "Duplicates", lowerIsBetter: true },
  { key: "fixable_interest_rate_at_k", label: "Fixable", lowerIsBetter: false },
];

function metricText(value: number | null | undefined) {
  return typeof value === "number" ? rateText(value) : "n/a";
}

function statusTone(status: string) {
  return status === "ok" ? "ok" : status === "error" || status === "failed" ? "warn" : "muted";
}

function regressionText(run: DiscoverLabelEvalTrendRun) {
  const regression = run.notable_regressions?.[0];
  if (!regression) return "none";
  const metric = formatTargetName(regression.metric);
  const delta = typeof regression.delta === "number" ? ` (${regression.delta > 0 ? "+" : ""}${rateText(regression.delta)})` : "";
  return `${metric}${delta}`;
}

export default function LabelEvalTrendPanel({
  runs,
  onTrigger,
  triggering,
}: {
  runs: DiscoverLabelEvalTrendRun[];
  onTrigger: () => void;
  triggering: boolean;
}) {
  const latest = runs[0];
  // L2-128 Item 2d: distinguish "no human labels yet" (starvation — ungraded, not
  // failing) from a genuine regression. An empty history or a latest run with zero
  // rows means nobody has graded picks in Review, so there's nothing to score — that
  // should read as a to-do, not a red alarm.
  const noLabels = !latest || (latest.row_count ?? 0) === 0;

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Label Eval History</h2>
          <p className="text-xs text-text-muted mt-1">
            Grades recent Discover picks against human labels you record in the Review tab
            (tapworthy? boring? duplicate?), and tracks whether each snapshot got better or
            worse than the last. Empty = nobody has graded a batch yet, not a failing feed.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {latest && (
            <StatusPill tone={statusTone(latest.status)}>
              {`${formatTargetName(latest.status)} ${latest.row_count} rows`}
            </StatusPill>
          )}
          <button
            type="button"
            onClick={onTrigger}
            disabled={triggering}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-text-primary text-surface-deep text-xs font-medium disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            {triggering ? "Queueing..." : "Queue eval"}
          </button>
        </div>
      </div>

      {latest ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div>
              <div className="text-xs text-text-muted">Latest</div>
              <div className="text-sm font-semibold text-text-primary">
                {latest.captured_at ? new Date(latest.captured_at).toLocaleString() : latest.run_id}
              </div>
            </div>
            {metricColumns.map((metric) => (
              <div key={metric.key}>
                <div className="text-xs text-text-muted">{metric.label} @{latest.top_k}</div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-sm font-semibold text-text-primary">
                    {metricText(latest[metric.key])}
                  </span>
                  <DeltaPill value={latest.deltas?.[metric.key]} lowerIsBetter={metric.lowerIsBetter} />
                </div>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto rounded-lg border border-surface-border">
            <table className="w-full text-sm">
              <thead className="bg-surface-elevated text-text-muted text-xs">
                <tr>
                  <th className="text-left font-medium p-3">Run</th>
                  <th className="text-left font-medium p-3">Status</th>
                  <th className="text-left font-medium p-3">Top-k Metrics</th>
                  <th className="text-left font-medium p-3">Fixable Interest</th>
                  <th className="text-left font-medium p-3">Regressions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/60">
                {runs.map((run) => (
                  <tr key={run.run_id} className="hover:bg-surface-elevated/40 align-top">
                    <td className="p-3 min-w-[190px]">
                      <div className="font-medium text-text-primary">
                        {run.captured_at ? new Date(run.captured_at).toLocaleString() : run.run_id}
                      </div>
                      <div className="text-xs text-text-muted">
                        top {run.top_k} of {run.row_count}
                        {run.surface ? `, ${run.surface}` : ""}
                        {run.reviewer ? `, ${run.reviewer}` : ""}
                      </div>
                    </td>
                    <td className="p-3">
                      <StatusPill tone={statusTone(run.status)}>{formatTargetName(run.status)}</StatusPill>
                    </td>
                    <td className="p-3 min-w-[250px]">
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                        {metricColumns.slice(0, 3).map((metric) => (
                          <div key={metric.key} className="flex items-center justify-between gap-2">
                            <span className="text-text-muted">{metric.label}</span>
                            <span className="flex items-center gap-1 text-text-primary">
                              {metricText(run[metric.key])}
                              <DeltaPill value={run.deltas?.[metric.key]} lowerIsBetter={metric.lowerIsBetter} />
                            </span>
                          </div>
                        ))}
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-text-muted">Broad appeal</span>
                          <span className="flex items-center gap-1 text-text-primary">
                            {metricText(run.broad_appeal_at_k)}
                            <DeltaPill value={run.deltas?.broad_appeal_at_k} lowerIsBetter={false} />
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className="text-text-primary">{metricText(run.fixable_interest_rate_at_k)}</span>
                        <DeltaPill value={run.deltas?.fixable_interest_rate_at_k} lowerIsBetter={false} />
                      </div>
                    </td>
                    <td className="p-3 min-w-[180px]">
                      <div className={run.notable_regressions?.length ? "text-accent-danger text-xs" : "text-text-muted text-xs"}>
                        {regressionText(run)}
                      </div>
                      {run.notable_regressions?.length > 1 && (
                        <div className="text-[11px] text-text-muted mt-1">
                          +{run.notable_regressions.length - 1} more
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="rounded-lg border border-surface-border bg-surface-elevated/50 p-3 text-sm text-text-secondary">
          <span className="font-medium text-text-primary">Ungraded, not failing.</span>{" "}
          No human-label eval snapshots exist yet because no picks have been graded. Grade a
          batch in the <span className="font-medium">Review</span> tab, then hit
          &ldquo;Queue eval&rdquo; above — a scored run will appear here.
        </div>
      )}
      {latest && noLabels && (
        <div className="rounded-lg border border-surface-border bg-surface-elevated/50 p-3 text-xs text-text-secondary">
          <span className="font-medium text-text-primary">Latest run scored 0 rows</span> —
          that&rsquo;s ungraded, not failing. Record labels in the{" "}
          <span className="font-medium">Review</span> tab so the next snapshot has something to grade.
        </div>
      )}
    </div>
  );
}
