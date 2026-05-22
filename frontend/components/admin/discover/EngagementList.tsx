"use client";

import type { DiscoverEngagementGroup } from "./types";
import { rateText, formatTargetName } from "./utils";

export default function EngagementList({
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
