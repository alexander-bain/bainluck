"use client";

import { Fragment, useState } from "react";
import { ChevronDown, ExternalLink, Play } from "lucide-react";
import type { DiscoverDiagnosticRun, DiscoverDiagnosticRowsResponse, DiscoverMarketTrace } from "./types";
import { StatusPill } from "./ui";
import { formatTargetName } from "./utils";
import TracePanel from "./TracePanel";

export default function DiagnosticRunsPanel({
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
