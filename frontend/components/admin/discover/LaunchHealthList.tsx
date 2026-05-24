"use client";

import { ExternalLink } from "lucide-react";

import type { DiscoverLaunchHealthItem } from "./types";
import { formatTargetName, itemHref } from "./utils";
import { StatusPill } from "./ui";

export default function LaunchHealthList({
  title,
  rows,
  metric,
}: {
  title: string;
  rows: DiscoverLaunchHealthItem[];
  metric: "impressions" | "extra_impressions";
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
      <div className="text-xs font-medium text-text-primary mb-2">{title}</div>
      {rows.length === 0 ? (
        <div className="text-xs text-text-muted">No candidates.</div>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 6).map((row) => (
            <div key={`${title}-${row.item_type}-${row.item_id}-${row.surface || "unknown"}`} className="text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-text-primary truncate">
                  {row.item_name || `${row.item_type} #${row.item_id}`}
                </span>
                <span className="text-text-muted shrink-0">{(row[metric] ?? 0).toLocaleString()}</span>
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                <StatusPill tone="muted">{row.surface || "unknown"}</StatusPill>
                <StatusPill tone="muted">{row.category || "other"}</StatusPill>
                {row.reason && <StatusPill tone="warn">{formatTargetName(row.reason)}</StatusPill>}
              </div>
              {itemHref(row.item_type, row.item_id) && (
                <a
                  href={itemHref(row.item_type, row.item_id) || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-accent-brand hover:underline"
                >
                  Open detail
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
