"use client";

import type { DiscoverDiagnosticTrendRun } from "./types";
import { StatusPill, DeltaPill } from "./ui";
import { formatTargetName } from "./utils";

export default function DiagnosticTrendsPanel({ runs }: { runs: DiscoverDiagnosticTrendRun[] }) {
  const latest = runs[0];

  return (
    <div className="bg-surface-card border border-surface-border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-text-primary">Diagnostic Trend</h2>
          <p className="text-xs text-text-muted mt-1">
            How many interesting markets our feed <em>missed</em> vs. what curator emails and
            external sources surfaced, tracked over recent snapshots. A miss = something worth
            showing that our ranking didn&rsquo;t. Fewer misses over time = the feed is catching
            up to the best public picks.
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
