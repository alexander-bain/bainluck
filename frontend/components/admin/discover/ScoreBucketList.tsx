"use client";

import type { DiscoverScoreBucket } from "./types";
import { rateText } from "./utils";
import { StatusPill } from "./ui";

export default function ScoreBucketList({ rows }: { rows: DiscoverScoreBucket[] }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-elevated/40 p-3">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div>
          <div className="text-xs font-medium text-text-primary">Score Buckets</div>
          <div className="text-[11px] text-text-muted">
            Engagement by feed score band. Negative scores here are candidates for ranking review.
          </div>
        </div>
        <StatusPill tone="muted">{rows.length} buckets</StatusPill>
      </div>
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-2">
        {rows.slice(0, 8).map((row) => (
          <div key={row.bucket} className="rounded-md border border-surface-border bg-surface-card p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-text-primary">{row.bucket}</span>
              <span className={row.engagement_score < 0 ? "text-xs text-accent-danger" : "text-xs text-accent-live"}>
                {signedNumber(row.engagement_score, 2)}
              </span>
            </div>
            <div className="text-[11px] text-text-muted mt-1">
              {row.impressions.toLocaleString()} impressions
            </div>
            <div className="grid grid-cols-3 gap-1 mt-2 text-[11px]">
              <span className="text-text-secondary">Open {rateText(row.open_rate)}</span>
              <span className="text-text-secondary">Dismiss {rateText(row.dismiss_rate)}</span>
              <span className="text-text-secondary">Share {rateText(row.share_rate)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
