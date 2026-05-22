"use client";

import type { DiscoverLaunchHealthTrend } from "./types";
import { StatusPill } from "./ui";
import { rateText } from "./utils";

export default function LaunchHealthTrendPanel({ rows }: { rows: DiscoverLaunchHealthTrend[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
      <div className="mb-3">
        <div className="text-xs font-medium text-text-primary">Launch Health Trend</div>
        <div className="text-[11px] text-text-muted">
          Repeat and stale impression rates across recent windows.
        </div>
      </div>
      <div className="grid md:grid-cols-3 gap-2">
        {rows.map((row) => {
          const topRootCause = Object.entries(row.stale_root_causes || {})[0];
          return (
            <div key={row.window} className="rounded-lg border border-surface-border bg-surface-card p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold text-text-primary">{row.window}</div>
                <StatusPill tone={row.stale_rate === 0 && row.repeat_rate === 0 ? "ok" : "warn"}>
                  {`${row.impressions} impressions`}
                </StatusPill>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                <div>
                  <div className="text-text-muted">Repeat</div>
                  <div className="font-semibold text-text-primary">{rateText(row.repeat_rate)}</div>
                  <div className="text-[11px] text-text-muted">
                    {row.repeat_extra_impressions} extra / {row.repeat_sessions} sessions
                  </div>
                </div>
                <div>
                  <div className="text-text-muted">Stale</div>
                  <div className="font-semibold text-text-primary">{rateText(row.stale_rate)}</div>
                  <div className="text-[11px] text-text-muted">
                    {row.stale_impressions} impressions
                  </div>
                </div>
              </div>
              {topRootCause && (
                <div className="mt-2">
                  <StatusPill tone="muted">
                    {`${formatTargetName(topRootCause[0])}: ${topRootCause[1]}`}
                  </StatusPill>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
